import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from .panel_v2 import build_panel_card


class RanksPanel(commands.Cog):
    """Sistema de Ranking de Compradores."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def display_ranking_panel(self, inter: disnake.MessageInteraction):
        ranking_data = db.get_document("ranking_compradores") or {}
        top_buyers = ranking_data.get("top_buyers", [])
        top_preview = "\n".join(
            f"{index}. <@{buyer.get('id')}> - R$ {buyer.get('total', 0)}"
            for index, buyer in enumerate(top_buyers[:5], start=1)
        ) or "`Nenhum comprador no ranking`"

        return build_panel_card(
            title="Ranking de Compradores",
            breadcrumb="Painel > Ranking",
            description="Acompanhe e gerencie os compradores mais ativos.",
            status_lines=[
                f"**Compradores ranqueados:** `{len(top_buyers)}`",
                f"**Top 5:**\n{top_preview}",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Visualizar", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "chart", None), custom_id="Ranking_Visualizar", disabled=not top_buyers),
                    disnake.ui.Button(label="Resetar", style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "trash", None), custom_id="Ranking_Resetar", disabled=not top_buyers),
                    disnake.ui.Button(label="Config", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "settings2", None), custom_id="Ranking_Config"),
                )
            ],
        )

    async def _refresh_panel(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_ranking_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @commands.Cog.listener("on_message_interaction")
    async def Ranking_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Ranking"):
            return

        if custom_id == "Ranking_Visualizar":
            ranking_data = db.get_document("ranking_compradores") or {}
            top_buyers = ranking_data.get("top_buyers", [])
            if not top_buyers:
                await inter.response.send_message(f"{emoji.wrong} Nenhum dado de ranking disponivel.", ephemeral=True)
                return

            ranking_text = "\n".join(
                f"{index}. <@{buyer.get('id')}> - R$ {buyer.get('total', 0)}"
                for index, buyer in enumerate(top_buyers, start=1)
            )
            await inter.response.send_message(f"**Ranking completo:**\n{ranking_text}", ephemeral=True)
            return

        if custom_id == "Ranking_Resetar":
            await inter.response.defer(ephemeral=True)
            ranking_data = db.get_document("ranking_compradores") or {}
            ranking_data["top_buyers"] = []
            db.save_document("ranking_compradores", ranking_data)
            await self._refresh_panel(inter)
            await inter.followup.send(f"{emoji.correct} Ranking resetado com sucesso.", ephemeral=True)
            return

        if custom_id == "Ranking_Config":
            await inter.response.send_message("O ranking e atualizado pelos registros de compras da loja.", ephemeral=True)


def setup(bot):
    bot.add_cog(RanksPanel(bot))
