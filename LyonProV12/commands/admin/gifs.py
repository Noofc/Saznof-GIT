import random

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from .panel_v2 import build_panel_card


class GIFsPanel(commands.Cog):
    """Sistema de GIFs Automaticos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def display_gifs_panel(self, inter: disnake.MessageInteraction):
        gifs_config = db.get_document("gifs_config") or {}
        gifs = gifs_config.get("gifs", {})
        total_urls = sum(len(item.get("urls", [])) for item in gifs.values())
        enabled = gifs_config.get("enabled", False)
        channel_id = gifs_config.get("channel_id")

        return build_panel_card(
            title="GIFs Automaticos",
            breadcrumb="Painel > GIFs",
            description="Configure GIFs para eventos automaticos do servidor.",
            status_lines=[
                f"**Status:** `{'Ativo' if enabled else 'Inativo'}`",
                f"**Canal:** {f'<#{channel_id}>' if channel_id else '`Nao configurado`'}",
                f"**Eventos configurados:** `{len(gifs)}`",
                f"**URLs cadastradas:** `{total_urls}`",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Desativar" if enabled else "Ativar", style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success, emoji=getattr(emoji, "power", None), custom_id="GIFs_Toggle"),
                    disnake.ui.Button(label="Adicionar", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "plus", None), custom_id="GIFs_Adicionar"),
                    disnake.ui.Button(label="Listar", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "receipt", None), custom_id="GIFs_Listar", disabled=not gifs),
                    disnake.ui.Button(label="Config", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "settings2", None), custom_id="GIFs_Config"),
                )
            ],
        )

    async def _refresh_panel(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_gifs_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @staticmethod
    def _event_card_data(event_keys: tuple[str, ...]) -> tuple[str, str, disnake.Colour]:
        keys = set(event_keys)
        if {"saida", "leave"} & keys:
            return "Saida do servidor", "Um membro saiu do servidor.", disnake.Colour.red()
        if {"entrada", "join", "boasvindas"} & keys:
            return "Entrada no servidor", "Um novo membro entrou no servidor.", disnake.Colour.green()
        return "GIF Automatico", "Evento automatico do servidor.", disnake.Colour.blurple()

    @classmethod
    def _build_event_gif_components(
        cls,
        member: disnake.Member,
        event_keys: tuple[str, ...],
        gif_url: str,
    ) -> list:
        title, description, accent_colour = cls._event_card_data(event_keys)
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {title}"),
                disnake.ui.TextDisplay(f"{member.mention}\n-# {description}"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.MediaGallery(
                    disnake.MediaGalleryItem(gif_url, description=title)
                ),
                accent_colour=accent_colour,
            )
        ]

    @commands.Cog.listener("on_message_interaction")
    async def GIFs_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("GIFs"):
            return

        if custom_id == "GIFs_Adicionar":
            class GifModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Adicionar GIF",
                        custom_id="GIFs_AddModal",
                        components=[
                            disnake.ui.TextInput(label="Evento", custom_id="event", max_length=48, placeholder="entrada, saida, compra..."),
                            disnake.ui.TextInput(label="URL do GIF", custom_id="url", max_length=500),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    event = values.get("event", "").strip().lower()
                    url = values.get("url", "").strip()
                    data = db.get_document("gifs_config") or {}
                    gifs = data.setdefault("gifs", {})
                    item = gifs.setdefault(event, {"urls": []})
                    item.setdefault("urls", []).append(url)
                    db.save_document("gifs_config", data)
                    await modal_inter.response.send_message(f"{emoji.correct} GIF adicionado ao evento `{event}`.", ephemeral=True)

            await inter.response.send_modal(GifModal())
            return

        if custom_id == "GIFs_Toggle":
            await inter.response.defer(ephemeral=True)
            data = db.get_document("gifs_config") or {}
            data["enabled"] = not data.get("enabled", False)
            db.save_document("gifs_config", data)
            await self._refresh_panel(inter)
            status = "ativado" if data["enabled"] else "desativado"
            await inter.followup.send(f"{emoji.correct} GIFs automaticos {status}.", ephemeral=True)
            return

        if custom_id == "GIFs_Listar":
            gifs_config = db.get_document("gifs_config") or {}
            gifs = gifs_config.get("gifs", {})
            if not gifs:
                await inter.response.send_message(f"{emoji.wrong} Nenhum GIF configurado.", ephemeral=True)
                return

            gifs_list = "\n".join(
                f"- `{event}` - {len(item.get('urls', []))} URL(s)"
                for event, item in list(gifs.items())[:10]
            )
            await inter.response.send_message(f"**GIFs Automaticos ({len(gifs)}):**\n{gifs_list}", ephemeral=True)
            return

        if custom_id == "GIFs_Config":
            await inter.response.send_message(
                "Selecione o canal onde os GIFs automaticos serao enviados.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Canal dos GIFs",
                            custom_id="GIFs_SelectCanal",
                            channel_types=[disnake.ChannelType.text],
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "GIFs_SelectCanal":
            data = db.get_document("gifs_config") or {}
            data["channel_id"] = int(inter.values[0])
            db.save_document("gifs_config", data)
            await inter.response.send_message(f"{emoji.correct} Canal de GIFs salvo em <#{inter.values[0]}>.", ephemeral=True)

    async def _send_event_gif(self, member: disnake.Member, event_keys: tuple[str, ...]):
        config = db.get_document("gifs_config") or {}
        if not config.get("enabled", False):
            return

        channel_id = config.get("channel_id")
        channel = member.guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, disnake.TextChannel):
            return

        gifs = config.get("gifs", {})
        urls = []
        for key in event_keys:
            urls.extend((gifs.get(key) or {}).get("urls", []))
        if not urls:
            return

        gif_url = random.choice(urls)
        components = self._build_event_gif_components(member, event_keys, gif_url)
        try:
            await channel.send(
                components=components,
                flags=disnake.MessageFlags(is_components_v2=True),
            )
        except disnake.HTTPException:
            pass

    @commands.Cog.listener("on_member_join")
    async def gifs_member_join(self, member: disnake.Member):
        await self._send_event_gif(member, ("entrada", "join", "boasvindas"))

    @commands.Cog.listener("on_member_remove")
    async def gifs_member_remove(self, member: disnake.Member):
        await self._send_event_gif(member, ("saida", "leave"))


def setup(bot):
    bot.add_cog(GIFsPanel(bot))
