from .cog import TaskThemesCog


def setup(bot):
    bot.add_cog(TaskThemesCog(bot))
