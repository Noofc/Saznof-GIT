from __future__ import annotations

import re
import unicodedata
from datetime import datetime

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.perms import perms
from functions.system_logs import send_system_log
from .panel_v2 import build_panel_card


KEY_PREFIX = "server_organizer_"


def _emoji(key: str, fallback: str = "settings"):
    value = getattr(emoji, key, None)
    if value:
        return value
    return getattr(emoji, fallback, None)


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _clean_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def _slug(value: str) -> str:
    text = _clean_text(value)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80] or "canal"


def _format_channel_name(label: str, icon: str = "") -> str:
    icon = icon or ">"
    return f"{icon}╺╸{_slug(label)}"[:100]


ROLE_PERMISSION_PRESETS = {
    "none": [],
    "support": ["manage_messages", "read_message_history", "attach_files"],
    "staff": ["manage_messages", "moderate_members", "kick_members", "mute_members", "move_members"],
    "manager": ["manage_channels", "manage_messages", "moderate_members", "kick_members", "view_audit_log"],
}

BASE_ROLES = [
    {"key": "direcao", "label": "Direcao", "colour": 0x0082FF, "preset": "manager", "hoist": True},
    {"key": "administracao", "label": "Administracao", "colour": 0x2F80ED, "preset": "manager", "hoist": True},
    {"key": "staff", "label": "Staff", "colour": 0x6C63FF, "preset": "staff", "hoist": True},
    {"key": "suporte", "label": "Suporte", "colour": 0x00A86B, "preset": "support", "hoist": True},
    {"key": "cliente", "label": "Cliente", "colour": 0xF2C94C, "preset": "none", "hoist": False},
    {"key": "membro", "label": "Membro", "colour": 0x95A5A6, "preset": "none", "hoist": False},
    {"key": "verificado", "label": "Verificado", "colour": 0x27AE60, "preset": "none", "hoist": False},
    {"key": "parceiro", "label": "Parceiro", "colour": 0x56CCF2, "preset": "none", "hoist": True},
]

BASE_CATEGORIES = [
    {"key": "central", "label": "Central", "icon": "◇"},
    {"key": "loja", "label": "Loja", "icon": "◆"},
    {"key": "atendimento", "label": "Atendimento", "icon": "◈"},
    {"key": "comunidade", "label": "Comunidade", "icon": "◇"},
    {"key": "staff", "label": "Staff", "icon": "◆", "private": True},
    {"key": "logs", "label": "Logs", "icon": "◈", "private": True},
]

CHANNEL_RULES = [
    ("logs", ("log", "logs", "auditoria", "registro")),
    ("staff", ("staff", "equipe", "admin", "mod", "ponto", "interno")),
    ("loja", ("loja", "produto", "produtos", "estoque", "stock", "venda", "compras", "cupom", "robux")),
    ("atendimento", ("suporte", "ticket", "atendimento", "middleman", "duvida", "triagem")),
    ("comunidade", ("chat", "comunidade", "instagram", "parceria", "eventos", "sugest", "midia", "criador")),
    ("central", ("regras", "avisos", "anuncio", "boas", "welcome", "entrada", "info")),
]

READ_ONLY_WORDS = ("regras", "avisos", "anuncio", "informacoes", "info", "status")
STAFF_WORDS = ("staff", "administracao", "direcao", "suporte", "moderador", "equipe")


class CustomRoleModal(disnake.ui.Modal):
    def __init__(self, cog: "ServerOrganizerPanel"):
        self.cog = cog
        super().__init__(
            title="Cargo Personalizado",
            custom_id="Organizador_CustomRoleModal",
            components=[
                disnake.ui.TextInput(label="Nome do cargo", custom_id="name", max_length=80, required=True),
                disnake.ui.TextInput(label="Cor HEX", custom_id="colour", placeholder="#0082ff", max_length=12, required=False),
                disnake.ui.TextInput(label="Preset", custom_id="preset", placeholder="none, support, staff ou manager", max_length=20, required=False),
                disnake.ui.TextInput(label="Separado na lista? (sim/nao)", custom_id="hoist", value="sim", max_length=8, required=False),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await self.cog._handle_custom_role(inter)


class ServerOrganizerPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _key(self, guild_id: int) -> str:
        return f"{KEY_PREFIX}{guild_id}"

    def _get_data(self, guild_id: int) -> dict:
        data = db.get_document(self._key(guild_id)) or {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("created_roles", {})
        data.setdefault("created_categories", {})
        data.setdefault("log_channel_id", "")
        data.setdefault("last_action", "")
        data.setdefault("last_run_at", "")
        return data

    def _save_data(self, guild_id: int, data: dict) -> None:
        db.save_document(self._key(guild_id), data)

    def _colour(self, raw: str | int | None, default: int = 0x0082FF) -> int:
        if isinstance(raw, int):
            return max(0, min(0xFFFFFF, raw))
        value = str(raw or "").strip().replace("#", "")
        try:
            return int(value, 16) if value else default
        except Exception:
            return default

    def _permissions(self, preset: str) -> disnake.Permissions:
        permissions = disnake.Permissions.none()
        for name in ROLE_PERMISSION_PRESETS.get(str(preset or "none").strip().lower(), []):
            if hasattr(permissions, name):
                setattr(permissions, name, True)
        return permissions

    def _can_manage(self, inter: disnake.Interaction) -> bool:
        if perms.get_owner_id() == str(getattr(inter.user, "id", "")):
            return True
        guild_perms = getattr(inter.user, "guild_permissions", None)
        return bool(guild_perms and (guild_perms.administrator or guild_perms.manage_guild))

    def _bot_permissions(self, guild: disnake.Guild) -> disnake.Permissions:
        me = guild.me or guild.get_member(self.bot.user.id)
        return getattr(me, "guild_permissions", disnake.Permissions.none())

    async def _defer(self, inter: disnake.MessageInteraction | disnake.ModalInteraction) -> bool:
        if inter.response.is_done():
            return True
        try:
            await inter.response.defer(ephemeral=True)
            return True
        except disnake.HTTPException as exc:
            if getattr(exc, "code", None) in {40060, 10062}:
                return getattr(exc, "code", None) == 40060
            raise
        except disnake.NotFound:
            return False

    async def _send_done(self, inter: disnake.Interaction, text: str) -> None:
        try:
            if inter.response.is_done():
                await inter.followup.send(text, ephemeral=True)
            else:
                await inter.response.send_message(text, ephemeral=True)
        except Exception:
            pass

    def _existing_role_by_name(self, guild: disnake.Guild, name: str):
        wanted = _clean_text(name)
        return next((role for role in guild.roles if _clean_text(role.name) == wanted), None)

    def _category_name(self, spec: dict) -> str:
        return _format_channel_name(spec["label"], spec.get("icon") or "◇")

    def _existing_category(self, guild: disnake.Guild, spec: dict):
        name = self._category_name(spec)
        wanted = _clean_text(name)
        return next((category for category in guild.categories if _clean_text(category.name) == wanted), None)

    def _staff_roles(self, guild: disnake.Guild, data: dict) -> list[disnake.Role]:
        role_ids = {str(value) for value in (data.get("created_roles") or {}).values() if value}
        roles = []
        for role in guild.roles:
            role_text = _clean_text(role.name)
            if str(role.id) in role_ids or any(word in role_text for word in STAFF_WORDS):
                if role not in roles and role < guild.me.top_role:
                    roles.append(role)
        return roles

    def _private_overwrites(self, guild: disnake.Guild, staff_roles: list[disnake.Role]) -> dict:
        overwrites = {guild.default_role: disnake.PermissionOverwrite(view_channel=False)}
        if guild.me:
            overwrites[guild.me] = disnake.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            )
        for role in staff_roles:
            overwrites[role] = disnake.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )
        return overwrites

    async def _ensure_categories(self, guild: disnake.Guild, data: dict) -> tuple[dict[str, disnake.CategoryChannel], list[str]]:
        staff_roles = self._staff_roles(guild, data)
        categories = {}
        created = []
        for spec in BASE_CATEGORIES:
            category = self._existing_category(guild, spec)
            if category is None:
                create_kwargs = {
                    "name": self._category_name(spec),
                    "reason": "Lyon Pro - organizador do servidor",
                }
                if spec.get("private"):
                    create_kwargs["overwrites"] = self._private_overwrites(guild, staff_roles)
                category = await guild.create_category(**create_kwargs)
                created.append(category.name)
            categories[spec["key"]] = category
            data["created_categories"][spec["key"]] = str(category.id)
        data["last_action"] = "Categorias verificadas/criadas"
        data["last_run_at"] = _now()
        self._save_data(guild.id, data)
        return categories, created

    async def _ensure_log_channel(self, guild: disnake.Guild, data: dict, categories: dict | None = None):
        raw_id = str(data.get("log_channel_id") or "")
        channel = guild.get_channel(int(raw_id)) if raw_id.isdigit() else None
        if isinstance(channel, disnake.TextChannel):
            return channel
        categories = categories or (await self._ensure_categories(guild, data))[0]
        logs_category = categories.get("logs")
        name = _format_channel_name("logs-organizador", "◈")
        channel = next((ch for ch in guild.text_channels if _clean_text(ch.name) == _clean_text(name)), None)
        if channel is None:
            channel = await guild.create_text_channel(
                name=name,
                category=logs_category,
                reason="Lyon Pro - logs do organizador",
            )
        data["log_channel_id"] = str(channel.id)
        self._save_data(guild.id, data)
        return channel

    def _target_category_key(self, channel: disnake.abc.GuildChannel) -> str | None:
        text = _clean_text(getattr(channel, "name", ""))
        for key, words in CHANNEL_RULES:
            if any(word in text for word in words):
                return key
        return None

    async def _send_log(self, guild: disnake.Guild, data: dict, title: str, description: str) -> None:
        try:
            categories = (await self._ensure_categories(guild, data))[0]
            channel = await self._ensure_log_channel(guild, data, categories)
            await channel.send(
                components=[
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(f"## {_emoji('settings', 'tools')} {title}"),
                        disnake.ui.TextDisplay(description),
                        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                        disnake.ui.TextDisplay(f"-# Lyon Pro • {_now()}"),
                        accent_colour=disnake.Colour(0x0082FF),
                    )
                ],
                flags=disnake.MessageFlags(is_components_v2=True),
            )
        except Exception:
            pass

    async def _create_base_roles(self, guild: disnake.Guild, data: dict) -> list[str]:
        created = []
        for spec in BASE_ROLES:
            role = self._existing_role_by_name(guild, spec["label"])
            if role is None:
                role = await guild.create_role(
                    name=spec["label"],
                    colour=disnake.Colour(spec["colour"]),
                    permissions=self._permissions(spec.get("preset")),
                    hoist=bool(spec.get("hoist")),
                    mentionable=True,
                    reason="Lyon Pro - cargos base",
                )
                created.append(role.name)
            data["created_roles"][spec["key"]] = str(role.id)
        data["last_action"] = "Cargos base verificados/criados"
        data["last_run_at"] = _now()
        self._save_data(guild.id, data)
        return created

    async def _organize_channels(self, guild: disnake.Guild, data: dict) -> list[str]:
        categories, _created = await self._ensure_categories(guild, data)
        moved = []
        supported_types = (
            disnake.TextChannel,
            disnake.VoiceChannel,
            disnake.StageChannel,
        )
        forum_type = getattr(disnake, "ForumChannel", None)
        if forum_type:
            supported_types = (*supported_types, forum_type)

        for channel in list(guild.channels):
            if not isinstance(channel, supported_types):
                continue
            target_key = self._target_category_key(channel)
            target = categories.get(target_key) if target_key else None
            if target and getattr(channel, "category_id", None) != target.id:
                try:
                    await channel.edit(category=target, reason="Lyon Pro - organizar canais")
                    moved.append(f"{channel.name} -> {target.name}")
                except Exception:
                    continue
        data["last_action"] = "Canais organizados por categoria"
        data["last_run_at"] = _now()
        self._save_data(guild.id, data)
        return moved

    async def _apply_permissions(self, guild: disnake.Guild, data: dict) -> tuple[list[str], list[str]]:
        categories, _created = await self._ensure_categories(guild, data)
        staff_roles = self._staff_roles(guild, data)
        private_updated = []
        readonly_updated = []

        for key in ("staff", "logs"):
            category = categories.get(key)
            if not category:
                continue
            try:
                await category.edit(
                    overwrites=self._private_overwrites(guild, staff_roles),
                    reason="Lyon Pro - proteger areas internas",
                )
                private_updated.append(category.name)
            except Exception:
                pass

        for channel in guild.text_channels:
            text = _clean_text(channel.name)
            if not any(word in text for word in READ_ONLY_WORDS):
                continue
            try:
                await channel.set_permissions(guild.default_role, send_messages=False, read_message_history=True, view_channel=True)
                for role in staff_roles:
                    await channel.set_permissions(role, send_messages=True, manage_messages=True, read_message_history=True, view_channel=True)
                readonly_updated.append(channel.name)
            except Exception:
                continue

        data["last_action"] = "Permissoes aplicadas"
        data["last_run_at"] = _now()
        self._save_data(guild.id, data)
        return private_updated, readonly_updated

    def _diagnostics(self, guild: disnake.Guild, data: dict) -> list[str]:
        role_names = {}
        for role in guild.roles:
            key = _clean_text(role.name)
            if key and key != "@everyone":
                role_names[key] = role_names.get(key, 0) + 1
        duplicate_roles = [name for name, count in role_names.items() if count > 1]
        empty_categories = [category.name for category in guild.categories if not category.channels]
        channels_without_category = [
            channel.name
            for channel in guild.channels
            if not isinstance(channel, disnake.CategoryChannel) and getattr(channel, "category_id", None) is None
        ]
        missing_roles = [
            spec["label"]
            for spec in BASE_ROLES
            if not self._existing_role_by_name(guild, spec["label"])
        ]
        return [
            f"**Canais:** `{len(guild.channels)}` total • `{len(channels_without_category)}` sem categoria",
            f"**Categorias vazias:** `{len(empty_categories)}`",
            f"**Cargos:** `{len(guild.roles)}` total • `{len(duplicate_roles)}` nomes duplicados",
            f"**Cargos base faltando:** `{len(missing_roles)}`",
            f"**Ultima acao:** `{data.get('last_action') or 'nenhuma'}`",
            f"**Ultima execucao:** `{data.get('last_run_at') or 'nunca'}`",
        ]

    def display_server_organizer_panel(self, inter: disnake.MessageInteraction):
        data = self._get_data(inter.guild.id)
        bot_perms = self._bot_permissions(inter.guild)
        status = "Operacional" if bot_perms.manage_channels and bot_perms.manage_roles else "Sem permissoes completas"
        log_channel_label = f"<#{data.get('log_channel_id')}>" if data.get("log_channel_id") else "`Nao configurado`"
        return build_panel_card(
            title=f"{_emoji('settings', 'tools')} Organizador do Servidor",
            breadcrumb="Painel > Administracao > Organizador",
            description="Organize cargos, categorias, canais e permissoes do servidor sem precisar refazer tudo manualmente.",
            status_lines=[
                f"**Status:** `{status}`",
                f"**Cargos registrados:** `{len(data.get('created_roles', {}))}`",
                f"**Categorias registradas:** `{len(data.get('created_categories', {}))}`",
                f"**Canal logs:** {log_channel_label}",
                f"**Ultima acao:** `{data.get('last_action') or 'nenhuma'}`",
                f"**Ultima execucao:** `{data.get('last_run_at') or 'nunca'}`",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Diagnosticar", style=disnake.ButtonStyle.grey, emoji=_emoji("search", "lupa"), custom_id="Organizador_Diagnose"),
                    disnake.ui.Button(label="Cargos Base", style=disnake.ButtonStyle.green, emoji=_emoji("role", "cargo"), custom_id="Organizador_CreateRoles"),
                    disnake.ui.Button(label="Categorias", style=disnake.ButtonStyle.green, emoji=_emoji("folder", "canal"), custom_id="Organizador_CreateCategories"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Organizar Canais", style=disnake.ButtonStyle.blurple, emoji=_emoji("wand", "settings"), custom_id="Organizador_OrganizeChannels"),
                    disnake.ui.Button(label="Permissoes", style=disnake.ButtonStyle.grey, emoji=_emoji("shield", "lock"), custom_id="Organizador_ApplyPermissions"),
                    disnake.ui.Button(label="Cargo Personalizado", style=disnake.ButtonStyle.grey, emoji=_emoji("plus", "mais2"), custom_id="Organizador_CustomRole"),
                ),
            ],
        )

    async def _guard_action(self, inter: disnake.MessageInteraction) -> bool:
        if not self._can_manage(inter):
            await self._send_done(inter, f"{emoji.wrong} Voce precisa de permissao de **Gerenciar Servidor** para usar o organizador.")
            return False
        bot_perms = self._bot_permissions(inter.guild)
        if not bot_perms.manage_channels or not bot_perms.manage_roles:
            await self._send_done(inter, f"{emoji.wrong} O bot precisa de **Gerenciar Canais** e **Gerenciar Cargos**.")
            return False
        return True

    @commands.Cog.listener("on_button_click")
    async def on_server_organizer_button(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Organizador_"):
            return

        if custom_id == "Organizador_CustomRole":
            if not self._can_manage(inter):
                await inter.response.send_message(f"{emoji.wrong} Voce precisa de permissao de **Gerenciar Servidor**.", ephemeral=True)
                return
            await inter.response.send_modal(CustomRoleModal(self))
            return

        if not await self._defer(inter):
            return
        if not await self._guard_action(inter):
            return

        guild = inter.guild
        data = self._get_data(guild.id)

        if custom_id == "Organizador_Diagnose":
            lines = self._diagnostics(guild, data)
            await self._send_done(inter, "\n".join(lines))
            return

        if custom_id == "Organizador_CreateRoles":
            created = await self._create_base_roles(guild, data)
            text = f"{emoji.correct} Cargos base verificados. Criados agora: `{len(created)}`."
            if created:
                text += "\n" + "\n".join(f"- {name}" for name in created[:12])
            await self._send_log(guild, data, "Cargos organizados", text)
            await send_system_log(self.bot, guild, title="Cargos base organizados", system="Organizador", description=text, actor=inter.user, config=data)
            await self._send_done(inter, text)
            return

        if custom_id == "Organizador_CreateCategories":
            categories, created = await self._ensure_categories(guild, data)
            await self._ensure_log_channel(guild, data, categories)
            text = f"{emoji.correct} Categorias verificadas. Criadas agora: `{len(created)}`."
            if created:
                text += "\n" + "\n".join(f"- {name}" for name in created[:12])
            await self._send_log(guild, data, "Categorias organizadas", text)
            await send_system_log(self.bot, guild, title="Categorias organizadas", system="Organizador", description=text, actor=inter.user, config=data)
            await self._send_done(inter, text)
            return

        if custom_id == "Organizador_OrganizeChannels":
            moved = await self._organize_channels(guild, data)
            text = f"{emoji.correct} Organizacao de canais concluida. Canais movidos: `{len(moved)}`."
            if moved:
                text += "\n" + "\n".join(f"- {item}" for item in moved[:15])
            await self._send_log(guild, data, "Canais organizados", text)
            await send_system_log(self.bot, guild, title="Canais organizados", system="Organizador", description=text, actor=inter.user, config=data)
            await self._send_done(inter, text)
            return

        if custom_id == "Organizador_ApplyPermissions":
            private_updated, readonly_updated = await self._apply_permissions(guild, data)
            text = (
                f"{emoji.correct} Permissoes aplicadas.\n"
                f"Areas internas protegidas: `{len(private_updated)}`\n"
                f"Canais informativos travados: `{len(readonly_updated)}`"
            )
            await self._send_log(guild, data, "Permissoes aplicadas", text)
            await send_system_log(self.bot, guild, title="Permissoes organizadas", system="Organizador", description=text, actor=inter.user, config=data)
            await self._send_done(inter, text)

    async def _handle_custom_role(self, inter: disnake.ModalInteraction):
        if not await self._defer(inter):
            return
        if not self._can_manage(inter):
            await self._send_done(inter, f"{emoji.wrong} Voce precisa de permissao de **Gerenciar Servidor**.")
            return
        bot_perms = self._bot_permissions(inter.guild)
        if not bot_perms.manage_roles:
            await self._send_done(inter, f"{emoji.wrong} O bot precisa de **Gerenciar Cargos**.")
            return

        values = getattr(inter, "text_values", {}) or {}
        name = str(values.get("name") or "").strip()[:80]
        if len(name) < 2:
            await self._send_done(inter, f"{emoji.wrong} Nome de cargo invalido.")
            return
        existing = self._existing_role_by_name(inter.guild, name)
        if existing:
            await self._send_done(inter, f"{emoji.wrong} Ja existe um cargo chamado **{existing.name}**.")
            return

        preset = str(values.get("preset") or "none").strip().lower()
        if preset not in ROLE_PERMISSION_PRESETS:
            preset = "none"
        hoist = str(values.get("hoist") or "").strip().lower() in {"sim", "s", "yes", "true", "1"}
        colour = self._colour(values.get("colour"))

        role = await inter.guild.create_role(
            name=name,
            colour=disnake.Colour(colour),
            permissions=self._permissions(preset),
            hoist=hoist,
            mentionable=True,
            reason="Lyon Pro - cargo personalizado",
        )
        data = self._get_data(inter.guild.id)
        data.setdefault("created_roles", {})[_slug(name)] = str(role.id)
        data["last_action"] = f"Cargo personalizado criado: {role.name}"
        data["last_run_at"] = _now()
        self._save_data(inter.guild.id, data)
        text = f"{emoji.correct} Cargo {role.mention} criado com preset `{preset}`."
        await self._send_log(inter.guild, data, "Cargo personalizado", text)
        await send_system_log(self.bot, inter.guild, title="Cargo personalizado criado", system="Organizador", description=text, actor=inter.user, config=data)
        await self._send_done(inter, text)


def setup(bot: commands.Bot):
    bot.add_cog(ServerOrganizerPanel(bot))
