# Whisper Audio Transcription API

API para transcrição de áudio usando o modelo Whisper da OpenAI.

## Requisitos

- Docker
- Docker Compose
- Banco de dados PostgreSQL (já existente)

## Configuração

1. Clone este repositório em sua VPS
2. Copie o arquivo `.env.example` para `.env` e configure as variáveis:

```bash
cp .env.example .env
nano .env
```

3. Edite o arquivo `.env` com as informações do seu banco de dados PostgreSQL

## Deployment com Docker

1. Certifique-se de que o Docker e o Docker Compose estejam instalados em sua VPS

2. Configure o banco de dados PostgreSQL e garanta que esteja acessível

3. Execute o comando para iniciar o serviço:

```bash
docker-compose up -d
```

4. Os logs podem ser verificados com:

```bash
docker-compose logs -f
```

5. A API estará disponível em `http://seu_ip:8001`

## Endpoints Principais

- `POST /transcribe` - Transcrição síncrona (para arquivos pequenos)
- `POST /transcribe/async` - Transcrição assíncrona (para arquivos maiores)
- `GET /transcribe/status/{id}` - Verificar status de transcrição assíncrona

## Cliente de Teste

Um cliente de teste está disponível no arquivo `client.py`:

```bash
python client.py --url http://seu_ip:8001 --api-key SUA_API_KEY --file caminho/para/audio.mp3 --modo assincrono
```

## Observações

- A API Key é gerada automaticamente na primeira inicialização e mostrada nos logs do contêiner.
- Os arquivos de áudio são armazenados no diretório `/uploads` que está mapeado como um volume.
- O banco de dados deve ser criado previamente antes de executar o contêiner.
