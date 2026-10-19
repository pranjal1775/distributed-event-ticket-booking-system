"""Run a disposable one-seat booking demo through the frontend/gateway stack.

Examples:
  python scripts/demo.py --mode race
  python scripts/demo.py --mode failure --compose-project dsmp_demo \
      --frontend-url http://localhost:13000 --gateway-url http://localhost:18000

The script creates one uniquely named event and removes only that event and
its dependent booking/notification rows when it exits.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path


def api_request(base_url: str, path: str, payload=None, token=None):
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base_url + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        return error.code, parsed


def compose_command(project: str | None, *args: str) -> list[str]:
    command = ["docker", "compose"]
    if project:
        command += ["--project-name", project]
    return command + list(args)


def env_file_value(key: str, default: str) -> str:
    env_path = Path(".env")
    if not env_path.exists():
        return os.environ.get(key, default)
    for line in env_path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            return os.environ.get(key, value.strip().strip('"').strip("'"))
    return os.environ.get(key, default)


def database_counts(project: str | None, event_id: int, seat_id: int) -> tuple[int, int, int, int]:
    sql = (
        "SELECT (SELECT count(*) FROM bookings WHERE event_id={event_id} AND booking_status='confirmed') || ',' || "
        "(SELECT count(*) FROM booking_items bi JOIN bookings b ON b.id=bi.booking_id WHERE b.event_id={event_id}) || ',' || "
        "(SELECT count(*) FROM seats WHERE id={seat_id} AND status='booked') || ',' || "
        "(SELECT count(*) FROM seats WHERE id={seat_id} AND status='available')"
    ).format(event_id=event_id, seat_id=seat_id)
    command = compose_command(
        project,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        env_file_value("POSTGRES_USER", "ticketuser"),
        "-d",
        env_file_value("POSTGRES_DB", "ticketdb"),
        "-Atc",
        sql,
    )
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return tuple(map(int, result.stdout.strip().split(",")))


def cleanup_event(project: str | None, event_id: int) -> None:
    sql = (
        "DELETE FROM notifications WHERE booking_id IN (SELECT id FROM bookings WHERE event_id={0}); "
        "DELETE FROM bookings WHERE event_id={0}; DELETE FROM events WHERE id={0};"
    ).format(event_id)
    command = compose_command(
        project,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        env_file_value("POSTGRES_USER", "ticketuser"),
        "-d",
        env_file_value("POSTGRES_DB", "ticketdb"),
        "-c",
        sql,
    )
    subprocess.run(command, check=True, capture_output=True, text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("race", "failure"), default="race")
    parser.add_argument("--gateway-url", default="http://localhost:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--compose-project", help="Compose project name, if not the directory default")
    parser.add_argument("--requests", type=int, default=20)
    args = parser.parse_args()
    if not 2 <= args.requests <= 40:
        parser.error("--requests must be between 2 and 40 (gateway rate limit is 60/minute)")

    gateway = args.gateway_url.rstrip("/")
    frontend = args.frontend_url.rstrip("/")
    event_id = None
    try:
        health_code, health = api_request(gateway, "/health")
        if health_code != 200:
            raise RuntimeError(f"gateway health failed: HTTP {health_code}")
        event_code, events = api_request(frontend, "/api/events/")
        if event_code != 200:
            raise RuntimeError(f"frontend-to-gateway event request failed: HTTP {event_code}")

        user_code, user = api_request(
            frontend,
            "/api/users/login",
            {"email": os.environ.get("DEMO_USER_EMAIL", "user@ticketbook.com"),
             "password": os.environ.get("DEMO_USER_PASSWORD", "user123")},
        )
        admin_code, admin = api_request(
            frontend,
            "/api/users/login",
            {"email": os.environ.get("DEMO_ADMIN_EMAIL", "admin@ticketbook.com"),
             "password": os.environ.get("DEMO_ADMIN_PASSWORD", "admin123")},
        )
        if user_code != 200 or admin_code != 200:
            raise RuntimeError("demo login failed; check the local seed credentials or DEMO_* variables")
        user_token, admin_token = user["access_token"], admin["access_token"]

        denial, _ = api_request(
            frontend,
            "/api/events/",
            {"name": "unauthorized-demo-check", "date": "2030-01-01", "time": "12:00:00",
             "venue": "Demo", "city": "Demo", "total_seats": 1, "price": "1.00", "rows": "A", "cols": 1},
            user_token,
        )
        if denial != 403:
            raise RuntimeError(f"regular-user admin check expected HTTP 403, got {denial}")

        event_payload = {
            "name": f"temporary-demo-{uuid.uuid4().hex[:10]}",
            "description": "Temporary event created by scripts/demo.py",
            "date": "2030-01-01",
            "time": "12:00:00",
            "venue": "Demo Hall",
            "city": "Demo City",
            "total_seats": 1,
            "price": "1.00",
            "rows": "A",
            "cols": 1,
        }
        code, event = api_request(frontend, "/api/events/", event_payload, admin_token)
        if code != 201:
            raise RuntimeError(f"temporary event creation failed: HTTP {code}")
        event_id = event["id"]
        code, seats = api_request(frontend, f"/api/events/{event_id}/seats/available")
        if code != 200 or len(seats) != 1:
            raise RuntimeError("event did not generate the expected single available seat")
        seat_id = seats[0]["id"]

        def attempt(_):
            return api_request(
                frontend,
                "/api/bookings/",
                {"event_id": event_id, "seat_ids": [seat_id]},
                user_token,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.requests) as pool:
            results = list(pool.map(attempt, range(args.requests)))
        statuses = Counter(code for code, _ in results)
        confirmed, items, booked, available = database_counts(args.compose_project, event_id, seat_id)

        if args.mode == "failure":
            if statuses != {402: args.requests} or (confirmed, items, booked, available) != (0, 0, 0, 1):
                raise RuntimeError(f"payment rollback failed: statuses={dict(statuses)}, db={(confirmed, items, booked, available)}")
        else:
            if statuses.get(201) != 1 or any(code not in (201, 402, 409) for code, _ in results):
                raise RuntimeError(f"same-seat race failed: statuses={dict(statuses)}")
            if (confirmed, items, booked, available) != (1, 1, 1, 0):
                raise RuntimeError(f"database race invariant failed: db={(confirmed, items, booked, available)}")
            _, body = next(result for result in results if result[0] == 201)
            notification_code, notifications = api_request(frontend, "/api/notifications/my", token=user_token)
            if notification_code != 200 or not any(n["booking_id"] == body["id"] for n in notifications):
                raise RuntimeError("confirmed booking notification was not visible")

        print(json.dumps({
            "gateway_health": "ok",
            "frontend_event_list_count": len(events),
            "regular_user_admin_create_status": denial,
            "mode": args.mode,
            "booking_response_counts": dict(sorted(statuses.items())),
            "database_confirmed_bookings_items_booked_available": [confirmed, items, booked, available],
            "booking_notification": "verified" if args.mode == "race" else "not applicable",
        }, sort_keys=True))
    finally:
        if event_id is not None:
            cleanup_event(args.compose_project, event_id)
            print("Temporary event and dependent booking/notification rows cleaned up.")


if __name__ == "__main__":
    main()
