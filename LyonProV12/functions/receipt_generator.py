# -*- coding: utf-8 -*-
import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import io
from typing import Any, Dict, List, Optional
from functions.timezone import BRASILIA_TZ, receipt_now


class ReceiptGenerator:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.fonts_path = os.path.join(self.base_dir, "assets", "fonts")
        self.fonts = {
            "regular": os.path.join(self.fonts_path, "gg sans Regular.ttf"),
            "medium": os.path.join(self.fonts_path, "gg sans Medium.ttf"),
            "semibold": os.path.join(self.fonts_path, "gg sans Semibold.ttf"),
            "bold": os.path.join(self.fonts_path, "gg sans Bold.ttf"),
        }
        self.bg_color = (12, 12, 12)
        self.card_top = (28, 28, 28)
        self.card_bottom = (8, 8, 8)
        self.text_color = (255, 255, 255)
        self.subtext_color = (180, 180, 180)
        self.green_color = (87, 242, 135)
        self.footer_color = (255, 255, 255)
        self.divider_color = (70, 70, 70)
        self.text_secondary = (180, 180, 180)
        self.brasilia_tz = BRASILIA_TZ

    def _load_font(self, path: str, size: int):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    def apply_rounded_corners(self, img: Image.Image, radius: int = 25) -> Image.Image:
        """
        Aplica cantos arredondados uniformes a uma imagem.
        
        Args:
            img (Image.Image): Imagem PIL
            radius (int): Raio de arredondamento em pixels
            
        Returns:
            Image.Image: Imagem com cantos arredondados
        """
        width, height = img.size
        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, width, height], radius=radius, fill=255)
        img.putalpha(mask)
        return img

    def generate_receipt(
        self,
        user_name: str,
        user_handle: str,
        user_avatar_path: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
        total_price: float = 0,
        guild_name: str = "",
        guild_icon_path: Optional[str] = None,
        footer_text: str = "Powered by Lyon Pro",
        subtotal: Optional[float] = None,
        discount_amount: Optional[float] = None,
        coupon_code: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        status: str = "Compra Realizada",
        order_id: Optional[str] = None,
    ) -> io.BytesIO:
        if items is None:
            items = [{"product_name": "Produto", "campo_name": "", "quantity": 1, "price": 0}]
        if not items:
            items = [{"product_name": "Produto", "campo_name": "", "quantity": 1, "price": 0}]

        if timestamp is None:
            timestamp = receipt_now()
        else:
            try:
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=self.brasilia_tz)
                else:
                    timestamp = timestamp.astimezone(self.brasilia_tz)
            except Exception:
                timestamp = receipt_now()

        def format_timestamp(ts: datetime) -> str:
            return ts.strftime("%d/%m/%Y • %H:%M")

        width = 720
        height = 390
        padding = 30
        content_x = 52
        content_width = width - content_x - 52
        content_right = content_x + content_width
        item_height = 20

        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        card_img = Image.new("RGBA", (width, height), self.card_top + (255,))
        card_draw = ImageDraw.Draw(card_img)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            r = int(self.card_top[0] * (1 - ratio) + self.card_bottom[0] * ratio)
            g = int(self.card_top[1] * (1 - ratio) + self.card_bottom[1] * ratio)
            b = int(self.card_top[2] * (1 - ratio) + self.card_bottom[2] * ratio)
            card_draw.line([(0, y), (width, y)], fill=(r, g, b))
        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([1, 1, width - 1, height - 1], radius=36, fill=255)
        img.paste(card_img, (0, 0), mask)

        font_title = self._load_font(self.fonts["bold"], 35)
        font_name = self._load_font(self.fonts["bold"], 24)
        font_handle = self._load_font(self.fonts["regular"], 14)
        font_date = self._load_font(self.fonts["semibold"], 12)
        font_label = self._load_font(self.fonts["semibold"], 16)
        font_item = self._load_font(self.fonts["semibold"], 17)
        font_price = self._load_font(self.fonts["bold"], 17)
        font_total_label = self._load_font(self.fonts["semibold"], 19)
        font_total_value = self._load_font(self.fonts["bold"], 22)
        font_footer = self._load_font(self.fonts["semibold"], 16)
        font_footer_powered = self._load_font(self.fonts["medium"], 17)
        font_footer_brand = self._load_font(self.fonts["bold"], 19)
        font_avatar_initial = self._load_font(self.fonts["bold"], 32)

        avatar_size = 58
        avatar_x = content_x
        avatar_y = padding + 14
        avatar_loaded = False
        if user_avatar_path and os.path.exists(user_avatar_path):
            try:
                avatar = Image.open(user_avatar_path).convert("RGBA")
                avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                avatar_mask = Image.new("L", (avatar_size, avatar_size), 0)
                avatar_mask_draw = ImageDraw.Draw(avatar_mask)
                avatar_mask_draw.ellipse([0, 0, avatar_size, avatar_size], fill=255)
                img.paste(avatar, (avatar_x, avatar_y), avatar_mask)
                avatar_loaded = True
            except Exception:
                avatar_loaded = False

        if not avatar_loaded:
            draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], fill=(50, 50, 50))
            initial = (user_name or user_handle or "?").strip()[:1].upper() or "?"
            initial_bbox = draw.textbbox((0, 0), initial, font=font_avatar_initial)
            initial_w = initial_bbox[2] - initial_bbox[0]
            initial_h = initial_bbox[3] - initial_bbox[1]
            draw.text(
                (avatar_x + (avatar_size - initial_w) / 2, avatar_y + (avatar_size - initial_h) / 2 - 2),
                initial,
                font=font_avatar_initial,
                fill=self.text_color
            )

        name_x = avatar_x + avatar_size + 16
        name_y = avatar_y + 5
        draw.text((name_x, name_y), user_name, font=font_name, fill=self.text_color)

        handle_text = f"@{user_handle}"
        handle_y = name_y + 32
        draw.text((name_x, handle_y), handle_text, font=font_handle, fill=self.subtext_color)

        date_str = format_timestamp(timestamp)
        date_w = draw.textbbox((0, 0), date_str, font=font_date)[2]
        date_x = width - content_x - date_w - 2
        date_y = avatar_y + 22
        draw.text((date_x, date_y), date_str, font=font_date, fill=self.subtext_color)

        handle_height = draw.textbbox((0, 0), handle_text, font=font_handle)[3]
        date_height = draw.textbbox((0, 0), date_str, font=font_date)[3]
        top_bottom = max(avatar_y + avatar_size, handle_y + handle_height, date_y + date_height)
        status_y = top_bottom + 26
        status_x = content_x
        status_circle = 28
        draw.ellipse([status_x, status_y, status_x + status_circle, status_y + status_circle], fill=self.green_color)
        check_offset_x = status_x + 8
        check_offset_y = status_y + 8
        draw.line([check_offset_x, check_offset_y + 4, check_offset_x + 8, check_offset_y + 14], fill=(255, 255, 255), width=3)
        draw.line([check_offset_x + 8, check_offset_y + 14, check_offset_x + 18, check_offset_y + 3], fill=(255, 255, 255), width=3)

        # Centralizar o texto do status verticalmente com o círculo
        status_text_bbox = draw.textbbox((0, 0), status, font=font_title)
        status_text_height = status_text_bbox[3] - status_text_bbox[1]
        status_text_y = status_y + (status_circle - status_text_height) // 2 + 1

        # Posicionar o texto mais próximo do círculo para melhor centralização visual
        status_text_x = status_x + status_circle + 16
        draw.text((status_text_x, status_text_y), status, font=font_title, fill=self.text_color)

        section_div_y = status_y + status_circle + 20
        # Linha divisória removida - mantém seções visualmente separadas sem bordas

        cart_y = section_div_y + 10
        draw.text((content_x, cart_y), "Carrinho", font=font_label, fill=self.subtext_color)

        current_y = cart_y + 12

        def truncate_text(text: str, max_width: int, font: ImageFont.ImageFont) -> str:
            if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
                return text
            ellipsis = "..."
            for length in range(len(text), 0, -1):
                candidate = text[:length].rstrip()
                if draw.textbbox((0, 0), candidate + ellipsis, font=font)[2] <= max_width:
                    return candidate + ellipsis
            return ellipsis

        right_margin = 20
        amount_right_x = content_right - right_margin

        # Calcular largura máxima dos preços para alinhamento perfeito com margem adicional
        max_price_width = 0
        for item in items:
            price = item.get("price", 0)
            price_text = f"R$ {price:.2f}".replace(".", ",")
            price_w = draw.textbbox((0, 0), price_text, font=font_price)[2]
            max_price_width = max(max_price_width, price_w)

        # Adicionar espaço extra para o valor total com margem de segurança
        total_price_text = f"R$ {total_price:.2f}".replace(".", ",")
        total_price_w = draw.textbbox((0, 0), total_price_text, font=font_total_value)[2]
        max_price_width = max(max_price_width, total_price_w + 6)

        for item in items:
            product_name = item.get("product_name", "Produto")
            campo_name = item.get("campo_name", "")
            quantity = item.get("quantity", 1)
            price = item.get("price", 0)
            if campo_name:
                item_title = f"📦 {quantity}x {product_name} | {campo_name}"
            else:
                item_title = f"📦 {quantity}x {product_name}"
            price_text = f"R$ {price:.2f}".replace(".", ",")
            # Usar largura máxima para alinhamento perfeito à direita
            item_title = item_title.split(" ", 1)[1] if " " in item_title else item_title
            price_w = draw.textbbox((0, 0), price_text, font=font_price)[2]
            max_title_width = int(amount_right_x - max_price_width - content_x - 16)

            item_title = truncate_text(item_title, max_title_width, font=font_item)
            draw.text((content_x, current_y + 3), item_title, font=font_item, fill=self.text_color)
            draw.text((amount_right_x - price_w, current_y + 3), price_text, font=font_price, fill=self.text_color)
            current_y += item_height + 4

        if subtotal is not None:
            current_y += 6
            subtotal_text = f"R$ {subtotal:.2f}".replace(".", ",")
            draw.text((content_x, current_y + 3), "Subtotal", font=font_label, fill=self.subtext_color)
            subtotal_w = draw.textbbox((0, 0), subtotal_text, font=font_price)[2]
            draw.text((amount_right_x - subtotal_w, current_y + 3), subtotal_text, font=font_price, fill=self.subtext_color)
            current_y += item_height + 8

        if coupon_code:
            coupon_text = f"Cupom: {coupon_code}"
            coupon_w = draw.textbbox((0, 0), coupon_text, font=font_handle)[2]
            draw.text((content_x, current_y + 3), coupon_text, font=font_handle, fill=self.text_secondary)
            current_y += item_height + 8

        total_price_text = f"R$ {total_price:.2f}".replace(".", ",")
        total_price_w = draw.textbbox((0, 0), total_price_text, font=font_total_value)[2]
        total_bbox = draw.textbbox((0, 0), total_price_text, font=font_total_value)
        total_text_height = total_bbox[3] - total_bbox[1]

        footer_icon_size = 24
        powered_text = footer_text
        powered_prefix = "Powered by "
        powered_brand = powered_text
        if powered_text.startswith(powered_prefix):
            powered_brand = powered_text[len(powered_prefix):]
        powered_prefix_w = draw.textbbox((0, 0), powered_prefix, font=font_footer_powered)[2]
        powered_brand_bbox = draw.textbbox((0, 0), powered_brand, font=font_footer_brand)
        powered_brand_w = powered_brand_bbox[2] - powered_brand_bbox[0]
        powered_w = powered_prefix_w + powered_brand_w
        footer_bbox = draw.textbbox((0, 0), powered_brand, font=font_footer_brand)
        footer_font_height = footer_bbox[3] - footer_bbox[1]
        footer_height = max(footer_icon_size, footer_font_height)
        footer_y = height - padding - footer_height - 4

        divider_y = current_y + 8
        draw.line([content_x, divider_y, content_x + content_width, divider_y], fill=(255, 255, 255, 30), width=1)

        total_y = current_y + 16
        total_x = amount_right_x - total_price_w
        draw.text((content_x, total_y + 2), "Valor pago", font=font_total_label, fill=self.text_color)
        draw.text((total_x, total_y - 1), total_price_text, font=font_total_value, fill=self.green_color)

        order_y = total_y + total_text_height + 4
        if order_id:
            order_text = f"Pedido #{order_id}"
            order_text_w = draw.textbbox((0, 0), order_text, font=font_handle)[2]
            order_x = amount_right_x - order_text_w
            draw.text((order_x, order_y + 2), order_text, font=font_handle, fill=self.subtext_color)

        current_y = order_y + (item_height if order_id else 0)

        powered_text = footer_text
        powered_prefix = "Powered by "
        powered_brand = powered_text
        if powered_text.startswith(powered_prefix):
            powered_brand = powered_text[len(powered_prefix):]
        powered_prefix_w = draw.textbbox((0, 0), powered_prefix, font=font_footer_powered)[2]
        powered_brand_bbox = draw.textbbox((0, 0), powered_brand, font=font_footer_brand)
        powered_brand_w = powered_brand_bbox[2] - powered_brand_bbox[0]
        powered_w = powered_prefix_w + powered_brand_w
        footer_bbox = draw.textbbox((0, 0), powered_brand, font=font_footer_brand)
        footer_font_height = footer_bbox[3] - footer_bbox[1]
        footer_height = max(footer_icon_size, footer_font_height)

        footer_name = guild_name.upper()
        powered_x = content_right - powered_w
        footer_x = content_x
        footer_y = height - padding - footer_height - 4
        icon_y = footer_y + (footer_height - footer_icon_size) // 2
        footer_text_y = footer_y + (footer_height - footer_font_height) // 2
        footer_name_w = draw.textbbox((0, 0), footer_name, font=font_footer)[2]

        if footer_x + footer_icon_size + 12 + footer_name_w + 24 > powered_x:
            font_footer = self._load_font(self.fonts["regular"], 12)
            font_footer_powered = self._load_font(self.fonts["medium"], 14)
            font_footer_brand = self._load_font(self.fonts["bold"], 16)
            powered_prefix_w = draw.textbbox((0, 0), powered_prefix, font=font_footer_powered)[2]
            powered_brand_bbox = draw.textbbox((0, 0), powered_brand, font=font_footer_brand)
            powered_brand_w = powered_brand_bbox[2] - powered_brand_bbox[0]
            powered_w = powered_prefix_w + powered_brand_w
            powered_x = content_right - powered_w
            footer_bbox = draw.textbbox((0, 0), powered_brand, font=font_footer_brand)
            footer_font_height = footer_bbox[3] - footer_bbox[1]
            footer_height = max(footer_icon_size, footer_font_height)
            footer_y = height - padding - footer_height - 8
            icon_y = footer_y + (footer_height - footer_icon_size) // 2
            footer_text_y = footer_y + (footer_height - footer_font_height) // 2
            footer_name_w = draw.textbbox((0, 0), footer_name, font=font_footer)[2]

        if guild_icon_path and os.path.exists(guild_icon_path):
            try:
                g_icon = Image.open(guild_icon_path).convert("RGBA")
                g_icon = g_icon.resize((footer_icon_size, footer_icon_size), Image.Resampling.LANCZOS)
                icon_mask = Image.new("L", (footer_icon_size, footer_icon_size), 0)
                icon_mask_draw = ImageDraw.Draw(icon_mask)
                icon_mask_draw.ellipse([0, 0, footer_icon_size, footer_icon_size], fill=255)
                img.paste(g_icon, (footer_x, icon_y), icon_mask)
            except Exception:
                # Adicionar letra "S" branca centralizada no círculo
                draw.ellipse([footer_x, icon_y, footer_x + footer_icon_size, icon_y + footer_icon_size], fill=(50, 50, 50))
                initial = "S"
                initial_bbox = draw.textbbox((0, 0), initial, font=font_footer)
                initial_w = initial_bbox[2] - initial_bbox[0]
                initial_h = initial_bbox[3] - initial_bbox[1]
                draw.text(
                    (footer_x + (footer_icon_size - initial_w) / 2, icon_y + (footer_icon_size - initial_h) / 2 - 1),
                    initial,
                    font=font_footer,
                    fill=(255, 255, 255)
                )
        else:
            # Adicionar letra "S" branca centralizada no círculo
            draw.ellipse([footer_x, icon_y, footer_x + footer_icon_size, icon_y + footer_icon_size], fill=(50, 50, 50))
            initial = "S"
            initial_bbox = draw.textbbox((0, 0), initial, font=font_footer)
            initial_w = initial_bbox[2] - initial_bbox[0]
            initial_h = initial_bbox[3] - initial_bbox[1]
            draw.text(
                (footer_x + (footer_icon_size - initial_w) / 2, icon_y + (footer_icon_size - initial_h) / 2 - 1),
                initial,
                font=font_footer,
                fill=(255, 255, 255)
            )

        draw.text((footer_x + footer_icon_size + 14, footer_text_y + 2), footer_name, font=font_footer, fill=self.text_color)
        draw.text((powered_x, footer_text_y + 3), powered_prefix, font=font_footer_powered, fill=self.footer_color)
        draw.text((powered_x + powered_prefix_w, footer_text_y + 2), powered_brand, font=font_footer_brand, fill=self.footer_color)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
