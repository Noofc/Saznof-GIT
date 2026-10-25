from .cog import Settings
from .cargos import setup as cargos_setup
from .canais import setup as canais_setup
from .payments import setup as payments_setup
from .antifake import setup as antifake_setup
from .extensions.cog import setup as extensions_panel_setup
from .extensions.boost.cog import setup as boost_setup
from .notificacoes.cog import setup as notificacoes_setup
from .bloquear.cog import setup as blacklist_setup
from .permissoes.cog import setup as permissoes_setup

def setup(bot):
    bot.add_cog(Settings(bot))
    cargos_setup(bot)
    canais_setup(bot)
    payments_setup(bot)
    antifake_setup(bot)
    extensions_panel_setup(bot)
    boost_setup(bot)
    notificacoes_setup(bot)
    blacklist_setup(bot)
    permissoes_setup(bot)

__all__ = ["setup"]