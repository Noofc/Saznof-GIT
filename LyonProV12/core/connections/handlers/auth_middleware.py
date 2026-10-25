"""Authorization middleware for WebSocket handlers"""

import logging
from functions.database import database as db

logger = logging.getLogger(__name__)

class AuthorizationError(Exception):
    """Raised when user is not authorized to access a handler"""
    pass

def check_owner_authorization(payload: dict) -> bool:
    """
    Verifica se o usuário que está faLyondo a requisição é o dono do bot.
    
    Args:
        payload: Dados da requisição contendo user_id
        
    Returns:
        bool: True se autorizado, False caso contrário
        
    Raises:
        AuthorizationError: Se o usuário não tem permissão
    """
    try:
        # Obter user_id do payload
        user_id = payload.get('user_id')
        
        if not user_id:
            logger.warning("Authorization check failed: no user_id in payload")
            raise AuthorizationError("user_id não fornecido na requisição")
        
        # Obter owner_id do config.json
        config = db.obter("config.json") or {}
        owner_id = config.get("bot", {}).get("owner")
        
        if not owner_id:
            logger.error("Authorization check failed: owner_id not configured")
            raise AuthorizationError("owner_id não configurado no sistema")
        
        # Converter para string para comparação
        user_id_str = str(user_id)
        owner_id_str = str(owner_id)
        
        # Verificar se é o dono
        if user_id_str != owner_id_str:
            logger.warning(f"Authorization denied: user {user_id} is not owner {owner_id}")
            raise AuthorizationError("Apenas o dono do bot pode acessar esta funcionalidade")
        
        logger.debug(f"Authorization granted for owner {user_id}")
        return True
        
    except AuthorizationError:
        raise
    except Exception as e:
        logger.error(f"Error checking authorization: {e}")
        raise AuthorizationError(f"Erro ao verificar autorização: {str(e)}")


def require_owner(handler):
    """
    Decorator para handlers que requerem autorização de owner.
    
    Usage:
        @require_owner
        async def my_handler(bot, payload):
            # handler code
    """
    async def wrapper(bot, payload):
        try:
            # Verificar autorização
            check_owner_authorization(payload)
            
            # Se autorizado, executar handler
            return await handler(bot, payload)
            
        except AuthorizationError as e:
            # Retornar erro de autorização
            logger.warning(f"Authorization failed for handler {handler.__name__}: {e}")
            raise
            
    return wrapper


# Lista de handlers que requerem autorização de owner
PROTECTED_HANDLERS = {
    # Protection handlers
    'protection.getConfig',
    'protection.updateConfig',
    'protection.getWhitelist',
    'protection.getBlacklist',
    
    # Cloud handlers
    'cloud.getConfig',
    'cloud.updateCredentials',
    'cloud.updateLogChannel',
    'cloud.updateVerifiedRole',
    'cloud.getStats',
    'cloud.getAuthLogs',
    'cloud.getGifts',
    'cloud.getGift',
    'cloud.createGift',
    'cloud.updateGift',
    'cloud.deleteGift',
    'cloud.getTasks',
    'cloud.getTask',
    'cloud.createTask',
    'cloud.updateTask',
    'cloud.deleteTask',
    'cloud.getVerificationMessage',
    'cloud.updateVerificationMessage',
    'cloud.updateMessageStyle',
    'cloud.resetVerificationMessage',
    'cloud.sendVerificationMessage',
    'cloud.connectWebSocket',
    'cloud.disconnectWebSocket',
    'cloud.getWebSocketStatus',
}


def is_protected_handler(handler_name: str) -> bool:
    """
    Verifica se um handler requer autorização de owner.
    
    Args:
        handler_name: Nome do handler (ex: 'protection.getConfig')
        
    Returns:
        bool: True se o handler é protegido
    """
    return handler_name in PROTECTED_HANDLERS
