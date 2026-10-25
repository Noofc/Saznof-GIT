from disnake.ext import commands
from .cog import GiftLyon

def setup(bot: commands.Bot):
    bot.add_cog(GiftLyon(bot))

__all__ = ["setup"]
