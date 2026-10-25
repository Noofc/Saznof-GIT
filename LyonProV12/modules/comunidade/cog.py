from disnake.ext import commands
import disnake
from .manager import ComunidadeManager
from functions.emoji import emoji

class Comunidade(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = ComunidadeManager()
    
    @commands.slash_command(name="perfil_comunidade", description="Ver seu perfil de comunidade")
    async def perfil(self, inter: disnake.AppCommandInteraction, usuario: disnake.User = None):
        """Exibe o perfil de um usuário"""
        user_id = usuario.id if usuario else inter.author.id
        perfil = await self.manager.get_perfil_usuario(user_id)
        
        embed = disnake.Embed(
            title=f"👤 Perfil - {perfil['titulo']}",
            color=disnake.Colour.blue()
        )
        
        embed.set_thumbnail(url=(await self.bot.fetch_user(user_id)).avatar.url)
        
        embed.add_field(
            name="⭐ Nível",
            value=f"```{perfil['nivel']}```",
            inline=True
        )
        
        embed.add_field(
            name="📊 Pontos",
            value=f"```{perfil['pontos']}```",
            inline=True
        )
        
        embed.add_field(
            name="💎 Reputação",
            value=f"```{perfil['reputacao']}```",
            inline=True
        )
        
        embed.add_field(
            name="🏆 Conquistas",
            value=f"```{len(perfil.get('conquistas', []))}```",
            inline=True
        )
        
        embed.add_field(
            name="👥 Amigos",
            value=f"```{len(perfil.get('amigos', []))}```",
            inline=True
        )
        
        embed.add_field(
            name="📍 Conectados",
            value=f"```{perfil['conectados']}```",
            inline=True
        )
        
        if perfil.get("bio"):
            embed.add_field(
                name="Bio",
                value=perfil["bio"],
                inline=False
            )
        
        # Listar conquistas
        if perfil.get("conquistas"):
            conquistas_str = ""
            for c_id in perfil["conquistas"]:
                if c_id in self.manager.CONQUISTAS:
                    c = self.manager.CONQUISTAS[c_id]
                    conquistas_str += f"{c['emoji']} {c['nome']}\n"
            
            if conquistas_str:
                embed.add_field(
                    name="🏆 Conquistas Desbloqueadas",
                    value=conquistas_str,
                    inline=False
                )
        
        await inter.response.send_message(embed=embed)
    
    @commands.slash_command(name="ranking_comunidade", description="Ver ranking da comunidade")
    async def ranking_comunidade(self, inter: disnake.AppCommandInteraction):
        """Exibe ranking geral"""
        ranking = await self.manager.get_ranking_geral()
        
        embed = disnake.Embed(
            title="🏆 Ranking da Comunidade",
            color=disnake.Colour.gold()
        )
        
        descricao = ""
        for pos, (user_id, dados) in enumerate(ranking[:10], 1):
            try:
                user = await self.bot.fetch_user(user_id)
                descricao += f"**{pos}º** {user.mention} - Nível **{dados['nivel']}** | {dados['pontos']} ⭐\n"
            except:
                descricao += f"**{pos}º** ID {user_id} - Nível **{dados['nivel']}** | {dados['pontos']} ⭐\n"
        
        embed.description = descricao or "Ranking vazio"
        await inter.response.send_message(embed=embed)
    
    @commands.slash_command(name="eventos", description="Ver eventos ativos")
    async def eventos(self, inter: disnake.AppCommandInteraction):
        """Exibe eventos ativos"""
        eventos = await self.manager.get_eventos_ativos()
        
        embed = disnake.Embed(
            title="📢 Eventos Ativos",
            color=disnake.Colour.purple()
        )
        
        if not eventos:
            embed.description = "Nenhum evento ativo no momento"
            await inter.response.send_message(embed=embed)
            return
        
        for evento in eventos[:5]:
            embed.add_field(
                name=f"🎯 {evento['nome']}",
                value=f"{evento['descricao']}\n💰 Prêmio: **{evento['premio']:.2f}**\n👥 Participantes: {len(evento.get('participantes', []))}",
                inline=False
            )
        
        await inter.response.send_message(embed=embed)
    
    @commands.slash_command(name="adicionar_amigo", description="Adicionar um amigo")
    async def adicionar_amigo(self, inter: disnake.AppCommandInteraction, usuario: disnake.User):
        """Adiciona um amigo"""
        sucesso, mensagem = await self.manager.adicionar_amigo(inter.author.id, usuario.id)
        
        embed = disnake.Embed(
            title="Amigos",
            description=mensagem,
            color=disnake.Colour.green() if sucesso else disnake.Colour.red()
        )
        
        await inter.response.send_message(embed=embed, ephemeral=True)
