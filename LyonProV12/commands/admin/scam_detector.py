from __future__ import annotations

import io
import re
import time
import unicodedata
from datetime import datetime

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import load_guild_channels
from functions.system_logs import ensure_guild_log_channel


CONFIG_KEY = "scam_detector_config"
LOG_KEY = "scam_detector_logs"


DEFAULT_RULES = [
    {
        "name": "Negociar fora do ticket",
        "pattern": r"\b(fora do ticket|fora do servidor|fora do discord|chama no pv|me chama no pv|chama privado|me chama privado|chama dm|me chama dm)\b",
        "score": 5,
    },
    {
        "name": "Evitar equipe/middleman",
        "pattern": r"\b(sem mm|sem middleman|nao chama (a )?(staff|equipe|admin|adm|middleman|mm)|nao fala com (a )?(staff|equipe|admin|adm))\b",
        "score": 5,
    },
    {
        "name": "Pressao para pagar/enviar primeiro",
        "pattern": r"\b(manda primeiro|envia primeiro|paga primeiro|pix antes|passa o pix antes|so libero depois|libero depois que pagar)\b",
        "score": 4,
    },
    {
        "name": "Pedido para apagar evidencias",
        "pattern": r"\b(apaga a mensagem|apaga isso|deleta a mensagem|limpa o chat|nao deixa print|sem print)\b",
        "score": 4,
    },
    {
        "name": "Contato externo",
        "pattern": r"\b(whatsapp|zap|telegram|t\.me|wa\.me|api\.whatsapp|instagram\.com|insta|chama no wpp)\b",
        "score": 3,
    },
    {
        "name": "Falsa confianca",
        "pattern": r"\b(confia em mim|sou confiavel|tenho vouches|nao vou dar golpe|relaxa que eu pago|relaxa que eu mando)\b",
        "score": 2,
    },
    {
        "name": "Termos diretos de golpe",
        "pattern": r"\b(golpe|scam|golpista|scammer|comprovante falso|fake receipt|chargeback|estorno depois)\b",
        "score": 3,
    },
    {
        "name": "Link suspeito",
        "pattern": r"\b(bit\.ly|tinyurl|is\.gd|grabify|iplogger|shorturl|discordgift|steamcomunnity)\b",
        "score": 4,
    },
    {
        "name": "Telefone no atendimento",
        "pattern": r"(\+?55\s*)?\(?\d{2}\)?\s*9?\d{4}[-.\s]?\d{4}",
        "score": 3,
    },
]


def _now_ts() -> int:
    return int(time.time())


def _emoji(name: str, fallback: str = ""):
    return getattr(emoji, name, None) or getattr(emoji, fallback, None) or ""


def _clean_text(text: str) -> str:
    raw = str(text or "").lower()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text).strip()


def _short(text: str, limit: int = 850) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _default_config() -> dict:
    return {
        "enabled": True,
        "monitor_tickets": True,
        "monitor_middleman": True,
        "ignore_staff": True,
        "alert_in_channel": True,
        "delete_message": False,
        "threshold": 4,
        "cooldown_seconds": 120,
        "evidence_messages": 12,
        "log_channel_id": "",
        "staff_role_ids": [],
        "custom_keywords": [],
    }


def _load_config() -> dict:
    config = db.get_document(CONFIG_KEY) or {}
    if not isinstance(config, dict):
        config = {}
    changed = False
    for key, value in _default_config().items():
        if key not in config:
            config[key] = value
            changed = True
    if changed:
        db.save_document(CONFIG_KEY, config)
    return config


def _save_config(config: dict) -> None:
    db.save_document(CONFIG_KEY, config)


def _append_detection(payload: dict) -> None:
    data = db.get_document(LOG_KEY) or {}
    detections = data.get("detections") if isinstance(data.get("detections"), list) else []
    detections.append(payload)
    data["detections"] = detections[-300:]
    db.save_document(LOG_KEY, data)


class ScamSensitivityModal(disnake.ui.Modal):
    def __init__(self):
        config = _load_config()
        components = [
            disnake.ui.TextInput(
                label="Pontuacao minima para alertar",
                custom_id="threshold",
                value=str(config.get("threshold", 4)),
                max_length=3,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Cooldown por usuario/canal (segundos)",
                custom_id="cooldown_seconds",
                value=str(config.get("cooldown_seconds", 120)),
                max_length=5,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Mensagens no arquivo de evidencia",
                custom_id="evidence_messages",
                value=str(config.get("evidence_messages", 12)),
                max_length=3,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Palavras extras (separadas por virgula)",
                custom_id="custom_keywords",
                value=", ".join(config.get("custom_keywords") or [])[:900],
                style=disnake.TextInputStyle.paragraph,
                max_length=900,
                required=False,
            ),
        ]
        super().__init__(title="Detector de Golpes", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        values = inter.text_values
        try:
            threshold = max(1, min(20, int(values.get("threshold", "4"))))
            cooldown = max(0, min(3600, int(values.get("cooldown_seconds", "120"))))
            evidence = max(3, min(30, int(values.get("evidence_messages", "12"))))
        except ValueError:
            await inter.response.send_message(f"{emoji.wrong} Informe numeros validos.", ephemeral=True)
            return

        keywords = [
            item.strip().lower()
            for item in str(values.get("custom_keywords") or "").split(",")
            if item.strip()
        ][:40]
        config = _load_config()
        config["threshold"] = threshold
        config["cooldown_seconds"] = cooldown
        config["evidence_messages"] = evidence
        config["custom_keywords"] = keywords
        _save_config(config)
        await inter.response.send_message(f"{emoji.correct} Sensibilidade do detector atualizada.", ephemeral=True)


class ScamDetectorPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldowns: dict[tuple[int, int], float] = {}

    @staticmethod
    def _channel_text(channel_id) -> str:
        return f"<#{channel_id}>" if channel_id else "`Nao configurado`"

    @staticmethod
    def _roles_text(role_ids) -> str:
        if not role_ids:
            return "`Automatico pelos cargos do ticket/MM`"
        return ", ".join(f"<@&{role_id}>" for role_id in role_ids[:8])

    def display_scam_detector_panel(self, inter: disnake.MessageInteraction):
        config = _load_config()
        logs = db.get_document(LOG_KEY) or {}
        detections = logs.get("detections") if isinstance(logs.get("detections"), list) else []
        enabled = bool(config.get("enabled", True))
        status = f"{_emoji('green')} `Ativo`" if enabled else f"{_emoji('red')} `Inativo`"
        shield = _emoji("shield", "warn")
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {shield} Detector de Golpes"),
                disnake.ui.TextDisplay(
                    "Monitora mensagens em **tickets** e **middleman**, detecta frases suspeitas, "
                    "alerta a equipe e registra um arquivo de evidencia com o contexto."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"{_emoji('chart')} **Status:** {status}\n"
                    f"{_emoji('ticket')} **Tickets:** `{'Ativo' if config.get('monitor_tickets') else 'Inativo'}`\n"
                    f"{_emoji('shield')} **Middleman:** `{'Ativo' if config.get('monitor_middleman') else 'Inativo'}`\n"
                    f"{_emoji('warn')} **Sensibilidade:** `{config.get('threshold', 4)} pontos`\n"
                    f"{_emoji('clock')} **Cooldown:** `{config.get('cooldown_seconds', 120)}s`\n"
                    f"{_emoji('textc')} **Logs:** {self._channel_text(config.get('log_channel_id'))}\n"
                    f"{_emoji('staff', 'members')} **Equipe marcada:** {self._roles_text(config.get('staff_role_ids') or [])}\n"
                    f"{_emoji('receipt')} **Alertas salvos:** `{len(detections)}`"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Desativar" if enabled else "Ativar",
                        style=disnake.ButtonStyle.red if enabled else disnake.ButtonStyle.green,
                        emoji=_emoji("power"),
                        custom_id="ScamDetector_Toggle",
                    ),
                    disnake.ui.Button(label="Sensibilidade", style=disnake.ButtonStyle.grey, emoji=_emoji("settings"), custom_id="ScamDetector_Sensitivity"),
                    disnake.ui.Button(label="Logs", style=disnake.ButtonStyle.grey, emoji=_emoji("textc"), custom_id="ScamDetector_Logs"),
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Equipe", style=disnake.ButtonStyle.blurple, emoji=_emoji("staff", "members"), custom_id="ScamDetector_Staff"),
                    disnake.ui.Button(label="Tickets", style=disnake.ButtonStyle.grey, emoji=_emoji("ticket"), custom_id="ScamDetector_ToggleTickets"),
                    disnake.ui.Button(label="Middleman", style=disnake.ButtonStyle.grey, emoji=_emoji("shield"), custom_id="ScamDetector_ToggleMiddleman"),
                    disnake.ui.Button(label="Alerta no canal", style=disnake.ButtonStyle.grey, emoji=_emoji("announcement", "warn"), custom_id="ScamDetector_ToggleChannelAlert"),
                ),
                accent_colour=disnake.Colour.red() if enabled else disnake.Colour.dark_grey(),
            )
        ]

    async def _refresh(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_scam_detector_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    @commands.Cog.listener("on_message_interaction")
    async def on_scam_detector_interaction(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("ScamDetector"):
            return

        if custom_id == "ScamDetector_Toggle":
            await inter.response.defer(ephemeral=True)
            config = _load_config()
            config["enabled"] = not bool(config.get("enabled", True))
            _save_config(config)
            await self._refresh(inter)
            await inter.followup.send(f"{emoji.correct} Detector {'ativado' if config['enabled'] else 'desativado'}.", ephemeral=True)
            return

        if custom_id == "ScamDetector_Sensitivity":
            await inter.response.send_modal(ScamSensitivityModal())
            return

        if custom_id in {"ScamDetector_ToggleTickets", "ScamDetector_ToggleMiddleman", "ScamDetector_ToggleChannelAlert"}:
            await inter.response.defer(ephemeral=True)
            config = _load_config()
            field = {
                "ScamDetector_ToggleTickets": "monitor_tickets",
                "ScamDetector_ToggleMiddleman": "monitor_middleman",
                "ScamDetector_ToggleChannelAlert": "alert_in_channel",
            }[custom_id]
            config[field] = not bool(config.get(field, True))
            _save_config(config)
            await self._refresh(inter)
            await inter.followup.send(f"{emoji.correct} Configuracao atualizada.", ephemeral=True)
            return

        if custom_id == "ScamDetector_Logs":
            await inter.response.send_message(
                "Selecione o canal para receber alertas do detector.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Canal de logs",
                            custom_id="ScamDetector_SelectLogs",
                            channel_types=[disnake.ChannelType.text],
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "ScamDetector_Staff":
            await inter.response.send_message(
                "Selecione os cargos marcados quando houver alerta.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.RoleSelect(
                            placeholder="Cargos da equipe",
                            custom_id="ScamDetector_SelectStaff",
                            min_values=1,
                            max_values=10,
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "ScamDetector_SelectLogs":
            config = _load_config()
            config["log_channel_id"] = int(inter.values[0])
            _save_config(config)
            await inter.response.send_message(f"{emoji.correct} Canal de logs definido em <#{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "ScamDetector_SelectStaff":
            config = _load_config()
            config["staff_role_ids"] = [int(value) for value in getattr(inter, "values", [])]
            _save_config(config)
            await inter.response.send_message(f"{emoji.correct} Cargos de alerta atualizados.", ephemeral=True)

    @commands.Cog.listener("on_message")
    async def on_scam_detector_message(self, message: disnake.Message):
        if not message.guild or message.author.bot:
            return

        config = _load_config()
        if not config.get("enabled", True):
            return

        context = self._find_middleman_context(message, config) or self._find_ticket_context(message, config)
        if not context:
            return

        if config.get("ignore_staff", True) and self._is_staff(message.author, context):
            return

        matches, score = self._match_rules(message.content or "", config)
        if score < int(config.get("threshold", 4)):
            return

        key = (message.channel.id, message.author.id)
        now = time.monotonic()
        cooldown = int(config.get("cooldown_seconds", 120) or 0)
        if cooldown and now - self._cooldowns.get(key, 0) < cooldown:
            return
        self._cooldowns[key] = now

        evidence_text = await self._build_evidence(message, context, matches, score, int(config.get("evidence_messages", 12) or 12))
        payload = {
            "guild_id": str(message.guild.id),
            "channel_id": str(message.channel.id),
            "message_id": str(message.id),
            "user_id": str(message.author.id),
            "user": str(message.author),
            "context_type": context["type"],
            "context_id": str(context.get("id") or ""),
            "score": score,
            "matches": [item["name"] for item in matches],
            "content": _short(message.content, 1200),
            "evidence": evidence_text[-8000:],
            "created_at": _now_ts(),
            "jump_url": message.jump_url,
        }
        _append_detection(payload)

        await self._send_alert(message, config, context, matches, score, evidence_text)

        if config.get("delete_message", False):
            try:
                await message.delete(reason="Detector de golpes")
            except disnake.HTTPException:
                pass

    def _find_middleman_context(self, message: disnake.Message, config: dict) -> dict | None:
        if not config.get("monitor_middleman", True):
            return None
        cfg = db.get_document(f"middleman_{message.guild.id}") or {}
        cases = cfg.get("cases") if isinstance(cfg.get("cases"), dict) else {}
        for case_id, case in cases.items():
            if str(case.get("channel_id")) == str(message.channel.id) and case.get("status") == "open":
                return {
                    "type": "Middleman",
                    "id": case_id,
                    "log_channel_id": cfg.get("logs_channel_id"),
                    "staff_role_ids": [int(role_id) for role_id in cfg.get("staff_roles", []) if str(role_id).isdigit()],
                }
        return None

    def _find_ticket_context(self, message: disnake.Message, config: dict) -> dict | None:
        if not config.get("monitor_tickets", True):
            return None
        tickets_data = db.get_document("tickets_data") or {}
        channel_id = str(message.channel.id)
        for panel_id, users in (tickets_data.get("panels") or {}).items():
            if not isinstance(users, dict):
                continue
            for user_id, tickets in users.items():
                if not isinstance(tickets, list):
                    continue
                for ticket in tickets:
                    if str(ticket.get("ticket_id")) != channel_id or ticket.get("status") == "closed":
                        continue
                    panel_config = (db.get_document("tickets_config") or {}).get("panels", {}).get(panel_id, {})
                    option_id = str(ticket.get("option_id") or "")
                    option_data = next(
                        (opt for opt in panel_config.get("options", []) if str(opt.get("id")) == option_id),
                        None,
                    )
                    roles_data = option_data.get("roles", {}) if option_data else panel_config.get("roles", {})
                    staff_roles = self._ticket_staff_roles(roles_data)
                    canais = load_guild_channels(message.guild)
                    return {
                        "type": "Ticket",
                        "id": panel_id,
                        "owner_id": user_id,
                        "log_channel_id": canais.get("canal_de_logs_de_tickets"),
                        "staff_role_ids": staff_roles,
                    }
        return None

    @staticmethod
    def _ticket_staff_roles(roles_data: dict) -> list[int]:
        role_ids = []
        if isinstance(roles_data, dict):
            for key in ("atendentes", "staff", "support"):
                values = roles_data.get(key)
                if isinstance(values, list):
                    role_ids.extend(values)
        return [int(role_id) for role_id in role_ids if str(role_id).isdigit()]

    @staticmethod
    def _is_staff(member: disnake.Member, context: dict) -> bool:
        permissions = getattr(member, "guild_permissions", None)
        if permissions and (permissions.manage_guild or permissions.administrator):
            return True
        staff_roles = {str(role_id) for role_id in context.get("staff_role_ids", [])}
        return any(str(role.id) in staff_roles for role in getattr(member, "roles", []) or [])

    @staticmethod
    def _match_rules(content: str, config: dict) -> tuple[list[dict], int]:
        clean = _clean_text(content)
        matches = []
        score = 0
        for rule in DEFAULT_RULES:
            if re.search(rule["pattern"], clean, flags=re.IGNORECASE):
                matches.append(rule)
                score += int(rule.get("score", 1))

        for keyword in config.get("custom_keywords") or []:
            kw = _clean_text(keyword)
            if kw and kw in clean:
                matches.append({"name": f"Palavra extra: {keyword}", "score": 3})
                score += 3

        return matches, score

    async def _build_evidence(self, message: disnake.Message, context: dict, matches: list[dict], score: int, limit: int) -> str:
        lines = [
            "DETECTOR DE GOLPES - EVIDENCIA",
            f"Data: {datetime.utcnow().isoformat(timespec='seconds')} UTC",
            f"Servidor: {message.guild.name} ({message.guild.id})",
            f"Sistema: {context.get('type')} ({context.get('id')})",
            f"Canal: #{getattr(message.channel, 'name', message.channel.id)} ({message.channel.id})",
            f"Usuario sinalizado: {message.author} ({message.author.id})",
            f"Pontuacao: {score}",
            f"Regras: {', '.join(item['name'] for item in matches)}",
            f"Link: {message.jump_url}",
            "",
            "CONTEXTO RECENTE",
        ]
        try:
            history = []
            async for msg in message.channel.history(limit=limit, oldest_first=False):
                history.append(msg)
            for msg in reversed(history):
                created_at = msg.created_at.isoformat(timespec="seconds") if msg.created_at else ""
                content = (msg.content or "").replace("\n", "\\n")
                attachments = ", ".join(att.url for att in getattr(msg, "attachments", []) or [])
                line = f"[{created_at}] {msg.author} ({msg.author.id}): {content}"
                if attachments:
                    line += f" | anexos: {attachments}"
                lines.append(line)
        except Exception as exc:
            lines.append(f"Falha ao coletar historico: {exc}")
        return "\n".join(lines)

    async def _send_alert(self, message: disnake.Message, config: dict, context: dict, matches: list[dict], score: int, evidence_text: str):
        role_ids = config.get("staff_role_ids") or context.get("staff_role_ids") or []
        mentions = " ".join(f"<@&{role_id}>" for role_id in role_ids[:8])
        log_channel_id = config.get("log_channel_id") or context.get("log_channel_id")
        log_channel = None
        if log_channel_id:
            log_channel = message.guild.get_channel(int(log_channel_id))
        if not isinstance(log_channel, disnake.TextChannel):
            log_channel = await ensure_guild_log_channel(message.guild, "canal_de_logs_de_antifraude")

        embed = disnake.Embed(
            title="Detector de Golpes - Alerta",
            description=(
                f"**Sistema:** `{context.get('type')}`\n"
                f"**Canal:** {message.channel.mention}\n"
                f"**Usuario:** {message.author.mention} (`{message.author.id}`)\n"
                f"**Pontuacao:** `{score}`\n"
                f"**Regras:** `{', '.join(item['name'] for item in matches)}`\n"
                f"**Mensagem:**\n```{_short(message.content, 900)}```"
            ),
            color=disnake.Color.red(),
        )
        embed.add_field(name="Link", value=f"[Abrir mensagem]({message.jump_url})", inline=False)
        file = disnake.File(
            io.BytesIO(evidence_text.encode("utf-8", errors="replace")),
            filename=f"evidencia-golpe-{message.id}.txt",
        )

        if isinstance(log_channel, disnake.TextChannel):
            try:
                await log_channel.send(
                    content=mentions or None,
                    embed=embed,
                    file=file,
                    allowed_mentions=disnake.AllowedMentions(roles=True),
                )
            except disnake.HTTPException as exc:
                print(f"[ScamDetector] Falha ao enviar log: {exc}")

        if config.get("alert_in_channel", True):
            try:
                await message.channel.send(
                    f"{mentions} {emoji.warn} **Possivel golpe detectado.** A equipe foi acionada e a evidencia foi registrada.",
                    allowed_mentions=disnake.AllowedMentions(roles=True),
                )
            except disnake.HTTPException:
                pass


def setup(bot):
    bot.add_cog(ScamDetectorPanel(bot))
