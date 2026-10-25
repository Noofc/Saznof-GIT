from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ASSETS_DIR = PROJECT_ROOT / "assets" / "generated"
RECEIPTS_ASSETS_DIR = PROJECT_ROOT / "assets" / "receipts"

for path in (PROJECT_ROOT, GENERATED_ASSETS_DIR, RECEIPTS_ASSETS_DIR):
    path.mkdir(parents=True, exist_ok=True)

project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
