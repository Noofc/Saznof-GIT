from __future__ import annotations

from collections.abc import Iterable

import disnake

from functions.database import database as db
from functions.emoji import emoji


def _accent_colour(default_hex: str = "#5865f2") -> disnake.Colour:
    colors = db.get_document("custom_colors") or {}
    color_hex = colors.get("primary") or default_hex
    try:
        return disnake.Colour(int(color_hex.replace("#", ""), 16))
    except Exception:
        return disnake.Colour(int(default_hex.replace("#", ""), 16))


def status_label(enabled: bool) -> str:
    return "`Ativo`" if enabled else "`Inativo`"


def configured_label(value) -> str:
    return "`Configurado`" if value else "`Nao configurado`"


def channel_label(channel_id) -> str:
    return f"<#{channel_id}>" if channel_id else "`Nao configurado`"


def back_row(custom_id: str = "PainelInicial") -> disnake.ui.ActionRow:
    return disnake.ui.ActionRow(
        disnake.ui.Button(
            label="",
            style=disnake.ButtonStyle.grey,
            emoji=emoji.back,
            custom_id=custom_id,
        )
    )


def build_panel_card(
    *,
    title: str,
    breadcrumb: str,
    description: str,
    status_lines: Iterable[str] | None = None,
    rows: Iterable[disnake.ui.ActionRow] | None = None,
    include_back: bool = True,
    back_custom_id: str = "PainelInicial",
) -> list:
    children = [
        disnake.ui.TextDisplay(f"## {title}"),
        disnake.ui.TextDisplay(f"-# {breadcrumb}"),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.TextDisplay(description),
    ]

    if status_lines:
        children.extend(
            [
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay("\n".join(status_lines)),
            ]
        )

    action_rows = list(rows or [])
    if action_rows:
        children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
        children.extend(action_rows)

    components = [
        disnake.ui.Container(
            *children,
            accent_colour=_accent_colour(),
        )
    ]
    if include_back:
        components.append(back_row(back_custom_id))
    return components
