from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
import disnake
from disnake.ext import commands, tasks

from functions.database import database as db
from functions.emoji import emoji
from functions.perms import perms
from .painel.components import PainelComponents


DATA_PATH = "database/fivem_system.json"


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


def _now_ts() -> int:
    return int(datetime.utcnow().timestamp())


def _duration_text(seconds: int) -> str:
    seconds = max(int(seconds or 0), 0)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _user(inter: disnake.Interaction):
    return getattr(inter, "user", None) or getattr(inter, "author", None)


def _id(value: str | None) -> str:
    raw = str(value or "").strip()
    for token in ("<@", "<@!", "<#", "<@&", ">"):
        raw = raw.replace(token, "")
    return raw if raw.isdigit() else ""


def _url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if "." in raw or ":" in raw:
        return f"http://{raw}"
    return raw


def _server_label(endpoint: str) -> str:
    if not endpoint:
        return "Nao vinculado"
    return endpoint[:90]


def _slug(value: str) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return (raw or "fac")[:32]


def _default_data() -> dict:
    return {
        "enabled": True,
        "city_name": "SYSTEM PRO",
        "server_endpoint": "",
        "join_url": "",
        "panel_channel_id": "",
        "panel_message_id": "",
        "status_panel_channel_id": "",
        "status_panel_message_id": "",
        "staff_panel_channel_id": "",
        "staff_panel_message_id": "",
        "log_channel_id": "",
        "staff_role_id": "",
        "whitelist_role_id": "",
        "panel_title": "PLANO FIVEM - SYSTEM PRO",
        "panel_description": (
            "OPERAÇÃO DE CIDADE EFICIENTE E ESCALÁVEL\n\n"
            "Padronize processos, reduza ruído operacional e entregue mais consistência para staff e jogadores.\n\n"
            "SISTEMAS INCLUSOS\n"
            "Whitelist + Painel • Notificações + Logs + Moderação\n\n"
            "SISTEMAS\n"
            "WHITELIST E CADASTRO\n"
            "Fluxo de entrada inteligente. Dados organizados e critérios revisáveis.\n\n"
            "PAINEL DO GESTOR\n"
            "Indicadores essenciais e visão operacional. Alertas e acompanhamento do time.\n\n"
            "NOTIFICAÇÕES E LOGS\n"
            "Eventos críticos com registro claro. Histórico auditável e fácil de consultar."
        ),
        "linked_ids": {},
        "whitelist": {},
        "factions": {},
        "faction_requests": {},
        "recruitment_requests": {},
        "blacklist": {},
        "punishments": [],
        "audit_logs": [],
        "alerts": {
            "server_down": True,
            "server_full_percent": 90,
            "pending_whitelist_limit": 5,
        },
        "auto_setup": {
            "separator": "╺╸",
            "category_name": "╺╸ FiveM",
            "logs_category_name": "╺╸ Logs FiveM",
            "staff_role_name": "FiveM Staff",
            "whitelist_role_name": "Cidadão",
        },
        "staff_sessions": {},
        "staff_time_records": [],
        "last_published_at": None,
        "last_status_panel_update": None,
        "last_staff_panel_update": None,
        "last_checked_at": None,
        "last_alerts": {},
        "cache": {
            "online": 0,
            "max": 0,
            "hostname": "",
            "players": [],
            "error": "",
        },
    }


class FiveMServerModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        cfg = cog.load()
        components = [
            disnake.ui.TextInput(
                label="Nome da cidade",
                custom_id="city_name",
                value=str(cfg.get("city_name") or "SYSTEM PRO")[:80],
                max_length=80,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Servidor FiveM",
                custom_id="server_endpoint",
                value=str(cfg.get("server_endpoint") or "")[:180],
                placeholder="IP:porta, http://IP:porta ou codigo cfx.re/join",
                max_length=180,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Link de entrada",
                custom_id="join_url",
                value=str(cfg.get("join_url") or "")[:300],
                placeholder="https://cfx.re/join/abc123",
                max_length=300,
                required=False,
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
        ]
        super().__init__(title="Vincular Servidor FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        self.cog.update(
            {
                "city_name": str(inter.text_values.get("city_name") or "SYSTEM PRO").strip(),
                "server_endpoint": _url(inter.text_values.get("server_endpoint")),
                "join_url": _url(inter.text_values.get("join_url")),
                "panel_channel_id": _id(inter.text_values.get("panel_channel_id")),
                "log_channel_id": _id(inter.text_values.get("log_channel_id")),
            }
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Servidor FiveM vinculado/configurado.",
            ephemeral=True,
        )


class FiveMRolesTextModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        cfg = cog.load()
        components = [
            disnake.ui.TextInput(
                label="Titulo do painel",
                custom_id="panel_title",
                value=str(cfg.get("panel_title") or "PLANO FIVEM - SYSTEM PRO")[:100],
                max_length=100,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Descricao do painel",
                custom_id="panel_description",
                style=disnake.TextInputStyle.paragraph,
                value=str(cfg.get("panel_description") or "")[:1800],
                max_length=1800,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Cargo da staff",
                custom_id="staff_role_id",
                value=str(cfg.get("staff_role_id") or "")[:32],
                placeholder="ID ou mencao do cargo",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Cargo aprovado na whitelist",
                custom_id="whitelist_role_id",
                value=str(cfg.get("whitelist_role_id") or "")[:32],
                placeholder="ID ou mencao do cargo",
                max_length=32,
                required=False,
            ),
        ]
        super().__init__(title="Textos e Cargos FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        self.cog.update(
            {
                "panel_title": str(inter.text_values.get("panel_title") or "").strip(),
                "panel_description": str(inter.text_values.get("panel_description") or "").strip(),
                "staff_role_id": _id(inter.text_values.get("staff_role_id")),
                "whitelist_role_id": _id(inter.text_values.get("whitelist_role_id")),
            }
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Textos e cargos do FiveM atualizados.",
            ephemeral=True,
        )


class FiveMPublicPanelsModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        cfg = cog.load()
        components = [
            disnake.ui.TextInput(
                label="Canal do painel principal",
                custom_id="panel_channel_id",
                value=str(cfg.get("panel_channel_id") or "")[:32],
                placeholder="ID ou mencao do canal",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Canal do status publico",
                custom_id="status_panel_channel_id",
                value=str(cfg.get("status_panel_channel_id") or "")[:32],
                placeholder="ID ou mencao do canal de status da cidade",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Canal do painel da staff",
                custom_id="staff_panel_channel_id",
                value=str(cfg.get("staff_panel_channel_id") or cfg.get("staff_point_channel_id") or "")[:32],
                placeholder="ID ou mencao do canal da staff",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Canal de whitelist",
                custom_id="whitelist_channel_id",
                value=str(cfg.get("whitelist_channel_id") or "")[:32],
                placeholder="Opcional: ID ou mencao",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Canal de faccoes/recrutamento",
                custom_id="factions_channel_id",
                value=str(cfg.get("factions_channel_id") or "")[:32],
                placeholder="Opcional: ID ou mencao",
                max_length=32,
                required=False,
            ),
        ]
        super().__init__(title="Paineis Publicos FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        self.cog.update(
            {
                "panel_channel_id": _id(inter.text_values.get("panel_channel_id")),
                "status_panel_channel_id": _id(inter.text_values.get("status_panel_channel_id")),
                "staff_panel_channel_id": _id(inter.text_values.get("staff_panel_channel_id")),
                "whitelist_channel_id": _id(inter.text_values.get("whitelist_channel_id")),
                "factions_channel_id": _id(inter.text_values.get("factions_channel_id")),
            }
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Canais publicos do FiveM salvos.",
            ephemeral=True,
        )


class FiveMLinkIdModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        components = [
            disnake.ui.TextInput(label="ID / Passaporte", custom_id="citizen_id", max_length=32, required=True),
            disnake.ui.TextInput(label="Nome do personagem", custom_id="character_name", max_length=80, required=True),
        ]
        super().__init__(title="Vincular ID FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        user = _user(inter)
        user_id = str(user.id)
        data = self.cog.load()
        citizen_id = str(inter.text_values.get("citizen_id") or "").strip()
        blocked = self.cog._find_blacklist(data, user_id=user_id, citizen_id=citizen_id)
        if blocked:
            await inter.response.send_message(self.cog._blocked_text(blocked), ephemeral=True)
            return
        existing_owner = self.cog._citizen_owner(data, citizen_id, ignore_user_id=user_id)
        if existing_owner:
            await inter.response.send_message(
                f"{_emoji('wrong', 'wrong')} Esse ID/passaporte ja esta vinculado em <@{existing_owner}>.",
                ephemeral=True,
            )
            return
        data.setdefault("linked_ids", {})[user_id] = {
            "citizen_id": citizen_id,
            "character_name": str(inter.text_values.get("character_name") or "").strip(),
            "discord_name": str(user),
            "updated_at": _now(),
        }
        self.cog.record_event(data, "linked_id_updated", user_id, user, data["linked_ids"][user_id])
        self.cog.save(data)
        await self.cog.send_log(
            f"{_emoji('link', 'link')} **ID vinculado**\n"
            f"Usuário: {user.mention}\n"
            f"ID: `{data['linked_ids'][user_id]['citizen_id']}`\n"
            f"Personagem: `{data['linked_ids'][user_id]['character_name']}`"
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Seu ID foi vinculado com sucesso.",
            ephemeral=True,
        )


class FiveMWhitelistModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        components = [
            disnake.ui.TextInput(label="ID / Passaporte", custom_id="citizen_id", max_length=32, required=True),
            disnake.ui.TextInput(label="Nome do personagem", custom_id="character_name", max_length=80, required=True),
            disnake.ui.TextInput(label="Idade", custom_id="age", max_length=8, required=False),
            disnake.ui.TextInput(
                label="Experiencia / motivo",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=900,
                required=True,
            ),
        ]
        super().__init__(title="Solicitar Whitelist", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        user = _user(inter)
        user_id = str(user.id)
        data = self.cog.load()
        citizen_id = str(inter.text_values.get("citizen_id") or "").strip()
        blocked = self.cog._find_blacklist(data, user_id=user_id, citizen_id=citizen_id)
        if blocked:
            await inter.response.send_message(self.cog._blocked_text(blocked), ephemeral=True)
            return
        existing_owner = self.cog._citizen_owner(data, citizen_id, ignore_user_id=user_id)
        if existing_owner:
            await inter.response.send_message(
                f"{_emoji('wrong', 'wrong')} Esse ID/passaporte ja esta vinculado em <@{existing_owner}>.",
                ephemeral=True,
            )
            return
        current = data.setdefault("whitelist", {}).get(user_id)
        if current and current.get("status") == "approved":
            await inter.response.send_message(
                f"{_emoji('warn', 'warn')} Sua whitelist já está aprovada.",
                ephemeral=True,
            )
            return

        request = {
            "status": "pending",
            "citizen_id": citizen_id,
            "character_name": str(inter.text_values.get("character_name") or "").strip(),
            "age": str(inter.text_values.get("age") or "").strip(),
            "reason": str(inter.text_values.get("reason") or "").strip(),
            "discord_name": str(user),
            "created_at": _now(),
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": "",
        }
        data["whitelist"][user_id] = request
        data.setdefault("linked_ids", {})[user_id] = {
            "citizen_id": request["citizen_id"],
            "character_name": request["character_name"],
            "discord_name": str(user),
            "updated_at": _now(),
        }
        self.cog.record_event(data, "whitelist_submitted", user_id, user, request)
        self.cog.save(data)

        await self.cog.send_log(
            f"{_emoji('receipt', 'receipt')} **Nova whitelist pendente**\n"
            f"Usuário: {user.mention}\n"
            f"ID: `{request['citizen_id']}`\n"
            f"Personagem: `{request['character_name']}`"
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Solicitação enviada. Aguarde a liberação da staff.",
            ephemeral=True,
        )


class FiveMFactionModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        components = [
            disnake.ui.TextInput(label="Nome da fac", custom_id="name", max_length=60, required=True),
            disnake.ui.TextInput(label="Cargo da fac", custom_id="role_id", max_length=32, placeholder="ID ou mencao do cargo", required=False),
            disnake.ui.TextInput(label="Canal da fac", custom_id="channel_id", max_length=32, placeholder="ID ou mencao do canal", required=False),
            disnake.ui.TextInput(
                label="Descricao / regras",
                custom_id="description",
                style=disnake.TextInputStyle.paragraph,
                max_length=700,
                required=False,
            ),
        ]
        super().__init__(title="Cadastrar Fac FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        name = str(inter.text_values.get("name") or "").strip()
        if not name:
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Informe o nome da fac.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)

        data = self.cog.load()
        factions = data.setdefault("factions", {})
        faction_id = _slug(name)
        base = faction_id
        count = 2
        while faction_id in factions and factions[faction_id].get("name", "").lower() != name.lower():
            faction_id = f"{base}-{count}"[:32]
            count += 1

        factions[faction_id] = {
            "id": faction_id,
            "name": name,
            "role_id": _id(inter.text_values.get("role_id")),
            "channel_id": _id(inter.text_values.get("channel_id")),
            "description": str(inter.text_values.get("description") or "").strip(),
            "created_by": str(_user(inter).id),
            "created_at": _now(),
            "enabled": True,
        }
        created_role = False
        created_channel = False
        setup_note = ""
        if not factions[faction_id].get("role_id") or not factions[faction_id].get("channel_id"):
            try:
                created_role, created_channel = await self.cog._create_faction_assets(inter, data, factions[faction_id])
            except Exception as exc:
                setup_note = f"\n{_emoji('warn', 'warn')} Fac salva, mas nao consegui criar cargo/canal automatico: `{exc}`"
        self.cog.record_event(data, "faction_created", faction_id, _user(inter), factions[faction_id])
        self.cog.save(data)
        await self.cog.send_log(
            f"{_emoji('group', 'members')} **Fac cadastrada**\n"
            f"Fac: `{name}`\n"
            f"Staff: {_user(inter).mention}\n"
            f"Cargo automatico: `{'sim' if created_role else 'nao'}` | Canal automatico: `{'sim' if created_channel else 'nao'}`"
        )
        await inter.followup.send(f"{_emoji('correct', 'correct')} Fac `{name}` cadastrada.{setup_note}", ephemeral=True)


class FiveMFactionRequestModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel", faction_id: str):
        self.cog = cog
        self.faction_id = faction_id
        components = [
            disnake.ui.TextInput(label="ID / Passaporte", custom_id="citizen_id", max_length=32, required=True),
            disnake.ui.TextInput(label="Nome do personagem", custom_id="character_name", max_length=80, required=True),
            disnake.ui.TextInput(
                label="Motivo para entrar na fac",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=700,
                required=False,
            ),
        ]
        super().__init__(title="Solicitar Fac FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        user = _user(inter)
        user_id = str(user.id)
        data = self.cog.load()
        citizen_id = str(inter.text_values.get("citizen_id") or "").strip()
        blocked = self.cog._find_blacklist(data, user_id=user_id, citizen_id=citizen_id)
        if blocked:
            await inter.response.send_message(self.cog._blocked_text(blocked), ephemeral=True)
            return
        faction = data.setdefault("factions", {}).get(self.faction_id)
        if not faction or not faction.get("enabled", True):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Fac nao encontrada ou desativada.", ephemeral=True)
            return

        requests = data.setdefault("faction_requests", {})
        current = requests.get(user_id)
        if current and current.get("status") == "pending":
            await inter.response.send_message(f"{_emoji('warn', 'warn')} Voce ja tem uma solicitacao de fac pendente.", ephemeral=True)
            return

        request = {
            "status": "pending",
            "faction_id": self.faction_id,
            "faction_name": faction.get("name"),
            "citizen_id": citizen_id,
            "character_name": str(inter.text_values.get("character_name") or "").strip(),
            "reason": str(inter.text_values.get("reason") or "").strip(),
            "discord_name": str(user),
            "created_at": _now(),
            "reviewed_by": None,
            "reviewed_at": None,
        }
        requests[user_id] = request
        data.setdefault("linked_ids", {})[user_id] = {
            "citizen_id": request["citizen_id"],
            "character_name": request["character_name"],
            "discord_name": str(user),
            "updated_at": _now(),
        }
        self.cog.record_event(data, "faction_request_submitted", user_id, user, request)
        self.cog.save(data)
        await self.cog.send_log(
            f"{_emoji('receipt', 'receipt')} **Nova solicitacao de fac**\n"
            f"Usuario: {user.mention}\n"
            f"Fac: `{faction.get('name')}`\n"
            f"ID: `{request['citizen_id']}`\n"
            f"Personagem: `{request['character_name']}`"
        )
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Solicitacao enviada para a staff.", ephemeral=True)


class FiveMRecruitmentModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        components = [
            disnake.ui.TextInput(label="Nome / ID na cidade", custom_id="citizen_id", max_length=80, required=True),
            disnake.ui.TextInput(label="Area desejada", custom_id="area", max_length=80, placeholder="Staff, fac, policia, hospital...", required=True),
            disnake.ui.TextInput(label="Disponibilidade", custom_id="availability", max_length=120, placeholder="Ex: noite e fim de semana", required=False),
            disnake.ui.TextInput(
                label="Experiencia / motivo",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=900,
                required=True,
            ),
        ]
        super().__init__(title="Formulario de Recrutamento", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        user = _user(inter)
        data = self.cog.load()
        requests = data.setdefault("recruitment_requests", {})
        user_id = str(user.id)
        citizen_id = str(inter.text_values.get("citizen_id") or "").strip()
        blocked = self.cog._find_blacklist(data, user_id=user_id, citizen_id=citizen_id)
        if blocked:
            await inter.response.send_message(self.cog._blocked_text(blocked), ephemeral=True)
            return

        for request in requests.values():
            if request.get("user_id") == user_id and request.get("status") == "pending":
                await inter.response.send_message(
                    f"{_emoji('warn', 'warn')} Voce ja tem um formulario de recrutamento pendente.",
                    ephemeral=True,
                )
                return

        request_id = f"{user_id}-{_now_ts()}"
        requests[request_id] = {
            "id": request_id,
            "user_id": user_id,
            "discord_name": str(user),
            "citizen_id": citizen_id,
            "area": str(inter.text_values.get("area") or "").strip(),
            "availability": str(inter.text_values.get("availability") or "").strip(),
            "reason": str(inter.text_values.get("reason") or "").strip(),
            "status": "pending",
            "created_at": _now(),
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": "",
        }
        self.cog.record_event(data, "recruitment_submitted", user_id, user, requests[request_id])
        self.cog.save(data)
        await self.cog.send_log(
            f"{_emoji('receipt', 'receipt')} **Novo formulario de recrutamento**\n"
            f"Usuario: {user.mention}\n"
            f"ID/Cidade: `{requests[request_id]['citizen_id']}`\n"
            f"Area: `{requests[request_id]['area']}`"
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Formulario enviado. A staff vai analisar e registrar nos logs.",
            ephemeral=True,
        )


class FiveMRejectModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel", target_id: str):
        self.cog = cog
        self.target_id = target_id
        components = [
            disnake.ui.TextInput(
                label="Motivo da rejeição",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=False,
            )
        ]
        super().__init__(title="Rejeitar Whitelist", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        await self.cog.review_whitelist(inter, self.target_id, approved=False, note=inter.text_values.get("reason") or "")


class FiveMRecruitmentRejectModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel", request_id: str):
        self.cog = cog
        self.request_id = request_id
        components = [
            disnake.ui.TextInput(
                label="Motivo da rejeicao",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=False,
            )
        ]
        super().__init__(title="Rejeitar Recrutamento", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        await self.cog.review_recruitment_request(
            inter,
            self.request_id,
            approved=False,
            note=inter.text_values.get("reason") or "",
        )


class FiveMBlacklistModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        components = [
            disnake.ui.TextInput(
                label="Usuario Discord",
                custom_id="user_id",
                placeholder="ID ou mencao. Pode deixar vazio se tiver so o passaporte.",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="ID / Passaporte",
                custom_id="citizen_id",
                placeholder="ID do personagem/cidadao",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Motivo",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=700,
                required=True,
            ),
        ]
        super().__init__(title="Adicionar Blacklist FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        if not self.cog._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode mexer na blacklist.", ephemeral=True)
            return

        user_id = _id(inter.text_values.get("user_id"))
        citizen_id = str(inter.text_values.get("citizen_id") or "").strip()
        if not user_id and not citizen_id:
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Informe o usuario ou o ID/passaporte.", ephemeral=True)
            return

        data = self.cog.load()
        key = user_id or f"id:{citizen_id.lower()}"
        data.setdefault("blacklist", {})[key] = {
            "user_id": user_id,
            "citizen_id": citizen_id,
            "reason": str(inter.text_values.get("reason") or "").strip(),
            "active": True,
            "created_by": str(_user(inter).id),
            "created_at": _now(),
        }
        self.cog.record_event(data, "blacklist_added", user_id or citizen_id, _user(inter), data["blacklist"][key])
        self.cog.save(data)

        await self.cog.send_log(
            f"{_emoji('warn', 'warn')} **Blacklist FiveM adicionada**\n"
            f"Alvo: {f'<@{user_id}>' if user_id else '`sem Discord`'}\n"
            f"ID: `{citizen_id or 'N/A'}`\n"
            f"Staff: {_user(inter).mention}\n"
            f"Motivo: `{data['blacklist'][key]['reason']}`"
        )
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Blacklist registrada.", ephemeral=True)


class FiveMUnblacklistModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        components = [
            disnake.ui.TextInput(
                label="Usuario ou ID / Passaporte",
                custom_id="target",
                placeholder="Mencao, ID Discord ou passaporte",
                max_length=64,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Motivo da remocao",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=False,
            ),
        ]
        super().__init__(title="Remover Blacklist FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        if not self.cog._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode mexer na blacklist.", ephemeral=True)
            return

        target_raw = str(inter.text_values.get("target") or "").strip()
        target_id = _id(target_raw)
        data = self.cog.load()
        removed = None
        for key, item in list(data.setdefault("blacklist", {}).items()):
            if not isinstance(item, dict) or not item.get("active", True):
                continue
            same_user = target_id and str(item.get("user_id") or "") == target_id
            same_citizen = str(item.get("citizen_id") or "").lower() == target_raw.lower()
            if same_user or same_citizen:
                item["active"] = False
                item["removed_by"] = str(_user(inter).id)
                item["removed_at"] = _now()
                item["remove_reason"] = str(inter.text_values.get("reason") or "").strip()
                removed = item
                break

        if not removed:
            await inter.response.send_message(f"{_emoji('warn', 'warn')} Nao encontrei uma blacklist ativa para esse alvo.", ephemeral=True)
            return

        self.cog.record_event(data, "blacklist_removed", target_raw, _user(inter), removed)
        self.cog.save(data)
        await self.cog.send_log(
            f"{_emoji('correct', 'correct')} **Blacklist FiveM removida**\n"
            f"Alvo: `{target_raw}`\n"
            f"Staff: {_user(inter).mention}"
        )
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Blacklist removida.", ephemeral=True)


class FiveMPunishmentModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        components = [
            disnake.ui.TextInput(
                label="Usuario Discord",
                custom_id="user_id",
                placeholder="ID ou mencao. Pode deixar vazio.",
                max_length=32,
                required=False,
            ),
            disnake.ui.TextInput(label="ID / Passaporte", custom_id="citizen_id", max_length=32, required=False),
            disnake.ui.TextInput(label="Tipo da punicao", custom_id="kind", placeholder="Advertencia, jail, ban, blacklist...", max_length=60, required=True),
            disnake.ui.TextInput(
                label="Motivo / prova",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=900,
                required=True,
            ),
        ]
        super().__init__(title="Registrar Punicao FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        if not self.cog._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode registrar punicoes.", ephemeral=True)
            return

        user_id = _id(inter.text_values.get("user_id"))
        citizen_id = str(inter.text_values.get("citizen_id") or "").strip()
        if not user_id and not citizen_id:
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Informe o usuario ou o ID/passaporte.", ephemeral=True)
            return

        data = self.cog.load()
        record = {
            "id": f"pun-{_now_ts()}-{len(data.get('punishments') or [])}",
            "user_id": user_id,
            "citizen_id": citizen_id,
            "kind": str(inter.text_values.get("kind") or "").strip(),
            "reason": str(inter.text_values.get("reason") or "").strip(),
            "created_by": str(_user(inter).id),
            "created_at": _now(),
        }
        punishments = data.setdefault("punishments", [])
        if not isinstance(punishments, list):
            punishments = []
        punishments.append(record)
        data["punishments"] = punishments[-500:]
        self.cog.record_event(data, "punishment_added", user_id or citizen_id, _user(inter), record)
        self.cog.save(data)

        await self.cog.send_log(
            f"{_emoji('warn', 'warn')} **Punicao FiveM registrada**\n"
            f"Alvo: {f'<@{user_id}>' if user_id else '`sem Discord`'}\n"
            f"ID: `{citizen_id or 'N/A'}`\n"
            f"Tipo: `{record['kind']}`\n"
            f"Staff: {_user(inter).mention}\n"
            f"Motivo: `{record['reason']}`"
        )
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Punicao registrada no historico.", ephemeral=True)


class FiveMProfileLookupModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        components = [
            disnake.ui.TextInput(
                label="Usuario, ID Discord ou Passaporte",
                custom_id="target",
                placeholder="@usuario, 123456789 ou passaporte",
                max_length=64,
                required=True,
            )
        ]
        super().__init__(title="Consultar Historico FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        if not self.cog._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode consultar historico.", ephemeral=True)
            return
        await self.cog.show_citizen_profile(inter, inter.text_values.get("target") or "")


class FiveMAlertsModal(disnake.ui.Modal):
    def __init__(self, cog: "FiveMLyonPanel"):
        self.cog = cog
        cfg = cog.load()
        alerts = cfg.get("alerts") if isinstance(cfg.get("alerts"), dict) else {}
        components = [
            disnake.ui.TextInput(
                label="Avisar cidade cheia em (%)",
                custom_id="server_full_percent",
                value=str(alerts.get("server_full_percent", 90))[:3],
                max_length=3,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Avisar whitelist pendente acima de",
                custom_id="pending_whitelist_limit",
                value=str(alerts.get("pending_whitelist_limit", 5))[:4],
                max_length=4,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Avisar servidor offline?",
                custom_id="server_down",
                value="sim" if alerts.get("server_down", True) else "nao",
                placeholder="sim ou nao",
                max_length=8,
                required=True,
            ),
        ]
        super().__init__(title="Alertas FiveM", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        if not self.cog._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode configurar alertas.", ephemeral=True)
            return

        def parse_int(value, default, minimum, maximum):
            try:
                return max(minimum, min(maximum, int(str(value).strip())))
            except Exception:
                return default

        data = self.cog.load()
        data["alerts"] = {
            "server_full_percent": parse_int(inter.text_values.get("server_full_percent"), 90, 1, 100),
            "pending_whitelist_limit": parse_int(inter.text_values.get("pending_whitelist_limit"), 5, 1, 999),
            "server_down": str(inter.text_values.get("server_down") or "sim").strip().lower() not in {"nao", "não", "off", "false", "0"},
        }
        self.cog.record_event(data, "alerts_updated", "fiveM", _user(inter), data["alerts"])
        self.cog.save(data)
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Alertas FiveM atualizados.", ephemeral=True)


class FiveMLyonPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ensure_data()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.fivem_public_panels_loop.is_running():
            self.fivem_public_panels_loop.start()

    def cog_unload(self):
        self.fivem_public_panels_loop.cancel()

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
        for key, value in defaults["cache"].items():
            if key not in data.setdefault("cache", {}):
                data["cache"][key] = value
                changed = True
        for section in ("alerts", "auto_setup"):
            section_data = data.setdefault(section, {})
            if not isinstance(section_data, dict):
                data[section] = dict(defaults[section])
                changed = True
                continue
            for key, value in defaults[section].items():
                if key not in section_data:
                    section_data[key] = value
                    changed = True
        if not isinstance(data.get("punishments"), list):
            data["punishments"] = []
            changed = True
        if not isinstance(data.get("audit_logs"), list):
            data["audit_logs"] = []
            changed = True
        if not isinstance(data.get("blacklist"), dict):
            data["blacklist"] = {}
            changed = True
        if not isinstance(data.get("last_alerts"), dict):
            data["last_alerts"] = {}
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

    def _get_channel(self, channel_id: str, guild: disnake.Guild | None = None):
        clean_id = _id(channel_id)
        if not clean_id:
            return None
        channel = self.bot.get_channel(int(clean_id)) if self.bot else None
        if channel is None and guild is not None:
            channel = guild.get_channel(int(clean_id))
        return channel

    def _container_kwargs(self) -> dict:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary") if isinstance(colors, dict) else None
        if not primary_color_hex:
            return {}
        try:
            return {"accent_colour": disnake.Colour(int(primary_color_hex.replace("#", ""), 16))}
        except Exception:
            return {}

    def _pending_requests(self) -> list[tuple[str, dict]]:
        data = self.load()
        requests = data.get("whitelist") if isinstance(data.get("whitelist"), dict) else {}
        return [(user_id, req) for user_id, req in requests.items() if req.get("status") == "pending"]

    def _pending_faction_requests(self) -> list[tuple[str, dict]]:
        data = self.load()
        requests = data.get("faction_requests") if isinstance(data.get("faction_requests"), dict) else {}
        return [(user_id, req) for user_id, req in requests.items() if req.get("status") == "pending"]

    def _pending_recruitment_requests(self) -> list[tuple[str, dict]]:
        data = self.load()
        requests = data.get("recruitment_requests") if isinstance(data.get("recruitment_requests"), dict) else {}
        return [(req_id, req) for req_id, req in requests.items() if req.get("status") == "pending"]

    def _active_staff_sessions(self) -> dict:
        data = self.load()
        sessions = data.get("staff_sessions") if isinstance(data.get("staff_sessions"), dict) else {}
        return sessions

    def _is_staff(self, member) -> bool:
        if member is None:
            return False
        if str(getattr(member, "id", "")) == str(perms.get_owner_id()):
            return True
        permissions = getattr(member, "guild_permissions", None)
        if permissions and (permissions.manage_guild or permissions.administrator):
            return True
        cfg = self.load()
        role_id = str(cfg.get("staff_role_id") or "")
        if not role_id:
            return False
        return any(str(getattr(role, "id", "")) == role_id for role in getattr(member, "roles", []) or [])

    def record_event(self, data: dict, event_type: str, target: str, actor, details: dict | None = None) -> None:
        events = data.setdefault("audit_logs", [])
        if not isinstance(events, list):
            events = []
        events.append(
            {
                "type": str(event_type),
                "target": str(target or ""),
                "actor_id": str(getattr(actor, "id", actor) or ""),
                "actor_name": str(actor or ""),
                "details": details if isinstance(details, dict) else {},
                "created_at": _now(),
                "created_ts": _now_ts(),
            }
        )
        data["audit_logs"] = events[-500:]

    def _find_blacklist(self, data: dict, user_id: str | None = "", citizen_id: str | None = "") -> dict | None:
        lookup_user = str(user_id or "")
        lookup_citizen = str(citizen_id or "").strip().lower()
        for item in (data.get("blacklist") or {}).values():
            if not isinstance(item, dict) or not item.get("active", True):
                continue
            if lookup_user and str(item.get("user_id") or "") == lookup_user:
                return item
            if lookup_citizen and str(item.get("citizen_id") or "").strip().lower() == lookup_citizen:
                return item
        return None

    def _citizen_owner(self, data: dict, citizen_id: str, ignore_user_id: str | None = "") -> str:
        lookup = str(citizen_id or "").strip().lower()
        if not lookup:
            return ""
        for user_id, item in (data.get("linked_ids") or {}).items():
            if str(user_id) == str(ignore_user_id or ""):
                continue
            if str(item.get("citizen_id") or "").strip().lower() == lookup:
                return str(user_id)
        return ""

    def _blocked_text(self, entry: dict | None) -> str:
        reason = str((entry or {}).get("reason") or "Nao informado").strip()
        return f"{_emoji('wrong', 'wrong')} Acao bloqueada pela blacklist da cidade. Motivo: `{reason}`"

    async def _send_status_alerts(self, result: dict) -> None:
        if not result.get("ok"):
            return
        data = self.load()
        alerts = data.get("alerts") if isinstance(data.get("alerts"), dict) else {}
        if not alerts:
            return

        online = int(result.get("online") or 0)
        max_players = int(result.get("max") or 0)
        full_percent = int(alerts.get("server_full_percent") or 90)
        last_alerts = data.setdefault("last_alerts", {})
        now_ts = _now_ts()
        if max_players > 0 and online >= max_players * full_percent / 100:
            if now_ts - int(last_alerts.get("server_full") or 0) >= 900:
                last_alerts["server_full"] = now_ts
                self.save(data)
                await self.send_log(
                    f"{_emoji('warn', 'warn')} **Alerta FiveM: cidade quase cheia**\n"
                    f"Online: `{online}/{max_players}`\n"
                    f"Limite configurado: `{full_percent}%`"
                )

        pending_limit = int(alerts.get("pending_whitelist_limit") or 0)
        pending_count = len(self._pending_requests())
        if pending_limit and pending_count >= pending_limit:
            if now_ts - int(last_alerts.get("pending_whitelist") or 0) >= 900:
                last_alerts["pending_whitelist"] = now_ts
                self.save(data)
                await self.send_log(
                    f"{_emoji('receipt', 'receipt')} **Alerta FiveM: whitelist acumulando**\n"
                    f"Pendentes: `{pending_count}`\n"
                    f"Limite configurado: `{pending_limit}`"
                )

    async def _get_or_create_category(self, guild: disnake.Guild, name: str, reason: str):
        clean = str(name or "╺╸ FiveM")[:90]
        existing = disnake.utils.get(guild.categories, name=clean)
        if existing:
            return existing, False
        return await guild.create_category(clean, reason=reason), True

    async def _get_or_create_role(self, guild: disnake.Guild, role_id: str, name: str, reason: str):
        clean_id = _id(role_id)
        if clean_id:
            role = guild.get_role(int(clean_id))
            if role:
                return role, False
        clean_name = str(name or "FiveM")[:90]
        existing = disnake.utils.get(guild.roles, name=clean_name)
        if existing:
            return existing, False
        return await guild.create_role(name=clean_name, reason=reason), True

    def _private_overwrites(self, guild: disnake.Guild, *roles) -> dict:
        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(view_channel=False),
        }
        me = getattr(guild, "me", None)
        if me:
            overwrites[me] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        for role in roles:
            if role:
                overwrites[role] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        return overwrites

    async def _get_or_create_text_channel(
        self,
        guild: disnake.Guild,
        channel_id: str,
        name: str,
        category,
        reason: str,
        overwrites: dict | None = None,
    ):
        clean_id = _id(channel_id)
        if clean_id:
            channel = guild.get_channel(int(clean_id))
            if channel:
                return channel, False
        clean_name = str(name or "fivem")[:90]
        existing = disnake.utils.get(guild.text_channels, name=clean_name)
        if existing:
            return existing, False
        try:
            return await guild.create_text_channel(clean_name, category=category, overwrites=overwrites or {}, reason=reason), True
        except disnake.HTTPException:
            fallback_name = _slug(clean_name)
            existing = disnake.utils.get(guild.text_channels, name=fallback_name)
            if existing:
                return existing, False
            return await guild.create_text_channel(fallback_name, category=category, overwrites=overwrites or {}, reason=reason), True

    async def _create_faction_assets(self, inter: disnake.Interaction, data: dict, faction: dict) -> tuple[bool, bool]:
        guild = getattr(inter, "guild", None)
        if guild is None:
            return False, False
        setup = data.get("auto_setup") if isinstance(data.get("auto_setup"), dict) else {}
        separator = str(setup.get("separator") or "╺╸")
        reason = f"Estrutura fac FiveM - {_user(inter)}"
        category, _ = await self._get_or_create_category(guild, setup.get("category_name") or "╺╸ FiveM", reason)
        staff_role, _ = await self._get_or_create_role(guild, data.get("staff_role_id"), setup.get("staff_role_name") or "FiveM Staff", reason)

        created_role = False
        created_channel = False
        role_id = _id(faction.get("role_id"))
        role = guild.get_role(int(role_id)) if role_id else None
        if role is None:
            role, created_role = await self._get_or_create_role(guild, "", f"{separator} Fac {faction.get('name')}", reason)
            faction["role_id"] = str(role.id)

        channel_id = _id(faction.get("channel_id"))
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if channel is None:
            channel_name = f"{separator}-{_slug(faction.get('name'))}"
            channel, created_channel = await self._get_or_create_text_channel(
                guild,
                "",
                channel_name,
                category,
                reason,
                overwrites=self._private_overwrites(guild, staff_role, role),
            )
            faction["channel_id"] = str(channel.id)
        return created_role, created_channel

    async def create_fivem_structure(self, inter: disnake.MessageInteraction):
        if not self._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode criar a estrutura FiveM.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        guild = getattr(inter, "guild", None)
        if guild is None:
            await inter.followup.send(f"{_emoji('wrong', 'wrong')} Use este botao dentro de um servidor.", ephemeral=True)
            return

        me = getattr(guild, "me", None)
        permissions = getattr(me, "guild_permissions", None)
        if not permissions or not permissions.manage_channels or not permissions.manage_roles:
            await inter.followup.send(f"{_emoji('wrong', 'wrong')} Preciso de permissao para gerenciar canais e cargos.", ephemeral=True)
            return

        data = self.load()
        setup = data.get("auto_setup") if isinstance(data.get("auto_setup"), dict) else {}
        separator = str(setup.get("separator") or "╺╸")
        reason = f"Estrutura FiveM - {_user(inter)}"
        created_channels = []
        created_roles = []

        category, created = await self._get_or_create_category(guild, setup.get("category_name") or "╺╸ FiveM", reason)
        if created:
            created_channels.append(category)
        logs_category, created = await self._get_or_create_category(guild, setup.get("logs_category_name") or "╺╸ Logs FiveM", reason)
        if created:
            created_channels.append(logs_category)

        staff_role, created = await self._get_or_create_role(guild, data.get("staff_role_id"), setup.get("staff_role_name") or "FiveM Staff", reason)
        if created:
            created_roles.append(staff_role)
        whitelist_role, created = await self._get_or_create_role(guild, data.get("whitelist_role_id"), setup.get("whitelist_role_name") or "Cidadao", reason)
        if created:
            created_roles.append(whitelist_role)
        data["staff_role_id"] = str(staff_role.id)
        data["whitelist_role_id"] = str(whitelist_role.id)

        channel_specs = [
            ("panel_channel_id", f"{separator}-fivem-painel", category, {}),
            ("status_panel_channel_id", f"{separator}-status-city", category, {}),
            ("whitelist_channel_id", f"{separator}-whitelist", category, {}),
            ("factions_channel_id", f"{separator}-faccoes", category, {}),
            ("recruitment_channel_id", f"{separator}-recrutamento", category, {}),
            ("staff_point_channel_id", f"{separator}-bate-ponto", logs_category, self._private_overwrites(guild, staff_role)),
            ("staff_panel_channel_id", f"{separator}-staff-fivem", logs_category, self._private_overwrites(guild, staff_role)),
            ("log_channel_id", f"{separator}-logs-fivem", logs_category, self._private_overwrites(guild, staff_role)),
        ]
        for key, name, target_category, overwrites in channel_specs:
            channel, created = await self._get_or_create_text_channel(guild, data.get(key), name, target_category, reason, overwrites=overwrites)
            data[key] = str(channel.id)
            if created:
                created_channels.append(channel)

        data["last_structure_at"] = _now()
        self.record_event(
            data,
            "structure_created",
            str(guild.id),
            _user(inter),
            {"channels": len(created_channels), "roles": len(created_roles)},
        )
        self.save(data)
        await self.send_log(
            f"{_emoji('correct', 'correct')} **Estrutura FiveM criada/atualizada**\n"
            f"Staff: {_user(inter).mention}\n"
            f"Canais novos: `{len(created_channels)}`\n"
            f"Cargos novos: `{len(created_roles)}`"
        )
        await inter.followup.send(
            f"{_emoji('correct', 'correct')} Estrutura FiveM pronta: `{len(created_channels)}` canais/categorias e `{len(created_roles)}` cargos criados.",
            ephemeral=True,
        )

    def _admin_text(self) -> str:
        cfg = self.load()
        cache = cfg.get("cache", {})
        linked = cfg.get("linked_ids") if isinstance(cfg.get("linked_ids"), dict) else {}
        whitelist = cfg.get("whitelist") if isinstance(cfg.get("whitelist"), dict) else {}
        factions = cfg.get("factions") if isinstance(cfg.get("factions"), dict) else {}
        faction_requests = cfg.get("faction_requests") if isinstance(cfg.get("faction_requests"), dict) else {}
        recruitment_requests = cfg.get("recruitment_requests") if isinstance(cfg.get("recruitment_requests"), dict) else {}
        staff_sessions = cfg.get("staff_sessions") if isinstance(cfg.get("staff_sessions"), dict) else {}
        blacklist = cfg.get("blacklist") if isinstance(cfg.get("blacklist"), dict) else {}
        punishments = cfg.get("punishments") if isinstance(cfg.get("punishments"), list) else []
        pending = [req for req in whitelist.values() if req.get("status") == "pending"]
        approved = [req for req in whitelist.values() if req.get("status") == "approved"]
        pending_facs = [req for req in faction_requests.values() if req.get("status") == "pending"]
        pending_recruitment = [req for req in recruitment_requests.values() if req.get("status") == "pending"]
        active_blacklist = [item for item in blacklist.values() if isinstance(item, dict) and item.get("active", True)]
        server = _server_label(cfg.get("server_endpoint"))
        logs = f"<#{cfg.get('log_channel_id')}>" if cfg.get("log_channel_id") else "Nao definido"
        panel = f"<#{cfg.get('panel_channel_id')}>" if cfg.get("panel_channel_id") else "Canal atual"
        online = int(cache.get("online") or 0)
        max_players = int(cache.get("max") or 0)
        hostname = cache.get("hostname") or cfg.get("city_name") or "FiveM"

        return (
            f"# {_emoji('cloud', '☁️')} {cfg.get('panel_title') or 'PLANO FIVEM'}\n"
            f"-# Painel > Sistemas > **FiveM**\n\n"
            f"{_emoji('power', 'power')} **Status:** `{'Ativo' if cfg.get('enabled') else 'Desativado'}`\n"
            f"{_emoji('route', '🧭')} **Servidor:** `{server}`\n"
            f"{_emoji('members', 'members')} **Online:** `{online}/{max_players}` em `{hostname}`\n"
            f"{_emoji('link', 'link')} **IDs vinculados:** `{len(linked)}`\n"
            f"{_emoji('receipt', 'receipt')} **Whitelist:** `{len(approved)} aprovadas` | `{len(pending)} pendentes`\n"
            f"{_emoji('group', 'members')} **Facs:** `{len(factions)}` cadastradas | `{len(pending_facs)}` pendentes\n"
            f"{_emoji('clock', '🕒')} **Bate ponto:** `{len(staff_sessions)}` ativos | **Recrutamento:** `{len(pending_recruitment)}` pendentes\n"
            f"{_emoji('warn', 'warn')} **Seguranca:** `{len(active_blacklist)}` blacklist | `{len(punishments)}` punicoes\n"
            f"{_emoji('textc', '#')} **Painel:** {panel} | **Logs:** {logs}\n"
            f"{_emoji('clock', '🕒')} **Ultima consulta:** `{cfg.get('last_checked_at') or 'Nunca'}`"
        )

    def _admin_components(self) -> list:
        cfg = self.load()
        pending_count = len(self._pending_requests())
        faction_pending_count = len(self._pending_faction_requests())
        recruitment_pending_count = len(self._pending_recruitment_requests())
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(self._admin_text()),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    "**Operação de cidade eficiente e escalável**\n"
                    "Whitelist + painel, notificações, logs e acompanhamento do time em um só lugar."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Cidade", style=disnake.ButtonStyle.blurple, emoji=_emoji("wifi", "wifi"), custom_id="FiveM_AreaCity"),
                    disnake.ui.Button(label=f"Whitelist ({pending_count})", style=disnake.ButtonStyle.blurple, emoji=_emoji("verified", "verified"), custom_id="FiveM_WhitelistQueue"),
                    disnake.ui.Button(label=f"Faccoes ({faction_pending_count})", style=disnake.ButtonStyle.blurple, emoji=_emoji("group", "members"), custom_id="FiveM_FactionsAdmin"),
                    disnake.ui.Button(label="Staff/Ponto", style=disnake.ButtonStyle.grey, emoji=_emoji("staff", "staff"), custom_id="FiveM_AreaStaff"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label=f"Recrutamento ({recruitment_pending_count})", style=disnake.ButtonStyle.blurple, emoji=_emoji("receipt", "receipt"), custom_id="FiveM_RecruitmentAdmin"),
                    disnake.ui.Button(label="Seguranca", style=disnake.ButtonStyle.red, emoji=_emoji("shield", "warn"), custom_id="FiveM_SecurityAdmin"),
                    disnake.ui.Button(label="Automacoes", style=disnake.ButtonStyle.green, emoji=_emoji("reload", "reload"), custom_id="FiveM_AreaAutomation"),
                    disnake.ui.Button(label="Relatorios", style=disnake.ButtonStyle.grey, emoji=_emoji("stock", "receipt"), custom_id="FiveM_Reports"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Desativar" if cfg.get("enabled") else "Ativar",
                        style=disnake.ButtonStyle.red if cfg.get("enabled") else disnake.ButtonStyle.green,
                        emoji=_emoji("off", "off") if cfg.get("enabled") else _emoji("on", "on"),
                        custom_id="FiveM_Toggle",
                    ),
                    disnake.ui.Button(label="Historico", style=disnake.ButtonStyle.grey, emoji=_emoji("search", "receipt"), custom_id="FiveM_ProfileLookup"),
                ),
                **self._container_kwargs(),
            ),
        ]

    def display_fivem_panel(self, inter: disnake.MessageInteraction):
        return self._admin_components()

    def _city_area_components(self) -> list:
        cfg = self.load()
        cache = cfg.get("cache", {})
        online = int(cache.get("online") or 0)
        max_players = int(cache.get("max") or 0)
        status_channel = f"<#{cfg.get('status_panel_channel_id')}>" if cfg.get("status_panel_channel_id") else "`Nao definido`"
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('wifi', 'wifi')} Cidade & Status\n\n"
                    f"**Servidor:** `{_server_label(cfg.get('server_endpoint'))}`\n"
                    f"**Online:** `{online}/{max_players}`\n"
                    f"**Painel status:** {status_channel}\n"
                    f"**Ultima consulta:** `{cfg.get('last_checked_at') or 'Nunca'}`"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Vincular Servidor", style=disnake.ButtonStyle.grey, emoji=_emoji("link", "link"), custom_id="FiveM_ConfigServer"),
                    disnake.ui.Button(label="Textos e Cargos", style=disnake.ButtonStyle.grey, emoji=_emoji("edit", "edit"), custom_id="FiveM_ConfigText"),
                    disnake.ui.Button(label="Atualizar Online", style=disnake.ButtonStyle.grey, emoji=_emoji("reload", "reload"), custom_id="FiveM_RefreshOnline"),
                ),
                **self._container_kwargs(),
            )
        ]

    def _automation_area_components(self) -> list:
        cfg = self.load()
        panel_channel = f"<#{cfg.get('panel_channel_id')}>" if cfg.get("panel_channel_id") else "`Nao definido`"
        status_channel = f"<#{cfg.get('status_panel_channel_id')}>" if cfg.get("status_panel_channel_id") else "`Nao definido`"
        staff_channel_id = cfg.get("staff_panel_channel_id") or cfg.get("staff_point_channel_id")
        staff_channel = f"<#{staff_channel_id}>" if staff_channel_id else "`Nao definido`"
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('reload', 'reload')} Automacoes FiveM\n\n"
                    f"**Painel principal:** {panel_channel}\n"
                    f"**Status publico:** {status_channel}\n"
                    f"**Painel staff:** {staff_channel}\n\n"
                    "O status da city e o painel de staff sao atualizados automaticamente a cada 10 minutos."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Canais dos Paineis", style=disnake.ButtonStyle.grey, emoji=_emoji("textc", "textc"), custom_id="FiveM_ConfigPublicPanels"),
                    disnake.ui.Button(label="Criar Estrutura", style=disnake.ButtonStyle.green, emoji=_emoji("plus", "plus"), custom_id="FiveM_CreateStructure"),
                    disnake.ui.Button(label="Alertas", style=disnake.ButtonStyle.grey, emoji=_emoji("warn", "warn"), custom_id="FiveM_Alerts"),
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Publicar Principal", style=disnake.ButtonStyle.green, emoji=_emoji("announcement", "announcement"), custom_id="FiveM_Publish"),
                    disnake.ui.Button(label="Publicar Status", style=disnake.ButtonStyle.green, emoji=_emoji("wifi", "wifi"), custom_id="FiveM_PublishStatus"),
                    disnake.ui.Button(label="Publicar Staff", style=disnake.ButtonStyle.green, emoji=_emoji("staff", "staff"), custom_id="FiveM_PublishStaff"),
                ),
                **self._container_kwargs(),
            )
        ]

    def _staff_area_components(self) -> list:
        data = self.load()
        sessions = data.get("staff_sessions") if isinstance(data.get("staff_sessions"), dict) else {}
        records = data.get("staff_time_records") if isinstance(data.get("staff_time_records"), list) else []
        now = _now_ts()
        active_lines = []
        for user_id, session in list(sessions.items())[:12]:
            started_ts = int(session.get("started_ts") or now)
            active_lines.append(f"- <@{user_id}> desde <t:{started_ts}:t> (`{_duration_text(now - started_ts)}`)")
        history_lines = []
        for record in list(records)[-6:][::-1]:
            status = "cancelado" if record.get("cancelled") else "finalizado"
            history_lines.append(f"- <@{record.get('user_id')}> `{_duration_text(record.get('duration_seconds', 0))}` | {status}")

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('staff', 'staff')} Staff & Bate Ponto\n\n"
                    f"**Pontos ativos:** `{len(sessions)}`\n"
                    f"{chr(10).join(active_lines) if active_lines else 'Nenhum ponto ativo.'}\n\n"
                    f"**Ultimos registros:**\n"
                    f"{chr(10).join(history_lines) if history_lines else 'Nenhum registro encerrado.'}"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Publicar Painel Staff", style=disnake.ButtonStyle.green, emoji=_emoji("announcement", "announcement"), custom_id="FiveM_PublishStaff"),
                    disnake.ui.Button(label="Canais dos Paineis", style=disnake.ButtonStyle.grey, emoji=_emoji("textc", "textc"), custom_id="FiveM_ConfigPublicPanels"),
                    disnake.ui.Button(label="Ver Pendencias", style=disnake.ButtonStyle.blurple, emoji=_emoji("receipt", "receipt"), custom_id="FiveM_StaffQuickQueues"),
                ),
                **self._container_kwargs(),
            )
        ]

    def _public_components(self) -> list:
        cfg = self.load()
        cache = cfg.get("cache", {})
        online = int(cache.get("online") or 0)
        max_players = int(cache.get("max") or 0)
        title = cfg.get("panel_title") or "PLANO FIVEM - SYSTEM PRO"
        description = cfg.get("panel_description") or _default_data()["panel_description"]
        status = f"`{online}/{max_players}` jogadores online" if cfg.get("server_endpoint") else "`Servidor nao vinculado`"

        buttons = [
            disnake.ui.Button(label="Online", style=disnake.ButtonStyle.grey, emoji=_emoji("members", "members"), custom_id="FiveM_PublicOnline"),
            disnake.ui.Button(label="Vincular ID", style=disnake.ButtonStyle.grey, emoji=_emoji("link", "link"), custom_id="FiveM_LinkID"),
            disnake.ui.Button(label="Whitelist", style=disnake.ButtonStyle.green, emoji=_emoji("verified", "verified"), custom_id="FiveM_RequestWhitelist"),
            disnake.ui.Button(label="Faccoes", style=disnake.ButtonStyle.blurple, emoji=_emoji("group", "members"), custom_id="FiveM_Factions"),
            disnake.ui.Button(label="Minha Liberação", style=disnake.ButtonStyle.blurple, emoji=_emoji("receipt", "receipt"), custom_id="FiveM_MyRelease"),
            disnake.ui.Button(label="Meu Perfil", style=disnake.ButtonStyle.grey, emoji=_emoji("member", "members"), custom_id="FiveM_MyProfile"),
            disnake.ui.Button(label="Recrutamento", style=disnake.ButtonStyle.grey, emoji=_emoji("form", "receipt"), custom_id="FiveM_Recruitment"),
            disnake.ui.Button(label="Iniciar Ponto", style=disnake.ButtonStyle.green, emoji=_emoji("clock", "clock"), custom_id="FiveM_TimeStart"),
            disnake.ui.Button(label="Encerrar Ponto", style=disnake.ButtonStyle.red, emoji=_emoji("off", "off"), custom_id="FiveM_TimeStop"),
            disnake.ui.Button(label="Cancelar Ponto", style=disnake.ButtonStyle.grey, emoji=_emoji("wrong", "wrong"), custom_id="FiveM_TimeCancel"),
        ]
        join_url = _url(cfg.get("join_url"))
        if join_url.startswith("http://") or join_url.startswith("https://"):
            buttons.append(disnake.ui.Button(label="Entrar", style=disnake.ButtonStyle.url, emoji=_emoji("play", "play"), url=join_url))

        rows = [disnake.ui.ActionRow(*buttons[index:index + 5]) for index in range(0, len(buttons), 5)]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('cloud', '☁️')} {title}\n\n"
                    f"{description}\n\n"
                    f"{_emoji('wifi', '📡')} **Status da cidade:** {status}"
                ),
                **self._container_kwargs(),
            ),
            *rows,
        ]

    def _status_panel_components(self) -> list:
        cfg = self.load()
        cache = cfg.get("cache", {})
        online = int(cache.get("online") or 0)
        max_players = int(cache.get("max") or 0)
        hostname = cache.get("hostname") or cfg.get("city_name") or "FiveM"
        players = cache.get("players") if isinstance(cache.get("players"), list) else []
        error = str(cache.get("error") or "").strip()
        last_checked = cfg.get("last_checked_at") or "Nunca"
        status_line = f"`{online}/{max_players}` jogadores online" if cfg.get("server_endpoint") else "`Servidor nao vinculado`"
        if error:
            status_line = f"`Indisponivel` - {error[:120]}"

        sample = "\n".join(f"- `{item.get('id')}` {item.get('name')}" for item in players[:12])
        if not sample:
            sample = "Nenhum jogador listado agora."

        rows = []
        join_url = _url(cfg.get("join_url"))
        if join_url.startswith("http://") or join_url.startswith("https://"):
            rows.append(
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Entrar na City", style=disnake.ButtonStyle.url, emoji=_emoji("play", "play"), url=join_url),
                    disnake.ui.Button(label="Atualizar Agora", style=disnake.ButtonStyle.grey, emoji=_emoji("reload", "reload"), custom_id="FiveM_PublicOnline"),
                )
            )
        else:
            rows.append(
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Atualizar Agora", style=disnake.ButtonStyle.grey, emoji=_emoji("reload", "reload"), custom_id="FiveM_PublicOnline"),
                )
            )

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('wifi', 'wifi')} Status da Cidade\n"
                    f"-# Atualizacao automatica a cada 10 minutos\n\n"
                    f"**Cidade:** `{hostname}`\n"
                    f"**Online:** {status_line}\n"
                    f"**Ultima consulta:** `{last_checked}`\n\n"
                    f"**Jogadores recentes:**\n{sample}"
                ),
                **self._container_kwargs(),
            ),
            *rows,
        ]

    def _staff_public_components(self) -> list:
        data = self.load()
        sessions = data.get("staff_sessions") if isinstance(data.get("staff_sessions"), dict) else {}
        records = data.get("staff_time_records") if isinstance(data.get("staff_time_records"), list) else []
        pending_whitelist = len(self._pending_requests())
        pending_factions = len(self._pending_faction_requests())
        pending_recruitment = len(self._pending_recruitment_requests())
        now = _now_ts()

        active_lines = []
        for user_id, session in list(sessions.items())[:8]:
            started_ts = int(session.get("started_ts") or now)
            active_lines.append(f"- <@{user_id}> `{_duration_text(now - started_ts)}`")
        active_text = "\n".join(active_lines) if active_lines else "Nenhuma staff em ponto agora."

        recent_lines = []
        for record in list(records)[-5:][::-1]:
            status = "cancelado" if record.get("cancelled") else "finalizado"
            recent_lines.append(f"- <@{record.get('user_id')}> `{_duration_text(record.get('duration_seconds', 0))}` | {status}")
        recent_text = "\n".join(recent_lines) if recent_lines else "Sem registros recentes."

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('staff', 'staff')} Painel da Staff FiveM\n"
                    f"-# Operacao diaria sem precisar abrir /painel\n\n"
                    f"**Pontos ativos:** `{len(sessions)}`\n{active_text}\n\n"
                    f"**Pendencias:** Whitelist `{pending_whitelist}` | Faccoes `{pending_factions}` | Recrutamento `{pending_recruitment}`\n\n"
                    f"**Ultimos pontos:**\n{recent_text}"
                ),
                **self._container_kwargs(),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Iniciar Ponto", style=disnake.ButtonStyle.green, emoji=_emoji("clock", "clock"), custom_id="FiveM_TimeStart"),
                disnake.ui.Button(label="Encerrar Ponto", style=disnake.ButtonStyle.red, emoji=_emoji("off", "off"), custom_id="FiveM_TimeStop"),
                disnake.ui.Button(label="Cancelar Ponto", style=disnake.ButtonStyle.grey, emoji=_emoji("wrong", "wrong"), custom_id="FiveM_TimeCancel"),
                disnake.ui.Button(label="Meu Perfil", style=disnake.ButtonStyle.grey, emoji=_emoji("member", "members"), custom_id="FiveM_MyProfile"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Ver Pendencias", style=disnake.ButtonStyle.blurple, emoji=_emoji("receipt", "receipt"), custom_id="FiveM_StaffQuickQueues"),
                disnake.ui.Button(label="Status da City", style=disnake.ButtonStyle.grey, emoji=_emoji("wifi", "wifi"), custom_id="FiveM_PublicOnline"),
            ),
        ]

    def _queue_components(self) -> list:
        pending = self._pending_requests()
        if not pending:
            body = f"# {_emoji('verified', 'correct')} Liberação FiveM\n\nNenhuma whitelist pendente no momento."
            rows = []
        else:
            lines = []
            options = []
            for user_id, req in pending[:25]:
                name = req.get("character_name") or req.get("discord_name") or user_id
                citizen_id = req.get("citizen_id") or "sem-id"
                lines.append(f"- <@{user_id}> | `{citizen_id}` | **{name}**")
                options.append(
                    disnake.SelectOption(
                        label=name[:100],
                        value=user_id,
                        description=f"ID: {citizen_id}"[:100],
                        emoji=_emoji("receipt", "receipt"),
                    )
                )
            body = f"# {_emoji('verified', 'correct')} Liberação FiveM\n\n" + "\n".join(lines[:15])
            rows = [
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="FiveM_WhitelistSelect",
                        placeholder="Selecione uma solicitação para analisar",
                        options=options,
                    )
                )
            ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(body),
                *rows,
                **self._container_kwargs(),
            ),
        ]

    def _factions_admin_components(self) -> list:
        data = self.load()
        factions = data.get("factions") if isinstance(data.get("factions"), dict) else {}
        pending = self._pending_faction_requests()
        if factions:
            lines = []
            for fac in list(factions.values())[:15]:
                role = f"<@&{fac.get('role_id')}>" if fac.get("role_id") else "sem cargo"
                channel = f"<#{fac.get('channel_id')}>" if fac.get("channel_id") else "sem canal"
                lines.append(f"- **{fac.get('name')}** | {role} | {channel}")
            body = "\n".join(lines)
        else:
            body = "Nenhuma fac cadastrada."

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('group', 'members')} Faccoes FiveM\n\n"
                    f"**Facs cadastradas:** `{len(factions)}`\n"
                    f"**Solicitacoes pendentes:** `{len(pending)}`\n\n{body}"
                ),
                **self._container_kwargs(),
            )
        ]

    def _faction_requests_components(self) -> list:
        pending = self._pending_faction_requests()
        if not pending:
            body = f"# {_emoji('group', 'members')} Solicitacoes de Fac\n\nNenhuma solicitacao pendente."
            rows = []
        else:
            lines = []
            options = []
            for user_id, req in pending[:25]:
                fac_name = req.get("faction_name") or req.get("faction_id") or "Fac"
                char_name = req.get("character_name") or req.get("discord_name") or user_id
                lines.append(f"- <@{user_id}> | **{fac_name}** | `{char_name}`")
                options.append(
                    disnake.SelectOption(
                        label=f"{fac_name} - {char_name}"[:100],
                        value=user_id,
                        description=f"ID: {req.get('citizen_id') or 'N/A'}"[:100],
                        emoji=_emoji("receipt", "receipt"),
                    )
                )
            body = f"# {_emoji('group', 'members')} Solicitacoes de Fac\n\n" + "\n".join(lines[:15])
            rows = [
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="FiveM_FactionRequestSelect",
                        placeholder="Selecione uma solicitacao de fac",
                        options=options,
                    )
                )
            ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(body),
                *rows,
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=_emoji("back", "back"), custom_id="FiveM_FactionsAdmin")
                ),
                **self._container_kwargs(),
            )
        ]

    def _recruitment_admin_components(self) -> list:
        pending = self._pending_recruitment_requests()
        if not pending:
            body = f"# {_emoji('receipt', 'receipt')} Recrutamento FiveM\n\nNenhum formulario pendente."
            rows = []
        else:
            lines = []
            options = []
            for req_id, req in pending[:25]:
                area = req.get("area") or "Area"
                citizen_id = req.get("citizen_id") or "sem-id"
                user_id = req.get("user_id") or "0"
                lines.append(f"- <@{user_id}> | **{area}** | `{citizen_id}`")
                options.append(
                    disnake.SelectOption(
                        label=f"{area} - {citizen_id}"[:100],
                        value=req_id[:100],
                        description=f"Usuario: {req.get('discord_name') or user_id}"[:100],
                        emoji=_emoji("receipt", "receipt"),
                    )
                )
            body = f"# {_emoji('receipt', 'receipt')} Recrutamento FiveM\n\n" + "\n".join(lines[:15])
            rows = [
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="FiveM_RecruitmentSelect",
                        placeholder="Selecione um formulario para analisar",
                        options=options,
                    )
                )
            ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(body),
                *rows,
                **self._container_kwargs(),
            )
        ]

    def _staff_time_components(self) -> list:
        data = self.load()
        sessions = data.get("staff_sessions") if isinstance(data.get("staff_sessions"), dict) else {}
        records = data.get("staff_time_records") if isinstance(data.get("staff_time_records"), list) else []
        now = _now_ts()
        if sessions:
            active_lines = []
            for user_id, session in list(sessions.items())[:15]:
                started_ts = int(session.get("started_ts") or now)
                active_lines.append(f"- <@{user_id}> desde <t:{started_ts}:t> (`{_duration_text(now - started_ts)}`)")
            active_text = "\n".join(active_lines)
        else:
            active_text = "Nenhum ponto ativo."

        if records:
            history_lines = []
            for record in list(records)[-5:][::-1]:
                status = "cancelado" if record.get("cancelled") else "finalizado"
                history_lines.append(
                    f"- <@{record.get('user_id')}> `{_duration_text(record.get('duration_seconds', 0))}` | {status}"
                )
            history_text = "\n".join(history_lines)
        else:
            history_text = "Nenhum registro encerrado."

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('clock', 'clock')} Bate ponto staff FiveM\n\n"
                    f"**Ativos:** `{len(sessions)}`\n{active_text}\n\n"
                    f"**Ultimos registros:**\n{history_text}"
                ),
                **self._container_kwargs(),
            )
        ]

    def _security_components(self) -> list:
        data = self.load()
        blacklist = data.get("blacklist") if isinstance(data.get("blacklist"), dict) else {}
        punishments = data.get("punishments") if isinstance(data.get("punishments"), list) else []
        active = [item for item in blacklist.values() if isinstance(item, dict) and item.get("active", True)]

        blacklist_lines = []
        for item in active[-8:][::-1]:
            target = f"<@{item.get('user_id')}>" if item.get("user_id") else "`sem Discord`"
            blacklist_lines.append(f"- {target} | ID `{item.get('citizen_id') or 'N/A'}` | {item.get('reason') or 'Sem motivo'}")
        punishment_lines = []
        for item in punishments[-6:][::-1]:
            target = f"<@{item.get('user_id')}>" if item.get("user_id") else "`sem Discord`"
            punishment_lines.append(f"- {target} | `{item.get('kind')}` | ID `{item.get('citizen_id') or 'N/A'}`")

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('warn', 'warn')} Segurança FiveM\n\n"
                    f"**Blacklist ativa:** `{len(active)}`\n"
                    f"{chr(10).join(blacklist_lines) if blacklist_lines else 'Nenhuma blacklist ativa.'}\n\n"
                    f"**Ultimas punicoes:** `{len(punishments)}` registradas\n"
                    f"{chr(10).join(punishment_lines) if punishment_lines else 'Nenhuma punicao registrada.'}"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Adicionar Blacklist", style=disnake.ButtonStyle.red, emoji=_emoji("warn", "warn"), custom_id="FiveM_BlacklistAdd"),
                    disnake.ui.Button(label="Remover Blacklist", style=disnake.ButtonStyle.grey, emoji=_emoji("correct", "correct"), custom_id="FiveM_BlacklistRemove"),
                    disnake.ui.Button(label="Registrar Punicao", style=disnake.ButtonStyle.blurple, emoji=_emoji("receipt", "receipt"), custom_id="FiveM_PunishmentAdd"),
                ),
                **self._container_kwargs(),
            )
        ]

    def _reports_components(self) -> list:
        data = self.load()
        whitelist = data.get("whitelist") if isinstance(data.get("whitelist"), dict) else {}
        faction_requests = data.get("faction_requests") if isinstance(data.get("faction_requests"), dict) else {}
        recruitment = data.get("recruitment_requests") if isinstance(data.get("recruitment_requests"), dict) else {}
        records = data.get("staff_time_records") if isinstance(data.get("staff_time_records"), list) else []
        events = data.get("audit_logs") if isinstance(data.get("audit_logs"), list) else []
        now = _now_ts()
        seven_days = now - (7 * 24 * 60 * 60)
        recent_records = [rec for rec in records if int(rec.get("ended_ts") or 0) >= seven_days]
        total_seconds = sum(int(rec.get("duration_seconds") or 0) for rec in recent_records if not rec.get("cancelled"))
        top_staff = {}
        for rec in recent_records:
            if rec.get("cancelled"):
                continue
            top_staff[str(rec.get("user_id"))] = top_staff.get(str(rec.get("user_id")), 0) + int(rec.get("duration_seconds") or 0)
        top_lines = [
            f"- <@{user_id}> `{_duration_text(seconds)}`"
            for user_id, seconds in sorted(top_staff.items(), key=lambda item: item[1], reverse=True)[:5]
        ]
        event_lines = [
            f"- `{item.get('type')}` | alvo `{item.get('target') or 'N/A'}` | <t:{int(item.get('created_ts') or now)}:R>"
            for item in events[-5:][::-1]
        ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('stock', 'receipt')} Relatorios FiveM\n\n"
                    f"**Whitelist:** `{sum(1 for item in whitelist.values() if item.get('status') == 'approved')}` aprovadas | "
                    f"`{sum(1 for item in whitelist.values() if item.get('status') == 'pending')}` pendentes | "
                    f"`{sum(1 for item in whitelist.values() if item.get('status') == 'rejected')}` rejeitadas\n"
                    f"**Faccoes:** `{len(data.get('factions') or {})}` cadastradas | "
                    f"`{sum(1 for item in faction_requests.values() if item.get('status') == 'pending')}` solicitacoes pendentes\n"
                    f"**Recrutamento:** `{sum(1 for item in recruitment.values() if item.get('status') == 'pending')}` pendentes\n"
                    f"**Bate ponto 7 dias:** `{_duration_text(total_seconds)}` registrados\n\n"
                    f"**Top staff 7 dias:**\n{chr(10).join(top_lines) if top_lines else 'Sem registros nos ultimos 7 dias.'}\n\n"
                    f"**Ultimos eventos:**\n{chr(10).join(event_lines) if event_lines else 'Sem eventos registrados.'}"
                ),
                **self._container_kwargs(),
            )
        ]

    async def show_citizen_profile(self, inter: disnake.Interaction, target: str | None = None):
        user = _user(inter)
        data = self.load()
        target_raw = str(target or "").strip()
        target_id = _id(target_raw) or (str(user.id) if not target_raw else "")
        citizen_lookup = "" if target_id else target_raw.lower()

        linked_user_id = target_id
        linked = (data.get("linked_ids") or {}).get(linked_user_id) if linked_user_id else None
        if not linked and citizen_lookup:
            for user_id, item in (data.get("linked_ids") or {}).items():
                if str(item.get("citizen_id") or "").strip().lower() == citizen_lookup:
                    linked_user_id = str(user_id)
                    linked = item
                    break

        whitelist = (data.get("whitelist") or {}).get(linked_user_id) if linked_user_id else None
        if not linked and whitelist:
            linked = {
                "citizen_id": whitelist.get("citizen_id"),
                "character_name": whitelist.get("character_name"),
                "discord_name": whitelist.get("discord_name"),
            }

        citizen_id = str((linked or {}).get("citizen_id") or citizen_lookup or "").strip()
        blacklist = self._find_blacklist(data, user_id=linked_user_id, citizen_id=citizen_id)
        punishments = [
            item for item in (data.get("punishments") or [])
            if isinstance(item, dict)
            and (
                (linked_user_id and str(item.get("user_id") or "") == linked_user_id)
                or (citizen_id and str(item.get("citizen_id") or "").strip().lower() == citizen_id.lower())
            )
        ]
        faction_requests = [
            item for uid, item in (data.get("faction_requests") or {}).items()
            if str(uid) == str(linked_user_id)
        ]
        recruitment = [
            item for item in (data.get("recruitment_requests") or {}).values()
            if str(item.get("user_id") or "") == str(linked_user_id)
        ]
        records = [
            item for item in (data.get("staff_time_records") or [])
            if str(item.get("user_id") or "") == str(linked_user_id)
        ]

        if not linked and not whitelist and not punishments and not blacklist and not faction_requests and not recruitment:
            await inter.response.send_message(f"{_emoji('warn', 'warn')} Nao encontrei historico para `{target_raw or user.id}`.", ephemeral=True)
            return

        status_map = {"pending": "Pendente", "approved": "Aprovada", "rejected": "Rejeitada"}
        punishment_lines = [
            f"- `{item.get('kind')}` | {item.get('reason') or 'Sem motivo'}"
            for item in punishments[-5:][::-1]
        ]
        faction_lines = [
            f"- `{item.get('faction_name') or item.get('faction_id')}` | `{status_map.get(item.get('status'), item.get('status'))}`"
            for item in faction_requests[-5:]
        ]

        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {_emoji('member', 'members')} Historico FiveM\n\n"
                    f"**Usuario:** {f'<@{linked_user_id}>' if linked_user_id else '`Nao vinculado`'}\n"
                    f"**ID/Passaporte:** `{citizen_id or 'Nao vinculado'}`\n"
                    f"**Personagem:** `{(linked or {}).get('character_name') or 'N/A'}`\n"
                    f"**Whitelist:** `{status_map.get((whitelist or {}).get('status'), (whitelist or {}).get('status') or 'Nao solicitada')}`\n"
                    f"**Blacklist:** `{'ativa' if blacklist else 'limpo'}`\n"
                    f"**Punicoes:** `{len(punishments)}`\n"
                    f"**Pontos staff:** `{len(records)}` registros\n\n"
                    f"**Faccoes:**\n{chr(10).join(faction_lines) if faction_lines else 'Sem solicitacoes de fac.'}\n\n"
                    f"**Ultimas punicoes:**\n{chr(10).join(punishment_lines) if punishment_lines else 'Sem punicoes.'}\n\n"
                    f"**Recrutamento:** `{len(recruitment)}` formulario(s)"
                ),
                **self._container_kwargs(),
            )
        ]
        await inter.response.send_message(components=components, flags=disnake.MessageFlags(is_components_v2=True), ephemeral=True)

    async def fetch_server_status(self) -> dict:
        cfg = self.load()
        endpoint = str(cfg.get("server_endpoint") or "").strip()
        if not endpoint:
            return {"ok": False, "message": "Servidor FiveM nao vinculado."}

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if endpoint.startswith("http://") or endpoint.startswith("https://"):
                    parsed = urlparse(endpoint)
                    if "servers-frontend.fivem.net" in parsed.netloc:
                        async with session.get(endpoint) as response:
                            payload = await response.json()
                            return self._save_cfx_status(payload)
                    base = endpoint.rstrip("/")
                    async with session.get(f"{base}/players.json") as players_response:
                        players = await players_response.json()
                    hostname = ""
                    max_players = 0
                    try:
                        async with session.get(f"{base}/info.json") as info_response:
                            info = await info_response.json()
                            hostname = info.get("vars", {}).get("sv_projectName") or info.get("vars", {}).get("sv_hostname") or info.get("hostname") or ""
                            max_players = int(info.get("vars", {}).get("sv_maxClients") or 0)
                    except Exception:
                        pass
                    return self._save_direct_status(players, hostname, max_players)

                code = endpoint.split("/")[-1]
                async with session.get(f"https://servers-frontend.fivem.net/api/servers/single/{code}") as response:
                    payload = await response.json()
                    return self._save_cfx_status(payload)
        except Exception as exc:
            data = self.load()
            data["cache"]["error"] = str(exc)
            data["last_checked_at"] = _now()
            self.save(data)
            alerts = data.get("alerts") if isinstance(data.get("alerts"), dict) else {}
            last_alerts = data.setdefault("last_alerts", {})
            now_ts = _now_ts()
            if alerts.get("server_down", True) and now_ts - int(last_alerts.get("server_down") or 0) >= 900:
                last_alerts["server_down"] = now_ts
                self.save(data)
                await self.send_log(
                    f"{_emoji('warn', 'warn')} **Alerta FiveM: servidor offline/indisponivel**\n"
                    f"Servidor: `{endpoint}`\n"
                    f"Erro: `{exc}`"
                )
            return {"ok": False, "message": f"Falha ao consultar servidor: {exc}"}

    def _save_direct_status(self, players: list, hostname: str, max_players: int) -> dict:
        players = players if isinstance(players, list) else []
        clean_players = [
            {"id": item.get("id"), "name": str(item.get("name") or "Sem nome")[:80], "ping": item.get("ping")}
            for item in players[:80]
            if isinstance(item, dict)
        ]
        data = self.load()
        data["cache"] = {
            "online": len(clean_players),
            "max": max_players or len(clean_players),
            "hostname": hostname or data.get("city_name") or "FiveM",
            "players": clean_players,
            "error": "",
        }
        data["last_checked_at"] = _now()
        self.save(data)
        return {"ok": True, **data["cache"]}

    def _save_cfx_status(self, payload: dict) -> dict:
        server = payload.get("Data") if isinstance(payload, dict) else {}
        players = server.get("players") if isinstance(server, dict) else []
        vars_data = server.get("vars") if isinstance(server, dict) else {}
        hostname = server.get("hostname") or vars_data.get("sv_projectName") or vars_data.get("sv_hostname") or ""
        max_players = int(server.get("svMaxclients") or vars_data.get("sv_maxClients") or 0)
        return self._save_direct_status(players if isinstance(players, list) else [], hostname, max_players)

    async def send_log(self, text: str):
        cfg = self.load()
        channel_id = _id(cfg.get("log_channel_id"))
        if not channel_id or not self.bot:
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
            await inter.response.send_message(f"{_emoji('warn', 'warn')} O sistema FiveM esta desativado.", ephemeral=True)
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
        self.update({"last_published_at": _now(), "panel_message_id": str(sent.id), "panel_channel_id": str(channel.id)})
        await inter.followup.send(f"{_emoji('correct', 'correct')} Painel FiveM publicado em {channel.mention}.", ephemeral=True)

    async def publish_status_panel(self, inter: disnake.MessageInteraction):
        cfg = self.load()
        if not cfg.get("enabled"):
            await inter.response.send_message(f"{_emoji('warn', 'warn')} O sistema FiveM esta desativado.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        await self.fetch_server_status()
        channel = self._get_channel(cfg.get("status_panel_channel_id"), getattr(inter, "guild", None))
        channel = channel or self._get_channel(cfg.get("panel_channel_id"), getattr(inter, "guild", None))
        channel = channel or getattr(inter, "channel", None)
        if channel is None:
            await inter.followup.send(f"{_emoji('wrong', 'wrong')} Canal do painel de status nao encontrado.", ephemeral=True)
            return

        sent = await channel.send(components=self._status_panel_components(), flags=disnake.MessageFlags(is_components_v2=True))
        self.update(
            {
                "status_panel_channel_id": str(channel.id),
                "status_panel_message_id": str(sent.id),
                "last_status_panel_update": _now(),
            }
        )
        await inter.followup.send(
            f"{_emoji('correct', 'correct')} Painel publico de status publicado em {channel.mention}. Ele vai atualizar a cada 10 minutos.",
            ephemeral=True,
        )

    async def publish_staff_panel(self, inter: disnake.MessageInteraction):
        cfg = self.load()
        if not cfg.get("enabled"):
            await inter.response.send_message(f"{_emoji('warn', 'warn')} O sistema FiveM esta desativado.", ephemeral=True)
            return
        if not self._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode publicar o painel da staff.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        channel = self._get_channel(cfg.get("staff_panel_channel_id") or cfg.get("staff_point_channel_id"), getattr(inter, "guild", None))
        channel = channel or getattr(inter, "channel", None)
        if channel is None:
            await inter.followup.send(f"{_emoji('wrong', 'wrong')} Canal do painel da staff nao encontrado.", ephemeral=True)
            return

        sent = await channel.send(components=self._staff_public_components(), flags=disnake.MessageFlags(is_components_v2=True))
        self.update(
            {
                "staff_panel_channel_id": str(channel.id),
                "staff_panel_message_id": str(sent.id),
                "last_staff_panel_update": _now(),
            }
        )
        await inter.followup.send(
            f"{_emoji('correct', 'correct')} Painel da staff publicado em {channel.mention}. Ele vai atualizar a cada 10 minutos.",
            ephemeral=True,
        )

    async def refresh_published_panels(self):
        data = self.load()
        if not data.get("enabled"):
            return

        if data.get("server_endpoint"):
            result = await self.fetch_server_status()
            if result.get("ok"):
                await self._send_status_alerts(result)

        data = self.load()
        updates = {}
        panel_specs = [
            ("status_panel_channel_id", "status_panel_message_id", self._status_panel_components, "last_status_panel_update"),
            ("staff_panel_channel_id", "staff_panel_message_id", self._staff_public_components, "last_staff_panel_update"),
            ("panel_channel_id", "panel_message_id", self._public_components, "last_published_update"),
        ]
        for channel_key, message_key, builder, stamp_key in panel_specs:
            channel_id = _id(data.get(channel_key))
            message_id = _id(data.get(message_key))
            if not channel_id or not message_id:
                continue
            channel = self._get_channel(channel_id)
            if channel is None:
                continue
            try:
                msg = await channel.fetch_message(int(message_id))
                await msg.edit(components=builder())
                updates[stamp_key] = _now()
            except disnake.NotFound:
                updates[message_key] = ""
            except Exception:
                continue
        if updates:
            self.update(updates)

    @tasks.loop(minutes=10)
    async def fivem_public_panels_loop(self):
        try:
            await self.refresh_published_panels()
        except Exception as exc:
            print(f"[FiveM] Falha ao atualizar paineis publicos: {exc}")

    @fivem_public_panels_loop.before_loop
    async def before_fivem_public_panels_loop(self):
        await self.bot.wait_until_ready()

    async def send_online_status(self, inter: disnake.MessageInteraction):
        await inter.response.defer(ephemeral=True)
        result = await self.fetch_server_status()
        cfg = self.load()
        cache = cfg.get("cache", {})
        if not result.get("ok"):
            await inter.followup.send(f"{_emoji('warn', 'warn')} {result.get('message')}", ephemeral=True)
            return

        await self._send_status_alerts(result)
        players = cache.get("players") if isinstance(cache.get("players"), list) else []
        names = "\n".join(f"- `{p.get('id')}` {p.get('name')}" for p in players[:30])
        if not names:
            names = "Nenhum jogador online."
        await inter.followup.send(
            f"{_emoji('members', 'members')} **Jogadores online:** `{cache.get('online', 0)}/{cache.get('max', 0)}`\n"
            f"**Cidade:** `{cache.get('hostname') or cfg.get('city_name')}`\n\n{names}",
            ephemeral=True,
        )

    async def show_my_release(self, inter: disnake.MessageInteraction):
        user = _user(inter)
        data = self.load()
        linked = data.get("linked_ids", {}).get(str(user.id))
        request = data.get("whitelist", {}).get(str(user.id))
        lines = [f"{_emoji('member', '👤')} **Usuário:** {user.mention}"]
        if linked:
            lines.append(f"{_emoji('link', 'link')} **ID vinculado:** `{linked.get('citizen_id')}` | `{linked.get('character_name')}`")
        else:
            lines.append(f"{_emoji('warn', 'warn')} **ID vinculado:** `Nao vinculado`")
        if request:
            status_map = {"pending": "Pendente", "approved": "Aprovada", "rejected": "Rejeitada"}
            lines.append(f"{_emoji('receipt', 'receipt')} **Whitelist:** `{status_map.get(request.get('status'), request.get('status'))}`")
            if request.get("review_note"):
                lines.append(f"**Observação:** {request.get('review_note')}")
        else:
            lines.append(f"{_emoji('receipt', 'receipt')} **Whitelist:** `Nao solicitada`")
        await inter.response.send_message("\n".join(lines), ephemeral=True)

    async def show_public_factions(self, inter: disnake.MessageInteraction):
        data = self.load()
        factions = [
            fac for fac in (data.get("factions") or {}).values()
            if isinstance(fac, dict) and fac.get("enabled", True)
        ]
        if not factions:
            await inter.response.send_message(f"{_emoji('warn', 'warn')} Nenhuma fac cadastrada no momento.", ephemeral=True)
            return

        options = []
        lines = []
        for fac in factions[:25]:
            fac_id = fac.get("id") or _slug(fac.get("name"))
            role = f"<@&{fac.get('role_id')}>" if fac.get("role_id") else "sem cargo"
            channel = f"<#{fac.get('channel_id')}>" if fac.get("channel_id") else "sem canal"
            description = str(fac.get("description") or "Solicitar entrada na fac")[:100]
            options.append(
                disnake.SelectOption(
                    label=str(fac.get("name") or fac_id)[:100],
                    value=str(fac_id),
                    description=description,
                    emoji=_emoji("group", "members"),
                )
            )
            lines.append(f"- **{fac.get('name')}** | {role} | {channel}")

        await inter.response.send_message(
            f"{_emoji('group', 'members')} **Faccoes disponiveis**\n\n" + "\n".join(lines[:15]),
            components=[
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="FiveM_FactionSelect",
                        placeholder="Escolha uma fac para solicitar entrada",
                        options=options,
                    )
                )
            ],
            ephemeral=True,
        )

    async def submit_staff_time(self, inter: disnake.MessageInteraction, action: str):
        if not self._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode usar o bate ponto da cidade.", ephemeral=True)
            return

        user = _user(inter)
        user_id = str(user.id)
        data = self.load()
        sessions = data.setdefault("staff_sessions", {})

        if action == "start":
            if user_id in sessions:
                started_ts = int(sessions[user_id].get("started_ts") or _now_ts())
                await inter.response.send_message(
                    f"{_emoji('warn', 'warn')} Seu ponto ja esta ativo desde <t:{started_ts}:t>.",
                    ephemeral=True,
                )
                return
            sessions[user_id] = {
                "user_id": user_id,
                "discord_name": str(user),
                "started_at": _now(),
                "started_ts": _now_ts(),
            }
            self.record_event(data, "staff_time_started", user_id, user, sessions[user_id])
            self.save(data)
            await self.send_log(
                f"{_emoji('clock', 'clock')} **Ponto FiveM iniciado**\n"
                f"Staff: {user.mention}\n"
                f"Inicio: <t:{sessions[user_id]['started_ts']}:F>"
            )
            await inter.response.send_message(f"{_emoji('correct', 'correct')} Ponto iniciado com sucesso.", ephemeral=True)
            self.bot.loop.create_task(self.refresh_published_panels())
            return

        session = sessions.pop(user_id, None)
        if not session:
            await inter.response.send_message(f"{_emoji('warn', 'warn')} Voce nao tem ponto ativo para encerrar.", ephemeral=True)
            return

        end_ts = _now_ts()
        started_ts = int(session.get("started_ts") or end_ts)
        duration = max(end_ts - started_ts, 0)
        record = {
            "user_id": user_id,
            "discord_name": str(user),
            "started_at": session.get("started_at") or "",
            "started_ts": started_ts,
            "ended_at": _now(),
            "ended_ts": end_ts,
            "duration_seconds": duration,
            "cancelled": action == "cancel",
        }
        records = data.setdefault("staff_time_records", [])
        if not isinstance(records, list):
            records = []
            data["staff_time_records"] = records
        records.append(record)
        data["staff_time_records"] = records[-300:]
        self.record_event(data, "staff_time_cancelled" if action == "cancel" else "staff_time_ended", user_id, user, record)
        self.save(data)

        label = "cancelado" if action == "cancel" else "encerrado"
        await self.send_log(
            f"{_emoji('clock', 'clock')} **Ponto FiveM {label}**\n"
            f"Staff: {user.mention}\n"
            f"Inicio: <t:{started_ts}:F>\n"
            f"Termino: <t:{end_ts}:F>\n"
            f"Tempo total: `{_duration_text(duration)}`"
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Ponto {label}. Tempo total: `{_duration_text(duration)}`.",
            ephemeral=True,
        )
        self.bot.loop.create_task(self.refresh_published_panels())

    async def review_recruitment_request(self, inter: disnake.MessageInteraction, request_id: str, approved: bool, note: str = ""):
        if not self._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode analisar recrutamento.", ephemeral=True)
            return

        data = self.load()
        request = data.get("recruitment_requests", {}).get(str(request_id))
        if not request:
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Formulario nao encontrado.", ephemeral=True)
            return

        request["status"] = "approved" if approved else "rejected"
        request["reviewed_by"] = str(_user(inter).id)
        request["reviewed_at"] = _now()
        request["review_note"] = str(note or "").strip()
        self.record_event(data, "recruitment_reviewed", request.get("user_id"), _user(inter), {"approved": approved, **request})
        self.save(data)

        user_id = request.get("user_id")
        await self.send_log(
            f"{_emoji('correct', 'correct') if approved else _emoji('wrong', 'wrong')} **Recrutamento {'aprovado' if approved else 'rejeitado'}**\n"
            f"Usuario: <@{user_id}>\n"
            f"Staff: {_user(inter).mention}\n"
            f"Area: `{request.get('area')}`\n"
            f"ID/Cidade: `{request.get('citizen_id')}`"
        )

        try:
            member = await self.bot.fetch_user(int(user_id))
            await member.send(
                f"{_emoji('correct', 'correct') if approved else _emoji('wrong', 'wrong')} "
                f"Seu formulario de recrutamento FiveM foi {'aprovado' if approved else 'rejeitado'}."
                + (f"\nMotivo: {note}" if note else "")
            )
        except Exception:
            pass

        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Recrutamento de <@{user_id}> {'aprovado' if approved else 'rejeitado'}.",
            ephemeral=True,
        )

    async def review_faction_request(self, inter: disnake.MessageInteraction, target_id: str, approved: bool):
        if not self._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode analisar solicitacoes de fac.", ephemeral=True)
            return

        data = self.load()
        request = data.get("faction_requests", {}).get(str(target_id))
        if not request:
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Solicitacao nao encontrada.", ephemeral=True)
            return
        if approved:
            blocked = self._find_blacklist(data, user_id=str(target_id), citizen_id=request.get("citizen_id"))
            if blocked:
                await inter.response.send_message(self._blocked_text(blocked), ephemeral=True)
                return

        faction = data.get("factions", {}).get(request.get("faction_id"), {})
        request["status"] = "approved" if approved else "rejected"
        request["reviewed_by"] = str(_user(inter).id)
        request["reviewed_at"] = _now()
        self.record_event(data, "faction_request_reviewed", target_id, _user(inter), {"approved": approved, **request})
        self.save(data)

        guild = getattr(inter, "guild", None)
        member = guild.get_member(int(target_id)) if guild else None
        role_id = _id(faction.get("role_id"))
        if approved and member and role_id:
            role = guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role, reason="Fac FiveM aprovada")
                except Exception:
                    pass

        await self.send_log(
            f"{_emoji('correct', 'correct') if approved else _emoji('wrong', 'wrong')} **Solicitacao de fac {'aprovada' if approved else 'rejeitada'}**\n"
            f"Usuario: <@{target_id}>\n"
            f"Staff: {_user(inter).mention}\n"
            f"Fac: `{request.get('faction_name') or request.get('faction_id')}`\n"
            f"ID: `{request.get('citizen_id')}`"
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Solicitacao de fac de <@{target_id}> {'aprovada' if approved else 'rejeitada'}.",
            ephemeral=True,
        )

    async def review_whitelist(self, inter: disnake.MessageInteraction, target_id: str, approved: bool, note: str = ""):
        if not self._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode liberar whitelist.", ephemeral=True)
            return

        data = self.load()
        request = data.get("whitelist", {}).get(str(target_id))
        if not request:
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Solicitação nao encontrada.", ephemeral=True)
            return
        if approved:
            blocked = self._find_blacklist(data, user_id=str(target_id), citizen_id=request.get("citizen_id"))
            if blocked:
                await inter.response.send_message(self._blocked_text(blocked), ephemeral=True)
                return

        request["status"] = "approved" if approved else "rejected"
        request["reviewed_by"] = str(_user(inter).id)
        request["reviewed_at"] = _now()
        request["review_note"] = note.strip()
        self.record_event(data, "whitelist_reviewed", target_id, _user(inter), {"approved": approved, **request})
        self.save(data)

        guild = getattr(inter, "guild", None)
        member = guild.get_member(int(target_id)) if guild else None
        role_id = _id(data.get("whitelist_role_id"))
        if approved and member and role_id:
            role = guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role, reason="Whitelist FiveM aprovada")
                except Exception:
                    pass

        await self.send_log(
            f"{_emoji('verified', 'correct') if approved else _emoji('wrong', 'wrong')} **Whitelist {'aprovada' if approved else 'rejeitada'}**\n"
            f"Usuário: <@{target_id}>\n"
            f"Staff: {_user(inter).mention}\n"
            f"ID: `{request.get('citizen_id')}`"
        )
        await inter.response.send_message(
            f"{_emoji('correct', 'correct')} Whitelist de <@{target_id}> {'aprovada' if approved else 'rejeitada'}.",
            ephemeral=True,
        )

    async def _refresh_admin_message(self, inter: disnake.MessageInteraction):
        if not inter.response.is_done():
            await inter.response.defer(with_message=False)
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self._admin_components(),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @commands.Cog.listener("on_button_click")
    async def on_fivem_button(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")

        if custom_id == "FiveM_AdminBack":
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(content=None, embed=None, components=PainelComponents(inter), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_AreaCity":
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._city_area_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_AreaStaff":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode abrir a area de ponto.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._staff_area_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_AreaAutomation":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode abrir automacoes FiveM.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._automation_area_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_ConfigPublicPanels":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode configurar os canais dos paineis.", ephemeral=True)
                return
            await inter.response.send_modal(FiveMPublicPanelsModal(self))
        elif custom_id == "FiveM_ConfigServer":
            await inter.response.send_modal(FiveMServerModal(self))
        elif custom_id == "FiveM_ConfigText":
            await inter.response.send_modal(FiveMRolesTextModal(self))
        elif custom_id == "FiveM_Publish":
            await self.publish_panel(inter)
        elif custom_id == "FiveM_PublishStatus":
            await self.publish_status_panel(inter)
        elif custom_id == "FiveM_PublishStaff":
            await self.publish_staff_panel(inter)
        elif custom_id == "FiveM_RefreshOnline":
            await inter.response.defer(ephemeral=True)
            result = await self.fetch_server_status()
            if result.get("ok"):
                await self._send_status_alerts(result)
                await inter.followup.send(f"{_emoji('correct', 'correct')} Online atualizado: `{result.get('online')}/{result.get('max')}`.", ephemeral=True)
                try:
                    await inter.message.edit(components=self._admin_components(), flags=disnake.MessageFlags(is_components_v2=True))
                except Exception:
                    pass
            else:
                await inter.followup.send(f"{_emoji('warn', 'warn')} {result.get('message')}", ephemeral=True)
        elif custom_id == "FiveM_WhitelistQueue":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode ver a fila de liberação.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._queue_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_FactionsAdmin":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode gerenciar facs.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._factions_admin_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_FactionAdd":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode cadastrar facs.", ephemeral=True)
                return
            await inter.response.send_modal(FiveMFactionModal(self))
        elif custom_id == "FiveM_FactionRequests":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode analisar facs.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._faction_requests_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_RecruitmentAdmin":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode analisar recrutamento.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._recruitment_admin_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_TimeAdmin":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode ver os pontos.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._staff_time_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_CreateStructure":
            await self.create_fivem_structure(inter)
        elif custom_id == "FiveM_SecurityAdmin":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode abrir a segurança FiveM.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._security_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_BlacklistAdd":
            await inter.response.send_modal(FiveMBlacklistModal(self))
        elif custom_id == "FiveM_BlacklistRemove":
            await inter.response.send_modal(FiveMUnblacklistModal(self))
        elif custom_id == "FiveM_PunishmentAdd":
            await inter.response.send_modal(FiveMPunishmentModal(self))
        elif custom_id == "FiveM_ProfileLookup":
            await inter.response.send_modal(FiveMProfileLookupModal(self))
        elif custom_id == "FiveM_Reports":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode ver relatorios.", ephemeral=True)
                return
            if not inter.response.is_done():
                await inter.response.defer(with_message=False)
            await inter.edit_original_message(components=self._reports_components(), flags=disnake.MessageFlags(is_components_v2=True))
        elif custom_id == "FiveM_Alerts":
            await inter.response.send_modal(FiveMAlertsModal(self))
        elif custom_id == "FiveM_Toggle":
            cfg = self.load()
            self.update({"enabled": not bool(cfg.get("enabled"))})
            await self._refresh_admin_message(inter)
        elif custom_id == "FiveM_PublicOnline":
            await self.send_online_status(inter)
        elif custom_id == "FiveM_Factions":
            await self.show_public_factions(inter)
        elif custom_id == "FiveM_LinkID":
            await inter.response.send_modal(FiveMLinkIdModal(self))
        elif custom_id == "FiveM_RequestWhitelist":
            await inter.response.send_modal(FiveMWhitelistModal(self))
        elif custom_id == "FiveM_Recruitment":
            await inter.response.send_modal(FiveMRecruitmentModal(self))
        elif custom_id == "FiveM_TimeStart":
            await self.submit_staff_time(inter, "start")
        elif custom_id == "FiveM_TimeStop":
            await self.submit_staff_time(inter, "stop")
        elif custom_id == "FiveM_TimeCancel":
            await self.submit_staff_time(inter, "cancel")
        elif custom_id == "FiveM_StaffQuickQueues":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode ver pendencias.", ephemeral=True)
                return
            await inter.response.send_message(
                components=[
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(
                            f"# {_emoji('receipt', 'receipt')} Pendencias FiveM\n\n"
                            f"**Whitelist:** `{len(self._pending_requests())}`\n"
                            f"**Faccoes:** `{len(self._pending_faction_requests())}`\n"
                            f"**Recrutamento:** `{len(self._pending_recruitment_requests())}`\n\n"
                            "Escolha uma area para analisar sem usar `/painel`."
                        ),
                        disnake.ui.ActionRow(
                            disnake.ui.Button(label="Whitelist", style=disnake.ButtonStyle.blurple, emoji=_emoji("verified", "verified"), custom_id="FiveM_WhitelistQueue"),
                            disnake.ui.Button(label="Faccoes", style=disnake.ButtonStyle.blurple, emoji=_emoji("group", "members"), custom_id="FiveM_FactionRequests"),
                            disnake.ui.Button(label="Recrutamento", style=disnake.ButtonStyle.blurple, emoji=_emoji("receipt", "receipt"), custom_id="FiveM_RecruitmentAdmin"),
                        ),
                        **self._container_kwargs(),
                    )
                ],
                ephemeral=True,
                flags=disnake.MessageFlags(is_components_v2=True),
            )
        elif custom_id == "FiveM_MyRelease":
            await self.show_my_release(inter)
        elif custom_id == "FiveM_MyProfile":
            await self.show_citizen_profile(inter, str(_user(inter).id))
        elif custom_id.startswith("FiveM_Approve_"):
            await self.review_whitelist(inter, custom_id.replace("FiveM_Approve_", ""), approved=True)
        elif custom_id.startswith("FiveM_Reject_"):
            target_id = custom_id.replace("FiveM_Reject_", "")
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode rejeitar whitelist.", ephemeral=True)
                return
            await inter.response.send_modal(FiveMRejectModal(self, target_id))
        elif custom_id.startswith("FiveM_FactionApprove_"):
            await self.review_faction_request(inter, custom_id.replace("FiveM_FactionApprove_", ""), approved=True)
        elif custom_id.startswith("FiveM_FactionReject_"):
            await self.review_faction_request(inter, custom_id.replace("FiveM_FactionReject_", ""), approved=False)
        elif custom_id.startswith("FiveM_RecruitApprove_"):
            await self.review_recruitment_request(inter, custom_id.replace("FiveM_RecruitApprove_", ""), approved=True)
        elif custom_id.startswith("FiveM_RecruitReject_"):
            request_id = custom_id.replace("FiveM_RecruitReject_", "")
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode rejeitar recrutamento.", ephemeral=True)
                return
            await inter.response.send_modal(FiveMRecruitmentRejectModal(self, request_id))

    @commands.Cog.listener("on_dropdown")
    async def on_fivem_dropdown(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if custom_id not in {"FiveM_WhitelistSelect", "FiveM_FactionSelect", "FiveM_FactionRequestSelect", "FiveM_RecruitmentSelect"}:
            return

        if custom_id == "FiveM_FactionSelect":
            faction_id = inter.values[0]
            await inter.response.send_modal(FiveMFactionRequestModal(self, faction_id))
            return

        if custom_id == "FiveM_FactionRequestSelect":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode analisar facs.", ephemeral=True)
                return
            target_id = inter.values[0]
            request = self.load().get("faction_requests", {}).get(target_id)
            if not request:
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Solicitacao nao encontrada.", ephemeral=True)
                return
            text = (
                f"{_emoji('group', 'members')} **Solicitacao de Fac**\n"
                f"Usuario: <@{target_id}>\n"
                f"Fac: `{request.get('faction_name') or request.get('faction_id')}`\n"
                f"ID: `{request.get('citizen_id')}`\n"
                f"Personagem: `{request.get('character_name')}`\n\n"
                f"**Motivo:**\n{request.get('reason') or 'N/A'}"
            )
            await inter.response.send_message(
                text,
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Aprovar", style=disnake.ButtonStyle.green, emoji=_emoji("correct", "correct"), custom_id=f"FiveM_FactionApprove_{target_id}"),
                        disnake.ui.Button(label="Rejeitar", style=disnake.ButtonStyle.red, emoji=_emoji("wrong", "wrong"), custom_id=f"FiveM_FactionReject_{target_id}"),
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "FiveM_RecruitmentSelect":
            if not self._is_staff(_user(inter)):
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode analisar recrutamento.", ephemeral=True)
                return
            request_id = inter.values[0]
            request = self.load().get("recruitment_requests", {}).get(request_id)
            if not request:
                await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Formulario nao encontrado.", ephemeral=True)
                return
            text = (
                f"{_emoji('receipt', 'receipt')} **Formulario de Recrutamento FiveM**\n"
                f"Usuario: <@{request.get('user_id')}>\n"
                f"ID/Cidade: `{request.get('citizen_id')}`\n"
                f"Area: `{request.get('area')}`\n"
                f"Disponibilidade: `{request.get('availability') or 'N/A'}`\n\n"
                f"**Experiencia/motivo:**\n{request.get('reason') or 'N/A'}"
            )
            await inter.response.send_message(
                text,
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Aprovar", style=disnake.ButtonStyle.green, emoji=_emoji("correct", "correct"), custom_id=f"FiveM_RecruitApprove_{request_id}"),
                        disnake.ui.Button(label="Rejeitar", style=disnake.ButtonStyle.red, emoji=_emoji("wrong", "wrong"), custom_id=f"FiveM_RecruitReject_{request_id}"),
                    )
                ],
                ephemeral=True,
            )
            return

        if not self._is_staff(_user(inter)):
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Apenas a staff pode analisar whitelist.", ephemeral=True)
            return

        target_id = inter.values[0]
        request = self.load().get("whitelist", {}).get(target_id)
        if not request:
            await inter.response.send_message(f"{_emoji('wrong', 'wrong')} Solicitação nao encontrada.", ephemeral=True)
            return
        text = (
            f"{_emoji('receipt', 'receipt')} **Solicitação de Whitelist**\n"
            f"Usuário: <@{target_id}>\n"
            f"ID: `{request.get('citizen_id')}`\n"
            f"Personagem: `{request.get('character_name')}`\n"
            f"Idade: `{request.get('age') or 'N/A'}`\n\n"
            f"**Motivo/experiência:**\n{request.get('reason') or 'N/A'}"
        )
        await inter.response.send_message(
            text,
            components=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Aprovar", style=disnake.ButtonStyle.green, emoji=_emoji("correct", "correct"), custom_id=f"FiveM_Approve_{target_id}"),
                    disnake.ui.Button(label="Rejeitar", style=disnake.ButtonStyle.red, emoji=_emoji("wrong", "wrong"), custom_id=f"FiveM_Reject_{target_id}"),
                )
            ],
            ephemeral=True,
        )


def setup(bot: commands.Bot):
    bot.add_cog(FiveMLyonPanel(bot))
