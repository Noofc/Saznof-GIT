import disnake
from disnake.ext import commands, tasks

from functions.antifraud import close_expired_carts, load_config, save_config
from functions.emoji import emoji


class AntiFraudeLimitModal(disnake.ui.Modal):
    def __init__(self):
        config = load_config()
        components = [
            disnake.ui.TextInput(
                label="Idade minima da conta (dias)",
                custom_id="min_account_age_days",
                value=str(config.get("min_account_age_days", 3)),
                max_length=4,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Tentativas por hora",
                custom_id="max_attempts_per_hour",
                value=str(config.get("max_attempts_per_hour", 6)),
                max_length=4,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Carrinhos abertos por usuario",
                custom_id="max_pending_carts",
                value=str(config.get("max_pending_carts", 2)),
                max_length=4,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Fechar carrinho aberto apos (min)",
                custom_id="open_cart_timeout_minutes",
                value=str(config.get("open_cart_timeout_minutes", 30)),
                max_length=5,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Fechar pagamento pendente apos (min)",
                custom_id="pending_cart_timeout_minutes",
                value=str(config.get("pending_cart_timeout_minutes", 15)),
                max_length=5,
                required=True,
            ),
        ]
        super().__init__(title="Limites Anti Fraude", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        values = inter.text_values
        try:
            min_age = max(0, int(values.get("min_account_age_days", "3")))
            attempts = max(0, int(values.get("max_attempts_per_hour", "6")))
            pending = max(0, int(values.get("max_pending_carts", "2")))
            open_timeout = max(5, int(values.get("open_cart_timeout_minutes", "30")))
            pending_timeout = max(5, int(values.get("pending_cart_timeout_minutes", "15")))
        except ValueError:
            await inter.response.send_message(f"{emoji.wrong} Informe apenas numeros validos.", ephemeral=True)
            return

        config = load_config()
        config["min_account_age_days"] = min_age
        config["max_attempts_per_hour"] = attempts
        config["max_pending_carts"] = pending
        config["open_cart_timeout_minutes"] = open_timeout
        config["pending_cart_timeout_minutes"] = pending_timeout
        save_config(config)
        await inter.response.send_message(f"{emoji.correct} Limites do Anti Fraude atualizados.", ephemeral=True)


class AntiFraudeBlacklistModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(label="ID do usuario", custom_id="user_id", max_length=32, required=True),
            disnake.ui.TextInput(
                label="Acao",
                custom_id="action",
                max_length=10,
                placeholder="add ou remove",
                required=True,
            ),
            disnake.ui.TextInput(
                label="Motivo",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=300,
                required=False,
            ),
        ]
        super().__init__(title="Blacklist Anti Fraude", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        user_id = "".join(ch for ch in str(inter.text_values.get("user_id") or "") if ch.isdigit())
        action = str(inter.text_values.get("action") or "").strip().lower()
        if not user_id:
            await inter.response.send_message(f"{emoji.wrong} Informe um ID valido.", ephemeral=True)
            return

        config = load_config()
        blacklist = config.setdefault("blacklist", {})
        if action.startswith("rem"):
            blacklist.pop(user_id, None)
            text = f"{emoji.correct} Usuario `{user_id}` removido da blacklist."
        else:
            blacklist[user_id] = {
                "reason": str(inter.text_values.get("reason") or "Sem motivo informado").strip(),
                "staff_id": str(inter.user.id),
            }
            text = f"{emoji.correct} Usuario `{user_id}` adicionado na blacklist."
        save_config(config)
        await inter.response.send_message(text, ephemeral=True)


class AntiFraudePanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._initial_auto_close_done = False

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.auto_close_old_carts.is_running():
            self.auto_close_old_carts.start()
        if not self._initial_auto_close_done:
            self._initial_auto_close_done = True
            self.bot.loop.create_task(close_expired_carts(self.bot, limit=100, notify_user=True))

    def cog_unload(self):
        self.auto_close_old_carts.cancel()

    @tasks.loop(minutes=5)
    async def auto_close_old_carts(self):
        await close_expired_carts(self.bot, limit=50, notify_user=True)

    @auto_close_old_carts.before_loop
    async def before_auto_close_old_carts(self):
        await self.bot.wait_until_ready()

    @staticmethod
    def _channel_text(channel_id):
        return f"<#{channel_id}>" if channel_id else "`Nao configurado`"

    def display_antifraud_panel(self, inter: disnake.MessageInteraction):
        config = load_config()
        enabled = bool(config.get("enabled", True))
        status = "`Ativo`" if enabled else "`Inativo`"
        dot = getattr(emoji, "green", "") if enabled else getattr(emoji, "red", "")
        shield = getattr(emoji, "shield", getattr(emoji, "warn", ""))
        color = disnake.Colour.green() if enabled else disnake.Colour.red()
        blacklist = config.get("blacklist") if isinstance(config.get("blacklist"), dict) else {}
        last_denied = config.get("last_denied") if isinstance(config.get("last_denied"), list) else []
        last_auto_closed = config.get("last_auto_closed") if isinstance(config.get("last_auto_closed"), list) else []
        auto_close_enabled = bool(config.get("auto_close_old_carts", True))
        auto_close_status = "`Ativo`" if auto_close_enabled else "`Inativo`"
        auto_close_dot = getattr(emoji, "green", "") if auto_close_enabled else getattr(emoji, "red", "")

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"## {shield} Anti Fraude\n"
                    "Bloqueia compras suspeitas antes de criar pagamento real."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"{getattr(emoji, 'chart', '')} **Status:** {dot} {status}\n"
                    f"{getattr(emoji, 'clock', '')} **Idade minima:** `{config.get('min_account_age_days', 3)} dias`\n"
                    f"{getattr(emoji, 'reload', '')} **Tentativas/hora:** `{config.get('max_attempts_per_hour', 6)}`\n"
                    f"{getattr(emoji, 'cart', '')} **Carrinhos abertos:** `{config.get('max_pending_carts', 2)}` por usuario\n"
                    f"{getattr(emoji, 'clock', '')} **Auto fechamento:** {auto_close_dot} {auto_close_status}\n"
                    f"{getattr(emoji, 'time', getattr(emoji, 'clock', ''))} **Carrinho aberto:** `{config.get('open_cart_timeout_minutes', 30)} min` | **Pagamento pendente:** `{config.get('pending_cart_timeout_minutes', 15)} min`\n"
                    f"{getattr(emoji, 'lock', '')} **Blacklist:** `{len(blacklist)}` usuarios\n"
                    f"{getattr(emoji, 'textc', '')} **Logs:** {self._channel_text(config.get('log_channel_id'))}\n"
                    f"{getattr(emoji, 'warn', '')} **Bloqueios recentes:** `{len(last_denied)}` | **Carrinhos fechados:** `{len(last_auto_closed)}`"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Desativar" if enabled else "Ativar",
                        style=disnake.ButtonStyle.red if enabled else disnake.ButtonStyle.green,
                        emoji=getattr(emoji, "power", None),
                        custom_id="AntiFraude_Toggle",
                    ),
                    disnake.ui.Button(label="Limites", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "edit", None), custom_id="AntiFraude_Limits"),
                    disnake.ui.Button(label="Canal Logs", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "textc", None), custom_id="AntiFraude_Channel"),
                ),
                accent_colour=color,
            )
        ]

    async def _refresh(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_antifraud_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @commands.Cog.listener("on_message_interaction")
    async def on_antifraud_interaction(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("AntiFraude"):
            return

        if custom_id == "AntiFraude_Toggle":
            await inter.response.defer(ephemeral=True)
            config = load_config()
            config["enabled"] = not bool(config.get("enabled", True))
            save_config(config)
            await self._refresh(inter)
            await inter.followup.send(f"{emoji.correct} Anti Fraude {'ativado' if config['enabled'] else 'desativado'}.", ephemeral=True)
            return

        if custom_id == "AntiFraude_AutoClose":
            await inter.response.defer(ephemeral=True)
            config = load_config()
            config["auto_close_old_carts"] = not bool(config.get("auto_close_old_carts", True))
            save_config(config)
            await self._refresh(inter)
            await inter.followup.send(
                f"{emoji.correct} Auto fechamento de carrinhos {'ativado' if config['auto_close_old_carts'] else 'desativado'}.",
                ephemeral=True,
            )
            return

        if custom_id == "AntiFraude_CloseExpired":
            await inter.response.defer(ephemeral=True)
            result = await close_expired_carts(self.bot, inter.guild, force=True, limit=100, notify_user=True)
            await self._refresh(inter)
            await inter.followup.send(
                f"{emoji.correct} Verificacao concluida. Carrinhos fechados: `{result.get('closed', 0)}`.",
                ephemeral=True,
            )
            return

        if custom_id == "AntiFraude_Limits":
            await inter.response.send_modal(AntiFraudeLimitModal())
            return

        if custom_id == "AntiFraude_Blacklist":
            await inter.response.send_modal(AntiFraudeBlacklistModal())
            return

        if custom_id == "AntiFraude_Channel":
            await inter.response.send_message(
                "Selecione o canal para logs do Anti Fraude.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Canal de logs",
                            custom_id="AntiFraude_SelectChannel",
                            channel_types=[disnake.ChannelType.text],
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "AntiFraude_SelectChannel":
            config = load_config()
            config["log_channel_id"] = int(inter.values[0])
            save_config(config)
            await inter.response.send_message(f"{emoji.correct} Canal de logs salvo em <#{inter.values[0]}>.", ephemeral=True)


def setup(bot):
    bot.add_cog(AntiFraudePanel(bot))
