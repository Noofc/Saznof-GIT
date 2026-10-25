import disnake
from disnake.ext import commands
from functions.database import database as db
from functions.message import message, embed_message
from functions.utils import utils


class GerenciarCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def autocomplete_produto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        """Autocomplete para produtos"""
        products = db.get_document("loja_products") or {}
        
        if not products:
            return ["Nenhum produto encontrado"]
        
        # Filtrar produtos pelo nome
        filtered = []
        for product_id, product in products.items():
            product_name = product.get("name", "Sem nome")
            if user_input.lower() in product_name.lower():
                filtered.append((product_name, product_id))
        
        # Ordenar por nome
        filtered.sort(key=lambda x: x[0].lower())
        
        # Retornar até 25 resultados (limite do Discord)
        return [f"{name}" for name, _ in filtered[:25]]

    async def autocomplete_campo(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        """Autocomplete para campos do produto selecionado"""
        # Pegar o produto selecionado
        produto_nome = inter.filled_options.get("produto", "")
        
        if not produto_nome:
            return ["Selecione um produto primeiro"]
        
        # Buscar produto pelo nome
        products = db.get_document("loja_products") or {}
        product_id = None
        for pid, p in products.items():
            if p.get("name", "") == produto_nome:
                product_id = pid
                break
        
        if not product_id:
            return ["Produto não encontrado"]
        
        # Buscar campos do produto
        product = products.get(product_id, {})
        campos = product.get("campos", {})
        
        if not campos:
            return ["Nenhum campo encontrado"]
        
        # Filtrar campos pelo nome
        filtered = []
        for campo_id, campo in campos.items():
            campo_name = campo.get("name", "Sem nome")
            if user_input.lower() in campo_name.lower():
                filtered.append((campo_name, campo_id))
        
        # Ordenar por nome
        filtered.sort(key=lambda x: x[0].lower())
        
        # Retornar até 25 resultados (limite do Discord)
        return [f"{name}" for name, _ in filtered[:25]]

    @commands.slash_command(
        name="gerenciar",
        description="Gerencia produtos e itens da loja",
        guild_ids=utils.obter_guild_ids()
    )
    async def gerenciar(self, inter: disnake.ApplicationCommandInteraction):
        """Comando base para gerenciar"""
        pass

    @gerenciar.sub_command(
        name="produto",
        description="Abre o painel de gerenciamento de um produto específico"
    )
    async def gerenciar_produto(
        self,
        inter: disnake.ApplicationCommandInteraction,
        produto: str = commands.Param(
            description="Nome do produto",
            autocomplete=autocomplete_produto
        )
    ):
        """Subcomando para gerenciar um produto específico"""
        # Buscar produto pelo nome
        products = db.get_document("loja_products") or {}
        
        product_id = None
        for pid, p in products.items():
            if p.get("name", "") == produto:
                product_id = pid
                break
        
        if not product_id:
            mode = db.get_document("custom_mode").get("mode")
            msg_handler = embed_message if mode == "embed" else message
            await msg_handler.error(inter, f"Produto **{produto}** não encontrado.", send=True)
            return
        
        # Importar e chamar o painel de configuração
        from modules.loja.products.product.configurar import ConfigurarProduto
        mode = db.get_document("custom_mode").get("mode")
        msg_handler = embed_message if mode == "embed" else message
        
        await msg_handler.wait(inter, send=True)
        
        panel_data = ConfigurarProduto.panel(inter, product_id)
        
        if mode == "embed":
            await inter.edit_original_message(content=None, **panel_data)
        else:
            await inter.edit_original_message(**panel_data)

    @gerenciar.sub_command(
        name="item",
        description="Abre o painel de gerenciamento de um campo/item específico"
    )
    async def gerenciar_item(
        self,
        inter: disnake.ApplicationCommandInteraction,
        produto: str = commands.Param(
            description="Nome do produto",
            autocomplete=autocomplete_produto
        ),
        campo: str = commands.Param(
            description="Nome do campo/item",
            autocomplete=autocomplete_campo
        )
    ):
        """Subcomando para gerenciar um campo/item específico de um produto"""
        # Buscar produto pelo nome
        products = db.get_document("loja_products") or {}
        
        product_id = None
        for pid, p in products.items():
            if p.get("name", "") == produto:
                product_id = pid
                break
        
        if not product_id:
            mode = db.get_document("custom_mode").get("mode")
            msg_handler = embed_message if mode == "embed" else message
            await msg_handler.error(inter, f"Produto **{produto}** não encontrado.", send=True)
            return
        
        # Buscar campo pelo nome
        product = products.get(product_id, {})
        campos = product.get("campos", {})
        
        campo_id = None
        for cid, c in campos.items():
            if c.get("name", "") == campo:
                campo_id = cid
                break
        
        if not campo_id:
            mode = db.get_document("custom_mode").get("mode")
            msg_handler = embed_message if mode == "embed" else message
            await msg_handler.error(inter, f"Campo **{campo}** não encontrado no produto **{produto}**.", send=True)
            return
        
        # Importar e chamar o painel de gerenciamento de campo
        try:
            from modules.loja.products.product.campos.fields.configurar import ConfigurarCampo
            mode = db.get_document("custom_mode").get("mode")
            msg_handler = embed_message if mode == "embed" else message
            
            await msg_handler.wait(inter, send=True)
            
            panel_data = ConfigurarCampo.panel(inter, product_id, campo_id)
            
            if mode == "embed":
                await inter.edit_original_message(content=None, **panel_data)
            else:
                await inter.edit_original_message(**panel_data)
        except Exception as e:
            print(f"❌ Erro ao abrir painel de campo: {e}")
            import traceback
            traceback.print_exc()
            mode = db.get_document("custom_mode").get("mode")
            msg_handler = embed_message if mode == "embed" else message
            await msg_handler.error(inter, f"Erro ao abrir painel do campo: {str(e)}", send=False)


def setup(bot: commands.Bot):
    bot.add_cog(GerenciarCommand(bot))
