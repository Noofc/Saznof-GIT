from __future__ import annotations

from typing import Any


MAX_DESCRIPTION_LENGTH = 100
DEFAULT_EMOJI = "✨"

COMMAND_EMOJIS = {
    "adicionar": "➕",
    "adicionar_amigo": "👥",
    "analise_mercado": "📈",
    "anunciar": "📣",
    "apostar_ff": "🎮",
    "apostas_ff": "🎮",
    "backup": "💾",
    "ban": "🔨",
    "buscar_pedido": "🧾",
    "calcular_juros": "📊",
    "calcular_lucro": "💹",
    "castigo": "⚖️",
    "conectar": "🔊",
    "convites": "📨",
    "criar_parceria": "🤝",
    "criar_partida_ff": "🎮",
    "cupom_massa": "🏷️",
    "desbanir": "✅",
    "economia": "💰",
    "emprestar": "💸",
    "entregar": "📦",
    "eventos": "📅",
    "expulsar": "👢",
    "falar": "📢",
    "ferramentas_economia": "🧰",
    "gerenciar": "🛍️",
    "gift": "🎁",
    "giveaway": "🎉",
    "limpar": "🧹",
    "lock": "🔒",
    "meu_relatorio": "📋",
    "meta_poupanca": "🎯",
    "nuke": "💥",
    "pagamento": "💳",
    "painel": "⚙️",
    "parceria": "🤝",
    "perfil": "👤",
    "perfil_comunidade": "👥",
    "ranking": "🏆",
    "ranking_comunidade": "🏆",
    "ranking_economia": "🏆",
    "ranking_parceiros": "🏆",
    "remover": "➖",
    "setup": "🛠️",
    "sincronizar_clientes": "🔄",
    "solicitar_estoque": "📦",
    "systemgen": "🔗",
    "ticket": "🎫",
    "transferir": "💱",
    "unlock": "🔓",
}

KEYWORD_EMOJIS = (
    ("ticket", "🎫"),
    ("pedido", "🧾"),
    ("pagamento", "💳"),
    ("pix", "💎"),
    ("loja", "🛒"),
    ("produto", "📦"),
    ("estoque", "📦"),
    ("cupom", "🏷️"),
    ("gift", "🎁"),
    ("sorteio", "🎉"),
    ("giveaway", "🎉"),
    ("parceria", "🤝"),
    ("ranking", "🏆"),
    ("perfil", "👤"),
    ("economia", "💰"),
    ("saldo", "💰"),
    ("lucro", "💹"),
    ("juros", "📊"),
    ("relatorio", "📋"),
    ("mercado", "📈"),
    ("meta", "🎯"),
    ("comunidade", "👥"),
    ("amigo", "👥"),
    ("evento", "📅"),
    ("ban", "🔨"),
    ("expuls", "👢"),
    ("castig", "⚖️"),
    ("limp", "🧹"),
    ("lock", "🔒"),
    ("unlock", "🔓"),
    ("nuke", "💥"),
    ("cargo", "👑"),
    ("convite", "📨"),
    ("dm", "✉️"),
    ("mensagem", "💬"),
    ("canal", "📌"),
    ("voz", "🔊"),
    ("backup", "💾"),
    ("painel", "⚙️"),
    ("config", "⚙️"),
    ("setup", "🛠️"),
    ("anunci", "📣"),
    ("free fire", "🎮"),
    ("aposta", "🎮"),
    ("boost", "🚀"),
    ("system", "🔗"),
)


def _body(command_or_option: Any) -> Any:
    return getattr(command_or_option, "body", None) or getattr(command_or_option, "option", None) or command_or_option


def _description(command_or_option: Any) -> str:
    return str(getattr(_body(command_or_option), "description", "") or "")


def _set_description(command_or_option: Any, description: str) -> None:
    setattr(_body(command_or_option), "description", description)


def _emoji_for(name: str | None, description: str | None = None, fallback: str = DEFAULT_EMOJI) -> str:
    normalized_name = str(name or "").lower()
    text = f"{normalized_name} {str(description or '').lower()}"

    if normalized_name in COMMAND_EMOJIS:
        return COMMAND_EMOJIS[normalized_name]

    for keyword, emoji in KEYWORD_EMOJIS:
        if keyword in text:
            return emoji

    return fallback


def _is_decorated(description: str) -> bool:
    if not description:
        return False

    first = description.strip()[:1]
    return bool(first and not first.isalnum() and first not in {"-", "_", "`", "*"})


def _fit_description(description: str) -> str:
    description = description.strip() or "-"
    if len(description) <= MAX_DESCRIPTION_LENGTH:
        return description

    return description[: MAX_DESCRIPTION_LENGTH - 3].rstrip() + "..."


def _unicode_emoji_tokens() -> tuple[str, ...]:
    values = set(COMMAND_EMOJIS.values())
    values.update(value for _, value in KEYWORD_EMOJIS)
    values.add(DEFAULT_EMOJI)
    return tuple(sorted(values, key=len, reverse=True))


def _strip_leading_unicode_emojis(description: str) -> str:
    text = str(description or "").strip()
    changed = True
    tokens = _unicode_emoji_tokens()
    while changed and text:
        changed = False
        for token in tokens:
            if text.startswith(token):
                text = text[len(token):].lstrip(" \u200b")
                changed = True
                break
    return text or "-"


def _decorate_text(description: str, emoji: str, fallback_text: str) -> str:
    description = _strip_leading_unicode_emojis(description)
    if not description or description == "-":
        description = fallback_text
    return _fit_description(description)


def _decorate_options(options: list[Any], fallback_emoji: str) -> int:
    updated = 0

    for option in options or []:
        option_description = _description(option)
        option_emoji = _emoji_for(getattr(option, "name", None), option_description, fallback_emoji)
        new_description = _decorate_text(
            option_description,
            option_emoji,
            f"Opção {getattr(option, 'name', 'do comando')}",
        )

        if new_description != option_description:
            _set_description(option, new_description)
            updated += 1

        updated += _decorate_options(getattr(option, "options", []) or [], option_emoji)

    return updated


def _decorate_command(command: Any, fallback_emoji: str = DEFAULT_EMOJI) -> int:
    description = _description(command)
    emoji = _emoji_for(getattr(command, "name", None), description, fallback_emoji)
    new_description = _decorate_text(
        description,
        emoji,
        f"Comandos de {getattr(command, 'name', 'sistema')}",
    )

    updated = 0
    if new_description != description:
        _set_description(command, new_description)
        updated += 1

    updated += _decorate_options(getattr(_body(command), "options", []) or [], emoji)

    for child in (getattr(command, "children", {}) or {}).values():
        updated += _decorate_command(child, emoji)

    return updated


def apply_slash_command_emojis(bot: Any) -> int:
    """Adiciona emojis nas descrições dos slash commands sem alterar seus nomes."""
    updated = 0
    for command in getattr(bot, "slash_commands", []) or []:
        updated += _decorate_command(command)

    print(f"[SlashEmojis] {updated} descricoes de slash commands decoradas.")
    return updated
