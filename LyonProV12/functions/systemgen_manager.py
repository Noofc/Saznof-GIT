from __future__ import annotations

import copy
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "database" / "Lyongen.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, fallback: str = "service") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or fallback


def _merge_defaults(data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(defaults)
    for key, value in (data or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_defaults(value, result[key])
        else:
            result[key] = value
    return result


class LyonGenManager:
    def __init__(self, path: Path | str = DATA_PATH):
        self.path = Path(path)

    @staticmethod
    def defaults() -> dict[str, Any]:
        return {
            "enabled": True,
            "integrated_user": "Local",
            "integrated_user_id": None,
            "project_key": "local",
            "settings": {
                "site_url": "http://127.0.0.1:8765",
                "site_host": "127.0.0.1",
                "site_port": 8765,
                "site_autostart": True,
                "max_generate": 20,
                "command_enabled": False,
            },
            "projects": {
                "local": {
                    "key": "local",
                    "name": "Projeto Local",
                    "usage": 0,
                    "created_at": _now(),
                }
            },
            "services": {},
            "pending_codes": {},
            "history": [],
            "livestock": {
                "accepted_warning": True,
                "dm_notifications": False,
                "products": {},
            },
        }

    def load(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            data = self.defaults()
            self.save(data)
            return data

        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            data = {}

        normalized = _merge_defaults(data if isinstance(data, dict) else {}, self.defaults())
        if normalized != data:
            self.save(normalized)
        return normalized

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

    def summary(self) -> dict[str, Any]:
        data = self.load()
        services = data.get("services", {})
        stock_total = sum(len(service.get("stock", [])) for service in services.values())
        try:
            max_generate = int(data.get("settings", {}).get("max_generate", 20) or 20)
        except Exception:
            max_generate = 20
        return {
            "enabled": bool(data.get("enabled", True)),
            "integrated_user": data.get("integrated_user") or "Local",
            "project_key": data.get("project_key") or "local",
            "service_count": len(services),
            "stock_total": stock_total,
            "history_count": len(data.get("history", [])),
            "site_url": data.get("settings", {}).get("site_url", "http://127.0.0.1:8765"),
            "command_enabled": bool(data.get("settings", {}).get("command_enabled", False)),
            "max_generate": max_generate,
        }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        data = self.load()
        data["enabled"] = bool(enabled)
        self.save(data)
        return data

    def update_settings(
        self,
        *,
        site_url: str | None = None,
        max_generate: int | str | None = None,
        command_enabled: bool | None = None,
    ) -> dict[str, Any]:
        data = self.load()
        settings = data.setdefault("settings", {})

        if site_url is not None:
            clean_url = str(site_url or "").strip()
            if clean_url:
                settings["site_url"] = clean_url

        if max_generate is not None:
            try:
                settings["max_generate"] = max(1, min(100, int(max_generate)))
            except Exception:
                settings["max_generate"] = int(settings.get("max_generate", 20) or 20)

        if command_enabled is not None:
            settings["command_enabled"] = bool(command_enabled)

        self.save(data)
        return data

    def set_command_enabled(self, enabled: bool) -> dict[str, Any]:
        return self.update_settings(command_enabled=enabled)

    def create_code(self, *, bot_id: str | int | None = None, created_by: str | int | None = None) -> str:
        data = self.load()
        code = "SG-" + secrets.token_urlsafe(6).replace("-", "").replace("_", "").upper()[:8]
        data.setdefault("pending_codes", {})[code] = {
            "code": code,
            "bot_id": str(bot_id or ""),
            "created_by": str(created_by or ""),
            "redeemed": False,
            "created_at": _now(),
        }
        self.save(data)
        return code

    def redeem_code(self, code: str, *, username: str, user_id: str | int | None = None) -> tuple[bool, str]:
        data = self.load()
        clean_code = str(code or "").strip().upper()
        pending = data.setdefault("pending_codes", {}).get(clean_code)
        if not pending:
            return False, "Codigo nao encontrado."
        if pending.get("redeemed"):
            return False, "Codigo ja foi usado."

        pending["redeemed"] = True
        pending["redeemed_at"] = _now()
        pending["username"] = str(username or "Local")
        pending["user_id"] = str(user_id or "")
        data["integrated_user"] = pending["username"]
        data["integrated_user_id"] = pending["user_id"] or data.get("integrated_user_id")
        data["project_key"] = data.get("project_key") or "local"
        self.save(data)
        return True, "Pro vinculado com sucesso."

    def check_code(self, code: str) -> dict[str, Any] | None:
        data = self.load()
        return data.get("pending_codes", {}).get(str(code or "").strip().upper())

    def create_project(self, name: str) -> dict[str, Any]:
        data = self.load()
        key_base = _slug(name, "project")
        key = key_base
        counter = 2
        while key in data.setdefault("projects", {}):
            key = f"{key_base}-{counter}"
            counter += 1
        project = {"key": key, "name": str(name or "Projeto").strip(), "usage": 0, "created_at": _now()}
        data["projects"][key] = project
        data["project_key"] = data.get("project_key") or key
        self.save(data)
        return project

    def select_project(self, key: str) -> bool:
        data = self.load()
        clean_key = str(key or "").strip()
        if clean_key not in data.get("projects", {}):
            return False
        data["project_key"] = clean_key
        self.save(data)
        return True

    def get_service(self, service_name: str) -> dict[str, Any] | None:
        data = self.load()
        service_id = _slug(service_name, "service")
        service = data.get("services", {}).get(service_id)
        return copy.deepcopy(service) if service else None

    def list_services(self, *, include_empty: bool = True, category: str | None = None) -> list[dict[str, Any]]:
        data = self.load()
        clean_category = str(category or "").strip().lower()
        services = []
        for service in data.get("services", {}).values():
            if clean_category and service.get("category") != clean_category:
                continue
            stock_count = len(service.get("stock", []))
            if not include_empty and stock_count <= 0:
                continue
            item = copy.deepcopy(service)
            item["stock_count"] = stock_count
            services.append(item)
        return sorted(services, key=lambda item: (str(item.get("category") or ""), str(item.get("name") or "")))

    def upsert_service(self, name: str, category: str = "streaming") -> dict[str, Any]:
        data = self.load()
        service_id = _slug(name, "service")
        services = data.setdefault("services", {})
        service = services.get(service_id) or {
            "id": service_id,
            "name": str(name or service_id).strip(),
            "category": str(category or "streaming").strip().lower(),
            "stock": [],
            "total_generated": 0,
            "created_at": _now(),
        }
        service["name"] = str(name or service.get("name") or service_id).strip()
        service["category"] = str(category or service.get("category") or "streaming").strip().lower()
        service["updated_at"] = _now()
        services[service_id] = service
        self.save(data)
        return copy.deepcopy(service)

    def delete_service(self, service_name: str) -> tuple[bool, str]:
        data = self.load()
        service_id = _slug(service_name, "service")
        services = data.setdefault("services", {})
        if service_id not in services:
            return False, "Servico nao encontrado."
        del services[service_id]
        self.save(data)
        return True, "Servico apagado com sucesso."

    def add_stock(self, service_name: str, category: str, items: list[str]) -> dict[str, Any]:
        data = self.load()
        service_id = _slug(service_name, "service")
        services = data.setdefault("services", {})
        service = services.get(service_id)
        if not service:
            service = {
                "id": service_id,
                "name": str(service_name or service_id).strip(),
                "category": str(category or "streaming").strip().lower(),
                "stock": [],
                "total_generated": 0,
                "created_at": _now(),
            }

        clean_items = []
        seen = set(service.get("stock", []))
        for item in items or []:
            clean = str(item or "").strip()
            if not clean or clean in seen:
                continue
            clean_items.append(clean)
            seen.add(clean)

        service.setdefault("stock", []).extend(clean_items)
        service["category"] = str(category or service.get("category") or "streaming").strip().lower()
        service["updated_at"] = _now()
        services[service_id] = service
        self.save(data)
        return {"service": copy.deepcopy(service), "added": len(clean_items), "total": len(service.get("stock", []))}

    def return_stock(self, service_name: str, items: list[str]) -> dict[str, Any]:
        data = self.load()
        service_id = _slug(service_name, "service")
        service = data.get("services", {}).get(service_id)
        if not service:
            return {"ok": False, "reason": "Servico nao encontrado.", "returned": 0}

        clean_items = [str(item or "").strip() for item in (items or []) if str(item or "").strip()]
        if not clean_items:
            return {"ok": True, "returned": 0, "total": len(service.get("stock", []))}

        current_stock = service.setdefault("stock", [])
        service["stock"] = clean_items + current_stock
        service["total_generated"] = max(0, int(service.get("total_generated", 0) or 0) - len(clean_items))
        service["updated_at"] = _now()

        project_key = data.get("project_key") or "local"
        if project_key in data.get("projects", {}):
            usage = int(data["projects"][project_key].get("usage", 0) or 0)
            data["projects"][project_key]["usage"] = max(0, usage - len(clean_items))

        self.save(data)
        return {"ok": True, "returned": len(clean_items), "total": len(service.get("stock", []))}

    def generate(self, service_name: str, category: str | None = None, quantity: int = 1, *, user_id: str | int | None = None, source: str = "bot") -> dict[str, Any]:
        data = self.load()
        if not data.get("enabled", True):
            return {"ok": False, "reason": "Lyon Gen esta desativado.", "items": [], "available": 0}

        service_id = _slug(service_name, "service")
        service = data.get("services", {}).get(service_id)
        if not service:
            return {"ok": False, "reason": "Servico nao encontrado no estoque do Gen.", "items": [], "available": 0}

        try:
            limit = max(1, min(int(data.get("settings", {}).get("max_generate", 20)), int(quantity)))
        except Exception:
            limit = 1

        stock = service.setdefault("stock", [])
        available = len(stock)
        if available <= 0:
            return {"ok": False, "reason": "Sem estoque disponivel para esse servico.", "items": [], "available": 0}

        amount = min(limit, available)
        items = stock[:amount]
        service["stock"] = stock[amount:]
        service["total_generated"] = int(service.get("total_generated", 0) or 0) + amount
        service["updated_at"] = _now()

        project_key = data.get("project_key") or "local"
        if project_key in data.get("projects", {}):
            data["projects"][project_key]["usage"] = int(data["projects"][project_key].get("usage", 0) or 0) + amount

        data.setdefault("history", []).insert(
            0,
            {
                "service": service.get("name", service_id),
                "service_id": service_id,
                "category": category or service.get("category", "streaming"),
                "quantity": amount,
                "requested": limit,
                "source": source,
                "user_id": str(user_id or ""),
                "created_at": _now(),
            },
        )
        data["history"] = data["history"][:200]
        self.save(data)
        return {"ok": True, "items": items, "available": len(service.get("stock", [])), "service": copy.deepcopy(service)}

    def public_state(self) -> dict[str, Any]:
        data = self.load()
        services = []
        for service in self.list_services():
            services.append(
                {
                    "id": service.get("id"),
                    "name": service.get("name"),
                    "category": service.get("category"),
                    "stock": int(service.get("stock_count", len(service.get("stock", []))) or 0),
                    "total_generated": int(service.get("total_generated", 0) or 0),
                    "updated_at": service.get("updated_at"),
                }
            )
        return {
            "summary": self.summary(),
            "settings": data.get("settings", {}),
            "projects": list(data.get("projects", {}).values()),
            "services": sorted(services, key=lambda item: item.get("name") or ""),
            "pending_codes": [],
            "history": data.get("history", [])[:50],
            "livestock": data.get("livestock", {}),
        }
