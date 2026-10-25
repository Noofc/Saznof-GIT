from functions.database import database as db
from disnake.ext import tasks
import disnake
import itertools

def get_status_obj(status_type: str) -> disnake.Status:
    status_map = {
        "online": disnake.Status.online,
        "idle": disnake.Status.idle,
        "dnd": disnake.Status.dnd,
        "streaming": disnake.Status.streaming
    }
    return status_map.get(status_type, disnake.Status.online)

@tasks.loop(seconds=5)
async def status_rotator_task(bot: disnake.Client):
    database = db.get_document("custom_status")
    status_obj = get_status_obj(database.get("type", "online"))

    names = database.get("names")
    if not names:  # Backwards compatibility
        name = database.get("name")
        names = [name] if name else []

    if not names:
        await bot.change_presence(status=status_obj, activity=None)
        return

    # Initialize or update cycler
    if not hasattr(bot, "_status_cycler") or getattr(bot, "_status_names", []) != names:
        bot._status_names = names
        bot._status_cycler = itertools.cycle(names)
    
    status_name = next(bot._status_cycler)

    if status_obj == disnake.Status.streaming:
        activity = disnake.Streaming(name=status_name, url="https://twitch.tv/discord")
    else:
        activity = disnake.CustomActivity(name=status_name)

    await bot.change_presence(status=status_obj, activity=activity)
