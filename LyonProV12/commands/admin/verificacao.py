import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from .panel_v2 import build_panel_card, channel_label, configured_label, status_label


class VerificacaoPanel(commands.Cog):
    """Sistema de Verificacao Captcha."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def display_verificacao_panel(self, inter: disnake.MessageInteraction):
        config = db.get_document("verificacao_config") or {}
        enabled = config.get("enabled", False)
        channel_id = config.get("channel_id") or config.get("channel")

        return build_panel_card(
            title="Verificacao Captcha",
            breadcrumb="Painel > Verificacao",
            description="Configure a verificacao para proteger o servidor contra contas indevidas.",
            status_lines=[
                f"**Status:** {status_label(enabled)}",
                f"**Canal:** {channel_label(channel_id)}",
                f"**Cargo verificado:** {configured_label(config.get('role_id'))}",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Canal", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "textc", None), custom_id="Verificacao_ConfigCanal"),
                    disnake.ui.Button(
                        label="Desativar" if enabled else "Ativar",
                        style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "power", None),
                        custom_id="Verificacao_Toggle",
                    ),
                    disnake.ui.Button(label="Cargo", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "role", None), custom_id="Verificacao_Config"),
                    disnake.ui.Button(label="Enviar Painel", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "send", None), custom_id="Verificacao_EnviarPainel"),
                )
            ],
        )

    async def _refresh_panel(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_verificacao_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @commands.Cog.listener("on_message_interaction")
    async def Verificacao_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Verificacao"):
            return

        if custom_id == "Verificacao_ConfigCanal":
            await inter.response.send_message(
                "Selecione o canal de verificacao.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Canal de verificacao",
                            custom_id="Verificacao_SelectCanal",
                            channel_types=[disnake.ChannelType.text],
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Verificacao_SelectCanal":
            config = db.get_document("verificacao_config") or {}
            config["channel_id"] = int(inter.values[0])
            db.save_document("verificacao_config", config)
            await inter.response.send_message(f"{emoji.correct} Canal de verificacao salvo em <#{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "Verificacao_Toggle":
            await inter.response.defer(ephemeral=True)
            config = db.get_document("verificacao_config") or {}
            config["enabled"] = not config.get("enabled", False)
            db.save_document("verificacao_config", config)
            await self._refresh_panel(inter)
            status = "ativado" if config["enabled"] else "desativado"
            await inter.followup.send(f"{emoji.correct} Sistema de verificacao {status}.", ephemeral=True)
            return

        if custom_id == "Verificacao_EnviarPainel":
            config = db.get_document("verificacao_config") or {}
            channel_id = config.get("channel_id") or config.get("channel")
            role_id = config.get("role_id")

            if not config.get("enabled", False):
                await inter.response.send_message(f"{emoji.wrong} Ative o sistema de verificacao antes de enviar o painel.", ephemeral=True)
                return
            if not channel_id or not role_id:
                await inter.response.send_message(f"{emoji.wrong} Configure canal e cargo verificado antes de enviar o painel.", ephemeral=True)
                return

            channel = inter.guild.get_channel(int(channel_id)) if inter.guild else None
            if not isinstance(channel, disnake.TextChannel):
                await inter.response.send_message(f"{emoji.wrong} Canal de verificacao nao encontrado.", ephemeral=True)
                return

            components = [
                disnake.ui.Container(
                    disnake.ui.TextDisplay("## Verificacao"),
                    disnake.ui.TextDisplay("Clique no botao abaixo para receber o cargo de verificado."),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    disnake.ui.ActionRow(
                        disnake.ui.Button(
                            label="Verificar",
                            style=disnake.ButtonStyle.success,
                            emoji=getattr(emoji, "correct", None),
                            custom_id="Verificacao_Verificar",
                        )
                    ),
                )
            ]
            await channel.send(components=components, flags=disnake.MessageFlags(is_components_v2=True))
            await inter.response.send_message(f"{emoji.correct} Painel de verificacao enviado em <#{channel.id}>.", ephemeral=True)
            return

        if custom_id == "Verificacao_Config":
            await inter.response.send_message(
                "Selecione o cargo entregue apos a verificacao.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.RoleSelect(placeholder="Cargo verificado", custom_id="Verificacao_SelectRole")
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Verificacao_SelectRole":
            config = db.get_document("verificacao_config") or {}
            config["role_id"] = int(inter.values[0])
            db.save_document("verificacao_config", config)
            await inter.response.send_message(f"{emoji.correct} Cargo verificado salvo: <@&{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "Verificacao_Verificar":
            config = db.get_document("verificacao_config") or {}
            if not config.get("enabled", False):
                await inter.response.send_message(f"{emoji.wrong} A verificacao esta desativada.", ephemeral=True)
                return

            role_id = config.get("role_id")
            role = inter.guild.get_role(int(role_id)) if inter.guild and role_id else None
            if not role:
                await inter.response.send_message(f"{emoji.wrong} Cargo de verificado nao configurado.", ephemeral=True)
                return

            member = inter.user if isinstance(inter.user, disnake.Member) else inter.guild.get_member(inter.user.id)
            if not member:
                await inter.response.send_message(f"{emoji.wrong} Nao consegui localizar seu membro no servidor.", ephemeral=True)
                return

            try:
                await member.add_roles(role, reason="Verificacao pelo painel")
            except disnake.Forbidden:
                await inter.response.send_message(f"{emoji.wrong} Nao tenho permissao para entregar esse cargo.", ephemeral=True)
                return

            await inter.response.send_message(f"{emoji.correct} Verificacao concluida. Cargo {role.mention} entregue.", ephemeral=True)


def setup(bot):
    bot.add_cog(VerificacaoPanel(bot))
