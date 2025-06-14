from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security, status, UploadFile, File, Form, Request
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
import uvicorn
import asyncio
import secrets
from typing import Optional, List, Dict, Any
from src.queue_processor import (
    execute_sync_transcription, enqueue_transcription, get_transcription_status,
    start_queue_processor, inicializar_modelo
)
from src.security import (
    get_api_key, generate_api_key, 
    revoke_api_key, get_api_keys
)
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa o modelo Whisper na inicialização
    await inicializar_modelo()
    
    # Iniciar o processador de fila
    await start_queue_processor()
    
    # Verifica se existe alguma API Key ativa
    keys = await get_api_keys(active_only=True)
    
    # Se não existir nenhuma API Key ativa, cria uma padrão
    if not keys:
        # Recarrega as variáveis de ambiente para garantir que temos os valores mais recentes
        load_dotenv()
        
        # Obtém configurações do arquivo .env
        default_name = os.getenv("DEFAULT_API_KEY_NAME", "API Default")
        default_expires = int(os.getenv("DEFAULT_API_KEY_EXPIRES_DAYS", "365"))
        default_ips_str = os.getenv("DEFAULT_API_KEY_ALLOWED_IPS", "")
        
        # Converte string de IPs para lista (se não estiver vazia)
        default_ips = [ip.strip() for ip in default_ips_str.split(",")] if default_ips_str else None
        
        # Cria a API Key padrão
        key_info = await generate_api_key(
            name=default_name,
            expires_days=default_expires,
            allowed_ips=default_ips
        )
        
        print(f"\n{'='*60}")
        print(f" API KEY GERADA: {key_info['api_key']}")
        print(f" GUARDE ESTA CHAVE EM LOCAL SEGURO!")
        print(f" Nome: {key_info['name']}")
        print(f" Criada em: {key_info['created_at']}")
        print(f" Expira em: {key_info['expires_at']}")
        print(f"{'='*60}\n")
    
    logger.info("Sistema de Transcrição de Áudio iniciado!")
    yield
    logger.info("Sistema de Transcrição de Áudio encerrado!")

app = FastAPI(
    title="Whisper Audio Transcription API",
    description="API para transcrição de áudio usando o modelo Whisper",
    version="1.0.0",
    lifespan=lifespan
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

class TranscriptionRequest(BaseModel):
    idioma: Optional[str] = None

class APIKeyRequest(BaseModel):
    name: str
    expires_days: Optional[int] = 365  # Validade em dias, padrão de 1 ano
    allowed_ips: Optional[List[str]] = None  # Lista de IPs permitidos (opcional)

class RevokeRequest(BaseModel):
    key_id: int

@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    idioma: Optional[str] = Form(None),
    api_key: str = Security(api_key_header)
):
    """
    Executa uma transcrição síncrona (bloqueante) e retorna os resultados diretamente.
    Ideal para arquivos pequenos que não exigem muito tempo de processamento.
    
    Requer uma API Key válida no cabeçalho X-API-Key.
    """
    try:
        # Verifica se o arquivo é um tipo de áudio suportado
        file_extension = os.path.splitext(file.filename)[1].lower()
        supported_extensions = ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm']
        
        if file_extension not in supported_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Formato de arquivo não suportado. Formatos suportados: {', '.join(supported_extensions)}"
            )
        
        # Lê o conteúdo do arquivo
        audio_bytes = await file.read()
        
        # Usa a função do queue_processor para executar a transcrição síncrona
        results = await execute_sync_transcription(
            audio_bytes=audio_bytes,
            nome_arquivo=file.filename,
            idioma=idioma
        )
        
        return results
    except Exception as e:
        logger.error(f"Erro na transcrição síncrona: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe/async")
async def transcribe_async(
    file: UploadFile = File(...),
    idioma: Optional[str] = Form(None),
    api_key: str = Security(api_key_header)
):
    """
    Adiciona um arquivo de áudio à fila de processamento para ser transcrito de forma assíncrona.
    Retorna imediatamente com um ID de transcrição para verificação posterior.
    Ideal para arquivos maiores que podem demorar mais tempo para processar.
    
    Requer uma API Key válida no cabeçalho X-API-Key.
    """
    try:
        # Verifica se o arquivo é um tipo de áudio suportado
        file_extension = os.path.splitext(file.filename)[1].lower()
        supported_extensions = ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm']
        
        if file_extension not in supported_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Formato de arquivo não suportado. Formatos suportados: {', '.join(supported_extensions)}"
            )
        
        # Lê o conteúdo do arquivo
        audio_bytes = await file.read()
        
        # Adiciona a transcrição à fila de processamento
        result = await enqueue_transcription(
            audio_bytes=audio_bytes,
            nome_arquivo=file.filename,
            idioma=idioma
        )
        
        return result
    except Exception as e:
        logger.error(f"Erro ao enfileirar transcrição: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcribe/status/{transcricao_id}")
async def get_transcribe_status(transcricao_id: int, api_key: str = Security(api_key_header)):
    """
    Verifica o status de uma transcrição assíncrona pelo ID.
    Retorna detalhes sobre o progresso e conclusão da transcrição.
    
    Requer uma API Key válida no cabeçalho X-API-Key.
    """
    try:
        status = await get_transcription_status(transcricao_id)
        return status
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao verificar status da transcrição: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Endpoints para gerenciar API Keys (com proteção especial)
@app.post("/admin/api-keys", status_code=status.HTTP_201_CREATED)
async def create_key(request: APIKeyRequest):
    """
    Cria uma nova API Key.
    
    Este endpoint deve ser protegido por senha ou estar em uma rede segura.
    Em um ambiente de produção, seria melhor adicionar autenticação adicional aqui.
    """
    try:
        result = await generate_api_key(
            name=request.name,
            expires_days=request.expires_days,
            allowed_ips=request.allowed_ips
        )
        return result
    except Exception as e:
        logger.error(f"Erro ao criar API Key: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/api-keys")
async def list_keys(active_only: bool = False):
    """
    Lista todas as API Keys.
    
    Este endpoint deve ser protegido por senha ou estar em uma rede segura.
    Em um ambiente de produção, seria melhor adicionar autenticação adicional aqui.
    """
    try:
        keys = await get_api_keys(active_only)
        return {"keys": keys, "count": len(keys)}
    except Exception as e:
        logger.error(f"Erro ao listar API Keys: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/api-keys/revoke")
async def revoke_key(request: RevokeRequest):
    """
    Revoga (desativa) uma API Key.
    
    Este endpoint deve ser protegido por senha ou estar em uma rede segura.
    Em um ambiente de produção, seria melhor adicionar autenticação adicional aqui.
    """
    try:
        success = await revoke_api_key(request.key_id)
        if not success:
            raise HTTPException(status_code=404, detail="API Key não encontrada")
        return {"message": "API Key revogada com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao revogar API Key: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=True)
