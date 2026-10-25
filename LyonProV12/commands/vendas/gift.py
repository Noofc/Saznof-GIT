import disnake
from disnake.ext import commands
from functions.emoji import emoji
from modules.loja.gifts.gift_manager import GiftManager


class GiftRedeem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(name="gift", description="Resgatar código de gift/cupom")
    async def gift(self, inter: disnake.ApplicationCommandInteraction, code: str):
        guild = inter.guild
        if not guild:
            await inter.response.send_message(f"{emoji.error} Este comando só funciona em servidores.", ephemeral=True)
            return

        result = GiftManager.redeem_gift(guild.id, code.strip(), inter.author.id)
        if not result["success"]:
            await inter.response.send_message(f"{emoji.error} {result['message']}", ephemeral=True)
            return

        items = result.get("items", [])
        product_text = "\n".join(f"- {item['product_id']} x{item['quantity']}" for item in items)
        await inter.response.send_message(
            f"{emoji.correct} Gift resgatado com sucesso!\n{product_text}",
            ephemeral=True
        )


def setup(bot: commands.Bot):
    bot.add_cog(GiftRedeem(bot))
