"""
Cliente WebSocket para API de Pagamentos
Recebe notificacoes em tempo real de pagamentos aprovados
"""
import asyncio
import logging
from typing import Optional, Callable, Dict, Any
import socketio
from functions.database import database as db

logger = logging.getLogger(__name__)


class PaymentWebSocketClient:
    """Cliente WebSocket para notificacoes de pagamento"""
    
    def __init__(self, bot):
        self.bot = bot
        self.server_url = self._get_api_url()
        self.sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=2,
            reconnection_delay_max=30,
            logger=False,
            engineio_logger=False
        )
        self.connected = False
        self.bot_id = None
        self.bot_token = None
        self.on_payment_approved: Optional[Callable] = None
        self._setup_events()
    
    def _get_api_url(self) -> str:
        """Obtem URL da API do config"""
        try:
            config = db.obter("configs/config_api.json") or {}
            api_url = config.get("api", "localhost:22222")
            if not api_url.startswith("http"):
                api_url = f"http://{api_url}"
            return api_url
        except Exception:
            return "http://localhost:22222"

    def _setup_events(self):
        """Configurar eventos do Socket.IO"""
        
        @self.sio.event
        async def connect():
            self.connected = True
            transport = self.sio.transport() if hasattr(self.sio, 'transport') else 'unknown'
            logger.info(f"[PaymentWS] Conectado via {transport}")
            print(f"[PaymentWS] Connected via {transport}")
            if self.bot_id and self.bot_token:
                await self.authenticate(self.bot_id, self.bot_token)
        
        @self.sio.event
        async def disconnect():
            self.connected = False
            logger.warning("[PaymentWS] Desconectado")
            print(f"[PaymentWS] Disconnected")
        
        @self.sio.event
        async def connected(data):
            logger.info(f"Servidor: {data.get('message')}")
        
        @self.sio.event
        async def auth_success(data):
            logger.info(f"Autenticado na API de Pagamentos")
            logger.info(f"Pro ID: {data.get('botId')}")
        
        @self.sio.event
        async def auth_error(data):
            logger.error(f"Erro de autenticacao: {data.get('message')}")
        
        @self.sio.on('payment:update')
        async def on_payment_update(data):
            payment_id = data.get('payment_id')
            status = data.get('status')
            logger.info(f"Pagamento atualizado: {payment_id} - Status: {status}")
            if status == 'approved' and self.on_payment_approved:
                try:
                    await self.on_payment_approved(data)
                except Exception as e:
                    logger.error(f"Erro no callback payment_approved: {e}")
        
        @self.sio.event
        async def watching_payment(data):
            logger.info(f"Monitorando pagamento: {data.get('paymentId')}")
        
        @self.sio.event
        async def error(data):
            logger.error(f"Erro: {data.get('message')}")

    async def connect(self) -> bool:
        """Conectar ao servidor via Socket.IO (WebSocket)"""
        try:
            if self.connected:
                logger.warning("Ja conectado a API de Pagamentos")
                return True
            
            logger.info(f"[PaymentWS] Conectando a API: {self.server_url}")
            print(f"[PaymentWS] Connecting to {self.server_url}...")
            
            await asyncio.wait_for(
                self.sio.connect(self.server_url, transports=['websocket']),
                timeout=15.0
            )
            print(f"[PaymentWS] ✅ Connected via Socket.IO (WebSocket)")
            return True
            
        except Exception as e:
            logger.info(f"[PaymentWS] API de pagamentos indisponivel: {e}")
            print(f"[PaymentWS] API indisponivel ({e}). Pro continua sem WebSocket de pagamentos.")
            await self.disconnect()
            return False
    
    async def disconnect(self):
        """Desconectar do servidor"""
        try:
            # Capturar sessão HTTP ANTES do disconnect
            http_session = None
            try:
                if hasattr(self.sio, 'eio') and hasattr(self.sio.eio, 'http'):
                    http_session = self.sio.eio.http
            except Exception:
                pass
            
            if self.sio.connected:
                await self.sio.disconnect()
            
            # Fechar sessão HTTP capturada
            if http_session and not http_session.closed:
                try:
                    await http_session.close()
                except Exception:
                    pass
            
            self.connected = False
            logger.info("Desconectado da API de Pagamentos")
        except Exception as e:
            logger.error(f"Erro ao desconectar: {e}")

    async def authenticate(self, bot_id: str, bot_token: str):
        """Autenticar bot"""
        try:
            self.bot_id = bot_id
            self.bot_token = bot_token
            
            if not self.connected:
                logger.warning("[PaymentWS] Nao conectado, aguardando conexao...")
                for _ in range(10):
                    if self.connected:
                        break
                    await asyncio.sleep(0.5)
                
                if not self.connected:
                    logger.error("[PaymentWS] Timeout aguardando conexao para autenticar")
                    return
            
            await self.sio.emit('bot:auth', {
                'botId': bot_id,
                'botToken': bot_token
            })
            
        except Exception as e:
            logger.error(f"[PaymentWS] Erro ao autenticar: {e}")
    
    async def watch_payment(self, payment_id: str):
        """Monitorar um pagamento especifico"""
        try:
            if not self.connected:
                logger.warning("Nao conectado a API de Pagamentos")
                return
            
            await self.sio.emit('watch:payment', {
                'paymentId': payment_id
            })
            
        except Exception as e:
            logger.error(f"Erro ao monitorar pagamento: {e}")
    
    async def unwatch_payment(self, payment_id: str):
        """Parar de monitorar um pagamento"""
        try:
            if not self.connected:
                return
            
            await self.sio.emit('unwatch:payment', {
                'paymentId': payment_id
            })
            
        except Exception as e:
            logger.error(f"Erro ao parar de monitorar: {e}")
    
    def set_payment_approved_callback(self, callback: Callable):
        """Define callback para quando pagamento for aprovado"""
        self.on_payment_approved = callback
    
    def is_connected(self) -> bool:
        """Verificar se esta conectado"""
        return self.connected


_ws_client: Optional[PaymentWebSocketClient] = None


def get_ws_client() -> Optional[PaymentWebSocketClient]:
    """Obter instancia global do cliente"""
    return _ws_client


def initialize_ws_client(bot) -> PaymentWebSocketClient:
    """Inicializar cliente WebSocket"""
    global _ws_client
    _ws_client = PaymentWebSocketClient(bot)
    return _ws_client


async def start_ws_client(bot_id: str, bot_token: str):
    """Iniciar e conectar cliente WebSocket"""
    if _ws_client is None:
        raise RuntimeError("Cliente WebSocket nao inicializado. Use initialize_ws_client() primeiro.")
    
    if not await _ws_client.connect():
        return False
    await _ws_client.authenticate(bot_id, bot_token)
    return True


async def stop_ws_client():
    """Parar cliente WebSocket"""
    if _ws_client:
        await _ws_client.disconnect()
