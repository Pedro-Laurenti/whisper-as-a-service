# API de Transcrição de Áudio com Whisper

Esta API permite transcrever arquivos de áudio utilizando o modelo Whisper da OpenAI. A API suporta processamento síncrono e assíncrono, gerenciamento de filas e autenticação via API Key.

## Requisitos

- Python 3.8+
- PostgreSQL 10+
- CUDA (opcional, para aceleração por GPU)

## Instalação

1. Clone o repositório:

```bash
git clone <url-do-repositorio>
cd whisper
```

2. Crie um ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate  # Windows
```

3. Instale as dependências:

```bash
pip install -r requirements.txt
```

4. Crie o arquivo `.env` com base no modelo:

```bash
cp .env.example .env
```

5. Edite o arquivo `.env` com suas configurações.

## Uso

### Iniciando a API

```bash
python api.py
```

A API estará disponível em `http://localhost:8001`.

### Swagger/OpenAPI

A documentação da API estará disponível em `http://localhost:8001/docs`.

## Endpoints da API

### Transcrição Síncrona

Processa um arquivo de áudio e retorna a transcrição imediatamente.

```
POST /transcribe
```

### Transcrição Assíncrona

Adiciona um arquivo de áudio à fila para processamento em segundo plano.

```
POST /transcribe/async
```

### Status da Transcrição

Verifica o status e o resultado de uma transcrição assíncrona.

```
GET /transcribe/status/{id}
```

### Gerenciamento de API Keys

Criar uma nova API Key:

```
POST /admin/api-keys
```

Listar API Keys:

```
GET /admin/api-keys
```

Revogar uma API Key:

```
POST /admin/api-keys/revoke
```

## Formatos de Áudio Suportados

- `.mp3`
- `.mp4`
- `.mpeg`
- `.mpga`
- `.m4a`
- `.wav`
- `.webm`

## Notas sobre desempenho

- Para arquivos grandes, é recomendado utilizar a API de transcrição assíncrona.
- O desempenho da transcrição depende do tamanho do modelo e do hardware utilizado.
- As configurações do modelo podem ser ajustadas no arquivo `.env`.

## Segurança

Todos os endpoints são protegidos por autenticação via API Key, que deve ser enviada no cabeçalho `X-API-Key` de cada requisição.

## Licença

[Inserir licença aqui]

## Contribuição

[Instruções para contribuição]
