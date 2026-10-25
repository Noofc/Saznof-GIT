import disnake
from disnake.ext import commands
import aiohttp
from datetime import datetime

from functions.emoji import emoji
from functions.database import database as db
from functions.message import message, embed_message
from functions.utils import utils
from .. import subscription_manager as subs


class BoostExtension(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_url = "https://getvyenx.cloud/api/v1"
        self.webhook_token = "seu_token_aqui"  # Configurar no painel

    def _check_extension_enabled(self) -> bool:
        """Verifica se a extensão boost está habilitada"""
        return subs.is_extension_active("boost")

    def _get_boost_data(self) -> dict:
        """Obtém dados do boost"""
        data = db.obter("database/extensions/data.json")
        if "boost" not in data:
            data["boost"] = {
                "total_accounts": 0,
                "total_boosts_sent": 0,
                "orders": {}
            }
            db.salvar("database/extensions/data.json", data)
        return data["boost"]

    def _save_boost_data(self, boost_data: dict):
        """Salva dados do boost"""
        data = db.obter("database/extensions/data.json")
        data["boost"] = boost_data
        db.salvar("database/extensions/data.json", data)

    def _get_stock(self) -> list:
        """Obtém estoque de tokens"""
        stock = db.obter("database/extensions/stock.json")
        return stock.get("tokens", [])

    def _save_stock(self, tokens: list):
        """Salva estoque de tokens"""
        db.salvar("database/extensions/stock.json", {"tokens": tokens})

    async def display_boost_panel(self, inter: disnake.MessageInteraction):
        """Exibe o painel principal de boost"""
        if not self._check_extension_enabled():
            mode = db.get_document("custom_mode").get("mode")
            text = "Esta extensão não está ativada. Compre a extensão primeiro!"
            send_initial = not inter.response.is_done()
            followup = inter.response.is_done()
            try:
                if mode == "embed":
                    await embed_message.error(inter, text, send=send_initial, followup=followup)
                else:
                    await message.error(inter, text, send=send_initial, followup=followup)
            except (disnake.NotFound, disnake.HTTPException) as exc:
                print(f"[Boost] Interacao expirada ao exibir aviso de extensao inativa: {exc}")
            return

        mode = db.get_document("custom_mode").get("mode")
        boost_data = self._get_boost_data()
        stock = self._get_stock()

        if mode == "embed":
            await embed_message.wait(inter, send=False)
            embed, components = self._build_embed_panel(inter, boost_data, stock)
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            await message.wait(inter, send=False)
            components = self._build_components_panel(inter, boost_data, stock)
            await inter.edit_original_message(components=components)

    def _build_components_panel(self, inter: disnake.MessageInteraction, boost_data: dict, stock: list) -> list:
        """Constrói painel em modo components"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        total_accounts = len(stock)
        total_boosts = boost_data.get("total_boosts_sent", 0)

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.Lyon}\n"
                    f"-# Painel > Configurações > Extensões > **system Boost**"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"{emoji.members} **Estoque de Contas:** `{total_accounts}`\n"
                    f"{emoji.boost} **Boosts Enviados:** `{total_boosts}`\n"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Estoque",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.cardbox,
                        custom_id="Boost_StockMenu"
                    ),
                    disnake.ui.Button(
                        label="Gerenciar Gifts",
                        style=disnake.ButtonStyle.green,
                        emoji=emoji.gift,
                        custom_id="Boost_ManageGifts"
                    ),
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Configuracoes_Extensoes"
                ),
                disnake.ui.Button(
                    label="Instruções",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.information,
                    custom_id="Boost_Instructions"
                ),
                disnake.ui.Button(
                    label="Token Checker",
                    style=disnake.ButtonStyle.link,
                    emoji=emoji.link,
                    url="https://www.mediafire.com/file/8aal844sxuadqaw/Token_Checker.zip/file"
                ),
            )
        ]

    def _build_embed_panel(self, inter: disnake.MessageInteraction, boost_data: dict, stock: list) -> tuple:
        """Constrói painel em modo embed"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        total_accounts = len(stock)
        total_boosts = boost_data.get("total_boosts_sent", 0)

        embed = disnake.Embed(
            title=f"{emoji.boost} system Boost",
            description=(
                f"{emoji.members} **Estoque de Contas:** {total_accounts}\n"
                f"{emoji.boost} **Boosts Enviados:** {total_boosts}"
            ),
        )

        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color

        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Estoque",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.cardbox,
                    custom_id="Boost_StockMenu"
                ),
                disnake.ui.Button(
                    label="Gerenciar Gifts",
                    style=disnake.ButtonStyle.green,
                    emoji=emoji.gift,
                    custom_id="Boost_ManageGifts"
                ),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Configuracoes_Extensoes"
                ),
                disnake.ui.Button(
                    label="Instruções",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.information,
                    custom_id="Boost_Instructions"
                ),
                disnake.ui.Button(
                    label="Token Checker",
                    style=disnake.ButtonStyle.link,
                    emoji=emoji.link,
                    url="https://www.mediafire.com/file/8aal844sxuadqaw/Token_Checker.zip/file"
                ),    
            )
        ]

        return embed, components

    @commands.Cog.listener("on_button_click")
    async def on_boost_button_click(self, inter: disnake.MessageInteraction):
        if not inter.component.custom_id.startswith("Boost_"):
            return

        if not self._check_extension_enabled():
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.error(inter, "Esta extensão não está ativada!", send=True)
            else:
                await message.error(inter, "Esta extensão não está ativada!", send=True)
            return

        if inter.component.custom_id == "Boost_StockMenu":
            await self._show_stock_menu(inter)
        elif inter.component.custom_id == "Boost_ManageGifts":
            await self._show_gifts_menu(inter)
        elif inter.component.custom_id == "Boost_AddStock":
            await self._show_add_stock_modal(inter)
        elif inter.component.custom_id == "Boost_ViewStock":
            await self._show_stock_view(inter)
        elif inter.component.custom_id == "Boost_GetStock":
            await self._send_stock_file(inter)
        elif inter.component.custom_id == "Boost_Instructions":
            await self._show_instructions(inter)
        elif inter.component.custom_id == "Boost_BackToPanel":
            await self._show_boost_panel(inter)

    async def _show_boost_panel(self, inter: disnake.MessageInteraction):
        """Mostra o painel principal do boost"""
        mode = db.get_document("custom_mode").get("mode")
        boost_data = self._get_boost_data()
        stock = self._get_stock()
        
        if mode == "embed":
            embed, components = self._build_embed_panel(inter, boost_data, stock)
            await inter.response.edit_message(embed=embed, components=components)
        else:
            components = self._build_components_panel(inter, boost_data, stock)
            await inter.response.edit_message(content=None, components=components)

    async def _show_instructions(self, inter: disnake.MessageInteraction):
        """Mostra instruções de uso do sistema de boost"""
        mode = db.get_document("custom_mode").get("mode")
        
        if mode == "embed":
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")
            
            embed = disnake.Embed(
                title=f"{emoji.information} Instruções - system Boost",
                description="Aprenda a usar o sistema de boost completo",
            )
            
            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                embed.color = primary_color
            
            embed.add_field(
                name=f"{emoji.cardbox} Gerenciar Estoque",
                value=(
                    "**Adicionar Tokens:**\n"
                    "1. Clique em `Estoque` no painel\n"
                    "2. Clique em `Adicionar Estoque`\n"
                    "3. Cole os tokens (um por linha)\n\n"
                    "**Ver Estoque:**\n"
                    "• Visualize tokens parcialmente ocultos\n"
                    "• Baixe arquivo completo com todos os tokens\n"
                    "• Limpe o estoque quando necessário"
                ),
                inline=False
            )
            
            embed.add_field(
                name=f"{emoji.gift} Sistema de Gifts",
                value=(
                    "**Criar Gift:**\n"
                    "1. Clique em `Gerenciar Gifts`\n"
                    "2. Clique em `Criar Gift`\n"
                    "3. Digite quantidade de boosts (deve ser PAR)\n"
                    "4. Opcionalmente: quantidade de gifts\n"
                    "5. Compartilhe o link gerado!\n\n"
                    "**Importante:**\n"
                    "• Cada conta = 2 boosts\n"
                    "• Quantidade deve ser par (2, 4, 6, 8...)\n"
                    "• Verifica estoque automaticamente"
                ),
                inline=False
            )
            
            embed.add_field(
                name=f"{emoji.rocket} Comandos de Boost",
                value=(
                    "**Enviar Boosts:**\n"
                    "`/boost enviar <quantidade> <convite> [nome] [bio]`\n"
                    "• `quantidade`: Número de tokens a usar\n"
                    "• `convite`: Link do servidor\n"
                    "• `nome`: Nome personalizado (opcional)\n"
                    "• `bio`: Bio personalizada (opcional)\n\n"
                    "**Verificar Status:**\n"
                    "`/boost status <order_id>`\n"
                    "• Veja progresso da ordem\n"
                    "• Boosts bem-sucedidos e falhados\n"
                    "• Erros detalhados se houver"
                ),
                inline=False
            )
            
            embed.add_field(
                name=f"{emoji.link} Links Úteis",
                value=(
                    "**Token Checker:**\n"
                    "[Download](https://www.mediafire.com/file/8aal844sxuadqaw/Token_Checker.zip/file)\n\n"
                    "**Suporte:**\n"
                    "Entre em contato pelo Discord para ajuda"
                ),
                inline=False
            )
            
            await inter.response.send_message(embed=embed, ephemeral=True)
        else:
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")
            
            container_kwargs = {}
            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                container_kwargs["accent_colour"] = disnake.Colour(primary_color)
            
            container = disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.information}\n"
                    f"-# Instruções - system Boost\n\n"
                    f"## {emoji.cardbox} Gerenciar Estoque\n\n"
                    f"**Adicionar Tokens:**\n"
                    f"1. Clique em `Estoque` no painel\n"
                    f"2. Clique em `Adicionar Estoque`\n"
                    f"3. Cole os tokens (um por linha)\n\n"
                    f"**Ver Estoque:**\n"
                    f"• Visualize tokens parcialmente ocultos\n"
                    f"• Baixe arquivo completo\n"
                    f"• Limpe quando necessário\n\n"
                    f"## {emoji.gift} Sistema de Gifts\n\n"
                    f"**Criar Gift:**\n"
                    f"1. Clique em `Gerenciar Gifts`\n"
                    f"2. Clique em `Criar Gift`\n"
                    f"3. Digite quantidade de boosts (PAR)\n"
                    f"4. Compartilhe o link!\n\n"
                    f"**Importante:**\n"
                    f"• Cada conta = 2 boosts\n"
                    f"• Quantidade deve ser par\n\n"
                    f"## {emoji.rocket} Comandos\n\n"
                    f"**Enviar Boosts:**\n"
                    f"`/boost enviar <qtd> <convite>`\n\n"
                    f"**Verificar Status:**\n"
                    f"`/boost status <order_id>`"
                ),
                **container_kwargs
            )
            
            await inter.response.send_message(components=[container], ephemeral=True)

    async def _show_stock_menu(self, inter: disnake.MessageInteraction):
        """Mostra menu de gerenciamento de estoque"""
        mode = db.get_document("custom_mode").get("mode")
        stock = self._get_stock()
        total_accounts = len(stock)

        if mode == "embed":
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")

            embed = disnake.Embed(
                title=f"{emoji.cardbox} Gerenciar Estoque",
                description=f"**Total de Contas:** `{total_accounts}`\n\nEscolha uma opção abaixo:",
            )

            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                embed.color = primary_color

            components = [
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Adicionar Estoque",
                        style=disnake.ButtonStyle.green,
                        emoji=emoji.plus,
                        custom_id="Boost_AddStock"
                    ),
                    disnake.ui.Button(
                        label="Ver Estoque",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.search,
                        custom_id="Boost_ViewStock"
                    ),
                    disnake.ui.Button(
                        label="Obter Estoque",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.save,
                        custom_id="Boost_GetStock"
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.back,
                        custom_id="Boost_BackToPanel"
                    )
                )
            ]

            await inter.response.send_message(embed=embed, components=components, ephemeral=True)
        else:
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")

            container_kwargs = {}
            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                container_kwargs["accent_colour"] = disnake.Colour(primary_color)

            container = disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.cardbox}\n"
                    f"-# Gerenciar Estoque\n\n"
                    f"**Total de Contas:** `{total_accounts}`\n\n"
                    f"Escolha uma opção abaixo:"
                ),
                **container_kwargs
            )

            buttons = [
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Adicionar Estoque",
                        style=disnake.ButtonStyle.green,
                        emoji=emoji.plus,
                        custom_id="Boost_AddStock"
                    ),
                    disnake.ui.Button(
                        label="Ver Estoque",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.search,
                        custom_id="Boost_ViewStock"
                    ),
                    disnake.ui.Button(
                        label="Obter Estoque",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.save,
                        custom_id="Boost_GetStock"
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.back,
                        custom_id="Boost_BackToPanel"
                    )
                )
            ]

            await inter.response.send_message(components=[container] + buttons, ephemeral=True)

    async def _show_gifts_menu(self, inter: disnake.MessageInteraction):
        """Mostra menu de gerenciamento de gifts"""
        mode = db.get_document("custom_mode").get("mode")

        # Importar gerenciador de gifts
        from .gifts import show_gifts_panel
        await show_gifts_panel(inter, self.bot)

    async def _show_add_stock_modal(self, inter: disnake.MessageInteraction):
        """Mostra modal para adicionar tokens ao estoque"""
        await inter.response.send_modal(
            title="Adicionar Tokens ao Estoque",
            custom_id="Boost_AddStockModal",
            components=[
                disnake.ui.TextInput(
                    label="Tokens (um por linha)",
                    placeholder="token1\ntoken2\ntoken3...",
                    custom_id="tokens",
                    style=disnake.TextInputStyle.paragraph,
                    required=True,
                    max_length=4000
                )
            ]
        )

    @commands.Cog.listener("on_modal_submit")
    async def on_boost_modal_submit(self, inter: disnake.ModalInteraction):
        if inter.custom_id == "Boost_AddStockModal":
            await self._process_add_stock(inter)

    async def _process_add_stock(self, inter: disnake.ModalInteraction):
        """Processa adição de tokens ao estoque"""
        mode = db.get_document("custom_mode").get("mode")
        
        if mode == "embed":
            await embed_message.wait(inter, send=True)
        else:
            await message.wait(inter, send=True)

        tokens_text = inter.text_values.get("tokens", "")
        new_tokens = [t.strip() for t in tokens_text.split("\n") if t.strip()]

        if not new_tokens:
            if mode == "embed":
                await embed_message.error(inter, "Nenhum token válido foi fornecido!", send=False)
            else:
                await message.error(inter, "Nenhum token válido foi fornecido!", send=False)
            return

        # Adicionar tokens ao estoque
        stock = self._get_stock()
        stock.extend(new_tokens)
        self._save_stock(stock)

        # Atualizar contadores
        boost_data = self._get_boost_data()
        boost_data["total_accounts"] = len(stock)
        self._save_boost_data(boost_data)

        if mode == "embed":
            await embed_message.success(
                inter,
                f"**{len(new_tokens)}** tokens adicionados ao estoque!\n"
                f"Total de contas: **{len(stock)}**",
                send=False
            )
        else:
            await message.success(
                inter,
                f"**{len(new_tokens)}** tokens adicionados ao estoque!\n"
                f"Total de contas: **{len(stock)}**",
                send=False
            )

    async def _show_stock_view(self, inter: disnake.MessageInteraction):
        """Mostra visualização do estoque"""
        mode = db.get_document("custom_mode").get("mode")

        stock = self._get_stock()

        if not stock:
            if mode == "embed":
                await embed_message.error(inter, "Nenhum token no estoque!", send=True)
            else:
                await message.error(inter, "Nenhum token no estoque!", send=True)
            return

        # Mostrar primeiros 10 tokens (parcialmente ocultos)
        preview_tokens = []
        for i, token in enumerate(stock[:10], 1):
            if len(token) > 20:
                hidden = token[:10] + "..." + token[-10:]
            else:
                hidden = token[:5] + "..." + token[-5:]
            preview_tokens.append(f"`{i}.` {hidden}")

        total = len(stock)
        remaining = total - 10 if total > 10 else 0

        description = "\n".join(preview_tokens)
        if remaining > 0:
            description += f"\n\n*E mais {remaining} tokens...*"

        if mode == "embed":
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")

            embed = disnake.Embed(
                title=f"{emoji.search} Estoque de Tokens",
                description=f"**Total:** {total} tokens\n\n{description}",
            )

            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                embed.color = primary_color

            components = [
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Limpar Estoque",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.wrong,
                        custom_id="Boost_ClearStock"
                    ),
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.back,
                        custom_id="Boost_BackToPanel"
                    )
                )
            ]

            await inter.response.send_message(embed=embed, components=components, ephemeral=True)
        else:
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")

            container_kwargs = {}
            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                container_kwargs["accent_colour"] = disnake.Colour(primary_color)

            container = disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.search}\n"
                    f"-# Estoque de Tokens\n\n"
                    f"**Total:** {total} tokens\n\n"
                    f"{description}"
                ),
                **container_kwargs
            )

            buttons = disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Limpar Estoque",
                    style=disnake.ButtonStyle.red,
                    emoji=emoji.wrong,
                    custom_id="Boost_ClearStock"
                ),
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Boost_BackToPanel"
                )
            )

            await inter.response.send_message(components=[container, buttons], ephemeral=True)

    async def _send_stock_file(self, inter: disnake.MessageInteraction):
        """Envia arquivo com todos os tokens"""
        mode = db.get_document("custom_mode").get("mode")

        stock = self._get_stock()

        if not stock:
            if mode == "embed":
                await embed_message.error(inter, "Nenhum token no estoque!", send=True)
            else:
                await message.error(inter, "Nenhum token no estoque!", send=True)
            return

        # Criar arquivo temporário
        import io
        file_content = "\n".join(stock)
        file = disnake.File(
            io.BytesIO(file_content.encode()),
            filename=f"tokens_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        if mode == "embed":
            await embed_message.success(
                inter,
                f"Arquivo com **{len(stock)}** tokens enviado!",
                send=True
            )
        else:
            await message.success(
                inter,
                f"Arquivo com **{len(stock)}** tokens enviado!",
                send=True
            )

        await inter.followup.send(file=file, ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def on_boost_action_button(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Boost_ClearStock":
            await self._confirm_clear_stock(inter)
        elif inter.component.custom_id == "Boost_BackToPanel":
            await self.display_boost_panel(inter)
        elif inter.component.custom_id == "Boost_ConfirmClear":
            await self._clear_stock(inter)
        elif inter.component.custom_id == "Boost_CancelClear":
            await self._show_stock_view(inter)
        elif inter.component.custom_id == "Boost_CreateGift":
            await self._show_create_gift_modal(inter)
        elif inter.component.custom_id == "Boost_ViewGifts":
            await self._view_gifts(inter)
        elif inter.component.custom_id == "Boost_ClearAllGifts":
            await self._clear_all_gifts(inter)
        elif inter.component.custom_id == "Boost_Instructions":
            await self._show_instructions(inter)
    
    async def _show_instructions(self, inter: disnake.MessageInteraction):
        """Mostra instruções de uso do sistema de boost"""
        mode = db.get_document("custom_mode").get("mode")
        
        if mode == "embed":
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")
            
            embed = disnake.Embed(
                title=f"{emoji.information} Instruções - system Boost",
                description="Aprenda a usar o sistema de boost completo",
            )
            
            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                embed.color = primary_color
            
            embed.add_field(
                name=f"{emoji.cardbox} Gerenciar Estoque",
                value=(
                    "**Adicionar Tokens:**\n"
                    "1. Clique em `Estoque` no painel\n"
                    "2. Clique em `Adicionar Estoque`\n"
                    "3. Cole os tokens (um por linha)\n\n"
                    "**Ver Estoque:**\n"
                    "• Visualize tokens parcialmente ocultos\n"
                    "• Baixe arquivo completo com todos os tokens\n"
                    "• Limpe o estoque quando necessário"
                ),
                inline=False
            )
            
            embed.add_field(
                name=f"{emoji.gift} Sistema de Gifts",
                value=(
                    "**Criar Gift:**\n"
                    "1. Clique em `Gerenciar Gifts`\n"
                    "2. Clique em `Criar Gift`\n"
                    "3. Digite quantidade de boosts (deve ser PAR)\n"
                    "4. Opcionalmente: quantidade de gifts\n"
                    "5. Compartilhe o link gerado!\n\n"
                    "**Importante:**\n"
                    "• Cada conta = 2 boosts\n"
                    "• Quantidade deve ser par (2, 4, 6, 8...)\n"
                    "• Verifica estoque automaticamente"
                ),
                inline=False
            )
            
            embed.add_field(
                name=f"{emoji.rocket} Comandos de Boost",
                value=(
                    "**Enviar Boosts:**\n"
                    "`/boost enviar <quantidade> <convite> [nome] [bio]`\n"
                    "• `quantidade`: Número de tokens a usar\n"
                    "• `convite`: Link do servidor\n"
                    "• `nome`: Nome personalizado (opcional)\n"
                    "• `bio`: Bio personalizada (opcional)\n\n"
                    "**Verificar Status:**\n"
                    "`/boost status <order_id>`\n"
                    "• Veja progresso da ordem\n"
                    "• Boosts bem-sucedidos e falhados\n"
                    "• Erros detalhados se houver"
                ),
                inline=False
            )
            
            embed.add_field(
                name=f"{emoji.link} Links Úteis",
                value=(
                    "**Token Checker:**\n"
                    "[Download](https://www.mediafire.com/file/8aal844sxuadqaw/Token_Checker.zip/file)\n\n"
                    "**Suporte:**\n"
                    "Entre em contato pelo Discord para ajuda"
                ),
                inline=False
            )
            
            await inter.response.send_message(embed=embed, ephemeral=True)
        else:
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")
            
            container_kwargs = {}
            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                container_kwargs["accent_colour"] = disnake.Colour(primary_color)
            
            container = disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.information}\n"
                    f"-# Instruções - system Boost\n\n"
                    f"## {emoji.cardbox} Gerenciar Estoque\n\n"
                    f"**Adicionar Tokens:**\n"
                    f"1. Clique em `Estoque` no painel\n"
                    f"2. Clique em `Adicionar Estoque`\n"
                    f"3. Cole os tokens (um por linha)\n\n"
                    f"**Ver Estoque:**\n"
                    f"• Visualize tokens parcialmente ocultos\n"
                    f"• Baixe arquivo completo\n"
                    f"• Limpe quando necessário\n\n"
                    f"## {emoji.gift} Sistema de Gifts\n\n"
                    f"**Criar Gift:**\n"
                    f"1. Clique em `Gerenciar Gifts`\n"
                    f"2. Clique em `Criar Gift`\n"
                    f"3. Digite quantidade de boosts (PAR)\n"
                    f"4. Compartilhe o link!\n\n"
                    f"**Importante:**\n"
                    f"• Cada conta = 2 boosts\n"
                    f"• Quantidade deve ser par\n\n"
                    f"## {emoji.rocket} Comandos\n\n"
                    f"**Enviar Boosts:**\n"
                    f"`/boost enviar <qtd> <convite>`\n\n"
                    f"**Verificar Status:**\n"
                    f"`/boost status <order_id>`"
                ),
                **container_kwargs
            )
            
            await inter.response.send_message(components=[container], ephemeral=True)
    
    async def _show_create_gift_modal(self, inter: disnake.MessageInteraction):
        """Mostra modal para criar gift"""
        from .gifts import CreateBoostGiftModal
        modal = CreateBoostGiftModal(bot=self.bot)
        await inter.response.send_modal(modal)
    
    async def _view_gifts(self, inter: disnake.MessageInteraction):
        """Mostra lista de gifts"""
        from .gifts import view_gifts
        await view_gifts(inter, self.bot)
    
    async def _clear_all_gifts(self, inter: disnake.MessageInteraction):
        """Limpa todos os gifts"""
        from .gifts import clear_all_gifts
        await clear_all_gifts(inter, self.bot)

    async def _confirm_clear_stock(self, inter: disnake.MessageInteraction):
        """Confirma limpeza do estoque"""
        mode = db.get_document("custom_mode").get("mode")
        
        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter, send=False)

        stock = self._get_stock()

        if mode == "embed":
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")

            embed = disnake.Embed(
                title=f"{emoji.warn} Confirmar Limpeza",
                description=f"Tem certeza que deseja limpar **{len(stock)}** tokens do estoque?\n\n**Esta ação não pode ser desfeita!**",
            )

            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                embed.color = primary_color

            components = [
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Confirmar",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.double_check,
                        custom_id="Boost_ConfirmClear"
                    ),
                    disnake.ui.Button(
                        label="Cancelar",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.wrong,
                        custom_id="Boost_CancelClear"
                    )
                )
            ]

            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")

            container_kwargs = {}
            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                container_kwargs["accent_colour"] = disnake.Colour(primary_color)

            container = disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.warn}\n"
                    f"-# Confirmar Limpeza\n\n"
                    f"Tem certeza que deseja limpar **{len(stock)}** tokens do estoque?\n\n"
                    f"**Esta ação não pode ser desfeita!**"
                ),
                **container_kwargs
            )

            buttons = disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Confirmar",
                    style=disnake.ButtonStyle.red,
                    emoji=emoji.double_check,
                    custom_id="Boost_ConfirmClear"
                ),
                disnake.ui.Button(
                    label="Cancelar",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.wrong,
                    custom_id="Boost_CancelClear"
                )
            )

            await inter.edit_original_message(content=None, components=[container, buttons])

    async def _clear_stock(self, inter: disnake.MessageInteraction):
        """Limpa o estoque de tokens"""
        mode = db.get_document("custom_mode").get("mode")
        
        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter, send=False)

        # Limpar estoque
        self._save_stock([])

        # Atualizar contadores
        boost_data = self._get_boost_data()
        boost_data["total_accounts"] = 0
        self._save_boost_data(boost_data)

        if mode == "embed":
            await embed_message.success(inter, "Estoque limpo com sucesso!", send=False)
        else:
            await message.success(inter, "Estoque limpo com sucesso!", send=False)

        # Voltar ao painel
        await self.display_boost_panel(inter)


def setup(bot: commands.Bot):
    bot.add_cog(BoostExtension(bot))
