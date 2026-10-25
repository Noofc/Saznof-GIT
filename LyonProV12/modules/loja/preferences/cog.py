"""
Aqui nesse painel vai ficar um select com todas as preferencias que da pra configurar igual no modules/tickets que tem o sistema de preferencias legal e organizado.
"""

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message


class PreferenciasLoja(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def panel(inter: disnake.MessageInteraction) -> dict:
        mode = db.get_document("custom_mode").get("mode")
        return PreferenciasLoja._panel_embed(inter) if mode == "embed" else PreferenciasLoja._panel_components(inter)

    @staticmethod
    def _panel_components(inter: disnake.MessageInteraction) -> dict:
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

        options = [
            disnake.SelectOption(label="Tempo do Carrinho", value="cart", emoji=emoji.clock, description="Defina o tempo padrão do carrinho"),
            disnake.SelectOption(label="Horário de Funcionamento", value="hours", emoji=emoji.calendar, description="Defina o horário de funcionamento da loja"),
            disnake.SelectOption(label="Manutenção", value="maintenance", emoji=emoji.settings2, description="Ative ou desative a manutenção da loja"),
            disnake.SelectOption(label="Solicitar Estoque", value="stock_requests", emoji=emoji.cardbox, description="Configure solicitações de estoque"),
            disnake.SelectOption(label="Termos da Loja", value="terms", emoji=emoji.receipt, description="Configure os termos que usuários precisam aceitar"),
            disnake.SelectOption(label="Preferências de Recibos", value="receipts", emoji=emoji.receipt, description="Configure o estilo de recibos enviados após compras."),
            disnake.SelectOption(label="Transcript de Carrinhos", value="transcripts", emoji=emoji.double_speech, description="Ative ou desative o transcript"),
        ]

        return {"components": [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Loja > **Preferências**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("Gerencie as preferências globais da sua loja."),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Loja_Preferencias_Select",
                        placeholder="Selecione uma preferência para configurar",
                        options=options
                    )
                ),
                **container_kwargs
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Loja")
            )
        ]}

    @staticmethod
    def _panel_embed(inter: disnake.MessageInteraction) -> dict:
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        embed = disnake.Embed(
            title="Preferências da Loja",
            description=(
                "-# Painel > Loja > **Preferências**\n\n"
                "Gerencie as preferências globais da sua loja."
            )
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)

        options = [
            disnake.SelectOption(label="Tempo do Carrinho", value="cart", emoji=emoji.clock, description="Defina o tempo padrão do carrinho"),
            disnake.SelectOption(label="Horário de Funcionamento", value="hours", emoji=emoji.calendar, description="Defina o horário de funcionamento da loja"),
            disnake.SelectOption(label="Manutenção", value="maintenance", emoji=emoji.settings2, description="Ative ou desative a manutenção da loja"),
            disnake.SelectOption(label="Solicitar Estoque", value="stock_requests", emoji=emoji.cardbox, description="Configure solicitações de estoque"),
            disnake.SelectOption(label="Termos da Loja", value="terms", emoji=emoji.receipt, description="Configure os termos que usuários precisam aceitar"),
            disnake.SelectOption(label="Preferências de Recibos", value="receipts", emoji=emoji.receipt, description="Configure o estilo de recibos enviados após compras."),
            disnake.SelectOption(label="Transcript de Carrinhos", value="transcripts", emoji=emoji.double_speech, description="Ative ou desative o transcript"),
        ]

        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Loja_Preferencias_Select",
                    placeholder="Selecione uma preferência para configurar",
                    options=options
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Loja")
            )
        ]
        return {"embed": embed, "components": components}

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Loja_Preferencias":
            mode = db.get_document("custom_mode").get("mode")
            await (embed_message if mode == "embed" else message).wait(inter, send=False)
            panel = PreferenciasLoja.panel(inter)
            if mode == "embed":
                await inter.edit_original_message(content=None, **panel)
            else:
                await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Loja_Preferencias_Select":
            value = inter.values[0]
            mode = db.get_document("custom_mode").get("mode")
            
            # Defer a resposta primeiro
            await inter.response.defer()

            try:
                if value == "cart":
                    from .temp_cart import CartPreferences
                    panel = CartPreferences.panel(inter)
                elif value == "hours":
                    from .horario import StoreHoursPreferences
                    panel = StoreHoursPreferences.panel(inter)
                elif value == "maintenance":
                    from .manutencao import MaintenancePreferences
                    panel = MaintenancePreferences.panel(inter)
                elif value == "stock_requests":
                    from .solicitar_estoque import StockRequestPreferences
                    panel = StockRequestPreferences.panel(inter)
                elif value == "terms":
                    from .terms import TermsPreferences
                    panel = TermsPreferences.panel(inter)
                elif value == "receipts":
                    from .receipts import ReceiptPreferences
                    panel = ReceiptPreferences.panel(inter)
                elif value == "transcripts":
                    from .transcripts import TranscriptsPreferences
                    panel = TranscriptsPreferences.panel(inter)
                else:
                    panel = PreferenciasLoja.panel(inter)

                # Verificar o tipo de retorno do painel
                if isinstance(panel, tuple):
                    # Pode ser (embed, components) ou (container, buttons)
                    first, second = panel
                    if isinstance(first, disnake.Embed):
                        await inter.edit_original_message(content=None, embed=first, components=second)
                    else:
                        # Tratar como components v2: construir lista de components
                        components_list = []
                        if isinstance(first, (disnake.ui.Container, disnake.ui.ActionRow)):
                            components_list.append(first)
                        elif isinstance(first, (list, tuple)):
                            components_list.extend(list(first))
                        else:
                            components_list.append(first)

                        if isinstance(second, (disnake.ui.Container, disnake.ui.ActionRow)):
                            components_list.append(second)
                        elif isinstance(second, (list, tuple)):
                            components_list.extend(list(second))
                        else:
                            components_list.append(second)

                        await inter.edit_original_message(content=None, components=components_list, flags=disnake.MessageFlags(is_components_v2=True))
                elif "embed" in panel:
                    if panel.get("embed") is None and "components" in panel:
                        await inter.edit_original_message(
                            content=None,
                            embed=None,
                            components=panel["components"],
                            flags=disnake.MessageFlags(is_components_v2=True),
                        )
                    else:
                        # Painel com embed
                        await inter.edit_original_message(content=None, **panel)
                elif "components" in panel:
                    # Painel apenas com components (modo components v2)
                    await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))
                else:
                    # Fallback: tentar editar com o que foi retornado
                    await inter.edit_original_message(**panel)
            except Exception as e:
                # Em caso de erro, voltar ao painel principal silenciosamente
                try:
                    panel = PreferenciasLoja.panel(inter)
                    if "embed" in panel:
                        await inter.edit_original_message(content=None, **panel)
                    else:
                        await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))
                except Exception as e2:
                    # Se ainda assim falhar, enviar mensagem de erro
                    await inter.followup.send(
                        f"{emoji.wrong} Erro ao carregar painel: {str(e2)}",
                        ephemeral=True
                    )


def setup(bot: commands.Bot):
    bot.add_cog(PreferenciasLoja(bot))
