from __future__ import annotations

from typing import Any

import disnake

from functions.database import database as db


MAIN_CHANNELS_DOC = "canais"


def clean_channel_id(value: Any) -> str:
    raw = str(value or "").replace("<#", "").replace(">", "").strip()
    return raw if raw.isdigit() else ""


def guild_channels_doc_key(guild_or_id: disnake.Guild | int | str | None) -> str:
    guild_id = getattr(guild_or_id, "id", guild_or_id)
    return f"canais_{guild_id}" if guild_id else MAIN_CHANNELS_DOC


def _main_guild_id() -> str:
    config = db.obter("config.json") or {}
    bot_config = config.get("bot") if isinstance(config, dict) else {}
    return str((bot_config or {}).get("server") or "").strip()


def is_main_guild(guild_or_id: disnake.Guild | int | str | None) -> bool:
    guild_id = str(getattr(guild_or_id, "id", guild_or_id) or "").strip()
    main_id = _main_guild_id()
    return bool(guild_id and main_id and guild_id == main_id)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _channel_exists_in_guild(guild: disnake.Guild | None, channel_id: Any) -> bool:
    raw = clean_channel_id(channel_id)
    if not raw:
        return False
    if guild is None:
        return True
    return guild.get_channel(int(raw)) is not None


def load_guild_channels(
    guild: disnake.Guild | int | str | None,
    *,
    include_global_fallback: bool = True,
) -> dict:
    guild_id = getattr(guild, "id", guild)
    data: dict = {}

    if guild_id:
        data.update(_as_dict(db.get_document(guild_channels_doc_key(guild_id))))

    if include_global_fallback:
        global_data = _as_dict(db.get_document(MAIN_CHANNELS_DOC))
        for key, value in global_data.items():
            if key in data:
                continue
            if isinstance(guild, disnake.Guild) and not _channel_exists_in_guild(guild, value):
                continue
            data[key] = value

    return data


def save_guild_channels(
    guild: disnake.Guild | int | str | None,
    data: dict,
    *,
    update_legacy_main: bool = True,
) -> None:
    guild_id = getattr(guild, "id", guild)
    if guild_id:
        db.save_document(guild_channels_doc_key(guild_id), {}, _as_dict(data))
        if update_legacy_main and is_main_guild(guild_id):
            db.save_document(MAIN_CHANNELS_DOC, {}, _as_dict(data))
        return

    db.save_document(MAIN_CHANNELS_DOC, {}, _as_dict(data))


def get_guild_channel_id(
    guild: disnake.Guild | None,
    channel_key: str,
    *,
    include_global_fallback: bool = True,
) -> str:
    data = load_guild_channels(guild, include_global_fallback=include_global_fallback)
    return clean_channel_id(data.get(channel_key))


def set_guild_channel(
    guild: disnake.Guild | int | str | None,
    channel_key: str,
    channel_id: Any,
) -> dict:
    data = load_guild_channels(guild, include_global_fallback=True)
    data[channel_key] = clean_channel_id(channel_id) or None
    save_guild_channels(guild, data)
    return data
