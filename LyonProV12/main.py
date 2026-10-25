import sys
import os
import signal
import logging
import traceback
import asyncio
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Fix para usar disnake local caso necessário
# Se você copiou a pasta disnake/ para o projeto, isso garante que ela seja usada
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR.parent


def cleanup_startup_logs():
    patterns_by_dir = {
        WORKSPACE_DIR: ("bot_stdout*.log", "bot_stderr*.log"),
        BASE_DIR: ("bot_stdout*.log", "bot_stderr*.log"),
        BASE_DIR / "logs": ("*.log",),
    }
    removed = 0

    for folder, patterns in patterns_by_dir.items():
        if not folder.exists() or not folder.is_dir():
            continue
        for pattern in patterns:
            for file_path in folder.glob(pattern):
                if not file_path.is_file():
                    continue
                try:
                    file_path.unlink()
                    removed += 1
                except PermissionError:
                    pass
                except Exception as exc:
                    print(f"[StartupCleanup] Nao foi possivel apagar {file_path.name}: {exc}")

    if removed:
        print(f"[StartupCleanup] {removed} log(s) temporario(s) removido(s).")


cleanup_startup_logs()

from core.create_bot import create_bot
from core.change_bio import change_bio
from core.enable_intents import enable_intents
from functions.emojis import emojis
from functions.database import database
from functions.utils import utils
from functions.emoji import init_on_startup
from functions.components_safety import apply_component_safety
from functions.slash_command_emojis import apply_slash_command_emojis
from core.server_protection import apply_server_protection

logger = logging.getLogger(__name__)

bot, token, id = create_bot()

database.initialize_database_if_needed()
database.verify_and_create_missing_documents()

init_on_startup(token, id)
apply_component_safety()

# Proteção de servidor
apply_server_protection(bot)

###########################################################

bot.load_extension("modules")
bot.load_extension("commands")
bot.load_extension("events")
bot.load_extension("tasks")

apply_slash_command_emojis(bot)

_shutting_down = False

async def shutdown(signal_type=None):
    """Graceful shutdown handler"""
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True

    print(f"\n🛑 Encerrando bot gracefully...")
    
    try:
        # Fechar WebSocket do Cloud
        from connections import get_manager
        ws_manager = get_manager()
        if ws_manager:
            print("🔌 Fechando conexão Cloud WebSocket...")
            await ws_manager.disconnect()
    except Exception as e:
        print(f"⚠️ Erro ao fechar Cloud WebSocket: {e}")
    
    try:
        # Fechar WebSocket de Pagamentos
        from functions.payments.websocket_client import stop_ws_client
        print("🔌 Fechando conexão Payment WebSocket...")
        await stop_ws_client()
    except Exception as e:
        print(f"⚠️ Erro ao fechar Payment WebSocket: {e}")
    
    try:
        # Fechar sessão HTTP do PaymentAPIClient
        from functions.payments.api_client import _api_client
        if _api_client:
            print("🔌 Fechando sessão Payment API Client...")
            await _api_client.close()
    except Exception as e:
        print(f"⚠️ Erro ao fechar Payment API Client: {e}")
    
    try:
        # Fechar bot (isso fecha o loop internamente)
        # Suprimir warnings de "Unclosed client session" do aiohttp durante shutdown
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)
        
        # Redirecionar stderr temporariamente para suprimir prints diretos do aiohttp
        import io
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()
        
        print("🤖 Fechando bot...")
        await bot.close()
        
        # Restaurar stderr
        sys.stderr = original_stderr
    except Exception as e:
        sys.stderr = original_stderr if 'original_stderr' in dir() else sys.__stderr__
        print(f"⚠️ Erro ao fechar bot: {e}")
    
    print("✅ Pro encerrado com sucesso!")
    # Sair limpo sem deixar o GC tentar fechar sessions com loop fechado
    os._exit(0)

def handle_signal(sig, frame):
    """Handle Ctrl+C signal"""
    print(f"\n⚠️ Sinal recebido: {sig}")
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(shutdown(sig))
    except RuntimeError:
        # Sem loop rodando, executar Lyon
        print("🛑 Forçando encerramento...")
        os._exit(0)

if __name__ == "__main__":
    # Registrar handlers de sinal
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Verificar se deve atualizar a bio do bot
    config = database.obter("config.json")
    update_bio = config.get("updateProBio", False)
    
    if update_bio:
        change_bio()
    else:
        logger.info("[Main] Atualização da bio do bot desabilitada. Pulando...")
    
    enable_intents(token, id)
    
    print("[Main] Iniciando conexao com o Discord...", flush=True)
    try:
        bot.run(token)
    except Exception as e:
        print(f"[Main] Erro ao iniciar o bot: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        raise
    except KeyboardInterrupt:
        print("\n⚠️ KeyboardInterrupt detectado")
        # Tentar shutdown limpo
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.run_until_complete(shutdown())
        except Exception:
            pass
        os._exit(0)
