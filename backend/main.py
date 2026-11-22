"""
backend/main.py
Entry point for Vercel FastAPI service.
"""
import sys
import types
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent

# Ensure 'backend' module is always resolvable:
# If 'backend' is not already in sys.modules, create a package shim whose __path__ points to CURRENT_DIR.
if "backend" not in sys.modules:
    backend_pkg = types.ModuleType("backend")
    backend_pkg.__path__ = [str(CURRENT_DIR)]
    sys.modules["backend"] = backend_pkg

# Also add CURRENT_DIR and CURRENT_DIR.parent to sys.path
for p in [str(CURRENT_DIR), str(CURRENT_DIR.parent)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app.main import app

# For direct invocation or ASGI servers
__all__ = ["app"]
