# 🌐 Global Intelligence Dashboard

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js&logoColor=white)](https://nextjs.org)
[![Tauri](https://img.shields.io/badge/Tauri-1.6-FFC131?logo=tauri&logoColor=white)](https://tauri.app)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20AI-white)](https://ollama.ai)
[![Three.js](https://img.shields.io/badge/Three.js-0.160-black?logo=three.js&logoColor=white)](https://threejs.org)
[![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900?logo=leaflet&logoColor=white)](https://leafletjs.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=white)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e)](https://choosealicense.com/licenses/mit/)

**A real-time global intelligence command center.**

Aggregates news from 40+ sources, synthesizes AI briefs via a local Ollama model, tracks stocks/crypto/commodities, visualizes 40+ data layers on an interactive globe or flat map, and computes live country risk scores — all without any external API keys.

[Quick Start](#-quick-start) · [Architecture](#️-architecture) · [Features](#-features) · [Desktop App](#️-desktop-app-tauri) · [Variants](#-themed-variants) · [API Reference](#-api-reference)

</div>

---

*The 3D globe displays animated attack arcs from source to destination countries. Arc colors correspond to attack type; arc thickness scales with severity.*

---

### Live Dashboard

![Dashboard panel showing stats](docs/screenshots/dashboard.png)

*The left-side panel shows events/second, total event count, rolling average, top attacker countries, top target countries, and a breakdown by attack type — all updating in real time.*

---

### Attack Feed

![Real-time attack feed](docs/screenshots/attack-feed.png)

*The right-side panel lists the 20 most recent attacks with timestamps, source → destination flags, attack-type badge, severity badge (LOW / MED / HIGH / CRIT), and a visual severity bar.*

---

### Anomaly Detection Alert

![Anomaly detection alert banner](docs/screenshots/anomaly-alert.png)

*When the 60-second rolling event rate spikes above the statistical threshold, a pulsing red ⚠ Anomaly Detected banner appears on the dashboard with the anomaly score.*

---

### Replay Mode

![Replay mode controls](docs/screenshots/replay-mode.png)

*Replay mode allows historical attack playback with configurable speed (0.5×–5×). Use the controls to pause, resume, or scrub through recorded events.*

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🌍 **3D Globe Visualization** | Animated arcs from source to destination, powered by `globe.gl` + Three.js |
| ⚡ **Real-time Streaming** | WebSocket push from backend to all connected clients instantly |
| 🎯 **GeoIP Enrichment** | IP → lat/lng/country mapping (in-memory, 50+ countries, no external API required) |
| 🔴 **Anomaly Detection** | 60-second sliding-window spike detection with animated alert banner |
| 🗂️ **Attack Clustering** | Groups events by attack type + source country for pattern analysis |
| ⏮️ **Replay Mode** | Historical attack playback with adjustable speed control |
| 📊 **Live Dashboard** | Events/sec, rolling average, top attackers, top targets, attack-type breakdown |
| 📜 **Attack Feed** | Scrolling live feed with severity indicators and country flag emojis |
| 🎨 **Color-coded Attacks** | 9 attack types each with a distinct neon color |
| 🏗️ **Production-Ready** | Dockerized with Nginx reverse proxy, graceful degradation without Redis/PostgreSQL |

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       CLIENT BROWSER                        │
│  ┌────────────┐   ┌──────────────┐   ┌───────────────────┐  │
│  │  3D Globe  │   │  Dashboard   │   │   Attack Feed     │  │
│  │ (Three.js) │   │  (Stats)     │   │  (Live Events)    │  │
│  └─────┬──────┘   └──────┬───────┘   └────────┬──────────┘  │
│        └─────────────────┴────────────────────┘             │
│                           │ WebSocket                        │
└───────────────────────────┼──────────────────────────────────┘
                            │
                      ┌─────▼──────┐
                      │   Nginx    │  Reverse Proxy :80
                      └─────┬──────┘
             ┌──────────────┴──────────────┐
             │                             │
       ┌─────▼─────┐                 ┌─────▼──────┐
       │  Next.js  │                 │  FastAPI   │
       │ Frontend  │                 │  Backend   │
       │  :3000    │                 │   :8000    │
       └───────────┘                 └──────┬─────┘
                                            │
                               ┌────────────┴────────────┐
                               │                         │
                         ┌─────▼─────┐             ┌─────▼─────┐
                         │ PostgreSQL│             │   Redis   │
                         │  :5432    │             │   :6379   │
                         └───────────┘             └───────────┘
```

### Event Pipeline

```
AttackGenerator ──► asyncio Queue ──► AttackProcessor
                                            │
                              ┌─────────────┼─────────────┐
                              ▼             ▼             ▼
                         GeoIP Enrich  AnomalyDetect  Cluster Assign
                                            │
                                    Redis Pub/Sub
                                     "attacks" ch
                                            │
                               WebSocketManager.broadcast()
                                            │
                                  All browser clients
                                            │
                                   globe.gl arc render
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend API** | Python 3.11, FastAPI, Uvicorn |
| **Real-time** | WebSockets, Redis Pub/Sub |
| **Database** | PostgreSQL 15, SQLAlchemy (async) |
| **Frontend** | Next.js 14, React 18, TypeScript |
| **Visualization** | globe.gl, Three.js |
| **Styling** | TailwindCSS, Framer Motion |
| **Proxy** | Nginx |
| **Containers** | Docker, Docker Compose |

---

## 🚀 Quick Start

### Prerequisites

- [Docker Desktop](https://docs.docker.com/get-docker/) (includes Docker Compose)

### 1. Clone and configure

```bash
git clone https://github.com/dnlkilonzi-pixel/Live-Cyber-Map.git
cd Live-Cyber-Map
cp .env.example .env
```

### 2. Start all services

```bash
docker-compose up --build
```

Docker Compose starts five services: **PostgreSQL**, **Redis**, **FastAPI backend**, **Next.js frontend**, and **Nginx**. The first build takes ~2–3 minutes to pull images and install dependencies.

### 3. Open the app

```
http://localhost:80
```

The globe will populate with live attack arcs within a few seconds of opening the page.

> **Tip:** To increase the event rate, set `EVENTS_PER_SECOND=200` in your `.env` file before starting.

---

## 💻 Local Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start Redis (required for pub/sub)
docker run -d -p 6379:6379 redis:7-alpine

# Start the API server (falls back to SQLite if no PostgreSQL)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend API is available at `http://localhost:8000`. Interactive API docs are at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
npm run dev
```

Open `http://localhost:3000`.

---

## 📡 API Reference

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check — returns DB + Redis status |
| `GET` | `/api/stats` | Current attack statistics snapshot |
| `GET` | `/api/attacks/recent?limit=100` | Most recent attack events |
| `GET` | `/api/attacks/history` | Historical events with optional filters |
| `POST` | `/api/replay/start` | Begin replay of historical data |
| `POST` | `/api/replay/stop` | Stop replay and resume live mode |
| `WS` | `/ws` | WebSocket endpoint for live event stream |

### WebSocket — Server → Client Messages

```json
// New attack event
{ "type": "attack",  "data": { "id": "...", "attack_type": "DDoS", "severity": 8, ... } }

// Stats update (sent ~every second)
{ "type": "stats",   "data": { "events_per_second": 48, "total_events": 12400, "is_anomaly": false } }

// Anomaly alert
{ "type": "anomaly", "data": { "message": "Traffic spike detected", "score": 3.2 } }

// Historical replay batch
{ "type": "history", "data": [ /* AttackEvent[] */ ] }
```

### WebSocket — Client → Server Commands

```json
{ "type": "pause" }
{ "type": "resume" }
{ "type": "set_speed", "data": { "speed": 2.0 } }
```

---

## ⚙️ Configuration

All configuration is via environment variables (see `.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | SQLite fallback | PostgreSQL async connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `EVENTS_PER_SECOND` | `50` | Attack simulation rate (max ~1000) |
| `MAX_EVENTS_HISTORY` | `1000` | In-memory event history buffer size |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000/ws` | WebSocket URL (consumed by the browser) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | REST API URL (consumed by the browser) |

> **Graceful degradation:** The backend runs without PostgreSQL (in-memory storage) and without Redis (direct WebSocket broadcast). This makes zero-dependency local development easy.

---

## 🎨 Attack Types & Colors

Each attack type is rendered with a unique neon color on the globe and in the dashboard.

| Attack Type | Arc Color | Frequency |
|-------------|-----------|-----------|
| DDoS | 🔴 `#ff4444` | Very Common |
| Malware | 🟠 `#ff8800` | Common |
| Phishing | 🟡 `#ffff00` | Common |
| BruteForce | 🟣 `#ff00ff` | Common |
| Ransomware | 🩷 `#ff0088` | Moderate |
| Intrusion | 🩵 `#00ffff` | Moderate |
| SQLInjection | 🟢 `#00ff88` | Moderate |
| XSS | 🔵 `#8888ff` | Moderate |
| ZeroDay | ⚪ `#ffffff` | Rare |

Arc **thickness** scales with event severity (1–10). Destination markers glow at the target coordinates.

---

## 📈 Performance

| Metric | Value |
|--------|-------|
| Max throughput | **1,000+ events/second** |
| Concurrent WebSocket clients | Unlimited |
| Simultaneous globe arcs | Up to **200** with no UI lag |
| DB write strategy | Batched to minimize PostgreSQL pressure |
| Fallback mode | In-memory only (no Redis or PostgreSQL needed) |

---

## 🔧 Troubleshooting

**Globe is blank / not loading**
- Check the browser console for errors.
- Verify the WebSocket connection: the dashboard header shows `CONNECTED` or `DISCONNECTED`.
- Ensure the backend is running: `curl http://localhost:8000/api/health`.

**No attack arcs appear**
- Wait ~5 seconds for the first batch of events.
- Check `EVENTS_PER_SECOND` in your `.env` — a value of `0` disables the generator.

**`docker-compose up` fails on the backend**
- The backend waits for PostgreSQL and Redis health checks before starting. If those services are slow, the backend may restart once before succeeding — this is normal.
- Run `docker-compose logs backend` to inspect errors.

**Port conflicts**
- Ports `80`, `3000`, `8000`, `5432`, and `6379` must be free. Stop any local Postgres, Redis, or other services using those ports before running Docker Compose.

---

## 🤝 Contributing

Contributions are welcome! For major changes, please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request

---

## 📄 License

[MIT](https://choosealicense.com/licenses/mit/) © [dnlkilonzi-pixel](https://github.com/dnlkilonzi-pixel)