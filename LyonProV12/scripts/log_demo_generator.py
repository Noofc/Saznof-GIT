#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstração visual do sistema de logging aprimorado
Gera uma imagem mostrando como os logs ficariam no console
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from _path import GENERATED_ASSETS_DIR
from functions.timezone import brasilia_now

class LogVisualizer:
    """Classe para visualizar logs em imagem"""

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.fonts_path = os.path.join(self.base_dir, "assets", "fonts")

        # Configurar fontes
        self.fonts = {
            "mono": self._load_font("JetBrains Mono Regular Nerd Font Complete.ttf", 14),
            "mono_bold": self._load_font("JetBrains Mono Bold Nerd Font Complete.ttf", 14),
        }

        # Configurar cores (simulando terminal)
        self.colors = {
            'background': (12, 12, 12),    # Terminal dark
            'text': (255, 255, 255),       # White text
            'timestamp': (128, 128, 128), # Gray timestamp
            'module': (128, 128, 128),    # Gray module
            'debug': (0, 255, 255),       # Cyan
            'info': (0, 255, 0),          # Green
            'warning': (255, 255, 0),     # Yellow
            'error': (255, 0, 0),         # Red
            'critical': (255, 0, 255),    # Magenta
        }

        self.line_height = 20
        self.padding = 20

    def _load_font(self, font_name: str, size: int):
        """Carrega fonte com fallback"""
        try:
            font_path = os.path.join(self.fonts_path, font_name)
            return ImageFont.truetype(font_path, size)
        except:
            return ImageFont.load_default()

    def generate_log_demo(self):
        """Gera imagem demonstrativa dos logs"""

        # Dados de exemplo dos logs
        log_entries = [
            ("DEBUG", "LyonPro", "09:15:23", "Iniciando verificação de conexões ativas"),
            ("INFO", "LyonPro", "09:15:24", "Pro conectado com sucesso - Latência: 45ms"),
            ("INFO", "Commands", "09:15:25", "Comando executado: /ticket criar {'user': 'João#1234', 'channel': '#suporte'}"),
            ("WARNING", "Database", "09:15:26", "Conexão MongoDB lenta detectada - 2.3s para resposta"),
            ("ERROR", "WebSocket", "09:15:27", "Falha na reconexão - tentando novamente em 30s"),
            ("INFO", "Events", "09:15:28", "Novo membro entrou: Maria#5678 (ID: 987654321)"),
            ("INFO", "Performance", "09:15:29", "Comando /help executado em 0.12s"),
            ("CRITICAL", "Security", "09:15:30", "Tentativa de acesso não autorizado detectada"),
            ("INFO", "LyonPro", "09:15:31", "Backup automático concluído - 1.2GB salvos"),
        ]

        # Calcular dimensões
        width = 1000
        height = self.padding * 2 + len(log_entries) * self.line_height

        # Criar imagem
        img = Image.new('RGB', (width, height), self.colors['background'])
        draw = ImageDraw.Draw(img)

        y = self.padding

        # Título
        title = "Sistema de Logging Aprimorado - Demonstração Visual"
        draw.text((self.padding, y), title, fill=self.colors['text'], font=self.fonts['mono_bold'])
        y += self.line_height * 1.5

        # Legenda
        legend = "Format: [HH:MM:SS] LEVEL      MODULE         MESSAGE"
        draw.text((self.padding, y), legend, fill=self.colors['timestamp'], font=self.fonts['mono'])
        y += self.line_height * 1.2

        # Linha separadora
        draw.line([(self.padding, y), (width - self.padding, y)], fill=self.colors['timestamp'], width=1)
        y += self.line_height * 0.5

        # Renderizar cada entrada de log
        for level, module, timestamp, message in log_entries:
            # Timestamp
            time_text = f"[{timestamp}]"
            draw.text((self.padding, y), time_text, fill=self.colors['timestamp'], font=self.fonts['mono'])

            # Level com cor
            level_x = self.padding + 120
            level_color = self.colors.get(level.lower(), self.colors['text'])
            level_text = f"{level:<8}"
            draw.text((level_x, y), level_text, fill=level_color, font=self.fonts['mono_bold'])

            # Module
            module_x = level_x + 100
            module_text = f"{module:<15}"
            draw.text((module_x, y), module_text, fill=self.colors['module'], font=self.fonts['mono'])

            # Message
            message_x = module_x + 180
            draw.text((message_x, y), message, fill=self.colors['text'], font=self.fonts['mono'])

            y += self.line_height

        # Adicionar informações sobre benefícios
        y += self.line_height * 0.5
        benefits = [
            "✅ Cores por nível de severidade",
            "✅ Timestamps em horário de Brasília",
            "✅ Formatação consistente e legível",
            "✅ Módulos identificados claramente",
            "✅ Fácil identificação de problemas",
            "✅ Pronto para logs em arquivo"
        ]

        for benefit in benefits:
            draw.text((self.padding, y), benefit, fill=self.colors['info'], font=self.fonts['mono'])
            y += self.line_height

        return img

def main():
    """Função principal"""
    visualizer = LogVisualizer()
    img = visualizer.generate_log_demo()

    # Salvar imagem
    output_path = GENERATED_ASSETS_DIR / 'log_system_demo.png'
    img.save(output_path, 'PNG')
    print(f"✅ Imagem de demonstração dos logs gerada: {output_path}")

    # Também mostrar informações sobre o sistema
    print("\n🎨 Sistema de Logging Aprimorado Criado!")
    print("📁 Arquivo: functions/logger.py")
    print("✨ Funcionalidades:")
    print("   • Logs coloridos no console")
    print("   • Níveis adequados (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    print("   • Timestamps em horário de Brasília")
    print("   • Formatação consistente")
    print("   • Suporte a logs em arquivo (opcional)")
    print("   • Funções especializadas para comandos, eventos e performance")

if __name__ == "__main__":
    main()
