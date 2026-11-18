# REGISTRY can point to a Docker Hub mirror, e.g. --build-arg REGISTRY=mirror.gcr.io/library
ARG REGISTRY=docker.io/library
# ---- build the web UI ----
FROM ${REGISTRY}/node:22.11.0-bookworm-slim AS web
WORKDIR /src
COPY shared/ shared/
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend/ frontend/
RUN cd frontend && npm run build

# ---- runtime ----
FROM ${REGISTRY}/python:3.12.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FBO_DATA_DIR=/data FBO_HOST=0.0.0.0 FBO_PORT=8765 FBO_MODE=network
RUN useradd --create-home --uid 10001 fbosint && mkdir /data && chown fbosint /data
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]>=3.1"
COPY backend/fbosint fbosint
COPY --from=web /src/frontend/dist fbosint/static
USER fbosint
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/health')"
ENTRYPOINT ["python", "-m", "fbosint.cli"]
CMD ["serve"]
