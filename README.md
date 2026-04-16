<div align="center">

<h1>🌐 Live Cyber Map</h1>
<h3>Real-Time Global Intelligence Command Center</h3>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=next.js&logoColor=white)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tauri](https://img.shields.io/badge/Tauri-1.6-FFC131?logo=tauri&logoColor=white)](https://tauri.app)
[![Three.js](https://img.shields.io/badge/Three.js-r179-000000?logo=three.js&logoColor=white)](https://threejs.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20AI-FF6B35)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-22c55e)](https://choosealicense.com/licenses/mit/)
[![Coverage](https://img.shields.io/badge/Test%20Coverage-97%25-brightgreen)](./backend/setup.cfg)

<br/>

**A self-hosted, zero-API-key intelligence platform that streams live cyber attacks on an interactive 3D globe, aggregates 40+ news sources into AI-synthesized briefs, tracks global financial markets, and computes real-time country risk scores — all from a single `docker compose up`.**

<br/>

[**Quick Start**](#-quick-start) &nbsp;·&nbsp;
[**Features**](#-features) &nbsp;·&nbsp;
[**Architecture**](#️-architecture) &nbsp;·&nbsp;
[**Tech Stack**](#️-tech-stack) &nbsp;·&nbsp;
[**API Reference**](#-api-reference) &nbsp;·&nbsp;
[**Desktop App**](#️-desktop-app) &nbsp;·&nbsp;
[**Contributing**](#-contributing)

</div>

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🌍 Visualization
- **Interactive 3D Globe** — animated neon arcs from attacker to target, powered by `globe.gl` + Three.js
- **2D Flat Map** — Leaflet-based alternative with full layer support
- **46 Live Data Layers** — USGS earthquakes, OpenSky flights, Open-Meteo weather, submarine cables, active volcanoes, and more
- **9 Attack Types** — each with a unique neon color and severity-scaled arc thickness
- **Country Choropleth** — risk score heat-map across all tracked nations

</td>
<td width="50%">

### ⚡ Real-Time Engine
- **WebSocket Streaming** — sub-second push from backend to every connected client
- **1,000+ events/sec** — batched DB writes keep PostgreSQL pressure minimal
- **Redis Pub/Sub** — fan-out to unlimited concurrent clients
- **Anomaly Detection** — 60-second sliding-window spike detection with live alert banner
- **Attack Clustering** — groups events by type + origin for pattern analysis

</td>
</tr>
<tr>
<td width="50%">

### 🤖 Intelligence & AI
- **40+ RSS Feeds** — aggregated, deduped, and cached automatically
- **Local Ollama AI** — synthesizes intelligence briefs from headlines (no cloud API)
- **Country Risk Scores** — composite cyber + news sentiment + baseline index, updated live
- **Configurable Alert Rules** — trigger WebSocket + browser notifications on any condition
- **Sentiment Analysis** — keyword-based scoring on every ingested news article

</td>
<td width="50%">

### 📈 Financial Markets
- **Crypto** — BTC, ETH, SOL, XRP and more via CoinGecko
- **Stocks & Indices** — SPY, QQQ, DXY via yfinance
- **Forex** — live exchange rates for 30+ currency pairs
- **Commodities** — Gold, Oil, Silver, Natural Gas
- **Persistent Snapshots** — full price history stored in PostgreSQL for replay

</td>
</tr>
</table>

### Additional Highlights

| | |
|---|---|
| ⏮️ **Replay Mode** | Scrub through historical attack data with configurable speed (0.5×–5×) |
| 🖥️ **Desktop App** | Native Tauri build for macOS, Windows, and Linux |
| 🎨 **Themed Variants** | Cyber, Finance, and Tech dashboard skins |
| 🔒 **Zero External APIs** | Everything runs locally — no keys, no quotas, no data leaving your network |
| 🛡️ **Graceful Degradation** | Runs without Redis (in-memory broadcast) and without PostgreSQL (SQLite fallback) |
| 📦 **One-Command Deploy** | Full stack up in under 3 minutes with Docker Compose |

---

## 🚀 Quick Start

### Prerequisites

- [Docker Desktop](https://docs.docker.com/get-docker/) (includes Docker Compose v2)
- 4 GB RAM minimum; 8 GB recommended if running Ollama AI

### 1. Clone & configure

```bash
git clone https://github.com/DANIELKILONZI/Live-Cyber-Map.git
cd Live-Cyber-Map
cp .env.example .env
```

### 2. Launch the full stack

```bash
docker compose up --build
```

Five services start in order: **PostgreSQL → Redis → Ollama → FastAPI backend → Next.js frontend**, all behind an **Nginx** reverse proxy. The first build takes 2–4 minutes to pull images and compile assets.

### 3. Open the dashboard

```
http://localhost
```

The globe will populate with live attack arcs within seconds of the page loading.

> **Tip:** Increase throughput by setting `EVENTS_PER_SECOND=500` in your `.env` before starting.

---

## 🏛️ Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       BROWSER  /  TAURI DESKTOP CLIENT                       │
│                                                                               │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ 3D Globe │  │  2D Map  │  │Intelligence│  │ Financial│  │ Alert Rules  │  │
│  │(Three.js)│  │(Leaflet) │  │  + AI Briefs│  │  Ticker  │  │& Notif. Tray │  │
│  └────┬─────┘  └────┬─────┘  └─────┬──────┘  └────┬─────┘  └──────┬───────┘  │
│       └─────────────┴──────────────┴───────────────┴───────────────┘          │
│                  WebSocket  (attacks · stats · anomaly · alert)                │
│                  REST  (news · risk · financial · replay · layers)             │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                  ┌─────▼──────┐
                                  │   Nginx    │  :80
                                  └──┬─────┬───┘
                         ┌───────────┘     └───────────┐
                   ┌─────▼─────┐                 ┌─────▼──────┐
                   │  Next.js  │                 │  FastAPI   │
                   │ Frontend  │                 │  Backend   │
                   │  :3000    │                 │   :8000    │
                   └───────────┘                 └─────┬──────┘
                                           ┌───────────┼────────────┐
                                           │           │            │
                                    ┌──────▼────┐ ┌────▼───┐ ┌─────▼──────┐
                                    │PostgreSQL │ │ Redis  │ │   Ollama   │
                                    │  :5432    │ │ :6379  │ │  :11434    │
                                    └───────────┘ └────────┘ └────────────┘
```

### Backend Services

| Service | Purpose |
|---------|---------|
| `AttackGenerator` | Generates a weighted, realistic synthetic cyber-attack event stream |
| `AttackProcessor` | GeoIP enrichment, anomaly scoring, clustering, DB persistence |
| `WebSocketManager` | Multiplexes real-time events to all connected clients via Redis Pub/Sub |
| `NewsAggregator` | Polls 40+ RSS feeds, deduplicates, scores sentiment, caches in Redis |
| `CountryRiskService` | Composite risk scores: cyber activity + news sentiment + stability baseline |
| `FinancialDataService` | CoinGecko crypto · yfinance stocks/indices · open.er-api.com forex |
| `OllamaService` | AI intelligence briefs; gracefully falls back to plain text summaries |
| `AlertService` | Evaluates user-defined rules against every event; fires WebSocket alerts |

### Frontend Panels

| Panel | Button | Description |
|-------|--------|-------------|
| **Stats Dashboard** | Left sidebar | Events/sec, rolling avg, top attackers/targets, attack-type breakdown |
| **Attack Feed** | Left sidebar | Live scrolling log with flag emoji, type badge, severity bar |
| **Layer Control** | 🗂️ LAYERS | Toggle 46 map overlays (seismic, weather, flights, cables, …) |
| **Intelligence** | 📰 INTEL | AI briefs + categorised news feed by region |
| **Country Risk** | 🌡️ RISK | Choropleth risk map + per-country drill-down |
| **Financial Ticker** | 📈 MARKETS | Stocks, crypto, indices, forex, commodities |
| **Alert Rules** | 🚨 ALERTS | Create, toggle, and delete notification rules |
| **Notifications** | 🔔 Bell | In-app tray + browser Notification API |
| **AI Settings** | 🤖 AI | List/pull Ollama models; switch active model at runtime |
| **Replay** | ⏮ REPLAY | Historical playback with speed control and scrubber |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend API** | Python 3.11, FastAPI, Uvicorn (ASGI) |
| **Real-time transport** | WebSockets, Redis Pub/Sub |
| **Database** | PostgreSQL 15 + SQLAlchemy 2 (async), Alembic migrations |
| **Frontend framework** | Next.js 15, React 18, TypeScript 5 |
| **3D visualization** | globe.gl, Three.js |
| **2D mapping** | Leaflet 1.9, React-Leaflet |
| **Styling** | Tailwind CSS, Framer Motion |
| **Local AI** | Ollama (llama3.2:3b, mistral, nomic-embed-text) |
| **Financial data** | CoinGecko API, yfinance, open.er-api.com |
| **Live map layers** | USGS earthquake feed, Open-Meteo weather, OpenSky Network ADS-B |
| **Desktop** | Tauri 1.6 (Rust + WebView2/WebKit) |
| **Reverse proxy** | Nginx 1.25 |
| **Container runtime** | Docker, Docker Compose |
| **Testing** | pytest, anyio, pytest-asyncio — 613 tests, 97% coverage |
| **CI/CD** | GitHub Actions |

---

## 💻 Local Development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Spin up Redis only (backend falls back to SQLite without PostgreSQL)
docker run -d -p 6379:6379 redis:7-alpine

# Start the API server with live reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive API docs: **http://localhost:8000/docs**

### Running Tests

```bash
cd backend
DATABASE_URL="sqlite+aiosqlite:///:memory:" \
REDIS_URL="redis://localhost:6379" \
OLLAMA_URL="http://localhost:11434" \
OLLAMA_MODEL="llama3.2:3b" \
python -m pytest tests/ -q --cov=app --cov-report=term-missing
```

### Frontend

```bash
cd frontend
npm install

NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
npm run dev
```

Open **http://localhost:3000**

---

## 🤖 Ollama — Local AI Setup

Ollama provides AI-synthesized intelligence briefs. It is **completely optional** — the app degrades gracefully to plain-text summaries without it.

```bash
# 1. Install Ollama: https://ollama.ai
# 2. Start the server
ollama serve

# 3. Pull a model (llama3.2:3b fits comfortably in 8 GB RAM)
ollama pull llama3.2:3b

# Already set in .env.example — no changes needed:
# OLLAMA_URL=http://localhost:11434
# OLLAMA_MODEL=llama3.2:3b
```

Click **🤖 AI** in the top bar to list installed models, pull new ones, or switch between `llama3.1:8b`, `mistral:7b`, `gemma:2b`, and others at runtime — no restart required.

---

## 📡 API Reference

### Core REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Service health — DB & Redis reachability |
| `GET` | `/api/stats` | Live attack statistics snapshot |
| `GET` | `/api/attacks/recent` | Most recent N attack events (in-memory) |
| `GET` | `/api/attacks/history` | Paginated DB history with filters |
| `GET` | `/api/replay` | Current replay state |
| `POST` | `/api/replay/start?speed=2.0` | Activate replay at given speed |
| `POST` | `/api/replay/stop` | Stop replay, resume live mode |
| `POST` | `/api/replay/seek?position=100` | Jump to event index, re-broadcast 50 events |
| `GET` | `/api/replay/intelligence` | Time-windowed risk + financial event timeline |
| `GET` | `/api/intel/news` | Paginated news feed with category/region filters |
| `POST` | `/api/intel/brief` | Generate an AI intelligence brief |
| `GET` | `/api/intel/risk` | All country risk scores |
| `GET` | `/api/financial/{asset_class}` | Price data by asset class |
| `GET` | `/api/alerts/rules` | List all alert rules |
| `POST` | `/api/alerts/rules` | Create a new alert rule |
| `PUT` | `/api/alerts/rules/{id}` | Update a rule |
| `PATCH` | `/api/alerts/rules/{id}/toggle` | Enable / disable a rule |
| `DELETE` | `/api/alerts/rules/{id}` | Delete a rule |

### WebSocket — `/ws`

#### Server → Client

```jsonc
// New attack event
{ "type": "attack",  "data": { "id": "…", "attack_type": "DDoS", "severity": 8, "source_country": "RU", … } }

// Stats update (~every 1 s)
{ "type": "stats",   "data": { "events_per_second": 48, "total_events": 12400, "is_anomaly": false } }

// Anomaly detected
{ "type": "anomaly", "data": { "message": "Traffic spike detected", "score": 3.2 } }

// User-defined alert fired
{ "type": "alert",   "data": { "rule_id": 1, "rule_name": "DDoS watch", "message": "…", "fired_at": 1700000000 } }

// Replay control
{ "type": "replay_started", "speed": 2.0 }
{ "type": "replay_stopped" }
{ "type": "replay_seek",    "position": 250 }
```

#### Client → Server

```jsonc
{ "type": "pause" }
{ "type": "resume" }
{ "type": "set_speed", "data": { "speed": 2.0 } }
```

---

## ⚙️ Configuration

All settings are controlled via environment variables. Copy `.env.example` to `.env` and adjust as needed.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | SQLite fallback | PostgreSQL async DSN |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `EVENTS_PER_SECOND` | `50` | Attack simulation rate (up to ~1,000) |
| `MAX_EVENTS_HISTORY` | `1000` | In-memory ring-buffer size |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Active model name |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000/ws` | WebSocket URL (browser) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | REST API URL (browser) |

> **Graceful degradation:** The backend starts and runs correctly with no PostgreSQL (uses SQLite) and with no Redis (direct WebSocket broadcast). This means zero-dependency local development requires only Python.

---

## 🎨 Attack Types & Color Palette

| Attack Type | Arc Color | Globe Hex | Relative Frequency |
|-------------|-----------|-----------|-------------------|
| DDoS | 🔴 Red | `#ff4444` | Very Common |
| Malware | 🟠 Orange | `#ff8800` | Common |
| Phishing | 🟡 Yellow | `#ffff00` | Common |
| BruteForce | 🟣 Magenta | `#ff00ff` | Common |
| Ransomware | 🩷 Pink | `#ff0088` | Moderate |
| Intrusion | 🩵 Cyan | `#00ffff` | Moderate |
| SQLInjection | 🟢 Green | `#00ff88` | Moderate |
| XSS | 🔵 Blue | `#8888ff` | Moderate |
| ZeroDay | ⚪ White | `#ffffff` | Rare |

Arc **thickness** scales linearly with severity (1–10). Destination coordinates pulse with a glow effect on impact.

---

## 📊 Performance Benchmarks

| Metric | Value |
|--------|-------|
| Sustained event throughput | **1,000+ events / second** |
| Concurrent WebSocket clients | Unlimited (Redis fan-out) |
| Globe arcs rendered simultaneously | Up to **200** without frame drops |
| DB write strategy | Async batched flush every 5 seconds |
| News aggregation cycle | ~5 minutes, fully async |
| Cold-start time (Docker) | ~2–3 minutes (image pull) |
| Warm-start time | < 10 seconds |

---

## 🖥️ Desktop App

Live Cyber Map ships as a native desktop application via **Tauri** (Rust + WebView).

```bash
# Install prerequisites
cargo install tauri-cli
npm install -g @tauri-apps/cli

# Development mode
cd src-tauri
tauri dev

# Production build (macOS .app / Windows .msi / Linux .AppImage)
tauri build
```

The desktop app bundles the Next.js frontend and connects to a locally running or remote FastAPI backend. Auto-updates are supported via an Ed25519-signed update manifest.

### Signing Keys (for auto-updater)

```bash
# Generate key pair
tauri signer generate -w ~/.tauri/update-key.key

# Add public key to src-tauri/tauri.conf.json
# Add private key as TAURI_PRIVATE_KEY secret in GitHub Actions
```

---

## 🎨 Themed Variants

Three pre-built dashboard themes ship in the `variants/` directory:

| Theme | Target Audience |
|-------|----------------|
| **Cyber** | Security operations, threat intelligence |
| **Finance** | Financial risk, market surveillance |
| **Tech** | Infrastructure monitoring, DevOps |

Apply a theme with the included helper script:

```bash
./build-variant.sh cyber    # or finance / tech
```

---

## 🔧 Troubleshooting

<details>
<summary><strong>Globe is blank / no attack arcs appearing</strong></summary>

- Check the browser console for WebSocket errors.
- The dashboard header shows `● CONNECTED` when the WebSocket is live.
- Confirm the backend is running: `curl http://localhost:8000/api/health`
- Wait ~5 seconds after page load for the first events to arrive.

</details>

<details>
<summary><strong>docker compose up fails on the backend service</strong></summary>

The backend waits for PostgreSQL and Redis health-checks before starting. A single restart on first boot is normal. Check logs:

```bash
docker compose logs backend --tail 50
```

</details>

<details>
<summary><strong>Port conflicts</strong></summary>

Ports **80**, **3000**, **8000**, **5432**, **6379**, and **11434** must be free. Stop any local Postgres, Redis, or other services occupying those ports before running Docker Compose.

</details>

<details>
<summary><strong>Ollama AI brief returns "Ollama unavailable"</strong></summary>

Ollama is optional. If it is not running, briefs fall back to a plain-text summary automatically. Start Ollama with `ollama serve` and pull at least one model: `ollama pull llama3.2:3b`.

</details>

---

## 🤝 Contributing

Contributions of all kinds are welcome — from bug reports to new data layers to UI improvements.

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/my-improvement`
3. **Commit** with a descriptive message: `git commit -m "feat: add submarine cable layer"`
4. **Push** to your fork: `git push origin feature/my-improvement`
5. **Open a Pull Request** against `main`

Please open an issue first for large or breaking changes so we can discuss direction before implementation.

### Development Standards

- Backend: `ruff` for linting, `pytest` for tests — run `pytest tests/ -q` before submitting
- Frontend: `eslint` + `prettier` — run `npm run lint` before submitting
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)

---

## 📄 License

[MIT](https://choosealicense.com/licenses/mit/) © [DANIELKILONZI](https://github.com/DANIELKILONZI)

---

<div align="center">

Built with ❤️ and a lot of caffeine.

⭐ **Star this repo** if you find it useful — it helps others discover the project.

</div>
