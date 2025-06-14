import asyncpg
import asyncio
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "whisper_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")

async def init_db():
    print(f"Conectando ao banco de dados PostgreSQL ({DB_HOST}:{DB_PORT}, DB: {DB_NAME})...")
    
    # Conecta primeiro ao banco de dados 'postgres' para poder criar o banco whisper_db caso não exista
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database="postgres"
    )
    
    # Verifica se o banco de dados já existe
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = $1)",
        DB_NAME
    )
    
    # Se não existir, cria o banco de dados
    if not exists:
        print(f"Criando o banco de dados '{DB_NAME}'...")
        await conn.execute(f"CREATE DATABASE {DB_NAME}")
    
    await conn.close()
    
    # Agora conecta ao banco de dados que acabamos de criar/verificar
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    
    # Cria as tabelas se não existirem
    schema_sql = """
    CREATE TABLE IF NOT EXISTS transcricoes (
        id SERIAL PRIMARY KEY,
        nome_arquivo TEXT NOT NULL,
        caminho_arquivo TEXT NOT NULL,
        duracao INTEGER,
        idioma TEXT,
        data_envio TIMESTAMP DEFAULT now(),
        data_processamento TIMESTAMP,
        status TEXT CHECK (status IN ('waiting', 'processing', 'error', 'concluido')),
        texto TEXT,
        api_key_id INTEGER
    );

    CREATE TABLE IF NOT EXISTS api_keys (
        id SERIAL PRIMARY KEY,
        key_hash TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMP,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        last_used_at TIMESTAMP,
        use_count INTEGER NOT NULL DEFAULT 0,
        allowed_ips TEXT[]
    );
    """
    
    await conn.execute(schema_sql)
    print("Tabelas verificadas/criadas com sucesso!")
    
    await conn.close()
    print("Inicialização do banco de dados concluída!")

if __name__ == "__main__":
    asyncio.run(init_db())
