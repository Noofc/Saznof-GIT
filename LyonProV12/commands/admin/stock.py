import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji


class StockPanel(commands.Cog):
    """Sistema de Aviso de Stock."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @staticmethod
    def _channel_text(channel_id):
        return f"<#{channel_id}>" if channel_id else "`Nao configurado`"
    
    @staticmethod
    def _role_text(role_id):
        if role_id == "everyone":
            return "@everyone"
        return f"<@&{role_id}>" if role_id else "`Nao configurado`"

    def display_stock_panel(self, inter: disnake.MessageInteraction):
        stock_config = db.get_document("stock_config") or {}
        enabled = stock_config.get("enabled", False)
        restock_channel_id = stock_config.get("restock_channel_id") or stock_config.get("logs_channel_id")
        mention_role_id = stock_config.get("mention_role_id", "everyone")
        status = "`Habilitado`" if enabled else "`Desabilitado`"
        status_dot = emoji.green if enabled else emoji.red
        author_name = getattr(inter.author, "display_name", inter.author.name)

        colors = db.get_document("custom_colors") or {}
        color_hex = colors.get("primary") or "#008cff"
        try:
            accent_colour = disnake.Colour(int(color_hex.replace("#", ""), 16))
        except Exception:
            accent_colour = disnake.Colour.blue()

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"## {emoji.cardbox} Alertas de Estoque"),
            disnake.ui.TextDisplay(
                f"Olá senhor(a) **{author_name}**, boa noite!\n"
                "Aqui você poderá configurar os **alertas de estoque** do servidor.\n\n"
                "Quando um produto acabar, o dono/equipe será avisado. Quando voltar, "
                "os clientes interessados serão notificados automaticamente."
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                f"{emoji.chart} **Status:** {status_dot} {status}\n"
                f"{emoji.wand} **Canal:** {self._channel_text(restock_channel_id)}\n"
                f"{emoji.speech} **Cargo para Marcar:** {self._role_text(mention_role_id)}"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Ativo" if enabled else "Inativo",
                    style=disnake.ButtonStyle.success if enabled else disnake.ButtonStyle.danger,
                    emoji=emoji.power,
                    custom_id="Stock_Toggle",
                ),
                disnake.ui.Button(
                    label="Selecionar Canal",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.textc,
                    custom_id="Stock_ConfigCanal",
                ),
                disnake.ui.Button(
                    label="Cargo para Marcar",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.role,
                    custom_id="Stock_ConfigCargo",
                ),
                disnake.ui.Button(
                    label="Prévia",
                    style=disnake.ButtonStyle.blurple,
                    emoji=emoji.search,
                    custom_id="Stock_Preview",
                ),
            ),
            accent_colour=accent_colour,
        )

        return [container]

    def _legacy_low_stock_rows(self, enabled: bool):
        return [
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Limite", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "edit", None), custom_id="Stock_ConfigLimite"),
                    disnake.ui.Button(
                        label="Desativar" if enabled else "Ativar",
                        style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "power", None),
                        custom_id="Stock_Toggle",
                    ),
                    disnake.ui.Button(label="Verificar", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "search", None), custom_id="Stock_Verificar"),
                    disnake.ui.Button(label="Canal Logs", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "textc", None), custom_id="Stock_ConfigCanal"),
                )
            ]

    @staticmethod
    def _preview_buy_url(product: dict) -> str | None:
        messages = product.get("messages") if isinstance(product, dict) else None
        if not isinstance(messages, list) or not messages:
            return None

        latest_message = max(messages, key=lambda item: item.get("created_at", 0) if isinstance(item, dict) else 0)
        if not isinstance(latest_message, dict):
            return None

        guild_id = latest_message.get("guild_id")
        channel_id = latest_message.get("channel_id")
        message_id = latest_message.get("message_id")
        if guild_id and channel_id and message_id:
            return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        return None

    @staticmethod
    def _restock_preview_data() -> dict:
        from modules.loja.cart.stock_manager import StockManager

        products = db.get_document("loja_products") or {}
        if isinstance(products, dict):
            for product_id, product in products.items():
                if not isinstance(product, dict):
                    continue

                campos = product.get("campos") or {}
                if not isinstance(campos, dict):
                    continue

                for campo_id, campo in campos.items():
                    if not isinstance(campo, dict):
                        continue

                    try:
                        current_stock = StockManager.get_available_stock(str(product_id), str(campo_id))
                    except Exception:
                        current_stock = 10
                    if current_stock == 999999:
                        current_stock = 100

                    added_count = 5
                    return {
                        "product_name": str(product.get("name") or product_id or "Produto de exemplo"),
                        "campo_name": str(campo.get("name") or campo_id or "Campo principal"),
                        "added_count": added_count,
                        "total": max(0, int(current_stock or 0)) + added_count,
                        "buy_url": StockPanel._preview_buy_url(product),
                    }

        return {
            "product_name": "Produto de exemplo",
            "campo_name": "Campo principal",
            "added_count": 5,
            "total": 15,
            "buy_url": None,
        }

    def _preview_restock_components(self) -> list:
        from modules.loja.cart.stock_manager import StockManager

        stock_config = db.get_document("stock_config") or {}
        preview_data = self._restock_preview_data()
        return StockManager._build_restock_components(
            product_name=preview_data["product_name"],
            campo_name=preview_data["campo_name"],
            added_count=preview_data["added_count"],
            total=preview_data["total"],
            buy_url=preview_data["buy_url"],
            mention_text=StockManager._format_restock_mention(stock_config.get("mention_role_id", "everyone")),
            preview=True,
        )

    async def _refresh_panel(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_stock_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @commands.Cog.listener("on_message_interaction")
    async def Stock_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Stock"):
            return

        if custom_id == "Stock_Preview_Buy":
            await inter.response.send_message(
                f"{emoji.information} Este botão é apenas da prévia. Na mensagem publicada ele abre a compra real do produto.",
                ephemeral=True,
            )
            return

        if custom_id == "Stock_ConfigLimite":
            class StockLimitModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Limite de stock",
                        custom_id="Stock_LimitModal",
                        components=[
                            disnake.ui.TextInput(label="Limite minimo", custom_id="min_stock", max_length=4, placeholder="1"),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    try:
                        min_stock = max(0, int(values.get("min_stock", "1").strip()))
                    except ValueError:
                        await modal_inter.response.send_message(f"{emoji.wrong} Informe um numero valido.", ephemeral=True)
                        return
                    stock_config = db.get_document("stock_config") or {}
                    stock_config["min_stock"] = min_stock
                    db.save_document("stock_config", stock_config)
                    await modal_inter.response.send_message(f"{emoji.correct} Limite minimo salvo como `{min_stock}`.", ephemeral=True)

            await inter.response.send_modal(StockLimitModal())
            return

        if custom_id == "Stock_Toggle":
            await inter.response.defer(ephemeral=True)
            stock_config = db.get_document("stock_config") or {}
            stock_config["enabled"] = not stock_config.get("enabled", False)
            db.save_document("stock_config", stock_config)
            await self._refresh_panel(inter)
            status = "ativado" if stock_config["enabled"] else "desativado"
            await inter.followup.send(f"{emoji.correct} Aviso de stock {status}.", ephemeral=True)
            return

        if custom_id == "Stock_ConfigCanal":
            await inter.response.send_message(
                "Selecione o canal para receber notificações de reestoque.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Canal de reestoque",
                            custom_id="Stock_SelectCanal",
                            channel_types=[disnake.ChannelType.text],
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Stock_SelectCanal":
            stock_config = db.get_document("stock_config") or {}
            stock_config["restock_channel_id"] = int(inter.values[0])
            stock_config["logs_channel_id"] = int(inter.values[0])
            db.save_document("stock_config", stock_config)
            await inter.response.send_message(f"{emoji.correct} Canal de reestoque salvo em <#{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "Stock_ConfigCargo":
            await inter.response.send_message(
                "Selecione o cargo que será marcado nas notificações de reestoque.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.RoleSelect(
                            placeholder="Cargo para marcar",
                            custom_id="Stock_SelectCargo",
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Stock_Preview":
            await inter.response.send_message(
                components=self._preview_restock_components(),
                flags=disnake.MessageFlags(is_components_v2=True),
                ephemeral=True,
                allowed_mentions=disnake.AllowedMentions.none(),
            )
            return

        if custom_id == "Stock_SelectCargo":
            stock_config = db.get_document("stock_config") or {}
            stock_config["mention_role_id"] = int(inter.values[0])
            db.save_document("stock_config", stock_config)
            await inter.response.send_message(f"{emoji.correct} Cargo para marcar salvo em <@&{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "Stock_Verificar":
            stock_config = db.get_document("stock_config") or {}
            min_stock = int(stock_config.get("min_stock", 1) or 1)
            low_items = self._scan_low_stock(min_stock)
            stock_config["last_check"] = disnake.utils.utcnow().strftime("%d/%m/%Y %H:%M:%S")
            stock_config["last_low_count"] = len(low_items)
            db.save_document("stock_config", stock_config)

            if low_items:
                details = "\n".join(
                    f"- **{item['product']}** / `{item['field']}`: `{item['stock']}`"
                    for item in low_items[:15]
                )
                content = f"{emoji.warn} **Produtos com stock baixo ({len(low_items)}):**\n{details}"
            else:
                content = f"{emoji.correct} Nenhum produto abaixo do limite `{min_stock}`."

            logs_channel_id = stock_config.get("logs_channel_id")
            logs_channel = inter.guild.get_channel(int(logs_channel_id)) if inter.guild and logs_channel_id else None
            if low_items and isinstance(logs_channel, disnake.TextChannel):
                try:
                    await logs_channel.send(content)
                except disnake.HTTPException:
                    pass

            await inter.response.send_message(
                content,
                ephemeral=True,
            )

    @staticmethod
    def _scan_low_stock(min_stock: int) -> list[dict]:
        from modules.loja.cart.stock_manager import StockManager

        products = db.get_document("loja_products") or {}
        low_items = []
        for product_id, product in products.items():
            product_name = product.get("name", product_id)
            for field_id, field in (product.get("campos") or {}).items():
                if field.get("infinite_stock", {}).get("enabled", False):
                    continue

                stock_count = StockManager.get_available_stock(product_id, field_id)
                if stock_count <= min_stock:
                    low_items.append(
                        {
                            "product": product_name,
                            "field": field.get("name", field_id),
                            "stock": stock_count,
                        }
                    )
        return low_items


def setup(bot):
    bot.add_cog(StockPanel(bot))
