from disnake.ext import commands
from .cog import ClientesLyon

def setup(bot: commands.Bot):
    bot.add_cog(ClientesLyon(bot))