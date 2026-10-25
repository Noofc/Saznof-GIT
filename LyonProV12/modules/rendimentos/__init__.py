from disnake.ext import commands
from .cog import RendimentosLyon

def setup(bot: commands.Bot):
    bot.add_cog(RendimentosLyon(bot))