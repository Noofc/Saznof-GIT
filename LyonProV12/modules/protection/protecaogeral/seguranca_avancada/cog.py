import asyncio
import re
import time
from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import disnake
from disnake.ext import commands, tasks

from functions.bool_utils import as_bool
from functions.database import database as db
from functions.emoji import emoji
from functions.message import embed_message, message


COLLECTION = "protection_advanced_security"
URL_RE = re.compile(r"(https?://[^\s<>()]+|discord\.gg/[^\s<>()]+|discord\.com/invite/[^\s<>()]+)", re.I)
PUNISHMENTS = ["timeout_1h", "kick", "ban", "remove_roles", "none"]
PRIVATE_LINK_DOMAINS = {
    "pastebin.com",
    "hastebin.com",
    "rentry.co",
    "ghostbin.co",
    "bit.ly",
    "tinyurl.com",
    "mega.nz",
    "mediafire.com",
}
STAFF_AUDIT_KEYWORDS = (
    "ticket",
    "close",
    "fechar",
    "parceria",
    "aprovar",
    "approve",
    "payment",
    "pagamento",
    "gateway",
    "pix",
    "config",
    "cargo",
    "role",
    "ban",
    "kick",
    "punish",
    "permiss",
    "loja",
    "produto",
    "stock",
    "estoque",
)
LEAK_PATTERNS = (
    ("webhook", "Webhook do Discord", re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_\-]+", re.I), "alto"),
    ("token", "Token de bot/conta", re.compile(r"(?:mfa\.[A-Za-z0-9_\-]{20,}|[A-Za-z0-9_\-]{23,28}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{27,})"), "critico"),
    ("email", "Email exposto", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "medio"),
    ("cpf", "CPF exposto", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "alto"),
    ("pix_uuid", "Chave PIX aleatoria", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "alto"),
)


DEFAULT_GUILD_CONFIG = {
    "enabled": False,
    "anti_raid": True,
    "anti_spam": True,
    "anti_link": True,
    "anti_leak": True,
    "anti_nuke": True,
    "block_external_bots": True,
    "smart_anti_raid": True,
    "staff_audit": True,
    "staff_abuse": True,
    "owner_alerts": True,
    "punishment": "timeout_1h",
    "link_punishment": "timeout_1h",
    "raid_action": "kick",
    "raid_high_risk_action": "ban",
    "raid_risk_threshold": 65,
    "raid_min_account_age_hours": 24,
    "raid_mode_minutes": 5,
    "spam_limit": 5,
    "spam_window": 7,
    "raid_limit": 6,
    "raid_window": 20,
    "nuke_limit": 3,
    "nuke_window": 20,
    "staff_abuse_limit": 4,
    "staff_abuse_window": 60,
    "crisis_minutes": 15,
    "crisis_mode_until": 0,
    "crisis_locked_channels": [],
    "crisis_previous_verification": None,
    "staff_audit_log": [],
    "restore_channels": True,
    "leak_delete": True,
    "allowed_domains": [],
    "allowed_bots": [],
    "immune_roles": [],
    "ignored_channels": [],
    "log_channel_id": None,
}


def _e(name: str, fallback=None):
    return getattr(emoji, name, fallback)


def _now() -> float:
    return time.monotonic()


def _human_bool(value) -> str:
    return "Ativo" if as_bool(value, False) else "Inativo"


class AdvancedSecurityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._spam_buckets: dict[tuple[int, int], deque] = defaultdict(deque)
        self._join_buckets: dict[int, deque] = defaultdict(deque)
        self._nuke_buckets: dict[tuple[int, int], deque] = defaultdict(deque)
        self._staff_action_buckets: dict[tuple[int, int], deque] = defaultdict(deque)
        self._punish_cooldowns: dict[tuple[int, int, str], float] = {}
        self._raid_mode_until: dict[int, float] = {}
        self._crisis_watchdog.start()

    def cog_unload(self):
        self._crisis_watchdog.cancel()

    def _all_config(self) -> dict:
        data = db.get_document(COLLECTION) or {}
        return data if isinstance(data, dict) else {}

    def _guild_config(self, guild_id: int) -> dict:
        data = self._all_config()
        guilds = data.setdefault("guilds", {})
        cfg = deepcopy(DEFAULT_GUILD_CONFIG)
        stored = guilds.get(str(guild_id))
        if isinstance(stored, dict):
            cfg.update(stored)
        cfg["guild_id"] = guild_id
        return cfg

    def _save_guild_config(self, guild_id: int, cfg: dict) -> None:
        data = self._all_config()
        guilds = data.setdefault("guilds", {})
        clean = deepcopy(DEFAULT_GUILD_CONFIG)
        clean.update(cfg or {})
        guilds[str(guild_id)] = clean
        db.save_document(COLLECTION, data)

    def _container_kwargs(self) -> dict:
        colors = db.get_document("custom_colors") or {}
        color = colors.get("primary") or "#5865f2"
        try:
            return {"accent_colour": disnake.Colour(int(color.replace("#", ""), 16))}
        except Exception:
            return {"accent_colour": disnake.Colour.blurple()}

    def _module_enabled(self, cfg: dict, key: str) -> bool:
        return as_bool(cfg.get("enabled"), False) and as_bool(cfg.get(key), False)

    def _ignored_channel(self, channel_id: int, cfg: dict) -> bool:
        return str(channel_id) in {str(c) for c in cfg.get("ignored_channels", [])}

    def _is_immune(self, member: disnake.Member | None, cfg: dict) -> bool:
        if not member:
            return False
        if member.id == member.guild.owner_id or member.id == self.bot.user.id:
            return True
        immune_roles = {str(role_id) for role_id in cfg.get("immune_roles", [])}
        return any(str(role.id) in immune_roles for role in getattr(member, "roles", []) or [])

    def _staff_like_permissions(self, member: disnake.Member | None) -> bool:
        if not member:
            return False
        perms = getattr(member, "guild_permissions", None)
        return bool(
            getattr(perms, "administrator", False)
            or getattr(perms, "manage_guild", False)
            or getattr(perms, "manage_channels", False)
            or getattr(perms, "manage_roles", False)
            or getattr(perms, "manage_messages", False)
            or getattr(perms, "ban_members", False)
            or getattr(perms, "kick_members", False)
        )

    def _should_audit_interaction(self, member: disnake.Member | None, custom_id: str) -> bool:
        if not custom_id or not self._staff_like_permissions(member):
            return False
        cid = custom_id.lower()
        return any(word in cid for word in STAFF_AUDIT_KEYWORDS)

    def _can_act_on(self, member: disnake.Member) -> bool:
        me = member.guild.me
        if not me or member.id == member.guild.owner_id:
            return False
        return me.top_role > member.top_role

    async def _log(self, guild: disnake.Guild, cfg: dict, title: str, description: str, *, color: int = 0x5865F2) -> None:
        channel_id = cfg.get("log_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, disnake.TextChannel):
            return

        embed = disnake.Embed(
            title=title,
            description=description[:4000],
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Lyon Pro - Seguranca Avancada")
        try:
            await channel.send(embed=embed)
        except disnake.HTTPException:
            pass

    def _owner_id(self) -> str:
        config = db.obter("config.json") or {}
        return str((config.get("bot") or {}).get("owner") or "")

    def _clip(self, value: str, limit: int = 950) -> str:
        text = str(value or "`Nao informado`")
        return text if len(text) <= limit else f"{text[:limit - 3]}..."

    def _crisis_remaining(self, cfg: dict) -> int:
        return max(0, int(cfg.get("crisis_mode_until") or 0) - int(time.time()))

    def _crisis_active(self, cfg: dict) -> bool:
        return self._crisis_remaining(cfg) > 0

    async def _smart_log(
        self,
        guild: disnake.Guild,
        cfg: dict,
        title: str,
        *,
        happened: str,
        caused_by: str,
        risk: str,
        action_taken: str,
        next_step: str,
        color: int = 0x5865F2,
    ) -> None:
        channel_id = cfg.get("log_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, disnake.TextChannel):
            return

        embed = disnake.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="O que aconteceu", value=self._clip(happened), inline=False)
        embed.add_field(name="Quem causou", value=self._clip(caused_by, 500), inline=False)
        embed.add_field(name="Risco", value=self._clip(risk, 500), inline=False)
        embed.add_field(name="Acao tomada", value=self._clip(action_taken), inline=False)
        embed.add_field(name="Proximo passo recomendado", value=self._clip(next_step), inline=False)
        embed.set_footer(text="Lyon Pro - Logs Inteligentes")
        try:
            await channel.send(embed=embed)
        except disnake.HTTPException:
            pass

    async def _alert_owner(self, guild: disnake.Guild, cfg: dict, title: str, description: str, *, color: int = 0xE74C3C) -> None:
        if not as_bool(cfg.get("owner_alerts"), True):
            return
        owner_id = self._owner_id()
        if not owner_id:
            return
        try:
            owner = self.bot.get_user(int(owner_id)) or await self.bot.fetch_user(int(owner_id))
        except (ValueError, disnake.HTTPException):
            return
        embed = disnake.Embed(
            title=title,
            description=self._clip(description, 3800),
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Servidor: {guild.name} ({guild.id})")
        try:
            await owner.send(embed=embed)
        except disnake.HTTPException:
            pass

    def _detect_leaks(self, text: str, cfg: dict) -> list[dict]:
        content = text or ""
        found: list[dict] = []
        seen = set()
        for key, label, pattern, severity in LEAK_PATTERNS:
            if pattern.search(content):
                seen.add(key)
                found.append({"key": key, "label": label, "severity": severity})

        allowed = {str(domain).lower().removeprefix("www.") for domain in cfg.get("allowed_domains", []) if domain}
        for domain in self._extract_domains(content):
            if domain in PRIVATE_LINK_DOMAINS and domain not in allowed and domain not in seen:
                seen.add(domain)
                found.append({"key": domain, "label": f"Link privado/suspeito ({domain})", "severity": "medio"})
        return found

    async def _record_staff_audit(
        self,
        guild: disnake.Guild,
        cfg: dict,
        actor_id: int | None,
        action_name: str,
        target_text: str = "",
        *,
        risk: str = "medio",
    ) -> None:
        if not actor_id or not self._module_enabled(cfg, "staff_audit"):
            return
        log = cfg.setdefault("staff_audit_log", [])
        if not isinstance(log, list):
            log = []
        log.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "actor_id": int(actor_id),
            "action": action_name,
            "target": str(target_text or "")[:300],
            "risk": risk,
        })
        cfg["staff_audit_log"] = log[-100:]
        self._save_guild_config(guild.id, cfg)

    async def _delete_invites(self, guild: disnake.Guild) -> int:
        deleted = 0
        try:
            invites = await guild.invites()
        except disnake.HTTPException:
            return 0
        for invite in invites:
            try:
                await invite.delete(reason="[Lyon] Modo Crise: convites desativados")
                deleted += 1
            except disnake.HTTPException:
                continue
        return deleted

    async def _lock_crisis_channels(self, guild: disnake.Guild, cfg: dict) -> list[dict]:
        ignored = {str(channel_id) for channel_id in cfg.get("ignored_channels", [])}
        if cfg.get("log_channel_id"):
            ignored.add(str(cfg.get("log_channel_id")))

        locked = []
        me = guild.me
        if not me:
            return locked
        for channel in guild.text_channels:
            if str(channel.id) in ignored:
                continue
            if not channel.permissions_for(me).manage_channels:
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            locked.append({"channel_id": int(channel.id), "send_messages": overwrite.send_messages})
            overwrite.send_messages = False
            try:
                await channel.set_permissions(
                    guild.default_role,
                    overwrite=overwrite,
                    reason="[Lyon] Modo Crise: canal travado temporariamente",
                )
            except disnake.HTTPException:
                continue
        return locked

    async def _unlock_crisis_channels(self, guild: disnake.Guild, cfg: dict) -> int:
        restored = 0
        for item in cfg.get("crisis_locked_channels", []) or []:
            channel = guild.get_channel(int(item.get("channel_id", 0) or 0))
            if not isinstance(channel, disnake.TextChannel):
                continue
            if not guild.me or not channel.permissions_for(guild.me).manage_channels:
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = item.get("send_messages")
            try:
                await channel.set_permissions(
                    guild.default_role,
                    overwrite=overwrite,
                    reason="[Lyon] Modo Crise: restaurando permissao de envio",
                )
                restored += 1
            except disnake.HTTPException:
                continue
        return restored

    async def _activate_crisis_mode(
        self,
        guild: disnake.Guild,
        cfg: dict,
        reason: str,
        *,
        actor_id: int | None = None,
        minutes: int | None = None,
    ) -> None:
        minutes = max(1, int(minutes or cfg.get("crisis_minutes", 15) or 15))
        already_active = self._crisis_active(cfg)
        cfg["enabled"] = True
        cfg["anti_raid"] = True
        cfg["anti_spam"] = True
        cfg["anti_link"] = True
        cfg["anti_leak"] = True
        cfg["anti_nuke"] = True
        cfg["block_external_bots"] = True
        cfg["staff_abuse"] = True
        cfg["raid_risk_threshold"] = min(int(cfg.get("raid_risk_threshold", 65) or 65), 45)
        cfg["crisis_mode_until"] = int(time.time()) + (minutes * 60)

        if not already_active:
            previous = getattr(guild.verification_level, "value", None)
            if previous is not None:
                cfg["crisis_previous_verification"] = int(previous)
            cfg["crisis_locked_channels"] = await self._lock_crisis_channels(guild, cfg)

        invites_deleted = await self._delete_invites(guild)
        try:
            await guild.edit(verification_level=disnake.VerificationLevel.high, reason="[Lyon] Modo Crise ativado")
        except disnake.HTTPException:
            pass

        self._save_guild_config(guild.id, cfg)
        actor = f"<@{actor_id}> (`{actor_id}`)" if actor_id else "`Painel/Automacao`"
        locked_count = len(cfg.get("crisis_locked_channels", []) or [])
        await self._smart_log(
            guild,
            cfg,
            f"{_e('shield', '')} Modo Crise ativado",
            happened=reason,
            caused_by=actor,
            risk="Alto. O servidor entrou em defesa reforcada contra raid, vazamento, spam, links e abuso de staff.",
            action_taken=f"Canais travados: `{locked_count}`. Convites apagados: `{invites_deleted}`. Verificacao elevada e anti-raid agressivo por `{minutes}` minuto(s).",
            next_step="Revise a auditoria recente, confira os cargos da staff envolvida e desative o Modo Crise quando o ambiente estiver seguro.",
            color=0xE74C3C,
        )
        await self._alert_owner(
            guild,
            cfg,
            "Modo Crise ativado",
            f"Motivo: {reason}\nExecutor/Gatilho: {actor}\nCanais travados: {locked_count}\nConvites apagados: {invites_deleted}",
        )

    async def _deactivate_crisis_mode(self, guild: disnake.Guild, cfg: dict, reason: str = "Modo Crise encerrado") -> None:
        restored = await self._unlock_crisis_channels(guild, cfg)
        previous = cfg.get("crisis_previous_verification")
        if previous is not None:
            try:
                await guild.edit(
                    verification_level=disnake.VerificationLevel(int(previous)),
                    reason="[Lyon] Modo Crise encerrado",
                )
            except (ValueError, disnake.HTTPException):
                pass
        cfg["crisis_mode_until"] = 0
        cfg["crisis_locked_channels"] = []
        cfg["crisis_previous_verification"] = None
        self._save_guild_config(guild.id, cfg)
        await self._smart_log(
            guild,
            cfg,
            f"{_e('correct', '')} Modo Crise encerrado",
            happened=reason,
            caused_by="`Sistema`",
            risk="Baixo, desde que a equipe tenha revisado os alertas anteriores.",
            action_taken=f"Permissoes de envio restauradas em `{restored}` canal(is).",
            next_step="Confira se os canais principais voltaram corretamente e mantenha os logs de seguranca monitorados.",
            color=0x2ECC71,
        )

    async def _track_staff_abuse(
        self,
        guild: disnake.Guild,
        cfg: dict,
        actor_id: int | None,
        action_name: str,
        target_text: str = "",
    ) -> bool:
        if not actor_id or not self._module_enabled(cfg, "staff_abuse"):
            return False
        member = guild.get_member(int(actor_id))
        if self._is_immune(member, cfg):
            return False

        window = max(10, int(cfg.get("staff_abuse_window", 60) or 60))
        limit = max(2, int(cfg.get("staff_abuse_limit", 4) or 4))
        bucket = self._staff_action_buckets[(guild.id, int(actor_id))]
        now = _now()
        bucket.append((now, action_name, target_text))
        while bucket and now - bucket[0][0] > window:
            bucket.popleft()

        if len(bucket) < limit:
            return False

        cooldown_key = (guild.id, int(actor_id), "staff_abuse")
        if _now() - self._punish_cooldowns.get(cooldown_key, 0) < 120:
            return False
        self._punish_cooldowns[cooldown_key] = _now()

        punished = False
        if member:
            punished = await self._punish_member(member, cfg, "Detector de Staff Abusivo", "remove_roles")
        await self._activate_crisis_mode(
            guild,
            cfg,
            f"Detector de Staff Abusivo: <@{actor_id}> fez `{len(bucket)}` acao(oes) critica(s) em `{window}s`. Ultima acao: `{action_name}`.",
            actor_id=actor_id,
            minutes=cfg.get("crisis_minutes", 15),
        )
        await self._smart_log(
            guild,
            cfg,
            f"{_e('ban', '')} Staff abusivo detectado",
            happened=f"Foram detectadas `{len(bucket)}` acoes administrativas em massa. Ultimo alvo: {target_text or '`nao informado`'}.",
            caused_by=f"<@{actor_id}> (`{actor_id}`)",
            risk="Critico. Acoes em massa de staff podem indicar nuke, conta comprometida ou abuso interno.",
            action_taken=f"Modo Crise ativado. Remocao de cargos aplicada: `{'sim' if punished else 'nao'}`.",
            next_step="Verifique o membro no audit log do Discord, confirme se a conta foi comprometida e restaure permissao apenas depois da revisao.",
            color=0xE74C3C,
        )
        bucket.clear()
        return True

    async def _handle_critical_staff_action(
        self,
        guild: disnake.Guild,
        cfg: dict,
        actor_id: int | None,
        action_name: str,
        target_text: str = "",
    ) -> bool:
        if self._module_enabled(cfg, "anti_nuke"):
            return await self._track_nuke(guild, actor_id, action_name, cfg, target_text)
        if actor_id and str(actor_id) != str(self.bot.user.id):
            member = guild.get_member(int(actor_id))
            await self._record_staff_audit(guild, cfg, actor_id, action_name, target_text, risk="alto")
            if not self._is_immune(member, cfg):
                await self._track_staff_abuse(guild, cfg, actor_id, action_name, target_text)
        return False

    @tasks.loop(minutes=1)
    async def _crisis_watchdog(self):
        data = self._all_config()
        guilds = data.get("guilds", {}) if isinstance(data, dict) else {}
        for guild_id, cfg in list(guilds.items()):
            if not isinstance(cfg, dict):
                continue
            if int(cfg.get("crisis_mode_until") or 0) <= 0:
                continue
            if int(cfg.get("crisis_mode_until") or 0) > int(time.time()):
                continue
            guild = self.bot.get_guild(int(guild_id))
            if guild:
                await self._deactivate_crisis_mode(guild, self._guild_config(int(guild_id)), "Tempo configurado do Modo Crise terminou.")

    @_crisis_watchdog.before_loop
    async def _before_crisis_watchdog(self):
        await self.bot.wait_until_ready()

    async def _punish_member(self, member: disnake.Member, cfg: dict, reason: str, punishment: str | None = None) -> bool:
        punishment = punishment or cfg.get("punishment", "timeout_1h")
        key = (member.guild.id, member.id, reason[:40])
        if _now() - self._punish_cooldowns.get(key, 0) < 20:
            return False
        self._punish_cooldowns[key] = _now()

        if punishment == "none" or self._is_immune(member, cfg) or not self._can_act_on(member):
            return False

        try:
            if punishment == "ban":
                await member.ban(reason=f"[Lyon] {reason}", delete_message_days=0)
            elif punishment == "kick":
                await member.kick(reason=f"[Lyon] {reason}")
            elif punishment == "remove_roles":
                removable = [
                    role for role in member.roles
                    if role != member.guild.default_role and member.guild.me.top_role > role
                ]
                if removable:
                    await member.remove_roles(*removable, reason=f"[Lyon] {reason}")
            else:
                await member.timeout(duration=timedelta(hours=1), reason=f"[Lyon] {reason}")
            return True
        except disnake.HTTPException:
            return False

    def _extract_domains(self, text: str) -> list[str]:
        domains = []
        for match in URL_RE.findall(text or ""):
            value = match
            if value.startswith("discord.gg/"):
                domains.append("discord.gg")
                continue
            if value.startswith("discord.com/invite/"):
                domains.append("discord.com")
                continue
            parsed = urlparse(value if value.startswith("http") else f"https://{value}")
            if parsed.netloc:
                domains.append(parsed.netloc.lower().removeprefix("www."))
        return domains

    def _has_blocked_link(self, text: str, cfg: dict) -> tuple[bool, list[str]]:
        domains = self._extract_domains(text)
        if not domains:
            return False, []
        allowed = {str(domain).lower().removeprefix("www.") for domain in cfg.get("allowed_domains", []) if domain}
        blocked = [domain for domain in domains if domain not in allowed]
        return bool(blocked), blocked

    def _account_age_hours(self, member: disnake.Member) -> float:
        created_at = getattr(member, "created_at", None)
        if not created_at:
            return 999999.0
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 3600)

    def _join_entry_time(self, entry) -> float:
        if isinstance(entry, dict):
            return float(entry.get("time", 0) or 0)
        return float(entry or 0)

    def _raid_risk(self, member: disnake.Member, cfg: dict, bucket: deque, raid_active: bool) -> dict:
        if not as_bool(cfg.get("smart_anti_raid"), True):
            return {"score": 100 if raid_active else 0, "reasons": ["modo inteligente desativado"], "age_hours": self._account_age_hours(member)}

        score = 0
        reasons = []
        limit = max(2, int(cfg.get("raid_limit", 6) or 6))
        window = max(5, int(cfg.get("raid_window", 20) or 20))
        join_count = len(bucket)
        age_hours = self._account_age_hours(member)
        min_age = max(1, int(cfg.get("raid_min_account_age_hours", 24) or 24))

        if join_count >= limit:
            score += 45
            reasons.append(f"{join_count} entradas em {window}s")
        elif join_count >= max(2, limit - 2):
            score += 24
            reasons.append("volume de entradas acima do normal")

        if raid_active:
            score += 30
            reasons.append("modo raid ativo")

        if member.bot:
            score += 35
            reasons.append("conta e bot")

        if age_hours <= 6:
            score += 35
            reasons.append("conta criada ha menos de 6h")
        elif age_hours <= min_age:
            score += 25
            reasons.append(f"conta criada ha menos de {min_age}h")
        elif age_hours <= 72:
            score += 12
            reasons.append("conta criada ha menos de 3 dias")

        recent_new = 0
        recent_bots = 0
        for item in bucket:
            if not isinstance(item, dict):
                continue
            if float(item.get("age_hours", 999999) or 999999) <= min_age:
                recent_new += 1
            if item.get("bot"):
                recent_bots += 1

        if recent_new >= max(2, limit // 2):
            score += 20
            reasons.append(f"{recent_new} contas novas no mesmo pico")
        if recent_bots >= 2:
            score += 25
            reasons.append(f"{recent_bots} bots no mesmo pico")

        name = f"{member.name} {getattr(member, 'display_name', '')}".lower()
        if re.search(r"(nitro|airdrop|steam|gift|free|promo|discord\.gg|\.gg/|http)", name):
            score += 15
            reasons.append("nome com padrao suspeito")

        if getattr(member, "avatar", None) is None and age_hours <= 72:
            score += 8
            reasons.append("conta nova sem avatar customizado")

        return {
            "score": min(100, score),
            "reasons": reasons or ["risco baixo"],
            "age_hours": age_hours,
            "join_count": join_count,
            "window": window,
        }

    async def _audit_entry(self, guild: disnake.Guild, action, target_id: int | None = None):
        await asyncio.sleep(0.8)
        try:
            async for entry in guild.audit_logs(limit=6, action=action):
                if target_id is not None:
                    target = getattr(entry, "target", None)
                    if not target or str(getattr(target, "id", "")) != str(target_id):
                        continue
                created_at = getattr(entry, "created_at", None)
                if created_at:
                    age = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).total_seconds()
                    if age > 20:
                        continue
                return entry
        except disnake.HTTPException:
            return None
        return None

    async def _track_nuke(self, guild: disnake.Guild, actor_id: int | None, action_name: str, cfg: dict, target_text: str = "") -> bool:
        if not actor_id or str(actor_id) == str(self.bot.user.id):
            return False
        member = guild.get_member(int(actor_id))
        await self._record_staff_audit(guild, cfg, actor_id, action_name, target_text, risk="alto")
        if self._is_immune(member, cfg):
            return False
        await self._track_staff_abuse(guild, cfg, actor_id, action_name, target_text)

        window = max(5, int(cfg.get("nuke_window", 20) or 20))
        limit = max(1, int(cfg.get("nuke_limit", 3) or 3))
        bucket = self._nuke_buckets[(guild.id, int(actor_id))]
        now = _now()
        bucket.append((now, action_name))
        while bucket and now - bucket[0][0] > window:
            bucket.popleft()

        if len(bucket) < limit:
            return False

        punished = False
        if member:
            punished = await self._punish_member(member, cfg, f"Anti Nuke: {len(bucket)} acoes em {window}s")
        await self._smart_log(
            guild,
            cfg,
            f"{_e('shield', '')} Anti Nuke acionado",
            happened=f"Acoes administrativas em massa: `{len(bucket)}/{limit}` dentro de `{window}s`. Ultima acao: `{action_name}`. Alvo: {target_text or '`nao informado`'}.",
            caused_by=f"<@{actor_id}> (`{actor_id}`)",
            risk="Critico. Pode ser nuke, conta de staff comprometida ou acao destrutiva em massa.",
            action_taken=f"Protecao Anti Nuke acionada. Punicao aplicada: `{'sim' if punished else 'nao'}`.",
            next_step="Confira os logs do Discord, revise os cargos do executor e restaure apenas o que for confiavel.",
            color=0xE74C3C,
        )
        bucket.clear()
        return True

    async def _restore_text_channel(self, channel: disnake.TextChannel, cfg: dict) -> None:
        if not as_bool(cfg.get("restore_channels"), True):
            return
        try:
            new_channel = await channel.guild.create_text_channel(
                name=channel.name,
                topic=channel.topic,
                category=channel.category,
                overwrites=channel.overwrites,
                nsfw=channel.nsfw,
                slowmode_delay=channel.slowmode_delay,
                position=channel.position,
                reason="[Lyon] Anti Nuke: restaurando canal deletado",
            )
            await self._log(
                channel.guild,
                cfg,
                f"{_e('reload', '')} Canal restaurado",
                f"Canal deletado: `{channel.name}`\nNovo canal: {new_channel.mention}",
                color=0x2ECC71,
            )
        except disnake.HTTPException:
            pass

    def _toggle_cfg(self, cfg: dict, key: str) -> None:
        cfg[key] = not as_bool(cfg.get(key), False)

    def _cycle_punishment(self, cfg: dict) -> str:
        current = cfg.get("punishment", "timeout_1h")
        try:
            idx = PUNISHMENTS.index(current)
        except ValueError:
            idx = 0
        cfg["punishment"] = PUNISHMENTS[(idx + 1) % len(PUNISHMENTS)]
        cfg["link_punishment"] = cfg["punishment"]
        return cfg["punishment"]

    def _panel_text(self, cfg: dict) -> str:
        allowed_domains = ", ".join(cfg.get("allowed_domains", [])[:5]) or "nenhum"
        log_text = f"<#{cfg.get('log_channel_id')}>" if cfg.get("log_channel_id") else "`Nao configurado`"
        raid_remaining = max(0, int(self._raid_mode_until.get(int(cfg.get("guild_id", 0) or 0), 0) - _now()))
        raid_mode_text = f" | modo raid: `{raid_remaining}s`" if raid_remaining else ""
        crisis_remaining = self._crisis_remaining(cfg)
        crisis_text = f"Ativo por `{crisis_remaining}s`" if crisis_remaining else "Inativo"
        return (
            f"{_e('shield', '')} **Status geral:** `{_human_bool(cfg.get('enabled'))}`\n"
            f"{_e('members', '')} **Anti Raid Inteligente:** `{_human_bool(cfg.get('anti_raid'))}` | `{cfg.get('raid_limit')}` entradas em `{cfg.get('raid_window')}s` | risco `{cfg.get('raid_risk_threshold')}/100`{raid_mode_text}\n"
            f"{_e('message', '')} **Anti Spam:** `{_human_bool(cfg.get('anti_spam'))}` | `{cfg.get('spam_limit')}` msgs em `{cfg.get('spam_window')}s`\n"
            f"{_e('link', '')} **Anti Link:** `{_human_bool(cfg.get('anti_link'))}` | Permitidos: `{allowed_domains}`\n"
            f"{_e('shield', '')} **Anti Vazamento:** `{_human_bool(cfg.get('anti_leak'))}` | apaga dados sensiveis sem repetir no log\n"
            f"{_e('ban', '')} **Anti Nuke:** `{_human_bool(cfg.get('anti_nuke'))}` | `{cfg.get('nuke_limit')}` acoes em `{cfg.get('nuke_window')}s`\n"
            f"{_e('staff', _e('members', ''))} **Auditoria Staff:** `{_human_bool(cfg.get('staff_audit'))}` | Abuso: `{_human_bool(cfg.get('staff_abuse'))}` | `{cfg.get('staff_abuse_limit')}` acoes em `{cfg.get('staff_abuse_window')}s`\n"
            f"{_e('warning', _e('shield', ''))} **Modo Crise:** `{crisis_text}` | duracao padrao `{cfg.get('crisis_minutes')}` min\n"
            f"{_e('robot', '')} **Pros de fora:** `{_human_bool(cfg.get('block_external_bots'))}` | Permitidos: `{len(cfg.get('allowed_bots', []))}`\n"
            f"{_e('hammer', '')} **Punicao padrao:** `{cfg.get('punishment')}`\n"
            f"{_e('textc', '')} **Logs:** {log_text}"
        )

    def _audit_preview(self, cfg: dict) -> str:
        entries = cfg.get("staff_audit_log", []) or []
        if not entries:
            return "`Sem eventos registrados.`"
        lines = []
        for item in list(entries)[-5:][::-1]:
            actor_id = item.get("actor_id")
            action = str(item.get("action") or "acao")
            target = str(item.get("target") or "sem alvo")
            lines.append(f"- <@{actor_id}> `{action}` -> `{target[:60]}`")
        return "\n".join(lines)

    def _main_components(self, guild_id: int) -> list:
        cfg = self._guild_config(guild_id)
        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {_e('shield', '')} Seguranca Avancada\n-# Painel > Protecao > Protecao Geral > **Seguranca Avancada**"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(self._panel_text(cfg)),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Geral", style=disnake.ButtonStyle.success if cfg.get("enabled") else disnake.ButtonStyle.danger, emoji=_e("power"), custom_id="AdvSec_Toggle:enabled"),
                disnake.ui.Button(label="Anti Raid", style=disnake.ButtonStyle.success if cfg.get("anti_raid") else disnake.ButtonStyle.grey, emoji=_e("members"), custom_id="AdvSec_Toggle:anti_raid"),
                disnake.ui.Button(label="Anti Spam", style=disnake.ButtonStyle.success if cfg.get("anti_spam") else disnake.ButtonStyle.grey, emoji=_e("message"), custom_id="AdvSec_Toggle:anti_spam"),
                disnake.ui.Button(label="Anti Link", style=disnake.ButtonStyle.success if cfg.get("anti_link") else disnake.ButtonStyle.grey, emoji=_e("link"), custom_id="AdvSec_Toggle:anti_link"),
                disnake.ui.Button(label="Anti Nuke", style=disnake.ButtonStyle.success if cfg.get("anti_nuke") else disnake.ButtonStyle.grey, emoji=_e("ban"), custom_id="AdvSec_Toggle:anti_nuke"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Pros de fora", style=disnake.ButtonStyle.success if cfg.get("block_external_bots") else disnake.ButtonStyle.grey, emoji=_e("robot"), custom_id="AdvSec_Toggle:block_external_bots"),
                disnake.ui.Button(label="Limites", style=disnake.ButtonStyle.blurple, emoji=_e("chart"), custom_id="AdvSec_Limits"),
                disnake.ui.Button(label="Dominios", style=disnake.ButtonStyle.grey, emoji=_e("web"), custom_id="AdvSec_Domains"),
                disnake.ui.Button(label="Punicao", style=disnake.ButtonStyle.grey, emoji=_e("hammer"), custom_id="AdvSec_Punishment"),
                disnake.ui.Button(label="Logs/Imunes", style=disnake.ButtonStyle.grey, emoji=_e("settings"), custom_id="AdvSec_Targets"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Anti Vazamento", style=disnake.ButtonStyle.success if cfg.get("anti_leak") else disnake.ButtonStyle.grey, emoji=_e("shield"), custom_id="AdvSec_Toggle:anti_leak"),
                disnake.ui.Button(label="Auditoria", style=disnake.ButtonStyle.success if cfg.get("staff_audit") else disnake.ButtonStyle.grey, emoji=_e("textc"), custom_id="AdvSec_Toggle:staff_audit"),
                disnake.ui.Button(label="Staff Abuso", style=disnake.ButtonStyle.success if cfg.get("staff_abuse") else disnake.ButtonStyle.grey, emoji=_e("ban"), custom_id="AdvSec_Toggle:staff_abuse"),
                disnake.ui.Button(label="Alertar Owner", style=disnake.ButtonStyle.success if cfg.get("owner_alerts") else disnake.ButtonStyle.grey, emoji=_e("member"), custom_id="AdvSec_Toggle:owner_alerts"),
                disnake.ui.Button(label="Modo Crise", style=disnake.ButtonStyle.red if self._crisis_active(cfg) else disnake.ButtonStyle.blurple, emoji=_e("warning", _e("shield")), custom_id="AdvSec_Crisis"),
            ),
            **self._container_kwargs(),
        )
        return [
            container,
        ]

    def _targets_components(self, guild_id: int) -> list:
        cfg = self._guild_config(guild_id)
        log_text = f"<#{cfg.get('log_channel_id')}>" if cfg.get("log_channel_id") else "`Nao configurado`"
        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {_e('settings', '')} Logs e Excecoes\n-# Seguranca Avancada"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"Logs: {log_text}\n"
                f"Cargos imunes: `{len(cfg.get('immune_roles', []))}`\n"
                f"Canais ignorados: `{len(cfg.get('ignored_channels', []))}`\n"
                f"Pros permitidos: `{len(cfg.get('allowed_bots', []))}`\n\n"
                f"**Ultimas auditorias:**\n{self._audit_preview(cfg)}"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(disnake.ui.ChannelSelect(placeholder="Canal de logs", custom_id="AdvSec_SelectLog", channel_types=[disnake.ChannelType.text], min_values=1, max_values=1)),
            disnake.ui.ActionRow(disnake.ui.RoleSelect(placeholder="Cargos imunes", custom_id="AdvSec_SelectRoles", min_values=0, max_values=25)),
            disnake.ui.ActionRow(disnake.ui.ChannelSelect(placeholder="Canais ignorados", custom_id="AdvSec_SelectChannels", channel_types=[disnake.ChannelType.text], min_values=0, max_values=25)),
            disnake.ui.ActionRow(disnake.ui.UserSelect(placeholder="Pros permitidos", custom_id="AdvSec_SelectPros", min_values=0, max_values=25)),
            **self._container_kwargs(),
        )
        return [
            container,
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Remover Logs", style=disnake.ButtonStyle.red, emoji=_e("delete"), custom_id="AdvSec_ClearLog"),
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="AdvSec_Back"),
            ),
        ]

    async def display_panel(self, inter: disnake.MessageInteraction):
        mode = db.get_document("custom_mode").get("mode")
        handler = embed_message if mode == "embed" else message
        await handler.wait(inter, send=False)
        await inter.edit_original_message(content=None, embed=None, components=self._main_components(inter.guild.id))

    @commands.Cog.listener("on_message")
    async def advanced_security_message(self, msg: disnake.Message):
        if not msg.guild or msg.author.bot or msg.webhook_id:
            return
        cfg = self._guild_config(msg.guild.id)
        if not as_bool(cfg.get("enabled"), False) or self._ignored_channel(msg.channel.id, cfg):
            return
        member = msg.author if isinstance(msg.author, disnake.Member) else msg.guild.get_member(msg.author.id)
        if self._is_immune(member, cfg):
            return

        if self._module_enabled(cfg, "anti_leak"):
            leaks = self._detect_leaks(msg.content, cfg)
            if leaks:
                deleted = False
                if as_bool(cfg.get("leak_delete"), True):
                    try:
                        await msg.delete()
                        deleted = True
                    except disnake.HTTPException:
                        deleted = False
                labels = ", ".join(item["label"] for item in leaks[:6])
                severities = {item["severity"] for item in leaks}
                risk = "Critico" if "critico" in severities else "Alto" if "alto" in severities else "Medio"
                await self._smart_log(
                    msg.guild,
                    cfg,
                    f"{_e('shield', '')} Anti Vazamento",
                    happened=f"Mensagem com dado sensivel detectada em {msg.channel.mention}. Tipos: `{labels}`.",
                    caused_by=f"{msg.author.mention} (`{msg.author.id}`)",
                    risk=f"{risk}. O bot nao registra o valor vazado no log para evitar exposicao repetida.",
                    action_taken=f"Mensagem apagada: `{'sim' if deleted else 'nao'}`. Staff alertada no canal de logs.",
                    next_step="Oriente o usuario a trocar qualquer token/chave vazada e revise se o dado apareceu em prints ou respostas.",
                    color=0xE74C3C if risk != "Medio" else 0xF1C40F,
                )
                if risk in {"Alto", "Critico"}:
                    await self._alert_owner(
                        msg.guild,
                        cfg,
                        "Anti Vazamento detectou dado sensivel",
                        f"Usuario: {msg.author} ({msg.author.id})\nCanal: #{getattr(msg.channel, 'name', msg.channel.id)}\nTipos: {labels}\nMensagem apagada: {'sim' if deleted else 'nao'}",
                    )
                return

        if self._module_enabled(cfg, "anti_link"):
            blocked, domains = self._has_blocked_link(msg.content, cfg)
            if blocked:
                try:
                    await msg.delete()
                except disnake.HTTPException:
                    pass
                punished = await self._punish_member(member, cfg, "Anti Link: link nao permitido", cfg.get("link_punishment"))
                await self._smart_log(
                    msg.guild,
                    cfg,
                    f"{_e('link', '')} Anti Link",
                    happened=f"Link nao permitido enviado em {msg.channel.mention}. Dominios: `{', '.join(domains[:5])}`.",
                    caused_by=f"{msg.author.mention} (`{msg.author.id}`)",
                    risk="Medio. Links externos podem levar a golpe, raid, phishing ou vazamento.",
                    action_taken=f"Mensagem apagada e punicao aplicada: `{'sim' if punished else 'nao'}`.",
                    next_step="Se o dominio for confiavel, adicione em Dominios Permitidos. Caso contrario, mantenha bloqueado.",
                    color=0xF1C40F,
                )
                return

        if self._module_enabled(cfg, "anti_spam"):
            key = (msg.guild.id, msg.author.id)
            bucket = self._spam_buckets[key]
            now = _now()
            content = " ".join((msg.content or "").lower().split())[:120]
            bucket.append((now, msg.channel.id, msg.id, content))
            window = max(3, int(cfg.get("spam_window", 7) or 7))
            limit = max(2, int(cfg.get("spam_limit", 5) or 5))
            while bucket and now - bucket[0][0] > window:
                bucket.popleft()

            repeated = content and sum(1 for item in bucket if item[3] == content) >= 3
            if len(bucket) >= limit or repeated:
                try:
                    await msg.delete()
                except disnake.HTTPException:
                    pass
                punished = await self._punish_member(member, cfg, f"Anti Spam: {len(bucket)} mensagens em {window}s")
                await self._smart_log(
                    msg.guild,
                    cfg,
                    f"{_e('message', '')} Anti Spam",
                    happened=f"Pico de mensagens em {msg.channel.mention}: `{len(bucket)}/{limit}` dentro de `{window}s`. Repeticao: `{'sim' if repeated else 'nao'}`.",
                    caused_by=f"{msg.author.mention} (`{msg.author.id}`)",
                    risk="Medio/alto. Spam pode ser ataque automatizado ou tentativa de poluir atendimento.",
                    action_taken=f"Mensagem apagada e punicao aplicada: `{'sim' if punished else 'nao'}`.",
                    next_step="Observe se outros usuarios repetem o padrao. Se sim, acione Modo Crise pelo painel.",
                    color=0xE67E22,
                )
                bucket.clear()

    @commands.Cog.listener("on_member_join")
    async def advanced_security_member_join(self, member: disnake.Member):
        cfg = self._guild_config(member.guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return

        if member.bot and self._module_enabled(cfg, "block_external_bots"):
            allowed = {str(bot_id) for bot_id in cfg.get("allowed_bots", [])}
            if str(member.id) not in allowed:
                entry = await self._audit_entry(member.guild, disnake.AuditLogAction.bot_add, member.id)
                inviter = getattr(entry, "user", None)
                inviter_member = member.guild.get_member(inviter.id) if inviter else None
                removed = False
                removal_error = ""
                try:
                    await member.kick(reason="[Lyon] Pro externo nao permitido")
                    removed = True
                except disnake.HTTPException as exc:
                    removal_error = f"Falha ao remover bot externo: {exc}"
                punished_inviter = False
                if inviter_member and not self._is_immune(inviter_member, cfg):
                    punished_inviter = await self._punish_member(inviter_member, cfg, "Adicionou bot externo nao permitido")
                action_lines = [
                    f"Pro removido: `{'sim' if removed else 'nao'}`.",
                    f"Autor punido: `{'sim' if punished_inviter else 'nao'}`.",
                ]
                if removal_error:
                    action_lines.append(removal_error)
                await self._smart_log(
                    member.guild,
                    cfg,
                    f"{_e('robot', '')} Pro externo bloqueado",
                    happened=f"Pro externo tentou entrar: `{member}` (`{member.id}`).",
                    caused_by=inviter.mention if inviter else "`desconhecido`",
                    risk="Alto. Pros de fora podem executar raid, spam, webhooks ou coleta de dados.",
                    action_taken="\n".join(action_lines),
                    next_step="Confirme se o bot era esperado. Se for confiavel, adicione em Pros Permitidos.",
                    color=0xE74C3C,
                )
                return

        if not self._module_enabled(cfg, "anti_raid"):
            return

        now = _now()
        bucket = self._join_buckets[member.guild.id]
        age_hours = self._account_age_hours(member)
        bucket.append({
            "time": now,
            "user_id": member.id,
            "age_hours": age_hours,
            "bot": member.bot,
        })
        window = max(5, int(cfg.get("raid_window", 20) or 20))
        limit = max(2, int(cfg.get("raid_limit", 6) or 6))
        while bucket and now - self._join_entry_time(bucket[0]) > window:
            bucket.popleft()

        raid_active = now < self._raid_mode_until.get(member.guild.id, 0)
        if len(bucket) >= limit:
            mode_seconds = max(60, int(cfg.get("raid_mode_minutes", 5) or 5) * 60)
            self._raid_mode_until[member.guild.id] = now + mode_seconds
            raid_active = True

        risk = self._raid_risk(member, cfg, bucket, raid_active)
        threshold = max(1, min(100, int(cfg.get("raid_risk_threshold", 65) or 65)))
        should_act = risk["score"] >= threshold or (raid_active and risk["score"] >= 30)

        if should_act and not self._is_immune(member, cfg):
            action = cfg.get("raid_action", "kick")
            if risk["score"] >= 85:
                action = cfg.get("raid_high_risk_action", action)
            punished = await self._punish_member(member, cfg, f"Anti Raid inteligente: risco {risk['score']}/100", action)
            await self._smart_log(
                member.guild,
                cfg,
                f"{_e('members', '')} Anti Raid inteligente",
                happened=f"Entrada suspeita: {member.mention} (`{member.id}`). Entradas recentes: `{len(bucket)}/{limit}` em `{window}s`.",
                caused_by=f"{member.mention} (`{member.id}`)",
                risk=f"{risk['score']}/100 (limiar {threshold}/100). Motivos: `{'; '.join(risk['reasons'])}`. Idade da conta: `{risk['age_hours']:.1f}h`.",
                action_taken=f"Acao configurada: `{action}`. Aplicada: `{'sim' if punished else 'nao'}`. Modo raid: `{'ativo' if raid_active else 'nao ativo'}`.",
                next_step="Se varias entradas continuarem, use Modo Crise e revise convites ativos.",
                color=0xE74C3C,
            )

    @commands.Cog.listener("on_guild_channel_delete")
    async def advanced_security_channel_delete(self, channel: disnake.abc.GuildChannel):
        guild = channel.guild
        cfg = self._guild_config(guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        entry = await self._audit_entry(guild, disnake.AuditLogAction.channel_delete, channel.id)
        triggered = await self._handle_critical_staff_action(
            guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "channel_delete",
            f"#{getattr(channel, 'name', 'canal')} ({channel.id})",
        )
        if triggered and isinstance(channel, disnake.TextChannel):
            await self._restore_text_channel(channel, cfg)

    @commands.Cog.listener("on_guild_channel_create")
    async def advanced_security_channel_create(self, channel: disnake.abc.GuildChannel):
        guild = channel.guild
        cfg = self._guild_config(guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        entry = await self._audit_entry(guild, disnake.AuditLogAction.channel_create, channel.id)
        triggered = await self._handle_critical_staff_action(
            guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "channel_create",
            f"#{getattr(channel, 'name', 'canal')} ({channel.id})",
        )
        if triggered:
            try:
                await channel.delete(reason="[Lyon] Anti Nuke: canal criado em massa")
            except disnake.HTTPException:
                pass

    @commands.Cog.listener("on_guild_role_delete")
    async def advanced_security_role_delete(self, role: disnake.Role):
        cfg = self._guild_config(role.guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        entry = await self._audit_entry(role.guild, disnake.AuditLogAction.role_delete, role.id)
        await self._handle_critical_staff_action(
            role.guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "role_delete",
            f"@{role.name} ({role.id})",
        )

    @commands.Cog.listener("on_guild_role_create")
    async def advanced_security_role_create(self, role: disnake.Role):
        cfg = self._guild_config(role.guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        entry = await self._audit_entry(role.guild, disnake.AuditLogAction.role_create, role.id)
        triggered = await self._handle_critical_staff_action(
            role.guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "role_create",
            f"@{role.name} ({role.id})",
        )
        if triggered and role.guild.me.top_role > role:
            try:
                await role.delete(reason="[Lyon] Anti Nuke: cargo criado em massa")
            except disnake.HTTPException:
                pass

    @commands.Cog.listener("on_member_ban")
    async def advanced_security_member_ban(self, guild: disnake.Guild, user: disnake.User):
        cfg = self._guild_config(guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        entry = await self._audit_entry(guild, disnake.AuditLogAction.ban, user.id)
        triggered = await self._handle_critical_staff_action(
            guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "member_ban",
            f"{user} ({user.id})",
        )
        if triggered:
            try:
                await guild.unban(user, reason="[Lyon] Anti Nuke: banimento em massa revertido")
            except disnake.HTTPException:
                pass

    @commands.Cog.listener("on_guild_channel_update")
    async def advanced_security_channel_update(self, before: disnake.abc.GuildChannel, after: disnake.abc.GuildChannel):
        guild = after.guild
        cfg = self._guild_config(guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        action = getattr(disnake.AuditLogAction, "channel_update", None)
        entry = await self._audit_entry(guild, action, after.id) if action else None
        await self._handle_critical_staff_action(
            guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "channel_update",
            f"#{getattr(after, 'name', 'canal')} ({after.id})",
        )

    @commands.Cog.listener("on_guild_role_update")
    async def advanced_security_role_update(self, before: disnake.Role, after: disnake.Role):
        cfg = self._guild_config(after.guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        action = getattr(disnake.AuditLogAction, "role_update", None)
        entry = await self._audit_entry(after.guild, action, after.id) if action else None
        await self._handle_critical_staff_action(
            after.guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "role_update",
            f"@{after.name} ({after.id})",
        )

    @commands.Cog.listener("on_member_update")
    async def advanced_security_member_update(self, before: disnake.Member, after: disnake.Member):
        if {role.id for role in before.roles} == {role.id for role in after.roles}:
            return
        cfg = self._guild_config(after.guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        action = getattr(disnake.AuditLogAction, "member_role_update", None)
        entry = await self._audit_entry(after.guild, action, after.id) if action else None
        await self._handle_critical_staff_action(
            after.guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "member_role_update",
            f"{after} ({after.id})",
        )

    @commands.Cog.listener("on_member_remove")
    async def advanced_security_member_remove(self, member: disnake.Member):
        cfg = self._guild_config(member.guild.id)
        if not as_bool(cfg.get("enabled"), False):
            return
        action = getattr(disnake.AuditLogAction, "kick", None)
        entry = await self._audit_entry(member.guild, action, member.id) if action else None
        if not entry:
            return
        await self._handle_critical_staff_action(
            member.guild,
            cfg,
            getattr(getattr(entry, "user", None), "id", None),
            "member_kick",
            f"{member} ({member.id})",
        )

    @commands.Cog.listener("on_button_click")
    async def advanced_security_global_button_audit(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if not cid or cid.startswith("AdvSec_") or not inter.guild:
            return
        cfg = self._guild_config(inter.guild.id)
        if not self._module_enabled(cfg, "staff_audit"):
            return
        member = inter.author if isinstance(inter.author, disnake.Member) else inter.guild.get_member(inter.author.id)
        if not self._should_audit_interaction(member, cid):
            return
        try:
            await self._record_staff_audit(inter.guild, cfg, inter.author.id, "button_interaction", cid, risk="medio")
        except Exception:
            pass

    @commands.Cog.listener("on_dropdown")
    async def advanced_security_global_dropdown_audit(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if not cid or cid.startswith("AdvSec_") or not inter.guild:
            return
        cfg = self._guild_config(inter.guild.id)
        if not self._module_enabled(cfg, "staff_audit"):
            return
        member = inter.author if isinstance(inter.author, disnake.Member) else inter.guild.get_member(inter.author.id)
        if not self._should_audit_interaction(member, cid):
            return
        try:
            await self._record_staff_audit(inter.guild, cfg, inter.author.id, "dropdown_interaction", cid, risk="medio")
        except Exception:
            pass

    @commands.Cog.listener("on_slash_command_completion")
    async def advanced_security_command_audit(self, inter):
        if not getattr(inter, "guild", None):
            return
        cfg = self._guild_config(inter.guild.id)
        if not self._module_enabled(cfg, "staff_audit"):
            return
        author = getattr(inter, "author", None) or getattr(inter, "user", None)
        member = author if isinstance(author, disnake.Member) else inter.guild.get_member(getattr(author, "id", 0))
        command = getattr(getattr(inter, "application_command", None), "qualified_name", "") or getattr(getattr(inter, "command", None), "qualified_name", "")
        if not self._should_audit_interaction(member, command):
            return
        try:
            await self._record_staff_audit(inter.guild, cfg, author.id, "slash_command", command, risk="medio")
        except Exception:
            pass

    @commands.Cog.listener("on_button_click")
    async def advanced_security_buttons(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if not cid.startswith("AdvSec_"):
            return

        if not getattr(inter.author.guild_permissions, "manage_guild", False):
            await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para configurar a seguranca.", ephemeral=True)
            return

        if cid == "AdvSec_Limits":
            cog = self
            cfg = self._guild_config(inter.guild.id)

            class LimitsModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Limites da Seguranca",
                        custom_id="AdvSec_LimitsModal",
                        components=[
                            disnake.ui.TextInput(label="Anti Spam: mensagens/janela", custom_id="spam", value=f"{cfg.get('spam_limit')}/{cfg.get('spam_window')}", placeholder="Ex.: 5/7", max_length=8),
                            disnake.ui.TextInput(label="Anti Raid: entradas/janela", custom_id="raid", value=f"{cfg.get('raid_limit')}/{cfg.get('raid_window')}", placeholder="Ex.: 6/20", max_length=8),
                            disnake.ui.TextInput(label="Anti Raid: risco/idade nova(h)", custom_id="raid_risk", value=f"{cfg.get('raid_risk_threshold')}/{cfg.get('raid_min_account_age_hours')}", placeholder="Ex.: 65/24", max_length=8),
                            disnake.ui.TextInput(label="Anti Nuke: acoes/janela", custom_id="nuke", value=f"{cfg.get('nuke_limit')}/{cfg.get('nuke_window')}", placeholder="Ex.: 3/20", max_length=8),
                            disnake.ui.TextInput(label="Staff Abuso: acoes/janela/crise", custom_id="staff", value=f"{cfg.get('staff_abuse_limit')}/{cfg.get('staff_abuse_window')}/{cfg.get('crisis_minutes')}", placeholder="Ex.: 4/60/15", max_length=10),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", {})
                    cfg_local = cog._guild_config(modal_inter.guild.id)
                    for prefix, limit_key, window_key in (
                        ("spam", "spam_limit", "spam_window"),
                        ("raid", "raid_limit", "raid_window"),
                        ("nuke", "nuke_limit", "nuke_window"),
                    ):
                        raw = str(values.get(prefix, "")).replace(" ", "")
                        if "/" in raw:
                            left, right = raw.split("/", 1)
                            cfg_local[limit_key] = max(1, int(left))
                            cfg_local[window_key] = max(3, int(right))
                    raw_risk = str(values.get("raid_risk", "")).replace(" ", "")
                    if "/" in raw_risk:
                        risk, min_age = raw_risk.split("/", 1)
                        cfg_local["raid_risk_threshold"] = max(1, min(100, int(risk)))
                        cfg_local["raid_min_account_age_hours"] = max(1, int(min_age))
                    raw_staff = str(values.get("staff", "")).replace(" ", "")
                    parts = raw_staff.split("/")
                    if len(parts) >= 2:
                        cfg_local["staff_abuse_limit"] = max(2, int(parts[0]))
                        cfg_local["staff_abuse_window"] = max(10, int(parts[1]))
                    if len(parts) >= 3:
                        cfg_local["crisis_minutes"] = max(1, int(parts[2]))
                    cog._save_guild_config(modal_inter.guild.id, cfg_local)
                    await cog._record_staff_audit(modal_inter.guild, cfg_local, modal_inter.user.id, "security_limits_update", "limites", risk="medio")
                    await modal_inter.response.send_message(f"{emoji.correct} Limites salvos.", ephemeral=True)

            await inter.response.send_modal(LimitsModal())
            return

        if cid == "AdvSec_Domains":
            cog = self
            cfg = self._guild_config(inter.guild.id)

            class DomainsModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Dominios Permitidos",
                        custom_id="AdvSec_DomainsModal",
                        components=[
                            disnake.ui.TextInput(
                                label="Dominios liberados",
                                custom_id="domains",
                                value=", ".join(cfg.get("allowed_domains", [])),
                                placeholder="exemplo.com, discord.com",
                                required=False,
                                max_length=500,
                                style=disnake.TextInputStyle.paragraph,
                            )
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    raw = getattr(modal_inter, "text_values", {}).get("domains", "")
                    domains = []
                    for item in re.split(r"[\n,; ]+", raw):
                        domain = item.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
                        if domain:
                            domains.append(domain.split("/")[0])
                    cfg_local = cog._guild_config(modal_inter.guild.id)
                    cfg_local["allowed_domains"] = sorted(set(domains))[:50]
                    cog._save_guild_config(modal_inter.guild.id, cfg_local)
                    await cog._record_staff_audit(modal_inter.guild, cfg_local, modal_inter.user.id, "security_domains_update", ", ".join(cfg_local["allowed_domains"][:10]), risk="medio")
                    await modal_inter.response.send_message(f"{emoji.correct} Dominios permitidos atualizados.", ephemeral=True)

            await inter.response.send_modal(DomainsModal())
            return

        try:
            await inter.response.defer(with_message=False)
        except disnake.NotFound:
            return
        except disnake.HTTPException:
            pass

        cfg = self._guild_config(inter.guild.id)
        if cid.startswith("AdvSec_Toggle:"):
            key = cid.split(":", 1)[1]
            if key in DEFAULT_GUILD_CONFIG and isinstance(DEFAULT_GUILD_CONFIG[key], bool):
                self._toggle_cfg(cfg, key)
                self._save_guild_config(inter.guild.id, cfg)
                await self._record_staff_audit(inter.guild, cfg, inter.user.id, "security_toggle", key, risk="medio")
            await inter.edit_original_message(content=None, embed=None, components=self._main_components(inter.guild.id))
            return

        if cid == "AdvSec_Crisis":
            if self._crisis_active(cfg):
                await self._deactivate_crisis_mode(inter.guild, cfg, f"Desativado manualmente por {inter.user} ({inter.user.id}).")
                await inter.edit_original_message(content=None, embed=None, components=self._main_components(inter.guild.id))
                await inter.followup.send(f"{emoji.correct} Modo Crise desativado e canais restaurados.", ephemeral=True)
            else:
                await self._activate_crisis_mode(
                    inter.guild,
                    cfg,
                    f"Acionado manualmente por {inter.user} ({inter.user.id}) pelo painel.",
                    actor_id=inter.user.id,
                    minutes=cfg.get("crisis_minutes", 15),
                )
                await inter.edit_original_message(content=None, embed=None, components=self._main_components(inter.guild.id))
                await inter.followup.send(f"{emoji.correct} Modo Crise ativado.", ephemeral=True)
            return

        if cid == "AdvSec_Punishment":
            new_value = self._cycle_punishment(cfg)
            self._save_guild_config(inter.guild.id, cfg)
            await self._record_staff_audit(inter.guild, cfg, inter.user.id, "security_punishment", new_value, risk="medio")
            await inter.edit_original_message(content=None, embed=None, components=self._main_components(inter.guild.id))
            await inter.followup.send(f"{emoji.correct} Punicao padrao definida para `{new_value}`.", ephemeral=True)
            return

        if cid == "AdvSec_Targets":
            await inter.edit_original_message(content=None, embed=None, components=self._targets_components(inter.guild.id))
            return

        if cid == "AdvSec_Back":
            await inter.edit_original_message(content=None, embed=None, components=self._main_components(inter.guild.id))
            return

        if cid == "AdvSec_ClearLog":
            cfg["log_channel_id"] = None
            self._save_guild_config(inter.guild.id, cfg)
            await inter.edit_original_message(content=None, embed=None, components=self._targets_components(inter.guild.id))

    @commands.Cog.listener("on_dropdown")
    async def advanced_security_dropdowns(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if not cid.startswith("AdvSec_Select"):
            return

        if not getattr(inter.author.guild_permissions, "manage_guild", False):
            await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para configurar a seguranca.", ephemeral=True)
            return

        try:
            await inter.response.defer(with_message=False)
        except disnake.NotFound:
            return
        except disnake.HTTPException:
            pass

        cfg = self._guild_config(inter.guild.id)
        if cid == "AdvSec_SelectLog":
            cfg["log_channel_id"] = int(inter.values[0]) if inter.values else None
        elif cid == "AdvSec_SelectRoles":
            cfg["immune_roles"] = [int(value) for value in inter.values]
        elif cid == "AdvSec_SelectChannels":
            cfg["ignored_channels"] = [int(value) for value in inter.values]
        elif cid == "AdvSec_SelectPros":
            cfg["allowed_bots"] = [int(value) for value in inter.values]
        self._save_guild_config(inter.guild.id, cfg)
        await self._record_staff_audit(inter.guild, cfg, inter.user.id, "security_targets_update", cid, risk="medio")
        await inter.edit_original_message(content=None, embed=None, components=self._targets_components(inter.guild.id))


def setup(bot: commands.Bot):
    bot.add_cog(AdvancedSecurityCog(bot))
