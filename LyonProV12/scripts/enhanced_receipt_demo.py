#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Versão melhorada do recibo com design mais profissional
"""

import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from _path import RECEIPTS_ASSETS_DIR
from functions.timezone import brasilia_now

class EnhancedReceiptGenerator:
    """Gerador de recibo com design aprimorado"""

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.fonts_path = os.path.join(self.base_dir, "assets", "fonts")

        # Configurar fontes
        self.fonts = {
            "regular": self._load_font("gg sans Regular.ttf", 16),
            "medium": self._load_font("gg sans Medium.ttf", 16),
            "semibold": self._load_font("gg sans Semibold.ttf", 16),
            "bold": self._load_font("gg sans Bold.ttf", 20),
            "title": self._load_font("gg sans Bold.ttf", 28),
            "price": self._load_font("gg sans Bold.ttf", 32),
            "small": self._load_font("gg sans Regular.ttf", 12),
            "tiny": self._load_font("gg sans Regular.ttf", 10),
        }

        # Cores aprimoradas
        self.colors = {
            'bg_top': (32, 32, 32),
            'bg_bottom': (18, 18, 18),
            'text_primary': (255, 255, 255),
            'text_secondary': (180, 180, 180),
            'text_muted': (120, 120, 120),
            'green': (87, 242, 135),
            'green_dark': (34, 197, 94),
            'divider': (80, 80, 80),
            'divider_light': (100, 100, 100),
            'success_bg': (34, 197, 94, 30),  # Verde com transparência
        }

    def _load_font(self, font_name: str, size: int):
        """Carrega fonte com fallback"""
        try:
            font_path = os.path.join(self.fonts_path, font_name)
            return ImageFont.truetype(font_path, size)
        except:
            return ImageFont.load_default()

    def generate_enhanced_receipt(self):
        """Gera recibo com design aprimorado"""

        width = 720
        height = 420  # Um pouco maior para acomodar mais informações
        padding = 24
        content_x = 48
        content_width = width - content_x - 48

        # Criar imagem com gradiente
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Gradiente de fundo mais suave
        card_img = Image.new("RGBA", (width, height), self.colors['bg_top'] + (255,))
        card_draw = ImageDraw.Draw(card_img)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            r = int(self.colors['bg_top'][0] * (1 - ratio) + self.colors['bg_bottom'][0] * ratio)
            g = int(self.colors['bg_top'][1] * (1 - ratio) + self.colors['bg_bottom'][1] * ratio)
            b = int(self.colors['bg_top'][2] * (1 - ratio) + self.colors['bg_bottom'][2] * ratio)
            card_draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Bordas arredondadas
        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=34, fill=255)
        img.paste(card_img, (0, 0), mask)

        # Avatar (placeholder)
        avatar_size = 56
        avatar_x = content_x
        avatar_y = padding + 8
        draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size],
                    fill=(60, 60, 60))

        # Inicial do usuário
        initial = "J"
        initial_bbox = draw.textbbox((0, 0), initial, font=self.fonts["bold"])
        initial_w = initial_bbox[2] - initial_bbox[0]
        initial_h = initial_bbox[3] - initial_bbox[1]
        draw.text(
            (avatar_x + (avatar_size - initial_w) / 2, avatar_y + (avatar_size - initial_h) / 2 - 2),
            initial,
            font=self.fonts["bold"],
            fill=self.colors['text_primary']
        )

        # Informações do usuário
        name_x = avatar_x + avatar_size + 16
        name_y = avatar_y + 4
        draw.text((name_x, name_y), "João Silva", font=self.fonts["bold"], fill=self.colors['text_primary'])
        handle_y = name_y + 24
        draw.text((name_x, handle_y), "@joaosilva", font=self.fonts["small"], fill=self.colors['text_muted'])

        # Data e hora no canto direito
        timestamp = brasilia_now()
        date_str = timestamp.strftime("%d/%m/%Y • %H:%M")
        date_bbox = draw.textbbox((0, 0), date_str, font=self.fonts["small"])
        date_w = date_bbox[2] - date_bbox[0]
        date_x = width - content_x - date_w
        date_y = avatar_y + 8
        draw.text((date_x, date_y), date_str, font=self.fonts["small"], fill=self.colors['text_secondary'])

        # Status com ícone de sucesso
        status_y = avatar_y + avatar_size + 20
        status_x = content_x

        # Fundo verde suave para o status
        status_bg_width = 140
        status_bg_height = 32
        status_bg_x = status_x - 8
        status_bg_y = status_y - 6

        # Criar layer separado para o fundo com transparência
        status_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        status_draw = ImageDraw.Draw(status_layer)
        status_draw.rounded_rectangle(
            [status_bg_x, status_bg_y, status_bg_x + status_bg_width, status_bg_y + status_bg_height],
            radius=16, fill=self.colors['success_bg']
        )
        img = Image.alpha_composite(img, status_layer)
        draw = ImageDraw.Draw(img)  # Recriar draw após composite

        # Ícone de check
        check_size = 20
        check_x = status_x + 2
        check_y = status_y + 2
        draw.ellipse([check_x, check_y, check_x + check_size, check_y + check_size],
                    fill=self.colors['green'])

        # Check mark
        draw.line([check_x + 5, check_y + 10, check_x + 9, check_y + 14], fill=(255, 255, 255), width=2)
        draw.line([check_x + 9, check_y + 14, check_x + 15, check_y + 8], fill=(255, 255, 255), width=2)

        # Texto do status
        status_text_x = status_x + check_size + 12
        status_text_y = status_y - 2
        draw.text((status_text_x, status_text_y), "Compra Realizada", font=self.fonts["semibold"],
                 fill=self.colors['text_primary'])

        # Separador
        separator_y = status_y + 40
        draw.line([content_x, separator_y, content_x + content_width, separator_y],
                 fill=self.colors['divider_light'], width=1)

        # Seção do carrinho
        cart_y = separator_y + 20
        draw.text((content_x, cart_y), "Carrinho", font=self.fonts["semibold"],
                 fill=self.colors['text_secondary'])

        # Itens com melhor espaçamento e alinhamento
        current_y = cart_y + 32
        items = [
            {"name": "Netflix Premium", "detail": "1 mês", "price": 39.90},
            {"name": "Spotify Premium", "detail": "Individual", "price": 19.90}
        ]

        # Calcular a posição X máxima para os preços (alinhamento à direita)
        max_price_x = content_x + content_width - 20

        for item in items:
            # Emoji e nome do produto
            item_text = f"📦 {item['name']}"
            if item['detail']:
                item_text += f" • {item['detail']}"

            draw.text((content_x, current_y), item_text, font=self.fonts["regular"],
                     fill=self.colors['text_primary'])

            # Preço alinhado à direita
            price_text = f"R$ {item['price']:.2f}".replace(".", ",")
            price_bbox = draw.textbbox((0, 0), price_text, font=self.fonts["regular"])
            price_w = price_bbox[2] - price_bbox[0]
            price_x = max_price_x - price_w
            draw.text((price_x, current_y), price_text, font=self.fonts["regular"],
                     fill=self.colors['text_primary'])

            current_y += 28  # Mais espaçamento entre itens

        # Separador antes do total
        total_separator_y = current_y + 12
        draw.line([content_x, total_separator_y, content_x + content_width, total_separator_y],
                 fill=self.colors['divider'], width=1)

        # Informações adicionais
        info_y = total_separator_y + 16

        # Pedido e método de pagamento
        order_info = "Pedido #12345 • Cartão de Crédito"
        draw.text((content_x, info_y), order_info, font=self.fonts["small"],
                 fill=self.colors['text_muted'])

        # Total
        total_y = info_y + 32
        draw.text((content_x, total_y), "Valor Total", font=self.fonts["semibold"],
                 fill=self.colors['text_primary'])

        total_price = 59.80
        total_text = f"R$ {total_price:.2f}".replace(".", ",")
        total_bbox = draw.textbbox((0, 0), total_text, font=self.fonts["price"])
        total_w = total_bbox[2] - total_bbox[0]
        total_x = max_price_x - total_w
        draw.text((total_x, total_y - 4), total_text, font=self.fonts["price"],
                 fill=self.colors['green'])

        # Footer aprimorado
        footer_y = height - padding - 20
        footer_text = "Lyon Pro"
        footer_bbox = draw.textbbox((0, 0), footer_text, font=self.fonts["small"])
        footer_w = footer_bbox[2] - footer_bbox[0]
        footer_x = width - padding - footer_w
        draw.text((footer_x, footer_y), footer_text, font=self.fonts["small"],
                 fill=self.colors['text_muted'])

        # Powered by no lado esquerdo
        powered_text = "Powered by"
        powered_x = content_x
        draw.text((powered_x, footer_y), powered_text, font=self.fonts["tiny"],
                 fill=self.colors['text_muted'])

        return img

def main():
    """Função principal"""
    generator = EnhancedReceiptGenerator()
    img = generator.generate_enhanced_receipt()

    # Salvar imagem
    output_path = RECEIPTS_ASSETS_DIR / 'enhanced_receipt_demo.png'
    img.save(output_path, 'PNG')
    print(f"✅ Recibo aprimorado gerado: {output_path}")
    print("🎨 Melhorias aplicadas:")
    print("   • Hierarquia visual mais forte")
    print("   • Alinhamento preciso dos preços")
    print("   • Informações adicionais (pedido, pagamento)")
    print("   • Status com fundo verde sutil")
    print("   • Footer mais limpo e profissional")
    print("   • Espaçamento otimizado")

if __name__ == "__main__":
    main()
