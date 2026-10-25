"""
Socket.IO connections module
Respects config_socket.json for websocket vs http mode
"""
import json
import os

from .socketio_manager import SocketIOManager
from .ws_manager import WSManager
from .http_polling import HTTPPollingManager
from .hybrid_manager import HybridConnectionManager

# Global instance
ws_manager = None

def _load_socket_config():
    """Load socket configuration"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'config_socket.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {'websocket': True}

def setup(bot):
    """Setup connection manager based on config_socket.json"""
    global ws_manager
    
    config = _load_socket_config()
    use_websocket = config.get('websocket', True)
    
    if use_websocket:
        # Use Socket.IO Manager (servers use Socket.IO protocol)
        print("🔧 [Connection] Mode: WebSocket (Socket.IO)")
        ws_manager = SocketIOManager(bot)
    else:
        # Use HTTP Polling directly
        print("🔧 [Connection] Mode: HTTP")
        ws_manager = HTTPPollingManager(bot)
    
    # Store reference in bot
    bot.ws_manager = ws_manager
    
    return ws_manager

async def initialize(bot):
    """Initialize and connect based on config"""
    global ws_manager
    
    if ws_manager is None:
        ws_manager = setup(bot)
    
    await ws_manager.initialize()
    
    # For HTTP Polling, also call connect() to start the connection
    if isinstance(ws_manager, HTTPPollingManager):
        print("🔄 [Connection] Starting HTTP connection...")
        await ws_manager.connect()
    
    # Log connection status
    if ws_manager.is_connected():
        print("✅ [Connection] Connected via Socket.IO")
    else:
        print("⏳ [Connection] Connecting in background...")
    
    return ws_manager

def get_manager():
    """Get connection manager instance"""
    return ws_manager

# Backwards compatibility
websocket_manager = None
WebSocketManager = SocketIOManager
