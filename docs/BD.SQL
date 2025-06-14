CREATE TABLE transcricoes (
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

CREATE TABLE api_keys (
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
