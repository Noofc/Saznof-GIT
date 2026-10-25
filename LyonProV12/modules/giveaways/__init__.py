from disnake.ext import commands
from .cog import Giveaways
from .raffles import RafflesCog

def setup(bot: commands.Bot):
    bot.add_cog(Giveaways(bot))
    bot.add_cog(RafflesCog(bot))

__all__ = ["setup"]
