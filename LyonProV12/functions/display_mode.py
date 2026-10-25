from __future__ import annotations

from functions.database import database as db
import time

_DISPLAY_CACHE = {}
_DISPLAY_CACHE_TTL = 3.0


def _cached_document(name: str) -> dict:
    now = time.monotonic()
    cached = _DISPLAY_CACHE.get(name)
    if cached and now - cached[0] < _DISPLAY_CACHE_TTL:
        return dict(cached[1])
    value = db.get_document(name) or {}
    value = dict(value) if isinstance(value, dict) else {}
    _DISPLAY_CACHE[name] = (now, value)
    return dict(value)


def clear_display_cache() -> None:
    _DISPLAY_CACHE.clear()


BOT_STYLE_LABELS = {
    "full_v2": "Full Components V2",
    "embed": "Embed",
    "hybrid": "Comp V2 + Embed",
}

PANEL_LAYOUT_LABELS = {
    "buttons": "Botoes",
    "select": "Select Menu",
    "both": "Botoes + Select Menu",
}


def normalize_bot_style(value: str | None, fallback_mode: str | None = None) -> str:
    style = str(value or "").lower().strip()
    mode = str(fallback_mode or "").lower().strip()
    aliases = {
        "components": "full_v2",
        "componentes": "full_v2",
        "components_v2": "full_v2",
        "componentes_v2": "full_v2",
        "container": "full_v2",
        "containers": "full_v2",
        "full_components": "full_v2",
        "full_components_v2": "full_v2",
        "full components v2": "full_v2",
        "full comp v2": "full_v2",
        "full_comp_v2": "full_v2",
        "full_v2": "full_v2",
        "embed": "embed",
        "embeds": "embed",
        "embed_v1": "embed",
        "hybrid": "hybrid",
        "hibrido": "hybrid",
        "comp v2 + embed": "hybrid",
        "compv2 + embed": "hybrid",
        "components v2 + embed": "hybrid",
        "embed + comp v2": "hybrid",
        "embed + components v2": "hybrid",
        "comp v2 embed": "hybrid",
        "compv2 embed": "hybrid",
        "comp_v2_embed": "hybrid",
        "compv2_embed": "hybrid",
        "components_embed": "hybrid",
        "embed_components": "hybrid",
        "embed_components_v2": "hybrid",
        "embed_comp_v2": "hybrid",
    }
    return aliases.get(style) or ("embed" if mode == "embed" else "full_v2")


def normalize_panel_layout(value: str | None) -> str:
    layout = str(value or "").lower().strip()
    aliases = {
        "button": "buttons",
        "buttons": "buttons",
        "botao": "buttons",
        "botoes": "buttons",
        "botões": "buttons",
        "select": "select",
        "select_menu": "select",
        "menu": "select",
        "both": "both",
        "ambos": "both",
        "complete": "both",
        "completo": "both",
    }
    return aliases.get(layout, "both")


def mode_from_style(style: str) -> str:
    return "embed" if style == "embed" else "components"


def get_bot_style() -> str:
    config = _cached_document("custom_mode")
    return normalize_bot_style(config.get("style"), config.get("mode"))


def get_bot_mode() -> str:
    return mode_from_style(get_bot_style())


def get_panel_layout() -> str:
    custom_mode = _cached_document("custom_mode")
    panel_mode = _cached_document("custom_panel_mode")
    return normalize_panel_layout(custom_mode.get("panel_layout") or panel_mode.get("mode"))


def get_display_config() -> dict:
    style = get_bot_style()
    return {
        "style": style,
        "mode": mode_from_style(style),
        "panel_layout": get_panel_layout(),
    }


def save_bot_style(style: str) -> dict:
    normalized = normalize_bot_style(style)
    config = _cached_document("custom_mode")
    config.update(
        {
            "style": normalized,
            "mode": mode_from_style(normalized),
            "panel_layout": get_panel_layout(),
        }
    )
    db.save_document("custom_mode", {}, config)
    clear_display_cache()
    return config


def save_panel_layout(layout: str) -> dict:
    normalized = normalize_panel_layout(layout)
    db.save_document("custom_panel_mode", {}, {"mode": normalized})

    config = _cached_document("custom_mode")
    style = normalize_bot_style(config.get("style"), config.get("mode"))
    config.update(
        {
            "style": style,
            "mode": mode_from_style(style),
            "panel_layout": normalized,
        }
    )
    db.save_document("custom_mode", {}, config)
    clear_display_cache()
    return config
