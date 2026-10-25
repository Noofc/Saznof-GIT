"""
Boost WebSocket Manager for Lyon Pro
Uses pure websockets library (same pattern as Cloud ws_manager)
"""
import asyncio
import json
import logging
import hashlib
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import uuid

try:
    import websockets
    from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
except ImportError:
    raise ImportError("Please install websockets: pip install websockets")

logger = logging.getLogger(__name__)


class BoostWebSocketManager:
    """WebSocket Manager for Boost API using pure websockets"""

    def __init__(self, server_url: str = "wss://boost.Lyonapplications.com.br", reconnect_interval: int = 5):
        self.server_url = server_url
        self.reconnect_interval = reconnect_interval
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.connecting = False
        self.should_reconnect = True
        
        # Pro instance
        self.bot = None
        self.api_key = None
        
        # Pending responses (requestId -> Future)
        self.pending_responses: Dict[str, asyncio.Future] = {}
        
        # Event handlers
        self.handlers: Dict[str, Callable] = {}
        
        # Tasks
        self._listen_task = None
        self._reconnect_task = None
        self.reconnect_attempts = 0
        
        # Configure logger
        if not logger.handlers:
            handler = logging.StreamHandler()
          #  handler.setFormatter(logging.Formatter('[BoostWS] %(message)s'))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def set_bot(self, bot):
        """Set bot instance and generate API key"""
        self.bot = bot
        
        if bot and hasattr(bot, 'user') and bot.user:
            bot_id = str(bot.user.id)
            self.api_key = self._generate_api_key(bot_id)
           # logger.info(f"API Key gerada para Boost: {self.api_key[:8]}...")

    def _generate_api_key(self, bot_id: str) -> str:
        """Generate unique API key for bot"""
        salt = "Lyon_boost_api_2024"
        unique_string = f"{bot_id}_{salt}"
        return hashlib.sha256(unique_string.encode()).hexdigest()

    async def start(self):
        """Start WebSocket connection"""
        self.should_reconnect = True
        await self.connect()

    async def stop(self):
        """Stop WebSocket connection"""
        self.should_reconnect = False
        await self.disconnect()

    async def connect(self):
        """Connect to WebSocket server with automatic reconnection"""
        if self.connecting or self.connected:
            return
        
        self.connecting = True
        max_attempts = 5
        
        while self.reconnect_attempts < max_attempts and not self.connected:
            try:
                self.reconnect_attempts += 1
               # logger.info(f"🔄 Connecting to Boost WebSocket: {self.server_url} (attempt {self.reconnect_attempts})")
                
                # Connect with timeout
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        self.server_url,
                        ping_interval=30,
                        ping_timeout=10,
                        close_timeout=5
                    ),
                    timeout=15
                )
                
                self.connected = True
                self.connecting = False
                self.reconnect_attempts = 0
                
               # logger.info("✅ Connected to Boost WebSocket!")
                
                # Start listener
                self._listen_task = asyncio.create_task(self._listen())
                
                # Send bot info
                await self._send_bot_info()
                
                return
                
            except asyncio.TimeoutError:
                pass
              #  logger.warning(f"⏳ Connection timeout (attempt {self.reconnect_attempts})")
            except ConnectionRefusedError:
                pass
               # logger.warning(f"❌ Connection refused - server may be offline")
            except Exception as e:
                pass
             #   logger.error(f"❌ Connection error: {e}")
            
            # Wait before retry with exponential backoff
            if self.should_reconnect and self.reconnect_attempts < max_attempts:
                wait_time = min(self.reconnect_interval * (2 ** (self.reconnect_attempts - 1)), 60)
               # logger.info(f"⏳ Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
        
        self.connecting = False
        if not self.connected:
            pass
            #logger.warning("⚠️ Could not connect to Boost WebSocket after all attempts")

    async def _send_bot_info(self):
        """Send bot information after connecting"""
        if not self.bot or not self.api_key:
            return
        
        try:
            bot_id = str(self.bot.user.id) if self.bot.user else None
            
            # Load unique_id from config
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    unique_id = config.get("botID", "LyonPro")
            except Exception:
                unique_id = "LyonPro"
            
            await self.send('bot_connected', {
                'bot_id': bot_id,
                'unique_id': unique_id,
                'api_key': self.api_key
            })
            
            logger.info(f"📤 Pro registered with API key: {self.api_key[:8]}...")
            
        except Exception as e:
            logger.error(f"❌ Error sending bot info: {e}")

    async def _listen(self):
        """Listen for incoming messages"""
        logger.info("🎧 Listener started")
        
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    event = data.get('event')
                    payload = data.get('data', {})
                    request_id = payload.get('requestId')
                    
                    # Check for response to pending request
                    if event and event.endswith('_response') and request_id:
                        if request_id in self.pending_responses:
                            future = self.pending_responses.pop(request_id)
                            if not future.done():
                                future.set_result(payload)
                            continue
                    
                    # Call registered handler if exists
                    if event in self.handlers:
                        try:
                            await self.handlers[event](payload)
                        except Exception as e:
                            logger.error(f"❌ Error in handler {event}: {e}")
                            
                except json.JSONDecodeError:
                    logger.warning("⚠️ Received invalid JSON")
                except Exception as e:
                    logger.error(f"❌ Error processing message: {e}")
                    
        except ConnectionClosedOK:
            logger.info("🔌 Connection closed normally")
        except ConnectionClosedError as e:
            logger.warning(f"🔌 Connection closed with error: {e}")
        except Exception as e:
            logger.error(f"❌ Listener error: {e}")
        finally:
            self.connected = False
            if self.should_reconnect:
                asyncio.create_task(self._schedule_reconnect())

    async def _schedule_reconnect(self):
        """Schedule reconnection attempt"""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        
        wait_time = min(self.reconnect_interval * (2 ** self.reconnect_attempts), 60)
        logger.info(f"🔄 Reconnecting in {wait_time}s...")
        await asyncio.sleep(wait_time)
        
        if self.should_reconnect:
            await self.connect()

    async def send(self, event: str, data: dict, request_id: str = None) -> bool:
        """Send a message to the server"""
        if not self.connected or not self.ws:
            logger.warning("⚠️ Not connected, cannot send message")
            return False
        
        try:
            message = {
                'event': event,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
            
            if request_id:
                message['requestId'] = request_id
            
            await self.ws.send(json.dumps(message))
            return True
            
        except Exception as e:
            logger.error(f"❌ Error sending message: {e}")
            self.connected = False
            return False

    async def request(self, event: str, data: dict, timeout: float = 30.0) -> dict:
        """Send a request and wait for response"""
        request_id = str(uuid.uuid4())
        
        # Add request_id to data
        data_with_id = {**data, 'requestId': request_id}
        
        # Create future for response
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_responses[request_id] = future
        
        try:
            # Send request
            message = {
                'event': event,
                'data': data_with_id,
                'requestId': request_id,
                'timestamp': datetime.now().isoformat()
            }
            
            if not self.connected or not self.ws:
                return {'success': False, 'message': 'Not connected'}
            
            await self.ws.send(json.dumps(message))
            
            # Wait for response
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            self.pending_responses.pop(request_id, None)
            return {'success': False, 'message': 'Request timeout'}
        except Exception as e:
            self.pending_responses.pop(request_id, None)
            return {'success': False, 'message': str(e)}

    async def disconnect(self):
        """Disconnect from server"""
        self.should_reconnect = False
        
        if self._listen_task:
            self._listen_task.cancel()
            
        if self.ws:
            await self.ws.close()
            self.ws = None
            
        self.connected = False
        logger.info("🔌 Disconnected from Boost WebSocket")

    def is_connected(self) -> bool:
        """Check if connected"""
        return self.connected

    def on(self, event: str):
        """Decorator to register event handler"""
        def decorator(func):
            self.handlers[event] = func
            return func
        return decorator

    # ============================================
    # GIFT METHODS
    # ============================================

    async def create_gift(self, gift_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new gift"""
        if not self.api_key:
            return {'success': False, 'message': 'API key não configurada'}
        
        return await self.request('create_gift', {
            'api_key': self.api_key,
            'gift_data': gift_data
        })

    async def get_gifts(self) -> Dict[str, Any]:
        """Get list of gifts"""
        if not self.api_key:
            return {'success': False, 'message': 'API key não configurada'}
        
        return await self.request('get_gifts', {
            'api_key': self.api_key
        })

    async def update_gift(self, gift_id: str, gift_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing gift"""
        if not self.api_key:
            return {'success': False, 'message': 'API key não configurada'}
        
        return await self.request('update_gift', {
            'api_key': self.api_key,
            'gift_id': gift_id,
            'gift_data': gift_data
        })

    async def delete_gift(self, gift_id: str) -> Dict[str, Any]:
        """Delete a gift"""
        if not self.api_key:
            return {'success': False, 'message': 'API key não configurada'}
        
        return await self.request('delete_gift', {
            'api_key': self.api_key,
            'gift_id': gift_id
        })

    async def delete_all_gifts(self) -> Dict[str, Any]:
        """Delete all gifts"""
        if not self.api_key:
            return {'success': False, 'message': 'API key não configurada'}
        
        return await self.request('delete_all_gifts', {
            'api_key': self.api_key
        })

    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information"""
        return {
            'connected': self.connected,
            'server_url': self.server_url,
            'api_key': f"{self.api_key[:8]}..." if self.api_key else None
        }


# Global instance
_boost_ws_manager = None


def get_websocket_manager() -> BoostWebSocketManager:
    """Get global WebSocket manager instance"""
    global _boost_ws_manager
    if _boost_ws_manager is None:
        _boost_ws_manager = BoostWebSocketManager()
    return _boost_ws_manager
