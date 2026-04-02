# 🌐 Live Cyber Map

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python) ![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi) ![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js) ![Three.js](https://img.shields.io/badge/Three.js-0.160-black?logo=three.js) ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker) ![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql) ![License](https://img.shields.io/badge/License-MIT-green)

A **production-grade real-time global cyber attack visualization platform** built for cybersecurity operations centers. Watch live (simulated) cyber attacks animate as arcs across a 3D interactive globe, powered by a high-throughput event pipeline capable of processing 1,000+ events per second.

---

## 🖥️ Live Demo

> The platform renders animated arcs from attacker sources to victim destinations on a dark 3D globe, with a live dashboard showing attack rates, anomaly detection, top attacker countries, and a real-time attack feed.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🌍 **3D Globe Visualization** | Animated arcs from source to destination, powered by `globe.gl` + Three.js |
| ⚡ **Real-time Streaming** | WebSocket push from backend to all connected clients |
| 🎯 **GeoIP Enrichment** | IP → lat/lng/country mapping (in-memory, 50+ countries, no external DB required) |
| 🔴 **Anomaly Detection** | 60-second sliding window spike detection with alert banner |
| 🗂️ **Attack Clustering** | Groups events by attack type + source country |
| ⏮️ **Replay Mode** | Historical attack playback with speed control |
| 📊 **Live Dashboard** | Events/sec, top attackers, top targets, attack-type breakdown |
| 📜 **Attack Feed** | Scrolling live feed with severity indicators and flag emojis |
| 🎨 **Color-coded Attacks** | 9 attack types each with a unique color |
| 🏗️ **Production-Ready** | Dockerized, Nginx reverse proxy, graceful degradation |

---

## 🏛️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENT BROWSER                          │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │  3D Globe  │  │  Dashboard   │  │   Attack Feed     │   │
│  │ (Three.js) │  │  (Stats)     │  │   (Live Events)   │   │
│  └─────┬──────┘  └──────┬───────┘  └────────┬──────────┘   │
│        └────────────────┴──────────────────┘               │
│                         │ WebSocket                         │
└─────────────────────────┼───────────────────────────────────┘
                          │
                    ┌─────▼──────┐
                    │   Nginx    │ (Reverse Proxy :80)
                    └─────┬──────┘
           ┌──────────────┼──────────────┐
           │              │              │
     ┌─────▼─────┐  ┌─────▼──────┐      │
     │  Next.js  │  │  FastAPI   │      │
     │ Frontend  │  │  Backend   │      │
     │  :3000    │  │   :8000    │      │
     └───────────┘  └──────┬─────┘      │
                           │            │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌────▼────┐      │
        │ PostgreSQL│ │  Redis  │      │
        │  :5432    │ │  :6379  │      │
        └───────────┘ └─────────┘      │
```

### Data Flow

```
AttackGenerator → Queue → AttackProcessor → GeoIP Enrichment
       ↓                        ↓                   ↓
  asyncio loop          AnomalyDetector      Cluster Assignment
                               ↓
                        Redis Pub/Sub ("attacks" channel)
                               ↓
                      WebSocketManager.broadcast()
                               ↓
                    All connected browser clients
                               ↓
                       globe.gl arc animation
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | Python 3.11, FastAPI, Uvicorn |
| Real-time | WebSockets, Redis Pub/Sub |
| Database | PostgreSQL 15, SQLAlchemy (async) |
| Frontend | Next.js 14, React 18, TypeScript |
| Visualization | globe.gl, Three.js |
| Styling | TailwindCSS |
| Proxy | Nginx |
| Containers | Docker, Docker Compose |

---

## 🚀 Quick Start

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/)

### 1. Clone and configure
```bash
git clone https://github.com/dnlkilonzi-pixel/Live-Cyber-Map.git
cd Live-Cyber-Map
cp .env.example .env
```

### 2. Launch all services
```bash
docker-compose up --build
```

### 3. Open the app
```
http://localhost:80
```

---

## 💻 Local Development

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start Redis locally (or use Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Run backend (SQLite fallback if no PostgreSQL)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws npm run dev
```
Open http://localhost:3000

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check (DB + Redis status) |
| GET | `/api/stats` | Current attack statistics |
| GET | `/api/attacks/recent?limit=100` | Recent attack events |
| GET | `/api/attacks/history` | Historical data with filters |
| POST | `/api/replay/start` | Start replay mode |
| POST | `/api/replay/stop` | Stop replay mode |
| WS | `/ws` | WebSocket connection for live events |

### WebSocket Message Types

```json
{ "type": "attack",  "data": { ...AttackEvent } }
{ "type": "stats",   "data": { "events_per_second": 48, "is_anomaly": false, ... } }
{ "type": "anomaly", "data": { "message": "Traffic spike detected", "score": 3.2 } }
{ "type": "history", "data": [ ...AttackEvent[] ] }
```

### WebSocket Commands (client → server)
```json
{ "type": "pause" }
{ "type": "resume" }
{ "type": "set_speed", "data": { "speed": 2.0 } }
```

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | SQLite fallback | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `EVENTS_PER_SECOND` | `50` | Simulation rate (max ~1000) |
| `MAX_EVENTS_HISTORY` | `1000` | In-memory history buffer |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000/ws` | WebSocket URL for frontend |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | REST API URL for frontend |

---

## 🎨 Attack Types & Colors

| Attack Type | Color | Frequency |
|-------------|-------|-----------|
| DDoS | 🔴 `#ff4444` | Very Common |
| Malware | 🟠 `#ff8800` | Common |
| Phishing | 🟡 `#ffff00` | Common |
| Ransomware | 🩷 `#ff0088` | Moderate |
| Intrusion | 🩵 `#00ffff` | Moderate |
| BruteForce | 🟣 `#ff00ff` | Common |
| SQLInjection | 🟢 `#00ff88` | Moderate |
| XSS | 🔵 `#8888ff` | Moderate |
| ZeroDay | ⚪ `#ffffff` | Rare |

---

## 📈 Performance

- ✅ Handles **1,000+ events/second** (configurable via `EVENTS_PER_SECOND`)
- ✅ WebSocket broadcasts to **unlimited concurrent clients**
- ✅ Frontend renders up to **200 simultaneous arcs** with no UI lag
- ✅ **Batched DB writes** to minimize PostgreSQL pressure
- ✅ **Graceful degradation** — runs without Redis or PostgreSQL (in-memory only)

---

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

---

## 📄 License

[MIT](https://choosealicense.com/licenses/mit/)