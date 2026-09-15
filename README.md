# ApexFlo — In-Cinema Commerce Platform

A focused mobile-web cinema ordering system. Patrons order food from their seats; staff manage stock and fulfil orders. PostgreSQL is the stock authority, so concurrent checkout cannot oversell.

## Stack

### Frontend

Static HTML/CSS/JavaScript patron and admin applications.

### Backend

FastAPI with async SQLAlchemy, cookie-based anonymous patron sessions, and admin authentication.

### Stock Storage

PostgreSQL inventory rows; Redis caches menu projections and carries stock-change events to WebSocket clients.

### System of Record

PostgreSQL. Checkout conditionally decrements stock in one transaction; Redis is never checkout authority.

### Digital Twin

Standard-library simulator that creates bursty, screen/showtime/audience demand and reports p95 latency, queue depth, stock-sync lag, 409 runouts, and oversells.

## Live Frontend Demos

- Patron: [apexflo-assignment-5dlz.vercel.app](https://apexflo-assignment-5dlz.vercel.app/)
- Admin: [apexflo-assignment.vercel.app](https://apexflo-assignment.vercel.app/)

The deployed frontend needs the backend URL configured before live ordering works.

## Local Setup

### Prerequisites

- Python 3.12+
- Docker Desktop (recommended), or local PostgreSQL 16 and Redis 7

### 1. Backend

#### Install dependencies

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

#### Configure environment

Copy `.env.example` to `.env`. For local non-Docker use, set valid local `DATABASE_URL`, `REDIS_URL`, and `ADMIN_ACCESS_KEY`.

#### Initialize database

The app creates schema and idempotently seeds demo data at startup.

#### Start server

Recommended one-command stack:

```powershell
docker compose up --build
```

Without Docker, start PostgreSQL and Redis locally, then:

```powershell
venv\Scripts\uvicorn app.main:app --reload
```

API: <http://localhost:8000/docs> · Health: <http://localhost:8000/health>

#### Run tests

```powershell
venv\Scripts\python -m pytest -v
```

### 2. Frontend

#### Install dependencies

None; both frontends are static HTML.

#### Start development server

Use the FastAPI-served pages, not `file:///` HTML files:

```text
http://localhost:8000/patron?show_id=1&screen_id=1&seat=A1
http://localhost:8000/admin
```

#### Patron flow

The QR-style URL supplies show, screen, and seat. The page creates an anonymous session, fetches live menu/stock, supports cart/checkout, and tracks `PLACED → PREPARING → READY → DELIVERED`.

#### Admin flow

Log in with the `ADMIN_ACCESS_KEY` (default: `apexflo-admin-demo`). Admin can restock, add menu items, and move orders through kitchen status. The queue polls every four seconds; stock changes notify patron screens through Redis/WebSockets.

### 3. Digital Twin

#### Install dependencies

None beyond Python 3.10+.

#### Run simulator

```powershell
venv\Scripts\python -m digital_twin.simulator
```

For a 25k-user-style scenario:

```powershell
venv\Scripts\python -m digital_twin.simulator --screens 40 --patrons-per-screen 625 --spike 4 --workers 25
```

The generated readout is in `digital_twin/RESULTS.md`.

## Deployment

### Frontend

Deploy `frontend/patron` and `frontend/admin` as separate Vercel projects. Configure their API and WebSocket base URLs to the deployed backend; never put database URLs or secrets in Vercel.

### Backend

Deploy the Dockerfile to Railway or Render, with managed PostgreSQL and Redis. Set `APP_ENV=production`, `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `ADMIN_ACCESS_KEY`; generate a public domain and restrict CORS to the two Vercel origins. Vercel alone is unsuitable because this project requires a persistent API/WebSocket service and managed data stores.

### Deploy it yourself

1. Push this repository to GitHub.
2. On Railway/Render, create PostgreSQL and Redis, then deploy the repository as a Docker service.
3. Set the backend variables above and generate its public HTTPS domain.
4. Set both frontend API/WebSocket base URLs to that backend domain; deploy `frontend/patron` and `frontend/admin` as separate Vercel projects.
5. Add both Vercel domains to backend CORS, redeploy, then test menu → checkout → admin restock.

## Repository Structure

```text
apexflo/
├── app/
│   ├── core/          configuration, database, Redis, authentication
│   ├── models/        order, menu, inventory, offer data models
│   ├── routers/       patron, admin, checkout, realtime API routes
│   ├── schemas/       request and response contracts
│   ├── services/      checkout, stock, menu, offer, order logic
│   ├── main.py        FastAPI app and startup lifecycle
│   └── seed.py        idempotent demo data
├── frontend/
│   ├── patron/        mobile patron page
│   └── admin/         operations and kitchen page
├── digital_twin/      demand/load simulator and results
├── docs/              review notes
├── design-doc.md      architecture and design decisions
├── tests/             correctness and concurrency tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```
