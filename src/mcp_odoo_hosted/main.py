"""Entry point — run with: uvicorn mcp_odoo_hosted.main:app --host 0.0.0.0 --port 8000"""
import logging
import uvicorn

from .config import settings
from .server import app  # noqa: F401 — exported for uvicorn

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)

# Affiche toujours les valeurs effectives au démarrage pour faciliter le debug
logger.info("=== MCP Odoo Hosted — démarrage ===")
logger.info("MCP endpoint  : %s/mcp", settings.server_url)
logger.info("OAuth client_id     : %s", settings.oauth_client_id)
logger.info("OAuth client_secret : %s", settings.oauth_client_secret)
logger.info("JWT secret key      : %s", settings.jwt_secret_key[:8] + "…(masqué)")

if __name__ == "__main__":
    uvicorn.run(
        "mcp_odoo_hosted.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
