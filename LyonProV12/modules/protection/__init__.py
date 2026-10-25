def setup(bot):
    bot.load_extension("modules.protection.cog")
    bot.load_extension("modules.protection.protecaogeral")
    bot.load_extension("modules.protection.privatizacoes")
    bot.load_extension("modules.protection.permsinternas.cog")

__all__ = ["setup"]
