"""Conexão MongoDB do bot.

O bot usa uma única collection fixa para todos os documentos de configuração.
Cada configuração lógica é um documento cujo `_id` é o nome da configuração,
por exemplo `custom_mode`, `loja_products` ou `canais`.

A URI nunca fica gravada no código. Ela deve ser fornecida por `MONGO_URL`
ou por `configs/config_mongo.json`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "configs" / "config_mongo.json"


def _read_config() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(f"[MongoDB] Configuração não carregada: {exc}")
        return {}


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _resolve_settings() -> tuple[str, str, str]:
    config = _read_config()
    mongo_config = config.get("mongo", config)
    if not isinstance(mongo_config, dict):
        mongo_config = {}

    mongo_url = _first_env("MONGO_URL", "MONGODB_URI", "MONGO_URI") or str(
        mongo_config.get("mongoURL") or mongo_config.get("uri") or ""
    ).strip()
    database_name = _first_env("MONGO_DATABASE", "MONGODB_DATABASE") or str(
        mongo_config.get("databaseName") or "lyonnew"
    ).strip()
    collection_name = _first_env("MONGO_COLLECTION", "MONGODB_COLLECTION") or str(
        mongo_config.get("collectionName") or "documents"
    ).strip()

    if not mongo_url:
        raise RuntimeError(
            "MONGO_URL não configurada. Defina MONGO_URL no ambiente ou em configs/config_mongo.json."
        )
    if not database_name:
        raise RuntimeError("MONGO_DATABASE não configurada.")
    if not collection_name:
        raise RuntimeError("MONGO_COLLECTION não configurada.")

    return mongo_url, database_name, collection_name


MONGO_URL, DATABASE_NAME, COLLECTION_NAME = _resolve_settings()

# MongoClient é thread-safe e mantém o pool de conexões internamente.
client: MongoClient = MongoClient(
    MONGO_URL,
    serverSelectionTimeoutMS=int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000")),
    connectTimeoutMS=int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "5000")),
    socketTimeoutMS=int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "10000")),
    retryWrites=True,
)

# Falha cedo com uma mensagem clara se a URI ou a rede estiverem incorretas.
client.admin.command("ping")
database: Database = client[DATABASE_NAME]
collection: Collection = database[COLLECTION_NAME]

# Compatibilidade com código que importa `bot_collection` ou usa `database`.
bot_collection = collection

print(
    f"[MongoDB] Conectado: database={DATABASE_NAME!r}, "
    f"collection={COLLECTION_NAME!r}"
)


__all__ = [
    "client",
    "database",
    "collection",
    "bot_collection",
    "MONGO_URL",
    "DATABASE_NAME",
    "COLLECTION_NAME",
]
