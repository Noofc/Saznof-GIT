"""
WebSocket initialization event
"""

import disnake
from disnake.ext import commands
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class WebSocketReady(commands.Cog):
    """Handle WebSocket initialization when bot is ready"""
    
    def __init__(self, bot):
        self.bot = bot
        self.websocket_initialized = False
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize WebSocket connection when bot is ready"""
        
        # Prevent multiple initializations
        if self.websocket_initialized:
            return
            
        self.websocket_initialized = True
        
        # Store bot start time
        if not hasattr(self.bot, 'start_time'):
            self.bot.start_time = datetime.now()
        
        logger.info(f"Pro {self.bot.user.name} is ready!")
        logger.info(f"Pro ID: {self.bot.user.id}")
        logger.info(f"Guilds: {len(self.bot.guilds)}")
        
        # Initialize WebSocket connection
        try:
            from connections import initialize as init_connection
            
            # Initialize connection manager (respects config_socket.json)
            websocket_manager = await init_connection(self.bot)
            
            logger.info("Connection Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Connection Manager: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    @commands.Cog.listener()
    async def on_disconnect(self):
        """Handle bot disconnect"""
        logger.warning("Pro disconnected from Discord")
        
        # Notify WebSocket manager if connected
        if hasattr(self.bot, 'websocket_manager') and self.bot.websocket_manager:
            try:
                await self.bot.websocket_manager.emit_event('bot_disconnected', {
                    'timestamp': datetime.now().isoformat()
                })
            except:
                pass
    
    @commands.Cog.listener()
    async def on_resumed(self):
        """Handle bot resume after disconnect"""
        logger.info("Pro connection resumed")
        
        # Notify WebSocket manager if connected
        if hasattr(self.bot, 'websocket_manager') and self.bot.websocket_manager:
            try:
                await self.bot.websocket_manager.emit_event('bot_resumed', {
                    'timestamp': datetime.now().isoformat()
                })
            except:
                pass
    
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if hasattr(self.bot, 'websocket_manager') and self.bot.websocket_manager:
            asyncio.create_task(self.bot.websocket_manager.disconnect())

def setup(bot):
    bot.add_cog(WebSocketReady(bot))
