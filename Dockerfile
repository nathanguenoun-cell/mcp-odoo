# ── Build stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

# ── Runtime stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src ./src

# Non-root user for security
RUN useradd -r -s /bin/false appuser
USER appuser

EXPOSE 8000

# Railway injects $PORT — fall back to 8000 for local Docker
CMD ["sh", "-c", "uvicorn mcp_odoo_hosted.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
