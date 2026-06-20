"""Smoke test for all new hardening modules."""
import sys
sys.path.insert(0, "/root/crisis-monitor/backend")

from src.middleware.logging import RequestLoggingMiddleware
from src.services.health import get_health
from src.services.auth import verify_crisis_token
from src.services.trigger_idempotency import find_recent_report
from src.routes import router
from src.main import app

print("All new modules import OK")
print(f"Routes: {len(router.routes)}")
print(f"Middleware count: {len(app.user_middleware)}")
print("Smoke test passed")
