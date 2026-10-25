import re
import secrets
from datetime import datetime, timezone

import disnake
from disnake.ext import commands, tasks

from functions.bool_utils import as_bool
from functions.database import database as db
from functions.emoji import emoji


KEY_PREFIX = "parcerias_"
DEFAULT_PANEL_TITLE = "Pro Parceria"
DEFAULT_PANEL_DESCRIPTION = "Para solicitar uma parceria, clique no botao abaixo."
DEFAULT_BUTTON_LABEL = "Realizar Parceria"
DEFAULT_FOOTER = "Powered by Lyon Pro"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _get_emoji(name: str, fallback=None):
    return getattr(emoji, name, fallback)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_text(text: str, limit: int = 180) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


class Parcerias(commands.Cog):
    """Sistema de parcerias com solicitacao, analise e aprovacao."""

    BLOCK_PATTERNS = {
        "adulto/porno": [
            r"\bporno\b",
            r"\bporn\b",
            r"\bxxx\b",
            r"\b18\+\b",
            r"\bnude(s|z)?\b",
            r"\bonlyfans\b",
            r"\bconteudo adulto\b",
            r"\bsexo\b",
        ],
        "golpe/scam": [
            r"\bscam\b",
            r"\bgolpe\b",
            r"\bphishing\b",
            r"\broubo\b",
            r"\bclon(a|e)\b",
            r"\bcarding\b",
            r"\bcc full\b",
        ],
        "ilegal": [
            r"\bdroga(s)?\b",
            r"\btrafico\b",
            r"\barma(s)?\b",
            r"\bfraude\b",
            r"\bcrackeado\b",
            r"\bmalware\b",
            r"\btoken grabber\b",
        ],
        "odio/violencia": [
            r"\bnazismo\b",
            r"\bracismo\b",
            r"\bterrorismo\b",
            r"\bamea(c|ç)a\b",
        ],
    }

    REVIEW_PATTERNS = {
        "divulgacao comercial": [r"\bvenda(s)?\b", r"\bloja\b", r"\bproduto(s)?\b", r"\bservi(c|ç)o(s)?\b"],
        "comunidade/discord": [r"\bdiscord\b", r"\bservidor\b", r"\bcomunidade\b", r"\bmembro(s)?\b"],
        "social/midia": [r"\binstagram\b", r"\btiktok\b", r"\byoutube\b", r"\btwitter\b", r"\bx\b"],
        "sorteio/evento": [r"\bsorteio\b", r"\bevento\b", r"\bgiveaway\b", r"\bpremio\b"],
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._auto_approve_partnerships.start()

    def cog_unload(self):
        self._auto_approve_partnerships.cancel()

    def _flags(self) -> disnake.MessageFlags:
        return disnake.MessageFlags(is_components_v2=True)

    def _is_invalid_emoji_error(self, error: disnake.HTTPException) -> bool:
        return getattr(error, "code", None) == 50035 and "Invalid emoji" in str(error)

    def _strip_component_emojis(self, components: list):
        def strip_item(item):
            if hasattr(item, "emoji"):
                try:
                    item.emoji = None
                except Exception:
                    pass
            for option in getattr(item, "options", []) or []:
                try:
                    option.emoji = None
                except Exception:
                    pass
            for child in list(getattr(item, "children", []) or []):
                strip_item(child)

        for component in components or []:
            strip_item(component)
        return components

    async def _send_components_to_channel(self, channel: disnake.TextChannel, components: list):
        try:
            return await channel.send(components=components, flags=self._flags())
        except disnake.HTTPException as exc:
            if self._is_invalid_emoji_error(exc):
                return await channel.send(components=self._strip_component_emojis(components), flags=self._flags())
            raise

    def _get_key(self, guild_id: int) -> str:
        return f"{KEY_PREFIX}{guild_id}"

    def _get_config(self, guild_id: int) -> dict:
        data = db.get_document(self._get_key(guild_id)) or {}
        return data if isinstance(data, dict) else {}

    def _save_config(self, guild_id: int, data: dict) -> None:
        data = dict(data or {})
        data["guild_id"] = guild_id
        data["enabled"] = as_bool(data.get("enabled"), False)
        if "smart_blocker_enabled" not in data:
            data["smart_blocker_enabled"] = True
        else:
            data["smart_blocker_enabled"] = as_bool(data.get("smart_blocker_enabled"), True)
        db.save_document(self._get_key(guild_id), data)

    def _container_kwargs(self) -> dict:
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary") or "#5865f2"
        try:
            return {"accent_colour": disnake.Colour(int(primary_color_hex.replace("#", ""), 16))}
        except Exception:
            return {"accent_colour": disnake.Colour.blurple()}

    def _channel_text(self, channel_id) -> str:
        if not channel_id:
            return "`Nao configurado`"
        return f"<#{channel_id}>"

    def _status_text(self, enabled: bool) -> str:
        return "`Ativo`" if enabled else "`Inativo`"

    def _valid_banner(self, url: str | None) -> bool:
        return bool(url and str(url).startswith(("http://", "https://")))

    def _proof_required(self, cfg: dict) -> bool:
        return as_bool(cfg.get("proof_required"), True)

    def _smart_blocker_enabled(self, cfg: dict) -> bool:
        if "smart_blocker_enabled" not in cfg:
            return True
        return as_bool(cfg.get("smart_blocker_enabled"), True)

    def _is_image_attachment(self, attachment: disnake.Attachment) -> bool:
        content_type = str(getattr(attachment, "content_type", "") or "").lower()
        filename = str(getattr(attachment, "filename", "") or "").lower()
        return content_type.startswith("image/") or filename.endswith(IMAGE_EXTENSIONS)

    def _proof_from_message(self, message: disnake.Message) -> dict | None:
        attachment = next((att for att in message.attachments if self._is_image_attachment(att)), None)
        if not attachment:
            return None

        width = int(getattr(attachment, "width", 0) or 0)
        height = int(getattr(attachment, "height", 0) or 0)
        size = int(getattr(attachment, "size", 0) or 0)
        confidence = 50
        reasons = ["arquivo de imagem detectado"]

        if width >= 300 and height >= 200:
            confidence += 20
            reasons.append("resolucao suficiente")
        if size >= 20_000:
            confidence += 15
            reasons.append("tamanho compativel com print/foto")
        if any(word in (message.content or "").lower() for word in ("parceria", "print", "comprovante", "divulguei", "feito")):
            confidence += 10
            reasons.append("mensagem indica comprovante")

        confidence = min(confidence, 100)
        return {
            "url": attachment.url,
            "proxy_url": getattr(attachment, "proxy_url", None),
            "filename": attachment.filename,
            "content_type": getattr(attachment, "content_type", None),
            "size": size,
            "width": width,
            "height": height,
            "message_id": message.id,
            "channel_id": message.channel.id,
            "submitted_at": _now_iso(),
            "analysis": {
                "valid": confidence >= 55,
                "confidence": confidence,
                "reason": "; ".join(reasons),
            },
        }

    def _auto_minutes(self, value) -> int:
        try:
            return max(1, min(1440, int(value)))
        except (TypeError, ValueError):
            return 30

    def _parse_dt(self, value: str | None) -> datetime:
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return datetime.now(timezone.utc)

    def _can_manage(self, inter: disnake.MessageInteraction) -> bool:
        perms = getattr(inter.author, "guild_permissions", None)
        return bool(perms and (perms.administrator or perms.manage_guild))

    def _cases(self, cfg: dict) -> dict:
        cases = cfg.get("cases")
        if not isinstance(cases, dict):
            cfg["cases"] = {}
        return cfg["cases"]

    def _moderate_text(self, text: str, smart_blocker_enabled: bool = True) -> dict:
        if not smart_blocker_enabled:
            return {
                "blocked": False,
                "needs_review": False,
                "score": 0,
                "type": "parceria geral",
                "categories": [],
                "reason": "bloqueador inteligente desativado; enviado para fluxo normal",
                "smart_blocker_enabled": False,
            }

        lowered = (text or "").lower()
        blocked_categories = []
        review_categories = []

        for category, patterns in self.BLOCK_PATTERNS.items():
            if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns):
                blocked_categories.append(category)

        for category, patterns in self.REVIEW_PATTERNS.items():
            if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns):
                review_categories.append(category)

        invite_count = len(re.findall(r"(discord\.gg/|discord\.com/invite/)", lowered))
        link_count = len(re.findall(r"https?://|discord\.gg/|discord\.com/invite/", lowered))
        mention_count = lowered.count("@everyone") + lowered.count("@here")

        score = 8
        reasons = []
        if blocked_categories:
            score = 98
            reasons.append("categoria bloqueada: " + ", ".join(blocked_categories))
        if invite_count > 2:
            score = max(score, 70)
            reasons.append("muitos convites no texto")
        if link_count > 6:
            score = max(score, 65)
            reasons.append("muitos links no texto")
        if mention_count:
            score = max(score, 75)
            reasons.append("mencoes globais nao permitidas")

        blocked = score >= 90
        needs_review = not blocked and score >= 60
        partnership_type = ", ".join(review_categories[:3]) if review_categories else "parceria geral"

        return {
            "blocked": blocked,
            "needs_review": needs_review,
            "score": score,
            "type": partnership_type,
            "categories": blocked_categories or review_categories,
            "reason": "; ".join(reasons) if reasons else "texto aprovado pela analise local",
            "smart_blocker_enabled": True,
        }

    def _build_admin_panel(self, guild_id: int) -> list:
        cfg = self._get_config(guild_id)
        enabled = as_bool(cfg.get("enabled"), False)
        cases = self._cases(cfg)
        pending = sum(1 for case in cases.values() if case.get("status") == "pending")
        waiting_proof = sum(1 for case in cases.values() if case.get("status") == "waiting_proof")
        approved = sum(1 for case in cases.values() if case.get("status") == "approved")
        blocked = sum(1 for case in cases.values() if case.get("status") == "blocked")
        auto_approve = as_bool(cfg.get("auto_approve_enabled"), False)
        auto_minutes = self._auto_minutes(cfg.get("auto_approve_minutes", 30))
        proof_required = self._proof_required(cfg)
        smart_blocker = self._smart_blocker_enabled(cfg)

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"## {_get_emoji('partner', '')} Parcerias Automaticas"),
            disnake.ui.TextDisplay("-# Painel > **Parcerias**"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                "Configure o painel publico de parceria, o canal de solicitacoes e o canal final onde as parcerias aprovadas serao publicadas."
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                f"**Status:** {self._status_text(enabled)}\n"
                f"**Canal do painel:** {self._channel_text(cfg.get('panel_channel_id'))}\n"
                f"**Canal de solicitacoes:** {self._channel_text(cfg.get('review_channel_id'))}\n"
                f"**Canal de destino:** {self._channel_text(cfg.get('destination_channel_id'))}\n"
                f"**Banner:** `{'Configurado' if self._valid_banner(cfg.get('banner_url')) else 'Nao configurado'}`\n"
                f"**Bloqueador inteligente:** `{('Ativo' if smart_blocker else 'Inativo')}`\n"
                f"**Comprovante por foto:** `{('Obrigatorio' if proof_required else 'Opcional')}`\n"
                f"**Autoaprovar:** `{('Ativo' if auto_approve else 'Inativo')}` apos `{auto_minutes} minuto(s)`\n"
                f"**Aguardando foto:** `{waiting_proof}` | **Pendentes:** `{pending}` | **Aprovadas:** `{approved}` | **Bloqueadas:** `{blocked}`"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Desativar" if enabled else "Ativar",
                    style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success,
                    emoji=_get_emoji("power"),
                    custom_id=f"Parcerias_Toggle:{guild_id}",
                ),
                disnake.ui.Button(label="Canais", style=disnake.ButtonStyle.blurple, emoji=_get_emoji("canal", _get_emoji("textc")), custom_id=f"Parcerias_Channels:{guild_id}"),
                disnake.ui.Button(label="Personalizar", style=disnake.ButtonStyle.grey, emoji=_get_emoji("paint", _get_emoji("edit")), custom_id=f"Parcerias_Customize:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Enviar Painel", style=disnake.ButtonStyle.success, emoji=_get_emoji("send", _get_emoji("rocket")), custom_id=f"Parcerias_SendPanel:{guild_id}"),
                disnake.ui.Button(label="Pendentes", style=disnake.ButtonStyle.grey, emoji=_get_emoji("receipt", _get_emoji("listening_music")), custom_id=f"Parcerias_Pending:{guild_id}"),
                disnake.ui.Button(label="Preview", style=disnake.ButtonStyle.grey, emoji=_get_emoji("preview", _get_emoji("search")), custom_id=f"Parcerias_Preview:{guild_id}"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Autoaprovar: Ativo" if auto_approve else "Autoaprovar: Inativo",
                    style=disnake.ButtonStyle.success if auto_approve else disnake.ButtonStyle.grey,
                    emoji=_get_emoji("clock"),
                    custom_id=f"Parcerias_AutoApprove:{guild_id}",
                ),
                disnake.ui.Button(label="Tempo Auto", style=disnake.ButtonStyle.grey, emoji=_get_emoji("time", _get_emoji("clock")), custom_id=f"Parcerias_AutoTime:{guild_id}"),
                disnake.ui.Button(
                    label="Foto: Obrigatoria" if proof_required else "Foto: Opcional",
                    style=disnake.ButtonStyle.success if proof_required else disnake.ButtonStyle.grey,
                    emoji=_get_emoji("image", _get_emoji("attach", _get_emoji("foto"))),
                    custom_id=f"Parcerias_ProofRequired:{guild_id}",
                ),
                disnake.ui.Button(
                    label="Bloqueador: Ativo" if smart_blocker else "Bloqueador: Inativo",
                    style=disnake.ButtonStyle.success if smart_blocker else disnake.ButtonStyle.grey,
                    emoji=_get_emoji("shield", _get_emoji("warn")),
                    custom_id=f"Parcerias_SmartBlocker:{guild_id}",
                )
            ),
            **self._container_kwargs(),
        )
        return [
            container,
        ]

    def _build_channels_panel(self, guild_id: int) -> list:
        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"## {_get_emoji('canal', '')} Canais de Parceria"),
            disnake.ui.TextDisplay("-# Painel > Parcerias > **Canais**"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay("Configure onde o painel aparece, onde chegam as solicitacoes e onde a parceria aprovada sera publicada."),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.ChannelSelect(
                    placeholder="Canal onde sera publicado o painel",
                    custom_id=f"Parcerias_SelectPanelChannel:{guild_id}",
                    min_values=1,
                    max_values=1,
                    channel_types=[disnake.ChannelType.text],
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.ChannelSelect(
                    placeholder="Canal onde chegam as solicitacoes",
                    custom_id=f"Parcerias_SelectReviewChannel:{guild_id}",
                    min_values=1,
                    max_values=1,
                    channel_types=[disnake.ChannelType.text],
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.ChannelSelect(
                    placeholder="Canal final das parcerias aprovadas",
                    custom_id=f"Parcerias_SelectDestinationChannel:{guild_id}",
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

    def _build_public_panel(self, guild_id: int) -> list:
        cfg = self._get_config(guild_id)
        title = cfg.get("panel_title") or DEFAULT_PANEL_TITLE
        description = cfg.get("panel_description") or DEFAULT_PANEL_DESCRIPTION
        button_label = cfg.get("button_label") or DEFAULT_BUTTON_LABEL
        footer = cfg.get("footer") or DEFAULT_FOOTER
        banner_url = cfg.get("banner_url")
        proof_line = "\n- " + str(_get_emoji("image", "")) + " Sera necessario enviar uma foto/print comprovando que a parceria foi feita." if self._proof_required(cfg) else ""

        children = []
        if self._valid_banner(banner_url):
            children.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(str(banner_url))))
            children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
        children.extend(
            [
                disnake.ui.TextDisplay(f"### {_get_emoji('announcement', '')} Sistema Parceria"),
                disnake.ui.TextDisplay(f"## {_get_emoji('members', '')} | {title}"),
                disnake.ui.TextDisplay(f"- {_get_emoji('rocket', '')} {description}{proof_line}\n-# {_get_emoji('flag', '')} | {footer}"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label=button_label[:80],
                        style=disnake.ButtonStyle.success,
                        emoji=_get_emoji("relations", _get_emoji("partner", _get_emoji("link"))),
                        custom_id=f"Parcerias_Request:{guild_id}",
                    )
                ),
            ]
        )
        return [disnake.ui.Container(*children, **self._container_kwargs())]

    def _build_review_components(self, guild_id: int, case_id: str, case: dict) -> list:
        moderation = case.get("moderation") or {}
        user_id = case.get("user_id")
        status = case.get("status", "pending")
        status_text = {
            "waiting_proof": "Aguardando foto",
            "pending": "Pendente",
            "approved": "Aprovada",
            "rejected": "Recusada",
            "blocked": "Bloqueada",
        }.get(status, status)

        disabled = status != "pending"
        proof = case.get("proof") or {}
        proof_analysis = proof.get("analysis") or {}
        proof_url = proof.get("url")
        proof_text = "`Nao enviado`"
        if proof:
            proof_text = (
                f"`Recebido` | Confianca: `{proof_analysis.get('confidence', 0)}/100`\n"
                f"Arquivo: `{proof.get('filename', 'imagem')}` | Resolucao: `{proof.get('width', 0)}x{proof.get('height', 0)}`\n"
                f"Analise: `{proof_analysis.get('reason', 'imagem recebida')}`"
            )

        children = [
            disnake.ui.TextDisplay(f"## {_get_emoji('partner', '')} Solicitacao de Parceria"),
            disnake.ui.TextDisplay(
                f"**Solicitante:** <@{user_id}>\n"
                f"**ID:** `{case_id}`\n"
                f"**Status:** `{status_text}`\n"
                f"**Tipo detectado:** `{moderation.get('type', 'parceria geral')}`\n"
                f"**Score IA:** `{moderation.get('score', 0)}/100`\n"
                f"**Analise:** `{moderation.get('reason', 'sem analise')}`"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(f"**Texto enviado:**\n{case.get('message', '')[:3500]}"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(f"**Comprovante por foto:**\n{proof_text}"),
        ]
        if self._valid_banner(proof_url):
            children.extend(
                [
                    disnake.ui.MediaGallery(disnake.MediaGalleryItem(str(proof_url))),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                ]
            )
        children.append(
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Aprovar", style=disnake.ButtonStyle.success, emoji=_get_emoji("correct"), custom_id=f"Parcerias_Approve:{guild_id}:{case_id}", disabled=disabled),
                disnake.ui.Button(label="Recusar", style=disnake.ButtonStyle.danger, emoji=_get_emoji("wrong"), custom_id=f"Parcerias_Reject:{guild_id}:{case_id}", disabled=disabled),
                disnake.ui.Button(label="Bloquear", style=disnake.ButtonStyle.danger, emoji=_get_emoji("forbidden", _get_emoji("ban")), custom_id=f"Parcerias_Block:{guild_id}:{case_id}", disabled=disabled),
            )
        )
        container = disnake.ui.Container(*children, **self._container_kwargs())
        return [container]

    def _build_final_components(self, guild_id: int, case: dict) -> list:
        cfg = self._get_config(guild_id)
        banner_url = cfg.get("final_banner_url") or cfg.get("banner_url")
        footer = cfg.get("footer") or DEFAULT_FOOTER
        moderation = case.get("moderation") or {}

        children = []
        if self._valid_banner(banner_url):
            children.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(str(banner_url))))
            children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
        children.extend(
            [
                disnake.ui.TextDisplay(case.get("message", "")[:3800]),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"-# {_get_emoji('verified', '')} Parceria aprovada | Tipo: `{moderation.get('type', 'parceria geral')}` | {footer}"
                ),
            ]
        )
        return [disnake.ui.Container(*children, **self._container_kwargs())]

    async def _defer_safely(self, inter: disnake.MessageInteraction, *, with_message: bool = False) -> bool:
        if inter.response.is_done():
            return True
        try:
            await inter.response.defer(with_message=with_message)
            return True
        except disnake.NotFound:
            return False
        except disnake.HTTPException as exc:
            if getattr(exc, "code", None) == 40060:
                return True
            if getattr(exc, "code", None) == 10062:
                return False
            print(f"[Parcerias] Falha ao deferir interacao: {exc}")
            return False

    async def _followup_safely(self, inter, text: str, *, ephemeral: bool = True):
        try:
            await inter.followup.send(text, ephemeral=ephemeral)
        except (disnake.NotFound, disnake.HTTPException):
            pass

    async def _respond_safely(self, inter, text: str, *, ephemeral: bool = True):
        try:
            if inter.response.is_done():
                await inter.followup.send(text, ephemeral=ephemeral)
            else:
                await inter.response.send_message(text, ephemeral=ephemeral)
        except (disnake.NotFound, disnake.HTTPException):
            pass

    async def _respond_components_safely(self, inter, components: list, *, ephemeral: bool = True):
        try:
            if inter.response.is_done():
                await inter.followup.send(components=components, flags=self._flags(), ephemeral=ephemeral)
            else:
                await inter.response.send_message(components=components, flags=self._flags(), ephemeral=ephemeral)
        except disnake.NotFound:
            pass
        except disnake.HTTPException as exc:
            if not self._is_invalid_emoji_error(exc):
                return
            try:
                components = self._strip_component_emojis(components)
                if inter.response.is_done():
                    await inter.followup.send(components=components, flags=self._flags(), ephemeral=ephemeral)
                else:
                    await inter.response.send_message(components=components, flags=self._flags(), ephemeral=ephemeral)
            except (disnake.NotFound, disnake.HTTPException):
                pass

    async def _edit_message_safely(self, message: disnake.Message | None, guild_id: int) -> bool:
        if not message:
            return False
        try:
            await message.edit(content=None, embed=None, components=self._build_admin_panel(guild_id), flags=self._flags())
            return True
        except disnake.NotFound:
            return False
        except disnake.HTTPException as exc:
            if self._is_invalid_emoji_error(exc):
                try:
                    await message.edit(content=None, embed=None, components=self._strip_component_emojis(self._build_admin_panel(guild_id)), flags=self._flags())
                    return True
                except disnake.HTTPException:
                    pass
            print(f"[Parcerias] Falha ao editar mensagem do painel: {exc}")
            return False

    async def _edit_components(self, inter: disnake.MessageInteraction, components: list):
        acknowledged = await self._defer_safely(inter, with_message=False)
        if acknowledged:
            try:
                await inter.edit_original_message(content=None, embed=None, components=components, flags=self._flags())
                return
            except disnake.NotFound:
                pass
            except disnake.HTTPException as exc:
                if self._is_invalid_emoji_error(exc):
                    try:
                        await inter.edit_original_message(content=None, embed=None, components=self._strip_component_emojis(components), flags=self._flags())
                        return
                    except disnake.HTTPException:
                        pass
                if getattr(exc, "code", None) not in {10008, 10062, 40060}:
                    print(f"[Parcerias] Falha ao editar resposta original: {exc}")

        message = getattr(inter, "message", None)
        if message:
            try:
                await message.edit(content=None, embed=None, components=components, flags=self._flags())
            except disnake.NotFound:
                pass
            except disnake.HTTPException as exc:
                if self._is_invalid_emoji_error(exc):
                    try:
                        await message.edit(content=None, embed=None, components=self._strip_component_emojis(components), flags=self._flags())
                        return
                    except disnake.HTTPException:
                        pass
                print(f"[Parcerias] Falha ao editar mensagem por fallback: {exc}")

    async def _send_review(self, guild: disnake.Guild, cfg: dict, case_id: str, case: dict) -> disnake.Message | None:
        channel_id = cfg.get("review_channel_id")
        channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
        if not isinstance(channel, disnake.TextChannel):
            return None
        return await self._send_components_to_channel(channel, self._build_review_components(guild.id, case_id, case))

    async def _publish_case(self, guild: disnake.Guild, cfg: dict, case: dict) -> disnake.Message | None:
        channel_id = cfg.get("destination_channel_id")
        channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
        if not isinstance(channel, disnake.TextChannel):
            return None
        return await self._send_components_to_channel(channel, self._build_final_components(guild.id, case))

    async def _approve_case(self, guild: disnake.Guild, cfg: dict, case_id: str, case: dict, approved_by: int | str = "auto") -> disnake.Message | None:
        published = await self._publish_case(guild, cfg, case)
        if not published:
            return None

        cases = self._cases(cfg)
        case["status"] = "approved"
        case["approved_by"] = approved_by
        case["reviewed_at"] = _now_iso()
        case["published_message_id"] = published.id
        case["published_channel_id"] = published.channel.id
        cases[case_id] = case
        self._save_config(guild.id, cfg)
        return published

    async def _update_review_message(self, guild: disnake.Guild, cfg: dict, case_id: str, case: dict):
        channel_id = case.get("review_channel_id") or cfg.get("review_channel_id")
        message_id = case.get("review_message_id")
        channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
        if not isinstance(channel, disnake.TextChannel) or not message_id:
            return
        message = None
        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(components=self._build_review_components(guild.id, case_id, case), flags=self._flags())
        except disnake.HTTPException as exc:
            if message and self._is_invalid_emoji_error(exc):
                try:
                    await message.edit(components=self._strip_component_emojis(self._build_review_components(guild.id, case_id, case)), flags=self._flags())
                except disnake.HTTPException:
                    pass

    @tasks.loop(minutes=1)
    async def _auto_approve_partnerships(self):
        for guild in list(self.bot.guilds):
            cfg = self._get_config(guild.id)
            if not as_bool(cfg.get("enabled"), False) or not as_bool(cfg.get("auto_approve_enabled"), False):
                continue
            if not cfg.get("destination_channel_id"):
                continue

            cases = self._cases(cfg)
            delay_seconds = self._auto_minutes(cfg.get("auto_approve_minutes", 30)) * 60
            now = datetime.now(timezone.utc)

            for case_id, case in list(cases.items()):
                if case.get("status") != "pending":
                    continue
                if self._proof_required(cfg) and not case.get("proof"):
                    continue
                moderation = case.get("moderation") or {}
                if moderation.get("blocked") or moderation.get("needs_review") or int(moderation.get("score", 0) or 0) >= 60:
                    continue
                created_at = self._parse_dt(case.get("created_at"))
                if (now - created_at).total_seconds() < delay_seconds:
                    continue

                try:
                    published = await self._approve_case(guild, cfg, case_id, case, approved_by="auto")
                    if published:
                        await self._update_review_message(guild, cfg, case_id, case)
                except Exception as exc:
                    print(f"[Parcerias] Erro na autoaprovacao: {exc}")

    @_auto_approve_partnerships.before_loop
    async def _before_auto_approve_partnerships(self):
        await self.bot.wait_until_ready()

    async def display_parcerias_panel(self, inter: disnake.MessageInteraction):
        return self._build_admin_panel(inter.guild.id)

    def _waiting_proof_case(self, cfg: dict, user_id: int, channel_id: int):
        waiting = []
        for case_id, case in self._cases(cfg).items():
            if case.get("status") != "waiting_proof":
                continue
            if str(case.get("user_id")) != str(user_id):
                continue
            proof_channel_id = case.get("proof_channel_id")
            if proof_channel_id and str(proof_channel_id) != str(channel_id):
                continue
            waiting.append((case_id, case))
        waiting.sort(key=lambda item: self._parse_dt(item[1].get("created_at")), reverse=True)
        return waiting[0] if waiting else (None, None)

    @commands.Cog.listener("on_message")
    async def on_message(self, message: disnake.Message):
        if not message.guild or message.author.bot:
            return
        if not message.attachments:
            return

        cfg = self._get_config(message.guild.id)
        if not as_bool(cfg.get("enabled"), False) or not self._proof_required(cfg):
            return

        case_id, case = self._waiting_proof_case(cfg, message.author.id, message.channel.id)
        if not case_id or not case:
            return

        proof = self._proof_from_message(message)
        if not proof:
            try:
                await message.reply(f"{emoji.wrong} Envie uma imagem valida como comprovante da parceria.", mention_author=True)
            except disnake.HTTPException:
                pass
            return

        proof_analysis = proof.get("analysis") or {}
        if not proof_analysis.get("valid"):
            try:
                await message.reply(
                    f"{emoji.warn} Recebi a imagem, mas ela parece pequena ou incompleta. Envie um print/foto mais claro da parceria.",
                    mention_author=True,
                )
            except disnake.HTTPException:
                pass
            return

        cases = self._cases(cfg)
        case["proof"] = proof
        case["status"] = "pending"
        case["proof_received_at"] = _now_iso()
        cases[case_id] = case
        self._save_config(message.guild.id, cfg)

        review_message = await self._send_review(message.guild, cfg, case_id, case)
        if review_message:
            case["review_message_id"] = review_message.id
            case["review_channel_id"] = review_message.channel.id
            cases[case_id] = case
            self._save_config(message.guild.id, cfg)
            reply_text = f"{emoji.correct} Comprovante recebido. Sua parceria foi enviada para analise da staff."
        else:
            reply_text = f"{emoji.warn} Comprovante recebido, mas nao consegui enviar para o canal de analise. Avise a staff."

        try:
            await message.reply(reply_text, mention_author=True)
        except disnake.HTTPException:
            pass

    @commands.Cog.listener("on_button_click")
    async def on_button(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if not cid.startswith("Parcerias_"):
            return

        parts = cid.split(":")
        action = parts[0].split("_", 1)[1]
        guild_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else inter.guild.id

        if action == "Request":
            class PartnershipModal(disnake.ui.Modal):
                def __init__(self, outer: "Parcerias"):
                    self.outer = outer
                    super().__init__(
                        title="Realizar Parceria",
                        custom_id=f"Parcerias_RequestModal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(
                                label="Texto da parceria",
                                custom_id="message",
                                style=disnake.TextInputStyle.paragraph,
                                placeholder="Cole aqui o texto completo da sua parceria.",
                                required=True,
                                max_length=4000,
                            ),
                            disnake.ui.TextInput(
                                label="Observacao para o admin",
                                custom_id="note",
                                style=disnake.TextInputStyle.short,
                                placeholder="Opcional",
                                required=False,
                                max_length=200,
                            ),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    message_text = (values.get("message") or "").strip()
                    note = (values.get("note") or "").strip()
                    if len(message_text) < 20:
                        await modal_inter.response.send_message(f"{emoji.wrong} Envie um texto de parceria mais completo.", ephemeral=True)
                        return

                    if not modal_inter.response.is_done():
                        await modal_inter.response.defer(ephemeral=True)

                    cfg_local = self.outer._get_config(guild_id)
                    if not as_bool(cfg_local.get("enabled"), False):
                        await modal_inter.followup.send(f"{emoji.wrong} O sistema de parcerias esta desativado no momento.", ephemeral=True)
                        return

                    if not cfg_local.get("review_channel_id"):
                        await modal_inter.followup.send(f"{emoji.wrong} O canal de solicitacoes ainda nao foi configurado.", ephemeral=True)
                        return

                    moderation = self.outer._moderate_text(
                        message_text,
                        self.outer._smart_blocker_enabled(cfg_local),
                    )
                    proof_required = self.outer._proof_required(cfg_local)
                    case_id = secrets.token_hex(4)
                    case = {
                        "id": case_id,
                        "user_id": modal_inter.user.id,
                        "message": message_text,
                        "note": note,
                        "status": "blocked" if moderation.get("blocked") else ("waiting_proof" if proof_required else "pending"),
                        "moderation": moderation,
                        "proof_required": proof_required,
                        "proof_channel_id": getattr(modal_inter.channel, "id", None) if proof_required else None,
                        "created_at": _now_iso(),
                    }
                    cases = self.outer._cases(cfg_local)
                    cases[case_id] = case
                    self.outer._save_config(guild_id, cfg_local)

                    if case["status"] != "waiting_proof":
                        review_message = await self.outer._send_review(modal_inter.guild, cfg_local, case_id, case)
                        if review_message:
                            case["review_message_id"] = review_message.id
                            case["review_channel_id"] = review_message.channel.id
                            cases[case_id] = case
                            self.outer._save_config(guild_id, cfg_local)
                        elif not moderation.get("blocked"):
                            await modal_inter.followup.send(
                                f"{emoji.wrong} Nao consegui enviar a solicitacao ao canal de analise. Verifique minhas permissoes no canal configurado.",
                                ephemeral=True,
                            )
                            return

                    if moderation.get("blocked"):
                        await modal_inter.followup.send(
                            f"{emoji.wrong} Sua parceria foi bloqueada automaticamente pela analise IA local. Motivo: `{moderation.get('reason')}`",
                            ephemeral=True,
                        )
                    elif proof_required:
                        await modal_inter.followup.send(
                            f"{emoji.correct} Texto recebido. Agora envie uma **foto/print do comprovante da parceria** neste canal para liberar a analise da staff.",
                            ephemeral=True,
                        )
                    else:
                        await modal_inter.followup.send(
                            f"{emoji.correct} Sua parceria foi enviada para analise da administracao.",
                            ephemeral=True,
                        )

            await inter.response.send_modal(PartnershipModal(self))
            return

        if not self._can_manage(inter):
            await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para configurar parcerias.", ephemeral=True)
            return

        if action == "AutoTime":
            outer = self
            source_message = inter.message

            class AutoTimeModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Tempo da autoaprovacao",
                        custom_id=f"Parcerias_AutoTimeModal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(
                                label="Aprovar apos quantos minutos?",
                                custom_id="minutes",
                                placeholder="Ex.: 30",
                                value="30",
                                required=True,
                                max_length=5,
                            )
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    minutes = outer._auto_minutes(values.get("minutes"))
                    if not modal_inter.response.is_done():
                        await modal_inter.response.defer(ephemeral=True)
                    cfg_local = outer._get_config(guild_id)
                    cfg_local["auto_approve_minutes"] = minutes
                    outer._save_config(guild_id, cfg_local)
                    await outer._edit_message_safely(source_message, guild_id)
                    await modal_inter.followup.send(f"{emoji.correct} Autoaprovacao definida para `{minutes}` minuto(s).", ephemeral=True)

            await inter.response.send_modal(AutoTimeModal())
            return

        if action == "Customize":
            outer = self
            source_message = inter.message

            class CustomizeModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Personalizar Parcerias",
                        custom_id=f"Parcerias_CustomizeModal:{guild_id}",
                        components=[
                            disnake.ui.TextInput(label="Titulo do painel", custom_id="panel_title", required=False, max_length=80, placeholder=DEFAULT_PANEL_TITLE),
                            disnake.ui.TextInput(label="Descricao do painel", custom_id="panel_description", required=False, max_length=300, placeholder=DEFAULT_PANEL_DESCRIPTION),
                            disnake.ui.TextInput(label="Banner URL", custom_id="banner_url", required=False, max_length=500, placeholder="https://..."),
                            disnake.ui.TextInput(label="Botao", custom_id="button_label", required=False, max_length=80, placeholder=DEFAULT_BUTTON_LABEL),
                            disnake.ui.TextInput(label="Rodape/Powered by", custom_id="footer", required=False, max_length=120, placeholder=DEFAULT_FOOTER),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    if not modal_inter.response.is_done():
                        await modal_inter.response.defer(ephemeral=True)
                    cfg_local = outer._get_config(guild_id)
                    for key in ("panel_title", "panel_description", "banner_url", "button_label", "footer"):
                        value = (values.get(key) or "").strip()
                        if value:
                            cfg_local[key] = value
                    outer._save_config(guild_id, cfg_local)
                    await outer._edit_message_safely(source_message, guild_id)
                    await modal_inter.followup.send(f"{emoji.correct} Personalizacao das parcerias salva.", ephemeral=True)

            await inter.response.send_modal(CustomizeModal())
            return

        await self._defer_safely(inter, with_message=False)
        cfg = self._get_config(guild_id)

        if action == "Back":
            await self._edit_components(inter, self._build_admin_panel(guild_id))
            return

        if action == "Toggle":
            cfg["enabled"] = not as_bool(cfg.get("enabled"), False)
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_admin_panel(guild_id))
            await self._followup_safely(inter, f"{emoji.correct} Sistema de parcerias {'ativado' if cfg['enabled'] else 'desativado'}.", ephemeral=True)
            return

        if action == "Channels":
            await self._edit_components(inter, self._build_channels_panel(guild_id))
            return

        if action == "SendPanel":
            channel_id = cfg.get("panel_channel_id")
            channel = inter.guild.get_channel(int(channel_id)) if channel_id else inter.channel
            if not isinstance(channel, disnake.TextChannel):
                await self._followup_safely(inter, f"{emoji.wrong} Configure um canal valido para publicar o painel.", ephemeral=True)
                return
            try:
                sent = await self._send_components_to_channel(channel, self._build_public_panel(guild_id))
            except disnake.HTTPException as exc:
                await self._followup_safely(
                    inter,
                    f"{emoji.wrong} Nao consegui enviar o painel em {channel.mention}. Verifique minhas permissoes. Erro: `{getattr(exc, 'code', 'HTTP')}`",
                    ephemeral=True,
                )
                return
            cfg["panel_message_id"] = sent.id
            cfg["panel_channel_id"] = sent.channel.id
            self._save_config(guild_id, cfg)
            await self._followup_safely(inter, f"{emoji.correct} Painel de parceria enviado em {sent.channel.mention}.", ephemeral=True)
            return

        if action == "Preview":
            await self._respond_components_safely(inter, self._build_public_panel(guild_id), ephemeral=True)
            return

        if action == "AutoApprove":
            cfg["auto_approve_enabled"] = not as_bool(cfg.get("auto_approve_enabled"), False)
            cfg.setdefault("auto_approve_minutes", 30)
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_admin_panel(guild_id))
            await self._followup_safely(
                inter,
                f"{emoji.correct} Autoaprovacao {'ativada' if cfg['auto_approve_enabled'] else 'desativada'}.",
                ephemeral=True,
            )
            return

        if action == "ProofRequired":
            cfg["proof_required"] = not self._proof_required(cfg)
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_admin_panel(guild_id))
            await self._followup_safely(
                inter,
                f"{emoji.correct} Comprovante por foto agora esta `{'obrigatorio' if cfg['proof_required'] else 'opcional'}`.",
                ephemeral=True,
            )
            return

        if action == "SmartBlocker":
            cfg["smart_blocker_enabled"] = not self._smart_blocker_enabled(cfg)
            self._save_config(guild_id, cfg)
            await self._edit_components(inter, self._build_admin_panel(guild_id))
            await self._followup_safely(
                inter,
                f"{emoji.correct} Bloqueador inteligente {'ativado' if cfg['smart_blocker_enabled'] else 'desativado'}.",
                ephemeral=True,
            )
            return

        if action == "Pending":
            cases = self._cases(cfg)
            pending = [(case_id, case) for case_id, case in cases.items() if case.get("status") in {"pending", "waiting_proof"}]
            if not pending:
                await self._followup_safely(inter, f"{emoji.information} Nao ha solicitacoes pendentes.", ephemeral=True)
                return
            lines = [
                f"- `{case_id}` | <@{case.get('user_id')}> | `{case.get('status')}` | `{(case.get('moderation') or {}).get('type', 'parceria geral')}` | {_short_text(case.get('message'), 80)}"
                for case_id, case in pending[-10:]
            ]
            await self._followup_safely(inter, "**Parcerias pendentes:**\n" + "\n".join(lines), ephemeral=True)
            return

        if action in {"Approve", "Reject", "Block"}:
            if len(parts) < 3:
                await self._followup_safely(inter, f"{emoji.wrong} Solicitacao invalida.", ephemeral=True)
                return
            case_id = parts[2]
            cases = self._cases(cfg)
            case = cases.get(case_id)
            if not case:
                await self._followup_safely(inter, f"{emoji.wrong} Solicitacao nao encontrada.", ephemeral=True)
                return
            if case.get("status") != "pending":
                await self._followup_safely(inter, f"{emoji.information} Essa solicitacao ja foi analisada.", ephemeral=True)
                return
            if action == "Approve" and case.get("proof_required", self._proof_required(cfg)) and not case.get("proof"):
                await self._followup_safely(inter, f"{emoji.wrong} Esta parceria ainda nao tem foto de comprovante.", ephemeral=True)
                return

            if action == "Approve":
                published = await self._approve_case(inter.guild, cfg, case_id, case, approved_by=inter.user.id)
                if not published:
                    await self._followup_safely(inter, f"{emoji.wrong} Configure o canal de destino antes de aprovar.", ephemeral=True)
                    return
                feedback = f"{emoji.correct} Parceria aprovada e publicada em {published.channel.mention}."
            elif action == "Reject":
                case["status"] = "rejected"
                case["rejected_by"] = inter.user.id
                feedback = f"{emoji.correct} Parceria recusada."
            else:
                case["status"] = "blocked"
                case["blocked_by"] = inter.user.id
                feedback = f"{emoji.correct} Parceria bloqueada."

            case["reviewed_at"] = case.get("reviewed_at") or _now_iso()
            cases[case_id] = case
            self._save_config(guild_id, cfg)
            try:
                await inter.edit_original_message(components=self._build_review_components(guild_id, case_id, case), flags=self._flags())
            except disnake.HTTPException:
                try:
                    await inter.message.edit(components=self._build_review_components(guild_id, case_id, case), flags=self._flags())
                except disnake.HTTPException:
                    pass
            await self._followup_safely(inter, feedback, ephemeral=True)

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if not cid.startswith("Parcerias_Select"):
            return
        if not self._can_manage(inter):
            await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para configurar parcerias.", ephemeral=True)
            return
        await self._defer_safely(inter, with_message=False)

        parts = cid.split(":")
        action = parts[0].split("_", 1)[1]
        guild_id = int(parts[1]) if len(parts) > 1 else inter.guild.id
        channel_id = int(inter.values[0])

        cfg = self._get_config(guild_id)
        if action == "SelectPanelChannel":
            cfg["panel_channel_id"] = channel_id
            text = f"Canal do painel definido para <#{channel_id}>."
        elif action == "SelectReviewChannel":
            cfg["review_channel_id"] = channel_id
            text = f"Canal de solicitacoes definido para <#{channel_id}>."
        elif action == "SelectDestinationChannel":
            cfg["destination_channel_id"] = channel_id
            text = f"Canal de destino definido para <#{channel_id}>."
        else:
            return

        self._save_config(guild_id, cfg)
        await self._edit_components(inter, self._build_admin_panel(guild_id))
        await self._followup_safely(inter, f"{emoji.correct} {text}", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(Parcerias(bot))
