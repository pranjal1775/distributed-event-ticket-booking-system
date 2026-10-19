@echo off
REM ============================================================
REM deploy.bat — Build images and deploy to local Kubernetes
REM Requires: minikube, kubectl, Docker Desktop
REM Usage: k8s\deploy.bat
REM ============================================================

echo [1/4] Locating the existing Minikube profile...
where minikube >nul 2>&1
if errorlevel 1 (
  if exist "%ProgramFiles%\Kubernetes\Minikube\minikube.exe" (
    set "MINIKUBE_EXE=%ProgramFiles%\Kubernetes\Minikube\minikube.exe"
  ) else (
    echo ERROR: minikube.exe was not found on PATH or in %ProgramFiles%\Kubernetes\Minikube.
    exit /b 1
  )
) else (
  set "MINIKUBE_EXE=minikube"
)
"%MINIKUBE_EXE%" status
if errorlevel 1 exit /b %ERRORLEVEL%

echo [2/4] Building Docker images...
docker build -t ticket-booking/user-service:latest         services\user-service
if errorlevel 1 exit /b %ERRORLEVEL%
docker build -t ticket-booking/event-service:latest        services\event-service
if errorlevel 1 exit /b %ERRORLEVEL%
docker build -t ticket-booking/booking-service:latest      services\booking-service
if errorlevel 1 exit /b %ERRORLEVEL%
docker build -t ticket-booking/notification-service:latest services\notification-service
if errorlevel 1 exit /b %ERRORLEVEL%
docker build -t ticket-booking/api-gateway:latest          gateway
if errorlevel 1 exit /b %ERRORLEVEL%
docker build -t ticket-booking/frontend:latest             frontend
if errorlevel 1 exit /b %ERRORLEVEL%

echo Loading application images into Minikube...
"%MINIKUBE_EXE%" image load postgres:15-alpine
if errorlevel 1 exit /b %ERRORLEVEL%
"%MINIKUBE_EXE%" image load ticket-booking/user-service:latest
if errorlevel 1 exit /b %ERRORLEVEL%
"%MINIKUBE_EXE%" image load ticket-booking/event-service:latest
if errorlevel 1 exit /b %ERRORLEVEL%
"%MINIKUBE_EXE%" image load ticket-booking/booking-service:latest
if errorlevel 1 exit /b %ERRORLEVEL%
"%MINIKUBE_EXE%" image load ticket-booking/notification-service:latest
if errorlevel 1 exit /b %ERRORLEVEL%
"%MINIKUBE_EXE%" image load ticket-booking/api-gateway:latest
if errorlevel 1 exit /b %ERRORLEVEL%
"%MINIKUBE_EXE%" image load ticket-booking/frontend:latest
if errorlevel 1 exit /b %ERRORLEVEL%

echo [3/4] Applying Kubernetes manifests...
kubectl apply -f k8s\namespace.yaml
if errorlevel 1 exit /b %ERRORLEVEL%

REM ConfigMaps and Secrets first
kubectl apply -f k8s\configmap.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl get secret app-secrets -n ticket-booking >nul 2>&1
if errorlevel 1 (
  echo ERROR: Secret app-secrets is missing. Create it with non-sample values before deploying.
  exit /b 1
)
kubectl apply -f k8s\postgres\init-sql-configmap.yaml
if errorlevel 1 exit /b %ERRORLEVEL%

REM Postgres (storage + service + deployment)
kubectl apply -f k8s\postgres\pvc.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\postgres\service.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\postgres\deployment.yaml
if errorlevel 1 exit /b %ERRORLEVEL%

echo Waiting for postgres to be ready...
kubectl wait --for=condition=ready pod -l app=postgres -n ticket-booking --timeout=120s
if errorlevel 1 exit /b %ERRORLEVEL%

REM Application services
kubectl apply -f k8s\user-service\service.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\user-service\deployment.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\event-service\service.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\event-service\deployment.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\notification-service\service.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\notification-service\deployment.yaml
if errorlevel 1 exit /b %ERRORLEVEL%

REM Booking service (3 replicas — horizontal scaling demo)
kubectl apply -f k8s\booking-service\service.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\booking-service\deployment.yaml
if errorlevel 1 exit /b %ERRORLEVEL%

REM Gateway and frontend
kubectl apply -f k8s\api-gateway\service.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\api-gateway\deployment.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\frontend\service.yaml
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl apply -f k8s\frontend\deployment.yaml
if errorlevel 1 exit /b %ERRORLEVEL%

echo Waiting for application deployments...
kubectl rollout status deployment/user-service -n ticket-booking --timeout=180s
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl rollout status deployment/event-service -n ticket-booking --timeout=180s
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl rollout status deployment/notification-service -n ticket-booking --timeout=180s
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl rollout status deployment/booking-service -n ticket-booking --timeout=180s
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl rollout status deployment/api-gateway -n ticket-booking --timeout=180s
if errorlevel 1 exit /b %ERRORLEVEL%
kubectl rollout status deployment/frontend -n ticket-booking --timeout=180s
if errorlevel 1 exit /b %ERRORLEVEL%

echo [4/4] Deployment complete.
echo.
echo Access URLs:
echo   API Gateway : http://127.0.0.1:30000
echo   Frontend    : http://127.0.0.1:30001
echo   If NodePort is unreachable from Windows, run in another terminal:
echo     kubectl port-forward --address 127.0.0.1 service/frontend 13001:3000 -n ticket-booking
echo     then open http://127.0.0.1:13001
echo.
echo Run: kubectl get pods -n ticket-booking
echo Run: minikube service api-gateway -n ticket-booking
