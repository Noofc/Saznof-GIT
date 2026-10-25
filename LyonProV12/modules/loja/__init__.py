import importlib

from disnake.ext import commands


SETUP_MODULES = (
    "modules.loja.products",
    "modules.loja.cart",
    "modules.loja.logs",
    "modules.loja.personalization",
    "modules.loja.clientes",
    "modules.loja.preferences",
    "modules.loja.saldo",
    "modules.loja.cashback",
    "modules.loja.gifts",
    "modules.loja.cloud_sales",
)


def setup(bot: commands.Bot):
    from .cog import Loja

    bot.add_cog(Loja(bot))
    for module_path in SETUP_MODULES:
        importlib.import_module(module_path).setup(bot)


__all__ = ["setup"]
