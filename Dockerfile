FROM python:3.10.16

WORKDIR /app

# Instala as dependências do sistema necessárias para compilar algumas bibliotecas Python
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copia os arquivos de requisitos primeiro para aproveitar o cache do Docker
COPY requirements.txt .

# Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código
COPY . .

# Cria diretório para uploads se não existir
RUN mkdir -p /app/uploads && chmod 777 /app/uploads

# Comando para iniciar a API
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8001"]

EXPOSE 8001
