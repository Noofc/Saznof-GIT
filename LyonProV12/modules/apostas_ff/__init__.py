from disnake.ext import commands
from .cog import ApostasFF

def setup(bot: commands.Bot):
    bot.add_cog(ApostasFF(bot))
