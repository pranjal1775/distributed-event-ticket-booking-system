# Implementation roadmap: Phase 4 onward

The repository did not define numbered phases after Phase 3. This proposed checklist groups the remaining work around the existing services and the project's distributed-systems goals; it does not present assumed milestones as original requirements.

## Phase 4 — Event management and seat availability

- [x] Public event listing and detail endpoints.
- [x] Admin-only event creation and status updates.
- [x] Generate seats in the same transaction as event creation.
- [x] Validate seat layouts and list all/available seats.
- [x] Automated authorization, event, and seat tests (`tests/test_events.py`).
- [x] Verify event creation and seat generation through the deployed services against PostgreSQL.

**Status:** Implemented, unit-tested, and exercised against PostgreSQL in an isolated Compose deployment.

## Phase 5 — Atomic booking and concurrency control

- [x] Lock requested seats in ascending ID order with `SELECT FOR UPDATE`.
- [x] Reject duplicate seat IDs, unavailable seats, and seats belonging to another event.
- [x] Persist booking, items, seat states, and event availability in one transaction.
- [x] Enforce `UNIQUE(seat_id)` as the database-level double-booking guard.
- [x] Unit-test competing requests and rollback behavior.
- [x] Send 20 simultaneous same-seat requests through the gateway to three Booking Service replicas using PostgreSQL: one returned 201, 19 returned 409, and database rows showed one confirmed booking/item and one booked seat.

**Status:** Unit and PostgreSQL concurrency acceptance passed. SQLite mutex tests are not used as evidence for PostgreSQL locking.

## Phase 6 — Payment and notification resilience

- [x] Support deterministic `success` and `failure` payment modes plus randomized demo mode.
- [x] On deterministic payment failure, return 402 and leave the seat available without booking or item rows; verified against PostgreSQL.
- [x] Commit confirmed bookings before attempting notification delivery.
- [x] Authenticate booking-to-notification requests with the internal token.
- [x] Log notification exceptions and non-2xx responses without undoing confirmed bookings; regression-tested.
- [x] Verify a successful booking's notification is visible through the frontend proxy.
- [ ] Add durable notification retry/outbox behavior if delivery guarantees become a requirement; current behavior is fire-and-forget.

**Status:** Booking/payment rollback and notification visibility passed local Compose/PostgreSQL checks. Durable delivery is outside the current implementation.

## Phase 7 — Gateway routing and request security

- [x] Route public auth/event requests and protected user, booking, and notification requests.
- [x] Validate JWT signature and expiry at the gateway and again downstream.
- [x] Apply per-IP rate limiting and map upstream errors to 503/504; automated tests cover these cases.
- [x] Verify gateway health, live downstream routing, login/profile, admin denial, events, bookings, and notifications through the deployed services.
- [ ] Fault-inject a live upstream outage and exercise the live rate limit; current evidence for those cases is from unit tests.

**Status:** Live routes and authorization passed. Runtime fault-injection and rate-limit acceptance remain unverified.

## Phase 8 — Frontend and API integration

- [x] Implement registration/login, event browsing, seat selection, booking, and booking/notification views.
- [x] Route `/api` through the Vite development proxy and production Nginx proxy.
- [x] Build frontend production assets.
- [x] Exercise listing, login/profile, role denial, seat generation, booking, booking history, and notifications through production Nginx → gateway → services.
- [ ] Verify interactive UI behavior with browser automation; no browser automation tool was available in this environment.
- [ ] Add admin event-management screens if event writes need a UI rather than the existing API.

**Status:** API-level frontend integration passed, including booking and notification checks. Interactive browser testing remains unverified.

## Phase 9 — Docker Compose deployment

- [x] Define PostgreSQL, services, gateway, frontend, bridge networking, and persistent PostgreSQL volume.
- [x] Require `JWT_SECRET`; pass `PAYMENT_MODE` through Compose.
- [x] Remove fixed global `container_name` values and publish only frontend and gateway host ports. Internal services and PostgreSQL are reached on Compose DNS; booking replicas no longer conflict on a host port.
- [x] Add healthchecks and readiness dependencies for PostgreSQL, backend services, gateway, and frontend.
- [x] Validate `docker compose config --quiet` and build all six images.
- [x] Run an isolated `dsmp_final` Compose project alongside the existing project; all services became healthy and three Booking Service replicas ran.
- [x] Verify frontend proxy flow, PostgreSQL same-seat concurrency, deterministic payment rollback, and persistence after recreating the isolated PostgreSQL container (counts remained 2 users, 5 events, 170 seats).
- [x] Correct the frontend health probe to use IPv4 loopback after the initial `localhost` probe failed in the Nginx container.

**Status:** Isolated Compose startup, health, scaling, persistence, PostgreSQL booking behavior, and API flows passed. The isolated named volume is retained; the original `ds_mp` project was not stopped.

## Phase 10 — Kubernetes deployment and scaling

- [x] Define Deployments and Services for PostgreSQL, all services, gateway, and frontend.
- [x] Configure three Booking Service replicas and readiness/liveness probes.
- [x] Load credentials from a Secret and runtime settings from a ConfigMap.
- [x] Provide PostgreSQL PVC-backed storage and schema/seed ConfigMap.
- [x] Provide Windows and Unix deployment scripts that build/load images, preserve the existing Secret, and wait for rollouts; all 19 YAML manifests parse.
- [x] Create a fresh `app-secrets` Secret in the local Minikube cluster without writing secret values into the repository or applying sample values.
- [x] Apply manifests to the already-running Minikube cluster; all six app Deployments and PostgreSQL became ready.
- [x] Verify ClusterIP service endpoints, three Booking Service replicas, a Bound PostgreSQL PVC, and successful event/login/booking/history/notification calls through the frontend proxy.
- [x] Verify the frontend response from Windows using local port-forward after confirming the private Minikube node IP was not host-routable.
- [ ] Browser-driven click automation remains unavailable; the verified user flows used real HTTP requests against the live deployed services.

**Status:** Local Minikube deployment and live API flow acceptance passed. The Windows-accessible URL is `http://127.0.0.1:13001` while `kubectl port-forward --address 127.0.0.1 service/frontend 13001:3000 -n ticket-booking` remains running. Interactive browser automation is unverified.

## Phase 11 — Documentation and final acceptance

- [x] Document architecture, schema constraints, APIs, environment, local setup, Docker/Kubernetes commands, tests, and design limitations in `README.md`.
- [x] Add `scripts/demo.py` for repeatable concurrent booking and payment-failure demonstrations with scoped cleanup.
- [x] Record actual isolated Compose/PostgreSQL and Minikube verification results in this roadmap.
- [x] Run final full test suite (109 passed, one Starlette deprecation warning), frontend build, Compose validation, Kubernetes YAML parsing, and demo script syntax check after documentation/demo updates.
- [ ] Perform interactive browser click automation; the frontend was verified via HTTP/API flows through the production Nginx proxy.

**Status:** Automated tests, production frontend build, isolated Compose/PostgreSQL checks, and local Minikube deployment acceptance passed. Remaining check: interactive browser click automation. Durable notification retries/outbox and live gateway fault-injection/rate-limit checks remain documented follow-up work, not deployment blockers.
