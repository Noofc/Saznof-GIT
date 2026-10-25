import disnake
from disnake.ext import commands
import asyncio
import json


class BoostWebSocketReady(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.websocket_started = False

    @commands.Cog.listener()
    async def on_ready(self):
        """Inicializa o WebSocket do Boost quando o bot estiver pronto"""
        if self.websocket_started:
            return
        
        self.websocket_started = True
        
        # Aguardar um pouco para garantir que o bot está completamente pronto
        await asyncio.sleep(3)
        
        try:
            # Carregar configuração do WebSocket
            with open('configs/config_websocket.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            boost_config = config.get('websocket_boost', {})
            
            if not boost_config.get('auto_start', True):
                print("[Boost WebSocket] Auto-start desabilitado")
                return
            
            # Importar e inicializar o gerenciador de WebSocket do Boost
            from modules.settings.extensions.boost.websocket_manager import get_websocket_manager
            
            ws_manager = get_websocket_manager()
            
            # Configurar URL e intervalo de reconexão do config
            server_url = boost_config.get('server_url', 'https://boost.Lyonapplications.com.br')
            reconnect_interval = boost_config.get('reconnect_interval', 5)
            
            ws_manager.server_url = server_url
            ws_manager.reconnect_interval = reconnect_interval
            ws_manager.set_bot(self.bot)
            
            # Iniciar conexão
            print(f"[Boost WebSocket] Iniciando conexão com {server_url}...")
            await ws_manager.start()
            
            # Confirmar estado real antes de anunciar sucesso
            if ws_manager.is_connected():
                print("[Boost WebSocket] ✅ WebSocket do Boost conectado")
            else:
                print("[Boost WebSocket] ⚠️ Servidor indisponível, reconexão automática ativada")
            
        except FileNotFoundError:
            print("[Boost WebSocket] ⚠️ Arquivo configs/config_websocket.json não encontrado")
        except Exception as e:
            print(f"[Boost WebSocket] ❌ Erro ao inicializar WebSocket do Boost: {e}")
            import traceback
            traceback.print_exc()


def setup(bot: commands.Bot):
    bot.add_cog(BoostWebSocketReady(bot))
