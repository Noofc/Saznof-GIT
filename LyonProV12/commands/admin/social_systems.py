from __future__ import annotations

import os
import secrets
from datetime import datetime

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.system_logs import send_system_log


DATA_PATH = "database/social_systems.json"
INSTAGRAM_LOCK_DIR = os.path.join("database", "social_instagram_locks")


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


def _user(inter: disnake.Interaction):
    return getattr(inter, "user", None) or getattr(inter, "author", None)


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _clean_url(value: str | None) -> str:
    url = str(value or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return ""


def _channel_id(value: str | None) -> str:
    raw = str(value or "").strip()
    raw = raw.replace("<#", "").replace(">", "")
    return raw if raw.isdigit() else ""


SYSTEMS = {
    "engagement": {
        "label": "Engajamento",
        "panel_id": "Painel_Engajamento",
        "emoji": "reaction",
        "fallback": "speech",
        "default_title": "Sistema de Engajamento",
        "default_description": (
            "Clique no botão abaixo para registrar sua participação no engajamento."
        ),
        "default_button": "Registrar Engajamento",
        "public_button": "Participar",
    },
    "instagram": {
        "label": "Instagram",
        "panel_id": "Painel_Instagram",
        "emoji": "image",
        "fallback": "image",
        "default_title": "Instagram",
        "default_description": "Acesse o perfil ou publicação configurada e registre seu engajamento.",
        "default_button": "Abrir Instagram",
        "public_button": "Registrar Instagram",
    },
    "fivem": {
        "label": "FiveM",
        "panel_id": "Painel_FiveM",
        "emoji": "controller",
        "fallback": "controller",
        "default_title": "FiveM",
        "default_description": "Entre no servidor FiveM configurado e registre seu acesso.",
        "default_button": "Entrar no FiveM",
        "public_button": "Registrar FiveM",
    },
}

SYSTEMS["instagram"].update(
    {
        "default_title": "Instagram da Comunidade",
        "default_description": "Compartilhe fotos e videos com a comunidade. Use o botao para publicar uma midia com legenda no feed publico.",
        "public_button": "Enviar Foto/Video",
    }
)


class SocialLyonConfigModal(disnake.ui.Modal):
    def __init__(self, cog: "SocialLyonsPanel", system_key: str):
        self.cog = cog
        self.system_key = system_key
        cfg = cog.get_system(system_key)
        meta = SYSTEMS[system_key]

        components = [
            disnake.ui.TextInput(
                label="Título do painel",
                custom_id="title",
                style=disnake.TextInputStyle.short,
                value=str(cfg.get("title") or meta["default_title"])[:100],
                max_length=100,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Descrição",
                custom_id="description",
                style=disnake.TextInputStyle.paragraph,
                value=str(cfg.get("description") or meta["default_description"])[:900],
                max_length=900,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Link do botão",
                custom_id="link_url",
                style=disnake.TextInputStyle.short,
                value=str(cfg.get("link_url") or "")[:500],
                placeholder="https://...",
                max_length=500,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Texto do botão",
                custom_id="button_label",
                style=disnake.TextInputStyle.short,
                value=str(cfg.get("button_label") or meta["default_button"])[:80],
                max_length=80,
                required=False,
            ),
            disnake.ui.TextInput(
                label="Canal para publicar",
                custom_id="channel_id",
                style=disnake.TextInputStyle.short,
                value=str(cfg.get("channel_id") or "")[:32],
                placeholder="ID do canal ou deixe vazio para usar o canal atual",
                max_length=32,
                required=False,
            ),
        ]
        super().__init__(title=f"Configurar {meta['label']}", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        title = str(inter.text_values.get("title") or "").strip()
        description = str(inter.text_values.get("description") or "").strip()
        link_url = _clean_url(inter.text_values.get("link_url"))
        button_label = str(inter.text_values.get("button_label") or "").strip()
        channel_id = _channel_id(inter.text_values.get("channel_id"))

        meta = SYSTEMS[self.system_key]
        self.cog.update_system(
            self.system_key,
            {
                "title": title or meta["default_title"],
                "description": description or meta["default_description"],
                "link_url": link_url,
                "button_label": button_label or meta["default_button"],
                "channel_id": channel_id,
            },
        )

        await self.cog._safe_response_send(
            inter,
            f"{_emoji('correct', 'correct')} Configuração de **{meta['label']}** salva.",
            ephemeral=True,
        )

class SocialLyonsPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._instagram_processing_messages: set[str] = set()
        self.ensure_data()

    def ensure_data(self) -> dict:
        data = db.obter(DATA_PATH)
        if not isinstance(data, dict):
            data = {}
        systems = data.setdefault("systems", {})

        changed = False
        for removed_key in ("tellonym", "twitterx"):
            if removed_key in systems:
                systems.pop(removed_key, None)
                changed = True

        for key, meta in SYSTEMS.items():
            if key not in systems or not isinstance(systems.get(key), dict):
                systems[key] = {}
                changed = True

            cfg = systems[key]
            defaults = {
                "enabled": True,
                "title": meta["default_title"],
                "description": meta["default_description"],
                "link_url": "",
                "button_label": meta["default_button"],
                "channel_id": "",
                "clicks": 0,
                "users": {},
                "posts": [],
                "last_published_at": None,
                "last_clicked_at": None,
            }
            for field, value in defaults.items():
                if field not in cfg:
                    cfg[field] = value
                    changed = True

        if changed or not db.obter(DATA_PATH):
            db.salvar(DATA_PATH, data)
        return data

    def load(self) -> dict:
        return self.ensure_data()

    def save(self, data: dict) -> None:
        db.salvar(DATA_PATH, data)

    def get_system(self, system_key: str) -> dict:
        return self.load().get("systems", {}).get(system_key, {}).copy()

    def update_system(self, system_key: str, changes: dict) -> dict:
        data = self.load()
        cfg = data["systems"][system_key]
        cfg.update(changes)
        self.save(data)
        return cfg.copy()

    def _system_emoji(self, system_key: str):
        meta = SYSTEMS[system_key]
        return _emoji(meta["emoji"], meta["fallback"])

    def _container_kwargs(self) -> dict:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary") if isinstance(colors, dict) else None
        if not primary_color_hex:
            return {}
        try:
            return {"accent_colour": disnake.Colour(int(primary_color_hex.replace("#", ""), 16))}
        except Exception:
            return {}

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
            print(f"[SocialLyons] Interacao expirada/defer ignorado: {exc}")
            return False

    async def _safe_send_modal(self, inter: disnake.MessageInteraction, modal: disnake.ui.Modal) -> bool:
        if inter.response.is_done():
            return False
        try:
            await inter.response.send_modal(modal)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[SocialLyons] Falha ao abrir modal: {exc}")
            return False

    async def _safe_response_send(self, inter: disnake.Interaction, content: str | None = None, **kwargs) -> bool:
        try:
            if inter.response.is_done():
                await inter.followup.send(content, **kwargs)
            else:
                await inter.response.send_message(content, **kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[SocialLyons] Falha ao responder interacao: {exc}")
            return False

    async def _safe_response_edit(self, inter: disnake.Interaction, **kwargs) -> bool:
        try:
            if inter.response.is_done():
                await inter.edit_original_message(**kwargs)
            else:
                await inter.response.edit_message(**kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[SocialLyons] Falha ao editar interacao: {exc}")
            return False

    async def _safe_edit_original(self, inter: disnake.Interaction, **kwargs) -> bool:
        try:
            await inter.edit_original_message(**kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[SocialLyons] Falha ao editar mensagem original: {exc}")
            return False

    async def _safe_followup(self, inter: disnake.Interaction, content: str | None = None, **kwargs) -> bool:
        try:
            await inter.followup.send(content, **kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[SocialLyons] Falha ao enviar followup: {exc}")
            return False

    def _find_instagram_source_post(self, source_message_id: str):
        data = self.load()
        cfg = data.get("systems", {}).get("instagram", {})
        posts = cfg.get("posts") if isinstance(cfg.get("posts"), list) else []
        for post in posts:
            if str(post.get("source_message_id") or "") == str(source_message_id):
                return data, cfg, post
        return data, cfg, None

    def _claim_instagram_source_message(self, message: disnake.Message) -> bool:
        message_id = str(getattr(message, "id", "") or "")
        if not message_id:
            return False
        if message_id in self._instagram_processing_messages:
            return False
        if self._find_instagram_source_post(message_id)[2]:
            return False

        self._instagram_processing_messages.add(message_id)
        try:
            os.makedirs(INSTAGRAM_LOCK_DIR, exist_ok=True)
            lock_path = os.path.join(INSTAGRAM_LOCK_DIR, f"{message_id}.lock")
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except OSError as exc:
            print(f"[SocialLyons] Nao foi possivel criar lock do Instagram: {exc}")
            return True

        with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
            lock_file.write(f"{getattr(message.guild, 'id', '')}:{getattr(message.channel, 'id', '')}:{message_id}")
        return True

    def _admin_components(self, system_key: str) -> list:
        cfg = self.get_system(system_key)
        meta = SYSTEMS[system_key]
        status = "Ativo" if cfg.get("enabled") else "Desativado"
        link_status = "Configurado" if cfg.get("link_url") else "Não configurado"
        channel_status = f"<#{cfg.get('channel_id')}>" if cfg.get("channel_id") else "Canal atual"
        users = cfg.get("users") if isinstance(cfg.get("users"), dict) else {}
        posts = cfg.get("posts") if isinstance(cfg.get("posts"), list) else []
        instagram_posts_line = f"{_emoji('image', 'image')} **Postagens:** `{len(posts)}`\n" if system_key == "instagram" else ""

        info = (
            f"{_emoji('power', 'power')} **Status:** `{status}`\n"
            f"{_emoji('link', 'link')} **Link:** `{link_status}`\n"
            f"{_emoji('textc', '#')} **Publicação:** {channel_status}\n"
            f"{_emoji('chart', 'chart')} **Registros:** `{int(cfg.get('clicks') or 0)}` "
            f"| **Usuários:** `{len(users)}`\n"
            f"{_emoji('clock', '🕒')} **Última publicação:** `{cfg.get('last_published_at') or 'Nunca'}`"
        )

        preview = (
            f"**Título:** {cfg.get('title') or meta['default_title']}\n"
            f"**Descrição:** {(cfg.get('description') or meta['default_description'])[:450]}"
        )

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {self._system_emoji(system_key)} {meta['label']}\n"
                    f"-# Painel > Sistemas > **{meta['label']}**"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(info),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(preview),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Editar",
                        style=disnake.ButtonStyle.grey,
                        emoji=_emoji("edit", "edit"),
                        custom_id=f"Social_Edit_{system_key}",
                    ),
                    disnake.ui.Button(
                        label="Publicar",
                        style=disnake.ButtonStyle.green,
                        emoji=_emoji("announcement", "announcement"),
                        custom_id=f"Social_Publish_{system_key}",
                    ),
                    disnake.ui.Button(
                        label="Resetar",
                        style=disnake.ButtonStyle.red,
                        emoji=_emoji("reload", "reload"),
                        custom_id=f"Social_Reset_{system_key}",
                    ),
                    disnake.ui.Button(
                        label="Desativar" if cfg.get("enabled") else "Ativar",
                        style=disnake.ButtonStyle.red if cfg.get("enabled") else disnake.ButtonStyle.green,
                        emoji=_emoji("off", "off") if cfg.get("enabled") else _emoji("on", "on"),
                        custom_id=f"Social_Toggle_{system_key}",
                    ),
                ),
                **self._container_kwargs(),
            ),
        ]

    def _public_components(self, system_key: str) -> list:
        cfg = self.get_system(system_key)
        meta = SYSTEMS[system_key]
        title = cfg.get("title") or meta["default_title"]
        description = cfg.get("description") or meta["default_description"]
        clicks = int(cfg.get("clicks") or 0)

        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {self._system_emoji(system_key)} {title}\n\n"
                    f"{description}\n\n"
                    f"-# Registros feitos: `{clicks}`"
                ),
                **self._container_kwargs(),
            )
        ]

        buttons = []
        link_url = _clean_url(cfg.get("link_url"))
        if link_url:
            buttons.append(
                disnake.ui.Button(
                    label=str(cfg.get("button_label") or meta["default_button"])[:80],
                    style=disnake.ButtonStyle.url,
                    emoji=self._system_emoji(system_key),
                    url=link_url,
                )
            )

        buttons.append(
            disnake.ui.Button(
                label=meta["public_button"],
                style=disnake.ButtonStyle.green,
                emoji=_emoji("correct", "correct"),
                custom_id=f"Social_Public_{system_key}",
            )
        )
        components.append(disnake.ui.ActionRow(*buttons[:5]))
        return components

    def _instagram_post_components(self, post: dict, *, with_media: bool = True) -> list:
        media_url = _clean_url(post.get("media_url"))
        caption = str(post.get("caption") or "Sem legenda.")[:1200]
        author_id = str(post.get("author_id") or "")
        author_text = f"<@{author_id}>" if author_id.isdigit() else str(post.get("author_name") or "Usuario")

        children = [
            disnake.ui.TextDisplay(
                f"## {_emoji('image', 'image')} Nova publicacao\n"
                f"**Autor:** {author_text}\n"
                f"**Data:** `{post.get('created_at') or _now()}`\n\n"
                f"{caption}"
            )
        ]
        if with_media and media_url:
            try:
                children.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(media=media_url)))
            except Exception:
                pass
        if media_url:
            children.append(
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Abrir midia", style=disnake.ButtonStyle.url, emoji=self._system_emoji("instagram"), url=media_url)
                )
            )
        return [disnake.ui.Container(*children, **self._container_kwargs())]

    def _resolve_channel(self, inter: disnake.Interaction, cfg: dict):
        channel_id = _channel_id(cfg.get("channel_id"))
        channel = None
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None and getattr(inter, "guild", None):
                channel = inter.guild.get_channel(int(channel_id))
        return channel or getattr(inter, "channel", None)

    def _record_instagram_post(self, user, caption: str, media_url: str, source_message_id: str = "") -> dict:
        data = self.load()
        cfg = data["systems"]["instagram"]
        posts = cfg.setdefault("posts", [])
        post = {
            "id": secrets.token_hex(4),
            "author_id": str(getattr(user, "id", "")),
            "author_name": str(getattr(user, "name", "Usuario")),
            "caption": str(caption or "Sem legenda.").strip()[:1200],
            "media_url": media_url,
            "source_message_id": str(source_message_id or ""),
            "created_at": _now(),
        }
        posts.append(post)
        cfg["posts"] = posts[-200:]
        cfg["clicks"] = int(cfg.get("clicks") or 0) + 1
        cfg["last_clicked_at"] = _now()
        self.save(data)
        return post

    async def _send_instagram_post(self, channel, post: dict):
        try:
            return await channel.send(components=self._instagram_post_components(post), flags=disnake.MessageFlags(is_components_v2=True))
        except Exception:
            return await channel.send(components=self._instagram_post_components(post, with_media=False), flags=disnake.MessageFlags(is_components_v2=True))

    async def _open_instagram_post_modal(self, inter: disnake.MessageInteraction):
        cfg = self.get_system("instagram")
        if not cfg.get("enabled"):
            await self._safe_response_send(inter, f"{_emoji('warn', 'warn')} O Instagram esta desativado no momento.", ephemeral=True)
            return

        cog = self

        class InstagramPostModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Publicar no Instagram",
                    custom_id="Social_InstagramPost_Modal",
                    components=[
                        disnake.ui.TextInput(label="URL da foto ou video", custom_id="media_url", max_length=500, required=True, placeholder="https://..."),
                        disnake.ui.TextInput(label="Legenda", custom_id="caption", style=disnake.TextInputStyle.paragraph, max_length=1200, required=True),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                media_url = _clean_url(modal_inter.text_values.get("media_url"))
                caption = str(modal_inter.text_values.get("caption") or "").strip()
                if not media_url:
                    await cog._safe_response_send(modal_inter, f"{_emoji('wrong', 'wrong')} Envie uma URL valida de foto ou video.", ephemeral=True)
                    return

                if not await cog._safe_defer(modal_inter, ephemeral=True):
                    return
                current_cfg = cog.get_system("instagram")
                channel = cog._resolve_channel(modal_inter, current_cfg)
                if channel is None:
                    await cog._safe_followup(modal_inter, f"{_emoji('wrong', 'wrong')} Canal do feed nao encontrado.", ephemeral=True)
                    return

                post = cog._record_instagram_post(modal_inter.user, caption, media_url)
                await cog._send_instagram_post(channel, post)
                await send_system_log(
                    cog.bot,
                    modal_inter.guild,
                    title="Publicacao no Instagram",
                    system="Instagram",
                    description=f"{modal_inter.user.mention} publicou uma midia em {channel.mention}.",
                    actor=modal_inter.user,
                    config=current_cfg,
                )
                await cog._safe_followup(modal_inter, f"{_emoji('correct', 'correct')} Publicacao enviada em {channel.mention}.", ephemeral=True)

        await self._safe_send_modal(inter, InstagramPostModal())

    def _instagram_post_components(self, post: dict, *, with_media: bool = True) -> list:
        media_url = _clean_url(post.get("media_url"))
        caption = str(post.get("caption") or "").strip()
        author_id = str(post.get("author_id") or "")
        author_text = f"<@{author_id}>" if author_id.isdigit() else str(post.get("author_name") or "Usuario")
        display_text = caption if caption and caption != "Sem legenda." else author_text
        likes = post.get("likes") if isinstance(post.get("likes"), list) else []
        dislikes = post.get("dislikes") if isinstance(post.get("dislikes"), list) else []
        comments = post.get("comments") if isinstance(post.get("comments"), list) else []
        post_id = str(post.get("id") or "")

        children = [
            disnake.ui.TextDisplay(f"- {display_text[:1200]}"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        ]
        if with_media and media_url:
            try:
                children.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(media=media_url)))
            except Exception:
                pass

        buttons = [
            disnake.ui.Button(label=str(len(likes)), style=disnake.ButtonStyle.grey, emoji=_emoji("like", "like"), custom_id=f"Social_InstaReact:{post_id}:like"),
            disnake.ui.Button(label=str(len(dislikes)), style=disnake.ButtonStyle.grey, emoji=_emoji("deslike", "deslike"), custom_id=f"Social_InstaReact:{post_id}:dislike"),
        ]
        if media_url:
            buttons.append(disnake.ui.Button(label="", style=disnake.ButtonStyle.url, emoji=self._system_emoji("instagram"), url=media_url))
        buttons.extend(
            [
                disnake.ui.Button(label=str(len(comments)), style=disnake.ButtonStyle.grey, emoji=_emoji("double_speech", "double_speech"), custom_id=f"Social_InstaComment:{post_id}"),
                disnake.ui.Button(label="", style=disnake.ButtonStyle.danger, emoji=_emoji("delete", "delete"), custom_id=f"Social_InstaDelete:{post_id}"),
            ]
        )
        children.extend(
            [
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(*buttons[:5]),
            ]
        )
        return [disnake.ui.Container(*children, **self._container_kwargs())]

    def _record_instagram_post(self, user, caption: str, media_url: str, source_message_id: str = "") -> dict:
        data = self.load()
        cfg = data["systems"]["instagram"]
        posts = cfg.setdefault("posts", [])
        post = {
            "id": secrets.token_hex(4),
            "author_id": str(getattr(user, "id", "")),
            "author_name": str(getattr(user, "name", "Usuario")),
            "caption": str(caption or "Sem legenda.").strip()[:1200],
            "media_url": media_url,
            "source_message_id": str(source_message_id or ""),
            "likes": [],
            "dislikes": [],
            "comments": [],
            "message_id": "",
            "channel_id": "",
            "created_at": _now(),
        }
        posts.append(post)
        cfg["posts"] = posts[-200:]
        cfg["clicks"] = int(cfg.get("clicks") or 0) + 1
        cfg["last_clicked_at"] = _now()
        self.save(data)
        return post

    def _find_instagram_post(self, post_id: str):
        data = self.load()
        cfg = data.get("systems", {}).get("instagram", {})
        posts = cfg.get("posts") if isinstance(cfg.get("posts"), list) else []
        for post in posts:
            if str(post.get("id")) == str(post_id):
                post.setdefault("likes", [])
                post.setdefault("dislikes", [])
                post.setdefault("comments", [])
                return data, cfg, post
        return data, cfg, None

    async def _send_instagram_post(self, channel, post: dict):
        try:
            sent = await channel.send(components=self._instagram_post_components(post), flags=disnake.MessageFlags(is_components_v2=True))
        except Exception:
            sent = await channel.send(components=self._instagram_post_components(post, with_media=False), flags=disnake.MessageFlags(is_components_v2=True))
        data, _cfg, stored_post = self._find_instagram_post(post.get("id"))
        if stored_post:
            stored_post["message_id"] = str(sent.id)
            stored_post["channel_id"] = str(sent.channel.id)
            self.save(data)
        return sent

    async def _open_instagram_comment_modal(self, inter: disnake.MessageInteraction, post_id: str):
        data, _cfg, post = self._find_instagram_post(post_id)
        if not post:
            await self._safe_response_send(inter, f"{_emoji('wrong', 'wrong')} Publicacao nao encontrada.", ephemeral=True)
            return
        cog = self
        source_message = inter.message

        class InstagramCommentModal(disnake.ui.Modal):
            def __init__(self):
                super().__init__(
                    title="Comentar publicacao",
                    custom_id=f"Social_InstagramComment_Modal:{post_id}",
                    components=[
                        disnake.ui.TextInput(label="Comentario", custom_id="comment", style=disnake.TextInputStyle.paragraph, max_length=500, required=True),
                    ],
                )

            async def callback(self, modal_inter: disnake.ModalInteraction):
                current_data, _current_cfg, current_post = cog._find_instagram_post(post_id)
                if not current_post:
                    await cog._safe_response_send(modal_inter, f"{_emoji('wrong', 'wrong')} Publicacao nao encontrada.", ephemeral=True)
                    return
                current_post.setdefault("comments", []).append(
                    {
                        "author_id": str(modal_inter.user.id),
                        "text": str(modal_inter.text_values.get("comment") or "").strip()[:500],
                        "created_at": _now(),
                    }
                )
                cog.save(current_data)
                try:
                    await source_message.edit(components=cog._instagram_post_components(current_post), flags=disnake.MessageFlags(is_components_v2=True))
                except Exception:
                    pass
                await cog._safe_response_send(modal_inter, f"{_emoji('correct', 'correct')} Comentario enviado.", ephemeral=True)

        await self._safe_send_modal(inter, InstagramCommentModal())

    async def _refresh_admin(self, inter: disnake.MessageInteraction, system_key: str):
        if not await self._safe_defer(inter, with_message=False):
            return
        await self._safe_edit_original(
            inter,
            content=None,
            embed=None,
            components=self._admin_components(system_key),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    def display_engagement_panel(self, inter: disnake.MessageInteraction):
        return self._admin_components("engagement")

    def display_instagram_panel(self, inter: disnake.MessageInteraction):
        return self._admin_components("instagram")

    def display_fivem_panel(self, inter: disnake.MessageInteraction):
        return self._admin_components("fivem")

    async def _publish(self, inter: disnake.MessageInteraction, system_key: str):
        if not await self._safe_defer(inter, ephemeral=True):
            return
        cfg = self.get_system(system_key)
        meta = SYSTEMS[system_key]
        if not cfg.get("enabled"):
            await self._safe_followup(inter, f"{_emoji('warn', 'warn')} O sistema **{meta['label']}** está desativado.", ephemeral=True)
            return

        channel = None
        channel_id = _channel_id(cfg.get("channel_id"))
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None and getattr(inter, "guild", None):
                channel = inter.guild.get_channel(int(channel_id))
        channel = channel or getattr(inter, "channel", None)

        if channel is None:
            await self._safe_followup(
                inter,
                f"{_emoji('wrong', 'wrong')} Não foi possível encontrar o canal para publicar.",
                ephemeral=True,
            )
            return

        await channel.send(
            components=self._public_components(system_key),
            flags=disnake.MessageFlags(is_components_v2=True),
        )
        self.update_system(system_key, {"last_published_at": _now()})
        await send_system_log(
            self.bot,
            inter.guild,
            title=f"Painel de {meta['label']} publicado",
            system=meta["label"],
            description=f"Painel publicado em {channel.mention}.",
            actor=inter.user,
            config=cfg,
        )
        await self._safe_followup(
            inter,
            f"{_emoji('correct', 'correct')} Painel de **{meta['label']}** publicado em {channel.mention}.",
            ephemeral=True,
        )

    async def _register_click(self, inter: disnake.MessageInteraction, system_key: str):
        if not await self._safe_defer(inter, ephemeral=True):
            return
        cfg = self.get_system(system_key)
        meta = SYSTEMS[system_key]
        if not cfg.get("enabled"):
            await self._safe_followup(inter, f"{_emoji('warn', 'warn')} Este sistema está desativado no momento.", ephemeral=True)
            return

        data = self.load()
        current = data["systems"][system_key]
        user = _user(inter)
        user_id = str(getattr(user, "id", "0"))
        users = current.setdefault("users", {})
        users[user_id] = int(users.get(user_id, 0)) + 1
        current["clicks"] = int(current.get("clicks") or 0) + 1
        current["last_clicked_at"] = _now()
        self.save(data)
        log_after_response = {
            "title": f"Registro de {meta['label']}",
            "system": meta["label"],
            "description": f"{user.mention if user else 'Usuario'} registrou uma acao no painel.",
            "actor": user,
            "config": current,
        }
        await self._safe_followup(
            inter,
            f"{_emoji('correct', 'correct')} Registro de **{meta['label']}** confirmado.",
            ephemeral=True,
        )
        await send_system_log(self.bot, inter.guild, **log_after_response)

    @commands.Cog.listener("on_button_click")
    async def on_social_button(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")

        if custom_id.startswith("Social_Edit_"):
            system_key = custom_id.replace("Social_Edit_", "")
            if system_key in SYSTEMS:
                await self._safe_send_modal(inter, SocialLyonConfigModal(self, system_key))
            return

        if custom_id.startswith("Social_Publish_"):
            system_key = custom_id.replace("Social_Publish_", "")
            if system_key in SYSTEMS:
                await self._publish(inter, system_key)
            return

        if custom_id.startswith("Social_Toggle_"):
            system_key = custom_id.replace("Social_Toggle_", "")
            if system_key in SYSTEMS:
                if not await self._safe_defer(inter, with_message=False):
                    return
                cfg = self.get_system(system_key)
                self.update_system(system_key, {"enabled": not bool(cfg.get("enabled"))})
                await self._refresh_admin(inter, system_key)
            return

        if custom_id.startswith("Social_Reset_"):
            system_key = custom_id.replace("Social_Reset_", "")
            if system_key in SYSTEMS:
                if not await self._safe_defer(inter, with_message=False):
                    return
                changes = {"clicks": 0, "users": {}, "last_clicked_at": None}
                if system_key == "instagram":
                    changes["posts"] = []
                self.update_system(system_key, changes)
                await self._refresh_admin(inter, system_key)
            return

        if custom_id.startswith("Social_InstaReact:"):
            if not await self._safe_defer(inter, with_message=False):
                return
            _prefix, post_id, reaction = custom_id.split(":", 2)
            data, _cfg, post = self._find_instagram_post(post_id)
            if not post:
                await self._safe_followup(inter, f"{_emoji('wrong', 'wrong')} Publicacao nao encontrada.", ephemeral=True)
                return
            user_id = str(inter.user.id)
            likes = post.setdefault("likes", [])
            dislikes = post.setdefault("dislikes", [])
            post["likes"] = [uid for uid in likes if str(uid) != user_id]
            post["dislikes"] = [uid for uid in dislikes if str(uid) != user_id]
            if reaction == "like":
                post["likes"].append(user_id)
            elif reaction == "dislike":
                post["dislikes"].append(user_id)
            self.save(data)
            await self._safe_response_edit(inter, components=self._instagram_post_components(post), flags=disnake.MessageFlags(is_components_v2=True))
            return

        if custom_id.startswith("Social_InstaComment:"):
            post_id = custom_id.split(":", 1)[1]
            await self._open_instagram_comment_modal(inter, post_id)
            return

        if custom_id.startswith("Social_InstaDelete:"):
            if not await self._safe_defer(inter, ephemeral=True):
                return
            post_id = custom_id.split(":", 1)[1]
            data, cfg, post = self._find_instagram_post(post_id)
            if not post:
                await self._safe_followup(inter, f"{_emoji('wrong', 'wrong')} Publicacao nao encontrada.", ephemeral=True)
                return
            is_author = str(post.get("author_id")) == str(inter.user.id)
            perms = getattr(inter.user, "guild_permissions", None)
            can_manage = bool(perms and (perms.manage_messages or perms.administrator))
            if not (is_author or can_manage):
                await self._safe_followup(inter, f"{_emoji('wrong', 'wrong')} Apenas o autor ou a equipe pode apagar essa publicacao.", ephemeral=True)
                return
            cfg["posts"] = [item for item in cfg.get("posts", []) if str(item.get("id")) != str(post_id)]
            self.save(data)
            try:
                await inter.message.delete()
            except Exception:
                pass
            await self._safe_followup(inter, f"{_emoji('correct', 'correct')} Publicacao removida.", ephemeral=True)
            await send_system_log(
                self.bot,
                inter.guild,
                title="Publicacao removida",
                system="Instagram",
                description=f"Publicacao `{post_id}` removida do feed.",
                actor=inter.user,
                config=cfg,
            )
            return

        if custom_id == "Social_Public_instagram":
            await self._open_instagram_post_modal(inter)
            return

        if custom_id.startswith("Social_Public_"):
            system_key = custom_id.replace("Social_Public_", "")
            if system_key in SYSTEMS:
                await self._register_click(inter, system_key)

    @commands.Cog.listener("on_message")
    async def on_instagram_feed_message(self, message: disnake.Message):
        if not getattr(message, "guild", None) or getattr(message.author, "bot", False):
            return

        cfg = self.get_system("instagram")
        channel_id = _channel_id(cfg.get("channel_id"))
        if not cfg.get("enabled") or not channel_id or str(message.channel.id) != channel_id:
            return

        attachments = list(getattr(message, "attachments", []) or [])
        if not attachments:
            return

        attachment = attachments[0]
        content_type = str(getattr(attachment, "content_type", "") or "").lower()
        if content_type and not (content_type.startswith("image/") or content_type.startswith("video/")):
            return

        media_url = _clean_url(getattr(attachment, "url", ""))
        if not media_url:
            return

        source_message_id = str(message.id)
        if not self._claim_instagram_source_message(message):
            return

        caption = (message.content or "").strip() or "Sem legenda."
        post = self._record_instagram_post(message.author, caption, media_url, source_message_id=source_message_id)
        await self._send_instagram_post(message.channel, post)
        try:
            await message.delete()
        except Exception:
            pass
        await send_system_log(
            self.bot,
            message.guild,
            title="Publicacao no Instagram",
            system="Instagram",
            description=f"{message.author.mention} publicou uma midia em {message.channel.mention}.",
            actor=message.author,
            config=cfg,
        )


def setup(bot: commands.Bot):
    bot.add_cog(SocialLyonsPanel(bot))
