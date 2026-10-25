from disnake.ext import commands
import disnake
from .saldo_manager import SaldoManager
from functions.emoji import emoji

class Economia(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.saldo_manager = SaldoManager()
    
    @commands.slash_command(name="economia", description="Gerenciar sua economia")
    async def economia(self, inter: disnake.AppCommandInteraction):
        """Painel principal de economia"""
        usuario = await self.saldo_manager.get_usuario(inter.author.id)
        
        embed = disnake.Embed(
            title=f"{emoji.wallet} Sua Economia",
            description="Gerencie seu saldo e finanças",
            color=disnake.Colour.gold()
        )
        
        embed.add_field(
            name=f"{emoji.coin} Saldo Principal",
            value=f"```{usuario['saldo']:.2f}```",
            inline=False
        )
        
        embed.add_field(
            name=f"{emoji.lock} Saldo Congelado",
            value=f"```{usuario['saldo_congelado']:.2f}```",
            inline=True
        )
        
        embed.add_field(
            name=f"{emoji.star} Reputação",
            value=f"```{usuario['reputacao']}```",
            inline=True
        )
        
        embed.add_field(
            name=f"{emoji.chart} Nível",
            value=f"```{usuario['nivel']}```",
            inline=True
        )
        
        emprestimos_ativos = len([e for e in usuario.get("emprestimos", []) if e["status"] == "ativo"])
        embed.add_field(
            name=f"{emoji.card} Empréstimos Ativos",
            value=f"```{emprestimos_ativos}```",
            inline=True
        )
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Transferir", emoji=emoji.arrow, custom_id="btn_transferir", style=disnake.ButtonStyle.blurple),
                disnake.ui.Button(label="Emprestar", emoji=emoji.coin, custom_id="btn_emprestar", style=disnake.ButtonStyle.success),
                disnake.ui.Button(label="Histórico", emoji=emoji.receipt, custom_id="btn_historico", style=disnake.ButtonStyle.secondary),
            )
        ]
        
        await inter.response.send_message(embed=embed, components=components)
    
    @commands.slash_command(name="transferir", description="Transferir saldo para outro usuário")
    async def transferir(
        self,
        inter: disnake.AppCommandInteraction,
        usuario: disnake.User,
        valor: float
    ):
        """Transfere saldo com taxa"""
        if valor <= 0:
            await inter.response.send_message(f"{emoji.wrong} Valor deve ser maior que zero!", ephemeral=True)
            return
        
        sucesso, mensagem = await self.saldo_manager.transferir(inter.author.id, usuario.id, valor)
        
        embed = disnake.Embed(
            title="Transferência de Saldo",
            description=mensagem,
            color=disnake.Colour.green() if sucesso else disnake.Colour.red()
        )
        
        await inter.response.send_message(embed=embed, ephemeral=True)
    
    @commands.slash_command(name="emprestar", description="Emprestar saldo com juros")
    async def emprestar(
        self,
        inter: disnake.AppCommandInteraction,
        valor: float
    ):
        """Empresta saldo ao usuário"""
        if valor <= 0:
            await inter.response.send_message(f"{emoji.wrong} Valor deve ser maior que zero!", ephemeral=True)
            return
        
        sucesso, mensagem = await self.saldo_manager.emprestar(inter.author.id, valor)
        
        embed = disnake.Embed(
            title=f"{emoji.card} Empréstimo",
            description=mensagem,
            color=disnake.Colour.green() if sucesso else disnake.Colour.red()
        )
        
        await inter.response.send_message(embed=embed, ephemeral=True)
    
    @commands.slash_command(name="ranking_economia", description="Ver ranking de usuários por saldo")
    async def ranking_economia(self, inter: disnake.AppCommandInteraction):
        """Exibe o ranking de economia"""
        ranking = await self.saldo_manager.get_ranking()
        
        embed = disnake.Embed(
            title=f"{emoji.trophy} Ranking de Economia",
            color=disnake.Colour.gold()
        )
        
        descricao = ""
        for pos, (user_id, saldo) in enumerate(ranking, 1):
            try:
                user = await self.bot.fetch_user(user_id)
                descricao += f"**{pos}º** - {user.mention}: `{saldo:.2f}`\n"
            except:
                descricao += f"**{pos}º** - ID {user_id}: `{saldo:.2f}`\n"
        
        embed.description = descricao or "Nenhum usuário ainda"
        await inter.response.send_message(embed=embed)
