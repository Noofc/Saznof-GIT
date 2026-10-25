import aiohttp
import asyncio
import logging
import json

# Bridge para SocketIOManager de connections
try:
    from connections import get_manager as _get_ws_manager, initialize as init_ws
    from connections.socketio_manager import SocketIOManager
except ImportError:
    # Fallback se executado de diretório diferente
    from bot.connections import get_manager as _get_ws_manager, initialize as init_ws
    from bot.connections.socketio_manager import SocketIOManager

# Instância global do gerenciador WebSocket
websocket_manager = None
logger = logging.getLogger(__name__)

def get_websocket_manager():
    """Retorna a instância global do gerenciador WebSocket (bridge para novo SocketIOManager)"""
    global websocket_manager
    if websocket_manager is None:
        # Tentar obter do connections module
        websocket_manager = _get_ws_manager()
    if websocket_manager is None:
        # Tentar obter do bot.ws_manager se disponível
        bot_instance = get_bot_instance()
        if bot_instance and hasattr(bot_instance, 'ws_manager') and bot_instance.ws_manager:
            websocket_manager = bot_instance.ws_manager
            print("🔄 [update_api] Using existing bot.ws_manager instance")
    # NÃO criar nova instância - deixar que connections module faça isso
    return websocket_manager

def _get_http_base_url() -> str:
    """Obtém a URL base para chamadas HTTP da Lyon Cloud API.
    Usa o config_api.json como fonte principal.
    """
    try:
        from .cloud_config import get_cloud_url
        return get_cloud_url()
    except Exception:
        # Fallback para config antigo
        try:
            from functions.database import database as db
            config = db.obter("configs/config_websocket.json") or {}
            websocket_cfg = (config.get("websocket_cloud") or {})
            http_cfg = (config.get("http") or {})
            return (
                websocket_cfg.get("http_url")
                or http_cfg.get("server_url")
                or websocket_cfg.get("server_url")
                or "https://cloud.Lyonapplications.com.br"
            )
        except Exception:
            return "https://cloud.Lyonapplications.com.br"

async def register_bot(bot_id: str, bot_token: str, client_secret: str = None, verified_role_id: str = None, log_channel_id: str = None, auto_role_id: str = None):
    """Registra o bot no servidor Cloud via HTTP"""
    try:
        # Resolver o clientId real a partir do token (pode ser um bot diferente do principal)
        client_id = bot_id  # fallback
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://discord.com/api/v10/users/@me',
                    headers={'Authorization': f'Bot {bot_token}'},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as discord_resp:
                    if discord_resp.status == 200:
                        discord_data = await discord_resp.json()
                        client_id = discord_data.get('id', bot_id)
                    else:
                        logger.warning(f"Não foi possível resolver clientId do token: {discord_resp.status}")
        except Exception as e:
            logger.warning(f"Erro ao resolver clientId do token: {e}")

        base_url = _get_http_base_url()
        url = f"{base_url}/api/bot/register"
        
        data = {
            "mainProId": bot_id,
            "token": bot_token,
            "clientId": client_id,
        }
        
        if client_secret:
            data["clientSecret"] = client_secret
        
        if verified_role_id:
            data["verifiedRoleId"] = verified_role_id
        
        if log_channel_id:
            data["logChannelId"] = log_channel_id
        
        if auto_role_id:
            data["autoRoleId"] = auto_role_id
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Pro registrado com sucesso: {client_id}")
                    
                    # Extrair informações do bot da resposta
                    bot_info = {
                        "token": bot_token,
                        "client_id": result.get("clientId") or result.get("oauthClientId") or client_id,
                        "client_secret": client_secret,
                        "log_channel_id": log_channel_id,
                        "verified_role_id": verified_role_id,
                        "auto_role_id": auto_role_id
                    }
                    
                    return True, "Pro registrado com sucesso!", bot_info
                else:
                    error_text = await response.text()
                    logger.error(f"Erro ao registrar bot: {response.status} - {error_text}")
                    return False, f"Erro ao registrar: {error_text}", {}
    except Exception as e:
        logger.error(f"Erro ao registrar bot: {e}")
        return False, f"Erro: {str(e)}", {}

# Variável global para armaLyonar instância do bot
_bot_instance = None

def set_bot_instance(bot):
    """Define a instância do bot para uso global"""
    global _bot_instance
    _bot_instance = bot
    
    # Definir bot no WebSocketManager se existir
    ws_manager = get_websocket_manager()
    if ws_manager and bot:
        ws_manager.set_bot(bot)

def get_bot_instance():
    """Retorna a instância do bot"""
    return _bot_instance

def register_websocket_callbacks():
    """Registra callbacks de mensagens/desconexão/erro no WebSocket já conectado (não inicia conexão)."""
    try:
        ws_manager = get_websocket_manager()
        
        # Se ws_manager ainda não existe, não fazer nada (será chamado novamente depois)
        if ws_manager is None:
            logger.debug("[CloudWebSocket] WebSocket manager not initialized yet, skipping callback registration")
            return

        # Definir bot no WebSocketManager se disponível
        bot_instance = get_bot_instance()
        if bot_instance:
            ws_manager.set_bot(bot_instance)

        async def on_connect():
            logger.info("[CloudWebSocket] WebSocket callbacks registrados e conexão ativa!")

        async def on_disconnect():
            # Não logar como warning - o WebSocketManager já cuida disso
            # Apenas logar como debug para não poluir os logs
            logger.debug("[CloudWebSocket] WebSocket desconectado - loop de reconexão ativo")

        async def on_error(e):
            logger.error(f"[CloudWebSocket] Erro no WebSocket: {e}")

        async def on_message(message_data):
            event = message_data.get('event')
            data = message_data.get('data', {})
            
            logger.info(f"[DEBUG] on_message callback called with event: {event}")

            if event == 'auth_log':
                logger.info(f"[DEBUG] Processing auth_log event in callback")
                await process_auth_log(data)
            elif event == 'redeem_gift':
                await process_redeem_gift(data)
            elif event == 'recover_members':
                await process_recover_members(data)
            elif event == 'remove_verified_role':
                await process_remove_verified_role(data)

        ws_manager.set_callbacks(
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            on_error=on_error,
            on_message=on_message
        )
    except Exception as e:
        logger.error(f"[CloudWebSocket] Erro ao registrar callbacks do WebSocket: {e}")

async def process_auth_log(data):
    """Processa log de autenticação e envia para o canal de logs"""
    try:
        bot = get_bot_instance()
        if not bot:
            logger.warning("[process_auth_log] Pro instance not available, cannot send auth log")
            return
        
        from .auth_logs import send_auth_log
        success, message = await send_auth_log(bot, data)
        if success:
            logger.info(f"[process_auth_log] Auth log enviado com sucesso")
        else:
            logger.warning(f"[process_auth_log] Falha ao enviar auth log: {message}")
    except Exception as e:
        logger.error(f"[process_auth_log] Erro ao processar auth log: {e}")
        import traceback
        traceback.print_exc()

async def process_redeem_gift(data):
    """Processa resgate de gift"""
    pass

async def process_recover_members(data):
    """Processa recuperação de membros"""
    pass

async def process_remove_verified_role(data):
    """Processa remoção de cargo verificado"""
    pass

async def start_recover_members(guild_id: str, member_ids: list):
    """Inicia recuperação de membros"""
    pass

async def get_recovery_status(task_id: str):
    """Obtém status de recuperação"""
    pass
