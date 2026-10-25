from __future__ import annotations

import re

from functions.database import database as db


CONFIG_KEY = "auto_setup_config"
DEFAULT_SEPARATOR = "╺╸"

CHANNEL_EMOJIS = {
    "canal_de_evento_de_compras": "🛒",
    "canal_de_boas_vindas": "👋",
    "canal_de_logs_do_sistema": "📋",
    "canal_de_logs_de_keys": "🔑",
    "canal_de_logs_de_conversor": "📝",
    "canal_de_logs_de_entradas": "📥",
    "canal_de_logs_de_saidas": "📤",
    "canal_de_logs_de_mensagens": "💬",
    "canal_de_logs_de_trafego_em_call": "🔊",
    "canal_de_logs_de_pedidos": "🧾",
    "canal_de_logs_de_robux": "💎",
    "canal_de_logs_de_middleman": "💎",
    "canal_de_logs_de_fivem": "🎮",
    "canal_de_logs_de_bate_ponto": "⏱️",
    "canal_de_logs_de_parcerias": "🤝",
    "canal_de_logs_de_instagram": "📸",
    "canal_de_logs_de_comunidade": "🏠",
    "canal_de_logs_de_restock": "📦",
    "canal_de_logs_de_antifraude": "🛡️",
    "canal_de_logs_de_protecao": "🛡️",
    "canal_de_logs_de_apostado": "🎮",
    "canal_de_logs_de_filas_apostas": "🎯",
    "canal_de_logs_de_sorteios": "🎉",
    "canal_de_feedback": "⭐",
    "canal_de_logs_de_tickets": "🎫",
    "canal_de_logs_de_comandos": "⌨️",
    "canal_de_logs_de_anti_falso": "🛡️",
    "canal_de_logs_de_banimentos": "🔨",
    "canal_de_logs_de_expulsoes": "🚪",
    "canal_de_logs_de_castigos": "⛔",
    "canal_de_logs_de_cargos_adicionados": "➕",
    "canal_de_logs_de_cargos_removidos": "➖",
    "canal_de_logs_de_cargos_criados": "🧩",
    "canal_de_logs_de_cargos_excluidos": "🗑️",
    "canal_de_logs_de_cargos_editados": "✏️",
    "canal_de_logs_de_canais_criados": "📁",
    "canal_de_logs_de_canais_excluidos": "🗑️",
    "canal_de_logs_de_canais_editados": "✏️",
    "canal_de_logs_de_permissoes_adicionadas": "🔐",
    "canal_de_logs_de_permissoes_removidas": "🔓",
}


def default_config() -> dict:
    return {
        "separator": DEFAULT_SEPARATOR,
        "channel_pattern": "{emoji}{separator}{name}",
        "role_pattern": "{name}",
        "logs_category": "╺╸ Logs",
        "community_category": "╺╸ Comunidade",
        "private_logs": True,
        "send_created_message": True,
        "channel_names": {},
        "role_names": {},
    }


def get_config() -> dict:
    data = db.get_document(CONFIG_KEY) or {}
    if not isinstance(data, dict):
        data = {}

    changed = False
    defaults = default_config()
    for key, value in defaults.items():
        if key not in data:
            data[key] = value.copy() if isinstance(value, dict) else value
            changed = True

    if not isinstance(data.get("channel_names"), dict):
        data["channel_names"] = {}
        changed = True
    if not isinstance(data.get("role_names"), dict):
        data["role_names"] = {}
        changed = True

    if changed:
        save_config(data)
    return data


def save_config(data: dict) -> None:
    db.save_document(CONFIG_KEY, data)


def slugify(value: str) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.replace("/", "-").replace("\\", "-")
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"[-_]+", "-", raw)
    raw = raw.strip("-")
    return raw or "canal"


def _format(pattern: str, *, name: str, emoji: str = "", separator: str = "") -> str:
    value = str(pattern or "{name}")
    return (
        value.replace("{emoji}", emoji)
        .replace("{separator}", separator)
        .replace("{sep}", separator)
        .replace("{name}", name)
        .replace("{nome}", name)
    ).strip()


def channel_name(key: str, label: str, config: dict | None = None, emoji_icon: str | None = None) -> str:
    config = config or get_config()
    custom = str(config.get("channel_names", {}).get(key) or "").strip()
    base = slugify(custom or label)
    icon = str(emoji_icon or CHANNEL_EMOJIS.get(key) or "📌")
    name = _format(
        str(config.get("channel_pattern") or "{emoji}{separator}{name}"),
        name=base,
        emoji=icon,
        separator=str(config.get("separator") or DEFAULT_SEPARATOR),
    )
    return name[:100]


def role_name(key: str, label: str, config: dict | None = None) -> str:
    config = config or get_config()
    custom = str(config.get("role_names", {}).get(key) or "").strip()
    base = custom or label
    name = _format(
        str(config.get("role_pattern") or "{name}"),
        name=base,
        separator=str(config.get("separator") or DEFAULT_SEPARATOR),
    )
    return name[:100]


def is_logs_key(key: str) -> bool:
    return "logs" in str(key or "")
