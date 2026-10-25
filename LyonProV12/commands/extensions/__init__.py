from disnake.ext import commands
from . import boost, systemgen

def setup(bot: commands.Bot):
    boost.setup(bot)
    systemgen.setup(bot)

__all__ = ["setup"]
