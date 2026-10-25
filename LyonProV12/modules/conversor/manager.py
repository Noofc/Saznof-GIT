from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import time

try:
    from imageio_ffmpeg import get_ffmpeg_exe
except ImportError:
    get_ffmpeg_exe = None
from datetime import datetime, timezone
from pathlib import Path

import disnake
from PIL import Image, ImageOps

from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import load_guild_channels, save_guild_channels
from functions import auto_setup
from functions.system_logs import send_system_log

DATA_PATH = "database/conversor_system.json"
DEFAULT_TITLE = "Conversor de arquivos"
DEFAULT_DESCRIPTION = "Converta vídeos em GIF, compacte GIFs e extraia áudio de vídeos."
STATUS_LABELS = {"convert": "Conversor", "compress": "Compressor", "extract": "Extrator", "bw": "Preto e branco"}
OPERATION_INFO = {
    "convert": {"title": "Conversor", "description": "Transforme seu vídeo em um GIF animado.", "emoji": "reload", "formats": ".mp4, .wmv, .flv, .mov, .mkv", "size": "25 MB"},
    "compress": {"title": "Compressor", "description": "Diminua o tamanho e otimize o seu GIF.", "emoji": "cardbox", "formats": ".gif", "size": "25 MB"},
    "extract": {"title": "Extrator", "description": "Extraia o áudio de um vídeo em formato MP3.", "emoji": "download", "formats": ".mp4, .wmv, .flv, .mov, .mkv", "size": "50 MB"},
    "bw": {"title": "Preto e branco", "description": "Converta uma imagem para tons de preto e branco.", "emoji": "palette", "formats": ".png, .jpg, .jpeg, .webp", "size": "10 MB"},
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_emoji(value, bot=None, fallback=""):
    raw = str(value or "").strip()
    if not raw:
        return fallback
    if raw.startswith("<") and raw.endswith(">"):
        return raw
    if raw.isdigit() and bot:
        for item in getattr(bot, "emojis", []) or []:
            if int(getattr(item, "id", 0) or 0) == int(raw):
                return str(item)
        return fallback
    if raw.isidentifier():
        resolved = internal_emoji(raw, "")
        return resolved or fallback
    return raw


def internal_emoji(name, fallback=""):
    for candidate in (name, fallback):
        if not candidate:
            continue
        value = getattr(emoji, str(candidate), None)
        if value:
            return value
    if fallback and (str(fallback).startswith("<") or not str(fallback).isidentifier()):
        return str(fallback)
    return ""


def primary_colour():
    colors = db.get_document("custom_colors") or {}
    raw = colors.get("primary") if isinstance(colors, dict) else None
    try:
        return disnake.Colour(int(str(raw).replace("#", ""), 16))
    except Exception:
        return disnake.Colour.blurple()


def ensure_data():
    data = db.obter(DATA_PATH)
    if not isinstance(data, dict):
        data = {}
    cfg = data.setdefault("config", {})
    defaults = {"enabled": True, "title": DEFAULT_TITLE, "description": DEFAULT_DESCRIPTION, "title_emoji": "textc", "log_channel_id": "", "channel_id": "", "category_id": "", "private_channel_ids": {}, "private_channel_meta": {}, "close_after_seconds": 1800, "options": {}}
    for key, value in defaults.items():
        cfg.setdefault(key, value.copy() if isinstance(value, dict) else value)
    for action, info in OPERATION_INFO.items():
        cfg["options"].setdefault(action, {})
        for field in ("title", "description", "emoji"):
            cfg["options"][action].setdefault(field, info[field])
    data.setdefault("logs", [])
    db.salvar(DATA_PATH, data)
    return data


def option_info(action):
    data = ensure_data()
    info = dict(OPERATION_INFO.get(action, OPERATION_INFO["convert"]))
    info.update(data["config"].get("options", {}).get(action, {}))
    return info


def set_option(action, changes):
    data = ensure_data()
    data["config"].setdefault("options", {}).setdefault(action, {}).update(changes)
    save(data)
    return option_info(action)


async def ensure_private_channel(bot, guild, user):
    data = ensure_data()
    cfg = data["config"]
    stored = cfg.setdefault("private_channel_ids", {})
    meta = cfg.setdefault("private_channel_meta", {})
    existing_id = stored.get(str(user.id))
    existing = guild.get_channel(int(existing_id)) if str(existing_id or "").isdigit() else None
    if existing:
        meta.setdefault(str(existing.id), {"user_id": str(user.id), "last_activity": time.time(), "completed_at": None})
        save(data)
        return existing
    category = guild.get_channel(int(cfg["category_id"])) if str(cfg.get("category_id") or "").isdigit() else None
    if not isinstance(category, disnake.CategoryChannel):
        category = next((item for item in guild.categories if item.name.lower() == "╺╸ conversor"), None)
    if category is None:
        category = await guild.create_category("╺╸ Conversor", reason="Criando categoria privada do Conversor")
    overwrites = {guild.default_role: disnake.PermissionOverwrite(view_channel=False)}
    member = guild.get_member(user.id)
    if member:
        overwrites[member] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True)
    if guild.me:
        overwrites[guild.me] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
    channel = await guild.create_text_channel(f"conversor-{user.id}", category=category, overwrites=overwrites, reason="Criando canal privado do Conversor")
    stored[str(user.id)] = str(channel.id)
    meta[str(channel.id)] = {"user_id": str(user.id), "last_activity": time.time(), "completed_at": None}
    save(data)
    return channel


def mark_channel_activity(channel_id, completed=False):
    data = ensure_data()
    item = data["config"].setdefault("private_channel_meta", {}).setdefault(str(channel_id), {"last_activity": time.time(), "completed_at": None})
    item["last_activity"] = time.time()
    item["completed_at"] = time.time() if completed else None
    save(data)
    return item


def remove_private_channel(channel_id):
    data = ensure_data()
    cfg = data["config"]
    channel_id = str(channel_id)
    cfg.setdefault("private_channel_meta", {}).pop(channel_id, None)
    for user_id, saved_id in list(cfg.setdefault("private_channel_ids", {}).items()):
        if str(saved_id) == channel_id:
            cfg["private_channel_ids"].pop(user_id, None)
    save(data)


def channels_due_for_close():
    data = ensure_data()
    timeout = int(data["config"].get("close_after_seconds") or 0)
    if timeout <= 0:
        return []
    now = time.time()
    due = []
    for channel_id, item in data["config"].setdefault("private_channel_meta", {}).items():
        reference = item.get("completed_at") or item.get("last_activity") or now
        if now - float(reference) >= timeout:
            due.append(str(channel_id))
    return due


def save(data):
    db.salvar(DATA_PATH, data)


def format_duration(seconds):
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}min")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def set_config(changes):
    data = ensure_data()
    data["config"].update(changes)
    save(data)
    return data


def _image_result(image: Image.Image, fmt: str, filename: str):
    output = io.BytesIO()
    if fmt.upper() in {"JPG", "JPEG"} and image.mode in {"RGBA", "LA", "P"}:
        image = image.convert("RGB")
    image.save(output, format=fmt.upper(), optimize=True)
    output.seek(0)
    return output, filename


def _ffmpeg_executable():
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    if get_ffmpeg_exe is not None:
        try:
            return get_ffmpeg_exe()
        except Exception:
            pass
    raise ValueError("FFmpeg não está instalado. Instale as dependências do requirements.txt e reinicie o bot.")


def _ffmpeg_result(action, filename, content):
    stem = Path(filename or "arquivo").stem
    ffmpeg = _ffmpeg_executable()
    with tempfile.TemporaryDirectory(prefix="conversor-") as folder:
        source = Path(folder) / Path(filename or "entrada").name
        source.write_bytes(content)
        if action == "convert":
            output = Path(folder) / f"{stem}.gif"
            command = [ffmpeg, "-y", "-i", str(source), "-vf", "fps=12,scale=480:-1:flags=lanczos", "-loop", "0", str(output)]
        elif action == "compress":
            output = Path(folder) / f"{stem}-compactado.gif"
            command = [ffmpeg, "-y", "-i", str(source), "-vf", "fps=10,scale=480:-1:flags=lanczos", "-loop", "0", str(output)]
        else:
            output = Path(folder) / f"{stem}.mp3"
            command = [ffmpeg, "-y", "-i", str(source), "-vn", "-codec:a", "libmp3lame", "-q:a", "4", str(output)]
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        if completed.returncode != 0 or not output.exists():
            raise ValueError("O FFmpeg não conseguiu processar este arquivo. Verifique o formato e o conteúdo do vídeo.")
        return [(io.BytesIO(output.read_bytes()), output.name)]


def process_file(action: str, filename: str, content: bytes, target_format: str = "PNG"):
    safe_name = Path(filename or "arquivo").name
    if action in {"convert", "compress", "extract"}:
        return _ffmpeg_result(action, safe_name, content)
    try:
        image = Image.open(io.BytesIO(content))
    except Exception as exc:
        raise ValueError("Envie uma imagem compatível para Preto e branco.") from exc
    image = ImageOps.grayscale(image)
    return [_image_result(image, "PNG", f"preto-branco-{Path(safe_name).stem}.png")]


async def ensure_log_channel(bot, guild):
    definitions = load_guild_channels(guild)
    key = "canal_de_logs_de_conversor"
    raw = definitions.get(key)
    channel = guild.get_channel(int(raw)) if str(raw or "").isdigit() else None
    if channel:
        set_config({"log_channel_id": str(channel.id)})
        return channel
    cfg = auto_setup.get_config()
    label = "Logs de Conversor"
    name = auto_setup.channel_name(key, label, cfg)
    category_name = cfg.get("logs_category") or "╺╸ Logs"
    category = next((item for item in guild.categories if item.name.lower() == str(category_name).lower()), None)
    if category is None:
        category = await guild.create_category(str(category_name)[:100], reason="Criando categoria de logs do Conversor")
    overwrites = {guild.default_role: disnake.PermissionOverwrite(view_channel=False)} if cfg.get("private_logs", True) else None
    channel = await guild.create_text_channel(name, category=category, overwrites=overwrites, reason="Criando canal de logs do Conversor")
    definitions[key] = str(channel.id)
    save_guild_channels(guild, definitions)
    set_config({"log_channel_id": str(channel.id)})
    return channel


async def log_event(bot, guild, title, description, actor=None):
    if not guild:
        return
    try:
        channel = await ensure_log_channel(bot, guild)
        data = ensure_data()
        data["logs"].append({"title": title, "description": description, "actor_id": str(getattr(actor, "id", "")), "at": now_iso()})
        save(data)
        await send_system_log(bot, guild, title=title, description=description, system="Conversor", actor=actor, channel_id=channel.id)
    except Exception as exc:
        print(f"[Conversor] Falha ao enviar log: {exc}")


def public_components(bot):
    cfg = ensure_data()["config"]
    title_emoji = resolve_emoji(cfg.get("title_emoji"), bot=bot, fallback=internal_emoji("textc", "📝"))
    children = [disnake.ui.TextDisplay(f"# {title_emoji} {cfg.get('title', DEFAULT_TITLE)}\n\n{cfg.get('description', DEFAULT_DESCRIPTION)}")]
    for value in OPERATION_INFO:
        info = option_info(value)
        icon = resolve_emoji(info["emoji"], bot=bot, fallback=internal_emoji("textc", "📝"))
        children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
        children.append(disnake.ui.TextDisplay(f"{icon}  **{info['title']}**\n{info['description']}"))
    options = [disnake.SelectOption(label=option_info(value)["title"], value=value, description=option_info(value)["description"][:100], emoji=resolve_emoji(option_info(value)["emoji"], bot=bot, fallback=internal_emoji("textc", "📝"))) for value in OPERATION_INFO]
    children.extend([disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small), disnake.ui.ActionRow(disnake.ui.StringSelect(placeholder="Escolha uma operação", custom_id="Conversor_Action", options=options))])
    return [disnake.ui.Container(*children, accent_colour=primary_colour())]


def processing_components(bot, action, filename, state="loading", error=None):
    info = option_info(action)
    if state == "done":
        icon = internal_emoji("correct", "✅")
        title = "Operação concluída"
        text = f"O arquivo `{filename}` foi processado com sucesso. O resultado está sendo enviado abaixo."
    elif state == "error":
        icon = internal_emoji("wrong", "❌")
        title = "Não foi possível concluir"
        text = str(error or "O arquivo não pôde ser processado.")
    else:
        icon = internal_emoji("loading", "⏳")
        title = "Processando arquivo"
        text = f"A operação **{info['title']}** está sendo executada. Aguarde enquanto o arquivo é processado."
    return [disnake.ui.Container(
        disnake.ui.TextDisplay(f"# {icon} {title}\n\n{text}"),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.TextDisplay(f"{internal_emoji(info['emoji'], 'textc')} Arquivo: `{filename}`"),
    )]


def session_components(bot, action, channel_id):
    info = option_info(action)
    icon = resolve_emoji(info["emoji"], bot=bot, fallback=internal_emoji("textc", "📝"))
    return [disnake.ui.Container(
        disnake.ui.TextDisplay(f"# {icon} {info['title']}\n\nEnvie o arquivo solicitado neste canal para iniciar automaticamente."),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.TextDisplay(f"**Arquivo esperado**\nFormatos aceitos: `{info['formats']}`\nTamanho recomendado: `{info['size']}`\n\n**Como vai funcionar**\nAssim que você enviar o arquivo, será exibida uma mensagem de processamento. Quando terminar, o resultado será enviado aqui mesmo. Se não for possível processar, o motivo será explicado."),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.ActionRow(disnake.ui.Button(label="Fechar", emoji=internal_emoji("lock", "🔒"), style=disnake.ButtonStyle.danger, custom_id="Conversor_Close")),
    )]


def option_editor_components(bot):
    options = [disnake.SelectOption(label=option_info(value)["title"], value=value, description=option_info(value)["description"][:100], emoji=resolve_emoji(option_info(value)["emoji"], bot=bot, fallback=internal_emoji("textc", "📝"))) for value in OPERATION_INFO]
    return [disnake.ui.Container(
        disnake.ui.TextDisplay(f"# {internal_emoji('settings', '⚙️')} Editar opções\n\nEscolha uma opção do Conversor para editar o nome, a descrição e o emoji personalizado do painel."),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.ActionRow(disnake.ui.StringSelect(placeholder="Escolha a opção para editar", custom_id="Conversor_OptionSelect", options=options)),
    )]


def admin_components(bot):
    cfg = ensure_data()["config"]
    enabled = bool(cfg.get("enabled"))
    log_channel = f"<#{cfg['log_channel_id']}>" if cfg.get('log_channel_id') else "Não configurado"
    publish_channel = f"<#{cfg['channel_id']}>" if cfg.get('channel_id') else "Canal atual"
    private_category = f"<#{cfg['category_id']}>" if cfg.get('category_id') else "╺╸ Conversor (padrão)"
    close_time = format_duration(cfg.get("close_after_seconds", 1800))
    children = [
        disnake.ui.TextDisplay(f"# {internal_emoji('save', '💾')} Gerenciar Conversor\n-# Painel > Sistemas > **Conversor**\n\n{internal_emoji('power', '⚡')} **Status:** `{'Ativo' if enabled else 'Desativado'}`\n{internal_emoji('textc', '📝')} **Canal de logs:** {log_channel}\n{internal_emoji('textc', '📝')} **Canal de publicação:** {publish_channel}\n{internal_emoji('settings', '⚙️')} **Categoria privada:** {private_category}\n{internal_emoji('clock', '🕒')} **Fechar canal após:** `{close_time}`\n\n{internal_emoji('textc', '📝')} **Título:** {cfg.get('title', DEFAULT_TITLE)}\n{internal_emoji('textc', '📝')} **Descrição:** {cfg.get('description', DEFAULT_DESCRIPTION)}"),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.ActionRow(
            disnake.ui.Button(label="Desativar" if enabled else "Ativar", emoji=internal_emoji("power", "⚡"), style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.green, custom_id="Conversor_Toggle"),
            disnake.ui.Button(label="Publicar", emoji=internal_emoji("announcement", ""), style=disnake.ButtonStyle.green, custom_id="Conversor_Publish", disabled=not enabled),
            disnake.ui.Button(label="Editar painel", emoji=internal_emoji("settings", "⚙️"), style=disnake.ButtonStyle.secondary, custom_id="Conversor_Edit", disabled=not enabled),
            disnake.ui.Button(label="Editar opções", emoji=internal_emoji("textc", "📝"), style=disnake.ButtonStyle.secondary, custom_id="Conversor_Options", disabled=not enabled),
            disnake.ui.Button(label="Criar canal de logs", emoji=internal_emoji("textc", "📋"), style=disnake.ButtonStyle.secondary, custom_id="Conversor_Logs", disabled=not enabled),
        ),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.ActionRow(
            disnake.ui.Button(label="Editar tempo", emoji=internal_emoji("clock", "🕒"), style=disnake.ButtonStyle.secondary, custom_id="Conversor_Time", disabled=not enabled),
            disnake.ui.Button(label="Editar canal", emoji=internal_emoji("textc", "📋"), style=disnake.ButtonStyle.secondary, custom_id="Conversor_Channel", disabled=not enabled),
            disnake.ui.Button(label="Editar categoria", emoji=internal_emoji("settings", "⚙️"), style=disnake.ButtonStyle.secondary, custom_id="Conversor_Category", disabled=not enabled),
        ),
    ]
    return [disnake.ui.Container(*children, accent_colour=primary_colour())]


class ConversorEditModal(disnake.ui.Modal):
    def __init__(self, cog):
        cfg = ensure_data()["config"]
        self.cog = cog
        super().__init__(title="Editar painel do Conversor", custom_id="Conversor_EditModal", components=[
            disnake.ui.TextInput(label="Título", custom_id="title", value=str(cfg.get("title", DEFAULT_TITLE))[:100], max_length=100),
            disnake.ui.TextInput(label="Descrição", custom_id="description", style=disnake.TextInputStyle.paragraph, value=str(cfg.get("description", DEFAULT_DESCRIPTION))[:900], max_length=900),
            disnake.ui.TextInput(label="ID ou emoji do título", custom_id="title_emoji", value=str(cfg.get("title_emoji", "textc"))[:40], required=False, max_length=40),
        ])

    async def callback(self, inter):
        set_config({"title": inter.text_values.get("title", DEFAULT_TITLE)[:100], "description": inter.text_values.get("description", DEFAULT_DESCRIPTION)[:900], "title_emoji": inter.text_values.get("title_emoji", "textc")[:40]})
        await inter.response.send_message(f"{emoji.correct} Painel do Conversor atualizado.", ephemeral=True)
