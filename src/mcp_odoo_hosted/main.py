"""Entry point — run with: uvicorn mcp_odoo_hosted.main:app --host 0.0.0.0 --port 8000"""
import logging
import uvicorn

from .config import settings
from .server import app  # noqa: F401 — exported for uvicorn

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

if __name__ == "__main__":
    uvicorn.run(
        "mcp_odoo_hosted.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
