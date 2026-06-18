# Ticket Analyzer

Extract and analyze supermarket ticket data from Gmail attachments using OCR and LLMs.

## Overview

This project automates the extraction of structured data from supermarket receipts (tickets) that arrive via Gmail. It uses:

- **Gmail API** to retrieve messages and attachments
- **Claude (Anthropic)** for OCR and data extraction
- **SQLAlchemy ORM** with PostgreSQL/SQLite for persistent storage
- **Python ETL pipeline** for orchestration

## Architecture

```
Gmail Messages
    ↓
[OCR Module] → Claude API (extract JSON)
    ↓
[Validation] → Ensure required fields
    ↓
[Insert Layer] → SQLAlchemy ORM
    ↓
PostgreSQL/SQLite Database
```

## Installation

### Prerequisites

- Python 3.10+
- PostgreSQL (optional, SQLite fallback)
- Google OAuth credentials for Gmail API
- Anthropic API key

### Setup

1. **Clone and install dependencies:**

```bash
pip install -r requirements.txt
```

2. **Configure environment variables:**

Create a `.env` file in the project root (copy from `.env.example` if provided):

```env
# Gmail OAuth
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_PROJECT_ID=your_project_id
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json

# AI
ANTHROPIC_API_KEY=your_anthropic_key

# Database (PostgreSQL) - optional, defaults to SQLite
DB_NAME=ticket_analyzer
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Logging
LOG_LEVEL=INFO
LOG_DIR=logs
```

3. **Initialize the database:**

```bash
python -m src.db.create_tables
```

## Usage

### Run the ETL Pipeline

```python
from src.etl.pipeline import run_pipeline

# Extract all tickets from Mercadona
ticket_ids = run_pipeline("from:mercadona")
print(f"Inserted {len(ticket_ids)} tickets")
```

Or from command line:

```bash
python -m src.etl.pipeline
```

### Database Schema

**Supermercado** (Supermarket)
- `id` (PK)
- `nombre` (name, unique)

**Ticket** (Receipt)
- `id` (PK)
- `id_supermercado` (FK)
- `fecha` (date, DateTime)
- `hora` (time, Time)
- `tienda` (store name)
- `total` (amount)
- `id_mensaje_gmail` (Gmail message ID, unique)
- `created_at` (insertion timestamp)

**Categoria** (Category)
- `id` (PK)
- `nombre` (name, unique)

**Producto** (Product)
- `id` (PK)
- `nombre` (name)
- `id_categoria` (FK)
- `unidad_medida` (unit)

**LineaTicket** (Line Item)
- `id` (PK)
- `id_ticket` (FK)
- `id_producto` (FK)
- `cantidad` (quantity)
- `unidad_medida` (unit)
- `precio_unitario` (unit price)
- `precio_total` (total price)
- `tipo_precio` ("unidad" | "peso")
- `oferta` (is offer)
- `descuento` (discount %)

## Running Tests

```bash
pytest tests/ -v
```

With coverage:

```bash
pytest tests/ --cov=src --cov-report=html
```

## Logging

Logs are written to both console and rotating file (`logs/app.log`).

Configure log level via `LOG_LEVEL` env var:
- `DEBUG`: Very detailed output
- `INFO`: Standard operational logs
- `WARNING`: Warnings and errors only
- `ERROR`: Errors only

## Project Structure

```
.
├── src/
│   ├── config/          # Settings, logging
│   ├── db/              # Models, insert functions, connection
│   ├── etl/             # Pipeline orchestration
│   ├── gmail/           # Gmail API integration
│   └── ocr/             # OCR extraction using Claude
├── tests/               # Unit tests
├── requirements.txt     # Pinned dependencies
├── pyproject.toml       # Project metadata and pytest config
└── README.md
```

## Key Features

✅ **Robust OCR** - Claude handles complex ticket layouts
✅ **Data Validation** - Validates all required fields before insertion
✅ **Transaction Management** - Proper rollback on errors
✅ **Type Safety** - DateTime/Time columns instead of strings
✅ **Connection Pooling** - Optimized for PostgreSQL and SQLite
✅ **Comprehensive Logging** - Debug and audit trails
✅ **Duplicate Prevention** - Prevents re-processing via Gmail message ID
✅ **Error Recovery** - Skips bad attachments, continues pipeline

## Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | - | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | - | OAuth client secret |
| `GOOGLE_PROJECT_ID` | Yes | - | Google Cloud project ID |
| `GOOGLE_CREDENTIALS_PATH` | No | `credentials.json` | Path to credentials file |
| `GOOGLE_TOKEN_PATH` | No | `token.json` | Path to save OAuth token |
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key |
| `DB_NAME` | No | - | PostgreSQL database name (SQLite if empty) |
| `DB_USER` | No | - | Database user |
| `DB_PASSWORD` | No | - | Database password |
| `DB_HOST` | No | `localhost` | Database host |
| `DB_PORT` | No | `5432` | Database port |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_DIR` | No | `logs` | Log directory |

## Troubleshooting

### "Missing required environment variable"
Check `.env` file is created and contains all required keys.

### OCR returning incomplete data
Review Claude's response in logs. May indicate image quality issues.

### Database connection errors
- For PostgreSQL: Verify credentials and database exists
- For SQLite: Check file permissions on `tickets.db`

### Duplicate ticket messages
The pipeline is idempotent - re-running with same Gmail messages is safe.

## License

Proprietary - Internal Use Only
