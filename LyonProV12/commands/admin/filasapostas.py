import re
import secrets
from datetime import datetime

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from .panel_v2 import build_panel_card
from .painel.components import PainelComponents

CONFIG_KEY = "filas_apostas_config"
DEFAULT_OPTIONS = ["Normal", "Full Ump Xm8", "Mobilador"]
CREATION_MODES = {
    "manual": "Manual",
    "custom": "Personalizada",
    "automatic": "Automática",
}


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _channel_id(value) -> str:
    raw = str(value or "").strip().replace("<#", "").replace(">", "")
    return raw if raw.isdigit() else ""


class FilasApostasPanel(commands.Cog):
    """Sistema de Filas de Apostas em componente V2."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._get_config()

    def _flags(self) -> disnake.MessageFlags:
        return disnake.MessageFlags(is_components_v2=True)

    def _default_queue(self) -> dict:
        return {
            "name": "2v2 Mobile",
            "mode": "2v2 Mobile",
            "value": "5.00",
            "capacity": 4,
            "options": DEFAULT_OPTIONS[:],
            "users": [],
            "closed": False,
            "source": "manual",
            "created_at": _now(),
            "message_id": "",
            "channel_id": "",
        }

    def _default_template(self) -> dict:
        queue = self._default_queue()
        queue["source"] = "template"
        queue.pop("users", None)
        queue.pop("closed", None)
        queue.pop("message_id", None)
        queue.pop("channel_id", None)
        return queue

    def _ensure_config_defaults(self, data: dict) -> bool:
        changed = False
        defaults = {
            "enabled": True,
            "creation_mode": "manual",
            "publish_channel_id": "",
            "auto_close_full": True,
            "auto_recreate": True,
            "last_fila_id": "",
            "filas": {},
            "template": self._default_template(),
        }
        for key, value in defaults.items():
            if key not in data:
                data[key] = value.copy() if isinstance(value, dict) else value
                changed = True

        if data.get("creation_mode") not in CREATION_MODES:
            data["creation_mode"] = "manual"
            changed = True

        if not isinstance(data.get("filas"), dict):
            data["filas"] = {}
            changed = True

        if not isinstance(data.get("template"), dict):
            data["template"] = self._default_template()
            changed = True

        template = data["template"]
        template_defaults = self._default_template()
        for key, value in template_defaults.items():
            if key not in template:
                template[key] = value
                changed = True
        template["options"] = self._normalise_options(template.get("options"))
        template["capacity"] = self._queue_capacity(template)
        return changed

    def _get_config(self) -> dict:
        data = db.get_document(CONFIG_KEY) or {}
        if not isinstance(data, dict):
            data = {}
        if self._ensure_config_defaults(data):
            self._save_config(data)
        return data

    def _save_config(self, data: dict) -> None:
        db.save_document(CONFIG_KEY, data)

    def _accent_colour(self) -> disnake.Colour:
        colors = db.get_document("custom_colors") or {}
        color_hex = colors.get("primary") or "#5865f2"
        try:
            return disnake.Colour(int(color_hex.replace("#", ""), 16))
        except Exception:
            return disnake.Colour.blurple()

    def _money_text(self, value) -> str:
        raw = str(value or "").replace("R$", "").replace(",", ".").strip()
        try:
            return f"R$ {float(raw):.2f}".replace(".", ",")
        except ValueError:
            return str(value or "R$ 0,00")

    def _queue_capacity(self, queue_or_mode) -> int:
        if isinstance(queue_or_mode, dict):
            raw_capacity = str(queue_or_mode.get("capacity") or "").strip()
            if raw_capacity.isdigit():
                return max(2, min(int(raw_capacity), 50))
            mode = queue_or_mode.get("mode") or queue_or_mode.get("name") or ""
        else:
            mode = str(queue_or_mode or "")

        match = re.search(r"(\d+)\s*[xv]\s*(\d+)", mode, re.IGNORECASE)
        if not match:
            return 10
        return max(2, min(int(match.group(1)) + int(match.group(2)), 50))

    def _normalise_options(self, raw_options) -> list[str]:
        if isinstance(raw_options, list):
            options = [str(option).strip() for option in raw_options if str(option).strip()]
        else:
            options = [part.strip() for part in str(raw_options or "").split(",") if part.strip()]
        return (options or DEFAULT_OPTIONS)[:5]

    def _normalise_queue(self, fila: dict, source: str = "manual") -> dict:
        normalised = self._default_queue()
        if isinstance(fila, dict):
            normalised.update(fila)
        else:
            normalised["name"] = str(fila or normalised["name"])
            normalised["mode"] = normalised["name"]
        normalised["source"] = normalised.get("source") or source
        normalised["options"] = self._normalise_options(normalised.get("options"))
        normalised["capacity"] = self._queue_capacity(normalised)
        normalised["users"] = self._normalise_users(normalised)
        normalised["closed"] = bool(normalised.get("closed", False))
        return normalised

    def _get_filas(self, data: dict) -> dict:
        if not isinstance(data.get("filas"), dict):
            data["filas"] = {}
        for fila_id, fila in list(data["filas"].items()):
            data["filas"][fila_id] = self._normalise_queue(fila)
        return data["filas"]

    def _latest_queue_id(self, data: dict) -> str:
        filas = self._get_filas(data)
        last_id = str(data.get("last_fila_id") or "")
        if last_id in filas:
            return last_id
        if filas:
            return next(reversed(filas))
        return ""

    def _queue_from_template(self, data: dict, source: str) -> dict:
        template = data.get("template") if isinstance(data.get("template"), dict) else self._default_template()
        queue = self._default_queue()
        for key in ("name", "mode", "value", "capacity", "options"):
            queue[key] = template.get(key, queue[key])
        queue["source"] = source
        queue["users"] = []
        queue["closed"] = False
        queue["created_at"] = _now()
        return self._normalise_queue(queue, source=source)

    def _create_queue(self, data: dict, queue: dict) -> str:
        filas = self._get_filas(data)
        fila_id = secrets.token_hex(3)
        filas[fila_id] = self._normalise_queue(queue, source=queue.get("source", "manual"))
        data["last_fila_id"] = fila_id
        return fila_id

    def _ensure_queue(self, data: dict) -> str:
        fila_id = self._latest_queue_id(data)
        if fila_id:
            data["last_fila_id"] = fila_id
            return fila_id
        return self._create_queue(data, self._queue_from_template(data, "manual"))

    def _normalise_users(self, fila: dict) -> list[dict]:
        users = fila.get("users") if isinstance(fila.get("users"), list) else []
        normalised = []
        for user in users:
            if isinstance(user, dict):
                user_id = user.get("id")
                if user_id:
                    normalised.append({"id": str(user_id), "option": user.get("option", "Normal")})
            elif user:
                normalised.append({"id": str(user), "option": "Normal"})
        fila["users"] = normalised
        return normalised

    def _players_text(self, fila: dict) -> str:
        users = self._normalise_users(fila)
        if not users:
            return "Nenhum jogador na fila."
        lines = []
        for index, user in enumerate(users[:20], start=1):
            lines.append(f"{index}. <@{user.get('id')}> - `{user.get('option', 'Normal')}`")
        if len(users) > 20:
            lines.append(f"... e mais {len(users) - 20} jogador(es).")
        return "\n".join(lines)

    def _mode_label(self, data: dict) -> str:
        return CREATION_MODES.get(data.get("creation_mode"), "Manual")

    def _channel_label(self, data: dict) -> str:
        channel_id = _channel_id(data.get("publish_channel_id"))
        return f"<#{channel_id}>" if channel_id else "`Canal atual`"

    def _resolve_publish_channel(self, inter: disnake.MessageInteraction, data: dict, fallback=None):
        channel_id = _channel_id(data.get("publish_channel_id"))
        channel = None
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None and getattr(inter, "guild", None):
                channel = inter.guild.get_channel(int(channel_id))
        return channel or fallback or getattr(inter, "channel", None)

    def _build_public_queue(self, fila_id: str, fila: dict) -> list:
        options = self._normalise_options(fila.get("options"))
        users = self._normalise_users(fila)
        capacity = self._queue_capacity(fila)
        closed = bool(fila.get("closed", False))
        status = "Fechada" if closed else ("Lotada" if len(users) >= capacity else "Aberta")
        source = {
            "manual": "Manual",
            "custom": "Modelo personalizado",
            "automatic": "Fila automática",
        }.get(str(fila.get("source") or "manual"), "Manual")

        option_buttons = [
            disnake.ui.Button(
                label=option[:80],
                style=disnake.ButtonStyle.grey,
                emoji=getattr(emoji, "swords", None),
                custom_id=f"Filas_Join:{fila_id}:{index}",
                disabled=closed or len(users) >= capacity,
            )
            for index, option in enumerate(options)
        ]

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"## {fila.get('name') or 'Fila Criada'}"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                f"**Valor Partida**\n"
                f"{self._money_text(fila.get('value'))}\n\n"
                f"**Modo**\n"
                f"{fila.get('mode') or fila.get('name') or 'Nao configurado'}\n\n"
                f"**Jogadores na fila ({len(users)}/{capacity})**\n"
                f"{self._players_text(fila)}\n\n"
                f"**Criação:** `{source}`\n"
                f"**Status:** `{status}`"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(*option_buttons),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Sair", style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "back", None), custom_id=f"Filas_Leave:{fila_id}", disabled=closed),
                disnake.ui.Button(label="Fechar Fila", style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "lock", None), custom_id=f"Filas_Close:{fila_id}", disabled=closed),
            ),
            accent_colour=self._accent_colour(),
        )
        return [container]

    def display_filas_panel(self, inter: disnake.MessageInteraction):
        data = self._get_config()
        filas = self._get_filas(data)
        template = data.get("template", self._default_template())
        open_count = sum(1 for fila in filas.values() if not fila.get("closed"))
        user_count = sum(len(fila.get("users", [])) for fila in filas.values())

        return build_panel_card(
            title="Filas de Apostas",
            breadcrumb="Painel > Sistemas > Filas/Apostas",
            description=(
                "Configure filas manuais, modelos personalizados e criação automática para apostas. "
                "Use o modo automático para recriar uma nova fila quando a atual lotar."
            ),
            status_lines=[
                f"**Status:** `{'Ativo' if data.get('enabled') else 'Inativo'}`",
                f"**Modo de criação:** `{self._mode_label(data)}`",
                f"**Canal padrão:** {self._channel_label(data)}",
                f"**Modelo:** `{template.get('name')}` • `{template.get('mode')}` • `{self._money_text(template.get('value'))}` • `{self._queue_capacity(template)} vagas",
                f"**Filas:** `{len(filas)}` total • `{open_count}` abertas • `{user_count}` jogadores",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Desativar" if data.get("enabled") else "Ativar", style=disnake.ButtonStyle.danger if data.get("enabled") else disnake.ButtonStyle.success, emoji=getattr(emoji, "power", None), custom_id="Filas_Toggle"),
                    disnake.ui.Button(label="Modo", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "reload", None), custom_id="Filas_Mode"),
                    disnake.ui.Button(label="Modelo", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "edit", None), custom_id="Filas_Template"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Criar Fila", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "plus", None), custom_id="Filas_Criar"),
                    disnake.ui.Button(label="Enviar Fila", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "announcement", None), custom_id="Filas_EnviarPainel"),
                    disnake.ui.Button(label="Canal", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "canal", None), custom_id="Filas_Canal"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Gerenciar", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "settings", None), custom_id="Filas_Gerenciar", disabled=not filas),
                    disnake.ui.Button(label="Auto recriar", style=disnake.ButtonStyle.green if data.get("auto_recreate") else disnake.ButtonStyle.grey, emoji=getattr(emoji, "reload", None), custom_id="Filas_AutoRecreate"),
                    disnake.ui.Button(label="Fechar ao lotar", style=disnake.ButtonStyle.green if data.get("auto_close_full") else disnake.ButtonStyle.grey, emoji=getattr(emoji, "lock", None), custom_id="Filas_AutoClose"),
                ),
            ],
        )

    def _manager_components(self, inter: disnake.MessageInteraction) -> list:
        data = self._get_config()
        filas = self._get_filas(data)
        fila_id = self._latest_queue_id(data)
        fila = filas.get(fila_id) if fila_id else None

        if not fila:
            return build_panel_card(
                title="Gerenciar Filas",
                breadcrumb="Painel > Filas/Apostas > Gerenciar",
                description="Nenhuma fila criada ainda.",
                include_back=False,
            )

        users = self._normalise_users(fila)
        return build_panel_card(
            title="Gerenciar Filas",
            breadcrumb="Painel > Filas/Apostas > Gerenciar",
            description=f"Gerenciando a última fila criada: `{fila_id}`.",
            status_lines=[
                f"**Nome:** `{fila.get('name')}`",
                f"**Modo:** `{fila.get('mode')}`",
                f"**Valor:** `{self._money_text(fila.get('value'))}`",
                f"**Jogadores:** `{len(users)}/{self._queue_capacity(fila)}`",
                f"**Status:** `{'Fechada' if fila.get('closed') else 'Aberta'}`",
                f"**Mensagem:** `{fila.get('message_id') or 'Nao enviada'}`",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Reenviar", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "announcement", None), custom_id="Filas_ResendLast"),
                    disnake.ui.Button(label="Reabrir", style=disnake.ButtonStyle.green, emoji=getattr(emoji, "unlock", None), custom_id="Filas_ReopenLast"),
                    disnake.ui.Button(label="Fechar", style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "lock", None), custom_id="Filas_CloseLast"),
                ),
            ],
            include_back=False,
        )

    async def _safe_defer(self, inter: disnake.Interaction, *, ephemeral: bool = False, with_message: bool | None = None) -> bool:
        if inter.response.is_done():
            return True
        try:
            kwargs = {"ephemeral": ephemeral}
            if with_message is not None:
                kwargs["with_message"] = with_message
            await inter.response.defer(**kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[FilasApostas] Interacao expirada/defer ignorado: {exc}")
            return False

    async def _safe_send_modal(self, inter: disnake.MessageInteraction, modal: disnake.ui.Modal) -> bool:
        if inter.response.is_done():
            return False
        try:
            await inter.response.send_modal(modal)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[FilasApostas] Falha ao abrir modal: {exc}")
            return False

    async def _safe_response_send(self, inter: disnake.Interaction, content: str | None = None, **kwargs) -> bool:
        try:
            if inter.response.is_done():
                await inter.followup.send(content, **kwargs)
            else:
                await inter.response.send_message(content, **kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[FilasApostas] Falha ao responder interacao: {exc}")
            return False

    async def _safe_response_edit(self, inter: disnake.Interaction, **kwargs) -> bool:
        try:
            if inter.response.is_done():
                await inter.edit_original_message(**kwargs)
            else:
                await inter.response.edit_message(**kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[FilasApostas] Falha ao editar interacao: {exc}")
            return False

    async def _safe_edit_original(self, inter: disnake.Interaction, **kwargs) -> bool:
        try:
            await inter.edit_original_message(**kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[FilasApostas] Falha ao editar mensagem original: {exc}")
            return False

    async def _safe_followup(self, inter: disnake.Interaction, content: str | None = None, **kwargs) -> bool:
        try:
            await inter.followup.send(content, **kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[FilasApostas] Falha ao enviar followup: {exc}")
            return False

    async def _refresh_admin_panel(self, message: disnake.Message | None, inter: disnake.Interaction):
        if not message:
            return
        try:
            await message.edit(content=None, embed=None, components=self.display_filas_panel(inter), flags=self._flags())
        except Exception as exc:
            print(f"[FilasApostas] Falha ao atualizar painel: {exc}")

    async def _refresh_manager_panel(self, inter: disnake.MessageInteraction):
        await self._safe_edit_original(inter, content=None, embed=None, components=self._manager_components(inter), flags=self._flags())

    async def _refresh_public_message(self, fila_id: str, fila: dict):
        channel_id = _channel_id(fila.get("channel_id"))
        message_id = str(fila.get("message_id") or "")
        if not channel_id or not message_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            return

        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(components=self._build_public_queue(fila_id, fila), flags=self._flags())
        except Exception as exc:
            print(f"[FilasApostas] Falha ao atualizar fila publica: {exc}")

    async def _send_queue(self, inter: disnake.MessageInteraction, fila_id: str | None = None, channel=None, data: dict | None = None):
        data = data or self._get_config()
        if not data.get("enabled", True):
            raise RuntimeError("Sistema de filas desativado")

        creation_mode = str(data.get("creation_mode") or "manual")
        if not fila_id:
            if creation_mode in {"custom", "automatic"}:
                fila_id = self._create_queue(data, self._queue_from_template(data, creation_mode))
            else:
                fila_id = self._ensure_queue(data)

        filas = self._get_filas(data)
        fila = filas[fila_id]
        self._normalise_users(fila)
        fila["closed"] = False
        data["last_fila_id"] = fila_id

        target_channel = channel or self._resolve_publish_channel(inter, data)
        if target_channel is None:
            raise RuntimeError("Canal de envio nao encontrado")

        sent = await target_channel.send(components=self._build_public_queue(fila_id, fila), flags=self._flags())
        fila["message_id"] = str(sent.id)
        fila["channel_id"] = str(sent.channel.id)
        self._save_config(data)
        return sent

    def _can_manage(self, inter: disnake.MessageInteraction) -> bool:
        user = getattr(inter, "author", None) or getattr(inter, "user", None)
        perms = getattr(user, "guild_permissions", None)
        return bool(perms and (perms.administrator or perms.manage_guild))

    async def _open_create_modal(self, inter: disnake.MessageInteraction):
        source_message = inter.message
        cog = self

        class FilaModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Criar fila personalizada",
                    custom_id="Filas_CreateModal",
                    components=[
                        disnake.ui.TextInput(label="Titulo da fila", custom_id="name", max_length=64, placeholder="2v2 Mobile"),
                        disnake.ui.TextInput(label="Modo", custom_id="mode", max_length=64, placeholder="2v2 Mobile"),
                        disnake.ui.TextInput(label="Valor", custom_id="value", required=True, max_length=16, placeholder="5.00"),
                        disnake.ui.TextInput(label="Capacidade", custom_id="capacity", required=False, max_length=3, placeholder="Vazio = detectar pelo modo"),
                        disnake.ui.TextInput(label="Botoes separados por virgula", custom_id="options", required=False, max_length=180, placeholder="Normal, Full Ump Xm8, Mobilador"),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                name = values.get("name", "").strip()
                mode = values.get("mode", "").strip()
                value = values.get("value", "").strip()
                if not name or not mode:
                    await cog._safe_response_send(modal_inter, f"{emoji.wrong} Informe titulo e modo da fila.", ephemeral=True)
                    return

                data = cog._get_config()
                queue = {
                    "name": name,
                    "mode": mode,
                    "value": value,
                    "capacity": values.get("capacity", "").strip(),
                    "options": cog._normalise_options(values.get("options")),
                    "source": "manual",
                }
                fila_id = cog._create_queue(data, queue)
                cog._save_config(data)
                if not await cog._safe_defer(modal_inter, ephemeral=True):
                    return
                await cog._refresh_admin_panel(source_message, modal_inter)
                await cog._safe_followup(modal_inter, f"{emoji.correct} Fila `{name}` criada (`{fila_id}`). Use **Enviar Fila** para publicar.", ephemeral=True)

        await self._safe_send_modal(inter, FilaModal())

    async def _open_template_modal(self, inter: disnake.MessageInteraction):
        source_message = inter.message
        cog = self
        data = self._get_config()
        template = data.get("template", self._default_template())

        class TemplateModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Modelo da fila",
                    custom_id="Filas_TemplateModal",
                    components=[
                        disnake.ui.TextInput(label="Titulo padrão", custom_id="name", value=str(template.get("name") or "")[:64], max_length=64, placeholder="2v2 Mobile"),
                        disnake.ui.TextInput(label="Modo padrão", custom_id="mode", value=str(template.get("mode") or "")[:64], max_length=64, placeholder="2v2 Mobile"),
                        disnake.ui.TextInput(label="Valor padrão", custom_id="value", value=str(template.get("value") or "5.00")[:16], max_length=16, placeholder="5.00"),
                        disnake.ui.TextInput(label="Capacidade", custom_id="capacity", value=str(cog._queue_capacity(template))[:3], required=False, max_length=3, placeholder="4"),
                        disnake.ui.TextInput(label="Botoes separados por virgula", custom_id="options", value=", ".join(cog._normalise_options(template.get("options")))[:180], required=False, max_length=180),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                data = cog._get_config()
                template = data["template"]
                template.update(
                    {
                        "name": values.get("name", "").strip() or "2v2 Mobile",
                        "mode": values.get("mode", "").strip() or "2v2 Mobile",
                        "value": values.get("value", "").strip() or "5.00",
                        "capacity": values.get("capacity", "").strip() or "4",
                        "options": cog._normalise_options(values.get("options")),
                    }
                )
                template["capacity"] = cog._queue_capacity(template)
                cog._save_config(data)
                if not await cog._safe_defer(modal_inter, ephemeral=True):
                    return
                await cog._refresh_admin_panel(source_message, modal_inter)
                await cog._safe_followup(modal_inter, f"{emoji.correct} Modelo das filas atualizado.", ephemeral=True)

        await self._safe_send_modal(inter, TemplateModal())

    @commands.Cog.listener("on_message_interaction")
    async def Filas_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Filas"):
            return

        if custom_id == "Filas_Criar":
            await self._open_create_modal(inter)
            return

        if custom_id == "Filas_Template":
            await self._open_template_modal(inter)
            return

        if custom_id == "Filas_Toggle":
            if not await self._safe_defer(inter, with_message=False):
                return
            data = self._get_config()
            data["enabled"] = not bool(data.get("enabled", True))
            self._save_config(data)
            await self._safe_edit_original(inter, content=None, embed=None, components=self.display_filas_panel(inter), flags=self._flags())
            return

        if custom_id == "Filas_Mode":
            if not await self._safe_defer(inter, with_message=False):
                return
            data = self._get_config()
            order = ["manual", "custom", "automatic"]
            current = str(data.get("creation_mode") or "manual")
            data["creation_mode"] = order[(order.index(current) + 1) % len(order)] if current in order else "manual"
            self._save_config(data)
            await self._safe_edit_original(inter, content=None, embed=None, components=self.display_filas_panel(inter), flags=self._flags())
            return

        if custom_id in {"Filas_AutoRecreate", "Filas_AutoClose"}:
            if not await self._safe_defer(inter, with_message=False):
                return
            data = self._get_config()
            key = "auto_recreate" if custom_id == "Filas_AutoRecreate" else "auto_close_full"
            data[key] = not bool(data.get(key, True))
            self._save_config(data)
            await self._safe_edit_original(inter, content=None, embed=None, components=self.display_filas_panel(inter), flags=self._flags())
            return

        if custom_id == "Filas_Canal":
            await self._safe_response_send(
                inter,
                "Selecione o canal padrão onde as filas serão publicadas.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            custom_id="Filas_ChannelSelect",
                            channel_types=[disnake.ChannelType.text],
                            placeholder="Canal das filas",
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Filas_ChannelSelect":
            selected = inter.values[0] if getattr(inter, "values", None) else None
            selected_id = str(getattr(selected, "id", selected) or "")
            channel_id = _channel_id(selected_id)
            if not channel_id:
                await self._safe_response_edit(inter, content=f"{emoji.wrong} Canal invalido.", components=[])
                return
            data = self._get_config()
            data["publish_channel_id"] = channel_id
            self._save_config(data)
            await self._safe_response_edit(inter, content=f"{emoji.correct} Canal das filas definido para <#{data['publish_channel_id']}>.", components=[])
            return

        if custom_id == "Filas_EnviarPainel":
            if not await self._safe_defer(inter, ephemeral=True):
                return
            try:
                sent = await self._send_queue(inter)
            except RuntimeError as exc:
                await self._safe_followup(inter, f"{emoji.wrong} {exc}", ephemeral=True)
                return
            await self._safe_followup(inter, f"{emoji.correct} Fila enviada em {sent.channel.mention}.", ephemeral=True)
            return

        if custom_id.startswith("Filas_Join:"):
            if not await self._safe_defer(inter, with_message=False):
                return
            _, fila_id, raw_option = custom_id.split(":", 2)
            data = self._get_config()
            filas = self._get_filas(data)
            fila = filas.get(fila_id)
            if not data.get("enabled", True):
                await self._safe_response_send(inter, f"{emoji.wrong} O sistema de filas esta desativado.", ephemeral=True)
                return
            if not fila:
                await self._safe_response_send(inter, f"{emoji.wrong} Essa fila nao existe mais.", ephemeral=True)
                return
            if fila.get("closed"):
                await self._safe_response_send(inter, f"{emoji.wrong} Essa fila esta fechada.", ephemeral=True)
                return

            users = self._normalise_users(fila)
            user_id = str(inter.user.id)
            options = self._normalise_options(fila.get("options"))
            try:
                option_index = int(raw_option)
            except (TypeError, ValueError):
                option_index = 0
            option = options[option_index] if option_index < len(options) else options[0]
            capacity = self._queue_capacity(fila)
            existing = next((user for user in users if str(user.get("id")) == user_id), None)
            if existing:
                existing["option"] = option
            else:
                if len(users) >= capacity:
                    await self._safe_response_send(inter, f"{emoji.wrong} Essa fila ja esta cheia.", ephemeral=True)
                    return
                users.append({"id": user_id, "option": option})

            full_after_join = len(users) >= capacity
            auto_queue_id = None
            auto_channel = None
            auto_sent = None
            auto_error = None
            if full_after_join and data.get("auto_close_full", True):
                fila["closed"] = True

            if full_after_join and data.get("creation_mode") == "automatic" and data.get("auto_recreate", True):
                auto_queue_id = self._create_queue(data, self._queue_from_template(data, "automatic"))
                auto_channel = self._resolve_publish_channel(inter, data, fallback=getattr(inter, "channel", None))

            self._save_config(data)
            if not await self._safe_response_edit(inter, components=self._build_public_queue(fila_id, fila), flags=self._flags()):
                return

            if auto_queue_id:
                try:
                    auto_sent = await self._send_queue(inter, auto_queue_id, channel=auto_channel, data=data)
                except Exception as exc:
                    auto_error = str(exc)

            extra = ""
            if auto_sent:
                extra = f"\n{emoji.correct} A fila lotou e uma nova fila automática foi enviada em {auto_sent.channel.mention}."
            elif auto_error:
                extra = f"\n{emoji.wrong} A fila lotou, mas nao consegui enviar a próxima fila: `{auto_error}`"
            await self._safe_followup(inter, f"{emoji.correct} Voce entrou na fila como `{option}`.{extra}", ephemeral=True)
            return

        if custom_id.startswith("Filas_Leave:"):
            if not await self._safe_defer(inter, with_message=False):
                return
            fila_id = custom_id.split(":", 1)[1]
            data = self._get_config()
            filas = self._get_filas(data)
            fila = filas.get(fila_id)
            if not fila:
                await self._safe_response_send(inter, f"{emoji.wrong} Essa fila nao existe mais.", ephemeral=True)
                return
            user_id = str(inter.user.id)
            users = self._normalise_users(fila)
            fila["users"] = [user for user in users if str(user.get("id", user)) != user_id]
            self._save_config(data)
            if not await self._safe_response_edit(inter, components=self._build_public_queue(fila_id, fila), flags=self._flags()):
                return
            await self._safe_followup(inter, f"{emoji.correct} Voce saiu da fila.", ephemeral=True)
            return

        if custom_id.startswith("Filas_Close:"):
            if not await self._safe_defer(inter, with_message=False):
                return
            if not self._can_manage(inter):
                await self._safe_response_send(inter, f"{emoji.wrong} Apenas administradores podem fechar a fila.", ephemeral=True)
                return
            fila_id = custom_id.split(":", 1)[1]
            data = self._get_config()
            filas = self._get_filas(data)
            fila = filas.get(fila_id)
            if not fila:
                await self._safe_response_send(inter, f"{emoji.wrong} Essa fila nao existe mais.", ephemeral=True)
                return
            fila["closed"] = True
            self._save_config(data)
            await self._safe_response_edit(inter, components=self._build_public_queue(fila_id, fila), flags=self._flags())
            return

        if custom_id == "Filas_Gerenciar":
            if not await self._safe_defer(inter, with_message=False):
                return
            await self._safe_edit_original(inter, content=None, embed=None, components=self._manager_components(inter), flags=self._flags())
            return

        if custom_id == "Filas_BackConfig":
            if not await self._safe_defer(inter, with_message=False):
                return
            await self._safe_edit_original(inter, content=None, embed=None, components=PainelComponents(inter), flags=self._flags())
            return

        if custom_id == "Filas_Config":
            if not await self._safe_defer(inter, with_message=False):
                return
            await self._safe_edit_original(inter, content=None, embed=None, components=self.display_filas_panel(inter), flags=self._flags())
            return

        if custom_id in {"Filas_ReopenLast", "Filas_CloseLast", "Filas_ClearLast", "Filas_DeleteLast", "Filas_ResendLast"}:
            if not await self._safe_defer(inter, with_message=False):
                return
            data = self._get_config()
            filas = self._get_filas(data)
            fila_id = self._latest_queue_id(data)
            fila = filas.get(fila_id) if fila_id else None
            if not fila:
                await self._safe_followup(inter, f"{emoji.wrong} Nenhuma fila encontrada.", ephemeral=True)
                return

            if custom_id == "Filas_ReopenLast":
                fila["closed"] = False
                await self._refresh_public_message(fila_id, fila)
            elif custom_id == "Filas_CloseLast":
                fila["closed"] = True
                await self._refresh_public_message(fila_id, fila)
            elif custom_id == "Filas_ClearLast":
                fila["users"] = []
                fila["closed"] = False
                await self._refresh_public_message(fila_id, fila)
            elif custom_id == "Filas_DeleteLast":
                filas.pop(fila_id, None)
                data["last_fila_id"] = self._latest_queue_id(data)
            elif custom_id == "Filas_ResendLast":
                try:
                    await self._send_queue(inter, fila_id=fila_id, data=data)
                except RuntimeError as exc:
                    await self._safe_followup(inter, f"{emoji.wrong} {exc}", ephemeral=True)
                    return

            self._save_config(data)
            await self._refresh_manager_panel(inter)
            return


def setup(bot):
    bot.add_cog(FilasApostasPanel(bot))
