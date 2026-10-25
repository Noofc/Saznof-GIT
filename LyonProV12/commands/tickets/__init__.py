import disnake
from disnake.ext import commands
from functions.ai_api import chamar_ia
from functions.emoji import emoji
from functions.utils import utils


class AskCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(
        name="ask",
        description="Pergunte algo para a IA do bot.",
        guild_ids=utils.obter_guild_ids()
    )
    async def ask(
        self,
        inter: disnake.ApplicationCommandInteraction,
        mensagem: str = commands.Param(description="Sua pergunta para a IA")
    ):
        await inter.response.defer(ephemeral=True)

        try:
            resposta = await chamar_ia(mensagem, "AskCommand")
            if len(resposta) > 1900:
                resposta = resposta[:1900] + "..."

            await inter.followup.send(
                f"{emoji.information} **Resposta da IA:**\n\n{resposta}",
                ephemeral=True
            )
        except Exception as e:
            await inter.followup.send(
                f"{emoji.wrong} Erro ao consultar a IA: {str(e)}",
                ephemeral=True
            )


def setup(bot: commands.Bot):
    """Ticket slash commands are disabled.

    Ticket actions now live inside the ticket panels/buttons.
    """
    bot.add_cog(AskCommand(bot))
