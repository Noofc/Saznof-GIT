import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from .panel_v2 import build_panel_card, channel_label, configured_label, status_label


class BoasVindasPanel(commands.Cog):
    """Sistema de Boas Vindas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def display_boasvindas_panel(self, inter: disnake.MessageInteraction):
        config = db.get_document("boasvindas_config") or {}
        enabled = config.get("enabled", False)
        channel_id = config.get("channel_id") or config.get("channel")
        title_emoji = getattr(emoji, "members", "")

        return build_panel_card(
            title=f"{title_emoji} Boas Vindas".strip(),
            breadcrumb="Painel > Boas Vindas",
            description="Configure a mensagem enviada quando novos membros entram no servidor.",
            status_lines=[
                f"**Status:** {status_label(enabled)}",
                f"**Canal:** {channel_label(channel_id)}",
                f"**Mensagem:** {configured_label(config.get('message'))}",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Mensagem", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "edit", None), custom_id="BoasVindas_ConfigMsg"),
                    disnake.ui.Button(label="Canal", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "textc", None), custom_id="BoasVindas_ConfigCanal"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Desativar" if enabled else "Ativar",
                        style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "power", None),
                        custom_id="BoasVindas_Toggle",
                    ),
                ),
            ],
        )

    async def _refresh_panel(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_boasvindas_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @staticmethod
    def _format_welcome_message(member: disnake.Member, template: str) -> str:
        return (
            template
            .replace("{user}", member.mention)
            .replace("{user_name}", member.name)
            .replace("{user_id}", str(member.id))
            .replace("{server}", member.guild.name)
            .replace("{member_count}", str(member.guild.member_count or 0))
        )

    @commands.Cog.listener("on_member_join")
    async def boasvindas_member_join(self, member: disnake.Member):
        config = db.get_document("boasvindas_config") or {}
        if not config.get("enabled", False):
            return

        channel_id = config.get("channel_id") or config.get("channel")
        channel = member.guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, disnake.TextChannel):
            return

        template = config.get("message") or "Bem-vindo {user} ao servidor {server}!"
        content = self._format_welcome_message(member, template)
        try:
            await channel.send(content)
        except disnake.HTTPException:
            pass

    @commands.Cog.listener("on_message_interaction")
    async def BoasVindas_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("BoasVindas"):
            return

        if custom_id == "BoasVindas_ConfigMsg":
            class WelcomeMessageModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Mensagem de boas vindas",
                        custom_id="BoasVindas_MessageModal",
                        components=[
                            disnake.ui.TextInput(
                                label="Mensagem",
                                custom_id="message",
                                style=disnake.TextInputStyle.paragraph,
                                placeholder="Bem-vindo {user} ao servidor {server}!",
                                max_length=1800,
                            )
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    config = db.get_document("boasvindas_config") or {}
                    config["message"] = modal_inter.text_values.get("message", "").strip()
                    db.save_document("boasvindas_config", config)
                    await modal_inter.response.send_message(f"{emoji.correct} Mensagem de boas vindas salva.", ephemeral=True)

            await inter.response.send_modal(WelcomeMessageModal())
            return

        if custom_id == "BoasVindas_ConfigCanal":
            await inter.response.send_message(
                "Selecione o canal de boas vindas.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Escolha um canal",
                            custom_id="BoasVindas_SelectCanal",
                            channel_types=[disnake.ChannelType.text],
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "BoasVindas_SelectCanal":
            config = db.get_document("boasvindas_config") or {}
            config["channel_id"] = int(inter.values[0])
            db.save_document("boasvindas_config", config)
            await inter.response.send_message(f"{emoji.correct} Canal de boas vindas salvo em <#{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "BoasVindas_Toggle":
            await inter.response.defer(ephemeral=True)
            config = db.get_document("boasvindas_config") or {}
            config["enabled"] = not config.get("enabled", False)
            db.save_document("boasvindas_config", config)
            await self._refresh_panel(inter)
            status = "ativado" if config["enabled"] else "desativado"
            await inter.followup.send(f"{emoji.correct} Sistema de boas vindas {status}.", ephemeral=True)


def setup(bot):
    bot.add_cog(BoasVindasPanel(bot))
