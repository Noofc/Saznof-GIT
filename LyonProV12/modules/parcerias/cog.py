from disnake.ext import commands
import disnake
from .manager import ParceriasManager
from functions.emoji import emoji

class Parcerias(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = ParceriasManager()
    
    @commands.slash_command(name="parceria", description="Gerenciar parcerias")
    async def parceria(self, inter: disnake.AppCommandInteraction):
        """Painel de parcerias"""
        parceria = await self.manager.get_parceria(inter.author.id)
        
        if not parceria:
            embed = disnake.Embed(
                title="Você ainda não tem parceria",
                description="Crie uma parceria para começar a ganhar comissões!",
                color=disnake.Colour.blue()
            )
            
            components = [
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Criar Parceria",
                        emoji=emoji.partner,
                        custom_id="btn_criar_parceria",
                        style=disnake.ButtonStyle.success
                    )
                )
            ]
            
            await inter.response.send_message(embed=embed, components=components, ephemeral=True)
            return
        
        embed = disnake.Embed(
            title=f"{emoji.partner} Parceria: {parceria['nome']}",
            color=disnake.Colour.green()
        )
        
        embed.add_field(
            name=f"{emoji.chart} Vendas Totais",
            value=f"```{parceria['vendas_totais']:.2f}```",
            inline=True
        )
        
        embed.add_field(
            name=f"{emoji.coin} Comissões Ganhas",
            value=f"```{parceria['comissoes_ganhas']:.2f}```",
            inline=True
        )
        
        embed.add_field(
            name=f"{emoji.star} Nível",
            value=f"```{parceria['nivel']}```",
            inline=True
        )
        
        embed.add_field(
            name=f"{emoji.members} Afiliados",
            value=f"```{len(parceria.get('afiliados', []))}```",
            inline=True
        )
        
        embed.add_field(
            name=f"{emoji.calendar} Status",
            value=f"```{parceria['status']}```",
            inline=True
        )
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Meus Afiliados", emoji=emoji.members, custom_id="btn_afiliados", style=disnake.ButtonStyle.blurple),
                disnake.ui.Button(label="Sacar Comissões", emoji=emoji.coin, custom_id="btn_sacar", style=disnake.ButtonStyle.success),
                disnake.ui.Button(label="Histórico", emoji=emoji.receipt, custom_id="btn_hist_parceria", style=disnake.ButtonStyle.secondary),
            )
        ]
        
        await inter.response.send_message(embed=embed, components=components)
    
    @commands.slash_command(name="criar_parceria", description="Criar uma nova parceria")
    async def criar_parceria(
        self,
        inter: disnake.AppCommandInteraction,
        nome: str,
        tipo: str
    ):
        """Cria uma parceria"""
        sucesso, mensagem = await self.manager.criar_parceria(inter.author.id, nome, tipo)
        
        embed = disnake.Embed(
            title="Parceria",
            description=mensagem,
            color=disnake.Colour.green() if sucesso else disnake.Colour.red()
        )
        
        await inter.response.send_message(embed=embed, ephemeral=True)
    
    @commands.slash_command(name="ranking_parceiros", description="Ver ranking de parceiros")
    async def ranking_parceiros(self, inter: disnake.AppCommandInteraction):
        """Exibe ranking de parceiros"""
        ranking = await self.manager.get_ranking_parceiros()
        
        embed = disnake.Embed(
            title=f"{emoji.partner} Ranking de Parceiros",
            color=disnake.Colour.gold()
        )
        
        descricao = ""
        for pos, (user_id, comissoes) in enumerate(ranking, 1):
            try:
                user = await self.bot.fetch_user(user_id)
                descricao += f"**{pos}º** - {user.mention}: `{comissoes:.2f}`\n"
            except:
                descricao += f"**{pos}º** - ID {user_id}: `{comissoes:.2f}`\n"
        
        embed.description = descricao or "Nenhum parceiro ainda"
        await inter.response.send_message(embed=embed)
