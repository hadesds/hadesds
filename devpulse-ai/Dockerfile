# syntax=docker/dockerfile:1
# --- painel (React) ---
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- backend (FastAPI + worker) ---
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/pyproject.toml ./
RUN python - <<'PY' > /tmp/reqs.txt
import tomllib; d = tomllib.load(open("pyproject.toml", "rb"))
print("\n".join(d["project"]["dependencies"] + d["project"]["optional-dependencies"]["dev"]))
PY
RUN pip install -r /tmp/reqs.txt
COPY backend/ ./
COPY config/ /app/config/
COPY --from=frontend /build/dist /app/frontend_dist
RUN useradd --create-home --uid 10001 devpulse && chown -R devpulse /app
USER devpulse
EXPOSE 8000
CMD ["uvicorn", "devpulse.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
