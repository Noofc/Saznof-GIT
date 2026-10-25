import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from .panel_v2 import build_panel_card, channel_label


class FeedbackPanel(commands.Cog):
    """Sistema de Monitor de Feedbacks."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def display_feedback_panel(self, inter: disnake.MessageInteraction):
        feedback_data = db.get_document("feedback_monitor") or {}
        feedbacks = feedback_data.get("feedbacks", [])
        pending = [item for item in feedbacks if not item.get("reviewed", False)]

        return build_panel_card(
            title="Monitor de Feedbacks",
            breadcrumb="Painel > Feedback",
            description="Monitore feedbacks recebidos dos usuarios.",
            status_lines=[
                f"**Total:** `{len(feedbacks)}`",
                f"**Pendentes:** `{len(pending)}`",
                f"**Canal logs:** {channel_label(feedback_data.get('logs_channel_id'))}",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Visualizar", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "receipt", None), custom_id="Feedback_Visualizar", disabled=not feedbacks),
                    disnake.ui.Button(label="Pendentes", style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "warn", None), custom_id="Feedback_Pendentes", disabled=not pending),
                    disnake.ui.Button(label="Config", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "settings2", None), custom_id="Feedback_Config"),
                )
            ],
        )

    @commands.Cog.listener("on_message_interaction")
    async def Feedback_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Feedback"):
            return

        if custom_id == "Feedback_Visualizar":
            feedback_data = db.get_document("feedback_monitor") or {}
            feedbacks = feedback_data.get("feedbacks", [])
            if not feedbacks:
                await inter.response.send_message(f"{emoji.wrong} Nenhum feedback disponivel.", ephemeral=True)
                return

            feedback_list = "\n".join(
                f"- {item.get('user', 'Usuario')} - {str(item.get('message', ''))[:80]}"
                for item in feedbacks[:10]
            )
            await inter.response.send_message(f"**Feedbacks ({len(feedbacks)}):**\n{feedback_list}", ephemeral=True)
            return

        if custom_id == "Feedback_Pendentes":
            feedback_data = db.get_document("feedback_monitor") or {}
            pending = [item for item in feedback_data.get("feedbacks", []) if not item.get("reviewed", False)]
            if not pending:
                await inter.response.send_message(f"{emoji.correct} Nao ha feedbacks pendentes.", ephemeral=True)
                return

            pending_list = "\n".join(
                f"- {item.get('user', 'Usuario')} - {str(item.get('message', ''))[:80]}"
                for item in pending[:10]
            )
            await inter.response.send_message(f"**Feedbacks pendentes ({len(pending)}):**\n{pending_list}", ephemeral=True)
            return

        if custom_id == "Feedback_Config":
            await inter.response.send_message("O monitor usa os feedbacks salvos em `feedback_monitor`.", ephemeral=True)


def setup(bot):
    bot.add_cog(FeedbackPanel(bot))
