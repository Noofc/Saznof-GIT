from __future__ import annotations

import io
import textwrap
import secrets
from datetime import datetime, timezone
from pathlib import Path

import disnake
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from functions.database import database as db
from functions.emoji import emoji

DATA_PATH = "database/twitter_system.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "approval_enabled": False,
    "send_channel_id": "",
    "approval_channel_id": "",
    "posts_channel_id": "",
    "logs_channel_id": "",
    "staff_role_id": "",
    "title": "Sistema Twitter/X",
    "description": "Membros podem enviar tweets com texto e imagem opcional. A equipe pode aprovar antes da publicação.",
    "title_emoji": "textc",
    "button_label": "Enviar tweet",
    "button_emoji": "textc",
    "banner_url": "",
    "thumbnail_enabled": False,
    "posts": [],
    "pending": [],
    "published_count": 0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emoji(name: str, fallback: str = ""):
    return getattr(emoji, name, None) or getattr(emoji, fallback, None) or fallback


def _id(value) -> str:
    raw = str(value or "").strip().replace("<#", "").replace("<@&", "").replace(">", "")
    return raw if raw.isdigit() else ""


def _channel_id(value) -> str:
    return _id(value)


def resolve_emoji(value, bot=None, fallback=""):
    raw = str(value or "").strip()
    if not raw:
        return _emoji(fallback, fallback) if fallback else ""
    if raw.startswith("<"):
        return raw
    if raw.isdigit() and bot:
        for item in getattr(bot, "emojis", []) or []:
            if str(getattr(item, "id", "")) == raw:
                return str(item)
        return ""
    return getattr(emoji, raw, raw) if raw.isidentifier() else raw


def ensure_data() -> dict:
    data = db.obter(DATA_PATH)
    if not isinstance(data, dict):
        data = {}
    cfg = data.setdefault("config", {})
    changed = False
    for key, value in DEFAULT_CONFIG.items():
        if key not in cfg:
            cfg[key] = list(value) if isinstance(value, list) else value.copy() if isinstance(value, dict) else value
            changed = True
    if not isinstance(cfg.get("posts"), list):
        cfg["posts"] = []
        changed = True
    if not isinstance(cfg.get("pending"), list):
        cfg["pending"] = []
        changed = True
    if changed or not Path(DATA_PATH).exists():
        db.salvar(DATA_PATH, data)
    return data


def config() -> dict:
    return ensure_data()["config"]


def update_config(changes: dict) -> dict:
    data = ensure_data()
    data["config"].update(changes)
    db.salvar(DATA_PATH, data)
    return data["config"]


def add_pending(item: dict) -> dict:
    data = ensure_data()
    item = dict(item)
    item.setdefault("id", secrets.token_hex(5))
    item.setdefault("created_at", _now())
    data["config"].setdefault("pending", []).append(item)
    data["config"]["pending"] = data["config"]["pending"][-100:]
    db.salvar(DATA_PATH, data)
    return item


def pop_pending(tweet_id: str) -> dict | None:
    data = ensure_data()
    pending = data["config"].setdefault("pending", [])
    for index, item in enumerate(pending):
        if str(item.get("id")) == str(tweet_id):
            found = pending.pop(index)
            db.salvar(DATA_PATH, data)
            return found
    return None


def add_post(item: dict) -> dict:
    data = ensure_data()
    item = dict(item)
    item.setdefault("id", secrets.token_hex(5))
    item.setdefault("created_at", _now())
    data["config"].setdefault("posts", []).append(item)
    data["config"]["posts"] = data["config"]["posts"][-200:]
    data["config"]["published_count"] = int(data["config"].get("published_count") or 0) + 1
    db.salvar(DATA_PATH, data)
    return item


def _accent() -> dict:
    colors = db.get_document("custom_colors") or {}
    raw = colors.get("primary") if isinstance(colors, dict) else None
    if not raw:
        return {}
    try:
        return {"accent_colour": disnake.Colour(int(str(raw).replace("#", ""), 16))}
    except Exception:
        return {}


def _channel_label(value: str, empty: str = "Não configurado") -> str:
    return f"<#{value}>" if _id(value) else empty


def admin_components(bot) -> list:
    cfg = config()
    status = "Ativado" if cfg.get("enabled") else "Desativado"
    approval = "Ativada" if cfg.get("approval_enabled") else "Desativada (direto)"
    pending = len(cfg.get("pending") or [])
    info = (
        f"{_emoji('power', 'power')} **Status:** `{status}`\n"
        f"{_emoji('shield', 'shield')} **Aprovação:** `{approval}`\n"
        f"{_emoji('textc', 'textc')} **Canal de Envio:** {_channel_label(cfg.get('send_channel_id'))}\n"
        f"{_emoji('textc', 'textc')} **Canal de Aprovação:** {_channel_label(cfg.get('approval_channel_id'))}\n"
        f"{_emoji('textc', 'textc')} **Canal de Posts:** {_channel_label(cfg.get('posts_channel_id'))}\n"
        f"{_emoji('textc', 'textc')} **Canal de Logs:** {_channel_label(cfg.get('logs_channel_id'))}\n"
        f"{_emoji('members', 'members')} **Cargo Staff:** {f'<@&{cfg.get("staff_role_id")}>' if _id(cfg.get('staff_role_id')) else 'Não configurado'}\n"
        f"{_emoji('clock', 'clock')} **Pendentes:** `{pending}` | **Publicados:** `{int(cfg.get('published_count') or 0)}`"
    )
    preview = (
        f"**Título:** {cfg.get('title') or DEFAULT_CONFIG['title']}\n"
        f"**Descrição:** {(cfg.get('description') or DEFAULT_CONFIG['description'])[:700]}\n"
        f"**Thumbnail:** `{'Ativada' if cfg.get('thumbnail_enabled') else 'Desativada'}`"
    )
    return [
        disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {_emoji('textc', 'textc')} Sistema Twitter/X\n-# Painel > Sistemas > **Twitter**"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(info),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(preview),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Desativar" if cfg.get("enabled") else "Ativar", style=disnake.ButtonStyle.red if cfg.get("enabled") else disnake.ButtonStyle.green, emoji=_emoji('off' if cfg.get('enabled') else 'on', 'power'), custom_id="Twitter_Toggle"),
                disnake.ui.Button(label="Ativar Aprovação" if not cfg.get("approval_enabled") else "Desativar Aprovação", style=disnake.ButtonStyle.secondary, emoji=_emoji('shield', 'shield'), custom_id="Twitter_Approval"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Canal Envio", style=disnake.ButtonStyle.grey, emoji=_emoji('textc', 'textc'), custom_id="Twitter_SendChannel"),
                disnake.ui.Button(label="Canal Aprovação", style=disnake.ButtonStyle.grey, emoji=_emoji('textc', 'textc'), custom_id="Twitter_ApprovalChannel"),
                disnake.ui.Button(label="Canal Posts", style=disnake.ButtonStyle.grey, emoji=_emoji('textc', 'textc'), custom_id="Twitter_PostsChannel"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Cargo Staff", style=disnake.ButtonStyle.grey, emoji=_emoji('members', 'members'), custom_id="Twitter_StaffRole"),
                disnake.ui.Button(label="Canal Logs", style=disnake.ButtonStyle.grey, emoji=_emoji('textc', 'textc'), custom_id="Twitter_LogsChannel"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Personalizar Painel", style=disnake.ButtonStyle.grey, emoji=_emoji('edit', 'edit'), custom_id="Twitter_EditPanel"),
                disnake.ui.Button(label="Emoji do Botão", style=disnake.ButtonStyle.grey, emoji=resolve_emoji(cfg.get('button_emoji'), bot, 'textc'), custom_id="Twitter_EditButton"),
                disnake.ui.Button(label="Ativar Thumb" if not cfg.get('thumbnail_enabled') else "Desativar Thumb", style=disnake.ButtonStyle.secondary, emoji=_emoji('image', 'image'), custom_id="Twitter_Thumbnail"),
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Enviar Painel", style=disnake.ButtonStyle.green, emoji=_emoji('announcement', 'announcement'), custom_id="Twitter_PublishPanel"),
                disnake.ui.Button(label="Atualizar Painel", style=disnake.ButtonStyle.secondary, emoji=_emoji('reload', 'reload'), custom_id="Twitter_Refresh"),
            ),
            **_accent(),
        )
    ]


def public_components(bot) -> list:
    cfg = config()
    title = str(cfg.get("title") or DEFAULT_CONFIG["title"])
    description = str(cfg.get("description") or DEFAULT_CONFIG["description"])
    children = [disnake.ui.TextDisplay(f"# {resolve_emoji(cfg.get('title_emoji'), bot, 'textc')} {title}\n\n{description}")]
    banner = str(cfg.get("banner_url") or "").strip()
    if banner.startswith(("http://", "https://")):
        try:
            children.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(media=banner)))
        except Exception:
            pass
    children.extend([
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.ActionRow(disnake.ui.Button(label=str(cfg.get("button_label") or "Enviar tweet")[:80], style=disnake.ButtonStyle.grey, emoji=resolve_emoji(cfg.get("button_emoji"), bot, "textc"), custom_id="Twitter_Submit")),
    ])
    return [disnake.ui.Container(*children, **_accent())]


def _font(size: int, bold: bool = False):
    local_font = Path(__file__).resolve().parents[2] / "assets" / "fonts" / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    candidates = [
        str(local_font),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _avatar_image(tweet: dict, size: int = 86):
    avatar_url = str(tweet.get("avatar_url") or "")
    image = None
    if avatar_url.startswith(("http://", "https://")):
        try:
            response = requests.get(avatar_url, timeout=4)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGBA")
        except Exception:
            image = None
    if image is None:
        image = Image.new("RGBA", (size, size), (55, 65, 81, 255))
        draw = ImageDraw.Draw(image)
        initials = "".join(part[:1] for part in str(tweet.get("author_name") or "M").split())[:2].upper()
        draw.text((size // 2, size // 2), initials, fill="white", anchor="mm", font=_font(30, True))
    image = ImageOps.fit(image, (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    image.putalpha(mask)
    return image


def tweet_file(tweet: dict):
    """Gera o card Twitter no estilo aprovado: limpo, 16:9 e sem sombras."""
    width, height = 1100, 620
    background = Image.new("RGB", (width, height), (14, 15, 18))
    draw = ImageDraw.Draw(background)
    white = (242, 243, 245)
    muted = (145, 149, 158)
    border = (70, 73, 80)
    divider = (66, 69, 76)

    # Borda simples, sem brilho ou sombra.
    draw.rounded_rectangle((8, 8, width - 8, height - 8), radius=22, outline=border, width=2)

    avatar = _avatar_image(tweet, size=140)
    background.paste(avatar, (78, 78), avatar)
    author_name = str(tweet.get("author_name") or "Membro")[:40]
    author_id = str(tweet.get("author_id") or "")
    draw.text((270, 82), author_name, fill=white, font=_font(42, True))
    draw.text((270, 136), author_id, fill=muted, font=_font(29))

    # Símbolo oficial X/Twitter, sem sombra ou texto adicional.
    logo_path = Path(__file__).resolve().parents[2] / "assets" / "twitter_x_logo.png"
    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((92, 92), Image.Resampling.LANCZOS)
        background.paste(logo, (width - 150, 66), logo)
    except Exception:
        x_left, x_top, x_right, x_bottom = width - 128, 72, width - 62, 138
        draw.line((x_left, x_top, x_right, x_bottom), fill=white, width=6)
        draw.line((x_right - 4, x_top, x_left + 4, x_bottom), fill=white, width=6)

    text = str(tweet.get("text") or "")[:900]
    lines = textwrap.wrap(text, width=58) or [""]
    # Espaço maior entre o cabeçalho e o texto, como no modelo de referência.
    y = 285
    for line_text in lines[:4]:
        draw.text((64, y), line_text, fill=white, font=_font(43))
        y += 56

    draw.line((64, 470, width - 64, 470), fill=divider, width=2)
    created = str(tweet.get("created_at") or _now()).replace("T", " ")[:19]
    draw.text((64, 515), created, fill=muted, font=_font(25))
    footer = "Lyon Applications"
    footer_width = draw.textbbox((0, 0), footer, font=_font(25, True))[2]
    draw.text((width - 64 - footer_width, 515), footer, fill=muted, font=_font(25, True))

    output = io.BytesIO()
    background.save(output, format="PNG", optimize=True)
    output.seek(0)
    return disnake.File(output, filename="twitter-card.png")


def comments_components(bot, tweet: dict, can_delete: bool = False) -> list:
    comments = tweet.get("comments") if isinstance(tweet.get("comments"), list) else []
    total = len(comments)
    children = [
        disnake.ui.TextDisplay(f"## {_emoji('speech', 'speech')} Comentários do Tweet"),
        disnake.ui.TextDisplay(f"**{str(tweet.get('author_name') or 'Membro')[:80]}**\n{str(tweet.get('text') or '')[:500]}"),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.TextDisplay(f"{_emoji('members', 'members')} **{total} comentário(s)**"),
    ]
    if not comments:
        children.append(disnake.ui.TextDisplay("Ainda não há comentários neste tweet."))
    else:
        for index, item in enumerate(comments[-10:]):
            author = str(item.get("author_name") or item.get("author_id") or "Membro")[:60]
            text = str(item.get("text") or "")[:500]
            created = str(item.get("created_at") or "").replace("T", " ")[:19]
            children.append(disnake.ui.TextDisplay(f"**{author}**\n{text}\n-# {created}"))
            if can_delete:
                real_index = len(comments) - len(comments[-10:]) + index
                children.append(disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Excluir",
                        style=disnake.ButtonStyle.red,
                        emoji=_emoji('delete', 'delete'),
                        custom_id=f"Twitter_DeleteComment:{tweet.get('id')}:{real_index}",
                    )
                ))
    return [disnake.ui.Container(*children, **_accent())]


def tweet_card(bot, tweet: dict, *, moderation: bool = False) -> list:
    children = [disnake.ui.TextDisplay(f"## {_emoji('textc', 'textc')} Tweet")]
    try:
        children.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(media="attachment://twitter-card.png")))
    except Exception:
        author_id = str(tweet.get("author_id") or "")
        author = f"<@{author_id}>" if author_id.isdigit() else str(tweet.get("author_name") or "Membro")
        children.append(disnake.ui.TextDisplay(f"**{author}**\n{str(tweet.get('text') or '')[:1800]}\n\n-# Lyon Applications"))
    buttons = []
    if moderation:
        buttons = [
            disnake.ui.Button(label="Aprovar", style=disnake.ButtonStyle.green, emoji=_emoji('correct', 'correct'), custom_id=f"Twitter_Approve:{tweet.get('id')}"),
            disnake.ui.Button(label="Rejeitar", style=disnake.ButtonStyle.red, emoji=_emoji('wrong', 'wrong'), custom_id=f"Twitter_Reject:{tweet.get('id')}"),
        ]
    else:
        likes = len(tweet.get("likes") if isinstance(tweet.get("likes"), list) else [])
        comments = len(tweet.get("comments") if isinstance(tweet.get("comments"), list) else [])
        first_row = [
            disnake.ui.Button(label=(str(likes) if likes else "Curtir"), style=disnake.ButtonStyle.grey, emoji=_emoji('like', 'like'), custom_id=f"Twitter_Like:{tweet.get('id')}"),
            disnake.ui.Button(label="Repost", style=disnake.ButtonStyle.grey, emoji=_emoji('reload', 'reload'), custom_id=f"Twitter_Repost:{tweet.get('id')}"),
            disnake.ui.Button(label="Comentar", style=disnake.ButtonStyle.grey, emoji=_emoji('speech', 'speech'), custom_id=f"Twitter_Comment:{tweet.get('id')}"),
        ]
        second_row = [
            disnake.ui.Button(label=f"Comentários ({comments})", style=disnake.ButtonStyle.grey, emoji=_emoji('members', 'members'), custom_id=f"Twitter_Comments:{tweet.get('id')}"),
            disnake.ui.Button(label="Apagar", style=disnake.ButtonStyle.red, emoji=_emoji('delete', 'delete'), custom_id=f"Twitter_Delete:{tweet.get('id')}"),
        ]
        children.append(disnake.ui.ActionRow(*first_row))
        children.append(disnake.ui.ActionRow(*second_row))
        return [disnake.ui.Container(*children, **_accent())]
    children.append(disnake.ui.ActionRow(*buttons))
    return [disnake.ui.Container(*children, **_accent())]


class TwitterPanelModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        cfg = config()
        super().__init__(title="Personalizar painel Twitter", custom_id="Twitter_EditPanelModal", components=[
            disnake.ui.TextInput(label="Título", custom_id="title", value=str(cfg.get("title") or DEFAULT_CONFIG["title"])[:100], max_length=100),
            disnake.ui.TextInput(label="Descrição", custom_id="description", style=disnake.TextInputStyle.paragraph, value=str(cfg.get("description") or DEFAULT_CONFIG["description"])[:900], max_length=900),
            disnake.ui.TextInput(label="Emoji do título (ID ou nome)", custom_id="title_emoji", value=str(cfg.get("title_emoji") or "textc")[:40], required=False, max_length=40),
            disnake.ui.TextInput(label="Banner (URL opcional)", custom_id="banner_url", value=str(cfg.get("banner_url") or "")[:500], required=False, max_length=500),
        ])

    async def callback(self, inter):
        values = inter.text_values
        banner = str(values.get("banner_url") or "").strip()
        if banner and not banner.startswith(("http://", "https://")):
            return await inter.response.send_message(f"{_emoji('wrong', 'wrong')} O banner precisa ser uma URL válida.", ephemeral=True)
        update_config({"title": str(values.get("title") or DEFAULT_CONFIG["title"])[:100], "description": str(values.get("description") or DEFAULT_CONFIG["description"])[:900], "title_emoji": str(values.get("title_emoji") or "textc")[:40], "banner_url": banner})
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Painel Twitter atualizado. Use **Enviar Painel** para publicar.", ephemeral=True)


class TwitterButtonModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        cfg = config()
        super().__init__(title="Editar botão Twitter", custom_id="Twitter_EditButtonModal", components=[
            disnake.ui.TextInput(label="Nome do botão", custom_id="button_label", value=str(cfg.get("button_label") or "Enviar tweet")[:80], max_length=80),
            disnake.ui.TextInput(label="Emoji do botão (ID ou nome)", custom_id="button_emoji", value=str(cfg.get("button_emoji") or "textc")[:40], required=False, max_length=40),
        ])

    async def callback(self, inter):
        update_config({"button_label": str(inter.text_values.get("button_label") or "Enviar tweet")[:80], "button_emoji": str(inter.text_values.get("button_emoji") or "textc")[:40]})
        await inter.response.send_message(f"{_emoji('correct', 'correct')} Botão Twitter atualizado.", ephemeral=True)


class TweetModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(title="Enviar tweet", custom_id="Twitter_TweetModal", components=[
            disnake.ui.TextInput(label="Texto do tweet", custom_id="text", style=disnake.TextInputStyle.paragraph, max_length=1800, required=True),
            disnake.ui.TextInput(label="URL da imagem (opcional)", custom_id="image_url", max_length=500, required=False, placeholder="https://..."),
        ])

    async def callback(self, inter):
        text = str(inter.text_values.get("text") or "").strip()
        image_url = str(inter.text_values.get("image_url") or "").strip()
        if image_url and not image_url.startswith(("http://", "https://")):
            return await inter.response.send_message(f"{_emoji('wrong', 'wrong')} A imagem precisa ser uma URL válida.", ephemeral=True)
        await self.cog.submit_tweet(inter, text, image_url)


class CommentModal(disnake.ui.Modal):
    def __init__(self, cog, tweet_id, source_message=None):
        self.cog = cog
        self.tweet_id = tweet_id
        self.source_message = source_message
        super().__init__(title="Comentar tweet", custom_id=f"Twitter_CommentModal:{tweet_id}", components=[disnake.ui.TextInput(label="Comentário", custom_id="comment", style=disnake.TextInputStyle.paragraph, max_length=500)])

    async def callback(self, inter):
        await self.cog.add_comment(inter, self.tweet_id, str(inter.text_values.get("comment") or "").strip(), self.source_message)


def channel_select(custom_id: str, placeholder: str, channel_types):
    return [disnake.ui.ActionRow(disnake.ui.ChannelSelect(custom_id=custom_id, placeholder=placeholder, channel_types=channel_types, min_values=1, max_values=1))]


def role_select():
    return [disnake.ui.ActionRow(disnake.ui.RoleSelect(custom_id="Twitter_StaffRoleSelect", placeholder="Selecionar cargo staff", min_values=1, max_values=1))]
