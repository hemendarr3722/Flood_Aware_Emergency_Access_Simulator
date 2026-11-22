"""
api/index.py
Vercel serverless function entrypoint for FastAPI backend.
"""
import sys
from pathlib import Path

# Add project root to sys.path so 'backend' package resolves
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app
