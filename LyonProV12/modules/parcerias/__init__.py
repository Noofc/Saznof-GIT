from disnake.ext import commands
from .cog import Parcerias

def setup(bot: commands.Bot):
    bot.add_cog(Parcerias(bot))
