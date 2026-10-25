from .cog import Personalizacao
from .edit_mode import EditMode
from .edit_panel_mode import EditPanelMode
from .edit_colors import EditColorsCog

def setup(bot):
    bot.add_cog(Personalizacao(bot))
    bot.add_cog(EditColorsCog(bot))

__all__ = ["setup"]