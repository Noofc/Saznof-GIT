"""
Hybrid Connection Manager
Tries WebSocket first, falls back to HTTP Polling if WebSocket fails
"""
import asyncio
import logging
from typing import Optional

from .ws_manager import WSManager
from .http_polling import HTTPPollingManager

logger = logging.getLogger(__name__)


class HybridConnectionManager:
    """
    Manages connection using WebSocket with HTTP Polling fallback
    Configurable via configs/config_socket.json
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.ws_manager = WSManager(bot)
        self.polling_manager = HTTPPollingManager(bot)
        self.active_manager = None
        self.connection_mode = None  # 'websocket' or 'http'
        
        # Configuration from config_socket.json
        self.use_websocket = True
        self.max_ws_retries = 2
        self.http_fallback = True
    
    def _load_socket_config(self):
        """Load configuration from config_socket.json"""
        import json
        import os
        
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'config_socket.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            self.use_websocket = config.get('websocket', True)
            self.max_ws_retries = config.get('max_ws_retries', 2)
            self.http_fallback = config.get('http_fallback', True)
            
            print(f"📋 [Hybrid] Config loaded: websocket={self.use_websocket}, max_retries={self.max_ws_retries}, fallback={self.http_fallback}")
            
        except FileNotFoundError:
            print("⚠️ [Hybrid] config_socket.json not found, using defaults")
        except Exception as e:
            print(f"⚠️ [Hybrid] Error loading config: {e}")
    
    async def initialize(self):
        """Initialize both managers"""
        # Load configuration first
        self._load_socket_config()
        
        await self.ws_manager.initialize()
        await self.polling_manager.initialize()
        
        # If websocket is disabled, go directly to HTTP
        if not self.use_websocket:
            print("🔧 [Hybrid] WebSocket disabled in config, using HTTP directly")
            if await self._connect_http():
                return
            else:
                print("❌ [Hybrid] HTTP connection failed!")
                return
        
        # Try WebSocket with retries
        print(f"🔄 [Hybrid] Trying WebSocket connection (max {self.max_ws_retries} attempts)...")
        
        for attempt in range(1, self.max_ws_retries + 1):
            print(f"🔄 [Hybrid] WebSocket attempt {attempt}/{self.max_ws_retries}...")
            
            ws_task = asyncio.create_task(self._try_websocket())
            
            try:
                # Wait up to 10 seconds for WebSocket
                await asyncio.wait_for(ws_task, timeout=10.0)
                
                if self.ws_manager.is_connected():
                    self.active_manager = self.ws_manager
                    self.connection_mode = 'websocket'
                    print("✅ [Hybrid] Using WebSocket connection")
                    return
            except asyncio.TimeoutError:
                print(f"⏱️ [Hybrid] WebSocket attempt {attempt} timeout")
            except Exception as e:
                print(f"❌ [Hybrid] WebSocket attempt {attempt} failed: {e}")
            
            # Small delay before next attempt
            if attempt < self.max_ws_retries:
                await asyncio.sleep(1)
        
        # Fallback to HTTP if enabled
        if self.http_fallback:
            print("🔄 [Hybrid] Falling back to HTTP...")
            if await self._connect_http():
                return
        
        print("❌ [Hybrid] All connection methods failed!")
    
    async def _connect_http(self):
        """Connect via HTTP"""
        if await self.polling_manager.connect():
            self.active_manager = self.polling_manager
            self.connection_mode = 'http'
            print("✅ [Hybrid] Using HTTP connection")
            return True
        return False
    
    async def _try_websocket(self):
        """Try to connect via WebSocket"""
        try:
            asyncio.create_task(self.ws_manager.connect())
            # Wait a bit to see if connection succeeds
            for _ in range(50):  # 5 seconds total
                if self.ws_manager.is_connected():
                    return True
                await asyncio.sleep(0.1)
            return False
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            return False
    
    def is_connected(self) -> bool:
        """Check if connected"""
        if self.active_manager:
            return self.active_manager.is_connected()
        return False
    
    def get_connection_mode(self) -> Optional[str]:
        """Get current connection mode"""
        return self.connection_mode
    
    # Proxy all methods to active manager
    async def send(self, event: str, data: dict, request_id: str = None):
        if self.active_manager:
            return await self.active_manager.send(event, data, request_id)
        return False
    
    async def request(self, event: str, data: dict, timeout: float = 30.0) -> dict:
        if self.active_manager:
            return await self.active_manager.request(event, data, timeout)
        return {'success': False, 'message': 'Not connected'}
    
    async def disconnect(self):
        if self.active_manager:
            await self.active_manager.disconnect()
    
    # API Methods
    async def register_bot(self, main_bot_id: str, token: str, client_secret: str, client_id: str) -> dict:
        if self.active_manager:
            return await self.active_manager.register_bot(main_bot_id, token, client_secret, client_id)
        return {'success': False, 'message': 'Not connected'}
    
    async def Lyonhronize(self, bot_id: str, Lyon_data: dict = None) -> dict:
        if self.active_manager:
            return await self.active_manager.Lyonhronize(bot_id, Lyon_data)
        return {'success': False, 'message': 'Not connected'}
    
    async def get_gifts(self, bot_id: str) -> dict:
        if self.active_manager:
            return await self.active_manager.get_gifts(bot_id)
        return {'success': False, 'message': 'Not connected'}
    
    async def create_gift(self, bot_id: str, gift_data: dict) -> dict:
        if self.active_manager:
            return await self.active_manager.create_gift(bot_id, gift_data)
        return {'success': False, 'message': 'Not connected'}
    
    async def delete_gift(self, gift_id: str) -> dict:
        if self.active_manager:
            return await self.active_manager.delete_gift(gift_id)
        return {'success': False, 'message': 'Not connected'}
    
    async def update_definitions(self, definitions: dict) -> dict:
        if self.active_manager:
            return await self.active_manager.update_definitions(definitions)
        return {'success': False, 'message': 'Not connected'}
    
    async def check_user_verification(self, bot_id: str, user_id: str) -> dict:
        if self.active_manager:
            return await self.active_manager.check_user_verification(bot_id, user_id)
        return {'success': False, 'message': 'Not connected'}
    
    async def list_members(self, bot_id: str) -> dict:
        if self.active_manager:
            return await self.active_manager.list_members(bot_id)
        return {'success': False, 'message': 'Not connected'}
    
    async def check_auth_count(self, bot_id: str) -> dict:
        if self.active_manager:
            return await self.active_manager.check_auth_count(bot_id)
        return {'success': False, 'message': 'Not connected'}
    
    async def recover_data(self, bot_id: str) -> dict:
        if self.active_manager:
            return await self.active_manager.recover_data(bot_id)
        return {'success': False, 'message': 'Not connected'}
