#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comparação visual: Sistema antigo vs Sistema novo de logs
"""

import os
from PIL import Image, ImageDraw, ImageFont
from _path import GENERATED_ASSETS_DIR

class ComparisonVisualizer:
    """Classe para criar comparação visual dos sistemas de log"""

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.fonts_path = os.path.join(self.base_dir, "assets", "fonts")

        # Configurar fontes
        self.fonts = {
            "mono": self._load_font("JetBrains Mono Regular Nerd Font Complete.ttf", 12),
            "mono_bold": self._load_font("JetBrains Mono Bold Nerd Font Complete.ttf", 14),
            "regular": self._load_font("gg sans Regular.ttf", 14),
            "bold": self._load_font("gg sans Bold.ttf", 16),
        }

        # Cores
        self.colors = {
            'background': (15, 15, 15),
            'text': (255, 255, 255),
            'accent': (87, 242, 135),  # Verde system
            'old_system': (128, 128, 128),  # Cinza
            'new_system': (0, 255, 0),      # Verde
            'separator': (70, 70, 70),
            'highlight': (255, 215, 0),     # Amarelo
        }

        self.line_height = 18
        self.padding = 20

    def _load_font(self, font_name: str, size: int):
        try:
            font_path = os.path.join(self.fonts_path, font_name)
            return ImageFont.truetype(font_path, size)
        except:
            return ImageFont.load_default()

    def generate_comparison(self):
        """Gera imagem de comparação"""

        width = 1200
        height = 800

        img = Image.new('RGB', (width, height), self.colors['background'])
        draw = ImageDraw.Draw(img)

        # Título
        title = "🎨 Sistema de Logs: Antes vs Depois"
        title_bbox = draw.textbbox((0, 0), title, font=self.fonts['bold'])
        title_x = (width - (title_bbox[2] - title_bbox[0])) // 2
        draw.text((title_x, self.padding), title, fill=self.colors['accent'], font=self.fonts['bold'])

        y = self.padding + 50

        # Sistema Antigo
        old_x = self.padding
        draw.text((old_x, y), "❌ SISTEMA ANTIGO", fill=self.colors['old_system'], font=self.fonts['bold'])
        y += self.line_height * 1.5

        old_logs = [
            "Conectado em Lyon Pro | 123456789",
            "Servidores: 15",
            "Usuários: 1250",
            "Servidor principal: Lyon Server",
            "Latência: 45ms",
            "",
            "[WS] Connecting to wss://api.system...",
            "[Connection] HTTP polling started",
            "✅ Pro ready!"
        ]

        for log in old_logs:
            if log.strip():
                draw.text((old_x + 20, y), log, fill=self.colors['old_system'], font=self.fonts['mono'])
            y += self.line_height

        # Separador vertical
        sep_x = width // 2
        draw.line([(sep_x, self.padding), (sep_x, height - self.padding)], fill=self.colors['separator'], width=2)

        # Sistema Novo
        y = self.padding + 50
        new_x = sep_x + self.padding
        draw.text((new_x, y), "✅ SISTEMA NOVO", fill=self.colors['new_system'], font=self.fonts['bold'])
        y += self.line_height * 1.5

        new_logs = [
            "[09:12:09] INFO     LyonPro       === BOT INICIALIZADO COM SUCESSO ===",
            "[09:12:09] INFO     LyonPro       Conectado como: Lyon Pro (ID: 123456789)",
            "[09:12:09] INFO     LyonPro       Servidores conectados: 15",
            "[09:12:09] INFO     LyonPro       Usuários totais: 1250",
            "[09:12:09] INFO     LyonPro       Servidor principal: Lyon Server (ID: 987654321)",
            "[09:12:09] INFO     LyonPro       Latência do bot: 45ms (Excelente)",
            "",
            "[09:12:09] INFO     WebSocket       Conectando ao servidor: wss://api.system...",
            "[09:12:09] INFO     Connection      Iniciando polling HTTP para backup",
            "[09:12:09] INFO     LyonPro       Pro totalmente operacional e pronto!"
        ]

        for log in new_logs:
            if log.strip():
                # Colorir baseado no nível do log
                if 'INFO' in log:
                    color = (0, 255, 0)  # Verde
                elif 'WARNING' in log:
                    color = (255, 255, 0)  # Amarelo
                elif 'ERROR' in log:
                    color = (255, 0, 0)  # Vermelho
                else:
                    color = self.colors['text']

                draw.text((new_x + 20, y), log, fill=color, font=self.fonts['mono'])
            y += self.line_height

        # Benefícios
        y = height - 200
        benefits_title = "🚀 MELHORIAS IMPLEMENTADAS:"
        draw.text((self.padding, y), benefits_title, fill=self.colors['highlight'], font=self.fonts['bold'])
        y += self.line_height * 1.5

        benefits = [
            "• ✨ Cores por nível de severidade (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
            "• 🕐 Timestamps consistentes em horário de Brasília",
            "• 📝 Formatação estruturada e legível",
            "• 🏷️ Identificação clara de módulos e componentes",
            "• 📊 Fácil identificação de problemas e padrões",
            "• 💾 Suporte opcional a logs em arquivo com rotação",
            "• 🎯 Funções especializadas para comandos, eventos e performance",
            "• 🔍 Melhor debugging e monitoramento do sistema"
        ]

        for benefit in benefits:
            draw.text((self.padding + 20, y), benefit, fill=self.colors['text'], font=self.fonts['regular'])
            y += self.line_height

        return img

def main():
    visualizer = ComparisonVisualizer()
    img = visualizer.generate_comparison()

    output_path = GENERATED_ASSETS_DIR / 'logs_comparison.png'
    img.save(output_path, 'PNG')
    print(f"✅ Imagem de comparação gerada: {output_path}")

if __name__ == "__main__":
    main()
