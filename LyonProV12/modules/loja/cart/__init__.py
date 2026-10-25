from disnake.ext import commands


def setup(bot: commands.Bot):
    from .buy_modal import BuyProductButton
    from .cancel import CancelCheckout
    from .cart_handlers import CartButtonHandlers
    from .cleanup import CartCleanup
    from .copy_handler import CopyProductHandler
    from .roles_temp_manager import RolesTempManager

    bot.add_cog(BuyProductButton(bot))
    bot.add_cog(CancelCheckout(bot))
    bot.add_cog(CartCleanup(bot))
    bot.add_cog(CopyProductHandler(bot))
    bot.add_cog(CartButtonHandlers(bot))
    bot.add_cog(RolesTempManager(bot))


__all__ = ["setup"]
