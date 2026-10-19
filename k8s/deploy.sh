#!/usr/bin/env bash
# Build images, load them into the existing Minikube profile, and deploy.
# This script never starts/resets Minikube or replaces app-secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MINIKUBE_BIN="$(command -v minikube || true)"
if [[ -z "$MINIKUBE_BIN" ]]; then
  echo "ERROR: minikube is not on PATH. Install it or invoke this script in a shell where it is available." >&2
  exit 1
fi
"$MINIKUBE_BIN" status
kubectl get nodes >/dev/null
kubectl config current-context

echo "[1/4] Building application images..."
docker build -t ticket-booking/user-service:latest         services/user-service
docker build -t ticket-booking/event-service:latest        services/event-service
docker build -t ticket-booking/booking-service:latest      services/booking-service
docker build -t ticket-booking/notification-service:latest services/notification-service
docker build -t ticket-booking/api-gateway:latest          gateway
docker build -t ticket-booking/frontend:latest             frontend

echo "Loading images into the existing Minikube profile..."
for image in \
  postgres:15-alpine \
  ticket-booking/user-service:latest \
  ticket-booking/event-service:latest \
  ticket-booking/booking-service:latest \
  ticket-booking/notification-service:latest \
  ticket-booking/api-gateway:latest \
  ticket-booking/frontend:latest; do
  "$MINIKUBE_BIN" image load "$image"
done

echo "[2/4] Applying configuration and database manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
if ! kubectl get secret app-secrets -n ticket-booking >/dev/null 2>&1; then
  echo "ERROR: Secret app-secrets is missing. Provision strong local credentials first; k8s/secret.yaml contains sample values and is intentionally not applied." >&2
  exit 1
fi
kubectl apply -f k8s/postgres/init-sql-configmap.yaml
kubectl apply -f k8s/postgres/pvc.yaml
kubectl apply -f k8s/postgres/service.yaml
kubectl apply -f k8s/postgres/deployment.yaml

echo "Waiting for PostgreSQL..."
kubectl rollout status deployment/postgres -n ticket-booking --timeout=180s

echo "[3/4] Applying application services..."
for service in user-service event-service notification-service booking-service api-gateway frontend; do
  kubectl apply -f "k8s/$service/service.yaml"
  kubectl apply -f "k8s/$service/deployment.yaml"
done

echo "[4/4] Waiting for all deployments..."
for deployment in user-service event-service notification-service booking-service api-gateway frontend; do
  kubectl rollout status "deployment/$deployment" -n ticket-booking --timeout=180s
done

echo "Deployment complete. Verify with: kubectl get pods,svc,pvc -n ticket-booking"
echo "Frontend NodePort: http://<minikube-node-ip>:30001"
echo "If Windows cannot route to the Minikube node IP, run in another terminal:"
echo "  kubectl port-forward --address 127.0.0.1 service/frontend 13001:3000 -n ticket-booking"
echo "Then open http://127.0.0.1:13001"
