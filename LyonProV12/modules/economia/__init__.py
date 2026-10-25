from disnake.ext import commands
from .cog import Economia

def setup(bot: commands.Bot):
    bot.add_cog(Economia(bot))
