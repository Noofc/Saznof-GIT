import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from .panel_v2 import build_panel_card, configured_label, status_label


def _safe_button_emoji(name: str, fallback: str | None = None):
    def is_safe(value: str | None) -> bool:
        if not isinstance(value, str):
            return False
        stripped = value.strip()
        if stripped.startswith("<:") or stripped.startswith("<a:"):
            return True
        return False

    value = getattr(emoji, name, None)
    if is_safe(value):
        return value.strip()
    fallback_value = getattr(emoji, str(fallback or ""), None)
    if is_safe(fallback_value):
        return fallback_value.strip()
    return None


class SistemaIAPanel(commands.Cog):
    """Sistema de IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def display_sistemaai_panel(self, inter: disnake.MessageInteraction):
        ai_config = db.get_document("ai_config") or {}
        enabled = ai_config.get("enabled", False)
        title_emoji = getattr(emoji, "robot", "")

        return build_panel_card(
            title=f"{title_emoji} Sistema IA".strip(),
            breadcrumb="Painel > Sistema IA",
            description="Configure a IA usada nas respostas e automacoes do bot.",
            status_lines=[
                f"**Status:** {status_label(enabled)}",
                f"**API:** {configured_label(ai_config.get('api_key'))}",
                f"**Modelo:** `{ai_config.get('model', 'Nao configurado')}`",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="API", style=disnake.ButtonStyle.blurple, emoji=_safe_button_emoji("key", "key"), custom_id="SistemaIA_ConfigAPI"),
                    disnake.ui.Button(
                        label="Desativar" if enabled else "Ativar",
                        style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success,
                        emoji=_safe_button_emoji("power", "power"),
                        custom_id="SistemaIA_Toggle",
                    ),
                    disnake.ui.Button(label="Avancado", style=disnake.ButtonStyle.grey, emoji=_safe_button_emoji("settings2", "settings"), custom_id="SistemaIA_Config"),
                )
            ],
        )

    async def _refresh_panel(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_sistemaai_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @commands.Cog.listener("on_message_interaction")
    async def SistemaIA_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("SistemaIA"):
            return

        if custom_id == "SistemaIA_ConfigAPI":
            class ApiModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Configurar IA",
                        custom_id="SistemaIA_ApiModal",
                        components=[
                            disnake.ui.TextInput(label="API Key", custom_id="api_key", style=disnake.TextInputStyle.paragraph, max_length=512),
                            disnake.ui.TextInput(label="Modelo", custom_id="model", required=False, max_length=64, placeholder="ex: gpt-4.1-mini"),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    ai_config = db.get_document("ai_config") or {}
                    ai_config["api_key"] = values.get("api_key", "").strip()
                    if values.get("model", "").strip():
                        ai_config["model"] = values.get("model", "").strip()
                    db.save_document("ai_config", ai_config)
                    await modal_inter.response.send_message(f"{emoji.correct} Configuracao da IA salva.", ephemeral=True)

            await inter.response.send_modal(ApiModal())
            return

        if custom_id == "SistemaIA_Toggle":
            await inter.response.defer(ephemeral=True)
            ai_config = db.get_document("ai_config") or {}
            ai_config["enabled"] = not ai_config.get("enabled", False)
            db.save_document("ai_config", ai_config)
            await self._refresh_panel(inter)
            status = "ativado" if ai_config["enabled"] else "desativado"
            await inter.followup.send(f"{emoji.correct} Sistema de IA {status}.", ephemeral=True)
            return

        if custom_id == "SistemaIA_Config":
            ai_config = db.get_document("ai_config") or {}
            await inter.response.send_message(
                f"**Status:** {status_label(ai_config.get('enabled', False))}\n"
                f"**API:** {configured_label(ai_config.get('api_key'))}\n"
                f"**Modelo:** `{ai_config.get('model', 'Nao configurado')}`",
                ephemeral=True,
            )


def setup(bot):
    bot.add_cog(SistemaIAPanel(bot))
