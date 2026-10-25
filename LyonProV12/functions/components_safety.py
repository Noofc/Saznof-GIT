"""Ajustes globais para componentes do Discord."""

from __future__ import annotations

import re
import unicodedata

import disnake


_CUSTOM_EMOJI_RE = re.compile(r"^<a?:[A-Za-z0-9_~]{2,32}:\d{17,22}>$")
_PATCHED = False
_GENERIC_EMOJI_KEYS = {
    "\u2705": "correct",
    "\u274c": "wrong",
    "\u26a0": "warn",
    "\u2139": "information",
    "\u21bb": "reload",
    "\u23fb": "power",
    "\u25cf": "on",
    "\u21a9": "back",
    "\u270f": "edit",
    "\u25b6": "play",
    "\u2b50": "star",
    "\U0001f44d": "like",
    "\U0001f44e": "deslike",
    "\U0001f4ac": "speech",
    "\U0001f5d1": "delete",
    "\U0001f465": "members",
    "\U0001f517": "link",
    "\U0001f4c4": "receipt",
    "\U0001f4a1": "bulb",
    "\U0001f4c5": "calendar",
    "\U0001f4f8": "image",
    "\U0001f44b": "members",
    "\U0001f91d": "partner",
    "\U0001f3ae": "controller",
    "\U0001f4b0": "coin",
    "\U0001f512": "lock",
    "\U0001f4b3": "card",
    "\U0001f4ca": "chart",
    "\U0001f48e": "diamond",
    "\U0001f7e2": "green",
    "\U0001f534": "red",
    "\U0001f4e3": "announcement",
    "\U0001f4da": "folder",
    "\U0001f4e6": "cardbox",
    "\U0001f916": "robot",
    "\U0001f3b2": "swords",
}


def _sanitize_emoji(value):
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if _CUSTOM_EMOJI_RE.match(stripped) else None
    return value


def _plain(value) -> str:
    text = str(value or "").lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _custom_emoji(key: str | None):
    if not key:
        return None
    try:
        from functions.emoji import emoji

        value = getattr(emoji, key, None)
        if isinstance(value, str) and _CUSTOM_EMOJI_RE.match(value.strip()):
            return value.strip()
    except Exception:
        pass
    return None


def _generic_emoji_key(value) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return _GENERIC_EMOJI_KEYS.get(stripped) or _GENERIC_EMOJI_KEYS.get(stripped.replace("\ufe0f", ""))


def _infer_emoji_key(*values) -> str:
    text = " ".join(_plain(value) for value in values if value)
    checks = [
        (("voltar", "back", "cancelar"), "back"),
        (("apagar", "delet", "delete", "remover", "limpar"), "delete"),
        (("confirm", "aprovar", "salvar", "assumir", "ativar"), "correct"),
        (("rejeitar", "desativar", "fechar"), "wrong"),
        (("histor", "extrato"), "receipt"),
        (("saldo", "carteira", "wallet"), "wallet"),
        (("sacar", "comissao", "coin", "economia", "emprestar"), "coin"),
        (("transfer", "enviar", "send"), "arrow"),
        (("loja", "produto", "comprar"), "store"),
        (("ticket", "atendimento", "suporte"), "ticket"),
        (("middleman", "intermedi"), "shield"),
        (("fivem", "game", "gaming", "jogo"), "controller"),
        (("aposta", "filas", "partida", "freefire", "ff"), "swords"),
        (("instagram", "foto", "video", "midia", "gifs"), "image"),
        (("twitter", "twitterx"), "slash"),
        (("tellonym", "telegram"), "telegram"),
        (("engajamento", "participar", "reaction"), "reaction"),
        (("parceria", "afiliado", "partner"), "partner"),
        (("robux", "premium"), "diamond"),
        (("cloud",), "cloud"),
        (("modera", "protec", "permiss"), "shield"),
        (("verifica", "whitelist", "liberacao"), "verified"),
        (("canal", "channel"), "canal"),
        (("cargo", "equipe", "staff"), "role"),
        (("config", "gerenciar", "editar", "modelo", "personaliza"), "settings"),
        (("publicar", "anunciar", "painel"), "announcement"),
        (("recarregar", "reload", "atualizar", "reabrir"), "reload"),
        (("online", "membros", "jogadores", "usuarios"), "members"),
        (("nivel", "ranking", "reputacao"), "trophy"),
        (("buscar", "pesquisar", "ver mais"), "search"),
        (("abrir menu", "menu", "sistemas"), "commands"),
        (("abrir", "entrar", "play"), "play"),
        (("link", "url"), "link"),
        (("taxa", "pagamento", "pix"), "dollar"),
        (("logs", "mensagem", "comentario"), "speech"),
    ]
    for needles, key in checks:
        if any(needle in text for needle in needles):
            return key
    return "commands"


def apply_component_safety() -> None:
    """Normaliza componentes para usarem emojis personalizados do bot."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    original_button_init = disnake.ui.Button.__init__
    original_select_option_init = disnake.SelectOption.__init__

    def safe_button_init(self, *args, **kwargs):
        label = kwargs.get("label")
        if label is None and args:
            label = args[0]
        custom_id = kwargs.get("custom_id")
        url = kwargs.get("url")
        raw_emoji = kwargs.get("emoji")
        sanitized = _sanitize_emoji(raw_emoji)
        kwargs["emoji"] = sanitized or _custom_emoji(_generic_emoji_key(raw_emoji) or _infer_emoji_key(label, custom_id, url))
        return original_button_init(self, *args, **kwargs)

    def safe_select_option_init(self, *args, **kwargs):
        label = kwargs.get("label")
        value = kwargs.get("value")
        description = kwargs.get("description")
        if label is None and args:
            label = args[0]
        if value is None and len(args) > 1:
            value = args[1]
        raw_emoji = kwargs.get("emoji")
        sanitized = _sanitize_emoji(raw_emoji)
        kwargs["emoji"] = sanitized or _custom_emoji(_generic_emoji_key(raw_emoji) or _infer_emoji_key(label, value, description))
        return original_select_option_init(self, *args, **kwargs)

    disnake.ui.Button.__init__ = safe_button_init
    disnake.SelectOption.__init__ = safe_select_option_init
