from __future__ import annotations

from datetime import datetime

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.perms import perms


DATA_PATH = "database/bateponto_system.json"


def _emoji(key: str, fallback=None):
    value = getattr(emoji, key, None)
    if value:
        return value
    if isinstance(fallback, str):
        fallback_value = getattr(emoji, fallback, None)
        if fallback_value:
            return fallback_value
        if fallback.startswith("<"):
            return fallback
    return getattr(emoji, "commands", "")


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _parse_dt(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or ""))
    except Exception:
        return None


def _id(value: str | None) -> str:
    raw = str(value or "").strip()
    for token in ("<@", "<@!", "<#", "<@&", ">"):
        raw = raw.replace(token, "")
    return raw if raw.isdigit() else ""


def _user(inter: disnake.Interaction):
    return getattr(inter, "user", None) or getattr(inter, "author", None)


def _duration(start_at: str | None, end_at: str | None = None) -> tuple[int, str]:
    start = _parse_dt(start_at)
    end = _parse_dt(end_at) or datetime.utcnow()
    if not start:
        return 0, "0m"
    seconds = max(int((end - start).total_seconds()), 0)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return seconds, f"{hours}h {minutes}m"
    if minutes:
        return seconds, f"{minutes}m {secs}s"
    return seconds, f"{secs}s"


def _default_data() -> dict:
    return {
        "enabled": True,
        "panel_channel_id": "",
        "panel_message_id": "",
        "log_channel_id": "",
        "staff_role_id": "",
        "panel_title": "BATE PONTO",
        "panel_description": "Controle de jornada da equipe com inicio, encerramento, cancelamento e logs automaticos.",
        "active_sessions": {},
        "records": [],
        "last_published_at": None,
    }


class BatePontoConfigModal(disnake.ui.Modal):
    def __init__(self, cog: "BatePontoPanel"):
        self.cog = cog
        cfg = cog.load()
        components = [
            disnake.ui.TextInput(
                label="Titulo do painel",
                custom_id="panel_title",
                value=str(cfg.get("panel_title") or "BATE PONTO")[:80],
                max_length=80,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Descricao do painel",
                custom_id="panel_description",
                style=disnake.TextInputStyle.paragraph,
                value=str(cfg.get("panel_description") or "")[:900],
                max_length=900,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Canal do painel",
                custom_id="panel_channel_id",
                value=str(cfg.get("panel_channel_id") or "")[:32],
                placeholder="ID ou mencao do canal",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Canal de logs",
                custom_id="log_channel_id",
                value=str(cfg.get("log_channel_id") or "")[:32],
                placeholder="ID ou mencao do canal",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Cargo autorizado",
                custom_id="staff_role_id",
                value=str(cfg.get("staff_role_id") or "")[:32],
                placeholder="Opcional: ID ou mencao do cargo",
                max_length=32,
                required=False,
            ),
        ]
        super().__init__(title="Configurar Bate Ponto", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        self.cog.update(
            {
                "panel_title": str(inter.text_values.get("panel_title") or "BATE PONTO").strip(),
                "panel_description": str(inter.text_values.get("panel_description") or "").strip(),
                "panel_channel_id": _id(inter.text_values.get("panel_channel_id")),
                "log_channel_id": _id(inter.text_values.get("log_channel_id")),
                "staff_role_id": _id(inter.text_values.get("staff_role_id")),
            }
        )
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Bate ponto configurado.", ephemeral=True)


class BatePontoPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ensure_data()

    def ensure_data(self) -> dict:
        data = db.obter(DATA_PATH)
        if not isinstance(data, dict):
            data = {}
        defaults = _default_data()
        changed = False
        for key, value in defaults.items():
            if key not in data:
                data[key] = value
                changed = True
        if not isinstance(data.get("active_sessions"), dict):
            data["active_sessions"] = {}
            changed = True
        if not isinstance(data.get("records"), list):
            data["records"] = []
            changed = True
        if changed or not db.obter(DATA_PATH):
            db.salvar(DATA_PATH, data)
        return data

    def load(self) -> dict:
        return self.ensure_data()

    def save(self, data: dict) -> None:
        db.salvar(DATA_PATH, data)

    def update(self, changes: dict) -> dict:
        data = self.load()
        data.update(changes)
        self.save(data)
        return data

    def _container_kwargs(self) -> dict:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary") if isinstance(colors, dict) else None
        if not primary_color_hex:
            return {}
        try:
            return {"accent_colour": disnake.Colour(int(primary_color_hex.replace("#", ""), 16))}
        except Exception:
            return {}

    def _is_admin(self, member) -> bool:
        if member is None:
            return False
        if str(getattr(member, "id", "")) == str(perms.get_owner_id()):
            return True
        permissions = getattr(member, "guild_permissions", None)
        return bool(permissions and (permissions.manage_guild or permissions.administrator))

    def _can_use_clock(self, member) -> bool:
        cfg = self.load()
        role_id = _id(cfg.get("staff_role_id"))
        if not role_id:
            return True
        if self._is_admin(member):
            return True
        return any(str(getattr(role, "id", "")) == role_id for role in getattr(member, "roles", []) or [])

    def _admin_text(self) -> str:
        cfg = self.load()
        active = cfg.get("active_sessions") if isinstance(cfg.get("active_sessions"), dict) else {}
        records = cfg.get("records") if isinstance(cfg.get("records"), list) else []
        panel = f"<#{cfg.get('panel_channel_id')}>" if cfg.get("panel_channel_id") else "Canal atual"
        logs = f"<#{cfg.get('log_channel_id')}>" if cfg.get("log_channel_id") else "Nao definido"
        role = f"<@&{cfg.get('staff_role_id')}>" if cfg.get("staff_role_id") else "Todos podem bater ponto"
        return (
            f"# {_emoji('clock', 'clock')} Bate Ponto\n"
            f"-# Painel > Sistemas > **Bate Ponto**\n\n"
            f"{_emoji('power', 'power')} **Status:** `{'Ativo' if cfg.get('enabled') else 'Desativado'}`\n"
            f"{_emoji('members', 'members')} **Pontos abertos:** `{len(active)}`\n"
            f"{_emoji('receipt', 'receipt')} **Registros salvos:** `{len(records)}`\n"
            f"{_emoji('role', 'role')} **Acesso:** {role}\n"
            f"{_emoji('textc', '#')} **Painel:** {panel} | **Logs:** {logs}"
        )

    def _admin_components(self) -> list:
        cfg = self.load()
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(self._admin_text()),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay("Publique o painel para a equipe iniciar, encerrar ou cancelar o bate ponto com registro automatico."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Configurar", style=disnake.ButtonStyle.grey, emoji=_emoji("settings", "config"), custom_id="BatePonto_Config"),
                    disnake.ui.Button(label="Publicar Painel", style=disnake.ButtonStyle.green, emoji=_emoji("announcement", "announcement"), custom_id="BatePonto_Publish"),
                    disnake.ui.Button(label="Registros", style=disnake.ButtonStyle.blurple, emoji=_emoji("receipt", "receipt"), custom_id="BatePonto_Records"),
                ),
                **self._container_kwargs(),
            )
        ]

    def display_bateponto_panel(self, inter: disnake.MessageInteraction):
        return self._admin_components()

    def _public_components(self) -> list:
        cfg = self.load()
        active = cfg.get("active_sessions") if isinstance(cfg.get("active_sessions"), dict) else {}
        title = cfg.get("panel_title") or "BATE PONTO"
        description = cfg.get("panel_description") or _default_data()["panel_description"]
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('clock', 'clock')} {title}\n\n"
                    f"{description}\n\n"
                    f"{_emoji('members', 'members')} **Pontos abertos agora:** `{len(active)}`"
                ),
                **self._container_kwargs(),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Iniciar", style=disnake.ButtonStyle.green, emoji=_emoji("play", "play"), custom_id="BatePonto_Start"),
                disnake.ui.Button(label="Encerrar", style=disnake.ButtonStyle.blurple, emoji=_emoji("correct", "correct"), custom_id="BatePonto_Stop"),
                disnake.ui.Button(label="Cancelar", style=disnake.ButtonStyle.red, emoji=_emoji("wrong", "wrong"), custom_id="BatePonto_Cancel"),
                disnake.ui.Button(label="Meu Status", style=disnake.ButtonStyle.grey, emoji=_emoji("receipt", "receipt"), custom_id="BatePonto_Status"),
            ),
        ]

    def _records_components(self) -> list:
        cfg = self.load()
        active = cfg.get("active_sessions") if isinstance(cfg.get("active_sessions"), dict) else {}
        records = cfg.get("records") if isinstance(cfg.get("records"), list) else []
        active_lines = []
        for user_id, session in list(active.items())[:10]:
            _, elapsed = _duration(session.get("start_at"))
            active_lines.append(f"- <@{user_id}> iniciou `{session.get('start_at')}` | `{elapsed}`")
        record_lines = []
        for record in list(reversed(records[-10:])):
            record_lines.append(
                f"- <@{record.get('user_id')}> | `{record.get('status')}` | `{record.get('duration_label')}` | fim `{record.get('end_at')}`"
            )
        body = (
            f"# {_emoji('receipt', 'receipt')} Registros de Bate Ponto\n\n"
            f"**Abertos:**\n{chr(10).join(active_lines) if active_lines else 'Nenhum ponto aberto.'}\n\n"
            f"**Ultimos registros:**\n{chr(10).join(record_lines) if record_lines else 'Nenhum registro salvo.'}"
        )
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(body[:4000]),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=_emoji("back", "back"), custom_id="BatePonto_Back")
                ),
                **self._container_kwargs(),
            )
        ]

    async def send_log(self, text: str):
        cfg = self.load()
        channel_id = _id(cfg.get("log_channel_id"))
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(text)
            except Exception:
                pass

    async def publish_panel(self, inter: disnake.MessageInteraction):
        cfg = self.load()
        if not cfg.get("enabled"):
            await inter.response.send_message(f"{_emoji('warn', 'warn')} O sistema de bate ponto esta desativado.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        channel = None
        channel_id = _id(cfg.get("panel_channel_id"))
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None and getattr(inter, "guild", None):
                channel = inter.guild.get_channel(int(channel_id))
        channel = channel or getattr(inter, "channel", None)
        if channel is None:
            await inter.followup.send(f"{_emoji('wrong', 'wrong')} Canal do painel nao encontrado.", ephemeral=True)
            return

        sent = await channel.send(components=self._public_components(), flags=disnake.MessageFlags(is_components_v2=True))
        self.update({"last_published_at": _now(), "panel_channel_id": str(channel.id), "panel_message_id": str(sent.id)})
        await inter.followup.send(f"{_emoji('correct', 'correct')} Painel de bate ponto publicado em {channel.mention}.", ephemeral=True)

    async def refresh_public_panel(self):
        cfg = self.load()
        channel_id = _id(cfg.get("panel_channel_id"))
        message_id = _id(cfg.get("panel_message_id"))
        if not channel_id or not message_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            return
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.edit(components=self._public_components())
        except disnake.NotFound:
            data = self.load()
            data["panel_message_id"] = ""
            self.save(data)
        except Exception:
            pass

    async def _refresh_admin_message(self, inter: disnake.MessageInteraction):
        if not inter.response.is_done():
            await inter.response.defer(with_message=False)
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self._admin_components(),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    async def start_point(self, inter: disnake.MessageInteraction):
        user = _user(inter)
        cfg = self.load()
        if not cfg.get("enabled"):
            await inter.response.send_message(f"{_emoji('warn', 'warn')} Bate ponto desativado.", ephemeral=True)
            return
        if not self._can_use_clock(user):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Voce nao tem permissao para bater ponto.", ephemeral=True)
            return

        data = self.load()
        active = data.setdefault("active_sessions", {})
        user_id = str(user.id)
        if user_id in active:
            _, elapsed = _duration(active[user_id].get("start_at"))
            await inter.response.send_message(f"{_emoji('warn', 'warn')} Voce ja esta com ponto aberto ha `{elapsed}`.", ephemeral=True)
            return

        active[user_id] = {
            "user_id": user_id,
            "discord_name": str(user),
            "start_at": _now(),
            "channel_id": str(getattr(getattr(inter, "channel", None), "id", "")),
        }
        self.save(data)
        await self.send_log(
            f"{_emoji('play', 'play')} **Bate ponto iniciado**\n"
            f"Usuario: {user.mention}\n"
            f"Inicio: `{active[user_id]['start_at']}`"
        )
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Bate ponto iniciado em `{active[user_id]['start_at']}`.", ephemeral=True)
        await self.refresh_public_panel()

    async def finish_point(self, inter: disnake.MessageInteraction, canceled: bool = False):
        user = _user(inter)
        data = self.load()
        active = data.setdefault("active_sessions", {})
        user_id = str(user.id)
        session = active.get(user_id)
        if not session:
            await inter.response.send_message(f"{_emoji('warn', 'warn')} Voce nao tem bate ponto aberto.", ephemeral=True)
            return

        end_at = _now()
        seconds, label = _duration(session.get("start_at"), end_at)
        status = "cancelado" if canceled else "encerrado"
        record = {
            "user_id": user_id,
            "discord_name": str(user),
            "start_at": session.get("start_at"),
            "end_at": end_at,
            "duration_seconds": seconds,
            "duration_label": label,
            "status": status,
        }
        active.pop(user_id, None)
        records = data.setdefault("records", [])
        records.append(record)
        data["records"] = records[-500:]
        self.save(data)

        await self.send_log(
            f"{_emoji('wrong', 'wrong') if canceled else _emoji('correct', 'correct')} **Bate ponto {status}**\n"
            f"Usuario: {user.mention}\n"
            f"Inicio: `{record['start_at']}`\n"
            f"Fim: `{record['end_at']}`\n"
            f"Total: `{label}`"
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Bate ponto {status}. Total: `{label}`.",
            ephemeral=True,
        )
        await self.refresh_public_panel()

    async def show_status(self, inter: disnake.MessageInteraction):
        user = _user(inter)
        data = self.load()
        session = data.get("active_sessions", {}).get(str(user.id))
        if not session:
            await inter.response.send_message(f"{_emoji('receipt', 'receipt')} Voce nao tem bate ponto aberto.", ephemeral=True)
            return
        _, elapsed = _duration(session.get("start_at"))
        await inter.response.send_message(
            f"{_emoji('clock', 'clock')} **Seu bate ponto esta aberto**\n"
            f"Inicio: `{session.get('start_at')}`\n"
            f"Tempo atual: `{elapsed}`",
            ephemeral=True,
        )

    @commands.Cog.listener("on_button_click")
    async def on_bateponto_button(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("BatePonto_"):
            return

        if custom_id == "BatePonto_Config":
            if not self._is_admin(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas administradores podem configurar.", ephemeral=True)
                return
            await inter.response.send_modal(BatePontoConfigModal(self))
        elif custom_id == "BatePonto_Publish":
            if not self._is_admin(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas administradores podem publicar.", ephemeral=True)
                return
            await self.publish_panel(inter)
        elif custom_id == "BatePonto_Toggle":
            if not self._is_admin(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas administradores podem alterar o status.", ephemeral=True)
                return
            cfg = self.load()
            self.update({"enabled": not bool(cfg.get("enabled"))})
            await self._refresh_admin_message(inter)
        elif custom_id == "BatePonto_Records":
            if not self._is_admin(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas administradores podem ver registros.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._records_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "BatePonto_Back":
            await self._refresh_admin_message(inter)
        elif custom_id == "BatePonto_Start":
            await self.start_point(inter)
        elif custom_id == "BatePonto_Stop":
            await self.finish_point(inter, canceled=False)
        elif custom_id == "BatePonto_Cancel":
            await self.finish_point(inter, canceled=True)
        elif custom_id == "BatePonto_Status":
            await self.show_status(inter)


def setup(bot: commands.Bot):
    bot.add_cog(BatePontoPanel(bot))
