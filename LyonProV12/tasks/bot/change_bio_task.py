from disnake.ext import tasks
import asyncio
from core.change_bio import change_bio

# Variável global para armaLyonar a referência do bot
_bot_instance = None

@tasks.loop(hours=6)
async def change_bio_task(bot):
    """Atualiza a bio do bot periodicamente sem bater rate limit."""
    global _bot_instance
    _bot_instance = bot
    
    try:
        # Executa a função síncrona em um executor para não bloquear o event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, change_bio)
    except Exception as e:
        print(f"Erro ao atualizar bio: {e}")

@change_bio_task.before_loop
async def before_change_bio_task():
    """Aguarda o bot estar pronto antes de iniciar a task."""
    if _bot_instance:
        await _bot_instance.wait_until_ready()

