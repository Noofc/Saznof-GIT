import time

import disnake

from functions.database import database
from functions.emoji import emoji
from functions.system_logs import send_system_log


async def log_restart(bot: disnake.Client):
    try:
        info = database.obter("config.json") or {}
        for guild in getattr(bot, "guilds", []) or []:
            await send_system_log(
                bot,
                guild,
                title="Reinicializacao do bot",
                system="Sistema",
                description=(
                    f"{emoji.reload} O **Lyon Pro** foi reiniciado.\n"
                    f"{emoji.robot} Versao atual: `{info.get('version', 'N/A')}`\n"
                    f"{emoji.calendar} **Data:** <t:{int(time.time())}:f> (<t:{int(time.time())}:R>)"
                ),
            )
    except Exception as e:
        import traceback

        print(f"Ocorreu um erro em log_restart: {e}")
        traceback.print_exc()
