from disnake.ext import commands
import disnake
from .manager import FerramentasEconomia, AnalisadorMercado
from functions.emoji import emoji

class Ferramentas(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ferramentas = FerramentasEconomia()
        self.analisador = AnalisadorMercado()
    
    @commands.slash_command(name="ferramentas_economia", description="Ferramentas econômicas avançadas")
    async def ferramentas_economia(self, inter: disnake.AppCommandInteraction):
        """Acessa ferramentas de análise"""
        options = [
            disnake.SelectOption(label="Calcular Lucro", value="lucro", emoji="💰"),
            disnake.SelectOption(label="Juros Compostos", value="juros", emoji="📈"),
            disnake.SelectOption(label="ROI Calculator", value="roi", emoji="💹"),
            disnake.SelectOption(label="Meu Relatório", value="relatorio", emoji="📊"),
            disnake.SelectOption(label="Análise de Mercado", value="mercado", emoji="📉"),
        ]
        
        embed = disnake.Embed(
            title="🛠️ Ferramentas de Economia",
            description="Selecione uma ferramenta abaixo",
            color=disnake.Colour.blue()
        )
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="ferramentas_select",
                    placeholder="Escolha uma ferramenta",
                    options=options
                )
            )
        ]
        
        await inter.response.send_message(embed=embed, components=components)
    
    @commands.slash_command(name="calcular_lucro", description="Calcular lucro de parceria")
    async def calcular_lucro(
        self,
        inter: disnake.AppCommandInteraction,
        vendas: float,
        comissao: float = 10.0
    ):
        """Calcula lucro esperado"""
        resultado = self.ferramentas.calcular_lucro_parceria(
            vendas,
            comissao / 100
        )
        
        embed = disnake.Embed(
            title="💰 Cálculo de Lucro",
            color=disnake.Colour.green()
        )
        
        embed.add_field(
            name="Vendas",
            value=f"```{resultado['vendas']:.2f}```",
            inline=True
        )
        
        embed.add_field(
            name="Taxa de Comissão",
            value=f"```{resultado['comissao_percentual']:.1f}%```",
            inline=True
        )
        
        embed.add_field(
            name="Comissão Bruta",
            value=f"```{resultado['comissao_bruta']:.2f}```",
            inline=True
        )
        
        embed.add_field(
            name="Taxa da Casa",
            value=f"```{resultado['taxa']:.2f}```",
            inline=True
        )
        
        embed.add_field(
            name="💚 Lucro Líquido",
            value=f"```{resultado['comissao_liquida']:.2f}```",
            inline=True
        )
        
        await inter.response.send_message(embed=embed)
    
    @commands.slash_command(name="calcular_juros", description="Calcular juros compostos")
    async def calcular_juros(
        self,
        inter: disnake.AppCommandInteraction,
        valor: float,
        dias: int = 7,
        taxa_diaria: float = 2.0
    ):
        """Calcula juros compostos"""
        resultado = self.ferramentas.calcular_juros_compostos(
            valor,
            taxa_diaria / 100,
            dias
        )
        
        embed = disnake.Embed(
            title="📈 Juros Compostos",
            color=disnake.Colour.gold()
        )
        
        embed.add_field(
            name="Principal",
            value=f"```{resultado['principal']:.2f}```"
        )
        
        embed.add_field(
            name="Taxa Diária",
            value=f"```{resultado['taxa_diaria']:.2f}%```"
        )
        
        embed.add_field(
            name="Período",
            value=f"```{resultado['dias']} dias```"
        )
        
        embed.add_field(
            name="Juros Gerados",
            value=f"```{resultado['juros']:.2f}```",
            inline=False
        )
        
        embed.add_field(
            name="💰 Total a Pagar",
            value=f"```{resultado['montante_total']:.2f}```",
            inline=False
        )
        
        await inter.response.send_message(embed=embed)
    
    @commands.slash_command(name="meu_relatorio", description="Gerar seu relatório de economia")
    async def meu_relatorio(self, inter: disnake.AppCommandInteraction):
        """Gera relatório completo"""
        relatorio = await self.ferramentas.gerar_relatorio_usuario(inter.author.id)
        
        embed = disnake.Embed(
            title="📊 Seu Relatório de Economia",
            color=disnake.Colour.blue()
        )
        
        # Economia
        embed.add_field(
            name="💰 Economia",
            value=f"Saldo: `{relatorio['economia']['saldo']:.2f}`\nNível: `{relatorio['economia']['nivel']}`\nReputação: `{relatorio['economia']['reputacao']}`",
            inline=True
        )
        
        # Comunidade
        embed.add_field(
            name="👥 Comunidade",
            value=f"Nível: `{relatorio['comunidade']['nivel']}`\nPontos: `{relatorio['comunidade']['pontos']}`\nAmigos: `{relatorio['comunidade']['amigos']}`",
            inline=True
        )
        
        # Parcerias
        embed.add_field(
            name="🤝 Parcerias",
            value=f"Status: `{relatorio['parcerias']['nome']}`\nVendas: `{relatorio['parcerias']['vendas_totais']:.2f}`\nComissões: `{relatorio['parcerias']['comissoes_ganhas']:.2f}`",
            inline=True
        )
        
        await inter.response.send_message(embed=embed)
    
    @commands.slash_command(name="analise_mercado", description="Analisar tendências de mercado")
    async def analise_mercado(self, inter: disnake.AppCommandInteraction):
        """Análise de mercado geral"""
        análise_apostas = await self.analisador.analisar_apostas_ff()
        análise_economia = await self.analisador.analisar_economia_geral()
        
        embed = disnake.Embed(
            title="📉 Análise de Mercado",
            color=disnake.Colour.purple()
        )
        
        if "erro" not in análise_apostas:
            embed.add_field(
                name="🎮 Apostas Free Fire",
                value=f"Total Apostado: `{análise_apostas['total_apostado']:.2f}`\nUsuários: `{análise_apostas['total_usuarios']}`\nMédia/Aposta: `{análise_apostas['media_aposta']:.2f}`",
                inline=False
            )
        
        if "erro" not in análise_economia:
            embed.add_field(
                name="💹 Economia Geral",
                value=f"Total na Economia: `{análise_economia['total_economia']:.2f}`\nMédia de Saldo: `{análise_economia['media_saldo']:.2f}`\nUsuários Ativos: `{análise_economia['usuarios_ativos']}`",
                inline=False
            )
        
        await inter.response.send_message(embed=embed)

    @commands.slash_command(name="meta_poupanca", description="Criar meta de poupança")
    async def meta_poupanca(
        self,
        inter: disnake.AppCommandInteraction,
        valor_meta: float,
        prazo_dias: int = 30
    ):
        """Cria uma meta de poupança"""
        resultado = await self.ferramentas.calcular_meta_poupanca(
            inter.author.id,
            valor_meta,
            prazo_dias
        )
        
        embed = disnake.Embed(
            title="🎯 Meta de Poupança",
            color=disnake.Colour.blue()
        )
        
        embed.add_field(
            name="Meta",
            value=f"```{resultado['meta']:.2f}```",
            inline=True
        )
        
        embed.add_field(
            name="Prazo",
            value=f"```{resultado['prazo_dias']} dias```",
            inline=True
        )
        
        embed.add_field(
            name="Depósito Diário Recomendado",
            value=f"```{resultado['deposito_diario']:.2f}```",
            inline=False
        )
        
        await inter.response.send_message(embed=embed)
    
    @commands.slash_command(name="comparar_taxas", description="Comparar taxas de rendimento")
    async def comparar_taxas(
        self,
        inter: disnake.AppCommandInteraction,
        valor: float
    ):
        """Compara rendimento em diferentes modalidades"""
        resultado = await self.ferramentas.calcular_taxas_comparativas(valor)
        
        embed = disnake.Embed(
            title="📊 Comparação de Taxas",
            description=f"Investimento inicial: `{valor:.2f}`",
            color=disnake.Colour.purple()
        )
        
        for tipo, dados in resultado.items():
            embed.add_field(
                name=f"💰 {tipo.title()}",
                value=f"Rendimento: `{dados['rendimento']:.2f}`\nRetorno: `{dados['retorno_percentual']:.2f}%`",
                inline=True
            )
        
        await inter.response.send_message(embed=embed)
