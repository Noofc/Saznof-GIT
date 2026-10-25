from disnake.ext import commands
from . import cupom_em_massa, entregar, perfil, ranking, sincronizar_clientes, gerenciar_produto
from . import gift

def setup(bot: commands.Bot):
    """Carrega todos os comandos de vendas"""
    cupom_em_massa.setup(bot)
    entregar.setup(bot)
    perfil.setup(bot)
    ranking.setup(bot)
    sincronizar_clientes.setup(bot)
    gerenciar_produto.setup(bot)
    gift.setup(bot)
