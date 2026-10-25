from disnake.ext import commands
import disnake

from functions.emoji import emoji
from functions.message import message, embed_message
from functions.database import database as db
from functions.utils import utils
from functions.text_utils import wrap_text

class ConfigurarProduto(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _format_price_brl(value: float) -> str:
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _build_legacy_embed(product: dict, guild: disnake.Guild, formatted_desc: bool = True) -> disnake.Embed:
        name = product.get("name", "Produto")
        info = product.get("info") or {}
        desc = info.get("description") or ""
        hex_color = info.get("hex_color")
        banner = info.get("banner")
        campos = product.get("campos") or {}
        
        # Obter preferências de exibição (com valores padrão para produtos antigos)
        display_prefs = info.get("display_preferences", {})
        if not display_prefs:
            # Inicializar preferências padrão se não existirem
            display_prefs = {
                "show_sales": True,
                "show_options": True,
                "show_stock": True
            }
            info["display_preferences"] = display_prefs
        show_sales = display_prefs.get("show_sales", True)
        show_options = display_prefs.get("show_options", True)
        
        prices = [campo.get("price", 0) for campo in campos.values()]
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0
        if min_price == max_price:
            price_text = ConfigurarProduto._format_price_brl(min_price)
        else:
            price_text = f"{ConfigurarProduto._format_price_brl(min_price)} - {ConfigurarProduto._format_price_brl(max_price)}"

        embed_kwargs = {}
        if hex_color:
            try:
                embed_kwargs["color"] = int(hex_color.replace("#", ""), 16)
            except:
                pass

        # Aplicar quebra de linha se formatada
        if formatted_desc and desc:
            desc = wrap_text(desc, max_line_length=50)

        embed = disnake.Embed(title=name, description=desc if desc else None, **embed_kwargs)
        embed.add_field(name=f"{emoji.dollar} Preço", value=f"`{price_text}`", inline=True)
        
        # Adicionar opções primeiro (se habilitado)
        if show_options:
            options_count = len(campos)
            embed.add_field(
                name=f"{emoji.information} Opções",
                value=f"`{options_count} disponível`" if options_count == 1 else f"`{options_count} disponíveis`",
                inline=True,
            )
        
        # Adicionar vendas depois (se habilitado)
        if show_sales:
            purchases_count = len(info.get("purchasesIds", []))
            if purchases_count > 0:
                embed.add_field(
                    name=f"{emoji.dollar} Vendas",
                    value=f"`{purchases_count} {'venda realizada' if purchases_count == 1 else 'vendas realizadas'}`",
                    inline=True
                )
        
        if banner:
            embed.set_image(url=banner)
        icon_url = guild.icon.url if guild.icon else None
        embed.set_footer(text=guild.name, icon_url=icon_url)
        embed.timestamp = disnake.utils.utcnow()
        return embed

    @staticmethod
    def _build_container_components(product: dict, image_inside: bool, product_id: str, formatted_desc: bool = True) -> list:
        info = product.get("info") or {}
        name = product.get("name", "Produto")
        desc = info.get("description") or ""
        hex_color = info.get("hex_color")
        banner = info.get("banner")
        campos = product.get("campos") or {}
        
        # Obter preferências de exibição (com valores padrão para produtos antigos)
        display_prefs = info.get("display_preferences", {})
        if not display_prefs:
            # Inicializar preferências padrão se não existirem
            display_prefs = {
                "show_sales": True,
                "show_options": True,
                "show_stock": True
            }
            info["display_preferences"] = display_prefs
        show_sales = display_prefs.get("show_sales", True)
        show_options = display_prefs.get("show_options", True)
        
        # Obter configuração do botão
        button_config = info.get("buy_button", {})
        if not button_config:
            # Inicializar botão padrão se não existir
            button_config = {
                "label": "Comprar",
                "emoji": emoji.cart
            }
            info["buy_button"] = button_config
        button_label = button_config.get("label", "Comprar")
        button_emoji_str = button_config.get("emoji", emoji.cart)

        prices = [campo.get("price", 0) for campo in campos.values()]
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0
        if min_price == max_price:
            price_text = ConfigurarProduto._format_price_brl(min_price)
        else:
            price_text = f"{ConfigurarProduto._format_price_brl(min_price)} - {ConfigurarProduto._format_price_brl(max_price)}"

        components = []
        container_kwargs = {}
        if hex_color:
            try:
                container_kwargs["accent_colour"] = disnake.Colour(int(hex_color.replace("#", ""), 16))
            except:
                pass

        title_text = f"**{name}**"
        # Sempre adicionar descrição se existir
        if desc:
            if formatted_desc:
                # Quebrar linha automaticamente
                desc = wrap_text(desc, max_line_length=50)
            title_text += f"\n{desc}"

        # Construir informações de preço
        price_info_parts = [f"**{price_text}**"]
        
        # Adicionar opções primeiro (se habilitado)
        if show_options:
            price_info_parts.append(f"-# {len(campos)} {'opção' if len(campos) == 1 else 'opções'} {'disponível' if len(campos) == 1 else 'disponíveis'}")
        
        # Adicionar vendas depois (se habilitado)
        if show_sales:
            purchases_count = len(info.get("purchasesIds", []))
            if purchases_count > 0:
                price_info_parts.append(f"-# {purchases_count} {'venda realizada' if purchases_count == 1 else 'vendas realizadas'}")
        
        price_info_text = "\n".join(price_info_parts)

        inner_items = []
        if image_inside and banner:
            inner_items.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(media=banner)))
        inner_items.append(disnake.ui.TextDisplay(title_text))
        
        inner_items.append(disnake.ui.Separator())
        
        # Criar botão com emoji customizado
        btn_emoji = button_emoji_str
        if isinstance(btn_emoji, str) and btn_emoji.startswith("<"):
            try:
                btn_emoji = disnake.PartialEmoji.from_str(btn_emoji)
            except:
                btn_emoji = emoji.cart
        elif not btn_emoji:
            btn_emoji = emoji.cart
        
        # Criar Section com texto de preço
        inner_items.append(
            disnake.ui.Section(
                disnake.ui.TextDisplay(price_info_text),
                accessory=disnake.ui.Button(
                    label=button_label,
                    emoji=btn_emoji,
                    style=disnake.ButtonStyle.grey,
                    custom_id=f"buy_product:{product_id}"
                )
            )
        )
        

        container = disnake.ui.Container(*inner_items, **container_kwargs)
        if (not image_inside) and banner:
            components.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(media=banner)))
        components.append(container)
        return components

    @staticmethod
    def panel(inter: disnake.MessageInteraction, product_id: str):
        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            return ConfigurarProduto._panel_embed(inter, product_id)
        return ConfigurarProduto._panel_components(inter, product_id)

    @staticmethod
    def _panel_components(inter: disnake.MessageInteraction, product_id: str) -> dict:
        products = db.get_document("loja_products")
        product = products.get(product_id)
        
        # Garantir que info existe
        info = product.get('info', {})

        raw_desc = info.get('description')
        if raw_desc:
            # Truncar descrição se for muito grande (máximo 800 caracteres para segurança)
            if len(raw_desc) > 800:
                raw_desc = raw_desc[:800] + "..."
            wrapped_desc = utils.wrap_text_hyphenate(raw_desc, max_width=40)
            # Garantir que o bloco de código não exceda o limite
            if len(wrapped_desc) > 3500:
                wrapped_desc = wrapped_desc[:3500] + "..."
            description = f"\n```{wrapped_desc}```"
        else:
            description = "`Não configurada`"
        color_data = db.get_document("custom_colors")
        primary_color_hex = color_data.get("primary")

        delivery_type = info.get('delivery_type')
        delivery_type_str = "Manual" if delivery_type == "manual" else "Automático"

        container_kwargs = {}
        hex_color = info.get('hex_color')
        if hex_color:
            container_kwargs["accent_colour"] = disnake.Colour(int(hex_color.replace("#", ""), 16))
        else:
            if primary_color_hex:
                container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

        # Construir textos separados para evitar limite de 4000 caracteres
        product_name = product.get('name', 'Sem nome')
        # Limitar nome do produto para evitar problemas
        if len(product_name) > 100:
            product_name = product_name[:100] + "..."
        
        info_text = f"""-# Nome: `{product_name}`
-# Tipo de entrega: `{delivery_type_str}`
-# Banner: `{"Configurado" if info.get('banner') else "Não configurado"}`"""
        
        management_text = f"""-# Criado em: {utils.format_timestamp(info.get('created_at'))}
-# Última edição: {utils.format_timestamp(info.get('updated_at'))}
-# Compras: `{len(info.get('purchasesIds', []))}` | Faturado: `{utils.format_price_brl(info.get('total_paid', 0))}`
-# Campos: `{len(product.get('campos', {}))}` | Categorias: `{len(product.get('categorias', {}))}` | Cupons: `{len(product.get('cupons', {}))}`"""
        
        # Construir TextDisplays com validação de tamanho
        header_text = f"# {emoji.lyon}\n-# Painel > Loja > Produto > **{product_name[:50]}**"
        info_display = f"**Informações do produto**\n{info_text}"
        desc_display = f"-# Descrição: {description}"
        
        # Garantir que nenhum TextDisplay exceda 3900 caracteres (margem de segurança)
        if len(header_text) > 3900:
            header_text = header_text[:3900]
        if len(info_display) > 3900:
            info_display = info_display[:3900]
        if len(desc_display) > 3900:
            desc_display = desc_display[:3900]
        if len(management_text) > 3900:
            management_text = management_text[:3900]
        
        return {"components": [
            disnake.ui.Container(
                disnake.ui.TextDisplay(header_text),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(info_display),
                disnake.ui.TextDisplay(desc_display),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(f"**Gerenciamento**\n{management_text}"),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Editar", emoji=emoji.edit, custom_id=f"Loja_EditarProduto:{product_id}"),
                    disnake.ui.Button(label="Gerenciar Campos ", emoji=emoji.commands, custom_id=f"Loja_CamposProduto:{product_id}"),
                    disnake.ui.Button(label="Cupons", emoji=emoji.coupon, custom_id=f"Loja_CuponsProduto:{product_id}"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Publicar mensagem", emoji=emoji.arrow, custom_id=f"Loja_PublicarProduto:{product_id}"),
                    disnake.ui.Button(label="Sincronizar", emoji=emoji.reload, custom_id=f"Loja_AtualizarProduto:{product_id}"),
                    disnake.ui.Button(label="Apagar", emoji=emoji.delete, custom_id=f"Loja_ApagarProduto:{product_id}"),
                ),
                **container_kwargs
            ),
        ]}

    @staticmethod
    def _panel_embed(inter: disnake.MessageInteraction, product_id: str) -> dict:
        products = db.get_document("loja_products")
        product = products.get(product_id)
        
        # Garantir que info existe
        info = product.get('info', {})
        
        color_data = db.get_document("custom_colors")
        primary_color_hex = color_data.get("primary")
        embed_kwargs = {}
        hex_color = info.get('hex_color')
        if hex_color:
            embed_kwargs["color"] = int(hex_color.replace("#", ""), 16)
        elif primary_color_hex:
            embed_kwargs["color"] = int(primary_color_hex.replace("#", ""), 16)

        # Descrição do produto (quebra em 40 colunas com hifenização)
        raw_desc = info.get('description')
        if raw_desc:
            # Truncar descrição se for muito grande (máximo 800 caracteres para segurança)
            if len(raw_desc) > 800:
                raw_desc = raw_desc[:800] + "..."
            wrapped_desc = utils.wrap_text_hyphenate(raw_desc, max_width=40)
            # Garantir que o bloco de código não exceda o limite
            if len(wrapped_desc) > 1500:
                wrapped_desc = wrapped_desc[:1500] + "..."
            description_block = f"\n```{wrapped_desc}```"
        else:
            description_block = "`Não configurada`"

        delivery_type = info.get('delivery_type')
        delivery_type_str = "Manual" if delivery_type == "manual" else "Automático"

        compras_qtd = len(info.get('purchasesIds', []))
        total_faturado = utils.format_price_brl(info.get('total_paid', 0))
        campos_qtd = len(product.get('campos', {})) if product.get('campos') else 0
        categorias_qtd = len(product.get('categorias', {})) if product.get('categorias') else 0
        cupons_qtd = len(product.get('cupons', {})) if product.get('cupons') else 0

        embed_description = (
            f"-# Painel > Loja > Produto > **{product.get('name')}**\n\n"
            f"**Informações do produto**\n"
            f"-# Nome: `{product.get('name')}`\n"
            f"-# Tipo de entrega: `{delivery_type_str}`\n"
            f"-# Descrição: {description_block}\n\n"
            f"**Gerenciamento do produto**\n"
            f"-# Criado em: {utils.format_timestamp(info.get('created_at'))}\n"
            f"-# Última edição: {utils.format_timestamp(info.get('updated_at'))}\n"
            f"-# Compras realizadas: `{compras_qtd}` | Total faturado: `{total_faturado}`\n"
            f"-# Campos: `{campos_qtd}` | Categorias: `{categorias_qtd}` | Cupons: `{cupons_qtd}`"
        )

        embed = disnake.Embed(description=embed_description, **embed_kwargs)

        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Editar", emoji=emoji.edit, custom_id=f"Loja_EditarProduto:{product_id}"),
                disnake.ui.Button(label="Gerenciar Campos ", emoji=emoji.commands, custom_id=f"Loja_CamposProduto:{product_id}"),
                disnake.ui.Button(label="Cupons", emoji=emoji.coupon, custom_id=f"Loja_CuponsProduto:{product_id}"),
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Publicar mensagem", emoji=emoji.arrow, custom_id=f"Loja_PublicarProduto:{product_id}"),
                disnake.ui.Button(label="Atualizar", emoji=emoji.reload, custom_id=f"Loja_AtualizarProduto:{product_id}"),
                disnake.ui.Button(label="Apagar", emoji=emoji.delete, custom_id=f"Loja_ApagarProduto:{product_id}"),
            ),
        ]
        return {"embed": embed, "components": components}

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id.startswith("Loja_ConfigurarProduto"):
            _, product_id = inter.component.custom_id.split(":", 1)
            mode = db.get_document("custom_mode").get("mode")
            panel_data = ConfigurarProduto.panel(inter, product_id)
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                await inter.edit_original_message(content=None, **panel_data)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(**panel_data)
        elif inter.component.custom_id.startswith("Loja_AtualizarProduto:"):
            _, product_id = inter.component.custom_id.split(":", 1)
            await inter.response.defer(ephemeral=True)

            products = db.get_document("loja_products")
            product = products.get(product_id)
            if not product:
                await inter.followup.send(
                    content=f"{emoji.wrong} Produto não encontrado.",
                    ephemeral=True
                )
                return

            total = 0
            updated = 0
            removed = 0
            skipped = 0

            original_messages = product.get("messages") or []
            new_messages = []

            for m in original_messages:
                try:
                    total += 1
                    guild_id = m.get("guild_id")
                    channel_id = m.get("channel_id")
                    message_id = m.get("message_id")
                    mode_saved = m.get("mode")
                    formatted_desc = m.get("formatted_desc", True)  # Padrão: formatada

                    if not (guild_id and channel_id and message_id):
                        # entrada inválida: remover
                        removed += 1
                        continue
                    if guild_id != inter.guild.id:
                        # não pertence a esta guild: manter
                        new_messages.append(m)
                        skipped += 1
                        continue
                    channel = inter.guild.get_channel(int(channel_id))
                    if channel is None:
                        # canal não existe mais
                        removed += 1
                        continue
                    try:
                        msg = await channel.fetch_message(int(message_id))
                    except disnake.NotFound:
                        # mensagem não existe mais
                        removed += 1
                        continue

                    # Usar métodos de SendProduct que respeitam preferências e botões customizados
                    from .send import SendProduct
                    send_cog = None
                    for cog in inter.client.cogs.values():
                        if isinstance(cog, SendProduct):
                            send_cog = cog
                            break
                    
                    if not send_cog:
                        send_cog = SendProduct(inter.bot)
                    
                    if mode_saved == "legacy":
                        embed = send_cog._build_legacy_embed(product, inter.guild, formatted_desc=formatted_desc)
                        components = send_cog._create_buy_button(product_id)
                        await msg.edit(embed=embed, components=components, flags=disnake.MessageFlags(is_components_v2=True))
                        updated += 1
                        new_messages.append(m)
                    elif mode_saved in ("container_outside", "container_inside"):
                        image_inside = (mode_saved == "container_inside")
                        comps = send_cog._build_container(product, image_inside=image_inside, product_id=product_id, formatted_desc=formatted_desc)
                        await msg.edit(components=comps, flags=disnake.MessageFlags(is_components_v2=True))
                        updated += 1
                        new_messages.append(m)
                    else:
                        skipped += 1
                        new_messages.append(m)
                except Exception:
                    skipped += 1
                    new_messages.append(m)

            # Se houve remoções, salvar alterações na database
            if len(new_messages) != len(original_messages):
                products[product_id]["messages"] = new_messages
                db.save_document("loja_products", products)

            color_data = db.get_document("custom_colors") or {}
            primary_color_hex = color_data.get("primary")
            container_kwargs = {}
            if primary_color_hex:
                container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

            result = disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Sincronização de Produto"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    f"**Produto:** `{product.get('name')}`\n"
                    f"**Total de mensagens:** `{total}`\n"
                    f"**Atualizadas:** `{updated}`\n"
                    f"**Removidas:** `{removed}`\n"
                    f"**Ignoradas:** `{skipped}`"
                ),
                **container_kwargs
            )
            await inter.followup.send(components=[result], ephemeral=True, flags=disnake.MessageFlags(is_components_v2=True))

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Loja_Produtos_Select":
            product_id = inter.values[0]
            mode = db.get_document("custom_mode").get("mode")
            
            # Verificar se a interação já foi respondida antes de fazer defer
            if not inter.response.is_done():
                try:
                    await inter.response.defer()
                except:
                    pass  # Another listener already responded
            
            panel_data = ConfigurarProduto.panel(inter, product_id)
            
            if mode == "embed":
                await inter.edit_original_message(content=None, **panel_data)
            else:
                await inter.edit_original_message(**panel_data)

def setup(bot: commands.Bot):
    bot.add_cog(ConfigurarProduto(bot))