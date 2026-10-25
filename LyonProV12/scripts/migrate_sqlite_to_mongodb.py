"""Migra os documentos do SQLite legado para MongoDB.

Uso:
    MONGO_URL='mongodb+srv://...' \
    MONGO_DATABASE=lyonnew \
    MONGO_COLLECTION=documents \
    python scripts/migrate_sqlite_to_mongodb.py

O script não apaga o SQLite e usa replace/upsert por `_id`, podendo ser
executado novamente com segurança.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from pymongo import MongoClient


BASE_DIR = Path(__file__).resolve().parents[1]
SQLITE_PATH = Path(
    os.getenv("SQLITE_PATH", str(BASE_DIR / "database" / "system_data.sqlite3"))
)
MONGO_URL = os.getenv("MONGO_URL", "").strip()
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "lyonnew").strip()
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "documents").strip()

if not MONGO_URL:
    raise SystemExit("Defina MONGO_URL antes de executar a migração.")
if not SQLITE_PATH.exists():
    raise SystemExit(f"SQLite não encontrado: {SQLITE_PATH}")

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
client.admin.command("ping")
collection = client[MONGO_DATABASE][MONGO_COLLECTION]

with sqlite3.connect(str(SQLITE_PATH)) as connection:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT id, data FROM documents WHERE collection = ?",
        (os.getenv("SQLITE_COLLECTION", "systempro_default"),),
    ).fetchall()

migrated = 0
skipped = 0
for row in rows:
    try:
        document = json.loads(row["data"])
        if not isinstance(document, dict):
            skipped += 1
            continue
        document["_id"] = str(document.get("_id", row["id"]))
        collection.replace_one({"_id": document["_id"]}, document, upsert=True)
        migrated += 1
    except Exception as exc:
        skipped += 1
        print(f"[MIGRATION] Documento ignorado {row['id']}: {exc}")

print(
    f"[MIGRATION] Concluída: {migrated} documento(s) migrado(s), "
    f"{skipped} ignorado(s), database={MONGO_DATABASE!r}, "
    f"collection={MONGO_COLLECTION!r}"
)
client.close()
