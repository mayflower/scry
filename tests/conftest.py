import os
import sys
from pathlib import Path


def pytest_sessionstart(_session):
    # Ensure src/ is importable when running pytest without installation
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    os.environ.setdefault("HEADLESS", "true")
    # Default to native playwright exploration
    os.environ.setdefault("NAV_BACKEND", "playwright")
