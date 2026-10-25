import disnake
import asyncio
from disnake.ext import commands
from .status_rotator import status_rotator_task
from .change_bio_task import change_bio_task
from .bio_monitor_task import bio_monitor_task
from .server_showcase import server_showcase_task
from core.change_bio import change_bio
from functions.database import database as db

class StatusRotatorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._bio_updated_once = False

    @commands.Cog.listener("on_ready")
    async def on_ready(self):
        if not status_rotator_task.is_running():
            status_rotator_task.start(self.bot)
        else:
            status_rotator_task.restart(self.bot)
        
        # Atualiza a bio imediatamente ao ligar o bot
        config = db.obter("config.json") or {}
        update_bio = bool(config.get("updateProBio", False))

        if update_bio and not self._bio_updated_once:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, change_bio)
                print("Bio atualizada ao iniciar o bot")
                self._bio_updated_once = True
            except Exception as e:
                print(f"Erro ao atualizar bio ao iniciar: {e}")
        
        # Inicia a task de atualização de bio a cada 1 hora
        if update_bio and not change_bio_task.is_running():
            change_bio_task.start(self.bot)
        
        # Inicia a task de monitoramento de bio a cada 30 segundos
        if update_bio and not bio_monitor_task.is_running():
            bio_monitor_task.start(self.bot)
        
        # Inicia a task de server showcase (envia info do servidor para o site)
        if not server_showcase_task.is_running():
            server_showcase_task.start(self.bot)

def setup(bot: commands.Bot):
    bot.add_cog(StatusRotatorCog(bot))
