# Distributed Event Ticket Booking System

A B.Tech mini-project demonstrating distributed systems concepts — microservices, horizontal scaling, concurrency control, logical clocks, and fault tolerance — using Python (FastAPI), React, PostgreSQL, Docker, and Kubernetes.

---

## Architecture

```
Browser
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  API Gateway  :8000                                         │
│  • JWT validation (early rejection)                         │
│  • Per-IP rate limiting (sliding window)                    │
│  • Reverse proxy to downstream services                     │
└──────┬──────────┬──────────┬──────────────────┬────────────┘
       │          │          │                  │
       ▼          ▼          ▼                  ▼
  User Svc   Event Svc  Booking Svc (×3)  Notification Svc
   :8001       :8002        :8003              :8004
       │          │          │                  │
       └──────────┴──────────┴──────────────────┘
                            │
                            ▼
                      PostgreSQL :5432
                      (shared DB)
```

### Services

| Service | Container port | Responsibility |
|---|---|---|
| api-gateway | 8000 (published) | JWT validation, rate limiting, reverse proxy |
| user-service | 8001 (internal) | Register, login, JWT issuance, user lookup |
| event-service | 8002 (internal) | Event CRUD, seat layout generation, availability |
| booking-service | 8003 (internal) | Seat locking, payment simulation, booking creation |
| notification-service | 8004 (internal) | Store and serve booking notifications |
| frontend | 3000 (published) | React/Vite SPA served by Nginx in containers |
| postgres | 5432 (internal) | Shared PostgreSQL database; not published to the host by Compose |

### Database Tables

| Table | Owner |
|---|---|
| `users` | user-service |
| `events`, `seats` | event-service |
| `bookings`, `booking_items` | booking-service |
| `notifications` | notification-service |

Named database constraints in `database/init.sql` enforce user roles, event status and seat counts, seat status and unique labels per event, payment and booking statuses, unique seat assignment in `booking_items`, and notification status. Inline checks also require positive event capacity and nonnegative availability and price. Foreign keys connect seats to events and booking items to bookings/seats.

> **Note:** booking-service directly accesses `events` and `seats` tables in one transaction. This is a deliberate simplification documented as a future improvement (use event-service API instead).

---

## Key Distributed Systems Concepts

### Concurrency Control — `SELECT FOR UPDATE`
When a booking request arrives, booking-service locks the requested seat rows with `SELECT FOR UPDATE ... ORDER BY id` inside a transaction. Ordering by `id` prevents deadlocks when two concurrent requests overlap on the same seat set. Only one transaction holds the lock; others block until it commits or rolls back.

The `UNIQUE(seat_id)` constraint on `booking_items` is a second safety net at the database level — even if two transactions somehow pass the status check, only one INSERT will succeed.

### Horizontal Scaling — Kubernetes
booking-service runs as **3 replicas** in Kubernetes. The Kubernetes ClusterIP Service distributes requests across all pods using round-robin. Each pod maintains its own in-process Lamport clock; the clock value is stored in the `bookings` table so events can be ordered across replicas.

### Lamport Logical Clock
Each booking-service pod increments a thread-safe in-process counter (`_logical_clock`, protected by `threading.Lock`) and stores the value in `bookings.logical_clock`. Notifications also carry a clock value. This demonstrates causal ordering of events across distributed processes.

### Fault Tolerance — Notification Fire-and-Forget
booking-service calls notification-service **after** `db.commit()` inside a `try/except`. If notification-service is down, the booking remains confirmed and the failure is logged. No retry is implemented — this is documented as a deliberate simplification.

### JWT — Defence in Depth
JWTs are validated at **two layers**:
1. API Gateway — rejects expired/invalid tokens immediately, before any downstream call
2. Each downstream service — re-validates independently, so services are secure even if called directly (bypassing the gateway)

---

## Project Structure

```
ds_mp/
├── database/
│   └── init.sql                  # Schema + seed data
├── gateway/
│   └── app/                      # API Gateway (FastAPI)
├── services/
│   ├── user-service/app/
│   ├── event-service/app/
│   ├── booking-service/app/
│   └── notification-service/app/
├── frontend/
│   └── src/                      # React/Vite SPA
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── postgres/
│   ├── user-service/
│   ├── event-service/
│   ├── booking-service/          # replicas: 3
│   ├── notification-service/
│   ├── api-gateway/
│   ├── frontend/
│   ├── deploy.sh                 # Linux/Mac one-command deploy
│   └── deploy.bat                # Windows one-command deploy
├── tests/
│   ├── test_users.py             # 21 tests
│   ├── test_events.py            # 23 tests
│   ├── test_bookings.py          # 24 tests
│   ├── test_notifications.py     # 12 tests
│   ├── test_gateway.py           # 23 tests
│   └── test_concurrent_booking.py # 6 concurrent tests
├── docs/diagrams/
├── docker-compose.yml
├── .env.example
└── .gitignore
```

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop (for Docker Compose / Kubernetes)
- minikube + kubectl (for Kubernetes demo)

---

## Quick Start — Local services (PostgreSQL in Docker)

### 1. Install Python dependencies

Each service has its own `requirements.txt`. Install for the service you want to run:

```bash
pip install -r services/user-service/requirements.txt
pip install -r services/event-service/requirements.txt
pip install -r services/booking-service/requirements.txt
pip install -r services/notification-service/requirements.txt
pip install -r gateway/requirements.txt
```

### 2. Set environment variables

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env; replace all example secrets. For local non-Compose services,
# set POSTGRES_HOST=localhost.
```

### 3. Start PostgreSQL

```powershell
docker run -d --name ticketbook-postgres-dev `
  --env-file .env `
  -p 5433:5432 `
  -v "${PWD}/database/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" `
  postgres:15-alpine
```

For local service processes, set `POSTGRES_HOST=localhost` and `POSTGRES_PORT=5433` in `.env`. The distinct container name and host port avoid colliding with an existing Compose database.

### 4. Run services (separate terminals)

```bash
cd services/user-service   && uvicorn app.main:app --port 8001 --reload
cd services/event-service  && uvicorn app.main:app --port 8002 --reload
cd services/booking-service && uvicorn app.main:app --port 8003 --reload
cd services/notification-service && uvicorn app.main:app --port 8004 --reload
cd gateway                 && uvicorn app.main:app --port 8000 --reload
```

### 5. Run frontend

```bash
cd frontend && npm install && npm run dev
# Open http://localhost:3000
```

---

## Quick Start — Docker Compose

```powershell
# Copy the placeholder environment file only if .env does not already exist;
# then replace its example secret values.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

```bash
# Start all services in the background
docker compose up --build -d

# Scale booking-service to 3 instances (horizontal scaling demo)
docker compose up -d --scale booking-service=3

# Check status, follow logs, and stop without deleting the persistent DB volume
docker compose ps
docker compose logs -f booking-service
docker compose down

# Access
# Frontend:    http://localhost:3000
# API Gateway: http://localhost:8000
```

Compose publishes only the gateway and frontend. Service-to-service calls use Compose DNS, PostgreSQL is reachable inside the Compose network, and the Booking Service can scale without a fixed host-port collision. To run an isolated copy alongside another stack, set distinct frontend/gateway ports in the same PowerShell session before `docker compose -p dsmp_demo up -d --build --scale booking-service=3`:

```powershell
$env:GATEWAY_HOST_PORT = '18000'
$env:FRONTEND_HOST_PORT = '13000'
docker compose -p dsmp_demo up -d --build --scale booking-service=3
```

Stop that project with `docker compose -p dsmp_demo down`; this leaves its named PostgreSQL volume intact. Do not use `down -v` if you need to preserve the database.

---

## Kubernetes deployment (Minikube)

The deployment scripts use the already-running Minikube profile; they do not start or reset the cluster. They build and load the six application images, preserve the current Kubernetes Secret, apply the PostgreSQL PVC and workloads, and wait for rollouts. Provision `app-secrets` in the `ticket-booking` namespace with unique `POSTGRES_PASSWORD`, `JWT_SECRET` (at least 32 characters), and `INTERNAL_SERVICE_TOKEN` values using your secrets manager before the first deploy. **Do not apply `k8s/secret.yaml`: it contains sample credentials.**

```powershell
# Windows: from the repository root; minikube.exe must be on PATH or in its standard Program Files location.
k8s\deploy.bat

# Check readiness and persistent storage
kubectl get pods -n ticket-booking
kubectl get deployments,services,pvc -n ticket-booking
kubectl get endpointslices -n ticket-booking

# On Windows configurations where the Minikube NodePort is not routable,
# keep this running in a terminal and open the URL shown below.
kubectl port-forward --address 127.0.0.1 service/frontend 13001:3000 -n ticket-booking
```

Open **http://127.0.0.1:13001** while the port-forward is running. The frontend's production Nginx configuration proxies `/api` requests to the API Gateway Service. The frontend NodePort is 30001, but on Windows it may not route through the private Minikube node IP. The API Gateway NodePort is 30000.

For Linux/macOS, `bash k8s/deploy.sh` performs the equivalent build, image load, apply, and rollout checks. To scale booking workers, edit the Deployment replica count or run:

```powershell
kubectl scale deployment/booking-service --replicas=3 -n ticket-booking
kubectl rollout status deployment/booking-service -n ticket-booking
```

---

## Running Tests

Each service has its own `PYTHONPATH`. Run individually:

```bash
# Windows
set PYTHONPATH=services\user-service         && pytest tests/test_users.py -v
set PYTHONPATH=services\event-service        && pytest tests/test_events.py -v
set PYTHONPATH=services\booking-service      && pytest tests/test_bookings.py -v
set PYTHONPATH=services\notification-service && pytest tests/test_notifications.py -v
set PYTHONPATH=gateway                       && pytest tests/test_gateway.py -v
set PYTHONPATH=services\booking-service      && pytest tests/test_concurrent_booking.py -v

# Linux/Mac
PYTHONPATH=services/user-service         pytest tests/test_users.py -v
PYTHONPATH=services/event-service        pytest tests/test_events.py -v
PYTHONPATH=services/booking-service      pytest tests/test_bookings.py -v
PYTHONPATH=services/notification-service pytest tests/test_notifications.py -v
PYTHONPATH=gateway                       pytest tests/test_gateway.py -v
PYTHONPATH=services/booking-service      pytest tests/test_concurrent_booking.py -v
```

### Test Summary

| File | Tests | What it covers |
|---|---|---|
| `test_users.py` | 21 | Register, login, JWT, RBAC, bcrypt |
| `test_events.py` | 23 | CRUD events, seat generation, admin auth |
| `test_bookings.py` | 24 | Booking flow, payment, seat locking, notification failure isolation, auth |
| `test_notifications.py` | 12 | Internal token auth, user JWT, clock |
| `test_gateway.py` | 23 | Proxy, JWT guard, rate limiter, error passthrough |
| `test_concurrent_booking.py` | 6 | 10-thread race, no double-booking, clock uniqueness |
| **Total** | **109** | |

Latest full-suite result: `pytest -q` — **109 passed**, one Starlette deprecation warning for the 422 status constant.

Run the full suite from the project root with `pytest -q`. Test modules isolate each service's generic `app` package, so individual service suites can also be run separately.

Run `python scripts/demo.py --mode race` with the Compose project running. It checks gateway health, frontend proxying, regular-user admin denial, races simultaneous requests for a temporary one-seat event, verifies database state and the user notification, then removes only its temporary event and related rows. To show deterministic payment rollback, set `PAYMENT_MODE=failure` for the Booking Service and recreate its replicas first; then run `python scripts/demo.py --mode failure`. The script verifies HTTP 402, no booking/item rows, and the seat remaining available. Restore the normal Compose payment mode after the demonstration.

See [docs/implementation-roadmap.md](docs/implementation-roadmap.md) for the Phase 4 onward checklist, acceptance criteria, and current verification status.

---

## Seed Data

The database is pre-seeded with:

| Account | Email | Password | Role |
|---|---|---|---|
| Admin | admin@ticketbook.com | admin123 | admin |
| User | user@ticketbook.com | user123 | user |

5 sample events across Bangalore, Mumbai, Pune, Delhi, Chennai.

---

## API Reference

All requests go through the gateway at `http://localhost:8000`.

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/users/register` | None | Register new user |
| POST | `/api/users/login` | None | Login, returns JWT |
| GET | `/api/users/me` | JWT | Current user profile |

Example registration and login requests:

```json
POST /api/users/register
{"email":"demo@example.com","password":"a-long-demo-password","full_name":"Demo User"}

POST /api/users/login
{"email":"demo@example.com","password":"a-long-demo-password"}
```

### Events
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/events/` | None | List active events |
| GET | `/api/events/{id}` | None | Event detail |
| GET | `/api/events/{id}/seats` | None | All seats |
| GET | `/api/events/{id}/seats/available` | None | Available seats only |
| POST | `/api/events/` | JWT (admin) | Create event + seats |
| PATCH | `/api/events/{id}` | JWT (admin) | Update event status |

An administrator can create an event with a generated seat layout:

```json
POST /api/events/
{"name":"Demo Concert","date":"2030-01-01","time":"19:00:00","venue":"Demo Hall","city":"Demo City","total_seats":2,"price":"25.00","rows":"A","cols":2}
```

### Bookings
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/bookings/` | JWT | Create booking |
| GET | `/api/bookings/my` | JWT | My bookings |
| GET | `/api/bookings/{id}` | JWT | Single booking |

Create a booking by sending the returned access token as a Bearer token:

```json
POST /api/bookings/
{"event_id":1,"seat_ids":[1]}
```

### Notifications
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/notifications/my` | JWT | My notifications |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | DB hostname |
| `POSTGRES_PORT` | `5432` | DB port |
| `POSTGRES_DB` | `ticketdb` | Database name |
| `POSTGRES_USER` | `ticketuser` | DB user |
| `POSTGRES_PASSWORD` | required by Compose | DB password |
| `JWT_SECRET` | — | **Must be set** — min 32 chars |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRY_MINUTES` | `60` | Token lifetime |
| `PAYMENT_MODE` | `random` | `success` / `failure` / `random` (95%) |
| `INTERNAL_SERVICE_TOKEN` | required by Compose | Shared secret for booking→notification calls |
| `RATE_LIMIT` | `60` | Max requests per window per IP |
| `RATE_WINDOW` | `60` | Rate limit window in seconds |

`.env.example` contains placeholders only. Keep `.env` local and replace its example JWT, database password, and internal service token before any shared or deployed use. Kubernetes `k8s/secret.yaml` contains sample values and must not be applied as-is; the deploy scripts refuse to create or overwrite `app-secrets`. For local persistent Compose data, `docker compose down` preserves the named volume.

---

## Design Decisions & Simplifications

| Decision | Rationale |
|---|---|
| Shared PostgreSQL | Simplification — in production each service would own its DB |
| booking-service reads events/seats directly | Avoids inter-service HTTP call inside a transaction; documented as future improvement |
| No Redis / RabbitMQ / Kafka | Scope — demonstrates core distributed concepts without message broker complexity |
| Notification fire-and-forget | Booking correctness must not depend on notification delivery |
| In-process Lamport clock | Demonstrates the concept; in production a distributed counter (Redis INCR) would be used |
| `SELECT FOR UPDATE` (not SKIP LOCKED) | Ensures all requests are processed in order; SKIP LOCKED would silently drop requests |
| JWT validated at gateway AND downstream | Defence in depth — services remain secure if called directly |

## Presentation demonstration

Start Compose with three booking replicas, then run the scripted race via the frontend proxy. The demo reports health, frontend event-list access, role denial, concurrent booking response counts, database invariants, and notification visibility. It creates and removes a uniquely identified temporary event; it does not delete any pre-existing events or bookings.

```powershell
docker compose up --build -d --scale booking-service=3
python scripts/demo.py --mode race
docker compose ps
```

For payment rollback, run a deterministic failure pass and then restore the `.env`-configured mode. These commands recreate only Booking Service containers and preserve the database volume:

```powershell
$env:PAYMENT_MODE = 'failure'
docker compose up -d --force-recreate --scale booking-service=3 booking-service
python scripts/demo.py --mode failure
Remove-Item Env:PAYMENT_MODE
docker compose up -d --force-recreate --scale booking-service=3 booking-service
```

The demo's exact PostgreSQL checks and scoped cleanup are implemented in [`scripts/demo.py`](scripts/demo.py). In a separate Compose project, pass its name and frontend/gateway URLs using `--compose-project`, `--frontend-url`, and `--gateway-url`. Seed accounts are for local demonstration only; replace them and their passwords before a shared deployment.

## Verification status and known limitations

- The automated unit suite uses service-level test clients and SQLite/mocks where appropriate; it does not replace live database tests.
- A separate Compose project was started with three booking replicas. PostgreSQL same-seat concurrency, deterministic failure rollback, frontend-to-gateway API flows, health, and named-volume persistence across PostgreSQL container recreation were exercised there.
- Browser interaction was not automated. Frontend checks exercised the production Nginx `/api` proxy with real HTTP requests.
- Minikube deployment was applied and verified: PostgreSQL and all six application Deployments became ready; the Booking Service ran three replicas and the PostgreSQL PVC was Bound. A real event-list/login/seat-selection/booking/history/notification flow succeeded through frontend Nginx and the gateway. The verification used real HTTP requests, not interactive browser automation.
- On this Windows/Minikube setup, the private node IP was not reachable from the host, so the verified browser URL uses `kubectl port-forward` at `http://127.0.0.1:13001`. Keep that terminal running while using the site.
- Kubernetes `app-secrets` was created with fresh random local values and is stored only in the cluster; those values were not written into the repository. The checked-in `k8s/secret.yaml` remains sample data and is not used by the deploy scripts.
- The seeded event dates are from 2025. Existing database rows were preserved; use the admin event endpoint or the demo script's temporary event for a current/future booking demonstration.
- Notifications are fire-and-forget with no retry/outbox, and the gateway's in-memory rate limiter resets on restart and is per process.
