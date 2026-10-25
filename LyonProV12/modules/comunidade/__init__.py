from disnake.ext import commands
from .cog import Comunidade

def setup(bot: commands.Bot):
    bot.add_cog(Comunidade(bot))
