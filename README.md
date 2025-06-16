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

```bash
docker-compose up -d
```

### Ver logs dos serviços

Para ver os logs de todos os serviços:

```bash
docker-compose logs -f
```

### Parar os serviços

```bash
docker-compose down
```

## Reconstruindo após alterações no código

Se você fez alterações no código-fonte, é necessário reconstruir as imagens:

```bash
# Pare os containers
docker-compose down

# Reconstrua sem usar cache
docker-compose build --no-cache

# Inicie novamente
docker-compose up -d

# Verifique os logs para confirmar que está funcionando corretamente
docker-compose logs -f
```

Para aplicar apenas as alterações do arquivo .env sem reiniciar completamente:

```bash
docker-compose down
docker-compose up -d
```
A API estará disponível em `http://seu_ip:PORTA`, onde PORTA é a definida na variável API_PORT (padrão: 8002)

## Endpoints Principais

- `POST /transcribe` - Transcrição síncrona (para arquivos pequenos)
- `POST /transcribe/async` - Transcrição assíncrona (para arquivos maiores)
- `GET /transcribe/status/{id}` - Verificar status de transcrição assíncrona

## Cliente de Teste

Um cliente de teste está disponível no arquivo `client.py`:

```bash
python client.py --url http://seu_ip:PORTA --api-key SUA_API_KEY --file caminho/para/audio.mp3 --modo assincrono
```

Substitua PORTA pela porta configurada na variável API_PORT no arquivo .env

## Observações

- A API Key é gerada automaticamente na primeira inicialização e mostrada nos logs do contêiner.
- Os arquivos de áudio são armazenados no diretório `/uploads` que está mapeado como um volume.
- O banco de dados deve ser criado previamente antes de executar o contêiner.
