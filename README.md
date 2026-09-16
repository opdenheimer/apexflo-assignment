# ApexFlo — In-Cinema Commerce Platform

A focused mobile-web cinema ordering system. Patrons order food from their seats; staff manage stock and fulfil orders. PostgreSQL is the stock authority, so concurrent checkout cannot oversell.

## Quick Start (Docker - Recommended)

```bash
# 1. Clone and enter directory
git clone <repo-url>
cd apexflo-assignment

# 2. Start everything (PostgreSQL + Redis + API + Frontend)
docker compose up --build -d

# 3. Access the applications
```

### Access URLs (after `docker compose up --build -d`)

| Interface | URL | Notes |
|-----------|-----|-------|
| **Patron (Mobile)** | http://localhost:8000/patron | Add query params: `?show_id=1&screen_id=1&seat=K12` |
| **Admin Dashboard** | http://localhost:8000/admin | Requires admin key set in your .env|
| **API Docs (Swagger)** | http://localhost:8000/docs | Interactive API testing |
| **Health Check** | http://localhost:8000/health | Verifies DB + Redis connectivity |

### Admin Access Key
```
X-Admin-Role: admin
```
**Default key:** `admin` (set via header `X-Admin-Role: admin`)

---

## Running WITHOUT Docker (Local PostgreSQL + Redis)

### Prerequisites
- Python 3.12+
- PostgreSQL 16+ running locally
- Redis 7+ running locally

### 1. Setup PostgreSQL
```bash
# Create database and user
psql -U postgres -c "CREATE DATABASE apexflo_db;"
psql -U postgres -c "CREATE USER apexflo WITH PASSWORD 'apexflo_secret';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE apexflo_db TO apexflo;"
```

### 2. Setup Redis
```bash
# Start Redis (default port 6379)
redis-server
# Or if installed as service:
# sudo systemctl start redis  (Linux)
# brew services start redis   (macOS)
```

### 3. Configure Environment
```bash
# Copy example and edit
cp .env.example .env

# Edit .env with your local settings:
# DATABASE_URL=postgresql+asyncpg://apexflo:apexflo_secret@localhost:5432/apexflo_db
# REDIS_URL=redis://localhost:6379/0
# ADMIN_ACCESS_KEY=admin
```

### 4. Install Python Dependencies
```bash
python -m venv venv
# Windows:
venv\Scripts\pip install -r requirements.txt
# Linux/macOS:
venv/bin/pip install -r requirements.txt
```

### 5. Start Backend API
```bash
# Windows:
venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Linux/macOS:
venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Access Applications
| Interface | URL |
|-----------|-----|
| **Patron** | http://localhost:8000/patron?show_id=1&screen_id=1&seat=K12 |
| **Admin** | http://localhost:8000/admin (Header: `X-Admin-Role: admin`) |
| **API Docs** | http://localhost:8000/docs |
| **Health** | http://localhost:8000/health |

---

## Running Tests

```bash
# Windows:
venv\Scripts\python -m pytest tests/ -v

# Linux/macOS:
venv/bin/python -m pytest tests/ -v
```

**Expected:** 16 tests pass (concurrency, idempotency, offers, inventory, realtime, auth)

---

## Digital Twin Load Simulator

```bash
# Run load test against local API
# Windows:
venv\Scripts\python -m digital_twin.report

# Linux/macOS:
venv/bin/python -m digital_twin.report
```

Generates report with p50/p95/p99 latency, throughput (RPS), and **zero oversell verification**.

---

## Patron Flow (QR Code Style)

The patron interface works via URL parameters (simulating QR code scan):

```
http://localhost:8000/patron?show_id=1&screen_id=1&seat=K12&user_id=anon_abc123
```

| Parameter | Description |
|-----------|-------------|
| `show_id` | Show ID (required) |
| `screen_id` | Screen ID (required) |
| `seat` | Seat identifier (required) |
| `user_id` | Optional anonymous ID (auto-generated if missing) |

**Features:**
- Live menu with real-time stock (WebSocket updates)
- Cart with quantity limits based on live stock
- Checkout with idempotency (prevents double-charge)
- Order tracking: PLACED → PREPARING → READY → DELIVERED

---

## Admin Dashboard

**Access:** http://localhost:8000/admin  
**Auth:** Header `X-Admin-Role: admin`

**Capabilities:**
- **Live Order Queue** — See all orders with items, seat, status
- **Menu Management** — Add items, toggle active/inactive
- **Stock Adjustment** — Restock items (instantly propagates to patron screens via WebSocket)
- **Order Status Control** — Move orders through kitchen workflow

---

## Architecture Highlights

| Component | Technology | Purpose |
|-----------|------------|---------|
| **API** | FastAPI + asyncpg | High-concurrency async backend |
| **Database** | PostgreSQL 16 | Source of truth, atomic stock decrement |
| **Cache/Streams** | Redis 7 | Menu cache, stock projections, event streams |
| **Realtime** | WebSockets + Redis Streams | Live stock sync to patron screens |
| **Frontend** | Vanilla HTML/JS | Mobile-first patron UI, admin dashboard |

**Zero Oversell Guarantee:** Single atomic SQL `UPDATE ... WHERE quantity >= :qty RETURNING` — mathematically impossible to oversell under concurrency.

---

## Repository Structure

```
apexflo-assignment/
├── app/
│   ├── core/          # config, database, redis, auth
│   ├── models/        # SQLAlchemy models (order, menu, inventory, offer)
│   ├── routers/       # API routes (patron, admin, checkout, realtime)
│   ├── schemas/       # Pydantic request/response models
│   ├── services/      # Business logic (checkout, inventory, offers, orders)
│   ├── main.py        # FastAPI app + lifespan
│   └── seed.py        # Idempotent demo data seeding
├── frontend/
│   ├── patron/        # Mobile patron interface (index.html)
│   └── admin/         # Admin/kitchen dashboard (index.html)
├── digital_twin/      # Load simulator + report generator
├── docs/              # Design docs + cross-questioning log
├── tests/             # 16 tests (concurrency, idempotency, offers, etc.)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## Key Features Demonstrated

- ✅ **Atomic Stock Claims** — Zero oversell under 20 concurrent requests for 1 unit
- ✅ **Idempotent Checkout** — Retry-safe with `idempotency_key`
- ✅ **Deterministic Offers** — Priority → Discount → ID tie-break, order-invariant
- ✅ **Real-time Sync** — Redis Streams → WebSocket with version-gated out-of-order protection
- ✅ **Graceful Degradation** — Redis failure falls back to PostgreSQL for menu reads
- ✅ **State Machine Orders** — PLACED → PREPARING → READY → DELIVERED (no invalid transitions)
- ✅ **Digital Twin** — Poisson burst simulator with p95 latency + oversell verification

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://apexflo:yourpassword@localhost:5432/apexflo_db` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `ADMIN_ACCESS_KEY` | `YOUR_ADMIN_ACCESS_KEY ` | Admin dashboard header value |
| `APP_ENV` | `development` | Environment mode |
| `DEBUG` | `True` | Debug logging |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `docker compose up` fails | Ensure Docker Desktop is running; check ports 5432, 6379, 8000 free |
| Health check fails | Verify PostgreSQL/Redis containers are healthy: `docker compose ps` |
| Menu not loading | Check `show_id=1` exists (seeded on startup); verify `/api/menu/1` in browser |
| WebSocket not connecting | Ensure accessing via `http://localhost:8000/patron` (not `file://`) |
| Admin 403 Forbidden | Add header `X-Admin-Role: admin` to request |