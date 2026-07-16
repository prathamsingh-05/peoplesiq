# People IQ Recruiter Agent — single-image build.
# Stage 1 builds the React front-end; stage 2 runs the FastAPI backend, which
# serves both the API and the built SPA from one origin (private by default —
# access is gated by login).

# ---- Stage 1: build the front-end ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: backend runtime ----
FROM python:3.11-slim AS runtime
WORKDIR /app

# System deps kept minimal; no build toolchain needed for the wheels used.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PEOPLEIQ_DATA_DIR=/data

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Persist candidate data / uploads / db / secret across restarts.
VOLUME ["/data"]
EXPOSE 8000

# Run as a non-root user for safety.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data && chown -R appuser /data /app
USER appuser

WORKDIR /app/backend
# Respect $PORT when the host sets it (Render, Railway, Cloud Run, …); default 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
