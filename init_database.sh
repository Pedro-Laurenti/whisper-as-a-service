#!/bin/bash
set -e

# Este script facilita a inicialização do banco de dados
# Ele pode ser executado manualmente na VPS se necessário

# Carregando variáveis de ambiente
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else 
    echo "Arquivo .env não encontrado!"
    exit 1
fi

echo "Executando inicialização do banco de dados..."
python -m src.init_db

echo "Inicialização completa!"
