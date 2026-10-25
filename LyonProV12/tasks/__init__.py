from disnake.ext import commands
from disnake.ext.commands.errors import ExtensionNotFound

from functions.plan import should_load_module


TASK_EXTENSIONS_BY_PLAN = (
    ("automations", ("tasks.automations.cog",)),
    ("backup", ("tasks.backup",)),
    ("protection", ("tasks.protection",)),
    ("bot", ("tasks.bot.cog", "tasks.bot.autorole")),
    ("giveaways", ("tasks.giveaways.cog",)),
)


def setup(bot: commands.Bot):
    for plan_key, extensions in TASK_EXTENSIONS_BY_PLAN:
        if not should_load_module(plan_key):
            continue

        for extension in extensions:
            try:
                bot.load_extension(extension)
            except ExtensionNotFound:
                print(f"[Tasks] Extensao opcional nao encontrada: {extension}")

    # Nubank IMAP monitor fica opcional para evitar conexoes sem configuracao.
    # bot.load_extension("tasks.payments.nubank_monitor")
