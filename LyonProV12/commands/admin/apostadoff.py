import re
import secrets
import asyncio
import unicodedata
from datetime import datetime

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.bool_utils import as_bool

KEY_PREFIX = "apostadoff_"
LEGACY_FILAS_KEY = "filas_apostas_config"
DEFAULT_SERVICE_FEE = 1.80
DEFAULT_OPTIONS = ["Normal", "Full Ump Xm8", "Mobilador"]
CREATION_MODES = {
    "manual": "Manual",
    "custom": "Personalizada",
    "automatic": "Automatica",
}


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _now_ts() -> int:
    return int(datetime.utcnow().timestamp())


def _get_emoji(name: str, fallback=None):
    return getattr(emoji, name, fallback)


def _clean_name(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"[^a-z ]+", "", raw)


def _clean_id(value: str | None) -> str:
    raw = str(value or "").strip()
    for token in ("<@", "<@!", "<#", "<@&", ">"):
        raw = raw.replace(token, "")
    return raw if raw.isdigit() else ""


def _money_float(value) -> float:
    raw = str(value or "0").replace("R$", "").replace(",", ".").strip()
    try:
        return max(0.0, float(raw))
    except Exception:
        return 0.0


class ApostadoFreeFire(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._auto_task: asyncio.Task | None = None
        self._auto_ready = False

    def cog_unload(self):
        if self._auto_task and not self._auto_task.done():
            self._auto_task.cancel()

    def _get_key(self, guild_id: int) -> str:
        return f"{KEY_PREFIX}{guild_id}"

    def _get_config(self, guild_id: int) -> dict:
        data = db.get_document(self._get_key(guild_id)) or {}
        if not isinstance(data, dict):
            data = {}
        if self._ensure_config_defaults(guild_id, data):
            self._save_config(guild_id, data)
        return data if isinstance(data, dict) else {}

    def _save_config(self, guild_id: int, data: dict) -> None:
        db.save_document(self._get_key(guild_id), data)

    def _default_template(self) -> dict:
        queue = self._default_queue()
        for key in ("players", "closed", "match_channel_id", "message_id", "channel_id", "payments"):
            queue.pop(key, None)
        queue["capacity"] = self._queue_capacity(queue.get("mode", ""))
        return queue

    def _ensure_config_defaults(self, guild_id: int, data: dict) -> bool:
        changed = False
        defaults = {
            "enabled": False,
            "container_mode": True,
            "queue_channel": "",
            "category": "",
            "logs_channel": "",
            "service_fee": DEFAULT_SERVICE_FEE,
            "auto_send_enabled": False,
            "auto_interval_minutes": 60,
            "creation_mode": "manual",
            "auto_close_full": True,
            "auto_recreate": True,
            "pix_name_confirmation": True,
            "pix_receiver_name": "",
            "pix_key": "",
            "queues": {},
            "queue_template": self._default_template(),
            "ranking": {},
            "blacklist": {},
            "disputes": [],
            "matches_history": [],
        }
        for key, value in defaults.items():
            if key not in data:
                data[key] = value.copy() if isinstance(value, dict) else value[:] if isinstance(value, list) else value
                changed = True

        if data.get("creation_mode") not in CREATION_MODES:
            data["creation_mode"] = "manual"
            changed = True
        if not isinstance(data.get("queues"), dict):
            data["queues"] = {}
            changed = True
        if not isinstance(data.get("queue_template"), dict):
            data["queue_template"] = self._default_template()
            changed = True
        if not isinstance(data.get("matches_history"), list):
            data["matches_history"] = []
            changed = True
        if not isinstance(data.get("blacklist"), dict):
            data["blacklist"] = {}
            changed = True
        if not isinstance(data.get("disputes"), list):
            data["disputes"] = []
            changed = True

        if self._migrate_legacy_filas(data):
            changed = True
        return changed

    def _migrate_legacy_filas(self, data: dict) -> bool:
        if data.get("legacy_filas_imported"):
            return False
        legacy = db.get_document(LEGACY_FILAS_KEY) or {}
        if not isinstance(legacy, dict) or not legacy:
            data["legacy_filas_imported"] = True
            return True

        if legacy.get("publish_channel_id") and not data.get("queue_channel"):
            data["queue_channel"] = legacy.get("publish_channel_id")
        for key in ("creation_mode", "auto_close_full", "auto_recreate"):
            if key in legacy:
                data[key] = legacy.get(key)

        template = legacy.get("template") if isinstance(legacy.get("template"), dict) else None
        if template:
            data["queue_template"] = {
                "name": template.get("name") or "2v2 Mobile",
                "mode": template.get("mode") or "2v2 Mobile",
                "value": template.get("value") or "5.00",
                "capacity": template.get("capacity") or self._queue_capacity(template.get("mode", "")),
                "options": self._normalise_options(template.get("options")),
            }

        queues = self._get_queues(data)
        legacy_filas = legacy.get("filas") if isinstance(legacy.get("filas"), dict) else {}
        for fila_id, fila in legacy_filas.items():
            if fila_id in queues or not isinstance(fila, dict):
                continue
            queues[fila_id] = {
                "name": fila.get("name") or fila.get("mode") or "Fila Apostado",
                "mode": fila.get("mode") or fila.get("name") or "Apostado",
                "value": fila.get("value") or "5.00",
                "capacity": fila.get("capacity") or self._queue_capacity(fila.get("mode", "")),
                "options": self._normalise_options(fila.get("options")),
                "players": fila.get("users") or [],
                "closed": bool(fila.get("closed", False)),
                "source": fila.get("source") or "imported",
                "created_at": fila.get("created_at") or _now(),
                "message_id": fila.get("message_id") or "",
                "channel_id": fila.get("channel_id") or "",
            }
        data["legacy_filas_imported"] = True
        return True

    def _flags(self) -> disnake.MessageFlags:
        return disnake.MessageFlags(is_components_v2=True)

    def _container_kwargs(self) -> dict:
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary") or "#8b2cff"
        try:
            return {"accent_colour": disnake.Colour(int(primary_color_hex.replace("#", ""), 16))}
        except Exception:
            return {"accent_colour": disnake.Colour(int("8b2cff", 16))}

    def _format_channel(self, channel_id) -> str:
        if not channel_id:
            return "`Nao configurado`"
        try:
            return f"<#{int(channel_id)}>"
        except (TypeError, ValueError):
            return f"`{channel_id}`"

    def _format_bool(self, enabled: bool, active_text: str = "Ativo", inactive_text: str = "Inativo") -> str:
        return f"`{active_text}`" if as_bool(enabled, False) else f"`{inactive_text}`"

    def _format_fee(self, value) -> str:
        try:
            fee = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            fee = DEFAULT_SERVICE_FEE
        return f"R$ {fee:.2f}".replace(".", ",")

    def _format_interval(self, value) -> int:
        try:
            return max(5, min(1440, int(value)))
        except (TypeError, ValueError):
            return 60

    def _format_roles(self, role_ids) -> str:
        if not isinstance(role_ids, list) or not role_ids:
            return "`Nao configurado`"
        return ", ".join(f"<@&{role_id}>" for role_id in role_ids[:8])

    def _short_queue_id(self, queue_id: str) -> str:
        return str(queue_id or "fila")[:8]

    def _queue_name_slug(self, queue: dict, queue_id: str) -> str:
        raw = queue.get("mode") or queue.get("name") or queue_id
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(raw).lower()).strip("-")
        return (slug or "fila")[:32]

    def _money_from_raw(self, value) -> str:
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
        match = re.search(r"(\d+)\s*[xv]\s*(\d+)", mode or "", re.IGNORECASE)
        if not match:
            return 10
        return max(2, min(int(match.group(1)) + int(match.group(2)), 50))

    def _normalise_options(self, raw_options) -> list[str]:
        if isinstance(raw_options, list):
            options = [str(option).strip() for option in raw_options if str(option).strip()]
        else:
            options = [part.strip() for part in str(raw_options or "").split(",") if part.strip()]
        return (options or DEFAULT_OPTIONS)[:5]

    def _default_queue(self) -> dict:
        return {
            "name": "2v2 Mobile",
            "mode": "2v2 Mobile",
            "value": "5.00",
            "capacity": 4,
            "options": DEFAULT_OPTIONS[:],
            "players": [],
            "closed": False,
            "source": "manual",
            "created_at": _now(),
            "message_id": "",
            "channel_id": "",
            "match_channel_id": None,
            "payments": {},
            "winner_ids": [],
            "result_note": "",
            "disputes": [],
        }

    def _get_queues(self, cfg: dict) -> dict:
        if not isinstance(cfg.get("queues"), dict):
            if isinstance(cfg.get("queues"), list):
                converted = {}
                for index, item in enumerate(cfg.get("queues") or []):
                    if isinstance(item, dict):
                        queue = self._default_queue()
                        queue.update(item)
                        converted[f"legacy{index}"] = queue
                    else:
                        queue = self._default_queue()
                        queue["name"] = str(item)
                        queue["mode"] = str(item)
                        converted[f"legacy{index}"] = queue
                cfg["queues"] = converted
            else:
                cfg["queues"] = {}

        queues = cfg["queues"]
        if isinstance(queues, dict):
            for queue_id, queue in list(queues.items()):
                if isinstance(queue, dict):
                    normalised = self._default_queue()
                    if isinstance(queue.get("users"), list) and not isinstance(queue.get("players"), list):
                        queue["players"] = queue.get("users")
                    normalised.update(queue)
                    normalised["options"] = self._normalise_options(normalised.get("options"))
                    normalised["capacity"] = self._queue_capacity(normalised)
                    normalised["source"] = normalised.get("source") or "manual"
                    normalised["payments"] = normalised.get("payments") if isinstance(normalised.get("payments"), dict) else {}
                    queues[queue_id] = normalised
                else:
                    normalised = self._default_queue()
                    normalised["name"] = str(queue)
                    normalised["mode"] = str(queue)
                    queues[queue_id] = normalised
            return queues
        return cfg["queues"]

    def _latest_queue_id(self, cfg: dict) -> str:
        queues = self._get_queues(cfg)
        last_id = str(cfg.get("last_queue_id") or "")
        if last_id in queues:
            return last_id
        if queues:
            return next(reversed(queues))
        return ""

    def _queue_from_template(self, cfg: dict, source: str) -> dict:
        template = cfg.get("queue_template") if isinstance(cfg.get("queue_template"), dict) else self._default_template()
        queue = self._default_queue()
        for key in ("name", "mode", "value", "capacity", "options"):
            queue[key] = template.get(key, queue[key])
        queue["source"] = source
        queue["players"] = []
        queue["closed"] = False
        queue["created_at"] = _now()
        queue["payments"] = {}
        queue["options"] = self._normalise_options(queue.get("options"))
        queue["capacity"] = self._queue_capacity(queue)
        return queue

    def _create_queue(self, cfg: dict, queue: dict) -> str:
        queues = self._get_queues(cfg)
        queue_id = secrets.token_hex(3)
        normalised = self._default_queue()
        normalised.update(queue if isinstance(queue, dict) else {})
        normalised["options"] = self._normalise_options(normalised.get("options"))
        normalised["capacity"] = self._queue_capacity(normalised)
        queues[queue_id] = normalised
        cfg["last_queue_id"] = queue_id
        return queue_id

    def _normalise_players(self, queue: dict) -> list[dict]:
        players = queue.get("players") if isinstance(queue.get("players"), list) else []
        normalised = []
        for player in players:
            if isinstance(player, dict):
                user_id = player.get("id")
                if user_id:
                    normalised.append({"id": str(user_id), "option": player.get("option", "Normal")})
            elif player:
                normalised.append({"id": str(player), "option": "Normal"})
        queue["players"] = normalised
        return normalised

    def _ensure_queue(self, cfg: dict) -> str:
        queue_id = self._latest_queue_id(cfg)
        if queue_id:
            cfg["last_queue_id"] = queue_id
            return queue_id
        return self._create_queue(cfg, self._queue_from_template(cfg, "manual"))

    def _queue_players_text(self, queue: dict) -> str:
        players = self._normalise_players(queue)
        if not players:
            return "Nenhum jogador na fila."
        lines = []
        for index, player in enumerate(players, start=1):
            user_id = player.get("id")
            option = player.get("option", "Normal")
            lines.append(f"{index}. <@{user_id}> - `{option}`")
        return "\n".join(lines)

    def _is_blacklisted(self, cfg: dict, user_id: str) -> dict | None:
        entry = (cfg.get("blacklist") or {}).get(str(user_id))
        if isinstance(entry, dict) and entry.get("active", True):
            return entry
        return None

    def _history_text(self, cfg: dict, limit: int = 10) -> str:
        history = cfg.get("matches_history") if isinstance(cfg.get("matches_history"), list) else []
        if not history:
            return f"{emoji.information} Nenhuma partida registrada ainda."
        lines = []
        for record in history[-limit:][::-1]:
            winners = ", ".join(f"<@{user_id}>" for user_id in record.get("winner_ids", [])[:4]) or "`sem vencedor`"
            status = record.get("status") or "registrada"
            lines.append(
                f"- `{record.get('queue_name') or record.get('queue_id')}` | `{status}` | "
                f"Vencedor: {winners} | <t:{int(record.get('created_ts') or _now_ts())}:R>"
            )
        return "\n".join(lines)

    def _ranking_text(self, cfg: dict, limit: int = 10) -> str:
        ranking = cfg.get("ranking") if isinstance(cfg.get("ranking"), dict) else {}
        if not ranking:
            return f"{emoji.information} Nenhum ranking registrado ainda."
        top = sorted(
            ranking.items(),
            key=lambda item: (int(item[1].get("wins", 0)), int(item[1].get("matches", 0))),
            reverse=True,
        )[:limit]
        lines = []
        for index, (user_id, stats) in enumerate(top, start=1):
            wins = int(stats.get("wins", 0))
            losses = int(stats.get("losses", 0))
            matches = int(stats.get("matches", 0))
            disputes = int(stats.get("disputes", 0))
            profit = float(stats.get("profit", 0) or 0)
            rate = int((wins / matches) * 100) if matches else 0
            lines.append(
                f"{index}. <@{user_id}> - `{wins}V/{losses}D` | `{rate}%` winrate | "
                f"Lucro: `{self._format_fee(profit)}` | Disputas: `{disputes}`"
            )
        return "\n".join(lines)

    def _record_match(self, cfg: dict, queue_id: str, queue: dict, status: str, actor_id: str = "") -> dict:
        players = [str(player.get("id")) for player in self._normalise_players(queue)]
        winner_ids = [str(user_id) for user_id in queue.get("winner_ids", []) if str(user_id) in players]
        value = _money_float(queue.get("value"))
        fee = _money_float(cfg.get("service_fee", DEFAULT_SERVICE_FEE))
        prize = max(0.0, (value * len(players)) - fee)
        record = {
            "id": f"match-{queue_id}-{_now_ts()}",
            "queue_id": queue_id,
            "queue_name": queue.get("name") or queue.get("mode") or queue_id,
            "mode": queue.get("mode") or "",
            "value": value,
            "service_fee": fee,
            "prize": prize,
            "status": status,
            "players": players,
            "winner_ids": winner_ids,
            "note": queue.get("result_note") or "",
            "actor_id": str(actor_id or ""),
            "created_at": _now(),
            "created_ts": _now_ts(),
        }
        history = cfg.setdefault("matches_history", [])
        if not isinstance(history, list):
            history = []
        history.append(record)
        cfg["matches_history"] = history[-500:]

        ranking = cfg.setdefault("ranking", {})
        if status == "finalizada":
            winners = set(winner_ids)
            split_prize = prize / max(len(winners), 1) if winners else 0
            for user_id in players:
                stats = ranking.setdefault(
                    user_id,
                    {"wins": 0, "losses": 0, "matches": 0, "profit": 0.0, "disputes": 0},
                )
                stats["matches"] = int(stats.get("matches", 0)) + 1
                if user_id in winners:
                    stats["wins"] = int(stats.get("wins", 0)) + 1
                    stats["profit"] = round(float(stats.get("profit", 0) or 0) + split_prize, 2)
                elif winners:
                    stats["losses"] = int(stats.get("losses", 0)) + 1
                    stats["profit"] = round(float(stats.get("profit", 0) or 0) - value, 2)
        return record

    def _build_queue_components(self, guild_id: int, queue_id: str, queue: dict) -> list:
        options = self._normalise_options(queue.get("options"))
        players = self._normalise_players(queue)
        closed = bool(queue.get("closed", False))
        capacity = self._queue_capacity(queue)
        status = "Fechada" if closed else "Aberta"
        source = CREATION_MODES.get(str(queue.get("source") or "manual"), str(queue.get("source") or "Manual").title())

        join_buttons = [
            disnake.ui.Button(
                label=option[:80],
                style=disnake.ButtonStyle.grey,
                emoji=_get_emoji("swords", _get_emoji("sword")),
                custom_id=f"ApostadoFila_Join:{guild_id}:{queue_id}:{index}",
                disabled=closed or (len(players) >= capacity),
            )
            for index, option in enumerate(options)
        ]

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"## {_get_emoji('swords', '')} {queue.get('name') or queue.get('mode') or 'Fila Free Fire'}"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                f"**{_get_emoji('dollar', '')} Valor Partida**\n"
                f"{self._money_from_raw(queue.get('value'))}\n\n"
                f"**{_get_emoji('swords', '')} Modo**\n"
                f"{queue.get('mode') or queue.get('name') or 'Nao configurado'}\n\n"
                f"**{_get_emoji('members', '')} Jogadores na fila ({len(players)}/{capacity})**\n"
                f"{self._queue_players_text(queue)}\n\n"
                f"**Criação:** `{source}`\n"
                f"**Status:** `{status}`"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(*join_buttons),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Sair",
                    style=disnake.ButtonStyle.danger,
                    emoji=emoji.back,
                    custom_id=f"ApostadoFila_Leave:{guild_id}:{queue_id}",
                    disabled=closed,
                ),
                disnake.ui.Button(
                    label="Fechar Fila",
                    style=disnake.ButtonStyle.danger,
                    emoji=_get_emoji("lock"),
                    custom_id=f"ApostadoFila_Close:{guild_id}:{queue_id}",
                    disabled=closed,
                ),
            ),
            **self._container_kwargs(),
        )
        return [container]

    def _build_apostado_panel(self, guild_id: int) -> list:
        data = self._get_config(guild_id)
        enabled = as_bool(data.get("enabled"), False)
        container_mode = as_bool(data.get("container_mode"), True)
        auto_send_enabled = as_bool(data.get("auto_send_enabled"), False)
        auto_interval = self._format_interval(data.get("auto_interval_minutes", 60))
        category = data.get("category")
        queue_channel = data.get("queue_channel")
        logs_channel = data.get("logs_channel")
        service_fee = data.get("service_fee", DEFAULT_SERVICE_FEE)
        queues = self._get_queues(data)
        open_count = sum(1 for queue in queues.values() if not queue.get("closed"))
        mode_label = CREATION_MODES.get(data.get("creation_mode"), "Manual")
        blacklist_count = sum(1 for item in (data.get("blacklist") or {}).values() if isinstance(item, dict) and item.get("active", True))
        history_count = len(data.get("matches_history") if isinstance(data.get("matches_history"), list) else [])

        toggle_label = "Desativar" if enabled else "Ativar"
        toggle_style = disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success
        container_label = "Container: Ativo" if container_mode else "Container: Inativo"
        auto_label = "Auto: Ativo" if auto_send_enabled else "Auto: Inativo"
        auto_style = disnake.ButtonStyle.success if auto_send_enabled else disnake.ButtonStyle.grey
        pix_label = "Pix Nome: Ativo" if as_bool(data.get("pix_name_confirmation"), True) else "Pix Nome: Inativo"

        container = disnake.ui.Container(
            disnake.ui.TextDisplay("## ApostadoFF"),
            disnake.ui.TextDisplay("-# Painel > **ApostadoFF**"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                "Sistema de apostas Free Fire.\n"
                "Configure filas, envie o painel em componente V2 e gerencie jogadores."
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                f"**Status:** {self._format_bool(enabled)}\n"
                f"**Canal das filas:** {self._format_channel(queue_channel)}\n"
                f"**Categoria Apostas:** {self._format_channel(category)}\n"
                f"**Canal Logs:** {self._format_channel(logs_channel)}\n"
                f"**Taxa de Servico:** `{self._format_fee(service_fee)}`\n"
                f"**Filas:** `{len(queues)}` configuradas | `{open_count}` abertas\n"
                f"**Partidas registradas:** `{history_count}` | **Blacklist:** `{blacklist_count}`\n"
                f"**Modo de criacao:** `{mode_label}` | **Auto recriar:** {self._format_bool(data.get('auto_recreate'), 'Sim', 'Nao')} | **Fecha ao lotar:** {self._format_bool(data.get('auto_close_full'), 'Sim', 'Nao')}\n"
                f"**Envio automatico:** {self._format_bool(auto_send_enabled)} a cada `{auto_interval} minuto(s)`\n"
                f"**Confirmacao Pix por nome:** {self._format_bool(data.get('pix_name_confirmation'), 'Ativa', 'Inativa')}\n"
                f"**Mediadores:** {self._format_roles(data.get('mediadores'))}\n"
                f"**Modo Container (V2):** {self._format_bool(container_mode)}"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label=toggle_label, style=toggle_style, emoji=_get_emoji("power"), custom_id=f"Apostado_Activate:{guild_id}"),
                disnake.ui.Button(label="Enviar Fila", style=disnake.ButtonStyle.success, emoji=_get_emoji("send", _get_emoji("rocket")), custom_id=f"Apostado_SendQueue:{guild_id}"),
                disnake.ui.Button(label=auto_label, style=auto_style, emoji=_get_emoji("reload"), custom_id=f"Apostado_AutoToggle:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Canais", style=disnake.ButtonStyle.grey, emoji=_get_emoji("textc", _get_emoji("canal")), custom_id=f"Apostado_Canais:{guild_id}"),
                disnake.ui.Button(label="Intervalo", style=disnake.ButtonStyle.grey, emoji=_get_emoji("clock"), custom_id=f"Apostado_AutoInterval:{guild_id}"),
                disnake.ui.Button(label="Taxa", style=disnake.ButtonStyle.grey, emoji=_get_emoji("dollar"), custom_id=f"Apostado_Taxa:{guild_id}"),
                disnake.ui.Button(label="Criar Fila", style=disnake.ButtonStyle.success, emoji=_get_emoji("plus", _get_emoji("edit")), custom_id=f"Apostado_Filas:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label=f"Modo: {mode_label}", style=disnake.ButtonStyle.grey, emoji=_get_emoji("reload"), custom_id=f"Apostado_Mode:{guild_id}"),
                disnake.ui.Button(label="Modelo Fila", style=disnake.ButtonStyle.blurple, emoji=_get_emoji("edit"), custom_id=f"Apostado_Template:{guild_id}"),
                disnake.ui.Button(label="Gerenciar Filas", style=disnake.ButtonStyle.blurple, emoji=_get_emoji("settings"), custom_id=f"Apostado_ManageQueue:{guild_id}", disabled=not queues),
                disnake.ui.Button(label="Pix", style=disnake.ButtonStyle.grey, emoji=_get_emoji("pix", _get_emoji("wallet")), custom_id=f"Apostado_PixConfig:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Auto recriar", style=disnake.ButtonStyle.green if as_bool(data.get("auto_recreate"), True) else disnake.ButtonStyle.grey, emoji=_get_emoji("reload"), custom_id=f"Apostado_AutoRecreate:{guild_id}"),
                disnake.ui.Button(label="Fechar ao lotar", style=disnake.ButtonStyle.green if as_bool(data.get("auto_close_full"), True) else disnake.ButtonStyle.grey, emoji=_get_emoji("lock"), custom_id=f"Apostado_AutoClose:{guild_id}"),
                disnake.ui.Button(label=pix_label, style=disnake.ButtonStyle.green if as_bool(data.get("pix_name_confirmation"), True) else disnake.ButtonStyle.grey, emoji=_get_emoji("pix", _get_emoji("wallet")), custom_id=f"Apostado_PixAutoToggle:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Mediadores", style=disnake.ButtonStyle.blurple, emoji=_get_emoji("staff", _get_emoji("members")), custom_id=f"Apostado_Mediadores:{guild_id}"),
                disnake.ui.Button(label="Analistas", style=disnake.ButtonStyle.blurple, emoji=_get_emoji("search"), custom_id=f"Apostado_Analistas:{guild_id}"),
                disnake.ui.Button(label="Coins", style=disnake.ButtonStyle.blurple, emoji=_get_emoji("coin"), custom_id=f"Apostado_Coins:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label=container_label, style=disnake.ButtonStyle.grey, emoji=_get_emoji("on"), custom_id=f"Apostado_ContainerToggle:{guild_id}"),
                disnake.ui.Button(label="Ranking", style=disnake.ButtonStyle.grey, emoji=_get_emoji("trophy"), custom_id=f"Apostado_Ranking:{guild_id}"),
                disnake.ui.Button(label="Historico", style=disnake.ButtonStyle.grey, emoji=_get_emoji("receipt"), custom_id=f"Apostado_History:{guild_id}"),
                disnake.ui.Button(label="Blacklist", style=disnake.ButtonStyle.danger, emoji=_get_emoji("ban", _get_emoji("wrong")), custom_id=f"Apostado_Blacklist:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Modelo Servidor Apostado", style=disnake.ButtonStyle.danger, emoji=_get_emoji("listening_music", _get_emoji("config")), custom_id=f"Apostado_Modelo:{guild_id}"),
            ),
            **self._container_kwargs(),
        )

        return [
            container,
        ]

    def _build_channels_panel(self, guild_id: int) -> list:
        container = disnake.ui.Container(
            disnake.ui.TextDisplay("## Canais do ApostadoFF"),
            disnake.ui.TextDisplay("-# Painel > ApostadoFF > **Canais**"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay("Selecione onde as filas serao enviadas, a categoria das apostas e o canal de logs."),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.ChannelSelect(
                    placeholder="Canal para enviar as filas",
                    custom_id=f"Apostado_SelectQueueChannel:{guild_id}",
                    min_values=1,
                    max_values=1,
                    channel_types=[disnake.ChannelType.text],
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.ChannelSelect(
                    placeholder="Categoria das apostas",
                    custom_id=f"Apostado_SelectCategory:{guild_id}",
                    min_values=1,
                    max_values=1,
                    channel_types=[disnake.ChannelType.category],
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.ChannelSelect(
                    placeholder="Canal de logs",
                    custom_id=f"Apostado_SelectLogs:{guild_id}",
                    min_values=1,
                    max_values=1,
                    channel_types=[disnake.ChannelType.text],
                )
            ),
            **self._container_kwargs(),
        )
        return [
            container,
        ]

    def _build_roles_panel(self, guild_id: int, role_type: str) -> list:
        label = "Mediadores" if role_type == "mediadores" else "Analistas"
        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"## {label}"),
            disnake.ui.TextDisplay(f"-# Painel > ApostadoFF > **{label}**"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(f"Selecione os cargos que poderao atuar como {label.lower()}."),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.RoleSelect(
                    placeholder=f"Selecionar cargos de {label.lower()}",
                    custom_id=f"Apostado_SelectRoles:{role_type}:{guild_id}",
                    min_values=1,
                    max_values=25,
                )
            ),
            **self._container_kwargs(),
        )
        return [
            container,
        ]

    def _build_queue_manager_panel(self, guild_id: int) -> list:
        cfg = self._get_config(guild_id)
        queues = self._get_queues(cfg)
        queue_id = self._latest_queue_id(cfg)
        queue = queues.get(queue_id) if queue_id else None
        if not queue:
            body = "Nenhuma fila criada ainda. Use **Criar Fila** ou configure o **Modelo Fila**."
            disabled = True
        else:
            players = self._normalise_players(queue)
            body = (
                f"**ID:** `{queue_id}`\n"
                f"**Nome:** `{queue.get('name')}`\n"
                f"**Modo:** `{queue.get('mode')}`\n"
                f"**Valor:** `{self._money_from_raw(queue.get('value'))}`\n"
                f"**Jogadores:** `{len(players)}/{self._queue_capacity(queue)}`\n"
                f"**Status:** `{'Fechada' if queue.get('closed') else 'Aberta'}`\n"
                f"**Mensagem:** `{queue.get('message_id') or 'Nao enviada'}`\n\n"
                f"{self._queue_players_text(queue)}"
            )
            disabled = False

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay("## Gerenciar Filas do ApostadoFF"),
                disnake.ui.TextDisplay("-# Painel > ApostadoFF > **Filas**"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(body),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Reenviar", style=disnake.ButtonStyle.success, emoji=_get_emoji("announcement", _get_emoji("rocket")), custom_id=f"Apostado_QueueResend:{guild_id}", disabled=disabled),
                    disnake.ui.Button(label="Reabrir", style=disnake.ButtonStyle.green, emoji=_get_emoji("unlock"), custom_id=f"Apostado_QueueReopen:{guild_id}", disabled=disabled),
                    disnake.ui.Button(label="Fechar", style=disnake.ButtonStyle.danger, emoji=_get_emoji("lock"), custom_id=f"Apostado_QueueClose:{guild_id}", disabled=disabled),
                ),
                **self._container_kwargs(),
            )
        ]

    def _payment_status_text(self, queue: dict) -> str:
        players = self._normalise_players(queue)
        payments = queue.get("payments") if isinstance(queue.get("payments"), dict) else {}
        lines = []
        for player in players:
            user_id = str(player.get("id"))
            payment = payments.get(user_id) if isinstance(payments.get(user_id), dict) else {}
            if payment.get("status") == "confirmed":
                lines.append(f"- <@{user_id}> {emoji.correct} `{payment.get('pix_name') or 'confirmado'}`")
            else:
                lines.append(f"- <@{user_id}> {emoji.warn} `aguardando nome do Pix`")
        return "\n".join(lines) if lines else "Nenhum jogador na partida."

    def _all_payments_confirmed(self, queue: dict) -> bool:
        players = self._normalise_players(queue)
        payments = queue.get("payments") if isinstance(queue.get("payments"), dict) else {}
        return bool(players) and all((payments.get(str(player.get("id"))) or {}).get("status") == "confirmed" for player in players)

    def _match_components(self, guild_id: int, queue_id: str, queue: dict) -> list:
        players = self._normalise_players(queue)
        players_text = "\n".join(f"- <@{player['id']}> - `{player.get('option', 'Normal')}`" for player in players) or "Nenhum jogador."
        cfg = self._get_config(guild_id)
        pix_lines = []
        if cfg.get("pix_receiver_name"):
            pix_lines.append(f"**Nome Pix:** `{cfg.get('pix_receiver_name')}`")
        if cfg.get("pix_key"):
            pix_lines.append(f"**Chave Pix:** `{cfg.get('pix_key')}`")
        pix_block = "\n".join(pix_lines) if pix_lines else "`Pix ainda nao configurado no painel.`"
        winners = ", ".join(f"<@{user_id}>" for user_id in queue.get("winner_ids", [])[:6]) or "`nao definido`"
        disputes = queue.get("disputes") if isinstance(queue.get("disputes"), list) else []
        dispute_text = f"`{len(disputes)}` aberta(s)" if disputes else "`sem disputa`"

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {_get_emoji('swords', '')} Partida ApostadoFF"),
                disnake.ui.TextDisplay(
                    f"**Fila:** `{queue.get('name') or queue_id}`\n"
                    f"**Modo:** `{queue.get('mode') or 'Nao configurado'}`\n"
                    f"**Valor:** `{self._money_from_raw(queue.get('value'))}`\n\n"
                    f"**Jogadores:**\n{players_text}\n\n"
                    f"**Pagamento Pix:**\n{pix_block}\n\n"
                    "**Confirmacao automatica:** cada jogador manda no chat o nome que apareceu no Pix.\n"
                    "Exemplo: `Thiago Henrike`"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"**Status dos pagamentos:**\n{self._payment_status_text(queue)}\n\n"
                    f"**Vencedor:** {winners}\n"
                    f"**Disputa:** {dispute_text}"
                    + (f"\n**Observacao:** {queue.get('result_note')}" if queue.get("result_note") else "")
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Confirmar Pix", style=disnake.ButtonStyle.blurple, emoji=_get_emoji("pix", _get_emoji("wallet")), custom_id=f"Apostado_MatchPay:{guild_id}:{queue_id}"),
                    disnake.ui.Button(label="Registrar Vencedor", style=disnake.ButtonStyle.blurple, emoji=_get_emoji("trophy"), custom_id=f"Apostado_MatchWinner:{guild_id}:{queue_id}"),
                    disnake.ui.Button(label="Abrir Disputa", style=disnake.ButtonStyle.grey, emoji=_get_emoji("warn"), custom_id=f"Apostado_MatchDispute:{guild_id}:{queue_id}"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Marcar Finalizada", style=disnake.ButtonStyle.success, emoji=_get_emoji("correct"), custom_id=f"Apostado_MatchFinish:{guild_id}:{queue_id}"),
                    disnake.ui.Button(label="Cancelar Partida", style=disnake.ButtonStyle.danger, emoji=_get_emoji("wrong"), custom_id=f"Apostado_MatchCancel:{guild_id}:{queue_id}"),
                ),
                **self._container_kwargs(),
            )
        ]

    async def _edit_components(self, inter: disnake.MessageInteraction, components: list):
        if not inter.response.is_done():
            await inter.response.defer(with_message=False)
        return await inter.edit_original_message(content=None, embed=None, components=components, flags=self._flags())

    async def _edit_source_message(self, message: disnake.Message | None, guild_id: int):
        if not message:
            return
        await message.edit(content=None, embed=None, components=self._build_apostado_panel(guild_id), flags=self._flags())

    async def _finish_modal(self, modal_inter: disnake.ModalInteraction, source_message, guild_id: int, text: str):
        if not modal_inter.response.is_done():
            await modal_inter.response.defer(ephemeral=True)
        try:
            await self._edit_source_message(source_message, guild_id)
        except Exception as exc:
            print(f"[ApostadoFF] Falha ao atualizar painel: {exc}")
        await modal_inter.followup.send(text, ephemeral=True)

    async def display_apostado_panel(self, inter: disnake.MessageInteraction):
        return self._build_apostado_panel(inter.guild.id)

    def _can_manage_queue(self, inter: disnake.MessageInteraction, cfg: dict) -> bool:
        perms = getattr(inter.author, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild):
            return True
        mediadores = cfg.get("mediadores") if isinstance(cfg.get("mediadores"), list) else []
        analistas = cfg.get("analistas") if isinstance(cfg.get("analistas"), list) else []
        allowed_roles = {str(role_id) for role_id in mediadores + analistas}
        return any(str(role.id) in allowed_roles for role in getattr(inter.author, "roles", []))

    async def _send_log(self, guild: disnake.Guild, cfg: dict, text: str):
        channel_id = cfg.get("logs_channel")
        channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
        if isinstance(channel, disnake.TextChannel):
            try:
                await channel.send(text)
            except disnake.HTTPException:
                pass

    def _next_auto_queue_id(self, cfg: dict) -> str:
        if cfg.get("creation_mode") == "automatic":
            return self._create_queue(cfg, self._queue_from_template(cfg, "automatic"))
        queues = self._get_queues(cfg)
        if not queues:
            return self._ensure_queue(cfg)
        queue_ids = list(queues.keys())
        index = int(cfg.get("auto_queue_index", 0) or 0) % len(queue_ids)
        cfg["auto_queue_index"] = (index + 1) % len(queue_ids)
        return queue_ids[index]

    async def _send_queue_to_channel(
        self,
        guild: disnake.Guild,
        fallback_channel: disnake.TextChannel | None,
        guild_id: int,
        queue_id: str | None = None,
    ):
        cfg = self._get_config(guild_id)
        if queue_id is None and cfg.get("creation_mode") in {"automatic", "custom"}:
            queue_id = self._create_queue(cfg, self._queue_from_template(cfg, cfg.get("creation_mode")))
        else:
            queue_id = queue_id or self._ensure_queue(cfg)
        queues = self._get_queues(cfg)
        queue = queues[queue_id]
        queue["players"] = []
        queue["closed"] = False
        queue["match_channel_id"] = None
        queue["match_message_id"] = None
        queue["payments"] = {}
        cfg["last_queue_id"] = queue_id
        self._save_config(guild_id, cfg)

        channel_id = cfg.get("queue_channel")
        target_channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
        if not isinstance(target_channel, disnake.TextChannel):
            target_channel = fallback_channel

        if not isinstance(target_channel, disnake.TextChannel):
            raise RuntimeError("Canal de filas nao configurado.")

        sent = await target_channel.send(
            components=self._build_queue_components(guild_id, queue_id, queue),
            flags=self._flags(),
        )
        queue["message_id"] = sent.id
        queue["channel_id"] = sent.channel.id
        self._save_config(guild_id, cfg)
        await self._send_log(guild, cfg, f"Fila ApostadoFF enviada: `{queue.get('name', queue_id)}` em {sent.channel.mention}.")
        return sent

    async def _refresh_queue_message(self, guild: disnake.Guild, cfg: dict, queue_id: str, queue: dict):
        channel_id = queue.get("channel_id")
        message_id = queue.get("message_id")
        if not channel_id or not message_id:
            return
        channel = guild.get_channel(int(channel_id)) if guild else None
        if not isinstance(channel, disnake.TextChannel):
            return
        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(components=self._build_queue_components(guild.id, queue_id, queue), flags=self._flags())
        except Exception as exc:
            await self._send_log(guild, cfg, f"Nao consegui atualizar fila `{queue.get('name', queue_id)}`: `{exc}`")

    async def _send_queue_message(self, inter: disnake.MessageInteraction, guild_id: int, queue_id: str | None = None):
        return await self._send_queue_to_channel(inter.guild, inter.channel, guild_id, queue_id)

    async def _create_match_channel(self, inter: disnake.MessageInteraction, cfg: dict, queue_id: str, queue: dict):
        if queue.get("match_channel_id"):
            return None

        guild = inter.guild
        if not guild:
            return None

        players = self._normalise_players(queue)
        category_id = cfg.get("category")
        category = guild.get_channel(int(category_id)) if category_id else None
        if category and not isinstance(category, disnake.CategoryChannel):
            category = None

        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(view_channel=False),
            guild.me: disnake.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }
        for player in players:
            member = guild.get_member(int(player["id"]))
            if member:
                overwrites[member] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        for role_id in (cfg.get("mediadores") or []) + (cfg.get("analistas") or []):
            role = guild.get_role(int(role_id))
            if role:
                overwrites[role] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel_name = f"apostado-{self._queue_name_slug(queue, queue_id)}-{self._short_queue_id(queue_id)}"
        try:
            channel = await guild.create_text_channel(
                name=channel_name[:90],
                category=category,
                overwrites=overwrites,
                reason="Fila ApostadoFF completa",
            )
        except disnake.HTTPException as exc:
            await self._send_log(guild, cfg, f"Nao consegui criar canal da partida `{queue.get('name', queue_id)}`: `{exc}`")
            return None

        queue["match_channel_id"] = channel.id
        payments = queue.get("payments") if isinstance(queue.get("payments"), dict) else {}
        for player in players:
            payments.setdefault(str(player["id"]), {"status": "pending", "pix_name": "", "confirmed_at": None})
        queue["payments"] = payments
        self._save_config(guild.id, cfg)

        sent = await channel.send(components=self._match_components(guild.id, queue_id, queue), flags=self._flags())
        queue["match_message_id"] = sent.id
        self._save_config(guild.id, cfg)
        await self._send_log(guild, cfg, f"Partida ApostadoFF organizada em {channel.mention}: `{queue.get('name', queue_id)}`.")
        return channel

    async def _refresh_match_message(self, guild: disnake.Guild, cfg: dict, queue_id: str, queue: dict):
        channel_id = queue.get("match_channel_id")
        message_id = queue.get("match_message_id")
        if not channel_id or not message_id:
            return
        channel = guild.get_channel(int(channel_id)) if guild else None
        if not isinstance(channel, disnake.TextChannel):
            return
        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(components=self._match_components(guild.id, queue_id, queue), flags=self._flags())
        except Exception as exc:
            await self._send_log(guild, cfg, f"Nao consegui atualizar painel da partida `{queue.get('name', queue_id)}`: `{exc}`")

    async def _run_auto_sender(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                now_ts = int(disnake.utils.utcnow().timestamp())
                for guild in list(self.bot.guilds):
                    cfg = self._get_config(guild.id)
                    if not as_bool(cfg.get("enabled"), False) or not as_bool(cfg.get("auto_send_enabled"), False):
                        continue
                    if not cfg.get("queue_channel"):
                        continue

                    interval_seconds = self._format_interval(cfg.get("auto_interval_minutes", 60)) * 60
                    last_ts = int(cfg.get("last_auto_send_ts", 0) or 0)
                    if now_ts - last_ts < interval_seconds:
                        continue

                    queue_id = self._next_auto_queue_id(cfg)
                    cfg["last_auto_send_ts"] = now_ts
                    self._save_config(guild.id, cfg)
                    try:
                        await self._send_queue_to_channel(guild, None, guild.id, queue_id)
                    except Exception as exc:
                        await self._send_log(guild, cfg, f"Falha no envio automatico da fila ApostadoFF: `{exc}`")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[ApostadoFF] Erro no envio automatico: {exc}")
            await asyncio.sleep(60)

    @commands.Cog.listener("on_ready")
    async def _apostado_auto_ready(self):
        if self._auto_ready:
            return
        self._auto_ready = True
        self._auto_task = asyncio.create_task(self._run_auto_sender())

    @commands.Cog.listener("on_message")
    async def on_apostado_pix_name(self, message: disnake.Message):
        if not message.guild or message.author.bot:
            return

        cfg = self._get_config(message.guild.id)
        if not as_bool(cfg.get("enabled"), False) or not as_bool(cfg.get("pix_name_confirmation"), True):
            return

        queues = self._get_queues(cfg)
        queue_id = ""
        queue = None
        for current_id, current_queue in queues.items():
            if str(current_queue.get("match_channel_id") or "") == str(message.channel.id):
                queue_id = current_id
                queue = current_queue
                break
        if not queue:
            return

        players = self._normalise_players(queue)
        user_id = str(message.author.id)
        if user_id not in {str(player.get("id")) for player in players}:
            return

        raw_name = str(message.content or "").strip()
        if len(raw_name) < 5 or len(raw_name) > 80 or "http" in raw_name.lower() or "@" in raw_name:
            return
        clean = _clean_name(raw_name)
        words = [word for word in clean.split() if len(word) >= 2]
        if len(words) < 2:
            return

        payments = queue.get("payments") if isinstance(queue.get("payments"), dict) else {}
        payment = payments.setdefault(user_id, {"status": "pending", "pix_name": "", "confirmed_at": None})
        if payment.get("status") == "confirmed":
            return

        payment.update(
            {
                "status": "confirmed",
                "pix_name": raw_name[:80],
                "confirmed_at": _now(),
                "confirmed_ts": _now_ts(),
                "confirmed_by_message_id": str(message.id),
            }
        )
        queue["payments"] = payments
        self._save_config(message.guild.id, cfg)
        await self._refresh_match_message(message.guild, cfg, queue_id, queue)
        await self._send_log(
            message.guild,
            cfg,
            f"{emoji.correct} Pix confirmado por nome na partida `{queue.get('name', queue_id)}`.\n"
            f"Jogador: {message.author.mention}\n"
            f"Nome informado: `{raw_name[:80]}`",
        )

        if self._all_payments_confirmed(queue):
            role_mentions = " ".join(f"<@&{role_id}>" for role_id in (cfg.get("mediadores") or [])[:3])
            await message.channel.send(
                f"{emoji.correct} Todos os jogadores confirmaram o nome do Pix. {role_mentions}".strip()
            )
        else:
            await message.reply(f"{emoji.correct} Pagamento confirmado pelo nome `{raw_name[:80]}`.", mention_author=False)

    async def _handle_queue_button(self, inter: disnake.MessageInteraction):
        parts = inter.component.custom_id.split(":")
        if len(parts) < 3:
            await inter.response.send_message(f"{emoji.wrong} Botao de fila invalido.", ephemeral=True)
            return

        action = parts[0].split("_", 1)[1]
        guild_id = int(parts[1])
        queue_id = parts[2]
        cfg = self._get_config(guild_id)
        queues = self._get_queues(cfg)
        queue = queues.get(queue_id)
        if not queue:
            await inter.response.send_message(f"{emoji.wrong} Essa fila nao existe mais.", ephemeral=True)
            return

        players = self._normalise_players(queue)
        user_id = str(inter.user.id)

        if action == "Close":
            if not self._can_manage_queue(inter, cfg):
                await inter.response.send_message(f"{emoji.wrong} Apenas administradores ou mediadores podem fechar a fila.", ephemeral=True)
                return
            queue["closed"] = True
            self._save_config(guild_id, cfg)
            await inter.response.edit_message(components=self._build_queue_components(guild_id, queue_id, queue), flags=self._flags())
            await self._send_log(inter.guild, cfg, f"Fila ApostadoFF fechada: `{queue.get('name', queue_id)}`.")
            return

        if queue.get("closed"):
            await inter.response.send_message(f"{emoji.wrong} Essa fila esta fechada.", ephemeral=True)
            return

        if action == "Leave":
            before = len(players)
            queue["players"] = [player for player in players if str(player.get("id")) != user_id]
            self._save_config(guild_id, cfg)
            await inter.response.edit_message(components=self._build_queue_components(guild_id, queue_id, queue), flags=self._flags())
            text = "Voce saiu da fila." if len(queue["players"]) != before else "Voce nao estava nessa fila."
            await inter.followup.send(f"{emoji.correct} {text}", ephemeral=True)
            return

        if action == "Join":
            if len(parts) < 4:
                await inter.response.send_message(f"{emoji.wrong} Botao de entrada invalido.", ephemeral=True)
                return
            blocked = self._is_blacklisted(cfg, user_id)
            if blocked:
                await inter.response.send_message(
                    f"{emoji.wrong} Voce esta bloqueado de entrar em apostas. Motivo: `{blocked.get('reason') or 'Nao informado'}`",
                    ephemeral=True,
                )
                return
            option_index = int(parts[3])
            options = self._normalise_options(queue.get("options"))
            option = options[option_index] if option_index < len(options) else options[0]
            capacity = self._queue_capacity(queue)
            existing = next((player for player in players if str(player.get("id")) == user_id), None)
            if existing:
                existing["option"] = option
            else:
                if len(players) >= capacity:
                    await inter.response.send_message(f"{emoji.wrong} Essa fila ja esta cheia.", ephemeral=True)
                    return
                players.append({"id": user_id, "option": option})

            queue_full = len(players) >= capacity
            if queue_full and as_bool(cfg.get("auto_close_full"), True):
                queue["closed"] = True

            self._save_config(guild_id, cfg)
            await inter.response.edit_message(components=self._build_queue_components(guild_id, queue_id, queue), flags=self._flags())
            await inter.followup.send(f"{emoji.correct} Voce entrou na fila como `{option}`.", ephemeral=True)
            if queue_full:
                channel = await self._create_match_channel(inter, cfg, queue_id, queue)
                if channel:
                    await inter.followup.send(f"{emoji.correct} Fila completa. Partida organizada em {channel.mention}.", ephemeral=True)
                if cfg.get("creation_mode") == "automatic" and as_bool(cfg.get("auto_recreate"), True):
                    try:
                        new_queue_id = self._create_queue(cfg, self._queue_from_template(cfg, "automatic"))
                        self._save_config(guild_id, cfg)
                        sent = await self._send_queue_to_channel(inter.guild, inter.channel, guild_id, new_queue_id)
                        await inter.followup.send(f"{emoji.correct} Nova fila automatica enviada em {sent.channel.mention}.", ephemeral=True)
                    except Exception as exc:
                        await inter.followup.send(f"{emoji.wrong} Nao consegui recriar a fila automaticamente: `{exc}`", ephemeral=True)
                await self._send_log(inter.guild, cfg, f"Fila cheia: `{queue.get('name', queue_id)}` com {len(players)} jogadores.")

    async def _send_queue_selector(self, inter: disnake.MessageInteraction, guild_id: int, queues: dict):
        options = [
            disnake.SelectOption(
                label=(queue.get("name") or queue.get("mode") or queue_id)[:100],
                value=queue_id,
                description=(queue.get("mode") or "Fila Free Fire")[:100],
            )
            for queue_id, queue in list(queues.items())[:25]
        ]
        await inter.response.send_message(
            "Escolha qual fila deseja enviar.",
            components=[
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Selecionar fila",
                        custom_id=f"Apostado_SelectSendQueue:{guild_id}",
                        options=options,
                    )
                )
            ],
            ephemeral=True,
        )

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if cid.startswith("ApostadoFila_"):
            await self._handle_queue_button(inter)
            return

        if not cid.startswith("Apostado_"):
            return

        parts = cid.split(":")
        action = parts[0].split("_")[1]
        guild_id = int(parts[1]) if len(parts) > 1 else inter.guild.id
        cfg = self._get_config(guild_id)

        if action not in {"Start", "History", "Saldo", "MatchDispute"} and not self._can_manage_queue(inter, cfg):
            await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para configurar o ApostadoFF.", ephemeral=True)
            return

        if action in {"OpenMenu", "Back"}:
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            return

        if action == "Start":
            await inter.response.send_message("Use **Enviar Fila** para publicar o painel de apostas.", ephemeral=True)
            return

        if action == "History":
            await inter.response.send_message(f"**Historico ApostadoFF**\n{self._history_text(cfg)}", ephemeral=True)
            return

        if action == "Saldo":
            coin_name = cfg.get("coin_name", "Coins")
            await inter.response.send_message(f"Seu saldo: `0 {coin_name}`.", ephemeral=True)
            return

        if action in {"MatchPay", "MatchWinner", "MatchDispute"}:
            queue_id = parts[2] if len(parts) > 2 else None
            queues = self._get_queues(cfg)
            queue = queues.get(queue_id) if queue_id else None
            if not queue:
                await inter.response.send_message(f"{emoji.wrong} Fila da partida nao encontrada.", ephemeral=True)
                return
            players = {str(player.get("id")) for player in self._normalise_players(queue)}
            is_player = str(inter.user.id) in players
            if action != "MatchDispute" and not self._can_manage_queue(inter, cfg):
                await inter.response.send_message(f"{emoji.wrong} Apenas administradores ou mediadores podem alterar a partida.", ephemeral=True)
                return
            if action == "MatchDispute" and not (is_player or self._can_manage_queue(inter, cfg)):
                await inter.response.send_message(f"{emoji.wrong} Apenas jogadores da partida ou mediadores podem abrir disputa.", ephemeral=True)
                return

            cog = self

            if action == "MatchPay":
                class ManualPaymentModal(disnake.ui.Modal):
                    def __init__(self):
                        super().__init__(
                            title="Confirmar Pix Manual",
                            custom_id=f"Apostado_MatchPay_Modal:{guild_id}:{queue_id}",
                            components=[
                                disnake.ui.TextInput(label="Usuario", custom_id="user_id", placeholder="ID ou mencao do jogador", required=True, max_length=32),
                                disnake.ui.TextInput(label="Nome que veio no Pix", custom_id="pix_name", placeholder="Ex.: Thiago Henrike", required=True, max_length=80),
                            ],
                        )

                    async def callback(self, modal_inter: disnake.ModalInteraction):
                        values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                        cfg_local = cog._get_config(guild_id)
                        queue_local = cog._get_queues(cfg_local).get(queue_id)
                        if not queue_local:
                            await modal_inter.response.send_message(f"{emoji.wrong} Partida nao encontrada.", ephemeral=True)
                            return
                        target_id = _clean_id(values.get("user_id"))
                        players = {str(player.get("id")) for player in cog._normalise_players(queue_local)}
                        if not target_id or target_id not in players:
                            await modal_inter.response.send_message(f"{emoji.wrong} Esse usuario nao esta nesta partida.", ephemeral=True)
                            return
                        payments = queue_local.get("payments") if isinstance(queue_local.get("payments"), dict) else {}
                        payments[target_id] = {
                            "status": "confirmed",
                            "pix_name": str(values.get("pix_name") or "").strip()[:80],
                            "confirmed_at": _now(),
                            "confirmed_ts": _now_ts(),
                            "confirmed_by_staff": str(modal_inter.user.id),
                        }
                        queue_local["payments"] = payments
                        cog._save_config(guild_id, cfg_local)
                        await cog._refresh_match_message(modal_inter.guild, cfg_local, queue_id, queue_local)
                        await cog._send_log(modal_inter.guild, cfg_local, f"{emoji.correct} Pix confirmado manualmente para <@{target_id}> por {modal_inter.user.mention}.")
                        await modal_inter.response.send_message(f"{emoji.correct} Pix de <@{target_id}> confirmado.", ephemeral=True)

                await inter.response.send_modal(ManualPaymentModal())
                return

            if action == "MatchWinner":
                class WinnerModal(disnake.ui.Modal):
                    def __init__(self):
                        super().__init__(
                            title="Registrar Vencedor",
                            custom_id=f"Apostado_MatchWinner_Modal:{guild_id}:{queue_id}",
                            components=[
                                disnake.ui.TextInput(label="Vencedor(es)", custom_id="winner_ids", placeholder="IDs ou mencoes dos vencedores", required=True, max_length=120),
                                disnake.ui.TextInput(label="Observacao", custom_id="note", placeholder="Opcional", required=False, max_length=300),
                            ],
                        )

                    async def callback(self, modal_inter: disnake.ModalInteraction):
                        values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                        cfg_local = cog._get_config(guild_id)
                        queue_local = cog._get_queues(cfg_local).get(queue_id)
                        if not queue_local:
                            await modal_inter.response.send_message(f"{emoji.wrong} Partida nao encontrada.", ephemeral=True)
                            return
                        raw = str(values.get("winner_ids") or "")
                        ids = re.findall(r"\d{15,22}", raw)
                        players = {str(player.get("id")) for player in cog._normalise_players(queue_local)}
                        winners = [user_id for user_id in ids if user_id in players]
                        if not winners:
                            await modal_inter.response.send_message(f"{emoji.wrong} Informe pelo menos um jogador que esteja nesta partida.", ephemeral=True)
                            return
                        queue_local["winner_ids"] = list(dict.fromkeys(winners))
                        queue_local["result_note"] = str(values.get("note") or "").strip()[:300]
                        cog._save_config(guild_id, cfg_local)
                        await cog._refresh_match_message(modal_inter.guild, cfg_local, queue_id, queue_local)
                        await cog._send_log(modal_inter.guild, cfg_local, f"{_get_emoji('trophy')} Vencedor registrado em `{queue_local.get('name', queue_id)}`: " + ", ".join(f"<@{uid}>" for uid in queue_local["winner_ids"]))
                        await modal_inter.response.send_message(f"{emoji.correct} Vencedor registrado. Agora a staff pode finalizar a partida.", ephemeral=True)

                await inter.response.send_modal(WinnerModal())
                return

            class DisputeModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Abrir Disputa",
                        custom_id=f"Apostado_MatchDispute_Modal:{guild_id}:{queue_id}",
                        components=[
                            disnake.ui.TextInput(label="Alvo da disputa", custom_id="target_id", placeholder="ID/mencao opcional", required=False, max_length=32),
                            disnake.ui.TextInput(label="Motivo", custom_id="reason", style=disnake.TextInputStyle.paragraph, required=True, max_length=700),
                            disnake.ui.TextInput(label="Prova em texto/link", custom_id="proof", style=disnake.TextInputStyle.paragraph, required=False, max_length=700),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    cfg_local = cog._get_config(guild_id)
                    queue_local = cog._get_queues(cfg_local).get(queue_id)
                    if not queue_local:
                        await modal_inter.response.send_message(f"{emoji.wrong} Partida nao encontrada.", ephemeral=True)
                        return
                    dispute = {
                        "id": f"disp-{queue_id}-{_now_ts()}",
                        "queue_id": queue_id,
                        "opened_by": str(modal_inter.user.id),
                        "target_id": _clean_id(values.get("target_id")),
                        "reason": str(values.get("reason") or "").strip()[:700],
                        "proof": str(values.get("proof") or "").strip()[:700],
                        "status": "open",
                        "created_at": _now(),
                        "created_ts": _now_ts(),
                    }
                    queue_disputes = queue_local.get("disputes") if isinstance(queue_local.get("disputes"), list) else []
                    queue_disputes.append(dispute)
                    queue_local["disputes"] = queue_disputes[-20:]
                    queue_local["match_status"] = "disputa"
                    disputes = cfg_local.setdefault("disputes", [])
                    if not isinstance(disputes, list):
                        disputes = []
                    disputes.append(dispute)
                    cfg_local["disputes"] = disputes[-300:]
                    ranking = cfg_local.setdefault("ranking", {})
                    for player in cog._normalise_players(queue_local):
                        stats = ranking.setdefault(str(player.get("id")), {"wins": 0, "losses": 0, "matches": 0, "profit": 0.0, "disputes": 0})
                        stats["disputes"] = int(stats.get("disputes", 0)) + 1
                    cog._save_config(guild_id, cfg_local)
                    await cog._refresh_match_message(modal_inter.guild, cfg_local, queue_id, queue_local)
                    await cog._send_log(modal_inter.guild, cfg_local, f"{emoji.warn} Disputa aberta em `{queue_local.get('name', queue_id)}` por {modal_inter.user.mention}.\nMotivo: `{dispute['reason']}`")
                    await modal_inter.response.send_message(f"{emoji.correct} Disputa registrada e enviada para os logs.", ephemeral=True)

            await inter.response.send_modal(DisputeModal())
            return

        if action == "Blacklist":
            source_message = inter.message
            cog = self

            class BlacklistModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Blacklist ApostadoFF",
                        custom_id=f"Apostado_Blacklist_Modal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(label="Usuario", custom_id="user_id", placeholder="ID ou mencao do usuario", required=True, max_length=32),
                            disnake.ui.TextInput(label="Acao", custom_id="action", placeholder="adicionar ou remover", required=True, max_length=12),
                            disnake.ui.TextInput(label="Motivo", custom_id="reason", placeholder="Obrigatorio ao adicionar", required=False, max_length=240),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    target_id = _clean_id(values.get("user_id"))
                    mode = str(values.get("action") or "").strip().lower()
                    reason = str(values.get("reason") or "").strip()[:240]
                    if not target_id:
                        await modal_inter.response.send_message(f"{emoji.wrong} Informe um ID ou mencao valida.", ephemeral=True)
                        return
                    if mode not in {"adicionar", "add", "remover", "remove", "tirar"}:
                        await modal_inter.response.send_message(f"{emoji.wrong} Use `adicionar` ou `remover`.", ephemeral=True)
                        return

                    cfg_local = cog._get_config(guild_id)
                    blacklist = cfg_local.setdefault("blacklist", {})
                    if not isinstance(blacklist, dict):
                        blacklist = {}
                    adding = mode in {"adicionar", "add"}
                    if adding:
                        blacklist[target_id] = {
                            "active": True,
                            "reason": reason or "Sem motivo informado",
                            "created_at": _now(),
                            "created_ts": _now_ts(),
                            "created_by": str(modal_inter.user.id),
                        }
                        result = f"{emoji.correct} <@{target_id}> bloqueado de entrar nas apostas."
                        log_text = f"{emoji.warn} Blacklist ApostadoFF: <@{target_id}> bloqueado por {modal_inter.user.mention}. Motivo: `{blacklist[target_id]['reason']}`"
                    else:
                        entry = blacklist.setdefault(target_id, {})
                        if isinstance(entry, dict):
                            entry["active"] = False
                            entry["removed_at"] = _now()
                            entry["removed_ts"] = _now_ts()
                            entry["removed_by"] = str(modal_inter.user.id)
                        result = f"{emoji.correct} <@{target_id}> removido da blacklist."
                        log_text = f"{emoji.correct} Blacklist ApostadoFF: <@{target_id}> liberado por {modal_inter.user.mention}."

                    cfg_local["blacklist"] = blacklist
                    cog._save_config(guild_id, cfg_local)
                    await cog._send_log(modal_inter.guild, cfg_local, log_text)
                    await cog._finish_modal(modal_inter, source_message, guild_id, result)

            await inter.response.send_modal(BlacklistModal())
            return

        if action in {"MatchFinish", "MatchCancel"}:
            if not self._can_manage_queue(inter, cfg):
                await inter.response.send_message(f"{emoji.wrong} Apenas administradores ou mediadores podem alterar a partida.", ephemeral=True)
                return
            queue_id = parts[2] if len(parts) > 2 else None
            queues = self._get_queues(cfg)
            queue = queues.get(queue_id) if queue_id else None
            if not queue:
                await inter.response.send_message(f"{emoji.wrong} Fila da partida nao encontrada.", ephemeral=True)
                return

            status_text = "finalizada" if action == "MatchFinish" else "cancelada"
            queue["match_status"] = status_text
            queue["closed"] = True
            if queue.get("history_recorded_status") != status_text:
                record = self._record_match(cfg, queue_id, queue, status_text, actor_id=str(inter.user.id))
                queue["history_recorded_status"] = status_text
                queue["history_record_id"] = record.get("id")
            self._save_config(guild_id, cfg)
            winners = ", ".join(f"<@{user_id}>" for user_id in queue.get("winner_ids", [])[:6]) or "`sem vencedor`"
            await inter.response.edit_message(
                components=[
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(f"## {_get_emoji('swords', '')} Partida {status_text.title()}"),
                        disnake.ui.TextDisplay(
                            f"A partida `{queue.get('name') or queue_id}` foi marcada como **{status_text}** por {inter.author.mention}.\n"
                            f"**Vencedor:** {winners}"
                            + (f"\n**Observacao:** {queue.get('result_note')}" if queue.get("result_note") else "")
                        ),
                        **self._container_kwargs(),
                    )
                ],
                flags=self._flags(),
            )
            await self._send_log(inter.guild, cfg, f"Partida ApostadoFF {status_text}: `{queue.get('name', queue_id)}`.")
            return

        if action == "Activate":
            cfg["enabled"] = not as_bool(cfg.get("enabled"), False)
            cfg.setdefault("container_mode", True)
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            status = "ativado" if cfg["enabled"] else "desativado"
            await inter.followup.send(f"{emoji.correct} ApostadoFF {status}.", ephemeral=True)
            return

        if action == "ContainerToggle":
            cfg["container_mode"] = not as_bool(cfg.get("container_mode"), True)
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            status = "ativo" if cfg["container_mode"] else "inativo"
            await inter.followup.send(f"{emoji.correct} Modo Container V2 {status}.", ephemeral=True)
            return

        if action == "AutoToggle":
            cfg["auto_send_enabled"] = not as_bool(cfg.get("auto_send_enabled"), False)
            cfg.setdefault("auto_interval_minutes", 60)
            cfg["last_auto_send_ts"] = 0
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            status = "ativo" if cfg["auto_send_enabled"] else "inativo"
            await inter.followup.send(f"{emoji.correct} Envio automatico {status}.", ephemeral=True)
            return

        if action == "Mode":
            modes = list(CREATION_MODES)
            current = cfg.get("creation_mode") if cfg.get("creation_mode") in modes else "manual"
            cfg["creation_mode"] = modes[(modes.index(current) + 1) % len(modes)]
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            await inter.followup.send(f"{emoji.correct} Modo das filas definido para `{CREATION_MODES[cfg['creation_mode']]}`.", ephemeral=True)
            return

        if action in {"AutoRecreate", "AutoClose", "PixAutoToggle"}:
            key = {
                "AutoRecreate": "auto_recreate",
                "AutoClose": "auto_close_full",
                "PixAutoToggle": "pix_name_confirmation",
            }[action]
            cfg[key] = not as_bool(cfg.get(key), True)
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            await inter.followup.send(f"{emoji.correct} Configuracao atualizada.", ephemeral=True)
            return

        if action == "ManageQueue":
            await self._edit_components(inter, self._build_queue_manager_panel(guild_id))
            return

        if action in {"QueueResend", "QueueReopen", "QueueClose", "QueueClear", "QueueDelete"}:
            queues = self._get_queues(cfg)
            queue_id = self._latest_queue_id(cfg)
            queue = queues.get(queue_id) if queue_id else None
            if not queue:
                await inter.response.send_message(f"{emoji.wrong} Nenhuma fila encontrada.", ephemeral=True)
                return

            if not inter.response.is_done():
                await inter.response.defer(ephemeral=True)

            if action == "QueueResend":
                sent = await self._send_queue_message(inter, guild_id, queue_id)
                await inter.followup.send(f"{emoji.correct} Fila reenviada em {sent.channel.mention}.", ephemeral=True)
            elif action == "QueueReopen":
                queue["closed"] = False
                await self._refresh_queue_message(inter.guild, cfg, queue_id, queue)
                await inter.followup.send(f"{emoji.correct} Fila reaberta.", ephemeral=True)
            elif action == "QueueClose":
                queue["closed"] = True
                await self._refresh_queue_message(inter.guild, cfg, queue_id, queue)
                await inter.followup.send(f"{emoji.correct} Fila fechada.", ephemeral=True)
            elif action == "QueueClear":
                queue["players"] = []
                queue["closed"] = False
                queue["payments"] = {}
                await self._refresh_queue_message(inter.guild, cfg, queue_id, queue)
                await inter.followup.send(f"{emoji.correct} Jogadores removidos da fila.", ephemeral=True)
            elif action == "QueueDelete":
                queues.pop(queue_id, None)
                cfg["last_queue_id"] = self._latest_queue_id(cfg)
                await inter.followup.send(f"{emoji.correct} Fila deletada da configuracao.", ephemeral=True)
            self._save_config(guild_id, cfg)
            try:
                await inter.message.edit(components=self._build_queue_manager_panel(guild_id), flags=self._flags())
            except Exception:
                pass
            return

        if action == "Canais":
            await self._edit_components(inter, self._build_channels_panel(guild_id))
            return

        if action == "Mediadores":
            await self._edit_components(inter, self._build_roles_panel(guild_id, "mediadores"))
            return

        if action == "Analistas":
            await self._edit_components(inter, self._build_roles_panel(guild_id, "analistas"))
            return

        if action == "SendQueue":
            if not as_bool(cfg.get("enabled"), False):
                await inter.response.send_message(f"{emoji.wrong} Ative o ApostadoFF antes de enviar uma fila.", ephemeral=True)
                return
            queues = self._get_queues(cfg)
            if cfg.get("creation_mode") == "automatic":
                sent = await self._send_queue_message(inter, guild_id, None)
                await inter.response.send_message(f"{emoji.correct} Fila automatica enviada em {sent.channel.mention}.", ephemeral=True)
                return
            if len(queues) > 1:
                await self._send_queue_selector(inter, guild_id, queues)
                return
            queue_id = self._ensure_queue(cfg)
            self._save_config(guild_id, cfg)
            sent = await self._send_queue_message(inter, guild_id, queue_id)
            await inter.response.send_message(f"{emoji.correct} Fila enviada em {sent.channel.mention}.", ephemeral=True)
            return

        if action == "Template":
            source_message = inter.message
            cog = self
            template = cfg.get("queue_template") if isinstance(cfg.get("queue_template"), dict) else self._default_template()

            class TemplateModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Modelo da fila",
                        custom_id=f"Apostado_Template_Modal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(label="Titulo padrao", custom_id="name", value=str(template.get("name") or "2v2 Mobile")[:60], required=True, max_length=60),
                            disnake.ui.TextInput(label="Modo padrao", custom_id="mode", value=str(template.get("mode") or "2v2 Mobile")[:60], required=True, max_length=60),
                            disnake.ui.TextInput(label="Valor padrao", custom_id="value", value=str(template.get("value") or "5.00")[:16], required=True, max_length=16),
                            disnake.ui.TextInput(label="Capacidade", custom_id="capacity", value=str(template.get("capacity") or 4)[:3], required=True, max_length=3),
                            disnake.ui.TextInput(label="Botoes separados por virgula", custom_id="options", value=", ".join(cog._normalise_options(template.get("options")))[:100], required=False, max_length=100),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    cfg_local = cog._get_config(guild_id)
                    try:
                        capacity = max(2, min(50, int(str(values.get("capacity") or "4").strip())))
                    except Exception:
                        capacity = cog._queue_capacity(values.get("mode"))
                    cfg_local["queue_template"] = {
                        "name": str(values.get("name") or "2v2 Mobile").strip(),
                        "mode": str(values.get("mode") or "2v2 Mobile").strip(),
                        "value": str(values.get("value") or "5.00").strip(),
                        "capacity": capacity,
                        "options": cog._normalise_options(values.get("options")),
                    }
                    cog._save_config(guild_id, cfg_local)
                    await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Modelo de fila atualizado.")

            await inter.response.send_modal(TemplateModal())
            return

        if action == "PixConfig":
            source_message = inter.message
            cog = self

            class PixModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Pagamento Pix do Apostado",
                        custom_id=f"Apostado_PixConfig_Modal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(label="Nome do recebedor", custom_id="pix_receiver_name", value=str(cfg.get("pix_receiver_name") or "")[:80], required=False, max_length=80),
                            disnake.ui.TextInput(label="Chave Pix", custom_id="pix_key", value=str(cfg.get("pix_key") or "")[:120], required=False, max_length=120),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    cfg_local = cog._get_config(guild_id)
                    cfg_local["pix_receiver_name"] = str(values.get("pix_receiver_name") or "").strip()
                    cfg_local["pix_key"] = str(values.get("pix_key") or "").strip()
                    cog._save_config(guild_id, cfg_local)
                    await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Dados Pix do Apostado atualizados.")

            await inter.response.send_modal(PixModal())
            return

        if action == "Taxa":
            source_message = inter.message
            cog = self

            class FeeModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Configurar taxa",
                        custom_id=f"Apostado_Taxa_Modal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(
                                label="Taxa de servico",
                                custom_id="service_fee",
                                placeholder="Ex.: 1.80",
                                required=True,
                                max_length=12,
                            )
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    raw_value = values.get("service_fee", "").replace(",", ".").strip()
                    try:
                        value = max(0, float(raw_value))
                    except Exception:
                        await modal_inter.response.send_message(f"{emoji.wrong} Taxa invalida.", ephemeral=True)
                        return
                    cfg_local = cog._get_config(guild_id)
                    cfg_local["service_fee"] = round(value, 2)
                    cog._save_config(guild_id, cfg_local)
                    await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Taxa definida para `R$ {value:.2f}`.")

            await inter.response.send_modal(FeeModal())
            return

        if action == "AutoInterval":
            source_message = inter.message
            cog = self

            class AutoIntervalModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Intervalo automatico",
                        custom_id=f"Apostado_AutoInterval_Modal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(
                                label="Intervalo em minutos",
                                custom_id="interval_minutes",
                                placeholder="Ex.: 60",
                                required=True,
                                max_length=5,
                            )
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    try:
                        interval = cog._format_interval(values.get("interval_minutes"))
                    except Exception:
                        await modal_inter.response.send_message(f"{emoji.wrong} Intervalo invalido.", ephemeral=True)
                        return
                    cfg_local = cog._get_config(guild_id)
                    cfg_local["auto_interval_minutes"] = interval
                    cfg_local["last_auto_send_ts"] = 0
                    cog._save_config(guild_id, cfg_local)
                    await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Envio automatico definido para cada `{interval}` minuto(s).")

            await inter.response.send_modal(AutoIntervalModal())
            return

        if action == "Coins":
            source_message = inter.message
            cog = self

            class CoinsModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Configurar coins",
                        custom_id=f"Apostado_Coins_Modal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(label="Nome da moeda", custom_id="coin_name", placeholder="Ex.: Coins", required=True, max_length=32),
                            disnake.ui.TextInput(label="Coins por vitoria", custom_id="win_coins", placeholder="Ex.: 10", required=True, max_length=8),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    coin_name = values.get("coin_name", "Coins").strip() or "Coins"
                    try:
                        win_coins = max(0, int(values.get("win_coins", "0")))
                    except Exception:
                        await modal_inter.response.send_message(f"{emoji.wrong} Quantidade invalida.", ephemeral=True)
                        return
                    cfg_local = cog._get_config(guild_id)
                    cfg_local["coin_name"] = coin_name
                    cfg_local["win_coins"] = win_coins
                    cog._save_config(guild_id, cfg_local)
                    await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Coins configurados.")

            await inter.response.send_modal(CoinsModal())
            return

        if action == "Filas":
            source_message = inter.message
            cog = self

            class QueueModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Configurar fila",
                        custom_id=f"Apostado_Filas_Modal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(label="Titulo da fila", custom_id="name", placeholder="Ex.: 2v2 Mobile", required=True, max_length=60),
                            disnake.ui.TextInput(label="Modo", custom_id="mode", placeholder="Ex.: 2v2 Mobile", required=True, max_length=60),
                            disnake.ui.TextInput(label="Valor da partida", custom_id="value", placeholder="Ex.: 5.00", required=True, max_length=16),
                            disnake.ui.TextInput(label="Capacidade", custom_id="capacity", placeholder="Ex.: 4", required=False, max_length=3),
                            disnake.ui.TextInput(label="Botoes separados por virgula", custom_id="options", placeholder="Normal, Full Ump Xm8, Mobilador", required=False, max_length=100),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    name = values.get("name", "").strip()
                    mode = values.get("mode", "").strip()
                    value = values.get("value", "").strip()
                    if not name or not mode:
                        await modal_inter.response.send_message(f"{emoji.wrong} Informe titulo e modo da fila.", ephemeral=True)
                        return
                    try:
                        capacity = max(2, min(50, int(str(values.get("capacity") or "").strip())))
                    except Exception:
                        capacity = cog._queue_capacity(mode)
                    cfg_local = cog._get_config(guild_id)
                    queues = cog._get_queues(cfg_local)
                    queue_id = secrets.token_hex(3)
                    queues[queue_id] = {
                        "name": name,
                        "mode": mode,
                        "value": value,
                        "capacity": capacity,
                        "options": cog._normalise_options(values.get("options")),
                        "players": [],
                        "closed": False,
                        "source": "custom",
                        "created_at": _now(),
                    }
                    cfg_local["last_queue_id"] = queue_id
                    cog._save_config(guild_id, cfg_local)
                    await cog._finish_modal(modal_inter, source_message, guild_id, f"{emoji.correct} Fila `{name}` salva. Use **Enviar Fila** para mandar no canal.")

            await inter.response.send_modal(QueueModal())
            return

        if action == "Ranking":
            await inter.response.send_message(f"**Ranking ApostadoFF**\n{self._ranking_text(cfg)}", ephemeral=True)
            return

        if action == "Modelo":
            cfg["server_model_enabled"] = not cfg.get("server_model_enabled", False)
            self._save_config(guild_id, cfg)
            status = "ativado" if cfg["server_model_enabled"] else "desativado"
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            await inter.followup.send(f"{emoji.correct} Modelo de servidor apostado {status}.", ephemeral=True)

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if not cid.startswith("Apostado_Select"):
            return

        parts = cid.split(":")
        action = parts[0].split("_", 1)[1]
        guild_id = int(parts[-1]) if len(parts) > 1 else inter.guild.id
        cfg = self._get_config(guild_id)

        if not self._can_manage_queue(inter, cfg):
            await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para configurar o ApostadoFF.", ephemeral=True)
            return

        if action == "SelectSendQueue":
            queue_id = inter.values[0]
            sent = await self._send_queue_message(inter, guild_id, queue_id)
            await inter.response.edit_message(content=f"{emoji.correct} Fila enviada em {sent.channel.mention}.", components=[])
            return

        if action == "SelectQueueChannel":
            channel_id = int(inter.values[0])
            cfg["queue_channel"] = channel_id
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            await inter.followup.send(f"{emoji.correct} Canal das filas definido para <#{channel_id}>.", ephemeral=True)
            return

        if action == "SelectCategory":
            channel_id = int(inter.values[0])
            cfg["category"] = channel_id
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            await inter.followup.send(f"{emoji.correct} Categoria de apostas definida para <#{channel_id}>.", ephemeral=True)
            return

        if action == "SelectLogs":
            channel_id = int(inter.values[0])
            cfg["logs_channel"] = channel_id
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            await inter.followup.send(f"{emoji.correct} Canal de logs definido para <#{channel_id}>.", ephemeral=True)
            return

        if action == "SelectRoles":
            role_type = parts[1] if len(parts) > 2 else None
            if role_type not in {"mediadores", "analistas"}:
                await inter.response.send_message(f"{emoji.wrong} Tipo de cargo invalido.", ephemeral=True)
                return
            role_ids = [int(value) for value in inter.values]
            cfg[role_type] = role_ids
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_apostado_panel(guild_id))
            await inter.followup.send(f"{emoji.correct} Cargos de {role_type} atualizados.", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(ApostadoFreeFire(bot))
