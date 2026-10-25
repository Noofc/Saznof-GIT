import disnake

from functions.database import database as db
from functions.receipt_generator import ReceiptGenerator
from functions.timezone import receipt_now
from ..preferences.receipts import current_receipt_style
from .order_utils import order_id_for_cart

DEFAULT_SITE = "https://systemapplications.com.br"


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_price(value) -> str:
    return f"R$ {_as_float(value):.2f}".replace(".", ",")


def _channel_url(guild_id: int, channel_id) -> str | None:
    channel_id = _as_int(channel_id)
    if not channel_id:
        return None
    return f"https://discord.com/channels/{guild_id}/{channel_id}"


def _purchase_event_channel(guild: disnake.Guild):
    config = db.get_document("loja_personalization") or {}
    event_config = config.get("purchase_event") or {}
    canais = db.get_document("canais") or {}
    channel_id = (
        event_config.get("event_channel_id")
        or event_config.get("channel_id")
        or canais.get("canal_de_evento_de_compras")
    )
    channel_id = _as_int(channel_id)
    if not channel_id:
        return None
    channel = guild.get_channel(channel_id)
    return channel if isinstance(channel, disnake.TextChannel) else None


def _product_url(guild_id: int, items: list) -> str | None:
    if not items:
        return None

    product_id = items[0].get("product_id")
    if not product_id:
        return None

    products = db.get_document("loja_products") or {}
    product = products.get(product_id, {})
    product_messages = product.get("messages", [])
    if not product_messages:
        return None

    latest_message = max(product_messages, key=lambda m: m.get("created_at", 0))
    channel_id = latest_message.get("channel_id")
    message_id = latest_message.get("message_id")
    if not channel_id or not message_id:
        return None
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def _build_buttons(guild: disnake.Guild, product_url: str | None = None) -> list:
    canais = db.get_document("canais") or {}
    feedback_url = _channel_url(guild.id, canais.get("canal_de_feedback"))
    support_url = _channel_url(guild.id, canais.get("canal_de_suporte"))

    row = disnake.ui.ActionRow()
    row.append_item(disnake.ui.Button(label="Comprar", style=disnake.ButtonStyle.link, url=product_url or DEFAULT_SITE))
    if feedback_url:
        row.append_item(disnake.ui.Button(label="Ver Feedbacks", style=disnake.ButtonStyle.link, url=feedback_url))
    if support_url:
        row.append_item(disnake.ui.Button(label="Suporte", style=disnake.ButtonStyle.link, url=support_url))
    return [row] if row.children else []


def _products_text(items: list) -> str:
    lines = []
    for item in items:
        product_name = item.get("product_name", item.get("product_id", "Item"))
        campo_name = item.get("campo_name") or item.get("field_name") or ""
        quantity = item.get("quantity", 1)
        if campo_name:
            lines.append(f"{quantity}x {product_name} | {campo_name}")
        else:
            lines.append(f"{quantity}x {product_name}")
    return "\n".join(lines) if lines else "Nenhum item listado."


def _receipt_items(items: list) -> list:
    normalized = []
    for item in items:
        normalized.append(
            {
                "product_name": item.get("product_name", item.get("product_id", "Item")),
                "campo_name": item.get("campo_name") or item.get("field_name") or "",
                "quantity": item.get("quantity", 1),
                "price": _as_float(item.get("price")),
            }
        )
    return normalized


def _build_v2_components(
    guild: disnake.Guild,
    user: disnake.Member,
    items: list,
    order_id: str,
    total_price: float,
    subtotal: float | None,
    discount_amount: float | None,
    coupon_code: str | None,
    buttons: list,
) -> list:
    details = [
        "## Compra Realizada",
        f"**Cliente:** {user.mention} (`@{user.name}`)",
        f"**Carrinho:**\n{_products_text(items)}",
    ]
    if subtotal is not None:
        details.append(f"**Subtotal:** `{_format_price(subtotal)}`")
    if discount_amount:
        details.append(f"**Desconto:** `-{_format_price(discount_amount)}`")
    if coupon_code:
        details.append(f"**Cupom:** `{coupon_code}`")
    details.extend(
        [
            f"**Valor pago:** `{_format_price(total_price)}`",
            f"**Pedido:** `{order_id}`",
            f"-# {receipt_now().strftime('%d/%m/%Y - %H:%M')} BRT",
        ]
    )

    children = [
        disnake.ui.TextDisplay("\n".join(details)),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.TextDisplay(f"**{guild.name.upper()}**\n-# Powered by Lyon Pro"),
    ]
    if buttons:
        children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
    components = [disnake.ui.Container(*children, accent_colour=disnake.Colour.green())]
    if buttons:
        components.extend(buttons)
    return components


def _build_embed(
    guild: disnake.Guild,
    user: disnake.Member,
    items: list,
    order_id: str,
    total_price: float,
    subtotal: float | None,
    discount_amount: float | None,
    coupon_code: str | None,
) -> disnake.Embed:
    embed = disnake.Embed(
        title="Compra Realizada",
        description=f"Cliente: {user.mention}",
        color=disnake.Color.green(),
        timestamp=receipt_now(),
    )
    embed.add_field(name="Pedido", value=f"`{order_id}`", inline=True)
    embed.add_field(name="Valor pago", value=f"**{_format_price(total_price)}**", inline=True)
    embed.add_field(name="Produtos", value=_products_text(items)[:1024], inline=False)
    if subtotal is not None:
        embed.add_field(name="Subtotal", value=_format_price(subtotal), inline=True)
    if discount_amount:
        embed.add_field(name="Desconto", value=f"-{_format_price(discount_amount)}", inline=True)
    if coupon_code:
        embed.add_field(name="Cupom", value=f"`{coupon_code}`", inline=True)
    embed.set_footer(text=f"Powered by Lyon Pro - {guild.name}")
    return embed


async def send_purchase_receipt(bot, guild: disnake.Guild, user: disnake.Member, cart: dict, items: list):
    style = current_receipt_style(guild.id)
    target_channel = _purchase_event_channel(guild)
    if not target_channel:
        print("[RECEIPT RENDERER] Canal de evento de compras nao configurado. Comprovante publico nao enviado.")
        return
    order_id = order_id_for_cart(cart, cart.get("cart_id") or cart.get("id"))
    total_price = _as_float(cart.get("total_price"))
    subtotal = cart.get("subtotal")
    if subtotal is None:
        subtotal = cart.get("original_price")
    subtotal = _as_float(subtotal) if subtotal is not None else None
    discount_amount = cart.get("discount_amount")
    discount_amount = _as_float(discount_amount) if discount_amount is not None else None
    coupon_code = cart.get("coupon_code")

    product_url = _product_url(guild.id, items)
    buttons = _build_buttons(guild, product_url)

    try:
        if style == "v2":
            await target_channel.send(
                components=_build_v2_components(
                    guild,
                    user,
                    items,
                    order_id,
                    total_price,
                    subtotal,
                    discount_amount,
                    coupon_code,
                    buttons,
                ),
                flags=disnake.MessageFlags(is_components_v2=True),
            )
            return

        if style == "image":
            receipt_buffer = ReceiptGenerator().generate_receipt(
                user_name=user.display_name,
                user_handle=user.name,
                user_avatar_path=None,
                items=_receipt_items(items),
                total_price=total_price,
                guild_name=guild.name,
                guild_icon_path=None,
                footer_text="Powered by Lyon Pro",
                subtotal=subtotal,
                discount_amount=discount_amount,
                coupon_code=coupon_code,
                timestamp=receipt_now(),
                status="Compra Realizada",
                order_id=order_id,
            )
            await target_channel.send(
                file=disnake.File(receipt_buffer, filename="recibo.png"),
                components=buttons if buttons else None,
            )
            return

        await target_channel.send(
            embed=_build_embed(guild, user, items, order_id, total_price, subtotal, discount_amount, coupon_code),
            components=buttons if buttons else None,
        )
    except disnake.Forbidden:
        print(f"[RECEIPT RENDERER] Sem permissao para enviar comprovante em {target_channel}.")
    except Exception as exc:
        print(f"[RECEIPT RENDERER] Erro ao enviar comprovante para {user}: {exc}")
