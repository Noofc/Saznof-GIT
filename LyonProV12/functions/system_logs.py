from __future__ import annotations

from datetime import datetime

import disnake

from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import clean_channel_id, load_guild_channels, set_guild_channel


LOG_FALLBACK_KEYS = (
    "canal_de_logs_do_sistema",
    "canal_de_logs_de_comandos",
    "canal_de_logs_de_canais_criados",
    "canal_de_logs_de_pedidos",
)


def _primary_colour() -> disnake.Colour:
    colors = db.get_document("custom_colors") or {}
    color_hex = colors.get("primary") if isinstance(colors, dict) else None
    if color_hex:
        try:
            return disnake.Colour(int(str(color_hex).replace("#", ""), 16))
        except Exception:
            pass
    return disnake.Colour.blurple()


def _iter_config_channel_ids(config: dict | None = None, *keys: str):
    config = config if isinstance(config, dict) else {}
    for key in keys:
        raw = clean_channel_id(config.get(key))
        if raw:
            yield raw


def _iter_guild_log_channel_ids(guild: disnake.Guild | None):
    canais = load_guild_channels(guild, include_global_fallback=True)
    for key in LOG_FALLBACK_KEYS:
        raw = clean_channel_id(canais.get(key))
        if raw:
            yield raw


async def ensure_guild_log_channel(
    guild: disnake.Guild | None,
    channel_key: str = "canal_de_logs_do_sistema",
    channel_name: str | None = None,
) -> disnake.TextChannel | None:
    if guild is None:
        return None

    canais = load_guild_channels(guild, include_global_fallback=True)
    for key in (channel_key, "canal_de_logs_do_sistema"):
        raw = clean_channel_id(canais.get(key))
        if raw:
            channel = guild.get_channel(int(raw))
            if isinstance(channel, disnake.TextChannel):
                return channel

    target_name = channel_name or "logs-do-sistema"
    names = (target_name,) if channel_name else ("logs-do-sistema", "system-logs", "logs")
    for name in names:
        channel = next((c for c in guild.text_channels if c.name == name), None)
        if isinstance(channel, disnake.TextChannel):
            set_guild_channel(guild, channel_key, channel.id)
            return channel

    category = next((c for c in guild.categories if str(c.name or "").lower() in {"logs", "system logs"}), None)
    overwrites = {guild.default_role: disnake.PermissionOverwrite(view_channel=False)}
    try:
        if category is None:
            category = await guild.create_category("Logs", reason="Criando categoria de logs por servidor")
        channel = await guild.create_text_channel(
            target_name,
            category=category,
            overwrites=overwrites,
            reason="Criando canal de logs por servidor",
        )
    except Exception as exc:
        print(f"[LyonLogs] Nao consegui criar canal de logs em {guild.id}: {exc}")
        return None

    set_guild_channel(guild, channel_key, channel.id)
    if channel_key != "canal_de_logs_do_sistema":
        set_guild_channel(guild, "canal_de_logs_do_sistema", channel.id)
    return channel


async def _resolve_log_channel(
    bot: disnake.Client,
    guild: disnake.Guild | None,
    config: dict | None,
    channel_id: int | str | None,
) -> disnake.TextChannel | None:
    candidates: list[str] = []
    explicit = clean_channel_id(channel_id)
    if explicit:
        candidates.append(explicit)
    candidates.extend(_iter_config_channel_ids(config, "logs_channel", "logs_channel_id", "log_channel_id"))
    candidates.extend(_iter_guild_log_channel_ids(guild))

    seen = set()
    for raw in candidates:
        if raw in seen:
            continue
        seen.add(raw)
        channel = guild.get_channel(int(raw)) if guild is not None else bot.get_channel(int(raw))
        if isinstance(channel, disnake.TextChannel):
            return channel

    return await ensure_guild_log_channel(guild)


async def send_system_log(
    bot: disnake.Client,
    guild: disnake.Guild | None,
    *,
    title: str,
    description: str,
    system: str = "Sistema",
    actor: disnake.abc.User | None = None,
    config: dict | None = None,
    channel_id: int | str | None = None,
) -> bool:
    channel = await _resolve_log_channel(bot, guild, config, channel_id)
    if channel is None:
        return False

    actor_line = f"\n**Responsavel:** {actor.mention} (`{actor.id}`)" if actor else ""
    content = (
        f"## {getattr(emoji, 'receipt', '')} {title}\n"
        f"-# Logs > {system}\n\n"
        f"{description}{actor_line}\n"
        f"**Data:** `{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}`"
    )

    try:
        await channel.send(
            components=[
                disnake.ui.Container(
                    disnake.ui.TextDisplay(content[:3900]),
                    accent_colour=_primary_colour(),
                )
            ],
            flags=disnake.MessageFlags(is_components_v2=True),
        )
        return True
    except Exception as exc:
        print(f"[LyonLogs] Falha ao enviar log de {system}: {exc}")
        return False
