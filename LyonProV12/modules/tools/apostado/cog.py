import disnake
from disnake.ext import commands

from functions.emoji import emoji
from functions.database import database as db
from functions.message import message, embed_message


class ApostadoFreeFire(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def display_apostado_panel(self, inter: disnake.MessageInteraction):
        mode_data = db.get_document("custom_mode")
        mode = mode_data.get("mode") if mode_data else "components"

        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter, send=False)

        # Tela inicial: mostrar emoji de arma antes de abrir o menu
        containers = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.Uzi}  APOSTADO FREE FIRE\nBem-vindo ao sistema de apostas. Clique em abrir o menu para acessar as ações."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Abrir Menu", style=disnake.ButtonStyle.green, emoji=emoji.commands, custom_id="Apostado_OpenMenu"),
                ),
                # usar acentuação padrão
            )
        ]

        await inter.edit_original_message(content=None, components=containers)

    @commands.Cog.listener("on_button_click")
    async def apostado_button_listener(self, inter: disnake.MessageInteraction):
        if not inter.component.custom_id.startswith("Apostado_"):
            return

        # Garantir modo/espera
        mode_data = db.get_document("custom_mode")
        mode = mode_data.get("mode") if mode_data else "components"
        if mode == "embed":
            await embed_message.wait(inter)
        else:
            await message.wait(inter)

        if inter.component.custom_id == "Apostado_OpenMenu":
            # Mostrar menu principal do sistema de apostas
            containers = [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(f"# {emoji.Uzi}  Menu Apostado Free Fire\nEscolha uma ação:"),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Iniciar Aposta", style=disnake.ButtonStyle.green, emoji=emoji.swords, custom_id="Apostado_Start"),
                        disnake.ui.Button(label="Histórico", style=disnake.ButtonStyle.grey, emoji=emoji.receipt, custom_id="Apostado_History"),
                        disnake.ui.Button(label="Saldo", style=disnake.ButtonStyle.grey, emoji=emoji.wallet, custom_id="Apostado_Saldo"),
                        disnake.ui.Button(label="", style=disnake.ButtonStyle.red, emoji=emoji.back, custom_id="Apostado_Back"),
                    ),
                )
            ]

            await inter.edit_original_message(content=None, components=containers)

        elif inter.component.custom_id == "Apostado_Start":
            await inter.response.send_message(f"{emoji.reload} Sistema de apostas: iniciando fluxo (placeholder).", ephemeral=True)

        elif inter.component.custom_id == "Apostado_History":
            await inter.response.send_message(f"{emoji.chart} Histórico de apostas (placeholder).", ephemeral=True)

        elif inter.component.custom_id == "Apostado_Saldo":
            await inter.response.send_message(f"{emoji.cart} Seu saldo: R$0,00 (placeholder).", ephemeral=True)

        elif inter.component.custom_id == "Apostado_Back":
            # Voltar para a tela inicial do painel principal
            painel_cog = self.bot.get_cog("PainelCommand")
            if painel_cog:
                # Reusar método de painel para redesenhar
                await painel_cog.Painel_Button_Listener(inter)
            else:
                await inter.response.send_message("Voltando...", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(ApostadoFreeFire(bot))
