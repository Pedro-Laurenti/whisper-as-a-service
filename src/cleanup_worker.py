import os
import asyncio
import datetime
import logging
from typing import List

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Diretório dos arquivos de upload
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")

async def cleanup_old_files(max_age_days: int = 1) -> List[str]:
    """
    Remove arquivos de áudio com idade maior que max_age_days da pasta de uploads.
    
    Args:
        max_age_days: Idade máxima dos arquivos em dias (padrão: 1)
        
    Returns:
        Lista com os nomes dos arquivos removidos
    """
    try:
        if not os.path.exists(UPLOAD_DIR):
            logger.warning(f"Diretório de uploads '{UPLOAD_DIR}' não existe.")
            return []
        
        now = datetime.datetime.now()
        removed_files = []
        
        # Percorre todos os arquivos na pasta de uploads
        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            
            # Verifica se é um arquivo (não um diretório)
            if os.path.isfile(file_path):
                # Obtém o timestamp de modificação do arquivo
                file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                file_age = now - file_mtime
                
                # Remove se o arquivo for mais antigo que max_age_days
                if file_age.days >= max_age_days:
                    try:
                        os.remove(file_path)
                        removed_files.append(filename)
                        logger.info(f"Arquivo removido: {filename} (idade: {file_age.days} dias)")
                    except Exception as e:
                        logger.error(f"Erro ao remover arquivo {filename}: {str(e)}")
        
        logger.info(f"Limpeza concluída: {len(removed_files)} arquivos removidos.")
        return removed_files
    
    except Exception as e:
        logger.error(f"Erro ao executar limpeza de arquivos: {str(e)}")
        return []

async def run_cleanup_worker(interval_hours: int = 1):
    """
    Executa o worker de limpeza periodicamente no intervalo especificado.
    
    Args:
        interval_hours: Intervalo entre execuções em horas (padrão: 1)
    """
    logger.info(f"Worker de limpeza de arquivos iniciado. Intervalo: {interval_hours} hora(s)")
    while True:
        try:
            files_removed = await cleanup_old_files()
            logger.info(f"Próxima execução do worker de limpeza em {interval_hours} hora(s)")
        except Exception as e:
            logger.error(f"Erro no worker de limpeza: {str(e)}")
        
        # Aguarda o intervalo configurado
        await asyncio.sleep(interval_hours * 3600)  # Converte horas para segundos

async def start_cleanup_worker(interval_hours: int = 1):
    """
    Inicia o worker de limpeza em uma task separada.
    
    Args:
        interval_hours: Intervalo entre execuções em horas (padrão: 1)
    """
    asyncio.create_task(run_cleanup_worker(interval_hours))
