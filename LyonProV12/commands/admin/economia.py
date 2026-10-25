import inspect
import re

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.bool_utils import as_bool

KEY_PREFIX = "economy_"
ID_RE = re.compile(r"(\d{16,20})")


class Economia(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _key(self, guild_id: int) -> str:
        return f"{KEY_PREFIX}{guild_id}"

    def _get_config(self, guild_id: int) -> dict:
        data = db.get_document(self._key(guild_id)) or {}
        return data if isinstance(data, dict) else {}

    def _save_config(self, guild_id: int, data: dict) -> None:
        db.save_document(self._key(guild_id), data)

    def _v2_flags(self) -> disnake.MessageFlags:
        return disnake.MessageFlags(is_components_v2=True)

    def _extract_id(self, raw: str) -> str | None:
        match = ID_RE.search(raw or "")
        return match.group(1) if match else None

    def _modal_values(self, inter: disnake.ModalInteraction) -> dict:
        return getattr(inter, "text_values", None) or getattr(inter, "resolved_values", {}) or {}

    def _channel_text(self, channel_id) -> str:
        return f"<#{channel_id}>" if channel_id else "`Nao configurado`"

    def _role_text(self, role_id) -> str:
        return f"<@&{role_id}>" if role_id else "`Nao configurado`"

    def _currency_text(self, data: dict) -> str:
        currency = data.get("currency") or {}
        if not isinstance(currency, dict):
            currency = {}
        name = currency.get("name") or "Coin"
        symbol = currency.get("emoji") or "$"
        return f"{symbol} {name}"

    def _global_multiplier(self, data: dict) -> float:
        try:
            return float(data.get("global_multiplier", 1.0) or 1.0)
        except (TypeError, ValueError):
            return 1.0

    def _accent_colour(self) -> disnake.Colour:
        colors = db.get_document("custom_colors") or {}
        color_hex = colors.get("primary") or "#5865f2"
        try:
            return disnake.Colour(int(color_hex.replace("#", ""), 16))
        except Exception:
            return disnake.Colour.blurple()

    def _build_economia_panel(self, guild_id: int):
        data = self._get_config(guild_id)
        enabled = as_bool(data.get("enabled"), False)
        logs_enabled = as_bool(data.get("logs_enabled"), bool(data.get("logs_channel")))
        guard_enabled = as_bool(data.get("guard_enabled"), False)
        commands_config = data.get("commands") if isinstance(data.get("commands"), dict) else {}

        status = "Ativo" if enabled else "Inativo"
        logs_status = "Ativo" if logs_enabled else "Inativo"
        guard_status = "Ativo" if guard_enabled else "Inativo"
        active_events = data.get("active_events") if isinstance(data.get("active_events"), list) else []
        jobs = data.get("jobs") if isinstance(data.get("jobs"), list) else []
        balances = data.get("balances") if isinstance(data.get("balances"), dict) else {}

        container = disnake.ui.Container(
            disnake.ui.TextDisplay("## Sistema de Economia"),
            disnake.ui.TextDisplay(
                "Painel > Economia\n"
                "Configure moeda, saldos, empregos, eventos, logs e guard do sistema."
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                f"**Status:** `{status}`\n"
                f"**Moeda:** `{self._currency_text(data)}`\n"
                f"**Multiplicador Global:** `{self._global_multiplier(data):.2f}x`\n"
                f"**Eventos Ativos:** `{len(active_events)}`\n"
                f"**Usuarios com saldo manual:** `{len(balances)}`\n"
                f"**Empregos:** `{len(jobs)}`\n"
                f"**Reset de Coins:** `{data.get('reset_coins') or 'Nunca'}`\n"
                f"**Logs:** `{logs_status}` em {self._channel_text(data.get('logs_channel'))}\n"
                f"**Comandos configurados:** `{len(commands_config)}`\n"
                f"**Guard:** `{guard_status}` {self._role_text(data.get('guard_role'))}"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Desativar" if enabled else "Ativar",
                    style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success,
                    emoji=emoji.power,
                    custom_id=f"Economia_Toggle:{guild_id}",
                ),
                disnake.ui.Button(label="Moeda", style=disnake.ButtonStyle.grey, emoji=emoji.coin, custom_id=f"Economia_Moeda:{guild_id}"),
                disnake.ui.Button(label="Multiplicador", style=disnake.ButtonStyle.grey, emoji=emoji.chart, custom_id=f"Economia_Multiplicadores:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Eventos", style=disnake.ButtonStyle.blurple, emoji=emoji.calendar, custom_id=f"Economia_Eventos:{guild_id}"),
                disnake.ui.Button(label="Usuarios", style=disnake.ButtonStyle.blurple, emoji=emoji.members, custom_id=f"Economia_Usuarios:{guild_id}"),
                disnake.ui.Button(label="Empregos", style=disnake.ButtonStyle.blurple, emoji=emoji.role, custom_id=f"Economia_Empregos:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Tempo Reset", style=disnake.ButtonStyle.grey, emoji=emoji.clock, custom_id=f"Economia_TempoReset:{guild_id}"),
                disnake.ui.Button(label=f"Logs: {logs_status}", style=disnake.ButtonStyle.grey, emoji=emoji.textc, custom_id=f"Economia_LogsToggle:{guild_id}"),
                disnake.ui.Button(label="Canal Logs", style=disnake.ButtonStyle.grey, emoji=emoji.canal, custom_id=f"Economia_CanalLogs:{guild_id}"),
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Comandos", style=disnake.ButtonStyle.grey, emoji=emoji.commands, custom_id=f"Economia_Comandos:{guild_id}"),
                disnake.ui.Button(label="Abrir Loja", style=disnake.ButtonStyle.grey, emoji=emoji.store, custom_id="Painel_Loja"),
                disnake.ui.Button(label="Resetar Tudo", style=disnake.ButtonStyle.danger, emoji=emoji.delete, custom_id=f"Economia_ResetarTudo:{guild_id}"),
            ),
            accent_colour=self._accent_colour(),
        )
        return [container]

    async def display_economia_panel(self, inter: disnake.MessageInteraction):
        return self._build_economia_panel(inter.guild.id)

    async def _edit_panel_interaction(self, inter: disnake.MessageInteraction, guild_id: int):
        payload = {
            "content": None,
            "embed": None,
            "components": self._build_economia_panel(guild_id),
            "flags": self._v2_flags(),
        }
        if not inter.response.is_done():
            return await inter.response.edit_message(**payload)
        return await inter.edit_original_message(**payload)

    async def _edit_panel_message(self, message: disnake.Message | None, guild_id: int):
        if message is None:
            return
        await message.edit(
            content=None,
            embed=None,
            components=self._build_economia_panel(guild_id),
            flags=self._v2_flags(),
        )

    async def _finish_modal(self, modal_inter: disnake.ModalInteraction, source_message, guild_id: int, text: str):
        if not modal_inter.response.is_done():
            await modal_inter.response.defer(ephemeral=True)
        try:
            await self._edit_panel_message(source_message, guild_id)
        except Exception as exc:
            print(f"[Economia] Falha ao atualizar painel pelo modal: {exc}")
        await modal_inter.followup.send(text, ephemeral=True)

    async def _send_error(self, inter, text: str = "Erro ao processar a economia."):
        try:
            if not inter.response.is_done():
                await inter.response.send_message(f"{emoji.wrong} {text}", ephemeral=True)
            else:
                await inter.followup.send(f"{emoji.wrong} {text}", ephemeral=True)
        except Exception:
            pass

    async def _send_modal_moeda(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class MoedaModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Configurar Moeda",
                    custom_id=f"Economia_Moeda_Modal:{guild_id}",
                    components=[
                        disnake.ui.TextInput(label="Nome da moeda", custom_id="name", max_length=32),
                        disnake.ui.TextInput(label="Simbolo ou emoji", custom_id="emoji", max_length=64, required=False),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                values = cog._modal_values(modal_inter)
                name = (values.get("name") or "").strip()
                symbol = (values.get("emoji") or "$").strip()
                if not name:
                    await modal_inter.response.send_message(f"{emoji.wrong} Informe o nome da moeda.", ephemeral=True)
                    return

                cfg = cog._get_config(guild_id)
                cfg["currency"] = {"name": name, "emoji": symbol}
                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Moeda atualizada para `{symbol} {name}`.")

        await inter.response.send_modal(MoedaModal())

    async def _send_modal_multiplier(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class MultModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Multiplicador Global",
                    custom_id=f"Economia_Multiplicadores_Modal:{guild_id}",
                    components=[disnake.ui.TextInput(label="Multiplicador global", custom_id="mult", max_length=10, placeholder="1.0")],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                value = (cog._modal_values(modal_inter).get("mult") or "").replace(",", ".").strip()
                try:
                    multiplier = max(0.0, float(value))
                except ValueError:
                    await modal_inter.response.send_message(f"{emoji.wrong} Informe um numero valido, exemplo: `1.5`.", ephemeral=True)
                    return

                cfg = cog._get_config(guild_id)
                cfg["global_multiplier"] = multiplier
                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Multiplicador definido para `{multiplier:.2f}x`.")

        await inter.response.send_modal(MultModal())

    async def _send_modal_eventos(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class EventosModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Gerenciar Eventos",
                    custom_id=f"Economia_Eventos_Modal:{guild_id}",
                    components=[
                        disnake.ui.TextInput(label="Acao: add ou remove", custom_id="action", max_length=6),
                        disnake.ui.TextInput(label="Nome do evento", custom_id="name", max_length=64),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                values = cog._modal_values(modal_inter)
                action = (values.get("action") or "").strip().lower()
                name = (values.get("name") or "").strip()
                if action not in {"add", "remove"} or not name:
                    await modal_inter.response.send_message(f"{emoji.wrong} Use `add` ou `remove` e informe o nome.", ephemeral=True)
                    return

                cfg = cog._get_config(guild_id)
                events = cfg.get("active_events") if isinstance(cfg.get("active_events"), list) else []
                if action == "add" and name not in events:
                    events.append(name)
                if action == "remove":
                    events = [event for event in events if event != name]

                cfg["active_events"] = events
                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Eventos atualizados.")

        await inter.response.send_modal(EventosModal())

    async def _send_modal_usuarios(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class UsuariosModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Gerenciar Usuarios",
                    custom_id=f"Economia_Usuarios_Modal:{guild_id}",
                    components=[
                        disnake.ui.TextInput(label="Usuario: mencao ou ID", custom_id="user", max_length=64),
                        disnake.ui.TextInput(label="Acao: set, add ou remove", custom_id="action", max_length=8),
                        disnake.ui.TextInput(label="Quantidade", custom_id="amount", max_length=20),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                values = cog._modal_values(modal_inter)
                user_id = cog._extract_id(values.get("user") or "")
                action = (values.get("action") or "").strip().lower()
                amount_raw = (values.get("amount") or "0").strip()
                if not user_id or action not in {"set", "add", "remove"}:
                    await modal_inter.response.send_message(f"{emoji.wrong} Informe usuario valido e acao `set`, `add` ou `remove`.", ephemeral=True)
                    return
                try:
                    amount = int(amount_raw)
                except ValueError:
                    await modal_inter.response.send_message(f"{emoji.wrong} Quantidade invalida.", ephemeral=True)
                    return

                cfg = cog._get_config(guild_id)
                balances = cfg.get("balances") if isinstance(cfg.get("balances"), dict) else {}
                current = int(balances.get(user_id, 0) or 0)
                if action == "set":
                    balances[user_id] = max(0, amount)
                elif action == "add":
                    balances[user_id] = max(0, current + amount)
                else:
                    balances[user_id] = max(0, current - amount)

                cfg["balances"] = balances
                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Saldo manual atualizado para <@{user_id}>.")

        await inter.response.send_modal(UsuariosModal())

    async def _send_modal_empregos(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class EmpregosModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Gerenciar Empregos",
                    custom_id=f"Economia_Empregos_Modal:{guild_id}",
                    components=[
                        disnake.ui.TextInput(label="Acao: add ou remove", custom_id="action", max_length=6),
                        disnake.ui.TextInput(label="Cargo: mencao ou ID", custom_id="role", max_length=64),
                        disnake.ui.TextInput(label="Salario", custom_id="salary", max_length=20, required=False),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                values = cog._modal_values(modal_inter)
                action = (values.get("action") or "").strip().lower()
                role_id = cog._extract_id(values.get("role") or "")
                if action not in {"add", "remove"} or not role_id:
                    await modal_inter.response.send_message(f"{emoji.wrong} Informe `add`/`remove` e um cargo valido.", ephemeral=True)
                    return
                try:
                    salary = max(0, int((values.get("salary") or "0").strip() or 0))
                except ValueError:
                    salary = 0

                cfg = cog._get_config(guild_id)
                jobs = cfg.get("jobs") if isinstance(cfg.get("jobs"), list) else []
                jobs = [job for job in jobs if str(job.get("role_id")) != str(role_id)]
                if action == "add":
                    jobs.append({"role_id": role_id, "salary": salary})

                cfg["jobs"] = jobs
                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Empregos atualizados.")

        await inter.response.send_modal(EmpregosModal())

    async def _send_modal_tempo_reset(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class ResetModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Tempo de Reset",
                    custom_id=f"Economia_TempoReset_Modal:{guild_id}",
                    components=[disnake.ui.TextInput(label="Tempo de reset", custom_id="reset", max_length=32, placeholder="Nunca, diario, 24h...")],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                reset_value = (cog._modal_values(modal_inter).get("reset") or "").strip()
                if not reset_value:
                    await modal_inter.response.send_message(f"{emoji.wrong} Informe o tempo de reset.", ephemeral=True)
                    return

                cfg = cog._get_config(guild_id)
                cfg["reset_coins"] = reset_value
                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Tempo de reset salvo como `{reset_value}`.")

        await inter.response.send_modal(ResetModal())

    async def _send_modal_canal_logs(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class CanalLogsModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Canal de Logs",
                    custom_id=f"Economia_CanalLogs_Modal:{guild_id}",
                    components=[disnake.ui.TextInput(label="Canal: mencao ou ID", custom_id="channel", max_length=64)],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                channel_id = cog._extract_id(cog._modal_values(modal_inter).get("channel") or "")
                if not channel_id:
                    await modal_inter.response.send_message(f"{emoji.wrong} Canal invalido.", ephemeral=True)
                    return

                cfg = cog._get_config(guild_id)
                cfg["logs_channel"] = channel_id
                cfg["logs_enabled"] = True
                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Canal de logs salvo em <#{channel_id}>.")

        await inter.response.send_modal(CanalLogsModal())

    async def _send_modal_comandos(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class ComandosModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Configurar Comandos",
                    custom_id=f"Economia_Comandos_Modal:{guild_id}",
                    components=[
                        disnake.ui.TextInput(label="Nome do comando", custom_id="cmd", max_length=64),
                        disnake.ui.TextInput(label="Acao: enable ou disable", custom_id="action", max_length=8),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                values = cog._modal_values(modal_inter)
                command = (values.get("cmd") or "").strip().lower().lstrip("/")
                action = (values.get("action") or "").strip().lower()
                if not command or action not in {"enable", "disable"}:
                    await modal_inter.response.send_message(f"{emoji.wrong} Informe comando e acao `enable` ou `disable`.", ephemeral=True)
                    return

                cfg = cog._get_config(guild_id)
                commands_cfg = cfg.get("commands") if isinstance(cfg.get("commands"), dict) else {}
                commands_cfg[command] = action == "enable"
                cfg["commands"] = commands_cfg
                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Comando `{command}` atualizado.")

        await inter.response.send_modal(ComandosModal())

    async def _send_modal_guard(self, inter: disnake.MessageInteraction, guild_id: int):
        source_message = inter.message
        cog = self

        class GuardModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Configurar Guard",
                    custom_id=f"Economia_Guard_Modal:{guild_id}",
                    components=[
                        disnake.ui.TextInput(label="Acao: toggle ou set", custom_id="action", max_length=6),
                        disnake.ui.TextInput(label="Cargo: mencao ou ID", custom_id="role", max_length=64, required=False),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                values = cog._modal_values(modal_inter)
                action = (values.get("action") or "").strip().lower()
                cfg = cog._get_config(guild_id)
                if action == "toggle":
                    cfg["guard_enabled"] = not as_bool(cfg.get("guard_enabled"), False)
                elif action == "set":
                    role_id = cog._extract_id(values.get("role") or "")
                    if not role_id:
                        await modal_inter.response.send_message(f"{emoji.wrong} Cargo invalido.", ephemeral=True)
                        return
                    cfg["guard_role"] = role_id
                    cfg["guard_enabled"] = True
                else:
                    await modal_inter.response.send_message(f"{emoji.wrong} Use `toggle` ou `set`.", ephemeral=True)
                    return

                cog._save_config(guild_id, cfg)
                await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Guard atualizado.")

        await inter.response.send_modal(GuardModal())

    async def _open_loja_panel(self, inter: disnake.MessageInteraction):
        loja_cog = self.bot.get_cog("Loja")
        if not loja_cog or not hasattr(loja_cog, "panel"):
            await inter.response.send_message(f"{emoji.wrong} O painel de loja nao esta carregado.", ephemeral=True)
            return

        await inter.response.defer(with_message=False)
        panel_data = loja_cog.panel(inter)
        if inspect.isawaitable(panel_data):
            panel_data = await panel_data

        if isinstance(panel_data, dict):
            payload = dict(panel_data)
            payload.setdefault("content", None)
            if "components" in payload and "embed" not in payload and "embeds" not in payload:
                payload.setdefault("flags", self._v2_flags())
            await inter.edit_original_message(**payload)
            return

        if isinstance(panel_data, tuple) and len(panel_data) == 2:
            embed, components = panel_data
            await inter.edit_original_message(content=None, embed=embed, components=components)
            return

        if isinstance(panel_data, list):
            await inter.edit_original_message(content=None, embed=None, components=panel_data, flags=self._v2_flags())
            return

        await inter.followup.send(f"{emoji.wrong} O painel de loja retornou um formato invalido.", ephemeral=True)

    async def _handle_action(self, inter: disnake.MessageInteraction, selected: str, guild_id: int):
        modal_handlers = {
            "Economia_Moeda": self._send_modal_moeda,
            "Economia_Multiplicadores": self._send_modal_multiplier,
            "Economia_Eventos": self._send_modal_eventos,
            "Economia_Usuarios": self._send_modal_usuarios,
            "Economia_Empregos": self._send_modal_empregos,
            "Economia_TempoReset": self._send_modal_tempo_reset,
            "Economia_CanalLogs": self._send_modal_canal_logs,
            "Economia_Comandos": self._send_modal_comandos,
            "Economia_Guard": self._send_modal_guard,
        }

        handler = modal_handlers.get(selected)
        if handler:
            await handler(inter, guild_id)
            return

        cfg = self._get_config(guild_id)
        if selected == "Economia_Toggle":
            cfg["enabled"] = not as_bool(cfg.get("enabled"), False)
            self._save_config(guild_id, cfg)
            await self._edit_panel_interaction(inter, guild_id)
            status = "ativada" if cfg["enabled"] else "desativada"
            await inter.followup.send(f"{emoji.correct} Economia {status}.", ephemeral=True)
            return

        if selected == "Economia_LogsToggle":
            cfg["logs_enabled"] = not as_bool(cfg.get("logs_enabled"), bool(cfg.get("logs_channel")))
            self._save_config(guild_id, cfg)
            await self._edit_panel_interaction(inter, guild_id)
            status = "ativados" if cfg["logs_enabled"] else "desativados"
            await inter.followup.send(f"{emoji.correct} Logs {status}.", ephemeral=True)
            return

        if selected == "Economia_ResetarTudo":
            self._save_config(guild_id, {})
            await self._edit_panel_interaction(inter, guild_id)
            await inter.followup.send(f"{emoji.correct} Configuracoes da economia resetadas.", ephemeral=True)
            return

        if selected == "Economia_Loja":
            await self._open_loja_panel(inter)
            return

        await inter.response.send_message(f"{emoji.wrong} Acao da economia nao encontrada.", ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Economia_"):
            return

        try:
            action, _, raw_guild_id = custom_id.partition(":")
            guild_id = int(raw_guild_id) if raw_guild_id else inter.guild.id
            await self._handle_action(inter, action, guild_id)
        except Exception as exc:
            print(f"[Economia] Erro na interacao {custom_id}: {exc}")
            await self._send_error(inter)

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Economia_Navegar"):
            return

        try:
            _, _, raw_guild_id = custom_id.partition(":")
            guild_id = int(raw_guild_id) if raw_guild_id else inter.guild.id
            selected = inter.values[0] if inter.values else ""
            if not selected:
                await inter.response.send_message(f"{emoji.wrong} Nenhuma opcao selecionada.", ephemeral=True)
                return
            await self._handle_action(inter, selected, guild_id)
        except Exception as exc:
            print(f"[Economia] Erro no select {custom_id}: {exc}")
            await self._send_error(inter)


def setup(bot: commands.Bot):
    bot.add_cog(Economia(bot))
