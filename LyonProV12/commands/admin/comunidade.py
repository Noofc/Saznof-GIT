from __future__ import annotations

import secrets
from datetime import datetime

import disnake
from disnake.ext import commands

from functions import auto_setup
from functions.database import database as db
from functions.emoji import emoji
from functions.system_logs import send_system_log
from .panel_v2 import build_panel_card
from .painel.components import PainelComponents


KEY_PREFIX = "comunidade_"

MODULES = {
    "verification": "Verificacao",
    "registration": "Registro",
    "family": "Familia",
    "suggestions": "Sugestoes",
    "events": "Eventos",
    "social": "Redes sociais",
    "instagram": "Instagram",
    "partnerships": "Parcerias",
    "creators": "Criadores",
}

MODULE_EMOJIS = {
    "verification": "verified",
    "registration": "members",
    "family": "heart",
    "suggestions": "bulb",
    "events": "calendar",
    "social": "link",
    "instagram": "image",
    "partnerships": "partner",
    "creators": "star",
}

COMMUNITY_CHANNELS = [
    {"key": "hub", "label": "central-comunidade", "emoji": "🏠", "module": None},
    {"key": "rules", "label": "regras", "emoji": "📜", "module": None},
    {"key": "announcements", "label": "avisos", "emoji": "📢", "module": None},
    {"key": "chat", "label": "chat-geral", "emoji": "💬", "module": None},
    {"key": "introductions", "label": "apresentacoes", "emoji": "👋", "module": "registration"},
    {"key": "verification", "label": "verificacao", "emoji": "✅", "module": "verification"},
    {"key": "suggestions", "label": "sugestoes", "emoji": "💡", "module": "suggestions"},
    {"key": "events", "label": "eventos", "emoji": "📅", "module": "events"},
    {"key": "instagram", "label": "instagram", "emoji": "📸", "module": "instagram"},
    {"key": "social", "label": "redes-sociais", "emoji": "🔗", "module": "social"},
    {"key": "partnerships", "label": "parcerias", "emoji": "🤝", "module": "partnerships"},
    {"key": "creators", "label": "criadores", "emoji": "🎬", "module": "creators"},
    {"key": "logs", "label": "logs-comunidade", "emoji": "📋", "module": None, "private": True},
]

COMMUNITY_ROLES = [
    ("member", "Membro"),
    ("verified", "Verificado"),
    ("creator", "Criador"),
    ("partner", "Parceiro"),
    ("community_staff", "Staff Comunidade"),
    ("family_leader", "Lider Familia"),
]


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _clean_id(value) -> str:
    raw = str(value or "").replace("<#", "").replace(">", "").strip()
    return raw if raw.isdigit() else ""


class Comunidade(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _flags(self) -> disnake.MessageFlags:
        return disnake.MessageFlags(is_components_v2=True)

    def _key(self, guild_id: int) -> str:
        return f"{KEY_PREFIX}{guild_id}"

    def _default_config(self) -> dict:
        setup = auto_setup.get_config()
        return {
            "enabled": False,
            "modules": {
                "verification": True,
                "registration": True,
                "family": False,
                "suggestions": True,
                "events": True,
                "social": True,
                "instagram": True,
                "partnerships": True,
                "creators": True,
            },
            "separator": setup.get("separator") or "╺╸",
            "channel_pattern": setup.get("channel_pattern") or "{emoji}{separator}{name}",
            "role_pattern": setup.get("role_pattern") or "{name}",
            "category_name": setup.get("community_category") or "╺╸ Comunidade",
            "logs_category_name": setup.get("logs_category") or "╺╸ Logs",
            "private_logs": True,
            "tag_bio": "",
            "logs_channel": "",
            "hub_channel": "",
            "verification_channel": "",
            "channels": {},
            "roles": {},
            "suggestions": {},
            "hub_title": "Central da Comunidade",
            "hub_description": "Use os botoes para se apresentar, enviar sugestoes, acompanhar eventos e acessar as redes sociais.",
            "last_structure_at": "",
            "last_hub_message": "",
        }

    def _get_config(self, guild_id: int) -> dict:
        data = db.get_document(self._key(guild_id)) or {}
        if not isinstance(data, dict):
            data = {}

        changed = False
        defaults = self._default_config()
        for key, value in defaults.items():
            if key not in data:
                data[key] = value.copy() if isinstance(value, dict) else value
                changed = True

        if not isinstance(data.get("modules"), dict):
            data["modules"] = defaults["modules"].copy()
            changed = True
        for key, value in defaults["modules"].items():
            if key not in data["modules"]:
                data["modules"][key] = value
                changed = True

        for field in ("channels", "roles", "suggestions"):
            if not isinstance(data.get(field), dict):
                data[field] = {}
                changed = True

        if changed:
            self._save_config(guild_id, data)
        return data

    def _save_config(self, guild_id: int, data: dict) -> None:
        db.save_document(self._key(guild_id), data)

    def _channel_name(self, cfg: dict, channel: dict) -> str:
        base = auto_setup.slugify(channel.get("label"))
        return (
            str(cfg.get("channel_pattern") or "{emoji}{separator}{name}")
            .replace("{emoji}", channel.get("emoji") or "📌")
            .replace("{separator}", str(cfg.get("separator") or "╺╸"))
            .replace("{sep}", str(cfg.get("separator") or "╺╸"))
            .replace("{name}", base)
            .replace("{nome}", base)
        )[:100]

    def _role_name(self, cfg: dict, key: str, label: str) -> str:
        return auto_setup.role_name(f"comunidade_{key}", label, {"role_pattern": cfg.get("role_pattern"), "separator": cfg.get("separator"), "role_names": {}})

    def _channel_text(self, guild: disnake.Guild | None, channel_id) -> str:
        raw = _clean_id(channel_id)
        if not raw:
            return "`Nao configurado`"
        channel = guild.get_channel(int(raw)) if guild else None
        return channel.mention if channel else f"<#{raw}>"

    def _module_status(self, cfg: dict, key: str) -> str:
        return "Ativo" if cfg.get("modules", {}).get(key) else "Inativo"

    def display_comunidade_panel(self, inter: disnake.MessageInteraction):
        cfg = self._get_config(inter.guild.id)
        modules_on = sum(1 for value in cfg.get("modules", {}).values() if value)
        channels = cfg.get("channels", {})
        roles = cfg.get("roles", {})

        return build_panel_card(
            title="Comunidade",
            breadcrumb="Painel > Sistemas > Comunidade",
            description="Central para servidores que estao construindo comunidade: estrutura, redes sociais, apresentacoes, sugestoes, eventos, cargos e logs.",
            status_lines=[
                f"**Status:** `{'Ativo' if cfg.get('enabled') else 'Inativo'}`",
                f"**Modulos ativos:** `{modules_on}/{len(MODULES)}`",
                f"**Canal hub:** {self._channel_text(inter.guild, cfg.get('hub_channel'))}",
                f"**Canal logs:** {self._channel_text(inter.guild, cfg.get('logs_channel'))}",
                f"**Estrutura:** `{len(channels)}` canais • `{len(roles)}` cargos",
                f"**Modelo canais:** `{cfg.get('channel_pattern')}` com separador `{cfg.get('separator')}`",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Desativar" if cfg.get("enabled") else "Ativar", style=disnake.ButtonStyle.danger if cfg.get("enabled") else disnake.ButtonStyle.success, emoji=getattr(emoji, "power", None), custom_id="Comunidade_Toggle"),
                    disnake.ui.Button(label="Modulos", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "settings", None), custom_id="Comunidade_Modules"),
                    disnake.ui.Button(label="Personalizar", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "edit", None), custom_id="Comunidade_Customize"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Criar estrutura", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "wand", None), custom_id="Comunidade_CreateStructure"),
                    disnake.ui.Button(label="Publicar hub", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "announcement", None), custom_id="Comunidade_PublishHub"),
                    disnake.ui.Button(label="Canal hub", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "textc", None), custom_id="Comunidade_SetHub"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Logs", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "receipt", None), custom_id="Comunidade_SetLogs"),
                    disnake.ui.Button(label="Verificacao", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "correct", None), custom_id="Comunidade_SetVerification"),
                    disnake.ui.Button(label="Tag/Bio", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "tag", None), custom_id="Comunidade_TagBio"),
                ),
            ],
        )

    def _modules_components(self, inter: disnake.MessageInteraction) -> list:
        cfg = self._get_config(inter.guild.id)
        rows = []
        items = list(MODULES.items())
        for index in range(0, len(items), 3):
            buttons = []
            for key, label in items[index:index + 3]:
                active = bool(cfg.get("modules", {}).get(key))
                buttons.append(
                    disnake.ui.Button(
                        label=label,
                        style=disnake.ButtonStyle.green if active else disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, MODULE_EMOJIS.get(key, "commands"), None),
                        custom_id=f"Comunidade_Module:{key}",
                    )
                )
            rows.append(disnake.ui.ActionRow(*buttons))

        return build_panel_card(
            title="Modulos da Comunidade",
            breadcrumb="Painel > Comunidade > Modulos",
            description="Ative apenas o que a comunidade vai usar. A criacao de estrutura respeita esses modulos.",
            status_lines=[f"**{label}:** `{self._module_status(cfg, key)}`" for key, label in MODULES.items()],
            rows=rows,
            include_back=False,
        )

    def _hub_components(self, guild_id: int) -> list:
        cfg = self._get_config(guild_id)
        title = str(cfg.get("hub_title") or "Central da Comunidade")[:100]
        description = str(cfg.get("hub_description") or "")[:1200]
        modules = cfg.get("modules", {})

        buttons = [
            disnake.ui.Button(label="Apresentar-se", style=disnake.ButtonStyle.green, emoji=getattr(emoji, "members", None), custom_id="Comunidade_PublicIntro", disabled=not modules.get("registration")),
            disnake.ui.Button(label="Sugestao", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "bulb", None), custom_id="Comunidade_PublicSuggestion", disabled=not modules.get("suggestions")),
            disnake.ui.Button(label="Eventos", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "calendar", None), custom_id="Comunidade_PublicEvent", disabled=not modules.get("events")),
            disnake.ui.Button(label="Instagram", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "image", None), custom_id="Comunidade_PublicInstagram", disabled=not modules.get("instagram")),
        ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {title}\n\n{description}\n\n-# Comunidade operacional • {_now()}"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(*buttons),
                accent_colour=self._accent_colour(),
            )
        ]

    def _suggestion_components(self, suggestion_id: str, suggestion: dict) -> list:
        upvotes = len(suggestion.get("upvotes", []))
        downvotes = len(suggestion.get("downvotes", []))
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"## {getattr(emoji, 'bulb', '')} {suggestion.get('title')}\n"
                    f"{suggestion.get('description')}\n\n"
                    f"**Autor:** <@{suggestion.get('author_id')}>\n"
                    f"**Votos:** `{upvotes}` a favor • `{downvotes}` contra"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label=str(upvotes), style=disnake.ButtonStyle.green, emoji=getattr(emoji, "like", None), custom_id=f"Comunidade_Vote:{suggestion_id}:up"),
                    disnake.ui.Button(label=str(downvotes), style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "deslike", None), custom_id=f"Comunidade_Vote:{suggestion_id}:down"),
                ),
                accent_colour=self._accent_colour(),
            )
        ]

    def _accent_colour(self) -> disnake.Colour:
        colors = db.get_document("custom_colors") or {}
        color_hex = colors.get("primary") if isinstance(colors, dict) else None
        if color_hex:
            try:
                return disnake.Colour(int(color_hex.replace("#", ""), 16))
            except Exception:
                pass
        return disnake.Colour.blurple()

    def _get_channel(self, guild: disnake.Guild, channel_id):
        raw = _clean_id(channel_id)
        return guild.get_channel(int(raw)) if raw else None

    async def _get_or_create_category(self, guild: disnake.Guild, name: str, reason: str):
        clean = str(name or "╺╸ Comunidade").strip()[:100]
        category = next((c for c in guild.categories if c.name.lower() == clean.lower()), None)
        if category:
            return category
        return await guild.create_category(clean, reason=reason)

    async def _create_structure(self, inter: disnake.MessageInteraction, cfg: dict) -> tuple[list, list]:
        guild = inter.guild
        reason = f"Estrutura de comunidade - {inter.user.name} ({inter.user.id})"
        category = await self._get_or_create_category(guild, cfg.get("category_name"), reason)
        logs_category = await self._get_or_create_category(guild, cfg.get("logs_category_name"), reason)
        created_channels = []
        created_roles = []

        for channel in COMMUNITY_CHANNELS:
            module = channel.get("module")
            if module and not cfg.get("modules", {}).get(module):
                continue

            existing_id = _clean_id(cfg.get("channels", {}).get(channel["key"]))
            if existing_id and guild.get_channel(int(existing_id)):
                continue

            name = self._channel_name(cfg, channel)
            existing = disnake.utils.get(guild.text_channels, name=name)
            if existing:
                cfg["channels"][channel["key"]] = str(existing.id)
                continue

            is_private = bool(channel.get("private"))
            overwrites = {}
            if is_private and cfg.get("private_logs", True):
                overwrites[guild.default_role] = disnake.PermissionOverwrite(view_channel=False)

            ch = await guild.create_text_channel(
                name,
                category=logs_category if is_private else category,
                overwrites=overwrites,
                reason=reason,
            )
            cfg["channels"][channel["key"]] = str(ch.id)
            created_channels.append(ch)

            if channel["key"] == "logs":
                cfg["logs_channel"] = str(ch.id)
            elif channel["key"] == "hub":
                cfg["hub_channel"] = str(ch.id)
            elif channel["key"] == "verification":
                cfg["verification_channel"] = str(ch.id)

        for role_key, label in COMMUNITY_ROLES:
            existing_id = str(cfg.get("roles", {}).get(role_key) or "")
            if existing_id.isdigit() and guild.get_role(int(existing_id)):
                continue

            name = self._role_name(cfg, role_key, label)
            existing = disnake.utils.get(guild.roles, name=name)
            if existing:
                cfg["roles"][role_key] = str(existing.id)
                continue

            role = await guild.create_role(name=name, reason=reason)
            cfg["roles"][role_key] = str(role.id)
            created_roles.append(role)

        cfg["last_structure_at"] = _now()
        return created_channels, created_roles

    async def _open_customize_modal(self, inter: disnake.MessageInteraction):
        cfg = self._get_config(inter.guild.id)
        source_message = inter.message
        cog = self

        class CustomizeModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Personalizar comunidade",
                    custom_id="Comunidade_CustomizeModal",
                    components=[
                        disnake.ui.TextInput(label="Separador", custom_id="separator", value=str(cfg.get("separator") or "╺╸")[:20], max_length=20, required=True),
                        disnake.ui.TextInput(label="Modelo de canal", custom_id="channel_pattern", value=str(cfg.get("channel_pattern") or "{emoji}{separator}{name}")[:80], max_length=80, required=True),
                        disnake.ui.TextInput(label="Modelo de cargo", custom_id="role_pattern", value=str(cfg.get("role_pattern") or "{name}")[:80], max_length=80, required=True),
                        disnake.ui.TextInput(label="Categoria da comunidade", custom_id="category_name", value=str(cfg.get("category_name") or "╺╸ Comunidade")[:80], max_length=80, required=True),
                        disnake.ui.TextInput(label="Texto do hub", custom_id="hub_description", style=disnake.TextInputStyle.paragraph, value=str(cfg.get("hub_description") or "")[:900], max_length=900, required=True),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                data = cog._get_config(modal_inter.guild.id)
                values = modal_inter.text_values
                data["separator"] = str(values.get("separator") or "╺╸").strip()[:20]
                data["channel_pattern"] = str(values.get("channel_pattern") or "{emoji}{separator}{name}").strip()[:80]
                data["role_pattern"] = str(values.get("role_pattern") or "{name}").strip()[:80]
                data["category_name"] = str(values.get("category_name") or "╺╸ Comunidade").strip()[:80]
                data["hub_description"] = str(values.get("hub_description") or "").strip()[:900]
                cog._save_config(modal_inter.guild.id, data)
                try:
                    await source_message.edit(content=None, embed=None, components=cog.display_comunidade_panel(modal_inter), flags=cog._flags())
                except Exception:
                    pass
                await modal_inter.response.send_message(f"{emoji.correct} Comunidade personalizada.", ephemeral=True)

        await inter.response.send_modal(CustomizeModal())

    async def _open_tag_modal(self, inter: disnake.MessageInteraction):
        cfg = self._get_config(inter.guild.id)
        source_message = inter.message
        cog = self

        class TagBioModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Cargo por tag/bio",
                    custom_id="Comunidade_TagBioModal",
                    components=[
                        disnake.ui.TextInput(label="Tag ou bio obrigatoria", custom_id="tag_bio", value=str(cfg.get("tag_bio") or "")[:100], max_length=100, required=False, placeholder="#sua-comunidade"),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                data = cog._get_config(modal_inter.guild.id)
                data["tag_bio"] = str(modal_inter.text_values.get("tag_bio") or "").strip()
                cog._save_config(modal_inter.guild.id, data)
                try:
                    await source_message.edit(content=None, embed=None, components=cog.display_comunidade_panel(modal_inter), flags=cog._flags())
                except Exception:
                    pass
                await modal_inter.response.send_message(f"{emoji.correct} Tag/Bio atualizada.", ephemeral=True)

        await inter.response.send_modal(TagBioModal())

    async def _send_channel_select(self, inter: disnake.MessageInteraction, custom_id: str, text: str):
        await inter.response.send_message(
            text,
            components=[
                disnake.ui.ActionRow(
                    disnake.ui.ChannelSelect(
                        custom_id=custom_id,
                        channel_types=[disnake.ChannelType.text],
                        min_values=1,
                        max_values=1,
                    )
                )
            ],
            ephemeral=True,
        )

    async def _publish_hub(self, inter: disnake.MessageInteraction):
        cfg = self._get_config(inter.guild.id)
        if not cfg.get("enabled"):
            await inter.response.send_message(f"{emoji.wrong} Ative a comunidade antes de publicar o hub.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        channel = self._get_channel(inter.guild, cfg.get("hub_channel")) or inter.channel
        sent = await channel.send(components=self._hub_components(inter.guild.id), flags=self._flags())
        cfg["hub_channel"] = str(channel.id)
        cfg["last_hub_message"] = str(sent.id)
        self._save_config(inter.guild.id, cfg)
        await send_system_log(self.bot, inter.guild, title="Hub da comunidade publicado", system="Comunidade", description=f"Hub publicado em {channel.mention}.", actor=inter.user, config=cfg)
        await inter.followup.send(f"{emoji.correct} Hub publicado em {channel.mention}.", ephemeral=True)

    async def _handle_intro(self, inter: disnake.MessageInteraction):
        cog = self

        class IntroModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Apresentacao",
                    custom_id="Comunidade_IntroModal",
                    components=[
                        disnake.ui.TextInput(label="Nome/apelido", custom_id="name", max_length=80, required=True),
                        disnake.ui.TextInput(label="Sobre voce", custom_id="about", style=disnake.TextInputStyle.paragraph, max_length=800, required=True),
                        disnake.ui.TextInput(label="Interesses", custom_id="interests", max_length=160, required=False, placeholder="games, design, estudo, networking..."),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                cfg = cog._get_config(modal_inter.guild.id)
                channel = cog._get_channel(modal_inter.guild, cfg.get("channels", {}).get("introductions")) or cog._get_channel(modal_inter.guild, cfg.get("hub_channel")) or modal_inter.channel
                values = modal_inter.text_values
                await channel.send(
                    components=[
                        disnake.ui.Container(
                            disnake.ui.TextDisplay(
                                f"## {getattr(emoji, 'members', '')} Nova apresentacao\n"
                                f"**Membro:** {modal_inter.user.mention}\n"
                                f"**Nome:** `{values.get('name')}`\n"
                                f"**Interesses:** `{values.get('interests') or 'Nao informado'}`\n\n"
                                f"{values.get('about')}"
                            ),
                            accent_colour=cog._accent_colour(),
                        )
                    ],
                    flags=cog._flags(),
                )
                await send_system_log(cog.bot, modal_inter.guild, title="Apresentacao enviada", system="Comunidade", description=f"{modal_inter.user.mention} enviou uma apresentacao em {channel.mention}.", actor=modal_inter.user, config=cfg)
                await modal_inter.response.send_message(f"{emoji.correct} Sua apresentacao foi enviada em {channel.mention}.", ephemeral=True)

        await inter.response.send_modal(IntroModal())

    async def _handle_suggestion(self, inter: disnake.MessageInteraction):
        cog = self

        class SuggestionModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Enviar sugestao",
                    custom_id="Comunidade_SuggestionModal",
                    components=[
                        disnake.ui.TextInput(label="Titulo", custom_id="title", max_length=100, required=True),
                        disnake.ui.TextInput(label="Sugestao", custom_id="description", style=disnake.TextInputStyle.paragraph, max_length=1200, required=True),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                cfg = cog._get_config(modal_inter.guild.id)
                suggestion_id = secrets.token_hex(3)
                suggestion = {
                    "title": str(modal_inter.text_values.get("title") or "").strip(),
                    "description": str(modal_inter.text_values.get("description") or "").strip(),
                    "author_id": str(modal_inter.user.id),
                    "upvotes": [],
                    "downvotes": [],
                    "created_at": _now(),
                }
                cfg.setdefault("suggestions", {})[suggestion_id] = suggestion
                cog._save_config(modal_inter.guild.id, cfg)
                channel = cog._get_channel(modal_inter.guild, cfg.get("channels", {}).get("suggestions")) or cog._get_channel(modal_inter.guild, cfg.get("hub_channel")) or modal_inter.channel
                await channel.send(components=cog._suggestion_components(suggestion_id, suggestion), flags=cog._flags())
                await send_system_log(cog.bot, modal_inter.guild, title="Sugestao enviada", system="Comunidade", description=f"Sugestao `{suggestion['title']}` enviada em {channel.mention}.", actor=modal_inter.user, config=cfg)
                await modal_inter.response.send_message(f"{emoji.correct} Sugestao enviada em {channel.mention}.", ephemeral=True)

        await inter.response.send_modal(SuggestionModal())

    @commands.Cog.listener("on_message_interaction")
    async def on_comunidade_interaction(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Comunidade_"):
            return

        guild_id = inter.guild.id
        cfg = self._get_config(guild_id)

        if custom_id == "Comunidade_Toggle":
            cfg["enabled"] = not bool(cfg.get("enabled"))
            self._save_config(guild_id, cfg)
            await inter.response.defer(with_message=False)
            await inter.edit_original_message(content=None, embed=None, components=self.display_comunidade_panel(inter), flags=self._flags())
            await send_system_log(self.bot, inter.guild, title="Comunidade alterada", system="Comunidade", description=f"Status definido como `{'Ativo' if cfg.get('enabled') else 'Inativo'}`.", actor=inter.user, config=cfg)
            return

        if custom_id == "Comunidade_Modules":
            await inter.response.defer(with_message=False)
            await inter.edit_original_message(content=None, embed=None, components=self._modules_components(inter), flags=self._flags())
            return

        if custom_id == "Comunidade_Back":
            await inter.response.defer(with_message=False)
            await inter.edit_original_message(content=None, embed=None, components=PainelComponents(inter), flags=self._flags())
            return

        if custom_id.startswith("Comunidade_Module:"):
            module = custom_id.split(":", 1)[1]
            if module in MODULES:
                cfg.setdefault("modules", {})[module] = not bool(cfg.get("modules", {}).get(module))
                self._save_config(guild_id, cfg)
            await inter.response.defer(with_message=False)
            await inter.edit_original_message(content=None, embed=None, components=self._modules_components(inter), flags=self._flags())
            return

        if custom_id == "Comunidade_Customize":
            await self._open_customize_modal(inter)
            return

        if custom_id == "Comunidade_TagBio":
            await self._open_tag_modal(inter)
            return

        if custom_id == "Comunidade_SetLogs":
            await self._send_channel_select(inter, "Comunidade_SelectLogs", "Selecione o canal de logs da comunidade.")
            return

        if custom_id == "Comunidade_SetHub":
            await self._send_channel_select(inter, "Comunidade_SelectHub", "Selecione o canal onde o hub da comunidade sera publicado.")
            return

        if custom_id == "Comunidade_SetVerification":
            await self._send_channel_select(inter, "Comunidade_SelectVerification", "Selecione o canal de verificacao da comunidade.")
            return

        if custom_id in {"Comunidade_SelectLogs", "Comunidade_SelectHub", "Comunidade_SelectVerification"}:
            channel_id = _clean_id(inter.values[0] if getattr(inter, "values", None) else "")
            if not channel_id:
                await inter.response.edit_message(content=f"{emoji.wrong} Canal invalido.", components=[])
                return
            if custom_id == "Comunidade_SelectLogs":
                cfg["logs_channel"] = channel_id
                text = f"{emoji.correct} Logs definidos em <#{channel_id}>."
            elif custom_id == "Comunidade_SelectHub":
                cfg["hub_channel"] = channel_id
                cfg.setdefault("channels", {})["hub"] = channel_id
                text = f"{emoji.correct} Hub definido em <#{channel_id}>."
            else:
                cfg["verification_channel"] = channel_id
                cfg.setdefault("channels", {})["verification"] = channel_id
                text = f"{emoji.correct} Verificacao definida em <#{channel_id}>."
            self._save_config(guild_id, cfg)
            await inter.response.edit_message(content=text, components=[])
            return

        if custom_id == "Comunidade_CreateStructure":
            await inter.response.defer(ephemeral=True)
            try:
                created_channels, created_roles = await self._create_structure(inter, cfg)
            except Exception as exc:
                await inter.followup.send(f"{emoji.wrong} Nao consegui criar a estrutura: `{exc}`", ephemeral=True)
                return
            self._save_config(guild_id, cfg)
            await send_system_log(
                self.bot,
                inter.guild,
                title="Estrutura de comunidade criada",
                system="Comunidade",
                description=f"Canais criados: `{len(created_channels)}`\nCargos criados: `{len(created_roles)}`",
                actor=inter.user,
                config=cfg,
            )
            await inter.followup.send(f"{emoji.correct} Estrutura pronta: `{len(created_channels)}` canais e `{len(created_roles)}` cargos criados.", ephemeral=True)
            return

        if custom_id == "Comunidade_PublishHub":
            await self._publish_hub(inter)
            return

        if custom_id == "Comunidade_PublicIntro":
            await self._handle_intro(inter)
            return

        if custom_id == "Comunidade_PublicSuggestion":
            await self._handle_suggestion(inter)
            return

        if custom_id == "Comunidade_PublicEvent":
            channel = self._get_channel(inter.guild, cfg.get("channels", {}).get("events")) or self._get_channel(inter.guild, cfg.get("hub_channel")) or inter.channel
            await inter.response.send_message(f"{emoji.correct} Os eventos da comunidade ficam em {channel.mention}.", ephemeral=True)
            return

        if custom_id == "Comunidade_PublicInstagram":
            social = self.bot.get_cog("SocialLyonsPanel")
            link = ""
            if social:
                try:
                    link = social.get_system("instagram").get("link_url") or ""
                except Exception:
                    link = ""
            if link:
                await inter.response.send_message(f"{emoji.correct} Instagram da comunidade: {link}", ephemeral=True)
            else:
                await inter.response.send_message(f"{emoji.wrong} O Instagram ainda nao foi configurado no painel de Instagram.", ephemeral=True)
            return

        if custom_id.startswith("Comunidade_Vote:"):
            _, suggestion_id, direction = custom_id.split(":", 2)
            suggestions = cfg.setdefault("suggestions", {})
            suggestion = suggestions.get(suggestion_id)
            if not suggestion:
                await inter.response.send_message(f"{emoji.wrong} Sugestao nao encontrada.", ephemeral=True)
                return
            user_id = str(inter.user.id)
            suggestion.setdefault("upvotes", [])
            suggestion.setdefault("downvotes", [])
            suggestion["upvotes"] = [uid for uid in suggestion["upvotes"] if uid != user_id]
            suggestion["downvotes"] = [uid for uid in suggestion["downvotes"] if uid != user_id]
            if direction == "up":
                suggestion["upvotes"].append(user_id)
            else:
                suggestion["downvotes"].append(user_id)
            self._save_config(guild_id, cfg)
            await inter.response.edit_message(components=self._suggestion_components(suggestion_id, suggestion), flags=self._flags())
            return


def setup(bot: commands.Bot):
    bot.add_cog(Comunidade(bot))
