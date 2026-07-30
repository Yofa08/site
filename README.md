# 🏷️ Deal Manager

A self-contained Amazon deals management platform — admin backend + public storefront + API.  
Modeled after [noelsdailydeals.com](https://noelsdailydeals.com).

## What It Does

| Page | URL | Who |
|------|-----|-----|
| **Admin Dashboard** | `/admin` | You — add/edit/delete deals, bulk import |
| **Categories** | `/admin/categories` | You — manage product categories |
| **Settings** | `/admin/settings` | You — site title, Google Sheet link, subscribers |
| **Public Storefront** | `/` | Visitors — browse daily deals, copy codes, buy on Amazon |
| **REST API** | `/api/merches`, `/api/categories` | Frontend — JSON API for custom storefronts |

## Features

- 📦 **Deal CRUD** — product name, prices, discount codes, Amazon links, ratings, dates
- 📋 **Bulk Import** — paste from Excel / Google Sheets (tab/pipe/comma), auto-detects headers
- 📥 **Excel Template** — download a pre-formatted `.xlsx`, fill in, paste back
- 📅 **Date Navigation** — deals organized by day (Today / Yesterday / 2 days ago)
- 📊 **Google Sheet Button** — link your sheet in the public header
- 📬 **Email Subscribe** — built-in capture modal or link to external form (Mailchimp, Google Forms)
- 🗂️ **Category Management** — with SEO keywords, sort order, status
- 🔥 **Featured Deals** — hot deals pinned to top
- 🏗️ **Multi-Tenant Ready** — tenant_id field built in from day one

## Quick Start (Local)

```bash
# 1. Install Python 3.11+ and pip

# 2. Clone or copy this folder
cd deal-manager

# 3. Create venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Start
python main.py

# 5. Open
# Admin:  http://localhost:8000/admin
# Public: http://localhost:8000/
```

## Deploy to Server

### Option A: One-Click Script (Ubuntu/Debian)

```bash
# Copy the folder to your server, then:
cd deal-manager
bash deploy.sh
```

This installs everything: Python venv, systemd service, nginx reverse proxy.

### Option B: Docker

```bash
docker compose up -d
# → http://your-server:8000
```

### Option C: Manual

```bash
# 1. Copy folder to /opt/deal-manager
# 2. Create .env from .env.example, edit if needed
# 3. Install deps:
cd /opt/deal-manager
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 4. Run (dev):
.venv/bin/python main.py

# 5. Run (prod):
ENV=prod .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000

# 6. (Optional) Set up systemd + nginx with provided files
sudo cp deal-manager.service /etc/systemd/system/
sudo cp nginx.conf /etc/nginx/sites-available/deal-manager
sudo systemctl enable --now deal-manager
```

## Configuration

All settings via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `dev` | `dev` = auto-reload, `prod` = no reload |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Port |
| `DATABASE_URL` | `sqlite:///./deals.db` | SQLite or PostgreSQL URL |

### Using PostgreSQL

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/dealmanager
```

Then install the driver:
```bash
pip install psycopg2-binary
```

## How to Import Deals from Excel

1. Go to Admin → **"📋 Import from Template"**
2. Click **"📥 Download Excel Template"** (or use your own spreadsheet)
3. Fill in deals in your spreadsheet (any column order, any names)
4. Select all rows including headers → **Ctrl+C**
5. Paste into the import text area → **Ctrl+V**
6. Click **"Import All"**

The importer auto-detects:
- Column header names (flexible — "Product Name" / "Name" / "Item" all work)
- Delimiter (tab / pipe / comma)
- Category names (resolves "Clothing" → category ID automatically)
- Dates, booleans, status values

## Project Structure

```
deal-manager/
├── main.py              # FastAPI app — all routes
├── models.py            # SQLAlchemy models (Category, Merch, Setting, Subscriber)
├── database.py          # DB connection (SQLite / PostgreSQL)
├── requirements.txt     # Python dependencies
├── templates/
│   ├── admin.html       # Admin deal dashboard
│   ├── categories.html  # Category manager
│   ├── settings.html    # Site settings + subscribers
│   └── public.html      # Public storefront
├── static/
│   └── template.xlsx    # Excel import template
├── Dockerfile
├── docker-compose.yml
├── deploy.sh            # One-click server deploy
├── deal-manager.service # systemd unit
├── nginx.conf           # nginx reverse proxy config
├── .env.example
└── .gitignore
```

## Tech Stack

- **Python 3.11+** — FastAPI + SQLAlchemy + Jinja2
- **Database** — SQLite (default) or PostgreSQL
- **Frontend** — Vanilla JS + CSS (zero npm/build step)
- **Deploy** — systemd, Docker, or any ASGI server (uvicorn, gunicorn)

---

Built for the [Hermes Agent](https://hermes-agent.nousresearch.com) project.
