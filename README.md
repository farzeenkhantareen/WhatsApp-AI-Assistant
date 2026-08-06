# WhatsApp AI Assistant

Production-ready WhatsApp chatbot built with **FastAPI**, **Evolution API**, and **OpenRouter**.

The assistant receives WhatsApp messages through Evolution webhooks, replies with an OpenRouter LLM, stores full conversation history in **PostgreSQL**, and caches recent turns in **Redis**.

## Architecture

```text
WhatsApp  -->  Evolution API (Baileys)  -->  POST /webhook  -->  FastAPI backend
                                                      |                |
                                                      |                +--> OpenRouter
                                                      |                +--> Redis (hot memory)
                                                      +------------------> PostgreSQL (durable history)
FastAPI  -->  Evolution sendText / sendMedia / presence / read receipts
```

| Component | Role |
|-----------|------|
| `backend` | FastAPI app: webhook intake, AI replies, REST API |
| `evolution-api` | WhatsApp multi-tenant REST bridge (v2.3.7) |
| `postgres` | App DB (`whatsapp_ai`) + Evolution DB (`evolution`) |
| `redis` | Conversation cache, debounce buffers, rate limits |

## Features

- Automatic replies with conversation context
- Multi-user (one conversation per phone number)
- Durable Postgres history + Redis recent window
- Typing indicators and read receipts
- Send text, images, and PDFs
- Image understanding (vision models)
- Voice transcription (audio-capable OpenRouter models)
- PDF text extraction and analysis
- Function calling (`lookup_business_knowledge`, `get_current_time`)
- Custom business knowledge from markdown files
- Debounced multi-bubble message handling
- Webhook secret validation, rate limiting, input sanitization
- Retries for OpenRouter and Evolution HTTP failures
- Graceful reconnect attempts on Evolution disconnects

## Project structure

```text
backend/
  app/
    api/           # Pydantic schemas
    config/        # Settings from environment
    database/      # SQLAlchemy + Redis clients
    memory/        # Conversation memory + debounce
    middleware/    # Logging + rate limit helpers
    models/        # ORM models
    prompts/       # System knowledge docs
    routers/       # HTTP endpoints
    services/      # Evolution, OpenRouter, media, tools
    utils/         # Sanitize, phone, security, retries
    main.py
docker-compose.yml
.env.example
requirements.txt
README.md
```

## Requirements

- Docker + Docker Compose (recommended)
- Or Python 3.12+, PostgreSQL 16, Redis 7, and a reachable Evolution API
- OpenRouter API key: https://openrouter.ai/
- A phone with WhatsApp for QR pairing

## Quick start (Docker)

1. **Clone / open the project** and copy environment defaults:

```bash
cp .env.example .env
```

2. **Edit `.env`** and set at least:

- `OPENROUTER_API_KEY`
- `EVOLUTION_API_KEY` (strong random secret)
- `INTERNAL_API_KEY` (protects admin API routes)
- `WEBHOOK_SECRET` (must match webhook headers)

3. **Start the stack**:

```bash
docker compose up -d --build
```

4. **Check health**:

```bash
curl http://localhost:8000/health
```

5. **Pair WhatsApp (QR)**:

- Open Evolution Manager: http://localhost:8080/manager  
  (or call `GET http://localhost:8080/instance/connect/whatsapp-ai` with header `apikey: <EVOLUTION_API_KEY>`)
- Scan the QR code in WhatsApp → Linked Devices
- Confirm connection state is `open` via `/health`

6. **Send a WhatsApp message** to the linked number — the assistant replies automatically.

## Evolution API setup

The Compose file pins **`evoapicloud/evolution-api:v2.3.7`**.

On backend startup the app will:

1. Create the instance (`INSTANCE_NAME`) if missing
2. Configure the webhook to `WEBHOOK_URL` (default `http://backend:8000/webhook`)
3. Subscribe to `MESSAGES_UPSERT`, `CONNECTION_UPDATE`, `QRCODE_UPDATED`
4. Attach `x-webhook-secret` header for validation

### Manual instance create (optional)

```bash
curl -X POST http://localhost:8080/instance/create \
  -H "apikey: YOUR_EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "instanceName": "whatsapp-ai",
    "qrcode": true,
    "integration": "WHATSAPP-BAILEYS"
  }'
```

### Set webhook manually

```bash
curl -X POST http://localhost:8080/webhook/set/whatsapp-ai \
  -H "apikey: YOUR_EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "http://backend:8000/webhook",
      "byEvents": false,
      "base64": true,
      "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "QRCODE_UPDATED"],
      "headers": {"x-webhook-secret": "YOUR_WEBHOOK_SECRET"}
    }
  }'
```

### QR scanning

1. Fetch connect payload / open Manager UI
2. Scan with the WhatsApp mobile app
3. Keep the phone online; if the session drops, Evolution emits `CONNECTION_UPDATE` and the backend attempts restart + reconnect

> Note: Evolution Foundation images may require license activation via the Manager UI before some endpoints unlock. Follow the on-screen registration flow if prompted.

## Environment variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | OpenRouter secret key |
| `OPENROUTER_MODEL` | Default chat model (e.g. `openai/gpt-4o-mini`) |
| `OPENROUTER_VISION_MODEL` | Vision-capable model |
| `OPENROUTER_AUDIO_MODEL` | Audio / transcription-capable model |
| `OPENROUTER_TEMPERATURE` | Sampling temperature `0–2` |
| `OPENROUTER_MAX_TOKENS` | Max completion tokens |
| `DATABASE_URL` | Async SQLAlchemy URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL |
| `EVOLUTION_URL` | Evolution base URL |
| `EVOLUTION_API_KEY` | Evolution global API key |
| `INSTANCE_NAME` | WhatsApp instance name |
| `WEBHOOK_URL` | Public/internal URL Evolution calls |
| `WEBHOOK_SECRET` | Shared secret in `x-webhook-secret` |
| `INTERNAL_API_KEY` | Key for `/send`, `/conversations`, `/messages`, `/memory` |
| `SYSTEM_PROMPT` | Base assistant system prompt |
| `MEMORY_WINDOW_SIZE` | Redis / LLM context window size |
| `REDIS_MEMORY_TTL` | Cache TTL (seconds) |
| `MESSAGE_DEBOUNCE_SECONDS` | Burst debounce delay |
| `RATE_LIMIT_PER_MINUTE` | Per-IP / per-phone rate limit |
| `KNOWLEDGE_DIR` | Path to business knowledge files |
| `AUTO_CREATE_INSTANCE` | Create Evolution instance on boot |

See [`.env.example`](.env.example) for the full list.

## Running locally (without Docker backend)

1. Start Postgres, Redis, and Evolution (Compose is easiest):

```bash
docker compose up -d postgres redis evolution-api
```

2. Create a virtualenv and install deps:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

3. Point `.env` at local services:

```env
DATABASE_URL=postgresql+asyncpg://whatsapp:whatsapp@localhost:5432/whatsapp_ai
REDIS_URL=redis://localhost:6379/0
EVOLUTION_URL=http://localhost:8080
WEBHOOK_URL=http://host.docker.internal:8000/webhook
```

> On Linux, use your host IP or a tunnel (ngrok) instead of `host.docker.internal` so Evolution can reach the webhook.

4. Run the API:

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive docs: http://localhost:8000/docs

## API documentation

### `POST /webhook`

Evolution event receiver. Validates `x-webhook-secret` (or `?secret=`).

Processes `MESSAGES_UPSERT` (private chats only), acknowledges connection/QR events.

### `POST /send`

Manual outbound message. Requires header `X-API-Key: <INTERNAL_API_KEY>`.

```json
{
  "phone": "15551234567",
  "message": "Hello from the API"
}
```

Media example:

```json
{
  "phone": "15551234567",
  "media_url": "https://example.com/file.pdf",
  "media_type": "pdf",
  "file_name": "invoice.pdf",
  "caption": "Your invoice"
}
```

### `GET /health`

Returns database, Redis, and Evolution connectivity plus instance connection state.

### `GET /conversations`

Lists conversations (`X-API-Key` required).

### `GET /messages/{phone}`

Paginated permanent history (`limit`, `offset`). `X-API-Key` required.

### `DELETE /memory/{phone}`

Clears Redis cache for a phone. Add `?clear_postgres=true` to also wipe Postgres messages. `X-API-Key` required.

## AI behaviour

- System prompt from `SYSTEM_PROMPT` plus files in `backend/app/prompts/knowledge/`
- Temperature and model from environment (switch models by changing env / restarting)
- Recent turns cached in Redis; full history always in Postgres
- Tools allow knowledge lookup and current UTC time
- Groups and `fromMe` echoes are ignored

## Custom business knowledge

Add `.md` / `.txt` files under:

```text
backend/app/prompts/knowledge/
```

They are injected into the system prompt and searchable via the `lookup_business_knowledge` tool.

## Deployment guide

1. Provision a VPS with Docker Compose
2. Point a domain (e.g. `https://wa-api.example.com`) to the host with TLS (Caddy/Nginx/Traefik)
3. Set in `.env`:
   - `WEBHOOK_URL=https://wa-api.example.com/webhook`
   - `EVOLUTION_PUBLIC_URL=https://evolution.example.com` (if exposing Evolution)
   - Strong values for all secrets
4. Expose only what you need publicly:
   - Backend `/webhook` (required)
   - Optionally backend `/health`
   - Keep `/send` and history routes private or behind VPN
5. `docker compose up -d --build`
6. Scan QR and verify `/health`
7. Monitor logs: `docker compose logs -f backend evolution-api`

### Production checklist

- [ ] Rotate all default `change-me-*` secrets
- [ ] Restrict CORS (`CORS_ORIGINS`)
- [ ] Enable HTTPS for webhook URL
- [ ] Persist Docker volumes / scheduled backups for Postgres
- [ ] Confirm Evolution license/activation if required by the image
- [ ] Set realistic `RATE_LIMIT_PER_MINUTE`
- [ ] Choose an OpenRouter model with vision/audio if you need those extras

## Security

- Webhook secret validation (`WEBHOOK_SECRET`)
- Internal API key for admin routes
- Redis rate limiting
- Input sanitization and payload truncation
- Secrets are never intentionally logged (redaction helpers applied)

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Webhook 401 | Match `WEBHOOK_SECRET` with Evolution webhook headers |
| No replies | Check `/health`, instance state `open`, OpenRouter key, backend logs |
| QR never appears | Open Manager UI; recreate instance; confirm Evolution license |
| Disconnect loops | Keep phone online; check Evolution logs; restart `evolution-api` |
| PDF/voice issues | Confirm webhook `base64` media enabled; pick capable OpenRouter models |

## License

MIT — use at your own risk. Comply with WhatsApp and OpenRouter terms of service.

<!-- Environment variable setup instructions documented -->

<!-- Updated quickstart steps for developers -->

<!-- Updated quickstart steps for developers -->
