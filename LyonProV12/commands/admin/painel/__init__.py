from disnake.ext import commands

from .interaction import PainelCommand


def setup(bot: commands.Bot):
    bot.add_cog(PainelCommand(bot))
