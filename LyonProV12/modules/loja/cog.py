from disnake.ext import commands
import disnake

from functions.emoji import emoji
from functions.message import message, embed_message
from functions.database import database as db
from modules.loja.cart.purchase_manager import PurchaseManager

class Loja(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def panel(self, inter: disnake.MessageInteraction):
        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            return self._panel_embed(inter)
        return self._panel_components(inter)

    def _panel_components(self, inter: disnake.MessageInteraction) -> dict:
        color_data = db.get_document("custom_colors")
        primary_color_hex = color_data.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

        options = [
            disnake.SelectOption(label="Gerenciar Produtos", value="produtos", emoji=emoji.cardbox, description="Crie, Configure e Edite seus produtos."),
            disnake.SelectOption(label="Personalizar Loja", value="personalizar", emoji=emoji.edit, description="Personalize sua loja com criatividade."),
            disnake.SelectOption(label="Preferências", value="preferencias", emoji=emoji.settings2, description="Configure preferências do seu sistema de loja."),
            #disnake.SelectOption(label="Vip (Em breve)", value="vip", emoji=emoji.fire, description="Opção em desenvolvimento final"),
            disnake.SelectOption(label="Configurar Clientes", value="clientes", emoji=emoji.members, description="Configure o sistema de clientes e condecorações"),
            disnake.SelectOption(label="Gerenciar Gifts", value="gifts", emoji=emoji.gift2, description="Crie e gerencie vouchers de produtos para resgate."),
            disnake.SelectOption(label="Sistema de Saldo", value="saldo", emoji=emoji.wallet, description="Configure o sistema de saldo para sua loja."),
            disnake.SelectOption(label="Cashback", value="cashback", emoji=emoji.bank, description="Configure o sistema de cashback para sua loja."),
            disnake.SelectOption(label="LyonCloud", value="systemcloud", emoji=emoji.cloud, description="Venda impulsos de extensoes e membros do LyonCloud."),
            # disnake.SelectOption(label="Afiliados (Em breve)", value="afiliados", emoji=emoji.dollar, description="Opção em desenvolvimento final"),
            # disnake.SelectOption(label="Lyon Marketplace (Em breve)", value="Lyon_market", emoji=emoji.basket, description="Opção em desenvolvimento final"),
        ]

        return {"components": [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > **Loja**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(f"Configure a sua loja selecionando uma seção abaixo.\nPara configurar as formas de pagamento, acesse as configurações."),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Loja_Select",
                        placeholder="Selecione uma seção para configurar",
                        options=options,
                    )
                ),
                **container_kwargs
            ),
        ]}

    def _panel_embed(self, inter: disnake.MessageInteraction) -> dict:
        color_data = db.get_document("custom_colors")
        primary_color_hex = color_data.get("primary")

        embed_kwargs = {}
        if primary_color_hex:
            embed_kwargs["color"] = int(primary_color_hex.replace("#", ""), 16)

        embed = disnake.Embed(
            # title=f"Configurar Loja",
            description=f"-# Painel > **Configurar Loja**\n\nConfigure a sua loja selecionando uma seção abaixo.\nPara configurar as formas de pagamento, acesse as configurações.",
            **embed_kwargs
        )

        options = [
            disnake.SelectOption(label="Gerenciar Produtos", value="produtos", emoji=emoji.cardbox, description="Crie, Configure e Edite seus produtos."),
            disnake.SelectOption(label="Personalizar Loja", value="personalizar", emoji=emoji.edit, description="Personalize sua loja com criatividade."),
            disnake.SelectOption(label="Preferências", value="preferencias", emoji=emoji.settings2, description="Configure preferências do seu sistema de loja."),
            #disnake.SelectOption(label="Vip (Em breve)", value="vip", emoji=emoji.fire, description="Opção em desenvolvimento final"),
            disnake.SelectOption(label="Configurar Clientes", value="clientes", emoji=emoji.members, description="Configure o sistema de clientes e condecorações"),
            disnake.SelectOption(label="Gerenciar Gifts", value="gifts", emoji=emoji.gift2, description="Crie e gerencie vouchers de produtos para resgate."),
            disnake.SelectOption(label="Sistema de Saldo", value="saldo", emoji=emoji.wallet, description="Configure o sistema de saldo para sua loja."),
            disnake.SelectOption(label="Cashback", value="cashback", emoji=emoji.bank, description="Configure o sistema de cashback para sua loja."),
            disnake.SelectOption(label="LyonCloud", value="systemcloud", emoji=emoji.cloud, description="Venda impulsos de extensoes e membros do LyonCloud."),
            # disnake.SelectOption(label="Afiliados (Em breve)", value="afiliados", emoji=emoji.dollar, description="Opção em desenvolvimento final"),
            # disnake.SelectOption(label="Lyon Marketplace (Em breve)", value="Lyon_market", emoji=emoji.basket, description="Opção em desenvolvimento final"),
        ]

        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Loja_Select",
                    placeholder="Selecione uma seção para configurar",
                    options=options,
                )
            ),
        ]
        return {"embed": embed, "components": components}

    @commands.slash_command(name="buscar_pedido", description="Buscar detalhes de um pedido por ID (Apenas Administradores)")
    @commands.has_permissions(administrator=True)
    async def buscar_pedido(
        self,
        inter: disnake.ApplicationCommandInteraction,
        pedido_id: str = commands.Param(description="ID do pedido para buscar")
    ):
        """Busca os detalhes de um pedido específico por ID"""
        await inter.response.defer(ephemeral=True)

        try:
            # Buscar pedido
            purchases_found = PurchaseManager.get_purchases_by_reference(pedido_id)
            purchase = purchases_found[0] if purchases_found else None

            if not purchase:
                await inter.followup.send(
                    f"{emoji.wrong} Pedido com ID `{pedido_id}` não encontrado!",
                    ephemeral=True
                )
                return

            # Formatar informações do pedido
            purchase_id = purchase.get("order_id") or purchase.get("metadata", {}).get("order_id") or purchase.get("purchase_id", "N/A")
            timestamp = purchase.get("timestamp", 0)
            user_id = purchase.get("user_id")

            # Encontrar o usuário que fez a compra
            # Informações do produto
            product_info = purchase.get("product", {})
            product_name = product_info.get("name", "N/A")
            product_id = product_info.get("id", "N/A")

            # Informações do campo
            field_info = purchase.get("field", {})
            field_name = field_info.get("name", "N/A")
            order_items_text = "\n".join(
                f"- **{p.get('product', {}).get('name', 'Produto')}** | {p.get('field', {}).get('name', 'Campo')} x{p.get('quantity', 1)}"
                for p in purchases_found[:8]
            ) or f"**{product_name}**\nCampo: {field_name}"

            # Informações de preço
            pricing = purchase.get("pricing", {})

            def _num(value, default=0.0):
                try:
                    return float(value if value is not None else default)
                except (TypeError, ValueError):
                    return default

            matched_purchases = purchases_found or [purchase]
            quantity = sum(max(1, int(_num(p.get("quantity", 1), 1))) for p in matched_purchases)
            unit_price = _num(pricing.get("unit_price"))
            total_price = sum(_num((p.get("pricing") or {}).get("total_price")) for p in matched_purchases)
            discount = sum(_num((p.get("pricing") or {}).get("discount_amount")) for p in matched_purchases)
            final_price = sum(_num((p.get("pricing") or {}).get("final_price")) for p in matched_purchases)

            if not total_price:
                total_price = _num(pricing.get("total_price"))
            if not final_price:
                final_price = _num(pricing.get("final_price"))

            # Informações de pagamento
            payment = purchase.get("payment", {})
            payment_method = payment.get("method", "N/A")
            coupon = payment.get("coupon_code", "Nenhum")

            # Formatar data
            from datetime import datetime
            dt = datetime.fromtimestamp(timestamp)

            mode = db.get_document("custom_mode").get("mode", "embed")

            if mode == "embed":
                embed = disnake.Embed(
                    title=f"🔍 Detalhes do Pedido #{purchase_id}",
                    color=disnake.Color.blue(),
                    timestamp=dt
                )

                embed.add_field(
                    name="👤 Cliente",
                    value=f"ID: `{user_id}`" if user_id else "N/A",
                    inline=True
                )

                embed.add_field(
                    name="📦 Produto",
                    value=order_items_text[:1024],
                    inline=True
                )

                embed.add_field(
                    name="🔢 Quantidade",
                    value=str(quantity),
                    inline=True
                )

                embed.add_field(
                    name="💰 Valores",
                    value=(
                        f"Unitário: R$ {unit_price:.2f}\n"
                        f"Total: R$ {total_price:.2f}\n"
                        f"Desconto: R$ {discount:.2f}\n"
                        f"**Final: R$ {final_price:.2f}**"
                    ),
                    inline=True
                )

                embed.add_field(
                    name="💳 Pagamento",
                    value=f"Método: {payment_method}\nCupom: {coupon}",
                    inline=True
                )

                embed.add_field(
                    name="📅 Data",
                    value=dt.strftime("%d/%m/%Y %H:%M:%S"),
                    inline=True
                )

                embed.set_footer(text=f"Pedido ID: {purchase_id}")

                await inter.followup.send(embed=embed, ephemeral=True)

            else:
                # Modo Container
                color_data = db.get_document("custom_colors")
                primary_color_hex = color_data.get("primary")
                container_kwargs = {}
                if primary_color_hex:
                    container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

                components = [
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(f"# 🔍 Detalhes do Pedido #{purchase_id}"),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(f"## 👤 Cliente\n-# ID: `{user_id}`" if user_id else "-# N/A"),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(
                            f"## 📦 Produto\n"
                            f"-# {order_items_text}"
                        ),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(
                            f"## 💰 Valores\n"
                            f"-# Unitário: R$ {unit_price:.2f}\n"
                            f"-# Total: R$ {total_price:.2f}\n"
                            f"-# Desconto: R$ {discount:.2f}\n"
                            f"-# **Final: R$ {final_price:.2f}**"
                        ),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(
                            f"## 💳 Pagamento\n"
                            f"-# Método: {payment_method}\n"
                            f"-# Cupom: {coupon}"
                        ),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(f"## 📅 Data\n-# {dt.strftime('%d/%m/%Y %H:%M:%S')}"),
                        **container_kwargs
                    )
                ]

                await inter.followup.send(
                    components=components,
                    flags=disnake.MessageFlags(is_components_v2=True),
                    ephemeral=True
                )

        except Exception as e:
            await inter.followup.send(
                f"{emoji.wrong} Erro ao buscar pedido: {e}",
                ephemeral=True
            )

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Loja_Panel":
            mode = db.get_document("custom_mode").get("mode")
            msg_handler = embed_message if mode == "embed" else message
            await msg_handler.wait(inter, send=False)

            panel_data = self.panel(inter)
            if "embed" in panel_data:
                await inter.edit_original_message(content=None, **panel_data)
            else:
                await inter.edit_original_message(**panel_data, flags=disnake.MessageFlags(is_components_v2=True))

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Loja_Select":
            choice = inter.values[0]

            # Itens agendados para uso
            coming_soon = {
                "vip", "afiliados", "Lyon_market"
            }

            if choice in coming_soon:
                await inter.response.send_message(
                    "Essa funcionalidade será implementada em breve em próximas atualizações.",
                    ephemeral=True
                )
                return

            mode = db.get_document("custom_mode").get("mode")
            msg_handler = embed_message if mode == "embed" else message
            await msg_handler.wait(inter, send=False)

            if choice == "produtos":
                from .products.cog import GerenciarProdutos
                panel_data = GerenciarProdutos(self.bot).panel(inter)
            elif choice == "personalizar":
                from .personalization.cog import PersonalizarLoja
                panel_data = PersonalizarLoja.panel(inter)
            elif choice == "preferencias":
                from .preferences.cog import PreferenciasLoja
                panel_data = PreferenciasLoja.panel(inter)
            elif choice == "clientes":
                from .clientes.cog import ClientesLyon
                clientes_system = ClientesLyon(self.bot)
                panel_data = clientes_system.panel_clientes(inter)
            elif choice == "gifts":
                from .gifts.cog import GiftLyon
                gift_system = GiftLyon(self.bot)
                await gift_system.display_gifts_panel(inter)
                return
            elif choice == "saldo":
                from .saldo.cog import SaldoLyon
                saldo_system = SaldoLyon(self.bot)
                panel_data = saldo_system.panel(inter)
            elif choice == "cashback":
                from .cashback.cog import CashbackLyon
                cashback_system = CashbackLyon(self.bot)
                panel_data = cashback_system.panel(inter)
            elif choice == "systemcloud":
                from .cloud_sales import CloudSales
                panel_data = CloudSales.panel(inter)
            else:
                panel_data = self.panel(inter)

            if isinstance(panel_data, tuple):
                embed, components = panel_data
                await inter.edit_original_message(content=None, embed=embed, components=components)
            elif "embed" in panel_data:
                await inter.edit_original_message(content=None, **panel_data)
            else:
                await inter.edit_original_message(**panel_data, flags=disnake.MessageFlags(is_components_v2=True))

def setup(bot: commands.Bot):
    bot.add_cog(Loja(bot))
