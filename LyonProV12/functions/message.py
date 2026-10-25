"""Mensagens padronizadas em Componentes V2."""

import disnake

from functions.emoji import emoji


def _v2_flags() -> disnake.MessageFlags:
    return disnake.MessageFlags(is_components_v2=True)


def _normalize_components(component=None) -> list:
    if not component:
        return []
    if isinstance(component, (list, tuple)):
        return list(component)
    return [component]


def _v2_components(text: str, component=None) -> list:
    components = [disnake.ui.Container(disnake.ui.TextDisplay(text))]
    components.extend(_normalize_components(component))
    return components


async def _send_or_edit(inter, text: str, send=False, ephemeral=True, followup=False, component=None):
    components = _v2_components(text, component)

    if send:
        return await inter.response.send_message(
            components=components,
            ephemeral=ephemeral,
            flags=_v2_flags(),
        )

    if followup:
        return await inter.followup.send(
            components=components,
            ephemeral=ephemeral,
            flags=_v2_flags(),
        )

    return await inter.edit_original_message(
        content=None,
        embed=None,
        components=components,
        flags=_v2_flags(),
    )


async def _send_or_edit_plain(inter, text: str, send=False, ephemeral=True, followup=False, component=None):
    components = _normalize_components(component) or None

    if send:
        return await inter.response.send_message(
            content=text,
            components=components,
            ephemeral=ephemeral,
        )

    if followup:
        return await inter.followup.send(
            content=text,
            components=components,
            ephemeral=ephemeral,
        )

    if not inter.response.is_done():
        try:
            await inter.response.defer(with_message=False)
        except (disnake.errors.NotFound, disnake.HTTPException):
            return None

    try:
        return await inter.edit_original_message(
            content=text,
            embed=None,
            components=components,
        )
    except (disnake.errors.NotFound, disnake.HTTPException):
        return None


class message:
    @staticmethod
    async def wait(inter: disnake.MessageInteraction, send=False, ephemeral=True, followup=False, use_v2_components=False) -> disnake.Message:
        if send or followup:
            return await _send_or_edit(
                inter,
                f"{emoji.loading} Carregando informacoes...",
                send=send,
                ephemeral=ephemeral,
                followup=followup,
            )

        if not inter.response.is_done():
            try:
                await inter.response.defer(with_message=False)
            except (disnake.errors.NotFound, disnake.HTTPException):
                return None

        try:
            return await _send_or_edit(inter, f"{emoji.loading} Carregando informacoes...")
        except (disnake.errors.NotFound, disnake.HTTPException):
            return None

    @staticmethod
    async def missing_perms(inter: disnake.MessageInteraction) -> disnake.Message:
        return await _send_or_edit(inter, "Voce nao tem permissao para usar este comando", send=True)

    @staticmethod
    async def error(inter: disnake.MessageInteraction, text: str, send=False, followup=False, component=None) -> disnake.Message:
        return await _send_or_edit(inter, text, send=send, followup=followup, component=component)

    @staticmethod
    async def success(inter: disnake.MessageInteraction, text: str, send=False, followup=False, component=None) -> disnake.Message:
        return await _send_or_edit(inter, text, send=send, followup=followup, component=component)


class embed_message:
    @staticmethod
    async def wait(inter: disnake.MessageInteraction, send=False, ephemeral=True, followup=False) -> disnake.Message:
        return await _send_or_edit_plain(
            inter,
            f"{emoji.loading} Carregando informacoes...",
            send=send,
            ephemeral=ephemeral,
            followup=followup,
        )

    @staticmethod
    async def missing_perms(inter: disnake.MessageInteraction) -> disnake.Message:
        return await _send_or_edit_plain(inter, "Voce nao tem permissao para usar este comando", send=True)

    @staticmethod
    async def error(inter: disnake.MessageInteraction, text: str, send=False, followup=False, component=None) -> disnake.Message:
        return await _send_or_edit_plain(inter, text, send=send, followup=followup, component=component)

    @staticmethod
    async def success(inter: disnake.MessageInteraction, text: str, send=False, followup=False, component=None) -> disnake.Message:
        return await _send_or_edit_plain(inter, text, send=send, followup=followup, component=component)

    @staticmethod
    async def plain(inter: disnake.MessageInteraction, content: str, send=False, followup=False, component=None) -> disnake.Message:
        return await _send_or_edit_plain(inter, content, send=send, followup=followup, component=component)
