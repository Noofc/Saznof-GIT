"""
Socket.IO Manager for Vision Pro
Uses python-socketio with automatic WebSocket + HTTP Long-Polling fallback
"""
import asyncio
import json
import logging
import traceback
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import uuid
import socket
from urllib.parse import urlparse

import socketio

logger = logging.getLogger(__name__)


class SocketIOManager:
    """Socket.IO Manager with automatic WebSocket + Polling fallback"""
    
    def __init__(self, bot):
        self.bot = bot
        self.sio = socketio.AsyncClient(
            reconnection=False,
            reconnection_attempts=0,
            reconnection_delay=1,
            reconnection_delay_max=30,
            logger=False,
            engineio_logger=False
        )
        self.connected = False
        self.using_websocket = False  # Track if using WebSocket
        self.use_polling_only = False  # Permitir upgrade para WebSocket
        
        # Configuration
        self.server_url = None
        self.jwt_secret = None
        self.bot_id = None
        
        # Event handlers
        self.handlers: Dict[str, Callable] = {}
        
        # Pending requests for request-response pattern
        self.pending_requests: Dict[str, asyncio.Future] = {}
        
        self._cloud_dns_pause_until = 0
        self._cloud_warning_shown = False
        logger.info("SocketIOManager initialized")

    async def _close_client_session(self, client=None):
        """Close Socket.IO HTTP resources before replacing/discarding a client."""
        client = client or self.sio
        http_session = None
        try:
            if hasattr(client, 'eio') and hasattr(client.eio, 'http'):
                http_session = client.eio.http
        except Exception:
            http_session = None

        try:
            if getattr(client, 'connected', False):
                await client.disconnect()
        except Exception:
            pass

        if http_session and not http_session.closed:
            try:
                await http_session.close()
            except Exception:
                pass
    
    async def initialize(self):
        """Initialize the Socket.IO manager"""
        try:
            config = self._load_config()
            
            # Cloud Data from database/cloud/data.json (prioritized)
            cloud_data = {}
            try:
                from functions.database import database as db
                cloud_data = db.get_document('cloud_data') or {}
                if not cloud_data:
                    with open('database/cloud/data.json', 'r', encoding='utf-8') as f:
                        cloud_data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cloud_data: {e}")

            ws_config = config.get('websocket_manager', {}) or config.get('websocket_cloud', {})
            
            # Prioritize server_url from config
            try:
                from modules.cloud.cloud_config import get_cloud_url
                self.server_url = get_cloud_url()
            except Exception:
                self.server_url = cloud_data.get('server_url') or ws_config.get('server_url', 'https://lyon.phanomcloud.online')
            
            # Ensure HTTP/HTTPS (Socket.IO will handle ws/wss internally)
            if self.server_url.startswith('ws://'):
                self.server_url = 'http://' + self.server_url[5:]
            elif self.server_url.startswith('wss://'):
                self.server_url = 'https://' + self.server_url[6:]
            
            self.jwt_secret = ws_config.get('jwt_secret', 'Lyon_secret_key_2026_secure_token_32bytes_minimum')
            
            # Prioritize Pro ID from cloud_data
            bot_config = config.get('bot', {})
            self.bot_id = cloud_data.get('client_id') or bot_config.get('botID', 'LyonPro')
            
            # Register Socket.IO event handlers
            self._register_socketio_handlers()
            
            # Register default application handlers
            self._register_default_handlers()
            
            # Check if configured
            client_id = cloud_data.get('client_id')
            is_configured = bool(client_id and str(client_id).strip())
            
            if ws_config.get('auto_start', True):
                if is_configured:
                    print(f"✅ [SocketIO] Pro configured, starting connection in background...")
                    # Não aguardar a conexão para não travar o bot
                    asyncio.create_task(self.connect())
                else:
                    print("ℹ️ [SocketIO] Pro not configured for Cloud Auth (cloud/data.json is empty)")
                    print("ℹ️ [SocketIO] Connection skipped - bot will run without Cloud features")
            
            logger.info("SocketIOManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize SocketIOManager: {e}")
            traceback.print_exc()
    
    def _load_config(self) -> dict:
        """Load configuration from files"""
        config = {}
        
        try:
            with open('configs/config_websocket.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load websocket config: {e}")
        
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config['bot'] = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load main config: {e}")
        
        return config
    
    def _cloud_host_available(self) -> bool:
        """Evita flood de conexao quando a Cloud/DNS esta fora do ar."""
        try:
            host = urlparse(str(self.server_url or "")).hostname
            if not host:
                return False
            socket.getaddrinfo(host, 443)
            self._cloud_warning_shown = False
            return True
        except Exception as exc:
            now = asyncio.get_event_loop().time()
            self._cloud_dns_pause_until = now + 600
            if not self._cloud_warning_shown:
                print(f"ℹ️ [SocketIO] Cloud indisponivel/DNS falhou ({exc}). Pausando tentativas por 10 minutos.")
                print("ℹ️ [SocketIO] Pro continuará online sem conexão Cloud.")
                self._cloud_warning_shown = True
            return False

    def _cloud_paused(self) -> bool:
        try:
            return asyncio.get_event_loop().time() < self._cloud_dns_pause_until
        except Exception:
            return False

    def _generate_token(self) -> str:
        """Generate JWT token for authentication"""
        try:
            import jwt
            
            discord_id = str(self.bot.user.id) if self.bot and self.bot.user else None
            
            if not discord_id:
                try:
                    with open('config.json', 'r', encoding='utf-8') as f:
                        main_config = json.load(f)
                        discord_id = main_config.get('bot', {}).get('id')
                except:
                    pass

            payload = {
                'botId': str(self.bot_id),
                'discordId': discord_id,
                'exp': datetime.utcnow() + timedelta(hours=24),
                'iat': datetime.utcnow()
            }
            
            token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
            return token
        except ImportError:
            import base64
            discord_id = str(self.bot.user.id) if self.bot and self.bot.user else None
            if not discord_id:
                try:
                    with open('config.json', 'r', encoding='utf-8') as f:
                        discord_id = json.load(f).get('bot', {}).get('id')
                except: pass

            payload_data = {
                'botId': str(self.bot_id),
                'discordId': discord_id,
            }
            return base64.b64encode(json.dumps(payload_data).encode()).decode()
    
    def _register_socketio_handlers(self):
        """Register Socket.IO connection event handlers"""
        
        @self.sio.event
        async def connect():
            self.connected = True
            transport = self.sio.transport()
            self.using_websocket = (transport == 'websocket')
            
            if self.using_websocket:
                print(f"✅ [SocketIO] Connected via WebSocket!")
                logger.info(f"Connected to server using WebSocket")
            else:
                print(f"✅ [SocketIO] Connected via {transport} (fallback)")
                logger.info(f"Connected to server using {transport}")
            
            print(f"🔗 [SocketIO] Socket ID: {self.sio.sid}")
            print(f"🔗 [SocketIO] Connected: {self.sio.connected}")
            
            # Send bot info after connection
            await self._send_bot_info()
        
        @self.sio.event
        async def disconnect():
            self.connected = False
            self.using_websocket = False
            print(f"❌ [SocketIO] Disconnected from server")
            logger.info("Disconnected from server")
        
        @self.sio.event
        async def connect_error(data):
            print(f"⚠️ [SocketIO] Connection error: {data}")
            logger.error(f"Connection error: {data}")
        
        @self.sio.on('connect_failed')
        async def connect_failed(data):
            print(f"❌ [SocketIO] Connection failed: {data}")
            logger.error(f"Connection failed: {data}")
        
        # Catch all events
        @self.sio.on('*')
        async def catch_all(event, data):
            # Ignore error events to avoid duplicate logging
            if event in ['connect_error', 'connect_failed', 'error']:
                return
            
            # Log todos os eventos recebidos
            if event not in ['connect', 'disconnect', 'connected']:
                print(f"📥 [SocketIO] Event received: {event}")
                logger.info(f"Event received: {event} - Data: {data}")
            
            # Check for response to pending request
            if event and event.endswith('_response'):
                request_id = data.get('requestId') if isinstance(data, dict) else None
                if request_id and request_id in self.pending_requests:
                    future = self.pending_requests.pop(request_id)
                    if not future.done():
                        print(f"✅ [SocketIO] Resolved request: {request_id[:8]}...")
                        future.set_result(data)
                    return
            
            # Dispatch to application handler
            if event in self.handlers:
                try:
                    print(f"🔧 [SocketIO] Dispatching to handler: {event}")
                    asyncio.create_task(self.handlers[event](data))
                except Exception as e:
                    print(f"❌ [SocketIO] Handler error for {event}: {e}")
                    logger.error(f"Handler error for {event}: {e}")
            else:
                # Log eventos sem handler
                if event not in ['connect', 'disconnect', 'connected']:
                    print(f"⚠️ [SocketIO] No handler for event: {event}")
    
    def _register_default_handlers(self):
        """Register default event handlers"""
        
        @self.on('connected')
        async def on_connected(data):
            print(f"📥 [SocketIO] Welcome message: {data}")
        
        @self.on('auth_log')
        async def on_auth_log(data):
            try:
                from modules.cloud.update_api import process_auth_log
                await process_auth_log(data)
            except ImportError:
                pass
            except Exception as e:
                logger.error(f"Error processing auth_log: {e}")
        
        @self.on('redeem_gift')
        async def on_redeem_gift(data):
            try:
                from .handlers import handle_redeem_gift
                await handle_redeem_gift(self.bot, data)
            except ImportError:
                pass
        
        @self.on('remove_verified_role')
        async def on_remove_role(data):
            try:
                from .handlers import handle_remove_role
                await handle_remove_role(self.bot, data)
            except ImportError:
                pass
    
    def on(self, event: str):
        """Decorator to register event handler"""
        def decorator(func):
            self.handlers[event] = func
            return func
        return decorator
    
    async def connect(self):
        """Connect to Socket.IO server"""
        try:
            if self._cloud_paused():
                return
            if not self._cloud_host_available():
                return

            token = self._generate_token()
            
            print(f"🔄 [SocketIO] Connecting to {self.server_url}...")
            print(f"🚀 [SocketIO] Trying WebSocket (WSS) first (preferred)...")
            
            # Tentar WebSocket primeiro (padrão)
            try:
                await asyncio.wait_for(
                    self.sio.connect(
                        self.server_url,
                        auth={'token': token},
                        transports=['websocket'],  # WebSocket primeiro
                        wait_timeout=10
                    ),
                    timeout=10.0
                )
                
                print(f"✅ [SocketIO] WebSocket connection successful!")
                self.using_websocket = True
                
                # Keep connection alive
                await self.sio.wait()
                return
                
            except (asyncio.TimeoutError, Exception) as ws_error:
                print(f"⚠️ [SocketIO] WebSocket failed: {ws_error}")
                print(f"🔄 [SocketIO] Falling back to Polling...")
                logger.warning(f"WebSocket connection failed, trying Polling: {ws_error}")
                
                # Close the previous HTTP session before replacing the client.
                await self._close_client_session(self.sio)
                
                # Criar novo cliente para Polling
                self.sio = socketio.AsyncClient(
                    reconnection=False,
                    reconnection_attempts=0,
                    reconnection_delay=1,
                    reconnection_delay_max=30,
                    logger=False,
                    engineio_logger=False
                )
                self._register_socketio_handlers()
            
            # Fallback: Conectar com Polling
            await self.sio.connect(
                self.server_url,
                auth={'token': token},
                transports=['polling'],  # Polling como fallback
                wait_timeout=10
            )
            
            print(f"✅ [SocketIO] Polling connection successful (fallback)!")
            self.using_websocket = False
            
            # NÃO tentar upgrade automático - causa múltiplas conexões
            # O Socket.IO já faz upgrade automático internamente se possível
            print(f"ℹ️  [SocketIO] Socket.IO will handle transport upgrade automatically")
            
            # Keep connection alive
            await self.sio.wait()
            
        except asyncio.TimeoutError:
            print(f"⏱️ [SocketIO] Connection timeout - continuing in background")
            logger.warning("Connection timeout")
            await self._close_client_session(self.sio)
        except Exception as e:
            print(f"⚠️ [SocketIO] Connection failed: {e}")
            print(f"ℹ️ [SocketIO] Pro will continue without Cloud connection")
            logger.error(f"Connection failed: {e}")
            await self._close_client_session(self.sio)
    
    async def _websocket_retry_background(self):
        """Tenta WebSocket em background após conectar com Polling (fallback)"""
        try:
            # Aguardar 5 segundos antes de começar tentativas
            await asyncio.sleep(5)
            
            print(f"🔄 [SocketIO] Starting WebSocket upgrade attempts (60s)...")
            start_time = asyncio.get_event_loop().time()
            attempt = 1
            
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= 60:
                    print(f"⏱️ [SocketIO] WebSocket retry period ended (60s), staying on Polling")
                    logger.info("WebSocket retry period ended, using Polling")
                    break
                
                if not self.connected or self.using_websocket:
                    break
                
                print(f"🔄 [SocketIO] WebSocket upgrade attempt #{attempt} ({int(elapsed)}s elapsed)...")
                logger.info(f"WebSocket retry attempt #{attempt}")
                attempt += 1
                
                try:
                    # Salvar estado atual
                    old_sio = self.sio
                    token = self._generate_token()
                    
                    # Criar novo cliente para tentar WebSocket
                    test_sio = socketio.AsyncClient(
                        reconnection=False,
                        logger=False,
                        engineio_logger=False
                    )
                    
                    # Tentar conectar via WebSocket
                    await asyncio.wait_for(
                        test_sio.connect(
                            self.server_url,
                            auth={'token': token},
                            transports=['websocket']
                        ),
                        timeout=8.0
                    )
                    
                    # Se chegou aqui, WebSocket funcionou!
                    print(f"✅ [SocketIO] WebSocket upgrade successful! Switching...")
                    logger.info("WebSocket upgrade successful")
                    
                    # Desconectar cliente antigo
                    if old_sio.connected:
                        await old_sio.disconnect()
                    
                    # Usar novo cliente
                    self.sio = test_sio
                    self.using_websocket = True
                    self._register_socketio_handlers()
                    
                    # Enviar bot info novamente
                    await self._send_bot_info()
                    
                    print(f"🎉 [SocketIO] Now using WebSocket (upgraded from Polling)")
                    
                    # Parar tentativas
                    break
                    
                except (asyncio.TimeoutError, Exception) as e:
                    logger.debug(f"WebSocket retry failed: {e}")
                    # Continuar tentando
                    if 'test_sio' in locals() and test_sio.connected:
                        await test_sio.disconnect()
                
                # Aguardar 5 segundos antes da próxima tentativa
                await asyncio.sleep(5)
                    
        except asyncio.CancelledError:
            logger.debug("WebSocket retry background task cancelled")
        except Exception as e:
            logger.error(f"Error in WebSocket retry background: {e}")
    
    async def _send_bot_info(self):
        """Send bot information after connecting"""
        try:
            print(f"📋 [SocketIO] Preparing to send bot info...")
            
            # Wait for connection to be fully established
            max_wait = 10  # Wait up to 10 seconds
            for i in range(max_wait * 10):
                if self.connected and self.sio.connected:
                    break
                await asyncio.sleep(0.1)
            else:
                # Timeout - connection not established
                logger.warning("Cannot send bot info: connection timeout")
                print(f"⏱️ [SocketIO] Timeout waiting for connection to stabilize")
                return
            
            # Extra small delay to ensure connection is stable
            await asyncio.sleep(0.2)
            
            config = self._load_config()
            bot_config = config.get('bot', {})
            
            guilds = []
            if self.bot.guilds:
                guilds = [str(g.id) for g in self.bot.guilds]
            
            data = {
                'bot_id': str(self.bot.user.id) if self.bot.user else None,
                'unique_id': bot_config.get('botID'),
                'server_id': bot_config.get('bot', {}).get('server'),
                'oauth_client_id': None,
                'version': 'LyonPro V12.5',
                'guilds': guilds
            }
            
            try:
                from functions.database import database as db
                cloud_config = db.get_document('cloud_data') or {}
                data['oauth_client_id'] = cloud_config.get('client_id')
                print(f"📋 [SocketIO] OAuth Client ID: {data['oauth_client_id']}")
            except Exception as e:
                print(f"⚠️ [SocketIO] Could not load cloud_data: {e}")
            
            print(f"📋 [SocketIO] Pro info prepared:")
            print(f"   - Pro ID: {data['bot_id']}")
            print(f"   - Client ID: {data['oauth_client_id']}")
            print(f"   - Guilds: {len(guilds)}")
            
            # Verify connection one more time before sending
            if self.connected and self.sio.connected:
                await self.send('bot_connected', data)
                print(f"📤 [SocketIO] Pro info sent successfully!")
            else:
                logger.warning("Cannot send bot info: connection lost")
                print(f"❌ [SocketIO] Connection lost before sending bot info")
            
        except Exception as e:
            logger.error(f"Failed to send bot info: {e}")
            print(f"❌ [SocketIO] Error sending bot info: {e}")
            import traceback
            traceback.print_exc()
    
    async def send(self, event: str, data: dict, request_id: str = None, silent: bool = False):
        """Send a message to the server"""
        if not self.connected or not self.sio.connected:
            if not silent:
                logger.warning(f"Cannot send {event}: not connected")
                print(f"⚠️ [SocketIO] Cannot send {event}: not connected")
            return False
        
        try:
            # Socket.IO handles events natively, no need for JSON wrapper
            if request_id:
                data['requestId'] = request_id
            
            print(f"📤 [SocketIO] Sending event: {event}")
            logger.info(f"Sending event: {event} - Data: {data}")
            
            await self.sio.emit(event, data)
            return True
        except Exception as e:
            logger.error(f"Failed to send {event}: {e}")
            print(f"❌ [SocketIO] Failed to send {event}: {e}")
            return False
    
    async def request(self, event: str, data: dict, timeout: float = 30.0) -> dict:
        """Send a request and wait for response"""
        request_id = str(uuid.uuid4())
        
        print(f"📤 [SocketIO] Request: {event} (ID: {request_id[:8]}...)")
        logger.info(f"Request: {event} - RequestID: {request_id} - Data: {data}")
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        
        future = loop.create_future()
        self.pending_requests[request_id] = future
        
        try:
            # Send request
            success = await self.send(event, data, request_id=request_id)
            if not success:
                self.pending_requests.pop(request_id, None)
                print(f"❌ [SocketIO] Failed to send request: {event}")
                return {'success': False, 'message': 'Failed to send request'}
            
            print(f"⏳ [SocketIO] Waiting for response: {event}_response (timeout: {timeout}s)")
            
            # Wait for response
            result = await asyncio.wait_for(future, timeout=timeout)
            print(f"✅ [SocketIO] Response received for: {event}")
            return result
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            print(f"⏱️ [SocketIO] Request timeout: {event} ({timeout}s)")
            logger.warning(f"Request timeout: {event}")
            return {'success': False, 'message': 'Request timeout'}
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            print(f"❌ [SocketIO] Request error: {event} - {e}")
            logger.error(f"Request error: {event} - {e}")
            return {'success': False, 'message': str(e)}
    
    async def disconnect(self):
        """Disconnect from server"""
        await self._close_client_session(self.sio)
        self.connected = False
        self.using_websocket = False
        logger.info("Disconnected from Socket.IO")
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self.connected and self.sio.connected
    
    # ============================================
    # API Methods
    # ============================================
    
    async def register_bot(self, main_bot_id: str, token: str, client_secret: str, client_id: str) -> dict:
        """Register bot with API"""
        return await self.request('register', {
            'mainProId': main_bot_id,
            'token': token,
            'clientSecret': client_secret,
            'clientId': client_id
        })
    
    async def Lyonhronize(self, bot_id: str, Lyon_data: dict = None) -> dict:
        """Lyonhronize data with API"""
        return await self.request('Lyonhronization', {
            'botId': bot_id,
            'LyonData': Lyon_data
        })
    
    async def get_gifts(self, bot_id: str) -> dict:
        """Get gifts for bot"""
        return await self.request('get_gifts', {'botId': bot_id})
    
    async def create_gift(self, bot_id: str, gift_data: dict) -> dict:
        """Create a new gift"""
        return await self.request('create_gift', {
            'botId': bot_id,
            'giftData': gift_data
        })
    
    async def delete_gift(self, gift_id: str) -> dict:
        """Delete a gift"""
        actual_id = gift_id
        if isinstance(gift_id, dict):
            actual_id = gift_id.get('gift_id') or gift_id.get('id')
            
        logger.info(f"🗑️ [SocketIO] Requesting deletion of gift: '{actual_id}'")
        return await self.request('delete_gift', {'giftId': str(actual_id), 'gift_id': str(actual_id)})
    
    async def update_definitions(self, definitions: dict) -> dict:
        """Update bot definitions"""
        config = self._load_config()
        bot_config = config.get('bot', {})
        
        cloud_config = {}
        try:
            from functions.database import database as db
            cloud_config = db.get_document('cloud_data') or {}
        except Exception:
            pass
        
        return await self.request('update_definitions', {
            'bot_id': cloud_config.get('client_id'),
            'definitions': definitions,
            'main_server_id': bot_config.get('bot', {}).get('server')
        })
    
    async def check_user_verification(self, bot_id: str, user_id: str) -> dict:
        """Check if user is verified"""
        return await self.request('check_user_verification', {
            'botId': bot_id,
            'userId': user_id
        })
    
    async def list_members(self, bot_id: str) -> dict:
        """List members for bot"""
        return await self.request('list_members', {'botId': bot_id})
    
    async def check_auth_count(self, bot_id: str) -> dict:
        """Check authenticated member count"""
        print(f"🔍 [check_auth_count] Requesting count for bot: {bot_id}")
        result = await self.request('check_auth_count', {'botId': bot_id})
        print(f"📊 [check_auth_count] Result: {result}")
        return result
    
    async def recover_data(self, bot_id: str) -> dict:
        """Recover bot data"""
        return await self.request('recover', {'botId': bot_id})
    
    # ============================================
    # Backwards Compatibility Methods
    # ============================================
    
    def set_bot(self, bot):
        """Set bot instance"""
        self.bot = bot
    
    async def start(self):
        """Start connection"""
        await self.initialize()
    
    async def stop(self):
        """Stop connection"""
        await self.disconnect()
    
    def set_callbacks(self, on_connect=None, on_disconnect=None, on_error=None, on_message=None):
        """Set callbacks (backwards compatibility - uses event handlers instead)"""
        if on_connect:
            @self.sio.event
            async def connect():
                self.connected = True
                await on_connect()
        
        if on_disconnect:
            @self.sio.event
            async def disconnect():
                self.connected = False
                await on_disconnect()
        
        if on_error:
            @self.sio.event
            async def connect_error(data):
                await on_error(data)
        
        if on_message:
            # Store message callback for dispatching all events
            self._on_message_callback = on_message
    
    async def resend_bot_connected(self):
        """Resend bot_connected event (backwards compatibility)"""
        await self._send_bot_info()
