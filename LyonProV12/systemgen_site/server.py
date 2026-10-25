from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import unquote

from aiohttp import web

import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from functions.systemgen_manager import LyonGenManager


SITE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "database" / "emojis" / "assets"
manager = LyonGenManager()
CATEGORIES = {"streaming", "gaming", "outros"}
ALLOWED_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico"}


def _json_error(status: int, message: str) -> web.HTTPException:
    payload = json.dumps({"ok": False, "message": message}, ensure_ascii=False)
    if status == 404:
        return web.HTTPNotFound(text=payload, content_type="application/json")
    if status == 403:
        return web.HTTPForbidden(text=payload, content_type="application/json")
    return web.HTTPBadRequest(text=payload, content_type="application/json")


def _has_hidden_segment(value: object) -> bool:
    text = unquote(str(value or "")).replace("\\", "/").strip()
    return any(segment.startswith(".") for segment in text.split("/") if segment)


def _assert_safe_public_value(field: str, value: object, *, max_length: int = 120) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise _json_error(400, f"{field} required")
    if len(clean) > max_length:
        raise _json_error(400, f"{field} muito longo.")
    if _has_hidden_segment(clean):
        raise _json_error(400, f"{field} nao pode comecar com ponto ou conter caminhos ocultos.")
    return clean


def _assert_safe_payload_keys(value: object, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _has_hidden_segment(key):
                raise _json_error(400, f"Campo bloqueado por seguranca: {path}.{key}")
            _assert_safe_payload_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_safe_payload_keys(item, f"{path}[{index}]")


def _safe_stock_items(raw_items: object) -> list[str]:
    if isinstance(raw_items, str):
        items = raw_items.splitlines()
    elif isinstance(raw_items, (list, tuple, set)):
        items = list(raw_items)
    else:
        items = [raw_items] if raw_items else []

    blocked = []
    safe_items = []
    for item in items:
        clean = str(item or "").strip()
        if not clean:
            continue
        if _has_hidden_segment(clean):
            blocked.append(clean)
            continue
        safe_items.append(clean)

    if blocked:
        raise _json_error(400, "Itens que comecam com ponto ou apontam para arquivos ocultos foram bloqueados.")
    return safe_items


@web.middleware
async def security_middleware(request: web.Request, handler):
    raw_path = request.raw_path.split("?", 1)[0]
    if _has_hidden_segment(raw_path) or _has_hidden_segment(request.rel_url.path):
        raise web.HTTPNotFound(text="not found")

    response = await handler(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def _category(value: str | None) -> str:
    clean = str(value or "streaming").strip().lower()
    return clean if clean in CATEGORIES else "outros"


async def _payload(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "message": "JSON invalido."}),
            content_type="application/json",
        )
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "message": "Payload precisa ser um objeto JSON."}),
            content_type="application/json",
        )
    _assert_safe_payload_keys(data)
    return data


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(SITE_DIR / "index.html")


async def asset(request: web.Request) -> web.FileResponse:
    name = request.match_info.get("name", "")
    safe_name = Path(name).name
    if not safe_name or _has_hidden_segment(safe_name):
        raise web.HTTPNotFound(text="asset not found")
    if Path(safe_name).suffix.lower() not in ALLOWED_ASSET_SUFFIXES:
        raise web.HTTPNotFound(text="asset not found")

    assets_root = ASSETS_DIR.resolve()
    path = (ASSETS_DIR / safe_name).resolve()
    try:
        path.relative_to(assets_root)
    except ValueError:
        raise web.HTTPNotFound(text="asset not found")
    if not path.is_file():
        raise web.HTTPNotFound(text="asset not found")
    return web.FileResponse(path)


async def state(_request: web.Request) -> web.Response:
    return web.json_response(manager.public_state())


async def toggle(request: web.Request) -> web.Response:
    payload = await _payload(request)
    if "enabled" not in payload:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "message": "enabled required"}),
            content_type="application/json",
        )
    data = manager.set_enabled(bool(payload.get("enabled")))
    return web.json_response({"ok": True, "enabled": data.get("enabled", True)})


async def update_settings(request: web.Request) -> web.Response:
    payload = await _payload(request)
    site_url = payload.get("site_url") if "site_url" in payload else None
    if site_url is not None and _has_hidden_segment(site_url):
        raise _json_error(400, "site_url bloqueado por seguranca.")
    data = manager.update_settings(
        max_generate=payload.get("max_generate") if "max_generate" in payload else None,
        command_enabled=payload.get("command_enabled") if "command_enabled" in payload else None,
        site_url=site_url,
    )
    return web.json_response({"ok": True, "settings": data.get("settings", {})})


async def create_project(request: web.Request) -> web.Response:
    payload = await _payload(request)
    name = _assert_safe_public_value("name", payload.get("name"))
    return web.json_response({"ok": True, "project": manager.create_project(name)})


async def select_project(request: web.Request) -> web.Response:
    payload = await _payload(request)
    key = _assert_safe_public_value("key", payload.get("key"), max_length=80)
    ok = manager.select_project(key)
    if not ok:
        raise web.HTTPNotFound(
            text=json.dumps({"ok": False, "message": "project not found"}),
            content_type="application/json",
        )
    return web.json_response({"ok": ok})


async def create_service(request: web.Request) -> web.Response:
    payload = await _payload(request)
    name = _assert_safe_public_value("name", payload.get("name"))
    category = _category(payload.get("category"))
    return web.json_response({"ok": True, "service": manager.upsert_service(name, category)})


async def delete_service(request: web.Request) -> web.Response:
    payload = await _payload(request)
    service = _assert_safe_public_value("service", payload.get("service"))
    ok, message = manager.delete_service(service)
    if not ok:
        raise web.HTTPNotFound(
            text=json.dumps({"ok": False, "message": message}),
            content_type="application/json",
        )
    return web.json_response({"ok": ok, "message": message})


async def add_stock(request: web.Request) -> web.Response:
    payload = await _payload(request)
    service = _assert_safe_public_value("service", payload.get("service"))
    category = _category(payload.get("category"))
    items = _safe_stock_items(payload.get("items") or "")
    if not items:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "message": "items required"}),
            content_type="application/json",
        )
    return web.json_response({"ok": True, **manager.add_stock(service, category, items)})


async def generate(request: web.Request) -> web.Response:
    payload = await _payload(request)
    service = _assert_safe_public_value("service", payload.get("service"))
    category = _category(payload.get("category")) if payload.get("category") else None
    quantity = payload.get("quantity", 1)
    result = manager.generate(service, category, quantity, source="site")
    return web.json_response(result)


async def redeem(request: web.Request) -> web.Response:
    payload = await _payload(request)
    code = _assert_safe_public_value("code", payload.get("code"), max_length=80)
    username = _assert_safe_public_value("username", payload.get("username") or "Site Local", max_length=80)
    user_id = str(payload.get("user_id") or "").strip()
    if user_id and _has_hidden_segment(user_id):
        raise _json_error(400, "user_id bloqueado por seguranca.")
    ok, message = manager.redeem_code(code, username=username, user_id=user_id)
    return web.json_response({"ok": ok, "message": message})


def create_app() -> web.Application:
    app = web.Application(middlewares=[security_middleware], client_max_size=512 * 1024)
    app.router.add_get("/", index)
    app.router.add_get("/assets/{name}", asset)
    app.router.add_get("/api/state", state)
    app.router.add_post("/api/toggle", toggle)
    app.router.add_post("/api/settings", update_settings)
    app.router.add_post("/api/projects", create_project)
    app.router.add_post("/api/projects/select", select_project)
    app.router.add_post("/api/services", create_service)
    app.router.add_delete("/api/services", delete_service)
    app.router.add_post("/api/stock", add_stock)
    app.router.add_post("/api/generate", generate)
    app.router.add_post("/api/redeem", redeem)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Lyon Gen local site")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    data = manager.load()
    settings = data.setdefault("settings", {})
    settings["site_url"] = f"http://{args.host}:{args.port}"
    settings["site_host"] = args.host
    settings["site_port"] = args.port
    manager.save(data)
    print(f"Lyon Gen site running at http://{args.host}:{args.port}")
    web.run_app(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
