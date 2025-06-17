from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security, status, UploadFile, File, Form, Request
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
import uvicorn
import asyncio
import secrets
import shutil
import subprocess
from typing import Optional, List, Dict, Any
from src.queue_processor import (
    execute_sync_transcription, enqueue_transcription, get_transcription_status,
    start_queue_processor, inicializar_modelo
)
from src.security import (
    get_api_key
)
from src.cleanup_worker import start_cleanup_worker
from contextlib import asynccontextmanager
import os
import base64
import re
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

def is_base64(s):
    """
    Verifica se uma string é base64 válida
    
    Args:
        s (str): String a ser verificada
        
    Returns:
        bool: True se a string for base64 válida, False caso contrário
    """
    try:
        # Verifica se a string é válida como base64
        if not isinstance(s, str):
            return False
        
        # Remove possíveis prefixos de data URI
        if s.startswith('data:'):
            s = s.split(',', 1)[1]
        
        # Tenta decodificar e verifica se é um áudio
        decoded = base64.b64decode(s)
        # Verificação básica se pode ser um arquivo de áudio (tem pelo menos alguns bytes)
        return len(decoded) > 100
    except Exception:
        return False

def decode_base64_to_audio(base64_string):
    """
    Decodifica uma string base64 para bytes de áudio
    
    Args:
        base64_string (str): String base64 para decodificar
        
    Returns:
        bytes: Bytes do áudio decodificado
    """
    # Remove possíveis prefixos de data URI
    if base64_string.startswith('data:'):
        base64_string = base64_string.split(',', 1)[1]
    
    # Decodifica a string base64 para bytes
    return base64.b64decode(base64_string)

def get_ffmpeg_install_command():
    """
    Retorna o comando para instalar ffmpeg com base no sistema operacional
    
    Returns:
        str: Comando de instalação para ffmpeg
    """
    import platform
    
    system = platform.system().lower()
    
    if system == "linux":
        # Tenta detectar a distribuição Linux
        try:
            with open("/etc/os-release") as f:
                os_info = {}
                for line in f:
                    if "=" in line:
                        k, v = line.rstrip().split("=", 1)
                        os_info[k] = v.strip('"')
            
            if "ID" in os_info:
                distro = os_info["ID"].lower()
                if distro in ["ubuntu", "debian", "linuxmint"]:
                    return "sudo apt update && sudo apt install -y ffmpeg"
                elif distro in ["fedora", "rhel", "centos"]:
                    return "sudo dnf install -y ffmpeg"
                elif distro in ["arch", "manjaro"]:
                    return "sudo pacman -S ffmpeg"
                elif distro == "opensuse":
                    return "sudo zypper install ffmpeg"
        except Exception:
            pass
        
        # Caso não consiga detectar a distribuição específica
        return "Instale o ffmpeg usando o gerenciador de pacotes da sua distribuição Linux"
    
    elif system == "darwin":  # macOS
        return "brew install ffmpeg"
    
    elif system == "windows":
        return "winget install ffmpeg (ou baixe em https://ffmpeg.org/download.html)"
    
    else:
        return "Baixe o ffmpeg em https://ffmpeg.org/download.html"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verifica se ffmpeg está instalado no sistema
    ffmpeg_installed = shutil.which("ffmpeg") is not None
    if not ffmpeg_installed:
        install_cmd = get_ffmpeg_install_command()
        print(f"\n{'='*60}")
        print(f" ERRO: ffmpeg não encontrado!")
        print(f" O Whisper requer ffmpeg para processar áudios.")
        print(f" Por favor, instale ffmpeg usando o comando:")
        print(f" {install_cmd}")
        print(f"{'='*60}\n")
        logger.error("ffmpeg não encontrado! A API não funcionará corretamente sem ffmpeg instalado.")
    else:
        logger.info("ffmpeg encontrado no sistema.")

    # Inicializa o modelo Whisper na inicialização
    await inicializar_modelo()
    
    # Iniciar o processador de fila
    await start_queue_processor()
    
    # Iniciar o worker de limpeza de arquivos (executa a cada 24 horas)
    logger.info("Iniciando worker de limpeza de arquivos antigos...")
    await start_cleanup_worker(interval_hours=24)
    logger.info("Worker de limpeza iniciado com sucesso!")
    
    # NOTA: A criação de API Keys agora é gerenciada pelo serviço separado "api-keys-manager"
    # Se precisar criar uma API Key, use o serviço dedicado
    
    # Verifica se o ffmpeg está disponível
    if not shutil.which("ffmpeg"):
        logger.warning("O ffmpeg não está instalado ou não está no PATH do sistema. Algumas funcionalidades podem não funcionar corretamente.")
    
    logger.info("Sistema de Transcrição de Áudio iniciado!")
    yield
    logger.info("Sistema de Transcrição de Áudio encerrado!")

app = FastAPI(
    title="Whisper Audio Transcription API",
    description="API para transcrição de áudio usando o modelo Whisper",
    version="1.0.0",
    lifespan=lifespan
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def validate_api_key_dependency(request: Request, api_key: str = Security(api_key_header)):
    """
    Função de dependência para validar a API Key.
    
    Args:
        request: Request do FastAPI
        api_key: Valor do cabeçalho X-API-Key
    
    Returns:
        A API Key validada
    
    Raises:
        HTTPException: Se a API Key for inválida ou não for fornecida
    """
    # O auto_error=True já garante que api_key não seja None
    # mas vamos verificar por garantia
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key não fornecida. Inclua um cabeçalho 'X-API-Key' com uma chave válida.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Valida a API Key usando a função existente
    return await get_api_key(api_key, request)

class TranscriptionRequest(BaseModel):
    idioma: Optional[str] = None
    
class AudioTranscriptionRequest(BaseModel):
    audio: str  # Conteúdo do áudio em base64
    nome_arquivo: Optional[str] = "audio.opus"  # Nome do arquivo, com extensão
    idioma: Optional[str] = None  # Idioma do áudio (opcional)

@app.post("/transcribe")
async def transcribe(
    request: Request,
    file: Optional[UploadFile] = File(None),
    idioma: Optional[str] = Form(None),
    api_key: str = Depends(validate_api_key_dependency)
):
    """
    Executa uma transcrição síncrona (bloqueante) e retorna os resultados diretamente.
    Ideal para arquivos pequenos que não exigem muito tempo de processamento.
    Aceita tanto arquivo upload quanto JSON com áudio em base64.
    
    Requer uma API Key válida no cabeçalho X-API-Key.
    """
    try:
        # Verifica se é uma requisição JSON (base64) ou multipart (upload de arquivo)
        content_type = request.headers.get('content-type', '')
        
        if content_type.startswith('application/json'):
            # Processa como JSON com áudio em base64
            data = await request.json()
            if not isinstance(data, dict) or 'audio' not in data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Formato JSON inválido. Esperado campo 'audio' com conteúdo em base64."
                )
            
            audio_base64 = data.get('audio')
            nome_arquivo = data.get('nome_arquivo', 'audio.opus')
            idioma_param = data.get('idioma', idioma)
            
            # Verifica e decodifica o áudio em base64
            if not is_base64(audio_base64):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Conteúdo de áudio base64 inválido."
                )
            
            # Decodifica o base64 para bytes
            audio_bytes = decode_base64_to_audio(audio_base64)
            
        else:
            # Processa como upload de arquivo
            if not file:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Nenhum arquivo enviado ou formato de requisição inválido"
                )
            
            # Verifica se o arquivo é um tipo de áudio suportado
            file_extension = os.path.splitext(file.filename)[1].lower()
            supported_extensions = ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.opus']
            
            if file_extension not in supported_extensions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Formato de arquivo não suportado. Formatos suportados: {', '.join(supported_extensions)}"
                )
            
            # Lê o conteúdo do arquivo
            audio_bytes = await file.read()
            nome_arquivo = file.filename
            idioma_param = idioma
        
        # Usa a função do queue_processor para executar a transcrição síncrona
        try:
            results = await execute_sync_transcription(
                audio_bytes=audio_bytes,
                nome_arquivo=nome_arquivo,
                idioma=idioma_param
            )
            
            return results
        except FileNotFoundError as e:
            if "ffmpeg" in str(e):
                install_cmd = get_ffmpeg_install_command()
                error_detail = f"ffmpeg não encontrado. Por favor, instale ffmpeg usando o comando: {install_cmd}"
                logger.error(error_detail)
                raise HTTPException(status_code=500, detail=error_detail)
            else:
                raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro na transcrição síncrona: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe/async")
async def transcribe_async(
    request: Request,
    file: Optional[UploadFile] = File(None),
    idioma: Optional[str] = Form(None),
    api_key: str = Depends(validate_api_key_dependency)
):
    """
    Adiciona um arquivo de áudio à fila de processamento para ser transcrito de forma assíncrona.
    Retorna imediatamente com um ID de transcrição para verificação posterior.
    Ideal para arquivos maiores que podem demorar mais tempo para processar.
    Aceita tanto arquivo upload quanto JSON com áudio em base64.
    
    Requer uma API Key válida no cabeçalho X-API-Key.
    """
    try:
        # Verifica se é uma requisição JSON (base64) ou multipart (upload de arquivo)
        content_type = request.headers.get('content-type', '')
        
        if content_type.startswith('application/json'):
            # Processa como JSON com áudio em base64
            data = await request.json()
            if not isinstance(data, dict) or 'audio' not in data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Formato JSON inválido. Esperado campo 'audio' com conteúdo em base64."
                )
            
            audio_base64 = data.get('audio')
            nome_arquivo = data.get('nome_arquivo', 'audio.opus')
            idioma_param = data.get('idioma', idioma)
            
            # Verifica e decodifica o áudio em base64
            if not is_base64(audio_base64):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Conteúdo de áudio base64 inválido."
                )
            
            # Decodifica o base64 para bytes
            audio_bytes = decode_base64_to_audio(audio_base64)
            
        else:
            # Processa como upload de arquivo
            if not file:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Nenhum arquivo enviado ou formato de requisição inválido"
                )
            
            # Verifica se o arquivo é um tipo de áudio suportado
            file_extension = os.path.splitext(file.filename)[1].lower()
            supported_extensions = ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.opus']
            
            if file_extension not in supported_extensions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Formato de arquivo não suportado. Formatos suportados: {', '.join(supported_extensions)}"
                )
            
            # Lê o conteúdo do arquivo
            audio_bytes = await file.read()
            nome_arquivo = file.filename
            idioma_param = idioma
        
        # Verifica se o ffmpeg está instalado antes de enfileirar
        if not shutil.which("ffmpeg"):
            install_cmd = get_ffmpeg_install_command()
            error_detail = f"ffmpeg não encontrado. Por favor, instale ffmpeg usando o comando: {install_cmd}"
            logger.error(error_detail)
            raise HTTPException(status_code=500, detail=error_detail)
        
        # Adiciona a transcrição à fila de processamento
        result = await enqueue_transcription(
            audio_bytes=audio_bytes,
            nome_arquivo=nome_arquivo,
            idioma=idioma_param
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao enfileirar transcrição: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcribe/status/{transcricao_id}")
async def get_transcribe_status(transcricao_id: int, request: Request, api_key: str = Depends(validate_api_key_dependency)):
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

# NOTA: API Key management endpoints have been moved to a separate service: api-keys-manager
# Only endpoints related to transcription remain in this service

if __name__ == "__main__":
    # Obter a porta da variável de ambiente API_PORT ou usar 8002 como padrão
    api_port = int(os.getenv("API_PORT", "8002"))
    uvicorn.run("api:app", host="0.0.0.0", port=api_port, reload=True)
