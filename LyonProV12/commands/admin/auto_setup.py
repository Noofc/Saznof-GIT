from __future__ import annotations

import json
import re
import secrets
import unicodedata
from datetime import datetime
from urllib.parse import urlencode

import disnake
from disnake.ext import commands

from functions import auto_setup as setup_utils
from functions.ai_api import chamar_ia
from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import load_guild_channels, save_guild_channels
from functions.perms import perms
from functions.system_logs import send_system_log
from .panel_v2 import build_panel_card, channel_label, status_label


STATE_PREFIX = "auto_setup_state_"
RUNS_KEY = "auto_setup_runs"
AI_PENDING_KEY = "auto_setup_ai_pending"
AI_RUNS_KEY = "auto_setup_ai_runs"
TICKET_PANEL_PREFIX = "autosetup_ticket_"
FIVEM_DATA_PATH = "database/fivem_system.json"
BATEPONTO_DATA_PATH = "database/bateponto_system.json"
SOCIAL_DATA_PATH = "database/social_systems.json"


def _emoji(key: str, fallback: str = "settings"):
    value = getattr(emoji, key, None)
    if value:
        return value
    if fallback:
        fallback_value = getattr(emoji, fallback, None)
        if fallback_value:
            return fallback_value
    return None


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


ROLE_SPECS = {
    "manager": {"label": "Gerente", "colour": 0x2F80ED},
    "staff": {"label": "Staff", "colour": 0x6C63FF},
    "support": {"label": "Suporte", "colour": 0x00A86B},
    "client": {"label": "Cliente", "colour": 0xF2C94C},
    "member": {"label": "Membro", "colour": 0x95A5A6},
    "verified": {"label": "Verificado", "colour": 0x27AE60},
    "creator": {"label": "Criador", "colour": 0xBB6BD9},
    "partner": {"label": "Parceiro", "colour": 0x56CCF2},
    "mediator": {"label": "Mediador MM", "colour": 0xEB5757},
    "fivem_staff": {"label": "Staff FiveM", "colour": 0x2D9CDB},
    "fivem_whitelist": {"label": "Whitelist", "colour": 0x27AE60},
    "fivem_faction": {"label": "Faccoes", "colour": 0x9B51E0},
    "roblox_staff": {"label": "Staff Roblox", "colour": 0xF2994A},
}

STAFF_ROLE_KEYS = {"manager", "staff", "support", "mediator", "fivem_staff", "roblox_staff"}

CATEGORY_SPECS = {
    "geral": {"label": "Geral"},
    "loja": {"label": "Loja"},
    "atendimento": {"label": "Atendimento"},
    "tickets": {"label": "Tickets", "private": True},
    "middleman": {"label": "Middleman", "private": True},
    "comunidade": {"label": "Comunidade"},
    "fivem": {"label": "FiveM"},
    "roblox": {"label": "Roblox"},
    "staff": {"label": "Staff", "private": True},
    "logs": {"label": "Logs", "private": True},
}

CHANNEL_SPECS = {
    "boas_vindas": {"label": "boas-vindas", "emoji": "👋", "category": "geral"},
    "regras": {"label": "regras", "emoji": "📜", "category": "geral", "read_only": True},
    "avisos": {"label": "avisos", "emoji": "📢", "category": "geral", "read_only": True},
    "chat": {"label": "chat-geral", "emoji": "💬", "category": "geral"},
    "loja": {"label": "loja", "emoji": "🛒", "category": "loja", "read_only": True},
    "produtos": {"label": "produtos", "emoji": "📦", "category": "loja", "read_only": True},
    "estoque": {"label": "estoque", "emoji": "📦", "category": "loja", "staff_only": True},
    "feedback": {"label": "feedback", "emoji": "⭐", "category": "loja"},
    "support_panel": {"label": "suporte", "emoji": "🎫", "category": "atendimento"},
    "middleman_panel": {"label": "middleman", "emoji": "💎", "category": "atendimento"},
    "ticket_waiting": {"label": "triagem", "emoji": "📨", "category": "tickets", "staff_only": True},
    "community_hub": {"label": "central-comunidade", "emoji": "🏠", "category": "comunidade"},
    "apresentacoes": {"label": "apresentacoes", "emoji": "👋", "category": "comunidade"},
    "sugestoes": {"label": "sugestoes", "emoji": "💡", "category": "comunidade"},
    "eventos": {"label": "eventos", "emoji": "📅", "category": "comunidade"},
    "instagram_feed": {"label": "instagram", "emoji": "📸", "category": "comunidade"},
    "redes_sociais": {"label": "redes-sociais", "emoji": "🔗", "category": "comunidade", "read_only": True},
    "parcerias": {"label": "parcerias", "emoji": "🤝", "category": "comunidade"},
    "criadores": {"label": "criadores", "emoji": "🎬", "category": "comunidade"},
    "fivem_panel": {"label": "painel-fivem", "emoji": "🎮", "category": "fivem"},
    "fivem_status": {"label": "status-cidade", "emoji": "📡", "category": "fivem", "read_only": True},
    "fivem_whitelist": {"label": "whitelist", "emoji": "✅", "category": "fivem"},
    "fivem_recruitment": {"label": "recrutamento", "emoji": "🧾", "category": "fivem"},
    "fivem_factions": {"label": "faccoes", "emoji": "⚔️", "category": "fivem"},
    "fivem_staff_point": {"label": "ponto-staff", "emoji": "⏱️", "category": "fivem"},
    "robux_panel": {"label": "robux", "emoji": "💎", "category": "roblox"},
    "robux_orders": {"label": "pedidos-robux", "emoji": "🧾", "category": "roblox", "staff_only": True},
    "roblox_group": {"label": "verificacao-grupo", "emoji": "🔎", "category": "roblox", "read_only": True},
    "roblox_proofs": {"label": "comprovantes", "emoji": "📎", "category": "roblox"},
    "staff_panel": {"label": "painel-staff", "emoji": "🛡️", "category": "staff", "staff_only": True},
    "bateponto_panel": {"label": "bate-ponto", "emoji": "⏱️", "category": "staff", "staff_only": True},
    "logs_system": {"label": "logs-sistema", "emoji": "📋", "category": "logs", "staff_only": True},
    "logs_sales": {"label": "logs-vendas", "emoji": "🧾", "category": "logs", "staff_only": True},
    "logs_tickets": {"label": "logs-tickets", "emoji": "🎫", "category": "logs", "staff_only": True},
    "logs_middleman": {"label": "logs-middleman", "emoji": "💎", "category": "logs", "staff_only": True},
    "logs_fivem": {"label": "logs-fivem", "emoji": "🎮", "category": "logs", "staff_only": True},
    "logs_robux": {"label": "logs-robux", "emoji": "💎", "category": "logs", "staff_only": True},
    "logs_community": {"label": "logs-comunidade", "emoji": "🏠", "category": "logs", "staff_only": True},
    "logs_scam": {"label": "logs-golpes", "emoji": "🛡️", "category": "logs", "staff_only": True},
}

TEMPLATES = {
    "complete": {
        "label": "Completo",
        "description": "Servidor pronto para venda, suporte, comunidade, FiveM, Roblox, middleman, logs e staff.",
        "roles": [
            "manager", "staff", "support", "client", "member", "verified", "creator", "partner",
            "mediator", "fivem_staff", "fivem_whitelist", "fivem_faction", "roblox_staff",
        ],
        "categories": ["geral", "loja", "atendimento", "tickets", "middleman", "comunidade", "fivem", "roblox", "staff", "logs"],
        "channels": list(CHANNEL_SPECS),
        "systems": ["tickets", "middleman", "community", "instagram", "fivem", "bateponto", "robux", "stock", "security", "welcome"],
    },
    "loja": {
        "label": "Loja",
        "description": "Estrutura para produtos, estoque, feedback, suporte, logs de vendas e alertas de stock.",
        "roles": ["manager", "staff", "support", "client"],
        "categories": ["loja", "atendimento", "tickets", "staff", "logs"],
        "channels": ["loja", "produtos", "estoque", "feedback", "support_panel", "ticket_waiting", "staff_panel", "logs_sales", "logs_tickets", "logs_system"],
        "systems": ["tickets", "stock", "security"],
    },
    "vendas": {
        "label": "Vendas",
        "description": "Modelo comercial com loja, middleman, tickets, feedback, robux e logs.",
        "roles": ["manager", "staff", "support", "client", "mediator", "roblox_staff"],
        "categories": ["loja", "atendimento", "tickets", "middleman", "roblox", "logs"],
        "channels": ["loja", "produtos", "feedback", "support_panel", "middleman_panel", "robux_panel", "robux_orders", "ticket_waiting", "logs_sales", "logs_tickets", "logs_middleman", "logs_robux", "logs_scam"],
        "systems": ["tickets", "middleman", "robux", "stock", "security"],
    },
    "suporte": {
        "label": "Suporte",
        "description": "Servidor de atendimento com ticket, triagem, bate ponto, logs e detector de golpes.",
        "roles": ["manager", "staff", "support", "client"],
        "categories": ["atendimento", "tickets", "staff", "logs"],
        "channels": ["support_panel", "ticket_waiting", "staff_panel", "bateponto_panel", "logs_tickets", "logs_system", "logs_scam"],
        "systems": ["tickets", "bateponto", "security"],
    },
    "comunidade": {
        "label": "Comunidade",
        "description": "Comunidade pronta com hub, apresentacoes, sugestoes, eventos, Instagram, parcerias e logs.",
        "roles": ["manager", "staff", "member", "verified", "creator", "partner"],
        "categories": ["geral", "comunidade", "logs"],
        "channels": ["boas_vindas", "regras", "avisos", "chat", "community_hub", "apresentacoes", "sugestoes", "eventos", "instagram_feed", "redes_sociais", "parcerias", "criadores", "logs_community", "logs_system"],
        "systems": ["community", "instagram", "welcome"],
    },
    "fivem": {
        "label": "FiveM",
        "description": "Cidade FiveM com whitelist, faccoes, recrutamento, bate ponto staff, status e logs.",
        "roles": ["manager", "staff", "fivem_staff", "fivem_whitelist", "fivem_faction", "member"],
        "categories": ["fivem", "staff", "logs"],
        "channels": ["fivem_panel", "fivem_status", "fivem_whitelist", "fivem_recruitment", "fivem_factions", "fivem_staff_point", "bateponto_panel", "logs_fivem", "logs_system"],
        "systems": ["fivem", "bateponto", "security"],
    },
    "roblox": {
        "label": "Roblox",
        "description": "Robux com pedidos, calculadora, verificacao de grupo, comprovantes e logs.",
        "roles": ["manager", "staff", "roblox_staff", "client"],
        "categories": ["roblox", "atendimento", "tickets", "logs"],
        "channels": ["robux_panel", "robux_orders", "roblox_group", "roblox_proofs", "support_panel", "ticket_waiting", "logs_robux", "logs_tickets", "logs_system"],
        "systems": ["robux", "tickets", "security"],
    },
    "middleman": {
        "label": "Middleman",
        "description": "Intermediacao com painel publico, categoria privada, equipe, logs e detector de golpes.",
        "roles": ["manager", "staff", "support", "mediator", "client"],
        "categories": ["atendimento", "middleman", "logs"],
        "channels": ["middleman_panel", "support_panel", "logs_middleman", "logs_scam", "logs_system"],
        "systems": ["middleman", "security"],
    },
}

AI_TEMPLATE_SOURCES = {
    "loja": "loja",
    "vendas": "vendas",
    "suporte": "suporte",
    "comunidade": "comunidade",
    "fivem": "fivem",
    "roblox": "roblox",
    "middleman": "middleman",
}

AI_KEYWORDS = {
    "loja": ["loja", "produto", "produtos", "estoque", "restock", "stock", "checkout", "venda", "vendas", "pix", "cupom", "cliente"],
    "vendas": ["vendas", "marketplace", "middleman", "intermedio", "intermediacao", "robux", "gamepass", "pagamento"],
    "suporte": ["suporte", "ticket", "atendimento", "helpdesk", "duvida", "triagem"],
    "comunidade": ["comunidade", "membros", "engajamento", "instagram", "social", "evento", "eventos", "parceria", "parcerias", "criador", "criadores"],
    "fivem": ["fivem", "cidade", "whitelist", "wl", "fac", "faccao", "faccoes", "recrutamento", "ponto staff", "status cidade"],
    "roblox": ["roblox", "robux", "grupo", "gamepass", "comprovante", "verificacao de grupo"],
    "middleman": ["middleman", "intermedio", "intermediario", "intermediacao", "mm", "pix seguro", "troca"],
    "security": ["seguranca", "anti raid", "antiraid", "golpe", "golpes", "anti fraude", "antifraude", "moderacao", "verificacao"],
}

AI_FAMILY_LABELS = {
    "loja": "Loja",
    "vendas": "Vendas",
    "suporte": "Suporte",
    "comunidade": "Comunidade",
    "fivem": "FiveM",
    "roblox": "Roblox",
    "middleman": "Middleman",
    "security": "Seguranca",
}

AI_COMPLETE_SYSTEMS = ["tickets", "middleman", "community", "instagram", "fivem", "bateponto", "robux", "stock", "security", "welcome"]

AI_SYSTEM_REQUIREMENTS = {
    "tickets": {
        "roles": ["manager", "staff", "support", "client"],
        "categories": ["atendimento", "tickets", "logs"],
        "channels": ["support_panel", "ticket_waiting", "logs_tickets"],
    },
    "middleman": {
        "roles": ["manager", "staff", "support", "mediator", "client"],
        "categories": ["atendimento", "middleman", "logs"],
        "channels": ["middleman_panel", "logs_middleman", "logs_scam"],
    },
    "community": {
        "roles": ["manager", "staff", "member", "verified", "creator", "partner"],
        "categories": ["geral", "comunidade", "logs"],
        "channels": ["boas_vindas", "regras", "avisos", "chat", "community_hub", "apresentacoes", "sugestoes", "eventos", "redes_sociais", "parcerias", "criadores", "logs_community"],
    },
    "instagram": {
        "roles": ["manager", "staff", "member", "creator"],
        "categories": ["comunidade", "logs"],
        "channels": ["instagram_feed", "logs_community"],
    },
    "fivem": {
        "roles": ["manager", "staff", "fivem_staff", "fivem_whitelist", "fivem_faction", "member"],
        "categories": ["fivem", "staff", "logs"],
        "channels": ["fivem_panel", "fivem_status", "fivem_whitelist", "fivem_recruitment", "fivem_factions", "fivem_staff_point", "logs_fivem"],
    },
    "bateponto": {
        "roles": ["manager", "staff", "fivem_staff"],
        "categories": ["staff", "fivem", "logs"],
        "channels": ["bateponto_panel", "logs_fivem", "logs_system"],
    },
    "robux": {
        "roles": ["manager", "staff", "roblox_staff", "client"],
        "categories": ["roblox", "logs"],
        "channels": ["robux_panel", "robux_orders", "roblox_group", "roblox_proofs", "logs_robux"],
    },
    "stock": {
        "roles": ["manager", "staff", "client"],
        "categories": ["loja", "logs"],
        "channels": ["loja", "produtos", "estoque", "feedback", "logs_sales"],
    },
    "security": {
        "roles": ["manager", "staff"],
        "categories": ["staff", "logs"],
        "channels": ["staff_panel", "logs_system", "logs_scam"],
    },
    "welcome": {
        "roles": ["member"],
        "categories": ["geral"],
        "channels": ["boas_vindas", "regras", "avisos", "chat"],
    },
}

AI_CHANNEL_IDEAS = [
    ("central", "central", "🏠", "geral", True),
    ("informacoes", "informacoes", "📌", "geral", True),
    ("anuncios", "anuncios", "📢", "geral", True),
    ("duvidas", "duvidas", "❓", "atendimento", False),
    ("status", "status", "📡", "geral", True),
    ("ranking", "ranking", "🏆", "comunidade", True),
    ("midias", "midias", "📸", "comunidade", False),
    ("eventos-vip", "eventos-vip", "🎉", "comunidade", False),
    ("area-staff", "area-staff", "🛡️", "staff", False),
    ("tarefas-staff", "tarefas-staff", "✅", "staff", False),
    ("relatorios", "relatorios", "📊", "staff", True),
    ("logs-auditoria", "logs-auditoria", "📋", "logs", True),
]

AI_PERMISSION_PRESETS = {
    "owner": ["administrator"],
    "manager": ["manage_guild", "manage_channels", "manage_roles", "manage_messages", "view_audit_log", "kick_members", "ban_members", "moderate_members", "move_members", "mute_members"],
    "staff": ["manage_messages", "kick_members", "moderate_members", "move_members", "mute_members"],
    "support": ["manage_messages", "read_message_history", "attach_files"],
    "moderation": ["manage_messages", "kick_members", "ban_members", "moderate_members"],
    "none": [],
}


class AutoSetupCustomizeModal(disnake.ui.Modal):
    def __init__(self, cog: "AutoSetupPanel"):
        self.cog = cog
        cfg = setup_utils.get_config()
        super().__init__(
            title="Personalizar Auto Setup",
            custom_id="AutoSetup_CustomizeModal",
            components=[
                disnake.ui.TextInput(
                    label="Separador",
                    custom_id="separator",
                    value=str(cfg.get("separator") or setup_utils.DEFAULT_SEPARATOR)[:20],
                    max_length=20,
                    required=True,
                ),
                disnake.ui.TextInput(
                    label="Modelo dos canais",
                    custom_id="channel_pattern",
                    value=str(cfg.get("channel_pattern") or "{emoji}{separator}{name}")[:80],
                    max_length=80,
                    required=True,
                ),
                disnake.ui.TextInput(
                    label="Modelo dos cargos",
                    custom_id="role_pattern",
                    value=str(cfg.get("role_pattern") or "{name}")[:80],
                    max_length=80,
                    required=True,
                ),
                disnake.ui.TextInput(
                    label="Categoria de logs",
                    custom_id="logs_category",
                    value=str(cfg.get("logs_category") or "╺╸ Logs")[:80],
                    max_length=80,
                    required=True,
                ),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        cfg = setup_utils.get_config()
        values = inter.text_values
        cfg["separator"] = str(values.get("separator") or "╺╸").strip()[:20]
        cfg["channel_pattern"] = str(values.get("channel_pattern") or "{emoji}{separator}{name}").strip()[:80]
        cfg["role_pattern"] = str(values.get("role_pattern") or "{name}").strip()[:80]
        cfg["logs_category"] = str(values.get("logs_category") or "╺╸ Logs").strip()[:80]
        setup_utils.save_config(cfg)
        await inter.response.send_message(f"{emoji.correct} Modelo do Auto Setup atualizado.", ephemeral=True)


class AutoSetupAIDescriptionModal(disnake.ui.Modal):
    def __init__(self, cog: "AutoSetupPanel"):
        self.cog = cog
        super().__init__(
            title="Criar Servidor com IA",
            custom_id="AutoSetup_AIDescriptionModal",
            components=[
                disnake.ui.TextInput(
                    label="Como voce quer o servidor?",
                    custom_id="description",
                    style=disnake.TextInputStyle.paragraph,
                    placeholder="Ex: quero uma loja com tickets, robux, logs, anti fraude e uma area de comunidade",
                    max_length=1500,
                    required=True,
                ),
                disnake.ui.TextInput(
                    label="Nome ou tema do servidor",
                    custom_id="theme",
                    placeholder="Ex: Lyon Store, cidade FiveM, comunidade Roblox...",
                    max_length=80,
                    required=False,
                ),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await self.cog._handle_ai_description(inter)


class AutoSetupAIGuildModal(disnake.ui.Modal):
    def __init__(self, cog: "AutoSetupPanel", request_id: str):
        self.cog = cog
        self.request_id = request_id
        super().__init__(
            title="Servidor Alvo",
            custom_id=f"AutoSetup_AIGuildModal:{request_id}",
            components=[
                disnake.ui.TextInput(
                    label="ID do servidor",
                    custom_id="guild_id",
                    placeholder="Cole aqui o ID do servidor onde o Lyon IA ja esta",
                    max_length=24,
                    required=True,
                ),
                disnake.ui.TextInput(
                    label="Confirmar recriacao limpa",
                    custom_id="reset_confirm",
                    value="RECRIAR",
                    placeholder="Digite RECRIAR para apagar os canais atuais e recriar tudo",
                    max_length=12,
                    required=True,
                ),
                disnake.ui.TextInput(
                    label="Publicar paineis? (sim/nao)",
                    custom_id="publish",
                    value="sim",
                    max_length=8,
                    required=True,
                ),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await self.cog._handle_ai_guild(inter, self.request_id)


class AutoSetupPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _flags(self) -> disnake.MessageFlags:
        return disnake.MessageFlags(is_components_v2=True)

    def _state_key(self, guild_id: int) -> str:
        return f"{STATE_PREFIX}{guild_id}"

    def _get_state(self, guild_id: int) -> dict:
        data = db.get_document(self._state_key(guild_id)) or {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("selected_template", "complete")
        data.setdefault("last_channels", {})
        data.setdefault("last_categories", {})
        data.setdefault("last_roles", {})
        data.setdefault("published_messages", {})
        return data

    def _save_state(self, guild_id: int, data: dict) -> None:
        db.save_document(self._state_key(guild_id), data)

    def _system_ia_invite_url(self, guild_id: int | str | None = None) -> str:
        client_id = str(getattr(self.bot.user, "id", "") or "")
        if not client_id:
            config = db.obter("config.json") or {}
            client_id = str(config.get("botID") or "")
        params = {
            "client_id": client_id,
            "permissions": "8",
            "scope": "bot applications.commands",
        }
        if guild_id:
            params["guild_id"] = str(guild_id)
            params["disable_guild_select"] = "true"
        return "https://discord.com/api/oauth2/authorize?" + urlencode(params)

    def _system_ia_invite_button(self, guild_id: int | str | None = None) -> disnake.ui.Button:
        return disnake.ui.Button(
            label="Adicionar Lyon IA",
            style=disnake.ButtonStyle.link,
            emoji=_emoji("robot", "wand"),
            url=self._system_ia_invite_url(guild_id),
        )

    def _template(self, key: str | None) -> dict:
        return TEMPLATES.get(str(key or ""), TEMPLATES["complete"])

    def _template_key(self, key: str | None) -> str:
        return str(key or "complete") if str(key or "complete") in TEMPLATES else "complete"

    def _normalize_ai_text(self, value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or "").lower())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", text).strip()

    def _unique_ordered(self, keys: list[str], order: list[str]) -> list[str]:
        selected = set(keys)
        return [key for key in order if key in selected]

    def _ai_scores(self, description: str) -> dict[str, int]:
        text = self._normalize_ai_text(description)
        scores = {family: 0 for family in AI_KEYWORDS}
        for family, words in AI_KEYWORDS.items():
            for word in words:
                token = self._normalize_ai_text(word)
                if token and token in text:
                    scores[family] += 1
        return scores

    def _ai_wants_complete(self, text: str) -> bool:
        complete_terms = (
            "completo", "completa", "full", "tudo", "todos os sistemas", "todas as funcionalidades",
            "servidor completo", "bot completo", "automacao completa", "automacoes completas",
        )
        return any(term in text for term in complete_terms)

    def _infer_ai_systems(self, plan: dict, description: str, theme: str, scores: dict[str, int]) -> list[str]:
        text = self._normalize_ai_text(f"{theme} {description}")
        requested = [
            str(system).strip().lower()
            for system in (plan.get("systems") if isinstance(plan.get("systems"), list) else [])
            if str(system).strip().lower() in AI_COMPLETE_SYSTEMS
        ]

        if self._ai_wants_complete(text):
            return list(AI_COMPLETE_SYSTEMS)

        inferred: list[str] = []
        if scores.get("loja") or scores.get("vendas") or any(word in text for word in ("loja", "venda", "produto", "estoque", "restock", "stock", "checkout", "pix")):
            self._append_unique(inferred, ["stock", "tickets", "security"])
        if scores.get("suporte") or any(word in text for word in ("suporte", "ticket", "atendimento", "triagem", "helpdesk")):
            self._append_unique(inferred, ["tickets"])
        if scores.get("middleman") or any(word in text for word in ("middleman", "intermedio", "intermediacao", "mm", "pix seguro")):
            self._append_unique(inferred, ["middleman", "security"])
        if scores.get("comunidade") or any(word in text for word in ("comunidade", "membro", "engajamento", "evento", "eventos", "parceria", "criador", "social")):
            self._append_unique(inferred, ["community", "welcome"])
        if any(word in text for word in ("instagram", "feed", "foto", "fotos", "video", "videos", "midia", "midias")):
            self._append_unique(inferred, ["instagram", "community"])
        if scores.get("fivem") or any(word in text for word in ("fivem", "cidade", "whitelist", "fac", "faccao", "faccoes", "recrutamento city", "ponto staff")):
            self._append_unique(inferred, ["fivem", "bateponto", "security"])
        if scores.get("roblox") or any(word in text for word in ("roblox", "robux", "gamepass", "grupo roblox", "verificacao de grupo")):
            self._append_unique(inferred, ["robux", "tickets", "security"])
        if scores.get("security") or any(word in text for word in ("seguranca", "anti raid", "antiraid", "golpe", "golpes", "anti fraude", "antifraude", "moderacao")):
            self._append_unique(inferred, ["security"])
        if any(word in text for word in ("boas vindas", "bem vindo", "entrada", "regras", "avisos")):
            self._append_unique(inferred, ["welcome"])

        if requested:
            if inferred:
                systems = [system for system in requested if system in inferred]
                self._append_unique(systems, inferred)
                return systems
            return requested

        if inferred:
            return inferred
        return ["community", "security"]

    def _category_from_raw_ai(self, raw_category: str, categories: list[str], category_specs: dict[str, dict], category_alias: dict[str, str], used: set[str], *, private: bool = False) -> str:
        clean = self._normalize_ai_text(raw_category)
        if not clean:
            return ""
        if clean in category_alias:
            return category_alias[clean]
        if clean in CATEGORY_SPECS:
            if clean not in categories:
                categories.append(clean)
            return clean

        key = self._ai_key("ai_cat", clean, used)
        label = str(raw_category or clean).replace("-", " ").strip().title()[:80] or "Area"
        category_alias[clean] = key
        category_specs[key] = {"label": label, "private": private}
        categories.append(key)
        return key

    def _ai_json_prompt(self, description: str, theme: str, scores: dict[str, int]) -> str:
        return (
            "Voce e uma IA de arquitetura de servidores Discord para um bot de automacoes chamado Lyon Pro.\n"
            "Crie uma estrutura propria, completa e profissional para o servidor descrito pelo usuario.\n"
            "A descricao do usuario manda mais que qualquer modelo interno. Siga literalmente o nicho, nomes, areas e prioridades que ele pediu.\n"
            "Nao copie templates prontos. Responda SOMENTE JSON valido, sem markdown.\n\n"
            "Schema obrigatorio:\n"
            "{\n"
            '  "label": "nome curto do plano",\n'
            '  "description": "resumo operacional",\n'
            '  "roles": [{"key":"staff_pro","label":"Staff Pro","colour":"#0082ff","staff":true,"hoist":true,"permission_preset":"staff"}],\n'
            '  "categories": [{"key":"central","label":"Central","private":false}],\n'
            '  "channels": [{"key":"avisos_vip","label":"avisos-vip","emoji":"📢","category":"central","read_only":true,"staff_only":false,"topic":"..."}],\n'
            '  "systems": ["tickets","middleman","community","instagram","fivem","bateponto","robux","stock","security","welcome"]\n'
            "}\n\n"
            "Regras:\n"
            "- Use nomes de canais curtos, em minusculo, sem espacos, com hifen.\n"
            "- Inclua somente areas e sistemas coerentes com o pedido. Nao adicione loja, Roblox, FiveM, middleman ou comunidade se o usuario nao pediu ou nao ficou claro.\n"
            "- Inclua canais especificos para o nicho informado; evite canais genericos quando o usuario deu detalhes.\n"
            "- Se o usuario citar nomes de categorias, cargos ou canais, preserve esses nomes na estrutura.\n"
            "- Crie 6 a 14 cargos personalizados para o nicho, com nomes bonitos, cores diferentes e hierarquia real.\n"
            "- Cargos de equipe podem usar permission_preset: owner, manager, staff, support, moderation ou none.\n"
            "- Use hoist=true em cargos importantes que devem aparecer separados na lista de membros.\n"
            "- Em systems, liste apenas os sistemas realmente necessarios para esse servidor.\n"
            "- Categorias privadas devem ser usadas para staff/logs/tickets internos.\n\n"
            f"Tema: {theme or 'nao informado'}\n"
            f"Descricao: {description}\n"
            f"Pontuacao local de intencao: {scores}\n"
        )

    def _extract_json_object(self, value: str) -> dict | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        raw = raw.replace("```json", "```").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start:end + 1])
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _ai_key(self, prefix: str, label: str, used: set[str]) -> str:
        base = setup_utils.slugify(label)
        base = re.sub(r"[^a-z0-9_-]+", "-", self._normalize_ai_text(base)).strip("-_")
        if not base:
            base = prefix
        key = f"{prefix}_{base}"[:48]
        original = key
        index = 2
        while key in used or key in ROLE_SPECS or key in CATEGORY_SPECS or key in CHANNEL_SPECS:
            key = f"{original[:42]}_{index}"
            index += 1
        used.add(key)
        return key

    def _colour_value(self, value, default: int = 0x0082FF) -> int:
        if isinstance(value, int):
            return max(0, min(0xFFFFFF, value))
        raw = str(value or "").strip().replace("#", "")
        try:
            return int(raw, 16) if raw else default
        except Exception:
            return default

    def _append_unique(self, target: list[str], values: list[str]) -> None:
        for value in values:
            if value and value not in target:
                target.append(value)

    def _fallback_role_ideas(self, text: str, scores: dict[str, int]) -> list[dict]:
        roles = [
            {"key": "ai_direcao_geral", "label": "Direcao Geral", "colour": "#0082ff", "staff": True, "hoist": True, "permission_preset": "owner"},
            {"key": "ai_administracao", "label": "Administracao", "colour": "#2f80ed", "staff": True, "hoist": True, "permission_preset": "manager"},
            {"key": "ai_coordenacao", "label": "Coordenacao", "colour": "#6c63ff", "staff": True, "hoist": True, "permission_preset": "staff"},
            {"key": "ai_atendimento", "label": "Atendimento", "colour": "#00a86b", "staff": True, "hoist": True, "permission_preset": "support"},
            {"key": "ai_cliente_verificado", "label": "Cliente Verificado", "colour": "#27ae60", "staff": False, "hoist": False, "permission_preset": "none"},
            {"key": "ai_membro_oficial", "label": "Membro Oficial", "colour": "#95a5a6", "staff": False, "hoist": False, "permission_preset": "none"},
            {"key": "ai_parceiro", "label": "Parceiro", "colour": "#56ccf2", "staff": False, "hoist": True, "permission_preset": "none"},
        ]
        if scores.get("loja") or scores.get("vendas") or any(word in text for word in ("loja", "venda", "produto", "estoque")):
            roles.extend([
                {"key": "ai_gestor_loja", "label": "Gestor da Loja", "colour": "#0082ff", "staff": True, "hoist": True, "permission_preset": "manager"},
                {"key": "ai_entregador", "label": "Entregador", "colour": "#f2c94c", "staff": True, "hoist": True, "permission_preset": "support"},
                {"key": "ai_cliente_premium", "label": "Cliente Premium", "colour": "#f2994a", "staff": False, "hoist": True, "permission_preset": "none"},
                {"key": "ai_alerta_restock", "label": "Avisos de Restock", "colour": "#9b51e0", "staff": False, "hoist": False, "permission_preset": "none"},
            ])
        if scores.get("fivem") or "fivem" in text or "cidade" in text:
            roles.extend([
                {"key": "ai_diretor_cidade", "label": "Diretor da Cidade", "colour": "#0082ff", "staff": True, "hoist": True, "permission_preset": "manager"},
                {"key": "ai_staff_wl", "label": "Equipe Whitelist", "colour": "#27ae60", "staff": True, "hoist": True, "permission_preset": "staff"},
                {"key": "ai_gestor_fac", "label": "Gestor de Faccoes", "colour": "#9b51e0", "staff": True, "hoist": True, "permission_preset": "staff"},
                {"key": "ai_lider_fac", "label": "Lider de Faccao", "colour": "#eb5757", "staff": False, "hoist": True, "permission_preset": "none"},
                {"key": "ai_cidadao", "label": "Cidadao", "colour": "#95a5a6", "staff": False, "hoist": False, "permission_preset": "none"},
            ])
        if scores.get("roblox") or "roblox" in text or "robux" in text:
            roles.extend([
                {"key": "ai_gerente_robux", "label": "Gerente Robux", "colour": "#0082ff", "staff": True, "hoist": True, "permission_preset": "manager"},
                {"key": "ai_verificador_grupo", "label": "Verificador de Grupo", "colour": "#f2994a", "staff": True, "hoist": True, "permission_preset": "support"},
                {"key": "ai_cliente_robux", "label": "Cliente Robux", "colour": "#27ae60", "staff": False, "hoist": True, "permission_preset": "none"},
                {"key": "ai_aguardando_entrega", "label": "Aguardando Entrega", "colour": "#f2c94c", "staff": False, "hoist": False, "permission_preset": "none"},
            ])
        if scores.get("middleman") or "middleman" in text or "intermedio" in text:
            roles.extend([
                {"key": "ai_mediador_pix", "label": "Mediador PIX", "colour": "#56ccf2", "staff": True, "hoist": True, "permission_preset": "support"},
                {"key": "ai_supervisor_mm", "label": "Supervisor Middleman", "colour": "#6c63ff", "staff": True, "hoist": True, "permission_preset": "staff"},
            ])
        if scores.get("comunidade") or "comunidade" in text:
            roles.extend([
                {"key": "ai_criador_conteudo", "label": "Criador de Conteudo", "colour": "#bb6bd9", "staff": False, "hoist": True, "permission_preset": "none"},
                {"key": "ai_engajado", "label": "Membro Engajado", "colour": "#00a86b", "staff": False, "hoist": True, "permission_preset": "none"},
            ])
        return roles

    def _fallback_ai_plan(self, description: str, theme: str, scores: dict[str, int]) -> dict:
        text = self._normalize_ai_text(f"{theme} {description}")
        systems = self._infer_ai_systems({}, description, theme, scores)
        categories = [
            {"key": "ai_entrada", "label": "Entrada", "private": False},
            {"key": "ai_staff", "label": "Staff", "private": True},
            {"key": "ai_logs", "label": "Logs", "private": True},
        ]
        if "fivem" in systems:
            categories.extend([
                {"key": "ai_cidade", "label": "Cidade", "private": False},
                {"key": "ai_operacao_city", "label": "Operacao City", "private": False},
            ])
        if "robux" in systems or "stock" in systems:
            categories.extend([
                {"key": "ai_loja", "label": "Loja", "private": False},
                {"key": "ai_atendimento", "label": "Atendimento", "private": False},
            ])
        if "community" in systems or "instagram" in systems or "welcome" in systems:
            categories.extend([
                {"key": "ai_comunidade", "label": "Comunidade", "private": False},
                {"key": "ai_engajamento", "label": "Engajamento", "private": False},
            ])
        roles = self._fallback_role_ideas(text, scores)
        channels = [
            {"key": "ai_inicio", "label": "inicio", "emoji": "🏠", "category": "ai_entrada", "read_only": True},
            {"key": "ai_anuncios", "label": "anuncios", "emoji": "📢", "category": "ai_entrada", "read_only": True},
            {"key": "ai_como_funciona", "label": "como-funciona", "emoji": "📌", "category": "ai_entrada", "read_only": True},
            {"key": "ai_suporte_rapido", "label": "suporte-rapido", "emoji": "🎫", "category": "ai_operacao"},
            {"key": "ai_chat", "label": "chat", "emoji": "💬", "category": "ai_experiencia"},
            {"key": "ai_midia", "label": "midia", "emoji": "📸", "category": "ai_experiencia"},
            {"key": "ai_painel_staff", "label": "painel-staff", "emoji": "🛡️", "category": "ai_staff", "staff_only": True},
            {"key": "ai_logs_operacao", "label": "logs-operacao", "emoji": "📋", "category": "ai_logs", "staff_only": True},
        ]
        if "fivem" in text or scores.get("fivem"):
            channels.extend([
                {"key": "ai_status_city", "label": "status-city", "emoji": "📡", "category": "ai_operacao", "read_only": True},
                {"key": "ai_whitelist_city", "label": "whitelist-city", "emoji": "✅", "category": "ai_operacao"},
                {"key": "ai_fac_recrutamento", "label": "fac-recrutamento", "emoji": "⚔️", "category": "ai_operacao"},
            ])
        if "roblox" in text or "robux" in text or scores.get("roblox"):
            channels.extend([
                {"key": "ai_robux", "label": "robux", "emoji": "💎", "category": "ai_operacao"},
                {"key": "ai_verificacao_grupo", "label": "verificacao-grupo", "emoji": "🔎", "category": "ai_operacao", "read_only": True},
            ])
        channels = [
            item for item in channels
            if item.get("category") not in {"ai_operacao", "ai_experiencia"}
            and item.get("key") not in {
                "ai_como_funciona",
                "ai_suporte_rapido",
                "ai_chat",
                "ai_midia",
                "ai_status_city",
                "ai_whitelist_city",
                "ai_fac_recrutamento",
                "ai_robux",
                "ai_verificacao_grupo",
            }
        ]
        channels.append({"key": "ai_regras", "label": "regras", "emoji": "📜", "category": "ai_entrada", "read_only": True})
        if "tickets" in systems or "middleman" in systems:
            channels.append({"key": "ai_suporte_rapido", "label": "suporte-rapido", "emoji": "🎫", "category": "ai_atendimento" if any(c["key"] == "ai_atendimento" for c in categories) else "ai_entrada"})
        if "community" in systems or "instagram" in systems or "welcome" in systems:
            channels.extend([
                {"key": "ai_chat", "label": "chat", "emoji": "💬", "category": "ai_comunidade"},
                {"key": "ai_midia", "label": "midia", "emoji": "📸", "category": "ai_engajamento"},
            ])
        if "fivem" in systems:
            channels.extend([
                {"key": "ai_status_city", "label": "status-city", "emoji": "📡", "category": "ai_cidade", "read_only": True},
                {"key": "ai_whitelist_city", "label": "whitelist-city", "emoji": "✅", "category": "ai_operacao_city"},
                {"key": "ai_fac_recrutamento", "label": "fac-recrutamento", "emoji": "⚔️", "category": "ai_operacao_city"},
            ])
        if "robux" in systems:
            channels.extend([
                {"key": "ai_robux", "label": "robux", "emoji": "💎", "category": "ai_loja"},
                {"key": "ai_verificacao_grupo", "label": "verificacao-grupo", "emoji": "🔎", "category": "ai_loja", "read_only": True},
            ])
        if "stock" in systems:
            channels.extend([
                {"key": "ai_produtos", "label": "produtos", "emoji": "📦", "category": "ai_loja", "read_only": True},
                {"key": "ai_feedback", "label": "feedback", "emoji": "⭐", "category": "ai_loja"},
            ])

        return {
            "label": f"IA {theme or 'Completo'}",
            "description": f"Plano criado dinamicamente para: {str(theme or description)[:120]}",
            "roles": roles,
            "categories": categories,
            "channels": channels,
            "systems": systems,
        }

    async def _ask_ai_for_plan(self, description: str, theme: str, scores: dict[str, int]) -> dict | None:
        try:
            raw = await chamar_ia(self._ai_json_prompt(description, theme, scores), "AutoSetupServidor")
        except Exception as exc:
            print(f"[AutoSetupIA] Falha ao chamar IA: {exc}")
            return None
        return self._extract_json_object(raw)

    def _normalise_ai_plan(self, plan: dict | None, description: str, theme: str, scores: dict[str, int]) -> tuple[dict, list[str]]:
        plan = plan if isinstance(plan, dict) else self._fallback_ai_plan(description, theme, scores)
        roles: list[str] = []
        categories: list[str] = []
        channels: list[str] = []
        systems = self._infer_ai_systems(plan, description, theme, scores)
        role_specs: dict[str, dict] = {}
        category_specs: dict[str, dict] = {}
        channel_specs: dict[str, dict] = {}
        staff_role_keys = set(STAFF_ROLE_KEYS)

        plan_roles = plan.get("roles") if isinstance(plan.get("roles"), list) else []
        used_role_keys = set(roles)

        def add_role_item(item: dict) -> None:
            if not isinstance(item, dict):
                return
            label = str(item.get("label") or item.get("name") or "").strip()[:80]
            if not label:
                return
            key = self._ai_key("ai_role", item.get("key") or label, used_role_keys)
            raw_permissions = item.get("permissions")
            permission_preset = item.get("permission_preset")
            if not isinstance(raw_permissions, list):
                raw_permissions = None
            role_specs[key] = {
                "label": label,
                "colour": self._colour_value(item.get("colour") or item.get("color")),
                "hoist": bool(item.get("hoist") or item.get("staff")),
                "permissions": raw_permissions,
                "permission_preset": str(permission_preset or ("staff" if item.get("staff") else "none")).strip().lower(),
            }
            roles.append(key)
            if item.get("staff") is True or "staff" in self._normalize_ai_text(label):
                staff_role_keys.add(key)

        existing_role_labels = set()
        for item in plan_roles:
            if not isinstance(item, dict):
                continue
            label_key = self._normalize_ai_text(item.get("label") or item.get("name") or "")
            if not label_key or label_key in existing_role_labels:
                continue
            existing_role_labels.add(label_key)
            add_role_item(item)

        minimum_custom_roles = 8 if len(systems) >= 3 else 6
        for fallback_role in self._fallback_role_ideas(self._normalize_ai_text(f"{theme} {description}"), scores):
            if len(role_specs) >= minimum_custom_roles and plan_roles:
                break
            fallback_label = self._normalize_ai_text(fallback_role.get("label") or "")
            if fallback_label and fallback_label not in existing_role_labels:
                existing_role_labels.add(fallback_label)
                add_role_item(fallback_role)

        used_category_keys = set(categories)
        category_alias: dict[str, str] = {}
        for item in plan.get("categories", []):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or "").strip()[:80]
            if not label:
                continue
            raw_key = str(item.get("key") or label).strip()
            key = self._ai_key("ai_cat", raw_key, used_category_keys)
            category_alias[self._normalize_ai_text(raw_key)] = key
            category_alias[self._normalize_ai_text(label)] = key
            category_specs[key] = {"label": label, "private": bool(item.get("private"))}
            categories.append(key)

        used_channel_keys = set(channels)
        for item in plan.get("channels", []):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or "").strip().lower()[:80]
            if not label:
                continue
            raw_category_value = str(item.get("category") or "").strip()
            raw_category = self._normalize_ai_text(raw_category_value)
            category_key = category_alias.get(raw_category) or (raw_category if raw_category in CATEGORY_SPECS else None)
            if not category_key:
                category_key = self._category_from_raw_ai(
                    raw_category_value,
                    categories,
                    category_specs,
                    category_alias,
                    used_category_keys,
                    private=bool(item.get("staff_only")),
                )
            if not category_key:
                normalized_label = self._normalize_ai_text(label)
                if item.get("staff_only") or "staff" in normalized_label:
                    category_key = "staff"
                elif "log" in normalized_label:
                    category_key = "logs"
                else:
                    category_key = "geral"
            if category_key not in categories and category_key in CATEGORY_SPECS:
                categories.append(category_key)
            key = self._ai_key("ai_ch", item.get("key") or label, used_channel_keys)
            channel_specs[key] = {
                "label": setup_utils.slugify(label),
                "emoji": str(item.get("emoji") or "📌")[:8],
                "category": category_key,
                "read_only": bool(item.get("read_only")),
                "staff_only": bool(item.get("staff_only")),
                "topic": str(item.get("topic") or "")[:1024] or None,
            }
            channels.append(key)

        for system in systems:
            req = AI_SYSTEM_REQUIREMENTS.get(system, {})
            self._append_unique(roles, req.get("roles", []))
            self._append_unique(categories, req.get("categories", []))
            self._append_unique(channels, req.get("channels", []))

        if not categories:
            self._append_unique(categories, ["geral", "staff", "logs"])
        if not channels:
            self._append_unique(channels, ["boas_vindas", "regras", "avisos", "chat", "logs_system"])

        target_channel_count = 28 if self._ai_wants_complete(self._normalize_ai_text(f"{theme} {description}")) else max(12, min(22, len(channels) + 4))
        for raw_key, label, icon, category, read_only in AI_CHANNEL_IDEAS:
            if len(channels) >= target_channel_count:
                break
            if raw_key in used_channel_keys:
                continue
            if category not in categories:
                continue
            if category == "comunidade" and not ({"community", "instagram", "welcome"} & set(systems)):
                continue
            if category == "atendimento" and not ({"tickets", "middleman"} & set(systems)):
                continue
            key = self._ai_key("ai_extra", raw_key, used_channel_keys)
            channel_specs[key] = {
                "label": label,
                "emoji": icon,
                "category": category,
                "read_only": read_only,
                "staff_only": category in {"staff", "logs"},
            }
            channels.append(key)

        if "logs_system" not in channels:
            channels.append("logs_system")
        if "logs" not in categories:
            categories.append("logs")

        system_families = {
            "tickets": "suporte",
            "middleman": "middleman",
            "community": "comunidade",
            "instagram": "comunidade",
            "fivem": "fivem",
            "bateponto": "fivem",
            "robux": "roblox",
            "stock": "loja",
            "security": "security",
            "welcome": "comunidade",
        }
        families = []
        for system in systems:
            family = system_families.get(system)
            if family and family not in families:
                families.append(family)
        if not families:
            families = [family for family, score in scores.items() if score > 0 and family != "security"] or ["comunidade"]
        template = {
            "label": str(plan.get("label") or f"IA {theme or 'Completo'}")[:80],
            "description": str(plan.get("description") or f"Servidor gerado por IA para {theme or 'operacao completa'}")[:300],
            "roles": roles[:45],
            "categories": categories[:40],
            "channels": channels[:50],
            "systems": self._unique_ordered(systems, AI_COMPLETE_SYSTEMS),
            "role_specs": role_specs,
            "category_specs": category_specs,
            "channel_specs": channel_specs,
            "staff_role_keys": list(staff_role_keys),
            "ai_native": True,
        }
        return template, families

    async def _build_ai_template(self, description: str, theme: str = "") -> tuple[str, dict, list[str], dict[str, int]]:
        full_text = f"{theme} {description}"
        scores = self._ai_scores(full_text)
        ai_plan = await self._ask_ai_for_plan(description, theme, scores)
        template, families = self._normalise_ai_plan(ai_plan, description, theme, scores)
        return "ai_native", template, families, scores

    def _ai_pending_doc(self) -> dict:
        data = db.get_document(AI_PENDING_KEY) or {}
        return data if isinstance(data, dict) else {}

    def _save_ai_pending_doc(self, data: dict) -> None:
        db.save_document(AI_PENDING_KEY, data)

    async def _can_manage_target_guild(self, user_id: int, guild: disnake.Guild) -> bool:
        if await perms.check(user_id):
            return True
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None
        permissions = getattr(member, "guild_permissions", None)
        return bool(permissions and (permissions.administrator or permissions.manage_guild))

    def _bot_can_setup_guild(self, guild: disnake.Guild) -> tuple[bool, str]:
        member = guild.me or guild.get_member(self.bot.user.id)
        permissions = getattr(member, "guild_permissions", None)
        if not permissions:
            return False, "Nao consegui ler minhas permissoes neste servidor."
        missing = []
        if not permissions.manage_channels:
            missing.append("Gerenciar Canais")
        if not permissions.manage_roles:
            missing.append("Gerenciar Cargos")
        if missing:
            return False, "Permissoes faltando: " + ", ".join(missing)
        return True, ""

    def _role_spec(self, key: str, template: dict | None = None) -> dict | None:
        custom = (template or {}).get("role_specs") if isinstance(template, dict) else {}
        if isinstance(custom, dict) and isinstance(custom.get(key), dict):
            return custom[key]
        return ROLE_SPECS.get(key)

    def _category_spec(self, key: str, template: dict | None = None) -> dict | None:
        custom = (template or {}).get("category_specs") if isinstance(template, dict) else {}
        if isinstance(custom, dict) and isinstance(custom.get(key), dict):
            return custom[key]
        return CATEGORY_SPECS.get(key)

    def _channel_spec(self, key: str, template: dict | None = None) -> dict | None:
        custom = (template or {}).get("channel_specs") if isinstance(template, dict) else {}
        if isinstance(custom, dict) and isinstance(custom.get(key), dict):
            return custom[key]
        return CHANNEL_SPECS.get(key)

    def _channel_name(self, key: str, template: dict | None = None) -> str:
        cfg = setup_utils.get_config()
        spec = self._channel_spec(key, template) or {"label": key, "emoji": "📌"}
        return setup_utils.channel_name(key, spec["label"], cfg, spec.get("emoji"))

    def _category_name(self, key: str, template: dict | None = None) -> str:
        cfg = setup_utils.get_config()
        spec = self._category_spec(key, template) or {"label": key}
        if key == "logs":
            return str(cfg.get("logs_category") or "╺╸ Logs")[:100]
        separator = str(cfg.get("separator") or setup_utils.DEFAULT_SEPARATOR)
        return f"{separator} {spec['label']}"[:100]

    def _role_name(self, key: str, template: dict | None = None) -> str:
        cfg = setup_utils.get_config()
        spec = self._role_spec(key, template) or {"label": key}
        return setup_utils.role_name(key, spec["label"], cfg)

    async def _can_manage(self, inter: disnake.MessageInteraction) -> bool:
        if await perms.check(inter.user.id):
            return True
        permissions = getattr(inter.user, "guild_permissions", None)
        return bool(permissions and (permissions.administrator or permissions.manage_guild))

    def _panel_rows(self, selected_key: str) -> list[disnake.ui.ActionRow]:
        options = [
            disnake.SelectOption(
                label=tpl["label"],
                value=key,
                description=tpl["description"][:100],
                emoji=_emoji("wand" if key == "complete" else "folder", "settings"),
                default=key == selected_key,
            )
            for key, tpl in TEMPLATES.items()
        ]
        return [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="AutoSetup_TemplateSelect",
                    placeholder="Escolha um template de servidor",
                    options=options,
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Criar com IA", style=disnake.ButtonStyle.blurple, emoji=_emoji("robot", "wand"), custom_id="AutoSetup_AIStart"),
                disnake.ui.Button(label="Aplicar Template", style=disnake.ButtonStyle.green, emoji=_emoji("rocket", "wand"), custom_id="AutoSetup_Apply"),
                disnake.ui.Button(label="Publicar Paineis", style=disnake.ButtonStyle.blurple, emoji=_emoji("announcement", "send"), custom_id="AutoSetup_Publish"),
                disnake.ui.Button(label="Personalizar", style=disnake.ButtonStyle.grey, emoji=_emoji("edit", "settings"), custom_id="AutoSetup_Customize"),
            ),
        ]

    def display_auto_setup_panel(self, inter: disnake.MessageInteraction):
        state = self._get_state(inter.guild.id)
        selected_key = self._template_key(state.get("selected_template"))
        template = self._template(selected_key)
        last_run = state.get("last_run_at") or "Nunca"
        published = len(state.get("published_messages") or {})
        status_lines = [
            f"**Template:** `{template['label']}`",
            f"**Canais:** `{len(template['channels'])}` | **Categorias:** `{len(template['categories'])}` | **Cargos:** `{len(template['roles'])}`",
            f"**Sistemas:** `{', '.join(template['systems'])}`",
            f"**Ultima aplicacao:** `{last_run}`",
            f"**Paineis publicados:** `{published}`",
        ]
        return build_panel_card(
            title=f"{_emoji('wand', 'settings')} Auto Setup Inteligente",
            breadcrumb="Painel > Administracao > Auto Setup",
            description=(
                "Escolha um modelo e o bot monta a estrutura automaticamente: cargos, categorias, canais, "
                "permissoes, logs e paineis publicos dos sistemas escolhidos."
            ),
            status_lines=status_lines,
            rows=self._panel_rows(selected_key),
        )

    async def _handle_ai_description(self, inter: disnake.ModalInteraction) -> None:
        values = getattr(inter, "text_values", None) or getattr(inter, "resolved_values", {})
        description = str(values.get("description") or "").strip()
        theme = str(values.get("theme") or "").strip()
        if len(description) < 12:
            await inter.response.send_message(f"{emoji.wrong} Descreva melhor como voce quer o servidor.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        request_id, template, families, scores = await self._build_ai_template(description, theme)
        request_id = f"{request_id}_{secrets.token_hex(3)}"
        pending = self._ai_pending_doc()
        pending[request_id] = {
            "user_id": str(inter.user.id),
            "source_guild_id": str(inter.guild.id) if inter.guild else "",
            "description": description,
            "theme": theme,
            "template": template,
            "families": families,
            "scores": scores,
            "created_at": _now(),
        }
        pending = dict(list(pending.items())[-100:])
        self._save_ai_pending_doc(pending)

        families_text = ", ".join(AI_FAMILY_LABELS.get(f, f.title()) for f in families)
        category_preview = ", ".join(self._category_name(key, template) for key in template["categories"][:8])
        channel_preview = ", ".join(self._channel_name(key, template) for key in template["channels"][:10])
        role_preview = ", ".join(self._role_name(key, template) for key in template["roles"][:8])
        preview = (
            f"## {_emoji('robot', 'wand')} Servidor com IA\n"
            f"-# Auto Setup > IA > Plano gerado\n\n"
            f"**Tipo detectado:** `{families_text}`\n"
            f"**Plano IA:** `{template['label']}`\n"
            f"**Canais:** `{len(template['channels'])}` | **Categorias:** `{len(template['categories'])}` | **Cargos:** `{len(template['roles'])}`\n"
            f"**Sistemas:** `{', '.join(template['systems']) or 'nenhum'}`\n\n"
            f"**Categorias geradas:** `{category_preview or 'nenhuma'}`\n"
            f"**Canais principais:** `{channel_preview or 'nenhum'}`\n"
            f"**Cargos principais:** `{role_preview or 'nenhum'}`\n\n"
            "Se o bot ainda nao estiver no servidor, adicione o **Lyon IA** primeiro. "
            "Depois informe o ID do servidor para eu identificar e aplicar o processo.\n\n"
            "**Recriacao limpa:** ao confirmar, os canais e categorias atuais do servidor escolhido serao apagados e recriados pela IA."
        )
        await inter.followup.send(
            components=[
                disnake.ui.Container(
                    disnake.ui.TextDisplay(preview[:3900]),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    disnake.ui.ActionRow(
                        self._system_ia_invite_button(),
                        disnake.ui.Button(label="Informar ID", style=disnake.ButtonStyle.green, emoji=_emoji("plus", "wand"), custom_id=f"AutoSetup_AIApply:{request_id}"),
                        disnake.ui.Button(label="Cancelar", style=disnake.ButtonStyle.grey, emoji=_emoji("wrong", "wrong"), custom_id=f"AutoSetup_AICancel:{request_id}"),
                    ),
                    accent_colour=disnake.Colour(0x0082FF),
                )
            ],
            ephemeral=True,
            flags=self._flags(),
        )

    async def _handle_ai_guild(self, inter: disnake.ModalInteraction, request_id: str) -> None:
        await inter.response.defer(ephemeral=True)
        pending = self._ai_pending_doc()
        request = pending.get(request_id)
        if not request or str(request.get("user_id")) != str(inter.user.id):
            await inter.followup.send(f"{emoji.wrong} Esse processo de IA expirou ou nao pertence a voce.", ephemeral=True)
            return

        values = getattr(inter, "text_values", None) or getattr(inter, "resolved_values", {})
        raw_guild_id = str(values.get("guild_id") or "").replace(" ", "").strip()
        if not raw_guild_id.isdigit():
            await inter.followup.send(f"{emoji.wrong} Informe um ID de servidor valido.", ephemeral=True)
            return

        target_guild = self.bot.get_guild(int(raw_guild_id))
        if target_guild is None:
            await inter.followup.send(
                components=[
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(
                            f"{emoji.wrong} **Nao encontrei esse servidor.**\n\n"
                            "O **Lyon IA** precisa estar dentro do servidor para eu conseguir identificar e montar a estrutura.\n"
                            f"ID informado: `{raw_guild_id}`\n\n"
                            "Clique no botao abaixo, adicione o bot no servidor e depois informe o ID novamente."
                        ),
                        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                        disnake.ui.ActionRow(self._system_ia_invite_button(raw_guild_id)),
                        accent_colour=disnake.Colour(0x0082FF),
                    )
                ],
                flags=self._flags(),
                ephemeral=True,
            )
            return

        if not await self._can_manage_target_guild(inter.user.id, target_guild):
            await inter.followup.send(f"{emoji.wrong} Voce precisa ter permissao de gerenciar esse servidor.", ephemeral=True)
            return

        can_setup, reason = self._bot_can_setup_guild(target_guild)
        if not can_setup:
            await inter.followup.send(f"{emoji.wrong} Nao consigo montar esse servidor ainda: {reason}", ephemeral=True)
            return

        template = request.get("template") if isinstance(request.get("template"), dict) else TEMPLATES["complete"]
        reset_confirm = self._normalize_ai_text(values.get("reset_confirm") or "")
        if reset_confirm != "recriar":
            await inter.followup.send(f"{emoji.wrong} Para recriar o servidor com IA, digite `RECRIAR` no campo de confirmacao.", ephemeral=True)
            return
        publish = str(values.get("publish") or "sim").strip().lower() not in {"nao", "não", "n", "no", "0"}
        template_key = str(request_id).split("_", 1)[0][:32] or "ai"

        try:
            result = await self._apply_template(
                inter,
                template_key,
                publish=publish,
                target_guild=target_guild,
                template_override=template,
                ai_description=request.get("description") or "",
                reset_channels=True,
            )
        except disnake.Forbidden:
            await inter.followup.send(f"{emoji.wrong} Nao tenho permissao para criar cargos/canais nesse servidor.", ephemeral=True)
            return
        except Exception as exc:
            await inter.followup.send(f"{emoji.wrong} Nao consegui criar o servidor com IA: `{exc}`", ephemeral=True)
            return

        pending.pop(request_id, None)
        self._save_ai_pending_doc(pending)
        self._save_ai_run(inter.user.id, target_guild.id, template, request, result)

        lines = [
            f"{emoji.correct} Servidor com IA aplicado em **{target_guild.name}** (`{target_guild.id}`).",
            f"Plano IA: `{template.get('label', 'IA')}`",
            f"Canais/categorias antigos removidos: `{len(result.get('reset_deleted', []))}`",
            f"Canais criados: `{len(result['created_channels'])}`",
            f"Categorias criadas: `{len(result['created_categories'])}`",
            f"Cargos criados: `{len(result['created_roles'])}`",
            f"Paineis publicados/atualizados: `{len(result['published'])}`",
        ]
        if result.get("reset_failed"):
            lines.append(f"Falhas ao remover: `{len(result['reset_failed'])}`")
        if result["published"]:
            lines.append("\n" + "\n".join(f"- {item}" for item in result["published"][:8]))
        await inter.followup.send("\n".join(lines), ephemeral=True)

    def _role_overwrites(self, guild: disnake.Guild, role_map: dict[str, disnake.Role], template: dict | None = None) -> list[disnake.Role]:
        roles = []
        staff_keys = set(STAFF_ROLE_KEYS)
        if isinstance(template, dict):
            staff_keys.update(str(key) for key in template.get("staff_role_keys", []) if key)
        for key in staff_keys:
            role = role_map.get(key)
            if role and role not in roles:
                roles.append(role)
        return roles

    def _private_overwrites(self, guild: disnake.Guild, staff_roles: list[disnake.Role]) -> dict:
        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(view_channel=False),
        }
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

    def _channel_overwrites(self, guild: disnake.Guild, spec: dict, staff_roles: list[disnake.Role]) -> dict:
        if spec.get("staff_only"):
            return self._private_overwrites(guild, staff_roles)
        if spec.get("read_only"):
            overwrites = {
                guild.default_role: disnake.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                )
            }
            if guild.me:
                overwrites[guild.me] = disnake.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                )
            for role in staff_roles:
                overwrites[role] = disnake.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                )
            return overwrites
        return {}

    def _role_permissions(self, spec: dict) -> disnake.Permissions | None:
        raw = spec.get("permissions")
        preset = spec.get("permission_preset")
        names = []
        if isinstance(raw, list):
            names = [str(item).strip() for item in raw if item]
        elif isinstance(raw, str) and raw.strip().lower() in AI_PERMISSION_PRESETS:
            names = AI_PERMISSION_PRESETS[raw.strip().lower()]
        elif isinstance(raw, str):
            names = [raw]
        elif isinstance(preset, str):
            names = AI_PERMISSION_PRESETS.get(preset.strip().lower(), [])

        if not names:
            return None

        permissions = disnake.Permissions.none()
        for name in names:
            clean_name = str(name or "").strip().lower().replace(" ", "_").replace("-", "_")
            if clean_name and hasattr(permissions, clean_name):
                setattr(permissions, clean_name, True)
        return permissions

    async def _ensure_roles(self, guild: disnake.Guild, role_keys: list[str], reason: str, template: dict | None = None) -> tuple[dict, list]:
        role_map = {}
        created = []
        for key in role_keys:
            spec = self._role_spec(key, template)
            if not spec:
                continue
            name = self._role_name(key, template)
            existing = disnake.utils.get(guild.roles, name=name)
            if existing:
                role_map[key] = existing
                continue
            create_kwargs = {
                "name": name,
                "colour": disnake.Colour(spec.get("colour", 0x5865F2)),
                "hoist": bool(spec.get("hoist")),
                "mentionable": True,
                "reason": reason,
            }
            permissions = self._role_permissions(spec)
            if permissions is not None:
                create_kwargs["permissions"] = permissions
            role = await guild.create_role(**create_kwargs)
            role_map[key] = role
            created.append(role)
        return role_map, created

    async def _ensure_categories(self, guild: disnake.Guild, category_keys: list[str], role_map: dict, reason: str, template: dict | None = None) -> tuple[dict, list]:
        categories = {}
        created = []
        staff_roles = self._role_overwrites(guild, role_map, template)
        for key in category_keys:
            spec = self._category_spec(key, template)
            if not spec:
                continue
            name = self._category_name(key, template)
            existing = disnake.utils.get(guild.categories, name=name)
            if existing:
                categories[key] = existing
                continue
            overwrites = self._private_overwrites(guild, staff_roles) if spec.get("private") else {}
            category = await guild.create_category(name=name, overwrites=overwrites, reason=reason)
            categories[key] = category
            created.append(category)
        return categories, created

    async def _ensure_channels(self, guild: disnake.Guild, channel_keys: list[str], categories: dict, role_map: dict, reason: str, template: dict | None = None) -> tuple[dict, list]:
        channel_map = {}
        created = []
        staff_roles = self._role_overwrites(guild, role_map, template)

        for key in channel_keys:
            spec = self._channel_spec(key, template)
            if not spec:
                continue
            name = self._channel_name(key, template)
            category = categories.get(spec.get("category"))
            existing = None
            if category:
                existing = disnake.utils.get(category.text_channels, name=name)
            existing = existing or disnake.utils.get(guild.text_channels, name=name)
            if existing:
                channel_map[key] = existing
                continue

            overwrites = self._channel_overwrites(guild, spec, staff_roles)
            channel = await guild.create_text_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                topic=spec.get("topic"),
                reason=reason,
            )
            channel_map[key] = channel
            created.append(channel)
        return channel_map, created

    async def _wipe_guild_channels(self, guild: disnake.Guild, reason: str) -> dict:
        deleted = []
        failed = []
        regular_channels = [channel for channel in guild.channels if not isinstance(channel, disnake.CategoryChannel)]
        categories = [channel for channel in guild.channels if isinstance(channel, disnake.CategoryChannel)]

        for channel in sorted(regular_channels, key=lambda item: getattr(item, "position", 0), reverse=True):
            try:
                name = getattr(channel, "name", str(channel.id))
                await channel.delete(reason=f"{reason} - recriacao limpa IA")
                deleted.append(name)
            except Exception as exc:
                failed.append(f"{getattr(channel, 'name', channel.id)}: {exc}")

        for category in sorted(categories, key=lambda item: getattr(item, "position", 0), reverse=True):
            try:
                name = getattr(category, "name", str(category.id))
                await category.delete(reason=f"{reason} - recriacao limpa IA")
                deleted.append(name)
            except Exception as exc:
                failed.append(f"{getattr(category, 'name', category.id)}: {exc}")

        return {"deleted": deleted, "failed": failed}

    def _channel_ids(self, channel_map: dict[str, disnake.TextChannel]) -> dict:
        return {key: str(channel.id) for key, channel in channel_map.items() if channel}

    def _role_ids(self, role_map: dict[str, disnake.Role]) -> dict:
        return {key: str(role.id) for key, role in role_map.items() if role}

    def _category_ids(self, categories: dict[str, disnake.CategoryChannel]) -> dict:
        return {key: str(category.id) for key, category in categories.items() if category}

    def _resolve_channels_from_state(self, guild: disnake.Guild, state: dict) -> dict:
        resolved = {}
        for key, raw_id in (state.get("last_channels") or {}).items():
            try:
                channel = guild.get_channel(int(raw_id))
            except Exception:
                channel = None
            if isinstance(channel, disnake.TextChannel):
                resolved[key] = channel
        return resolved

    def _resolve_categories_from_state(self, guild: disnake.Guild, state: dict) -> dict:
        resolved = {}
        for key, raw_id in (state.get("last_categories") or {}).items():
            try:
                channel = guild.get_channel(int(raw_id))
            except Exception:
                channel = None
            if isinstance(channel, disnake.CategoryChannel):
                resolved[key] = channel
        return resolved

    def _resolve_roles_from_state(self, guild: disnake.Guild, state: dict) -> dict:
        resolved = {}
        for key, raw_id in (state.get("last_roles") or {}).items():
            try:
                role = guild.get_role(int(raw_id))
            except Exception:
                role = None
            if role:
                resolved[key] = role
        return resolved

    def _update_canais_doc(self, channel_map: dict[str, disnake.TextChannel]) -> None:
        guild = next((channel.guild for channel in channel_map.values() if channel), None)
        canais = load_guild_channels(guild)
        mapping = {
            "loja": "canal_de_evento_de_compras",
            "boas_vindas": "canal_de_boas_vindas",
            "feedback": "canal_de_feedback",
            "logs_system": "canal_de_logs_do_sistema",
            "logs_sales": "canal_de_logs_de_pedidos",
            "logs_tickets": "canal_de_logs_de_tickets",
            "logs_middleman": "canal_de_logs_de_middleman",
            "logs_fivem": "canal_de_logs_de_fivem",
            "logs_robux": "canal_de_logs_de_robux",
            "logs_community": "canal_de_logs_de_comunidade",
            "logs_scam": "canal_de_logs_de_anti_falso",
        }
        changed = False
        for local_key, doc_key in mapping.items():
            channel = channel_map.get(local_key)
            if channel:
                canais[doc_key] = channel.id
                changed = True
        if changed:
            save_guild_channels(guild, canais)

    def _update_roles_docs(self, role_map: dict[str, disnake.Role]) -> None:
        cargos = db.get_document("cargos") or {}
        if role_map.get("support"):
            cargos["cargo_suporte"] = role_map["support"].id
        if role_map.get("client"):
            cargos["cargo_cliente"] = role_map["client"].id
        if role_map.get("staff"):
            cargos["cargo_staff"] = role_map["staff"].id
        if cargos:
            db.save_document("cargos", cargos)

    def _ticket_defaults(self) -> dict:
        return {
            "close_message": "Seu ticket `{channel_name}` foi fechado por {autor_mention}.",
            "close_message_reason": "Seu ticket `{channel_name}` foi fechado por {autor_mention}.\n**Motivo:** {reason}",
            "notify_message_staff_to_user": "Olá {user_mention}, a equipe está aguardando sua resposta no ticket `{channel_name}`.",
            "notify_message_user_to_staff": "{user_mention} está solicitando atenção no ticket `{channel_name}`.",
            "add_user_message": "{alvo_mention} foi adicionado a este ticket por {autor_mention}.",
            "add_user_dm_message": "Olá {alvo_mention}, você foi adicionado ao ticket `{channel_name}` por {autor_mention}.",
            "remove_user_message": "{alvo_mention} foi removido deste ticket por {autor_mention}.",
            "remove_user_dm_message": "Olá {alvo_mention}, você foi removido do ticket `{channel_name}` por {autor_mention}.",
            "assume_message": "{autor_mention} assumiu o atendimento deste ticket.",
            "assume_dm_message": "Olá {user_mention}, o atendente {autor_mention} assumiu seu ticket `{channel_name}`.",
            "transfer_message": "O ticket foi transferido por {autor_mention}.",
            "create_call_message": "Uma call de voz foi iniciada para este ticket por {autor_mention}.",
            "create_call_dm_message": "Olá! Uma call de voz foi criada para o seu ticket `{channel_name}`.",
            "request_call_message": "O usuário {autor_mention} solicitou a criação de uma call.",
        }

    def _configure_ticket(self, template_key: str, channel_map: dict, categories: dict, role_map: dict) -> str | None:
        channel = channel_map.get("support_panel")
        category = categories.get("tickets") or categories.get("atendimento")
        if not channel or not category:
            return None

        panel_id = f"{TICKET_PANEL_PREFIX}{template_key}"
        staff_ids = [role.id for key, role in role_map.items() if key in {"manager", "staff", "support"}]
        config = db.get_document("tickets_config") or {}
        panels = config.setdefault("panels", {})
        existing_message = panels.get(panel_id, {}).get("message_id")
        panels[panel_id] = {
            "name": "Atendimento",
            "messages": self._ticket_defaults(),
            "options": [
                {
                    "id": "suporte",
                    "name": "Abrir Ticket",
                    "description": "Clique para falar com a equipe.",
                    "emoji": getattr(emoji, "ticket", ""),
                    "roles": {"mention": staff_ids, "allowed": [], "forbidden": []},
                    "open_message": {
                        "style": "container",
                        "container": {"content": "Seu ticket foi aberto. Aguarde um atendente assumir o atendimento.", "color": ""},
                    },
                }
            ],
            "button": {"label": "Abrir Ticket", "style": "green", "emoji": getattr(emoji, "ticket", "")},
            "roles": {"mention": staff_ids, "allowed": [], "forbidden": []},
            "channel_id": channel.id,
            "category_id": category.id,
            "message_id": existing_message,
            "enabled": True,
            "message_style": "container",
            "has_pending_changes": False,
            "container": {
                "content": (
                    "## Atendimento\n"
                    "Abra um ticket para suporte, compras, dúvidas ou problemas.\n\n"
                    "- Explique o que precisa com clareza.\n"
                    "- Evite chamar a equipe no privado.\n"
                    "- Aguarde um atendente assumir."
                ),
                "color": "",
            },
            "mode": "channel",
            "office_hours": {"enabled": False, "start_time": "00:00", "end_time": "23:59", "off_days": [], "message": ""},
            "preferences": {
                "transcripts": {"send_on_close": True},
                "auto_close": {"user_left": {"enabled": True}},
                "team_setup": {"disabled_buttons": []},
                "member_setup": {"disabled_buttons": []},
            },
        }
        db.save_document("tickets_config", config)
        return panel_id

    def _configure_middleman(self, guild_id: int, channel_map: dict, categories: dict, role_map: dict) -> None:
        if not channel_map.get("middleman_panel"):
            return
        key = f"middleman_{guild_id}"
        data = db.get_document(key) or {}
        data.setdefault("cases", {})
        data.update(
            {
                "enabled": True,
                "category_id": int((categories.get("middleman") or categories.get("tickets")).id),
                "logs_channel_id": int((channel_map.get("logs_middleman") or channel_map.get("logs_system")).id),
                "staff_roles": [
                    role.id for key_name, role in role_map.items()
                    if key_name in {"manager", "staff", "support", "mediator"}
                ],
                "service_fee": data.get("service_fee", 0.0),
            }
        )
        db.save_document(key, data)

    def _configure_community(self, guild_id: int, channel_map: dict, role_map: dict) -> None:
        if not channel_map.get("community_hub"):
            return
        setup = setup_utils.get_config()
        key = f"comunidade_{guild_id}"
        cfg = db.get_document(key) or {}
        channels = cfg.setdefault("channels", {})
        channel_pairs = {
            "hub": "community_hub",
            "rules": "regras",
            "announcements": "avisos",
            "chat": "chat",
            "introductions": "apresentacoes",
            "suggestions": "sugestoes",
            "events": "eventos",
            "instagram": "instagram_feed",
            "social": "redes_sociais",
            "partnerships": "parcerias",
            "creators": "criadores",
            "logs": "logs_community",
        }
        for dest, local_key in channel_pairs.items():
            channel = channel_map.get(local_key)
            if channel:
                channels[dest] = str(channel.id)

        cfg.update(
            {
                "enabled": True,
                "separator": setup.get("separator") or "╺╸",
                "channel_pattern": setup.get("channel_pattern") or "{emoji}{separator}{name}",
                "role_pattern": setup.get("role_pattern") or "{name}",
                "hub_channel": str(channel_map["community_hub"].id),
                "logs_channel": str((channel_map.get("logs_community") or channel_map.get("logs_system")).id),
                "channels": channels,
                "roles": {
                    "member": str(role_map["member"].id) if role_map.get("member") else "",
                    "verified": str(role_map["verified"].id) if role_map.get("verified") else "",
                    "creator": str(role_map["creator"].id) if role_map.get("creator") else "",
                    "partner": str(role_map["partner"].id) if role_map.get("partner") else "",
                    "community_staff": str((role_map.get("staff") or role_map.get("manager")).id) if (role_map.get("staff") or role_map.get("manager")) else "",
                },
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
                "hub_title": "Central da Comunidade",
                "hub_description": "Use os botões abaixo para se apresentar, enviar sugestões, acompanhar eventos e interagir com a comunidade.",
                "last_structure_at": _now(),
            }
        )
        db.save_document(key, cfg)

    def _configure_social(self, channel_map: dict) -> None:
        social = self.bot.get_cog("SocialLyonsPanel")
        if social:
            try:
                data = social.load()
            except Exception:
                data = db.obter(SOCIAL_DATA_PATH)
        else:
            data = db.obter(SOCIAL_DATA_PATH)

        if not isinstance(data, dict):
            data = {}
        systems = data.setdefault("systems", {})

        instagram = systems.setdefault("instagram", {})
        if channel_map.get("instagram_feed"):
            instagram.update(
                {
                    "enabled": True,
                    "title": "Instagram da Comunidade",
                    "description": "Compartilhe fotos e vídeos com a comunidade. Envie uma mídia no canal ou use o botão para publicar no feed.",
                    "button_label": "Abrir Instagram",
                    "channel_id": str(channel_map["instagram_feed"].id),
                }
            )

        engagement = systems.setdefault("engagement", {})
        if channel_map.get("community_hub"):
            engagement.setdefault("title", "Engajamento da Comunidade")
            engagement.setdefault("description", "Registre sua participação nas ações da comunidade.")
            engagement["enabled"] = True
            engagement["channel_id"] = str(channel_map["community_hub"].id)

        db.salvar(SOCIAL_DATA_PATH, data)

    def _configure_fivem(self, channel_map: dict, role_map: dict) -> None:
        if not channel_map.get("fivem_panel"):
            return
        cog = self.bot.get_cog("FiveMLyonPanel")
        data = cog.load() if cog else db.obter(FIVEM_DATA_PATH)
        if not isinstance(data, dict):
            data = {}
        data.update(
            {
                "enabled": True,
                "city_name": data.get("city_name") or "SYSTEM CITY",
                "panel_channel_id": str(channel_map["fivem_panel"].id),
                "log_channel_id": str((channel_map.get("logs_fivem") or channel_map.get("logs_system")).id),
                "staff_role_id": str((role_map.get("fivem_staff") or role_map.get("staff") or role_map.get("manager")).id),
                "whitelist_role_id": str(role_map["fivem_whitelist"].id) if role_map.get("fivem_whitelist") else "",
                "panel_title": data.get("panel_title") or "PLANO FIVEM - SYSTEM CITY",
                "panel_description": data.get("panel_description") or (
                    "OPERAÇÃO DE CIDADE EFICIENTE E ESCALÁVEL\n\n"
                    "Whitelist, facções, recrutamento, bate ponto staff, status do servidor e logs operacionais."
                ),
            }
        )
        data.setdefault("linked_ids", {})
        data.setdefault("whitelist", {})
        data.setdefault("factions", {})
        data.setdefault("faction_requests", {})
        data.setdefault("recruitment_requests", {})
        data.setdefault("staff_sessions", {})
        data.setdefault("staff_time_records", [])
        data.setdefault("cache", {"online": 0, "max": 0, "hostname": "", "players": [], "error": ""})
        if cog:
            cog.save(data)
        else:
            db.salvar(FIVEM_DATA_PATH, data)

    def _configure_bateponto(self, channel_map: dict, role_map: dict) -> None:
        channel = channel_map.get("bateponto_panel") or channel_map.get("fivem_staff_point")
        if not channel:
            return
        cog = self.bot.get_cog("BatePontoPanel")
        data = cog.load() if cog else db.obter(BATEPONTO_DATA_PATH)
        if not isinstance(data, dict):
            data = {}
        data.update(
            {
                "enabled": True,
                "panel_channel_id": str(channel.id),
                "log_channel_id": str((channel_map.get("logs_fivem") or channel_map.get("logs_system")).id),
                "staff_role_id": str((role_map.get("staff") or role_map.get("fivem_staff") or role_map.get("manager")).id),
                "panel_title": "BATE PONTO",
                "panel_description": "Controle de jornada da equipe com início, encerramento, cancelamento e logs automáticos.",
            }
        )
        data.setdefault("active_sessions", {})
        data.setdefault("records", [])
        if cog:
            cog.save(data)
        else:
            db.salvar(BATEPONTO_DATA_PATH, data)

    def _configure_robux(self, channel_map: dict, categories: dict) -> None:
        if not channel_map.get("robux_panel"):
            return
        config = db.get_document("robux_config") or {}
        config.update(
            {
                "enabled": True,
                "public_channel_id": int(channel_map["robux_panel"].id),
                "calculator_channel_id": int(channel_map["robux_panel"].id),
                "log_channel_id": int((channel_map.get("logs_robux") or channel_map.get("logs_system")).id),
                "category_id": int((categories.get("roblox") or categories.get("tickets")).id),
                "group_verification_enabled": bool(config.get("group_id")),
                "group_min_days": int(config.get("group_min_days") or 14),
                "group_block_orders": True,
            }
        )
        db.save_document("robux_config", config)

    def _configure_safety(self, channel_map: dict, role_map: dict) -> None:
        log_channel = channel_map.get("logs_scam") or channel_map.get("logs_system")
        staff_ids = [role.id for key, role in role_map.items() if key in STAFF_ROLE_KEYS]
        if log_channel:
            antifraud = db.get_document("antifraud_config") or {}
            antifraud.update({"enabled": True, "log_channel_id": int(log_channel.id)})
            db.save_document("antifraud_config", antifraud)

            scam = db.get_document("scam_detector_config") or {}
            scam.update(
                {
                    "enabled": True,
                    "monitor_tickets": True,
                    "monitor_middleman": True,
                    "log_channel_id": int(log_channel.id),
                    "staff_role_ids": staff_ids,
                }
            )
            db.save_document("scam_detector_config", scam)

        mod_log = channel_map.get("logs_system")
        if mod_log:
            moderation = db.get_document("moderacao_config") or {}
            moderation.update({"enabled": True, "logs_channel_id": int(mod_log.id)})
            if role_map.get("staff"):
                moderation["moderator_role_id"] = int(role_map["staff"].id)
            db.save_document("moderacao_config", moderation)

    def _configure_misc(self, channel_map: dict, role_map: dict) -> None:
        welcome_channel = channel_map.get("boas_vindas")
        if welcome_channel:
            db.save_document(
                "boasvindas_config",
                {
                    "enabled": True,
                    "channel_id": int(welcome_channel.id),
                    "message": "Bem-vindo {user} ao servidor {server}! Leia as regras e aproveite a comunidade.",
                },
            )

        stock_log = channel_map.get("logs_sales") or channel_map.get("logs_system")
        if stock_log:
            stock = db.get_document("stock_config") or {}
            stock.update(
                {
                    "enabled": True,
                    "restock_channel_id": int(stock_log.id),
                    "logs_channel_id": int(stock_log.id),
                    "mention_role_id": int((role_map.get("staff") or role_map.get("manager")).id) if (role_map.get("staff") or role_map.get("manager")) else "everyone",
                }
            )
            db.save_document("stock_config", stock)

        feedback_channel = channel_map.get("feedback")
        if feedback_channel:
            feedback = db.get_document("feedback_monitor") or {}
            feedback["logs_channel_id"] = int(feedback_channel.id)
            feedback.setdefault("feedbacks", [])
            db.save_document("feedback_monitor", feedback)

    def _configure_systems(self, guild_id: int, template_key: str, template: dict, channel_map: dict, categories: dict, role_map: dict) -> str | None:
        self._update_canais_doc(channel_map)
        self._update_roles_docs(role_map)

        panel_id = None
        systems = set(template.get("systems", []))
        if "tickets" in systems:
            panel_id = self._configure_ticket(template_key, channel_map, categories, role_map)
        if "middleman" in systems:
            self._configure_middleman(guild_id, channel_map, categories, role_map)
        if "community" in systems:
            self._configure_community(guild_id, channel_map, role_map)
        if "instagram" in systems:
            self._configure_social(channel_map)
        if "fivem" in systems:
            self._configure_fivem(channel_map, role_map)
        if "bateponto" in systems:
            self._configure_bateponto(channel_map, role_map)
        if "robux" in systems:
            self._configure_robux(channel_map, categories)
        if "security" in systems:
            self._configure_safety(channel_map, role_map)
        if "stock" in systems or "welcome" in systems:
            self._configure_misc(channel_map, role_map)
        return panel_id

    async def _send_or_edit_panel(self, state: dict, panel_key: str, channel: disnake.TextChannel, components: list, *, content: str | None = None):
        published = state.setdefault("published_messages", {})
        previous = published.get(panel_key) or {}
        message = None
        if str(previous.get("channel_id") or "") == str(channel.id) and str(previous.get("message_id") or "").isdigit():
            try:
                message = await channel.fetch_message(int(previous["message_id"]))
            except Exception:
                message = None

        if message:
            await message.edit(content=content, embed=None, components=components, flags=self._flags())
            action = "atualizado"
        else:
            message = await channel.send(content=content, components=components, flags=self._flags())
            action = "publicado"

        published[panel_key] = {"channel_id": str(channel.id), "message_id": str(message.id), "updated_at": _now()}
        return action, message

    async def _publish_ticket_panel(self, state: dict, template_key: str, panel_id: str, channel: disnake.TextChannel) -> str:
        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"## {_emoji('ticket', 'ticket')} Atendimento\n"
                    "Abra um ticket para falar com a equipe de forma organizada e segura."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Abrir Ticket",
                        style=disnake.ButtonStyle.green,
                        emoji=_emoji("ticket", "mail2"),
                        custom_id=f"create_ticket_{panel_id}",
                    )
                ),
                accent_colour=disnake.Colour.green(),
            )
        ]
        action, message = await self._send_or_edit_panel(state, f"ticket:{template_key}", channel, components)
        config = db.get_document("tickets_config") or {}
        if panel_id in config.get("panels", {}):
            config["panels"][panel_id]["message_id"] = message.id
            config["panels"][panel_id]["channel_id"] = channel.id
            db.save_document("tickets_config", config)
        return f"Ticket {action} em {channel.mention}"

    async def _publish_template_panels(
        self,
        guild: disnake.Guild,
        template_key: str,
        template: dict,
        state: dict,
        channel_map: dict[str, disnake.TextChannel],
        ticket_panel_id: str | None = None,
    ) -> list[str]:
        systems = set(template.get("systems", []))
        published = []

        if "tickets" in systems:
            ticket_panel_id = ticket_panel_id or f"{TICKET_PANEL_PREFIX}{template_key}"
            channel = channel_map.get("support_panel")
            if channel:
                published.append(await self._publish_ticket_panel(state, template_key, ticket_panel_id, channel))

        if "middleman" in systems and channel_map.get("middleman_panel"):
            middleman = self.bot.get_cog("MiddlemanPanel")
            components = middleman._build_public_panel(guild.id) if middleman else [
                disnake.ui.Container(
                    disnake.ui.TextDisplay("## Middleman\nAbra uma solicitação de intermediação segura."),
                    disnake.ui.ActionRow(disnake.ui.Button(label="Solicitar Middleman", style=disnake.ButtonStyle.green, emoji=_emoji("shield"), custom_id="Middleman_Request")),
                    accent_colour=disnake.Colour.blue(),
                )
            ]
            action, _ = await self._send_or_edit_panel(state, f"middleman:{template_key}", channel_map["middleman_panel"], components)
            published.append(f"Middleman {action} em {channel_map['middleman_panel'].mention}")

        if "community" in systems and channel_map.get("community_hub"):
            comunidade = self.bot.get_cog("Comunidade")
            components = comunidade._hub_components(guild.id) if comunidade else [
                disnake.ui.Container(disnake.ui.TextDisplay("## Central da Comunidade\nUse este canal como hub da comunidade."), accent_colour=disnake.Colour.blurple())
            ]
            action, message = await self._send_or_edit_panel(state, f"community:{template_key}", channel_map["community_hub"], components)
            cfg = db.get_document(f"comunidade_{guild.id}") or {}
            cfg["last_hub_message"] = str(message.id)
            db.save_document(f"comunidade_{guild.id}", cfg)
            published.append(f"Comunidade {action} em {channel_map['community_hub'].mention}")

        if "instagram" in systems and channel_map.get("instagram_feed"):
            social = self.bot.get_cog("SocialLyonsPanel")
            if social:
                components = social._public_components("instagram")
            else:
                components = [
                    disnake.ui.Container(
                        disnake.ui.TextDisplay("## Instagram da Comunidade\nCompartilhe fotos e vídeos com o público."),
                        disnake.ui.ActionRow(disnake.ui.Button(label="Enviar Foto/Video", style=disnake.ButtonStyle.green, emoji=_emoji("image"), custom_id="Social_Public_instagram")),
                        accent_colour=disnake.Colour.blurple(),
                    )
                ]
            action, _ = await self._send_or_edit_panel(state, f"instagram:{template_key}", channel_map["instagram_feed"], components)
            if social:
                social.update_system("instagram", {"last_published_at": _now(), "channel_id": str(channel_map["instagram_feed"].id)})
            published.append(f"Instagram {action} em {channel_map['instagram_feed'].mention}")

        if "fivem" in systems and channel_map.get("fivem_panel"):
            fivem = self.bot.get_cog("FiveMLyonPanel")
            components = fivem._public_components() if fivem else [
                disnake.ui.Container(disnake.ui.TextDisplay("## FiveM\nWhitelist, status, facções e recrutamento."), accent_colour=disnake.Colour.blue())
            ]
            action, _ = await self._send_or_edit_panel(state, f"fivem:{template_key}", channel_map["fivem_panel"], components)
            if fivem:
                fivem.update({"last_published_at": _now(), "panel_channel_id": str(channel_map["fivem_panel"].id)})
            published.append(f"FiveM {action} em {channel_map['fivem_panel'].mention}")

        if "bateponto" in systems:
            channel = channel_map.get("bateponto_panel") or channel_map.get("fivem_staff_point")
            if channel:
                bateponto = self.bot.get_cog("BatePontoPanel")
                components = bateponto._public_components() if bateponto else [
                    disnake.ui.Container(disnake.ui.TextDisplay("## Bate Ponto\nInicie, encerre ou cancele seu ponto."), accent_colour=disnake.Colour.green())
                ]
                action, _ = await self._send_or_edit_panel(state, f"bateponto:{template_key}", channel, components)
                if bateponto:
                    bateponto.update({"last_published_at": _now(), "panel_channel_id": str(channel.id)})
                published.append(f"Bate ponto {action} em {channel.mention}")

        if "robux" in systems and channel_map.get("robux_panel"):
            robux = self.bot.get_cog("RobuxPanel")
            components = robux._public_panel_components() if robux else [
                disnake.ui.Container(disnake.ui.TextDisplay("## Robux\nCalcule valores e abra pedidos de Robux."), accent_colour=disnake.Colour.green())
            ]
            action, _ = await self._send_or_edit_panel(state, f"robux:{template_key}", channel_map["robux_panel"], components)
            published.append(f"Robux {action} em {channel_map['robux_panel'].mention}")

        return published

    async def _apply_template(
        self,
        inter: disnake.MessageInteraction,
        template_key: str,
        *,
        publish: bool = True,
        target_guild: disnake.Guild | None = None,
        template_override: dict | None = None,
        ai_description: str = "",
        reset_channels: bool = False,
    ) -> dict:
        guild = target_guild or inter.guild
        template = template_override if isinstance(template_override, dict) else self._template(template_key)
        reason = f"Auto Setup {template['label']} - {inter.user} ({inter.user.id})"
        state = self._get_state(guild.id)
        reset_result = {"deleted": [], "failed": []}

        if reset_channels:
            state["published_messages"] = {}
            state["last_channels"] = {}
            state["last_categories"] = {}
            reset_result = await self._wipe_guild_channels(guild, reason)

        role_map, created_roles = await self._ensure_roles(guild, template["roles"], reason, template)
        categories, created_categories = await self._ensure_categories(guild, template["categories"], role_map, reason, template)
        channel_map, created_channels = await self._ensure_channels(guild, template["channels"], categories, role_map, reason, template)

        ticket_panel_id = self._configure_systems(guild.id, template_key, template, channel_map, categories, role_map)

        state["selected_template"] = template_key
        state["last_run_at"] = _now()
        state["last_template"] = template["label"]
        state["last_channels"] = self._channel_ids(channel_map)
        state["last_categories"] = self._category_ids(categories)
        state["last_roles"] = self._role_ids(role_map)

        published = []
        if publish:
            published = await self._publish_template_panels(guild, template_key, template, state, channel_map, ticket_panel_id)

        self._save_state(guild.id, state)
        self._save_run_log(guild.id, template_key, created_channels, created_categories, created_roles, published)
        await send_system_log(
            self.bot,
            guild,
            title="Auto Setup aplicado",
            system="Auto Setup",
            description=(
                f"Template: `{template['label']}`\n"
                f"Canais criados: `{len(created_channels)}`\n"
                f"Categorias criadas: `{len(created_categories)}`\n"
                f"Cargos criados: `{len(created_roles)}`\n"
                f"Canais/categorias removidos: `{len(reset_result.get('deleted', []))}`\n"
                f"Paineis: `{len(published)}`"
                + (f"\nDescricao IA: `{ai_description[:500]}`" if ai_description else "")
            ),
            actor=inter.user,
            channel_id=(channel_map.get("logs_system").id if channel_map.get("logs_system") else None),
        )
        return {
            "created_channels": created_channels,
            "created_categories": created_categories,
            "created_roles": created_roles,
            "published": published,
            "reset_deleted": reset_result.get("deleted", []),
            "reset_failed": reset_result.get("failed", []),
        }

    def _save_run_log(self, guild_id: int, template_key: str, channels: list, categories: list, roles: list, published: list) -> None:
        data = db.get_document(RUNS_KEY) or {}
        runs = data.setdefault(str(guild_id), [])
        runs.append(
            {
                "template": template_key,
                "created_channels": len(channels),
                "created_categories": len(categories),
                "created_roles": len(roles),
                "published": len(published),
                "created_at": _now(),
            }
        )
        data[str(guild_id)] = runs[-50:]
        db.save_document(RUNS_KEY, data)

    def _save_ai_run(self, user_id: int, guild_id: int, template: dict, request: dict, result: dict) -> None:
        data = db.get_document(AI_RUNS_KEY) or {}
        runs = data.setdefault(str(guild_id), [])
        runs.append(
            {
                "user_id": str(user_id),
                "template": template.get("label", "IA"),
                "families": request.get("families", []),
                "description": str(request.get("description") or "")[:500],
                "created_channels": len(result.get("created_channels", [])),
                "created_categories": len(result.get("created_categories", [])),
                "created_roles": len(result.get("created_roles", [])),
                "published": len(result.get("published", [])),
                "created_at": _now(),
            }
        )
        data[str(guild_id)] = runs[-50:]
        db.save_document(AI_RUNS_KEY, data)

    async def _publish_existing(self, inter: disnake.MessageInteraction, template_key: str) -> list[str]:
        guild = inter.guild
        template = self._template(template_key)
        state = self._get_state(guild.id)
        channel_map = self._resolve_channels_from_state(guild, state)
        if not channel_map:
            return []
        categories = self._resolve_categories_from_state(guild, state)
        roles = self._resolve_roles_from_state(guild, state)
        ticket_panel_id = self._configure_systems(guild.id, template_key, template, channel_map, categories, roles)
        published = await self._publish_template_panels(guild, template_key, template, state, channel_map, ticket_panel_id)
        state["last_published_at"] = _now()
        self._save_state(guild.id, state)
        return published

    @commands.slash_command(name="criar_servidor_ia", description="Criar estrutura de servidor com IA")
    async def criar_servidor_ia(self, inter: disnake.ApplicationCommandInteraction):
        if not await self._can_manage(inter):
            await inter.response.send_message(f"{emoji.wrong} Voce precisa ter permissao de gerenciamento para usar este sistema.", ephemeral=True)
            return
        await inter.response.send_modal(AutoSetupAIDescriptionModal(self))

    @commands.Cog.listener("on_message_interaction")
    async def on_auto_setup_interaction(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("AutoSetup_"):
            return

        if not await self._can_manage(inter):
            await inter.response.send_message(f"{emoji.wrong} Voce precisa ter permissao de gerenciamento para usar o Auto Setup.", ephemeral=True)
            return

        state = self._get_state(inter.guild.id)
        selected_key = self._template_key(state.get("selected_template"))

        if custom_id == "AutoSetup_AIStart":
            await inter.response.send_modal(AutoSetupAIDescriptionModal(self))
            return

        if custom_id.startswith("AutoSetup_AIApply:"):
            request_id = custom_id.split(":", 1)[1]
            await inter.response.send_modal(AutoSetupAIGuildModal(self, request_id))
            return

        if custom_id.startswith("AutoSetup_AICancel:"):
            request_id = custom_id.split(":", 1)[1]
            pending = self._ai_pending_doc()
            request = pending.get(request_id)
            if request and str(request.get("user_id")) == str(inter.user.id):
                pending.pop(request_id, None)
                self._save_ai_pending_doc(pending)
            await inter.response.send_message(f"{emoji.correct} Processo de criacao com IA cancelado.", ephemeral=True)
            return

        if custom_id == "AutoSetup_TemplateSelect":
            selected_key = self._template_key(inter.values[0])
            state["selected_template"] = selected_key
            self._save_state(inter.guild.id, state)
            await inter.response.defer(with_message=False)
            await inter.edit_original_message(content=None, embed=None, components=self.display_auto_setup_panel(inter), flags=self._flags())
            return

        if custom_id == "AutoSetup_Customize":
            await inter.response.send_modal(AutoSetupCustomizeModal(self))
            return

        if custom_id == "AutoSetup_Apply":
            await inter.response.defer(ephemeral=True)
            try:
                result = await self._apply_template(inter, selected_key, publish=True)
            except disnake.Forbidden:
                await inter.followup.send(f"{emoji.wrong} Nao tenho permissao para criar cargos/canais neste servidor.", ephemeral=True)
                return
            except Exception as exc:
                await inter.followup.send(f"{emoji.wrong} Nao consegui aplicar o Auto Setup: `{exc}`", ephemeral=True)
                return

            lines = [
                f"{emoji.correct} Auto Setup **{self._template(selected_key)['label']}** aplicado.",
                f"Canais criados: `{len(result['created_channels'])}`",
                f"Categorias criadas: `{len(result['created_categories'])}`",
                f"Cargos criados: `{len(result['created_roles'])}`",
                f"Paineis publicados/atualizados: `{len(result['published'])}`",
            ]
            if result["published"]:
                lines.append("\n" + "\n".join(f"- {item}" for item in result["published"][:8]))
            await inter.followup.send("\n".join(lines), ephemeral=True)
            return

        if custom_id == "AutoSetup_Publish":
            await inter.response.defer(ephemeral=True)
            try:
                published = await self._publish_existing(inter, selected_key)
            except Exception as exc:
                await inter.followup.send(f"{emoji.wrong} Nao consegui publicar os paineis: `{exc}`", ephemeral=True)
                return
            if not published:
                await inter.followup.send(f"{emoji.wrong} Ainda nao existe estrutura salva para este template. Use **Aplicar Template** primeiro.", ephemeral=True)
                return
            await inter.followup.send(
                f"{emoji.correct} Paineis publicados/atualizados:\n" + "\n".join(f"- {item}" for item in published[:10]),
                ephemeral=True,
            )


def setup(bot: commands.Bot):
    bot.add_cog(AutoSetupPanel(bot))
