import io
import re

import disnake
from disnake.ext import commands

from functions.emoji import emoji
from functions.systemgen_manager import LyonGenManager
from functions.utils import utils


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "systemgen")).strip("_")
    return (name or "systemgen")[:48]


class LyonGenCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.systemgen = LyonGenManager()

    async def service_autocomplete(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        query = str(user_input or "").lower()
        services = self.systemgen.list_services(include_empty=False)
        choices = {}

        for service in services:
            name = str(service.get("name") or service.get("id") or "Servico")
            category = str(service.get("category") or "outros")
            stock = int(service.get("stock_count", 0) or 0)
            if query and query not in name.lower() and query not in category.lower():
                continue
            label = f"{name} ({stock} em estoque)"
            choices[label[:100]] = str(service.get("id") or name)
            if len(choices) >= 25:
                break

        if choices:
            return choices
        return ["Nenhum servico com estoque"]

    @commands.slash_command(
        name="gen",
        description="Gerar contas do estoque do Lyon Gen",
        guild_ids=utils.obter_guild_ids(),
    )
    async def gen(
        self,
        inter: disnake.ApplicationCommandInteraction,
        servico: str = commands.Param(description="Servico do estoque", autocomplete=service_autocomplete),
        quantidade: int = commands.Param(description="Quantidade de itens", ge=1, le=100, default=1),
    ):
        data = self.systemgen.load()
        settings = data.get("settings", {})

        if not data.get("enabled", True):
            await inter.response.send_message(f"{emoji.off} O Lyon Gen esta desativado.", ephemeral=True)
            return

        if not settings.get("command_enabled", False):
            await inter.response.send_message(
                f"{emoji.warn} O comando `/gen` esta desativado no painel do Lyon Gen.",
                ephemeral=True,
            )
            return

        if servico == "Nenhum servico com estoque":
            await inter.response.send_message(
                f"{emoji.warn} Nenhum servico com estoque disponivel no Lyon Gen.",
                ephemeral=True,
            )
            return

        await inter.response.defer(ephemeral=True)
        result = self.systemgen.generate(servico, quantity=quantidade, user_id=inter.author.id, source="slash-gen")

        if not result.get("ok"):
            await inter.followup.send(f"{emoji.warn} {result.get('reason')}", ephemeral=True)
            return

        items = result.get("items", [])
        service = result.get("service") or {}
        service_name = service.get("name") or servico
        content = "\n".join(items)
        filename = f"{_safe_filename(service_name)}_gen.txt"

        try:
            await inter.author.send(
                content=f"{emoji.correct} Lyon Gen gerou `{len(items)}` item(ns) de **{service_name}**.",
                file=disnake.File(io.BytesIO(content.encode("utf-8")), filename=filename),
            )
            await inter.followup.send(
                f"{emoji.correct} Gerei `{len(items)}` item(ns) de **{service_name}** e enviei no seu privado.\n"
                f"Estoque restante: `{result.get('available', 0)}`.",
                ephemeral=True,
            )
            return
        except disnake.Forbidden:
            pass

        try:
            await inter.followup.send(
                f"{emoji.warn} Nao consegui enviar no privado, entao deixei o arquivo aqui de forma efemera.",
                file=disnake.File(io.BytesIO(content.encode("utf-8")), filename=filename),
                ephemeral=True,
            )
        except Exception:
            self.systemgen.return_stock(servico, items)
            await inter.followup.send(
                f"{emoji.wrong} Nao consegui entregar o arquivo. O estoque foi devolvido para **{service_name}**.",
                ephemeral=True,
            )


def setup(bot: commands.Bot):
    bot.add_cog(LyonGenCommands(bot))
