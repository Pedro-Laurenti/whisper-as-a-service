import asyncpg
import asyncio
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configurações de conexão ao banco de dados existente
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "whisper_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

async def get_db_conn():
    """
    Função para obter uma conexão com o banco de dados.
    Usa as configurações de ambiente para se conectar ao banco existente.
    
    Returns:
        Conexão com o banco de dados PostgreSQL
    """
    return await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )

async def test_connection():
    """
    Testa a conexão com o banco de dados.
    Útil para verificar se as configurações estão corretas.
    """
    print(f"Testando conexão ao banco de dados PostgreSQL ({DB_HOST}:{DB_PORT}, DB: {DB_NAME})...")
    
    try:
        # Tenta estabelecer uma conexão
        conn = await get_db_conn()
        await conn.execute("SELECT 1")  # Consulta simples para testar a conexão
        await conn.close()
        print("Conexão ao banco de dados estabelecida com sucesso!")
        return True
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {str(e)}")
        return False

if __name__ == "__main__":
    # Quando executado diretamente, apenas testa a conexão
    asyncio.run(test_connection())
