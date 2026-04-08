"""Entry point — run with: uvicorn mcp_odoo_hosted.main:app --host 0.0.0.0 --port 8000"""
import logging
import os
import uvicorn

from .config import settings
from .server import app  # noqa: F401 — exported for uvicorn

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)

# Warn if OAuth credentials were auto-generated (not set via env vars)
if not os.environ.get("OAUTH_CLIENT_SECRET"):
    logger.warning(
        "OAUTH_CLIENT_SECRET is not set — a random secret was generated for this session: %s\n"
        "Set OAUTH_CLIENT_SECRET=<value> as an environment variable to make it persistent.",
        settings.oauth_client_secret,
    )

if not os.environ.get("OAUTH_CLIENT_ID"):
    logger.warning(
        "OAUTH_CLIENT_ID is not set — using default value: %s",
        settings.oauth_client_id,
    )

logger.info("MCP server ready — endpoint: %s/mcp", settings.server_url)

if __name__ == "__main__":
    uvicorn.run(
        "mcp_odoo_hosted.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
