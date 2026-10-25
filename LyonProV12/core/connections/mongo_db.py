import copy
import base64
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace


BASE_DIR = Path(__file__).resolve().parents[2]


def _candidate_data_dirs() -> list[Path]:
    raw_values = [
        os.getenv("SYSTEMPRO_DATA_DIR"),
        os.getenv("SYSTEM_DATA_DIR"),
        os.getenv("PERSISTENT_DATA_DIR"),
        os.getenv("DATA_DIR"),
        os.getenv("CAMPOSCLOUD_DATA_DIR"),
    ]
    candidates = [Path(value).expanduser() for value in raw_values if str(value or "").strip()]
    candidates.extend([
        Path("/data/systempro"),
        Path("/app/data/systempro"),
        BASE_DIR.parent / "data" / "systempro",
        BASE_DIR / "database",
    ])
    return candidates


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _resolve_sql_dir() -> Path:
    for candidate in _candidate_data_dirs():
        if _is_writable_dir(candidate):
            return candidate
    fallback = BASE_DIR / "database"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


SQL_DIR = _resolve_sql_dir()
SQL_FILE = SQL_DIR / "system_data.sqlite3"
LEGACY_SQL_FILE = BASE_DIR / "database" / "system_data.sqlite3"
LEGACY_FALLBACK_FILE = BASE_DIR / "database" / "mongo_fallback.json"


def _migrate_legacy_sql_once() -> None:
    try:
        if SQL_FILE.resolve() == LEGACY_SQL_FILE.resolve():
            return
        if SQL_FILE.exists() or not LEGACY_SQL_FILE.exists():
            return
        SQL_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_SQL_FILE, SQL_FILE)
        print(f"[SQL] Banco antigo migrado para pasta persistente: {SQL_FILE}")
    except Exception as exc:
        print(f"[SQL] Nao foi possivel migrar banco antigo para pasta persistente: {exc}")


_migrate_legacy_sql_once()


class AwaitableValue:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        async def _coro():
            return self.value

        return _coro().__await__()

    def __bool__(self):
        return bool(self.value)

    def __iter__(self):
        if self.value is None:
            return iter(())
        return iter(self.value)

    def __getitem__(self, key):
        return self.value[key]

    def __contains__(self, key):
        return key in self.value

    def __len__(self):
        return len(self.value) if self.value is not None else 0

    def get(self, *args, **kwargs):
        return self.value.get(*args, **kwargs)

    def copy(self):
        return self.value.copy()

    def pop(self, *args, **kwargs):
        return self.value.pop(*args, **kwargs)

    def keys(self):
        return self.value.keys()

    def items(self):
        return self.value.items()

    def values(self):
        return self.value.values()

    def __repr__(self):
        return repr(self.value)


class SQLCollection:
    def __init__(self, db_path: Path, collection_name: str):
        self.db_path = db_path
        self.collection_name = str(collection_name or "systempro_default")
        self.lock = threading.RLock()
        self._ensure_schema()
        self._migrate_legacy_json_once()

    def _connect(self):
        SQL_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    collection TEXT NOT NULL,
                    id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (collection, id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_collection ON documents(collection)")

    def _migrate_legacy_json_once(self):
        if not LEGACY_FALLBACK_FILE.exists():
            return
        marker = SQL_DIR / ".legacy_mongo_fallback_imported"
        if marker.exists():
            return
        try:
            with LEGACY_FALLBACK_FILE.open("r", encoding="utf-8") as file:
                legacy = json.load(file)
            if isinstance(legacy, dict) and legacy:
                with self.lock, self._connect() as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM documents WHERE collection = ?",
                        (self.collection_name,),
                    ).fetchone()[0]
                    if count == 0:
                        now = int(time.time())
                        for doc_id, document in legacy.items():
                            if not isinstance(document, dict):
                                continue
                            doc = copy.deepcopy(document)
                            doc.setdefault("_id", str(doc_id))
                            conn.execute(
                                "INSERT OR REPLACE INTO documents(collection, id, data, updated_at) VALUES (?, ?, ?, ?)",
                                (self.collection_name, str(doc.get("_id")), json.dumps(doc, ensure_ascii=False), now),
                            )
            marker.write_text(str(int(time.time())), encoding="utf-8")
        except Exception as exc:
            print(f"[SQL] Nao foi possivel migrar fallback JSON legado: {exc}")

    def _doc_key(self, doc_id) -> str:
        return str(doc_id)

    def _load(self) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, data FROM documents WHERE collection = ?",
                (self.collection_name,),
            ).fetchall()
        result = {}
        for row in rows:
            try:
                result[str(row["id"])] = json.loads(row["data"])
            except Exception:
                continue
        return result

    def _save(self, data: dict):
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("DELETE FROM documents WHERE collection = ?", (self.collection_name,))
            for key, doc in (data or {}).items():
                if not isinstance(doc, dict):
                    continue
                doc_copy = copy.deepcopy(doc)
                doc_copy.setdefault("_id", str(key))
                conn.execute(
                    "INSERT OR REPLACE INTO documents(collection, id, data, updated_at) VALUES (?, ?, ?, ?)",
                    (self.collection_name, str(doc_copy.get("_id")), json.dumps(doc_copy, ensure_ascii=False), now),
                )

    def _get_path(self, data, path: str):
        current = data
        for part in str(path).split("."):
            if isinstance(current, dict):
                if part not in current:
                    return None
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    return None
                current = current[index]
            else:
                return None
        return current

    def _ensure_parent(self, data, path: str):
        parts = str(path).split(".")
        current = data
        for index, part in enumerate(parts[:-1]):
            next_part = parts[index + 1]
            next_container = [] if next_part.isdigit() else {}

            if isinstance(current, dict):
                if part not in current or not isinstance(current[part], (dict, list)):
                    current[part] = copy.deepcopy(next_container)
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                list_index = int(part)
                while len(current) <= list_index:
                    current.append(copy.deepcopy(next_container))
                if not isinstance(current[list_index], (dict, list)):
                    current[list_index] = copy.deepcopy(next_container)
                current = current[list_index]
            else:
                raise TypeError(f"Caminho invalido para update: {path}")

        return current, parts[-1]

    def _set_path(self, data, path: str, value):
        parent, last = self._ensure_parent(data, path)
        if isinstance(parent, list) and last.isdigit():
            index = int(last)
            while len(parent) <= index:
                parent.append(None)
            parent[index] = value
        elif isinstance(parent, dict):
            parent[last] = value

    def _inc_path(self, data, path: str, amount):
        current = self._get_path(data, path)
        if not isinstance(current, (int, float)):
            current = 0
        self._set_path(data, path, current + amount)

    def _push_path(self, data, path: str, value):
        current = self._get_path(data, path)
        if not isinstance(current, list):
            current = []
        if isinstance(value, dict) and "$each" in value:
            current.extend(value.get("$each") or [])
        else:
            current.append(value)
        self._set_path(data, path, current)

    def _add_to_set_path(self, data, path: str, value):
        current = self._get_path(data, path)
        if not isinstance(current, list):
            current = []
        values = value.get("$each", []) if isinstance(value, dict) and "$each" in value else [value]
        for item in values:
            if item not in current:
                current.append(item)
        self._set_path(data, path, current)

    def _unset_path(self, data, path: str):
        parent, last = self._ensure_parent(data, path)
        if isinstance(parent, dict):
            parent.pop(last, None)
        elif isinstance(parent, list) and last.isdigit():
            index = int(last)
            if index < len(parent):
                parent[index] = None

    def _matches(self, doc: dict, query: dict | None) -> bool:
        if not query:
            return True
        for key, expected in query.items():
            if key == "$or" and isinstance(expected, list):
                if not any(self._matches(doc, item) for item in expected):
                    return False
                continue
            if key == "$and" and isinstance(expected, list):
                if not all(self._matches(doc, item) for item in expected):
                    return False
                continue
            actual = doc.get("_id") if key == "_id" else self._get_path(doc, key)
            if isinstance(expected, dict):
                if "$exists" in expected:
                    exists = actual is not None
                    if bool(expected["$exists"]) != exists:
                        return False
                if "$in" in expected:
                    if str(actual) not in [str(x) for x in expected.get("$in", [])]:
                        return False
                if "$nin" in expected:
                    if str(actual) in [str(x) for x in expected.get("$nin", [])]:
                        return False
                if "$ne" in expected:
                    if str(actual) == str(expected.get("$ne")):
                        return False
                if "$gte" in expected and actual < expected.get("$gte"):
                    return False
                if "$lte" in expected and actual > expected.get("$lte"):
                    return False
            elif str(actual) != str(expected):
                return False
        return True

    def _apply_update(self, doc: dict, update: dict):
        if not isinstance(update, dict):
            return
        if not any(str(key).startswith("$") for key in update):
            doc.clear()
            doc.update(copy.deepcopy(update))
            return

        for path, value in update.get("$set", {}).items():
            self._set_path(doc, path, copy.deepcopy(value))
        for path, value in update.get("$inc", {}).items():
            self._inc_path(doc, path, value)
        for path, value in update.get("$push", {}).items():
            self._push_path(doc, path, copy.deepcopy(value))
        for path, value in update.get("$addToSet", {}).items():
            self._add_to_set_path(doc, path, copy.deepcopy(value))
        for path in update.get("$unset", {}).keys():
            self._unset_path(doc, path)

    def find_one(self, query: dict | None = None, projection: dict | None = None):
        with self.lock:
            data = self._load()
            for doc in data.values():
                if self._matches(doc, query):
                    return AwaitableValue(copy.deepcopy(doc))
        return AwaitableValue(None)

    def find(self, query: dict | None = None, projection: dict | None = None):
        with self.lock:
            data = self._load()
            return [copy.deepcopy(doc) for doc in data.values() if self._matches(doc, query)]

    def replace_one(self, query: dict, document: dict, upsert: bool = False):
        with self.lock:
            data = self._load()
            target_key = None
            for key, doc in data.items():
                if self._matches(doc, query):
                    target_key = key
                    break
            if target_key is None:
                if not upsert:
                    return AwaitableValue(SimpleNamespace(acknowledged=True, matched_count=0, modified_count=0))
                target_key = self._doc_key(query.get("_id") or document.get("_id") or int(time.time() * 1000))

            doc_copy = copy.deepcopy(document)
            doc_copy.setdefault("_id", query.get("_id", doc_copy.get("_id", target_key)))
            data[str(doc_copy.get("_id"))] = doc_copy
            if str(target_key) != str(doc_copy.get("_id")):
                data.pop(str(target_key), None)
            self._save(data)
            return AwaitableValue(SimpleNamespace(acknowledged=True, matched_count=1, modified_count=1))

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        with self.lock:
            data = self._load()
            target_key = None
            for key, doc in data.items():
                if self._matches(doc, query):
                    target_key = key
                    break

            if target_key is None:
                if not upsert:
                    return AwaitableValue(SimpleNamespace(acknowledged=True, matched_count=0, modified_count=0))
                target_key = self._doc_key(query.get("_id") or int(time.time() * 1000))
                data[target_key] = {"_id": query.get("_id", target_key)}

            self._apply_update(data[target_key], update)
            self._save(data)
            return AwaitableValue(SimpleNamespace(acknowledged=True, matched_count=1, modified_count=1))

    def insert_one(self, document: dict):
        with self.lock:
            data = self._load()
            doc_copy = copy.deepcopy(document)
            key = self._doc_key(doc_copy.get("_id") or int(time.time() * 1000))
            doc_copy.setdefault("_id", key)
            data[key] = doc_copy
            self._save(data)
            return AwaitableValue(SimpleNamespace(acknowledged=True, inserted_id=doc_copy.get("_id")))

    def delete_one(self, query: dict):
        with self.lock:
            data = self._load()
            deleted = 0
            for key, doc in list(data.items()):
                if self._matches(doc, query):
                    data.pop(key, None)
                    deleted = 1
                    break
            if deleted:
                self._save(data)
            return AwaitableValue(SimpleNamespace(acknowledged=True, deleted_count=deleted))

    def delete_many(self, query: dict):
        with self.lock:
            data = self._load()
            deleted = 0
            for key, doc in list(data.items()):
                if self._matches(doc, query):
                    data.pop(key, None)
                    deleted += 1
            if deleted:
                self._save(data)
            return AwaitableValue(SimpleNamespace(acknowledged=True, deleted_count=deleted))


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def _first_value(*values) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _bot_id_from_token(token: str) -> str:
    token = str(token or "").strip()
    if "." not in token:
        return ""

    first_part = token.split(".", 1)[0]
    try:
        padding = "=" * ((4 - len(first_part) % 4) % 4)
        decoded = base64.urlsafe_b64decode((first_part + padding).encode()).decode()
        return decoded if decoded.isdigit() else ""
    except Exception:
        return ""


def _safe_collection_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or "").strip())
    name = name.replace("$", "_").replace("\x00", "_").strip(" .")
    if not name or name.lower().startswith("system."):
        return "systempro_default"
    return name[:120]


def _resolve_bot_id(config_data: dict) -> str:
    bot_data = config_data.get("bot") if isinstance(config_data.get("bot"), dict) else {}
    token = _first_value(
        os.getenv("BOT_TOKEN"),
        os.getenv("TOKEN"),
        os.getenv("DISCORD_TOKEN"),
        bot_data.get("token"),
        config_data.get("botToken"),
    )

    resolved = _first_value(
        os.getenv("BOT_ID"),
        os.getenv("CLIENT_ID"),
        os.getenv("APPLICATION_CLIENT_ID"),
        os.getenv("APPLICATION_ID"),
        bot_data.get("id"),
        config_data.get("botID"),
        _bot_id_from_token(token),
        os.getenv("CAMPOSCLOUD_APP_ID"),
        "systempro_default",
    )
    return _safe_collection_name(resolved)


config = _load_json("config.json")
bot_id = _resolve_bot_id(config)
collection = SQLCollection(SQL_FILE, bot_id)
database = collection
client = None

print(f"[SQL] Banco SQLite ativo em {SQL_FILE} | colecao {bot_id}.")
