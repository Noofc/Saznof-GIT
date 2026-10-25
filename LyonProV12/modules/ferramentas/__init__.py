from disnake.ext import commands
from .cog import Ferramentas

def setup(bot: commands.Bot):
    bot.add_cog(Ferramentas(bot))
