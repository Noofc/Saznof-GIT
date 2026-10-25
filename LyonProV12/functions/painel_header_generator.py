# -*- coding: utf-8 -*-
"""Gerador do banner usado no painel principal."""

import io
import os

from PIL import Image, ImageDraw, ImageFont


class PainelHeaderGenerator:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.fonts_path = os.path.join(self.base_dir, "assets", "fonts")
        self.fonts = {
            "regular": os.path.join(self.fonts_path, "gg sans Regular.ttf"),
            "medium": os.path.join(self.fonts_path, "gg sans Medium.ttf"),
            "semibold": os.path.join(self.fonts_path, "gg sans Semibold.ttf"),
            "bold": os.path.join(self.fonts_path, "gg sans Bold.ttf"),
        }

    def _load_font(self, path: str, size: int):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    def generate_header(self) -> io.BytesIO:
        width = 1600
        height = 380

        color_dark = (12, 15, 21)
        color_panel = (19, 24, 32)
        color_blue = (0, 132, 255)
        color_blue_soft = (55, 160, 255)
        color_white = (245, 247, 250)
        color_gray = (155, 165, 178)
        color_line = (53, 65, 78, 150)

        img = Image.new("RGBA", (width, height), color_dark + (255,))
        draw = ImageDraw.Draw(img)

        for y in range(height):
            ratio = y / max(height - 1, 1)
            r = int(color_dark[0] + (color_panel[0] - color_dark[0]) * ratio)
            g = int(color_dark[1] + (color_panel[1] - color_dark[1]) * ratio)
            b = int(color_dark[2] + (color_panel[2] - color_dark[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        for x in range(0, width, 80):
            draw.line([(x, 0), (x - 220, height)], fill=(255, 255, 255, 10), width=1)
        for y in range(0, height, 58):
            draw.line([(0, y), (width, y + 36)], fill=(255, 255, 255, 8), width=1)

        draw.rectangle((0, 0, 10, height), fill=color_blue)
        draw.rectangle((70, 54, width - 70, height - 54), outline=(255, 255, 255, 70), width=2)
        draw.line((70, 54, 205, 54), fill=color_white, width=5)
        draw.line((width - 215, 54, width - 70, 54), fill=color_white, width=5)
        draw.line((width - 250, height - 86, width - 190, height - 86), fill=color_blue, width=8)

        for offset, alpha in [(0, 64), (26, 40), (52, 22)]:
            draw.ellipse(
                (width - 650 + offset, 74 + offset, width - 190 + offset, height + 198 + offset),
                outline=(color_blue[0], color_blue[1], color_blue[2], alpha),
                width=3,
            )

        draw.rectangle((width - 405, 138, width - 130, 203), fill=(255, 255, 255, 18), outline=color_line, width=1)

        font_title = self._load_font(self.fonts["bold"], 78)
        font_title_small = self._load_font(self.fonts["bold"], 62)
        font_description = self._load_font(self.fonts["medium"], 23)
        font_small = self._load_font(self.fonts["semibold"], 20)
        font_corner = self._load_font(self.fonts["bold"], 24)

        title_x = 205
        title_y = 94

        draw.text((title_x, title_y), "PAINEL DE", font=font_title, fill=color_white)
        draw.text((title_x, title_y + 82), "GERENCIAMENTO", font=font_title_small, fill=color_white)

        draw.text(
            (title_x, title_y + 168),
            "Hub de gerenciamento do bot, centralizando informacoes essenciais e",
            font=font_description,
            fill=color_gray,
        )
        draw.text(
            (title_x, title_y + 198),
            "oferecendo acesso rapido as configuracoes.",
            font=font_description,
            fill=color_gray,
        )

        draw.text((82, 84), "SYSTEM", font=font_small, fill=color_blue_soft)
        draw.text((82, 112), "APPLICATIONS", font=font_small, fill=color_white)
        draw.text((width - 380, 158), "GERENCIAMENTO", font=font_corner, fill=color_gray)
        draw.text((width - 160, 82), "SA", font=font_corner, fill=color_white)
        draw.text((width - 150, height - 124), "SYSTEM", font=font_corner, fill=color_white)
        draw.text((width - 150, height - 96), "APPS", font=font_corner, fill=color_blue_soft)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer


_generator = PainelHeaderGenerator()


def generate_painel_header() -> io.BytesIO:
    return _generator.generate_header()
