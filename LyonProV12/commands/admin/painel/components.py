from datetime import datetime

import disnake

from functions.database import database as db
from functions.display_mode import get_panel_layout, normalize_panel_layout
from functions.emoji import emoji
from functions.plan import should_enable_panel_button

PANEL_HEADER_FILENAME = "painellyonapplications.png"
PANEL_HEADER_ATTACHMENT = f"attachment://{PANEL_HEADER_FILENAME}"
DEFAULT_ACCENT_COLOR = 0x0A84FF

MAIN_BUTTON_PANEL_IDS = {
    "Painel_Loja",
    "Painel_Ticket",
    "Painel_BoasVindas",
    "Painel_Personalizacao",
    "Painel_Protection",
    "Painel_Rendimentos",
    "Painel_Automacoes",
    "Painel_Sorteios",
    "Painel_Configuracoes",
    "Painel_Parcerias",
    "Painel_Robux",
}

HOME_BUTTON_PANEL_IDS = {
    "Painel_Loja",
    "Painel_Ticket",
    "Painel_BoasVindas",
    "Painel_Personalizacao",
    "Painel_Rendimentos",
    "Painel_Automacoes",
    "Painel_Engajamento",
    "Painel_Instagram",
    "Painel_FiveM",
    "Painel_BatePonto",
    "Painel_Organizador",
    "Painel_Protection",
    "Painel_Sorteios",
    "Painel_Configuracoes",
    "Painel_Parcerias",
    "Painel_Robux",
}

PINNED_SELECT_PANEL_IDS = {
    "Painel_Parcerias",
    "Painel_Middleman",
    "Painel_ApostadoFF",
    "Painel_FilasApostas",
}



PANEL_GROUPS = {
    "PainelGrupo_Mais": {
        "title": "Mais Sistemas",
        "emoji": ("commands", "tools"),
        "items": [
            ("Atendimento", "PainelGrupo_Atendimento", "ticket", None, disnake.ButtonStyle.grey),
            ("Sistemas", "PainelGrupo_Sistemas", "commands", None, disnake.ButtonStyle.grey),
            ("Social", "PainelGrupo_Social", "speech", None, disnake.ButtonStyle.grey),
            ("Administração", "PainelGrupo_Admin", "settings", None, disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Atendimento": {
        "title": "Atendimento",
        "emoji": ("ticket", "headset"),
        "items": [
            ("Gerenciar Ticket", "Painel_Ticket", "ticket", "ticket", disnake.ButtonStyle.grey),
            ("Middleman", "Painel_Middleman", "shield", None, disnake.ButtonStyle.grey),
            ("Detector Golpes", "Painel_ScamDetector", "shield_star", "scamdetector", disnake.ButtonStyle.grey),
            ("Apostado FF", "Painel_ApostadoFF", "Uzi", None, disnake.ButtonStyle.blurple),
        ],
    },
    "PainelGrupo_Sistemas": {
        "title": "Sistemas",
        "emoji": ("commands", "tools"),
        "items": [
            ("FiveM", "Painel_FiveM", "controller", "fivem", disnake.ButtonStyle.grey),
            ("Robux", "Painel_Robux", "diamond", "robux", disnake.ButtonStyle.blurple),
            ("Gift Cards", "Painel_GiftCard", "gift", "giftcard", disnake.ButtonStyle.grey),
            ("Key", "Painel_Key", "thunder", "keys", disnake.ButtonStyle.green),
            ("Conversor", "Painel_Conversor", "textc", "conversor", disnake.ButtonStyle.green),
            ("Twitter", "Painel_Twitter", "textc", "twitter", disnake.ButtonStyle.grey),
            ("Sistema IA", "Painel_SistemaIA", "robot", "sistemaai", disnake.ButtonStyle.grey),
            ("Economia", "Painel_Economia", "coin", None, disnake.ButtonStyle.grey),
            ("Comunidade", "Painel_Comunidade", "members", None, disnake.ButtonStyle.grey),
            ("Ferramentas", "Painel_Ferramentas", "hammer", None, disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Social": {
        "title": "Social",
        "emoji": ("speech", "reaction"),
        "items": [
            ("Engajamento", "Painel_Engajamento", "reaction", "engajamento", disnake.ButtonStyle.grey),
            ("Instagram", "Painel_Instagram", "image", "instagram", disnake.ButtonStyle.grey),
            ("Parcerias", "Painel_Parcerias", "partner", "parcerias", disnake.ButtonStyle.green),
            ("Feedback", "Painel_Feedback", "speech", "feedback", disnake.ButtonStyle.grey),
            ("Ranking", "Painel_Ranking", "trophy", "ranking", disnake.ButtonStyle.grey),
            ("GIFs", "Painel_GIFs", "image", "gifs", disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Admin": {
        "title": "Administração",
        "emoji": ("settings", "config"),
        "items": [
            ("Cloud", "Painel_Cloud", "cloud", "cloud", disnake.ButtonStyle.grey),
            ("Moderação", "Painel_Moderacao", "shield", "moderacao", disnake.ButtonStyle.grey),
            ("Verificação", "Painel_Verificacao", "lock", "verificacao", disnake.ButtonStyle.grey),
            ("Bate Ponto", "Painel_BatePonto", "clock", "bateponto", disnake.ButtonStyle.grey),
            ("Aviso Stock", "Painel_Stock", "cardbox", "stock", disnake.ButtonStyle.grey),
            ("Anti Fraude", "Painel_AntiFraude", "shield", "antifraude", disnake.ButtonStyle.grey),
            ("Detector Golpes", "Painel_ScamDetector", "shield_star", "scamdetector", disnake.ButtonStyle.grey),
            ("Organizador", "Painel_Organizador", "settings", "organizador", disnake.ButtonStyle.green),
            ("Auto Setup", "Painel_AutoSetup", "wand", "autosetup", disnake.ButtonStyle.green),
        ],
    },
}

LEGACY_PANEL_GROUPS = PANEL_GROUPS

PANEL_GROUPS = {
    "PainelGrupo_Mais": {
        "title": "Central de Sistemas",
        "emoji": ("commands", "tools"),
        "items": [
            ("Vendas", "PainelGrupo_Vendas", "store", None, disnake.ButtonStyle.green),
            ("Operacao", "PainelGrupo_Operacao", "settings", None, disnake.ButtonStyle.grey),
            ("Comunidade", "PainelGrupo_Comunidade", "members", None, disnake.ButtonStyle.grey),
            ("Administracao", "PainelGrupo_Admin", "shield", None, disnake.ButtonStyle.grey),
            ("Integracoes", "PainelGrupo_Integracoes", "cloud", None, disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Vendas": {
        "title": "Vendas",
        "emoji": ("store", "cart"),
        "items": [
            ("Loja", "Painel_Loja", "store", "loja", disnake.ButtonStyle.green),
            ("Rendimentos", "Painel_Rendimentos", "rendimentos", "rendimentos", disnake.ButtonStyle.green),
            ("Gift Cards", "Painel_GiftCard", "gift", "giftcard", disnake.ButtonStyle.grey),
            ("Robux", "Painel_Robux", "diamond", "robux", disnake.ButtonStyle.blurple),
            ("Aviso Stock", "Painel_Stock", "cardbox", "stock", disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Operacao": {
        "title": "Operacao",
        "emoji": ("settings", "tools"),
        "items": [
            ("Tickets", "Painel_Ticket", "ticket", "ticket", disnake.ButtonStyle.grey),
            ("Middleman", "Painel_Middleman", "shield", None, disnake.ButtonStyle.grey),
            ("Bate Ponto", "Painel_BatePonto", "clock", "bateponto", disnake.ButtonStyle.grey),
            ("Boas Vindas", "Painel_BoasVindas", "members", "boasvindas", disnake.ButtonStyle.grey),
            ("Apostado FF", "Painel_ApostadoFF", "Uzi", None, disnake.ButtonStyle.blurple),
        ],
    },
    "PainelGrupo_Comunidade": {
        "title": "Comunidade",
        "emoji": ("members", "users"),
        "items": [
            ("Comunidade", "Painel_Comunidade", "members", None, disnake.ButtonStyle.grey),
            ("Instagram", "Painel_Instagram", "image", "instagram", disnake.ButtonStyle.grey),
            ("Engajamento", "Painel_Engajamento", "reaction", "engajamento", disnake.ButtonStyle.grey),
            ("Parcerias", "Painel_Parcerias", "partner", "parcerias", disnake.ButtonStyle.green),
            ("Sorteios", "Painel_Sorteios", "giveaway", "sorteios", disnake.ButtonStyle.grey),
            ("Feedback", "Painel_Feedback", "speech", "feedback", disnake.ButtonStyle.grey),
            ("Ranking", "Painel_Ranking", "trophy", "ranking", disnake.ButtonStyle.grey),
            ("GIFs", "Painel_GIFs", "image", "gifs", disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Admin": {
        "title": "Administracao",
        "emoji": ("shield", "settings"),
        "items": [
            ("Configuracoes", "Painel_Configuracoes", "settings", "configuracoes", disnake.ButtonStyle.grey),
            ("Permissao", "Painel_Protection", "flag", "protection", disnake.ButtonStyle.grey),
            ("Personalizacao", "Painel_Personalizacao", "paint", "personalizacao", disnake.ButtonStyle.grey),
            ("Automacoes", "Painel_Automacoes", "wand", "automacoes", disnake.ButtonStyle.grey),
            ("Moderacao", "Painel_Moderacao", "shield", "moderacao", disnake.ButtonStyle.grey),
            ("Verificacao", "Painel_Verificacao", "lock", "verificacao", disnake.ButtonStyle.grey),
            ("Anti Fraude", "Painel_AntiFraude", "shield", "antifraude", disnake.ButtonStyle.grey),
            ("Organizador", "Painel_Organizador", "settings", "organizador", disnake.ButtonStyle.green),
            ("Auto Setup", "Painel_AutoSetup", "wand", "autosetup", disnake.ButtonStyle.green),
            ("Economia", "Painel_Economia", "coin", None, disnake.ButtonStyle.grey),
            ("Ferramentas", "Painel_Ferramentas", "hammer", None, disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Integracoes": {
        "title": "Integracoes",
        "emoji": ("cloud", "link"),
        "items": [
            ("FiveM", "Painel_FiveM", "controller", "fivem", disnake.ButtonStyle.grey),
            ("Sistema IA", "Painel_SistemaIA", "robot", "sistemaai", disnake.ButtonStyle.grey),
            ("Lyon Cloud", "Painel_Cloud", "cloud", "cloud", disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Atendimento": {
        "title": "Atendimento",
        "emoji": ("ticket", "headset"),
        "items": [
            ("Tickets", "Painel_Ticket", "ticket", "ticket", disnake.ButtonStyle.grey),
            ("Middleman", "Painel_Middleman", "shield", None, disnake.ButtonStyle.grey),
            ("Bate Ponto", "Painel_BatePonto", "clock", "bateponto", disnake.ButtonStyle.grey),
            ("Boas Vindas", "Painel_BoasVindas", "members", "boasvindas", disnake.ButtonStyle.grey),
            ("Apostado FF", "Painel_ApostadoFF", "Uzi", None, disnake.ButtonStyle.blurple),
        ],
    },
    "PainelGrupo_Sistemas": {
        "title": "Sistemas",
        "emoji": ("commands", "tools"),
        "items": [
            ("FiveM", "Painel_FiveM", "controller", "fivem", disnake.ButtonStyle.grey),
            ("Robux", "Painel_Robux", "diamond", "robux", disnake.ButtonStyle.blurple),
            ("Gift Cards", "Painel_GiftCard", "gift", "giftcard", disnake.ButtonStyle.grey),
            ("Key", "Painel_Key", "thunder", "keys", disnake.ButtonStyle.green),
            ("Conversor", "Painel_Conversor", "textc", "conversor", disnake.ButtonStyle.green),
            ("Twitter", "Painel_Twitter", "textc", "twitter", disnake.ButtonStyle.grey),
            ("Sistema IA", "Painel_SistemaIA", "robot", "sistemaai", disnake.ButtonStyle.grey),
            ("Economia", "Painel_Economia", "coin", None, disnake.ButtonStyle.grey),
            ("Comunidade", "Painel_Comunidade", "members", None, disnake.ButtonStyle.grey),
            ("Ferramentas", "Painel_Ferramentas", "hammer", None, disnake.ButtonStyle.grey),
            ("Aviso Stock", "Painel_Stock", "cardbox", "stock", disnake.ButtonStyle.grey),
            ("Lyon Cloud", "Painel_Cloud", "cloud", "cloud", disnake.ButtonStyle.grey),
        ],
    },
    "PainelGrupo_Social": {
        "title": "Comunidade",
        "emoji": ("members", "users"),
        "items": [
            ("Comunidade", "Painel_Comunidade", "members", None, disnake.ButtonStyle.grey),
            ("Instagram", "Painel_Instagram", "image", "instagram", disnake.ButtonStyle.grey),
            ("Engajamento", "Painel_Engajamento", "reaction", "engajamento", disnake.ButtonStyle.grey),
            ("Parcerias", "Painel_Parcerias", "partner", "parcerias", disnake.ButtonStyle.green),
            ("Sorteios", "Painel_Sorteios", "giveaway", "sorteios", disnake.ButtonStyle.grey),
            ("Feedback", "Painel_Feedback", "speech", "feedback", disnake.ButtonStyle.grey),
            ("Ranking", "Painel_Ranking", "trophy", "ranking", disnake.ButtonStyle.grey),
            ("GIFs", "Painel_GIFs", "image", "gifs", disnake.ButtonStyle.grey),
        ],
    },
}

PANEL_GROUP_IDS = set(PANEL_GROUPS)


def get_salutation() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "bom dia!"
    if 12 <= hour < 18:
        return "boa tarde!"
    return "boa noite!"


def get_panel_button_states(button_states: dict = None) -> dict:
    if button_states is not None:
        button_states.setdefault("rendimentos", should_enable_panel_button("rendimentos"))
        button_states.setdefault("boasvindas", True)
        button_states.setdefault("parcerias", True)
        button_states.setdefault("robux", True)
        button_states.setdefault("engajamento", True)
        button_states.setdefault("instagram", True)
        button_states.setdefault("twitter", True)
        button_states.setdefault("fivem", True)
        button_states.setdefault("bateponto", True)
        button_states.setdefault("filasapostas", True)
        button_states.setdefault("antifraude", True)
        button_states.setdefault("scamdetector", True)
        button_states.setdefault("autosetup", True)
        button_states.setdefault("organizador", True)
        return button_states

    return {
        "loja": should_enable_panel_button("loja"),
        "ticket": should_enable_panel_button("ticket"),
        "cloud": should_enable_panel_button("cloud"),
        "personalizacao": should_enable_panel_button("personalizacao"),
        "automacoes": should_enable_panel_button("automacoes"),
        "protection": should_enable_panel_button("protection"),
        "sorteios": should_enable_panel_button("sorteios"),
        "configuracoes": should_enable_panel_button("configuracoes"),
        "rendimentos": should_enable_panel_button("rendimentos"),
        "boasvindas": True,
        "giftcard": True,
        "keys": True,
        "sistemaai": True,
        "filasapostas": True,
        "moderacao": True,
        "verificacao": True,
        "gifs": True,
        "ranking": True,
        "robux": True,
        "parcerias": True,
        "engajamento": True,
        "instagram": True,
        "twitter": True,
        "fivem": True,
        "bateponto": True,
        "stock": True,
        "antifraude": True,
        "scamdetector": True,
        "autosetup": True,
        "organizador": True,
        "feedback": True,
    }


def _emoji(key: str, default=None):
    return getattr(emoji, key, default)


def _button(label: str, custom_id: str, style=disnake.ButtonStyle.grey, disabled: bool = False, emoji_value=None) -> disnake.ui.Button:
    return disnake.ui.Button(label=label, custom_id=custom_id, style=style, disabled=disabled, emoji=emoji_value)


def _option(label: str, value: str, description: str = None, emoji_value=None) -> disnake.SelectOption:
    return disnake.SelectOption(label=label, value=value, description=description, emoji=emoji_value)


def _dedupe_options(options: list[disnake.SelectOption]) -> list[disnake.SelectOption]:
    unique = []
    seen = set()
    for option in options:
        if option.value in seen:
            continue
        seen.add(option.value)
        unique.append(option)
    return unique[:25]


def _user_display_name(inter: disnake.MessageInteraction) -> str:
    user = getattr(inter, "user", None) or getattr(inter, "author", None)
    return getattr(user, "display_name", None) or getattr(user, "name", "usuario")


def _get_bot_version() -> str:
    config = db.obter("config.json") or {}
    version = config.get("version") or config.get("bot", {}).get("version") or "2.0.0"
    version = str(version).strip()
    return version or "2.0.0"


def _format_uptime(inter: disnake.MessageInteraction) -> str:
    bot = getattr(inter, "bot", None)
    started_at = getattr(bot, "start_time", None)

    if isinstance(started_at, (int, float)):
        started_at = datetime.fromtimestamp(started_at)

    if not isinstance(started_at, datetime):
        return "agora"

    now = datetime.now(started_at.tzinfo) if started_at.tzinfo else datetime.now()
    seconds = max(int((now - started_at).total_seconds()), 0)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if seconds >= 3600:
        return f"{seconds // 3600}h {minutes}m" if minutes else f"{seconds // 3600}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return "agora"


def _format_ping(inter: disnake.MessageInteraction) -> str:
    latency = getattr(getattr(inter, "bot", None), "latency", None)
    if not isinstance(latency, (int, float)):
        return "0ms"
    return f"{max(int(latency * 1000), 0)}ms"


def build_select_options(button_states: dict, include_main_buttons: bool = True) -> list[disnake.SelectOption]:
    options = []

    if button_states["loja"]:
        options.append(_option("Gerenciar Loja", "Painel_Loja", "Configure sua loja", _emoji("store", _emoji("cart"))))
    if button_states["ticket"]:
        options.append(_option("Gerenciar Ticket", "Painel_Ticket", "Configure tickets", _emoji("ticket")))
    if button_states["cloud"]:
        options.append(_option("Lyon Cloud", "Painel_Cloud", "Acesse o cloud", _emoji("cloud")))
    if button_states["engajamento"]:
        options.append(_option("Engajamento", "Painel_Engajamento", "Sistema de engajamento", _emoji("reaction", _emoji("speech"))))
    if button_states["instagram"]:
        options.append(_option("Instagram", "Painel_Instagram", "Painel de Instagram", _emoji("image", _emoji("heart"))))
    if button_states["fivem"]:
        options.append(_option("FiveM", "Painel_FiveM", "Painel de FiveM", _emoji("controller", _emoji("route"))))
    if button_states.get("organizador", True):
        options.append(_option("Organizador", "Painel_Organizador", "Organize cargos, canais e permissoes", _emoji("settings", _emoji("tools"))))
    if button_states.get("autosetup", True):
        options.append(_option("Auto Setup", "Painel_AutoSetup", "Templates automaticos", _emoji("wand", _emoji("settings"))))
    if button_states["bateponto"]:
        options.append(_option("Bate Ponto", "Painel_BatePonto", "Controle de jornada da equipe", _emoji("clock", _emoji("time"))))
    if button_states["rendimentos"]:
        options.append(_option("Rendimentos Lyon", "Painel_Rendimentos", "Veja seus rendimentos", _emoji("rendimentos", _emoji("chart"))))
    if button_states["personalizacao"]:
        options.append(_option("Themes", "Painel_Personalizacao", "Personalize o bot", _emoji("paint", _emoji("wand"))))

    options.extend(
        [
            _option("Economia", "Painel_Economia", "Gerencie a economia", _emoji("coin", _emoji("dollar"))),
            _option("Comunidade", "Painel_Comunidade", "Recursos de comunidade", _emoji("members", _emoji("users"))),
            _option("Ferramentas", "Painel_Ferramentas", "Ferramentas e utilitários", _emoji("hammer", _emoji("tools"))),
            _option("Parcerias", "Painel_Parcerias", "Parcerias automáticas", _emoji("partner", _emoji("link"))),
            _option("Robux", "Painel_Robux", "Pedidos de Robux", _emoji("diamond", _emoji("coin"))),
        ]
    )

    if button_states.get("stock", True):
        options.append(_option("Aviso Stock", "Painel_Stock", "Alertas de estoque", _emoji("cardbox")))
    if button_states["automacoes"]:
        options.append(_option("Automações", "Painel_Automacoes", "Configure automações", _emoji("wand", _emoji("reload"))))
    if button_states["protection"]:
        options.append(_option("Proteção do Cliente", "Painel_Protection", "Configure proteções", _emoji("shield")))
    if button_states.get("antifraude", True):
        options.append(_option("Anti Fraude", "Painel_AntiFraude", "Bloqueios de compras suspeitas", _emoji("shield")))
    if button_states.get("scamdetector", True):
        options.append(_option("Detector Golpes", "Painel_ScamDetector", "Alerta golpes em tickets e middleman", _emoji("shield_star", _emoji("shield"))))
    if button_states["sorteios"]:
        options.append(_option("Giveaways", "Painel_Sorteios", "Gerencie sorteios", _emoji("giveaway")))
    if button_states["configuracoes"]:
        options.append(_option("Configurações", "Painel_Configuracoes", "Configurações gerais", _emoji("settings", _emoji("config"))))

    options.extend(
        [
            _option("Apostado Free Fire", "Painel_ApostadoFF", "Apostas Free Fire", _emoji("Uzi")),
            _option("Middleman", "Painel_Middleman", "Intermediacao segura", _emoji("shield")),
            _option("Boas Vindas", "Painel_BoasVindas", "Mensagens de boas-vindas", _emoji("members")),
            _option("Gift Cards", "Painel_GiftCard", "Gerencie gift cards", _emoji("gift")),
            _option("Key", "Painel_Key", "Crie, expire e publique keys", _emoji("thunder")),
            _option("Conversor", "Painel_Conversor", "Converta e processe arquivos", _emoji("textc")),
            _option("Twitter", "Painel_Twitter", "Envie tweets com aprovação e logs", _emoji("textc")),
            _option("Sistema IA", "Painel_SistemaIA", "Configure IA", _emoji("robot")),
            _option("Organizador", "Painel_Organizador", "Organize cargos, canais e permissoes", _emoji("settings", _emoji("tools"))),
            _option("Moderação", "Painel_Moderacao", "Ferramentas de moderação", _emoji("shield")),
            _option("Verificação", "Painel_Verificacao", "Sistema de verificação", _emoji("lock")),
            _option("Anti Fraude", "Painel_AntiFraude", "Bloqueios de compras suspeitas", _emoji("shield")),
            _option("GIFs Automaticos", "Painel_GIFs", "Configure GIFs automaticos", _emoji("image")),
            _option("Ranking", "Painel_Ranking", "Ranking de compradores", _emoji("trophy")),
            _option("Aviso Stock", "Painel_Stock", "Aviso de stock", _emoji("cardbox")),
            _option("Bate Ponto", "Painel_BatePonto", "Controle de jornada da equipe", _emoji("clock", _emoji("time"))),
            _option("Monitor Feedback", "Painel_Feedback", "Monitore feedbacks", _emoji("speech")),
        ]
    )

    if not include_main_buttons:
        options = [option for option in options if option.value not in MAIN_BUTTON_PANEL_IDS or option.value in PINNED_SELECT_PANEL_IDS]

    return _dedupe_options(options)


def _build_header_components(inter: disnake.MessageInteraction, show_header_image: bool):
    components = []
    if show_header_image:
        components.extend(
            [
                disnake.ui.MediaGallery(
                    disnake.MediaGalleryItem(
                        PANEL_HEADER_ATTACHMENT,
                        description="Painel de gerenciamento",
                    )
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            ]
        )

    components.append(
        disnake.ui.TextDisplay(
            f"## {_emoji('settings', _emoji('config', '⚙️'))} Painel de Gerenciamento\n"
            f"Olá senhor(a) **{_user_display_name(inter)}**, {get_salutation()}\n"
            "Aqui você pode **configurar** e **personalizar** as funcionalidades do seu **Lyon Pro**."
        )
    )
    return components


def _home_showcase_text() -> str:
    return (
        f"## {_emoji('rocket', _emoji('sparkles'))} Central de Controle\n"
        "Escolha uma area para configurar o bot sem precisar procurar sistema por sistema.\n\n"
        f"{_emoji('store', _emoji('cart'))} **Vendas & Receita** - loja, rendimentos, gift cards, robux e stock.\n"
        f"{_emoji('settings', _emoji('tools'))} **Operacao** - tickets, middleman, bate ponto, boas-vindas e ApostadoFF.\n"
        f"{_emoji('members', _emoji('users'))} **Comunidade** - Instagram, engajamento, ranking, feedback e sorteios.\n"
        f"{_emoji('shield', _emoji('settings'))} **Administracao** - configuracoes, permissoes, organizador, automacoes, moderacao e verificacao.\n"
        f"{_emoji('cloud', _emoji('link'))} **Integracoes** - FiveM, Lyon IA e Cloud."
    )


def _main_panel_button_rows(button_states: dict) -> list[disnake.ui.ActionRow]:
    return [
        disnake.ui.ActionRow(
            _button("Gerenciar Loja", "Painel_Loja", disnake.ButtonStyle.green, not button_states["loja"], _emoji("store", _emoji("cart"))),
            _button("Gerenciar Ticket", "Painel_Ticket", disnake.ButtonStyle.grey, not button_states["ticket"], _emoji("ticket", _emoji("tag"))),
            _button("Boas Vindas", "Painel_BoasVindas", disnake.ButtonStyle.grey, not button_states["boasvindas"], _emoji("members", _emoji("users"))),
            _button("Personalização", "Painel_Personalizacao", disnake.ButtonStyle.grey, not button_states["personalizacao"], _emoji("paint", _emoji("wand"))),
        ),
        disnake.ui.ActionRow(
            _button("Rendimentos", "Painel_Rendimentos", disnake.ButtonStyle.green, not button_states["rendimentos"], _emoji("rendimentos", _emoji("chart"))),
            _button("Automações", "Painel_Automacoes", disnake.ButtonStyle.grey, not button_states["automacoes"], _emoji("wand", _emoji("reload"))),
            _button("Permissão", "Painel_Protection", disnake.ButtonStyle.grey, not button_states["protection"], _emoji("flag", _emoji("shield"))),
            _button("Sorteio", "Painel_Sorteios", disnake.ButtonStyle.grey, not button_states["sorteios"], _emoji("giveaway", _emoji("gift"))),
        ),
        disnake.ui.ActionRow(
            _button("Configurações", "Painel_Configuracoes", disnake.ButtonStyle.grey, not button_states["configuracoes"], _emoji("settings", _emoji("config"))),
            _button("Parcerias", "Painel_Parcerias", disnake.ButtonStyle.green, not button_states["parcerias"], _emoji("partner", _emoji("link"))),
            _button("Robux", "Painel_Robux", disnake.ButtonStyle.blurple, not button_states["robux"], _emoji("diamond", _emoji("coin"))),
        ),
    ]


def _panel_select_row(button_states: dict, include_main_buttons: bool = False) -> disnake.ui.ActionRow:
    select_options = build_select_options(button_states, include_main_buttons=include_main_buttons)
    return disnake.ui.ActionRow(
        disnake.ui.StringSelect(
            placeholder="Mais sistemas do Lyon Pro",
            custom_id="Painel_Select",
            options=select_options or [
                disnake.SelectOption(label="Nenhum sistema disponivel", value="none", emoji=_emoji("wrong"))
            ],
        )
    )


def _extra_panel_button_rows(button_states: dict) -> list[disnake.ui.ActionRow]:
    buttons = [
        _button("Lyon Cloud", "Painel_Cloud", disnake.ButtonStyle.grey, not button_states.get("cloud", True), _emoji("cloud")),
        _button("Economia", "Painel_Economia", disnake.ButtonStyle.grey, False, _emoji("coin", _emoji("dollar"))),
        _button("Comunidade", "Painel_Comunidade", disnake.ButtonStyle.grey, False, _emoji("members", _emoji("users"))),
        _button("Ferramentas", "Painel_Ferramentas", disnake.ButtonStyle.grey, False, _emoji("hammer", _emoji("tools"))),
        _button("Apostado FF", "Painel_ApostadoFF", disnake.ButtonStyle.blurple, False, _emoji("Uzi")),
        _button("Middleman", "Painel_Middleman", disnake.ButtonStyle.grey, False, _emoji("shield")),
        _button("Gift Cards", "Painel_GiftCard", disnake.ButtonStyle.grey, not button_states.get("giftcard", True), _emoji("gift")),
        _button("Sistema IA", "Painel_SistemaIA", disnake.ButtonStyle.grey, not button_states.get("sistemaai", True), _emoji("robot")),
        _button("Auto Setup", "Painel_AutoSetup", disnake.ButtonStyle.green, not button_states.get("autosetup", True), _emoji("wand", _emoji("settings"))),
        _button("Organizador", "Painel_Organizador", disnake.ButtonStyle.green, not button_states.get("organizador", True), _emoji("settings", _emoji("tools"))),
        _button("Moderação", "Painel_Moderacao", disnake.ButtonStyle.grey, not button_states.get("moderacao", True), _emoji("shield")),
        _button("Verificação", "Painel_Verificacao", disnake.ButtonStyle.grey, not button_states.get("verificacao", True), _emoji("lock")),
        _button("Anti Fraude", "Painel_AntiFraude", disnake.ButtonStyle.grey, not button_states.get("antifraude", True), _emoji("shield")),
        _button("Detector Golpes", "Painel_ScamDetector", disnake.ButtonStyle.grey, not button_states.get("scamdetector", True), _emoji("shield_star", _emoji("shield"))),
        _button("GIFs", "Painel_GIFs", disnake.ButtonStyle.grey, not button_states.get("gifs", True), _emoji("image")),
        _button("Ranking", "Painel_Ranking", disnake.ButtonStyle.grey, not button_states.get("ranking", True), _emoji("trophy")),
        _button("Aviso Stock", "Painel_Stock", disnake.ButtonStyle.grey, not button_states.get("stock", True), _emoji("cardbox")),
        _button("Bate Ponto", "Painel_BatePonto", disnake.ButtonStyle.grey, not button_states.get("bateponto", True), _emoji("clock", _emoji("time"))),
        _button("Feedback", "Painel_Feedback", disnake.ButtonStyle.grey, not button_states.get("feedback", True), _emoji("speech")),
    ]

    rows = []
    for index in range(0, len(buttons), 4):
        rows.append(disnake.ui.ActionRow(*buttons[index:index + 4]))
    return rows


def _panel_action_rows(button_states: dict, layout: str = None) -> list[disnake.ui.ActionRow]:
    layout = normalize_panel_layout(layout or get_panel_layout())
    if layout == "select":
        return [_panel_select_row(button_states, include_main_buttons=True)]

    rows = _main_panel_button_rows(button_states)
    if layout == "buttons":
        rows.append(_panel_select_row(button_states, include_main_buttons=False))
        return rows
    return rows


def _embed_panel_action_rows(button_states: dict, layout: str = None) -> list[disnake.ui.ActionRow]:
    layout = normalize_panel_layout(layout or get_panel_layout())
    if layout == "select":
        return [_panel_select_row(button_states, include_main_buttons=True)]
    if layout == "buttons":
        return _panel_action_rows(button_states, layout)
    return [*_panel_action_rows(button_states, layout), _panel_select_row(button_states)]


def _group_button_rows(group_id: str, button_states: dict) -> list[disnake.ui.ActionRow]:
    group = PANEL_GROUPS.get(group_id)
    if not group:
        return []

    rows = []
    buttons = []
    for label, custom_id, emoji_key, state_key, style in group["items"]:
        disabled = not button_states.get(state_key, True) if state_key else False
        buttons.append(_button(label, custom_id, style, disabled, _emoji(emoji_key)))

    for index in range(0, len(buttons), 3):
        rows.append(disnake.ui.ActionRow(*buttons[index:index + 3]))

    rows.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
    rows.append(
        disnake.ui.ActionRow(
            _button("", "PainelAnterior", disnake.ButtonStyle.grey, False, _emoji("back", _emoji("arrow"))),
            _button("", "PainelInicial", disnake.ButtonStyle.grey, False, _emoji("home", _emoji("house", _emoji("settings")))),
        )
    )
    return rows


def _group_description(group_id: str) -> str:
    descriptions = {
        "PainelGrupo_Vendas": "Tudo que move receita: produtos, saldo, pagamentos indiretos, estoque e pedidos.",
        "PainelGrupo_Operacao": "Rotina da equipe em um lugar so: atendimento, filas, intermediacao e controle de jornada.",
        "PainelGrupo_Comunidade": "Ferramentas para manter a comunidade viva, com social, ranking, feedback e engajamento.",
        "PainelGrupo_Admin": "Configuracoes internas, seguranca, permissao, automacoes e ajustes finos do bot.",
        "PainelGrupo_Integracoes": "Conecte o bot com servicos externos, cidade FiveM, IA e recursos cloud.",
        "PainelGrupo_Mais": "Central por areas para navegar sem poluir o painel principal.",
    }
    return descriptions.get(group_id, "Escolha um sistema abaixo para abrir as configuracoes.")


def PainelComponents(
    inter: disnake.MessageInteraction,
    primary_color_hex: str = None,
    button_states: dict = None,
    show_header_image: bool = False,
    panel_layout: str = None,
) -> list[disnake.ui.Container]:
    button_states = get_panel_button_states(button_states)
    panel_layout = normalize_panel_layout(panel_layout or get_panel_layout())

    container_kwargs = {}

    if primary_color_hex:
        primary_color = int(primary_color_hex.replace("#", ""), 16)
        container_kwargs["accent_colour"] = disnake.Colour(primary_color)

    status_line = (
        f"{_emoji('wifi', '')} **Version:** `{_get_bot_version()}` | "
        f"{_emoji('clock', '')} **Uptime:** `{_format_uptime(inter)}` | "
        f"{_emoji('correct', '✅')} **Sistema:** `Ligado` | "
        f"{_emoji('sparkles', '')} **Ping:** `{_format_ping(inter)}`"
    )
    action_rows = _panel_action_rows(button_states, panel_layout)
    panel_items = [
        *_build_header_components(inter, show_header_image),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        disnake.ui.TextDisplay(status_line),
    ]

    if action_rows:
        panel_items.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
        panel_items.extend(action_rows)

    if panel_layout in {"select", "both"}:
        panel_items.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
        panel_items.append(_panel_select_row(button_states, include_main_buttons=panel_layout == "select"))

    return [disnake.ui.Container(*panel_items, **container_kwargs)]


def PainelGroupComponents(
    inter: disnake.MessageInteraction,
    group_id: str,
    primary_color_hex: str = None,
    button_states: dict = None,
) -> list[disnake.ui.Container]:
    button_states = get_panel_button_states(button_states)
    group = PANEL_GROUPS.get(group_id)
    container_kwargs = {}

    if primary_color_hex:
        primary_color = int(primary_color_hex.replace("#", ""), 16)
        container_kwargs["accent_colour"] = disnake.Colour(primary_color)

    if not group:
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"{_emoji('wrong', '')} Grupo nao encontrado."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    _button("", "PainelAnterior", disnake.ButtonStyle.grey, False, _emoji("back", _emoji("arrow"))),
                    _button("", "PainelInicial", disnake.ButtonStyle.grey, False, _emoji("home", _emoji("house", _emoji("settings")))),
                ),
                **container_kwargs,
            )
        ]

    emoji_value = _emoji(group["emoji"][0], _emoji(group["emoji"][1]))
    panel_items = [
        disnake.ui.TextDisplay(f"## {emoji_value} {group['title']}"),
        disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
        *_group_button_rows(group_id, button_states),
    ]
    return [disnake.ui.Container(*panel_items, **container_kwargs)]


def PainelEmbed(inter: disnake.MessageInteraction, primary_color_hex: str = None, button_states: dict = None, panel_layout: str = None):
    button_states = get_panel_button_states(button_states)
    embed = disnake.Embed(
        title=f"{_emoji('settings', _emoji('config', '⚙️'))} Painel de Gerenciamento",
        description=(
            f"Olá senhor(a) **{_user_display_name(inter)}**, {get_salutation()}\n"
            "Aqui você pode **configurar** e **personalizar** as funcionalidades do seu **Lyon Pro**.\n\n"
            f"{_emoji('wifi', '')} **Version:** `{_get_bot_version()}` | "
            f"{_emoji('clock', '')} **Uptime:** `{_format_uptime(inter)}` | "
            f"{_emoji('correct', '✅')} **Sistema:** `Ligado` | "
            f"{_emoji('sparkles', '')} **Ping:** `{_format_ping(inter)}`"
        ),
    )
    if primary_color_hex:
        embed.color = int(primary_color_hex.replace("#", ""), 16)

    components = _embed_panel_action_rows(button_states, panel_layout)
    return embed, components
