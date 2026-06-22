<div align="center">

# 🧾 Ticket Analyzer

**Turn the supermarket receipts that land in your Gmail into clean, structured data.**

AI-powered OCR · Product & brand normalization · Price history · SQLAlchemy ORM

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red?logo=sqlite&logoColor=white)](https://www.sqlalchemy.org/)
[![Gmail API](https://img.shields.io/badge/Gmail-API-EA4335?logo=gmail&logoColor=white)](https://developers.google.com/gmail/api)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey)](#-license)

</div>

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Pipeline Architecture](#-pipeline-architecture)
- [Data Model](#-data-model)
- [Tech Stack](#-tech-stack)
- [Installation](#-installation)
- [Configuration](#-configuration-env)
- [Usage](#-usage)
- [Tests](#-tests)
- [Project Structure](#-project-structure)
- [Roadmap](#-roadmap)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## 🔍 Overview

**Ticket Analyzer** automates the full lifecycle of a supermarket receipt: from the moment it lands as an email attachment, to the moment its products, prices, and brands are stored in a relational database ready for analysis.

```
📧 Email with a receipt attached
        │
        ▼
🤖 AI-powered OCR (Gemini 2.5 Flash) → extracts supermarket, store, products, prices and brands
        │
        ▼
✅ Validation → checks that no required fields are missing
        │
        ▼
🗄️ ORM Insert Layer → normalizes products, brands and categories, prevents duplicates
        │
        ▼
🐘 PostgreSQL / SQLite
```

The system does **more than just store the receipt**: it normalizes product names, separates the brand (manufacturer or store brand) from the name, links each product to a fixed category, and keeps a price history per supermarket — all ready to power spending analytics and price comparisons.

---

## ✨ Features

| | |
|---|---|
| 🧠 **Robust AI-powered OCR** | Gemini 2.5 Flash reads receipts with complex layouts, abbreviations, and truncated names |
| 🏷️ **Brand recognition** | Detects manufacturer brands and, when none is visible, infers the supermarket's own private label (Mercadona → Hacendado, Alcampo → Auchan...) |
| 🧩 **Product normalization** | Completes truncated/abbreviated names and separates brand, category, and alias from the original name |
| 📍 **Structured addresses** | Extracts address, postal code, and city for every physical store |
| 📊 **Price history** | Lets you track price evolution per product and supermarket |
| 🔁 **Idempotency** | The `gmail_id` prevents the same receipt from being processed twice |
| 🛡️ **Strict validation** | Rejects receipts with missing required fields before touching the database |
| ↩️ **Safe transactions** | Automatic rollback on any insertion error |
| 🪵 **Comprehensive logging** | Console + rotating file (`logs/app.log`), configurable level |
| 🐘 **PostgreSQL or SQLite** | Production-ready with PostgreSQL, zero-config development/testing with SQLite |

---

## 🏗️ Pipeline Architecture

```
┌──────────────┐     ┌────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Gmail API    │────▶│ OCR (Gemini)   │────▶│ JSON Validation  │────▶│ Insert Layer ORM │
│ src/gmail/   │     │ src/ocr/       │     │ src/etl/pipeline │     │ src/db/insert.py │
└──────────────┘     └────────────────┘     └──────────────────┘     └────────┬────────┘
                                                                               │
                                                                               ▼
                                                                     ┌───────────────────┐
                                                                     │ PostgreSQL / SQLite│
                                                                     └───────────────────┘
```

1. **`src/gmail`** — authenticates via OAuth2, searches messages by query (`from:mercadona`), and downloads attachments in memory.
2. **`src/ocr`** — sends the attachment (PDF/image) to Gemini 2.5 Flash with a prompt specialized in Spanish supermarket receipts.
3. **`src/etl/pipeline.py`** — validates the returned JSON, parses dates/addresses, and orchestrates the insertion.
4. **`src/db`** — ORM layer (SQLAlchemy) with idempotent *get-or-create* functions for every entity.

---

## 🗃️ Data Model

<div align="center">
  <img src="docs/er%20diagram.png" alt="ER Diagram" width="850">
</div>

<details>
<summary>📋 Table descriptions</summary>

| Table | Purpose |
|---|---|
| **Supermarket** | Supermarket chain (Mercadona, Carrefour, Dia...) |
| **Store** | A specific physical store: address, postal code, city, province, and country |
| **Source** | Origin of the receipt (Email, WhatsApp, manual entry...) |
| **Receipt** | A specific receipt, linked to its Gmail message (`gmail_id` is unique → idempotency) |
| **ReceiptLine** | Each product line within a receipt: quantity, price before/after discount, total |
| **Product** | Normalized product (clean name, category, and brand) |
| **ProductAlias** | Names "as-is" exactly as they appear on receipts (`original_name`), mapped to the normalized product |
| **Category** | Product category, with optional hierarchy (parent/child category) |
| **Brand** | Product brand: manufacturer (Coca-Cola, Colgate...) or supermarket private label (Hacendado, Auchan...) |
| **PriceHistory** | Price evolution of a product at a given supermarket over time |

</details>

---

## 🛠️ Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.10+ |
| OCR / AI | Gemini 2.5 Flash (`google-genai`) |
| Email | Gmail API + OAuth2 (`google-api-python-client`) |
| ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL (production) / SQLite (development & tests) |
| Tests | pytest + pytest-cov |
| Code quality | black, ruff |

---

## 📦 Installation

### Prerequisites

- Python 3.10+
- PostgreSQL (optional — automatic SQLite fallback)
- Gmail API OAuth credentials
- Google AI (Gemini) API key

### Steps

**1. Clone the repo and install dependencies**

```bash
pip install -r requirements.txt
```

**2. Set up environment variables**

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

**3. Initialize the database**

```bash
python -m src.db.create_tables
```

You're all set! 🎉

---

## ⚙️ Configuration (`.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | ✅ | — | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | ✅ | — | OAuth client secret |
| `GOOGLE_PROJECT_ID` | ✅ | — | Google Cloud project ID |
| `GOOGLE_CREDENTIALS_PATH` | ❌ | `credentials.json` | Path to the credentials file |
| `GOOGLE_TOKEN_PATH` | ❌ | `token.json` | Path where the OAuth token is saved |
| `ANTHROPIC_API_KEY` | ✅ | — | API key for the AI model |
| `DB_NAME` | ❌ | — | PostgreSQL database name (empty → SQLite) |
| `DB_USER` | ❌ | — | Database user |
| `DB_PASSWORD` | ❌ | — | Database password |
| `DB_HOST` | ❌ | `localhost` | Database host |
| `DB_PORT` | ❌ | `5432` | Database port |
| `LOG_LEVEL` | ❌ | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `LOG_DIR` | ❌ | `logs` | Logs directory |

---

## 🚀 Usage

### From Python

```python
from src.etl.pipeline import run_pipeline

# Extract all pending Mercadona receipts from Gmail
ticket_ids = run_pipeline("from:mercadona")
print(f"Inserted {len(ticket_ids)} receipts")
```

### From the command line

```bash
python -m src.etl.pipeline
```

---

## 🧪 Tests

```bash
pytest tests/ -v
```

With coverage:

```bash
pytest tests/ --cov=src --cov-report=html
```

---

## 📁 Project Structure

```
.
├── src/
│   ├── config/          # Centralized settings and logging
│   ├── db/               # ORM models, insert layer, and connection
│   ├── etl/              # Pipeline orchestration (validation + insertion)
│   ├── gmail/             # Gmail authentication and reading
│   └── ocr/               # AI-powered receipt data extraction
├── tests/                # Unit test suite
├── requirements.txt      # Pinned dependencies
├── pyproject.toml        # Project metadata and pytest config
└── README.md
```

---

## 🗺️ Roadmap

- [ ] Extract store province/country (currently defaulted)
- [ ] Spending analytics dashboard by category/brand
- [ ] Multi-language support for receipts outside Spain
- [ ] Automatic detection of offers like "2x1" / "3x2"

---

## 🆘 Troubleshooting

<details>
<summary><strong>"Missing required environment variable"</strong></summary>

Check that the `.env` file exists and contains all required keys.
</details>

<details>
<summary><strong>OCR returns incomplete data</strong></summary>

Check Gemini's response in the logs (`LOG_LEVEL=DEBUG`). This usually points to image quality issues or a receipt with an unusual layout.
</details>

<details>
<summary><strong>Database connection errors</strong></summary>

- **PostgreSQL**: verify credentials and that the database exists.
- **SQLite**: check write permissions on `tickets.db`.
</details>

<details>
<summary><strong>Duplicate receipts</strong></summary>

The pipeline is idempotent thanks to the unique `gmail_id` on `Receipt`: re-running it against the same messages is safe and won't create duplicates.
</details>

---

## 📄 License

Internal / proprietary use.

<div align="center">

Built with ☕ and a lot of care

</div>