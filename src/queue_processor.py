import os
import asyncio
import aiofiles
from typing import List, Dict, Any, Optional
import asyncpg
import datetime
import whisper
import tempfile
from dotenv import load_dotenv
import logging
from src.init_db import get_db_conn

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "whisper_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

# Diretório para armazenar arquivos de áudio
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Modelo Whisper a ser carregado (tiny, base, small, medium, large)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

# Inicialização do modelo Whisper
model = None

# A função get_db_conn agora é importada do módulo init_db

async def inicializar_modelo():
    """
    Inicializa o modelo Whisper em uma thread separada para não bloquear a thread principal.
    Inclui mecanismo de retry em caso de falha.
    """
    global model
    
    max_attempts = 3
    current_attempt = 0
    
    while current_attempt < max_attempts:
        current_attempt += 1
        try:
            logger.info(f"Carregando modelo Whisper '{WHISPER_MODEL}' (tentativa {current_attempt}/{max_attempts})...")
            loop = asyncio.get_event_loop()
            
            # Inicializando o modelo em uma thread separada
            model = await loop.run_in_executor(None, lambda: whisper.load_model(WHISPER_MODEL))
            
            if model:
                logger.info(f"Modelo Whisper '{WHISPER_MODEL}' carregado com sucesso!")
                return model
            else:
                logger.error(f"Falha ao carregar o modelo Whisper (resultado nulo)")
        except Exception as e:
            logger.error(f"Erro ao carregar modelo Whisper: {str(e)}")
            if current_attempt < max_attempts:
                wait_time = 5 * current_attempt  # Aumenta o tempo de espera entre tentativas
                logger.info(f"Tentando novamente em {wait_time} segundos...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Falha ao inicializar o modelo Whisper após {max_attempts} tentativas")
                raise
    
    return model

async def salvar_arquivo_audio(audio_bytes: bytes, nome_arquivo: str) -> str:
    """
    Salva um arquivo de áudio no sistema de arquivos.
    
    Args:
        audio_bytes: Os bytes do arquivo de áudio
        nome_arquivo: Nome do arquivo usado apenas para a extensão
        
    Returns:
        Caminho do arquivo salvo
    """
    # Cria um caminho único para o arquivo
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    # Extrai a extensão do nome do arquivo original
    extensao = os.path.splitext(nome_arquivo)[1] if '.' in nome_arquivo else '.audio'
    nome_arquivo_seguro = f"{timestamp}{extensao}"
    caminho_arquivo = os.path.join(UPLOAD_DIR, nome_arquivo_seguro)
    
    # Salva o arquivo
    async with aiofiles.open(caminho_arquivo, 'wb') as f:
        await f.write(audio_bytes)
    
    return caminho_arquivo

async def enqueue_transcription(audio_bytes: bytes, nome_arquivo: str, idioma: Optional[str] = 'pt') -> Dict[str, Any]:
    """
    Adiciona uma transcrição à fila para processamento.
    
    Args:
        audio_bytes: Os bytes do arquivo de áudio
        nome_arquivo: Nome do arquivo (usado apenas para manter a extensão)
        idioma: Idioma do áudio (opcional, padrão é 'pt')
    
    Returns:
        Informações sobre a transcrição enfileirada
    """
    # Salva o arquivo
    caminho_arquivo = await salvar_arquivo_audio(audio_bytes, nome_arquivo)
    
    # Adiciona à fila no banco de dados
    conn = await get_db_conn()
    try:
        result = await conn.fetchrow(
            """
            INSERT INTO transcricoes (caminho_arquivo, idioma, status)
            VALUES ($1, $2, 'waiting')
            RETURNING id, caminho_arquivo, idioma, status, data_envio
            """,
            caminho_arquivo, idioma
        )
        
        # Extrai apenas o nome do arquivo do caminho para retornar na resposta
        nome_arquivo_extraido = os.path.basename(caminho_arquivo)
        
        return {
            "id": result["id"],
            "caminho_arquivo": result["caminho_arquivo"],
            "nome_arquivo": nome_arquivo_extraido,  # Apenas para compatibilidade na resposta
            "idioma": result["idioma"],
            "status": result["status"],
            "data_envio": result["data_envio"].isoformat(),
            "mensagem": "Arquivo adicionado à fila de transcrição"
        }
    finally:
        await conn.close()

async def execute_sync_transcription(audio_bytes: bytes, nome_arquivo: str, idioma: Optional[str] = 'pt') -> Dict[str, Any]:
    """
    Executa uma transcrição de forma síncrona.
    
    Args:
        audio_bytes: Os bytes do arquivo de áudio
        nome_arquivo: Nome do arquivo (usado apenas para referência de registro)
        idioma: Idioma do áudio (opcional, padrão 'pt')
        
    Returns:
        Resultados da transcrição
    """
    global model
    
    # Garante que o modelo está inicializado
    if model is None:
        await inicializar_modelo()
    
    # Verifica se o ffmpeg está instalado
    import shutil
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg não encontrado no sistema. Por favor instale ffmpeg para processar áudios.")
    
    # Salva o arquivo em um diretório temporário
    with tempfile.NamedTemporaryFile(suffix=f"_{nome_arquivo}", delete=False) as temp:
        temp.write(audio_bytes)
        temp_path = temp.name
    
    try:
        # Inicializa os parâmetros de transcrição
        transcribe_options = {}
        if idioma:
            transcribe_options["language"] = idioma
        
        # Executa a transcrição em uma thread separada
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: model.transcribe(temp_path, **transcribe_options)
        )
        
        return {
            "nome_arquivo": os.path.basename(temp_path),  # Nome derivado do caminho temporário
            "idioma_detectado": result.get("language"),
            "texto": result.get("text"),
            "duracao": result.get("duration", 0),
            "segments": [
                {
                    "id": seg.get("id"),
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text")
                }
                for seg in result.get("segments", [])
            ]
        }
    except Exception as e:
        logger.error(f"Erro na transcrição síncrona: {str(e)}")
        raise
    finally:
        # Limpa o arquivo temporário
        if os.path.exists(temp_path):
            os.remove(temp_path)

async def processa_transcrição(transcricao_id: int):
    """
    Processa uma transcrição da fila.
    
    Args:
        transcricao_id: ID da transcrição a processar
    """
    global model
    
    conn = await get_db_conn()
    try:
        # Busca a informação da transcrição
        transcricao = await conn.fetchrow(
            """
            SELECT id, caminho_arquivo, idioma
            FROM transcricoes
            WHERE id = $1 AND status = 'waiting'
            """,
            transcricao_id
        )
        
        if not transcricao:
            logger.warning(f"Transcrição ID {transcricao_id} não encontrada ou não está no status 'waiting'")
            return
        
        # Atualiza status para 'processing'
        await conn.execute(
            """
            UPDATE transcricoes
            SET status = 'processing', data_processamento = NOW()
            WHERE id = $1
            """,
            transcricao_id
        )
        
        try:
            # Garante que o modelo está inicializado
            if model is None:
                logger.info(f"Modelo não inicializado para transcrição ID {transcricao_id}. Inicializando...")
                await inicializar_modelo()
                if model is None:
                    raise RuntimeError("Falha ao inicializar o modelo Whisper")
            
            # Verifica se o ffmpeg está instalado
            import shutil
            if shutil.which("ffmpeg") is None:
                raise FileNotFoundError("ffmpeg não encontrado no sistema. Por favor instale ffmpeg para processar áudios.")
            
            # Lê o arquivo
            caminho_arquivo = transcricao["caminho_arquivo"]
            
            # Verifica se o arquivo existe
            if not os.path.exists(caminho_arquivo):
                raise FileNotFoundError(f"Arquivo não encontrado: {caminho_arquivo}")
            
            # Inicializa os parâmetros de transcrição
            transcribe_options = {}
            if transcricao["idioma"]:
                transcribe_options["language"] = transcricao["idioma"]
            
            # Log para debug
            logger.info(f"Iniciando transcrição do arquivo {caminho_arquivo} (ID: {transcricao_id})")
            
            # Executa a transcrição em uma thread separada
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: model.transcribe(caminho_arquivo, **transcribe_options)
                )
                
                if not result or not isinstance(result, dict):
                    raise ValueError("Resultado da transcrição inválido ou vazio")
                
                # Atualiza o resultado no banco de dados
                await conn.execute(
                    """
                    UPDATE transcricoes
                    SET status = 'done',
                        texto = $1,
                        idioma = $2,
                        duracao = $3
                    WHERE id = $4
                    """,
                    result.get("text"),
                    result.get("language"),
                    result.get("duration", 0),
                    transcricao_id
                )
                
                logger.info(f"Transcrição ID {transcricao_id} concluída com sucesso!")
            except Exception as transcribe_error:
                logger.error(f"Erro durante a transcrição ID {transcricao_id}: {str(transcribe_error)}")
                raise transcribe_error
            
        except Exception as e:
            logger.error(f"Erro ao processar transcrição ID {transcricao_id}: {str(e)}")
            
            # Atualiza status para 'error' com informações do erro
            await conn.execute(
                """
                UPDATE transcricoes
                SET status = 'error',
                    texto = $1
                WHERE id = $2
                """,
                f"Erro: {str(e)}",
                transcricao_id
            )
            # Re-lança a exceção para que seja tratada pelo chamador
            raise
    finally:
        await conn.close()

async def get_transcription_status(transcricao_id: int) -> Dict[str, Any]:
    """
    Verifica o status de uma transcrição.
    
    Args:
        transcricao_id: ID da transcrição
        
    Returns:
        Informações sobre a transcrição
        
    Raises:
        ValueError: Se a transcrição não for encontrada
    """
    conn = await get_db_conn()
    try:
        # Busca a informação da transcrição
        result = await conn.fetchrow(
            """
            SELECT id, caminho_arquivo, idioma, status, data_envio, data_processamento, duracao, texto
            FROM transcricoes
            WHERE id = $1
            """,
            transcricao_id
        )
        
        if not result:
            raise ValueError(f"Transcrição ID {transcricao_id} não encontrada")
        
        # Extrai o nome do arquivo do caminho para manter compatibilidade na resposta
        nome_arquivo = os.path.basename(result["caminho_arquivo"])
        
        resposta = {
            "id": result["id"],
            "caminho_arquivo": result["caminho_arquivo"],
            "nome_arquivo": nome_arquivo,  # Adicionado para compatibilidade
            "idioma": result["idioma"],
            "status": result["status"],
            "data_envio": result["data_envio"].isoformat(),
            "data_processamento": result["data_processamento"].isoformat() if result["data_processamento"] else None,
            "duracao": result["duracao"]
        }
        
        # Inclui o texto apenas se a transcrição estiver concluída
        if result["status"] == "done":
            resposta["texto"] = result["texto"]
        
        return resposta
    finally:
        await conn.close()

async def processar_fila():
    """
    Função principal de processamento da fila de transcrições.
    Executa em um loop contínuo, buscando transcrições pendentes.
    """
    await inicializar_modelo()
    
    logger.info("Iniciando processador de fila de transcrições...")
    
    while True:
        try:
            # Busca próxima transcrição pendente
            conn = await get_db_conn()
            try:
                transcricao = await conn.fetchrow(
                    """
                    SELECT id FROM transcricoes
                    WHERE status = 'waiting'
                    ORDER BY data_envio ASC
                    LIMIT 1
                    """
                )
                
                if transcricao:
                    # Processa a transcrição
                    try:
                        await processa_transcrição(transcricao["id"])
                        # Adiciona um pequeno atraso entre processamentos para garantir 
                        # a estabilidade dos recursos
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Erro ao processar transcrição ID {transcricao['id']}: {str(e)}")
                        # Não interrompe o processador de fila em caso de erro em um item
                        # Aguarda um pouco antes de processar o próximo para dar tempo de recursos se recuperarem
                        await asyncio.sleep(3)
                else:
                    # Se não houver transcrições pendentes, aguarda um pouco
                    await asyncio.sleep(5)
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"Erro no processador de fila: {str(e)}")
            # Reinicializa o modelo em caso de erro grave
            try:
                global model
                model = None
                await inicializar_modelo()
            except Exception as model_error:
                logger.error(f"Falha ao reinicializar o modelo: {str(model_error)}")
            await asyncio.sleep(10)  # Aguarda um pouco mais se ocorrer um erro

async def start_queue_processor():
    """
    Inicia o processador de fila em uma task separada.
    """
    asyncio.create_task(processar_fila())
