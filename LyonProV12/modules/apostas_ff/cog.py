from disnake.ext import commands
import disnake
from .manager import ApostasFFManager
from functions.emoji import emoji
import asyncio

class ApostasFF(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = ApostasFFManager()
    
    @commands.slash_command(name="apostas_ff", description="Sistema de apostas em Free Fire")
    async def apostas_ff(self, inter: disnake.AppCommandInteraction):
        """Painel de apostas Free Fire"""
        partidas = await self.manager.listar_partidas_abertas()
        
        embed = disnake.Embed(
            title=f"{emoji.controller} Apostas Free Fire",
            description="Escolha uma partida para apostar",
            color=disnake.Colour.red()
        )
        
        if not partidas:
            embed.description = f"{emoji.wrong} Nenhuma partida disponível"
            await inter.response.send_message(embed=embed)
            return
        
        for partida in partidas[:5]:
            poder1 = f"{emoji.green} Favorito" if partida["poder1"] > partida["poder2"] else f"{emoji.red} Underdog"
            poder2 = f"{emoji.red} Underdog" if partida["poder1"] > partida["poder2"] else f"{emoji.green} Favorito"
            
            embed.add_field(
                name=f"{partida['equipe1']} vs {partida['equipe2']}",
                value=f"{poder1} vs {poder2}\nPoder: {partida['poder1']} vs {partida['poder2']}\nApostado: {partida['apostas_total']:.2f}",
                inline=False
            )
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Ver Mais", emoji=emoji.search, custom_id="btn_mais_partidas", style=disnake.ButtonStyle.blurple),
                disnake.ui.Button(label="Minhas Apostas", emoji=emoji.swords, custom_id="btn_minhas_apostas", style=disnake.ButtonStyle.success),
            )
        ]
        
        await inter.response.send_message(embed=embed, components=components)
    
    @commands.slash_command(name="apostar_ff", description="Apostar em uma partida")
    async def apostar_ff(
        self,
        inter: disnake.AppCommandInteraction,
        partida_id: str,
        valor: float,
        escolha: str
    ):
        """Realiza uma aposta"""
        sucesso, mensagem, premio = await self.manager.fazer_aposta(
            inter.author.id,
            partida_id,
            valor,
            escolha
        )
        
        embed = disnake.Embed(
            title="Aposta Free Fire",
            description=mensagem,
            color=disnake.Colour.green() if sucesso else disnake.Colour.red()
        )
        
        if sucesso and premio:
            embed.add_field(
                name=f"{emoji.diamond} Possível Prêmio",
                value=f"```{premio:.2f}```"
            )
        
        await inter.response.send_message(embed=embed, ephemeral=True)
    
    @commands.slash_command(name="criar_partida_ff", description="Criar uma partida (Admin)")
    async def criar_partida_ff(
        self,
        inter: disnake.AppCommandInteraction,
        equipe1: str,
        equipe2: str,
        poder1: int,
        poder2: int
    ):
        """Cria uma partida para apostas (apenas admin)"""
        if not inter.author.guild_permissions.administrator:
            await inter.response.send_message(f"{emoji.wrong} Apenas administradores", ephemeral=True)
            return
        
        # Data de início: 30 minutos a partir de agora
        data_inicio = (datetime.now() + timedelta(minutes=30)).isoformat()
        
        sucesso, mensagem, partida_id = await self.manager.criar_partida(
            equipe1, equipe2, data_inicio, poder1, poder2
        )
        
        embed = disnake.Embed(
            title="Criar Partida",
            description=mensagem,
            color=disnake.Colour.green() if sucesso else disnake.Colour.red()
        )
        
        if sucesso:
            embed.add_field(name="ID da Partida", value=f"```{partida_id}```")
        
        await inter.response.send_message(embed=embed, ephemeral=True)

# Import necessário
from datetime import datetime, timedelta
