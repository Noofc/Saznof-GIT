from disnake.ext import commands

from functions.plan import should_load_command, should_load_module

from . import contextmenus, extensions, giveaways, tickets, vendas
from .admin import (
    anunciar,
    antifraude,
    apostadoff,
    auto_setup,
    backup,
    bateponto,
    boasvindas,
    comunidade,
    economia,
    feedback,
    ferramentas,
    filasapostas,
    fivem_system,
    function_payment,
    gifs,
    giftcard,
    keys,
    middleman,
    moderacao,
    painel,
    parcerias,
    ranking,
    robux,
    scam_detector,
    server_organizer,
    sistemaai,
    social_systems,
    stock,
    verificacao,
)
from .mod import mod
from modules import conversor, twitter


COMMANDS_BY_PLAN = (
    ("anunciar", anunciar.setup),
    ("painel", painel.setup),
    ("function_payment", function_payment.setup),
    ("mod", mod.setup),
    ("tickets", tickets.setup),
    ("backup", backup.setup),
    ("contextmenus", contextmenus.setup),
    ("giveaways", giveaways.setup),
)

ALWAYS_ACTIVE_ADMIN = (
    economia.setup,
    bateponto.setup,
    parcerias.setup,
    apostadoff.setup,
    comunidade.setup,
    ferramentas.setup,
    boasvindas.setup,
    giftcard.setup,
    keys.setup,
    conversor.setup,
    twitter.setup,
    sistemaai.setup,
    filasapostas.setup,
    middleman.setup,
    moderacao.setup,
    verificacao.setup,
    gifs.setup,
    ranking.setup,
    robux.setup,
    social_systems.setup,
    stock.setup,
    antifraude.setup,
    scam_detector.setup,
    server_organizer.setup,
    auto_setup.setup,
    feedback.setup,
    fivem_system.setup,
)


def setup(bot: commands.Bot):
    for plan_key, setup_func in COMMANDS_BY_PLAN:
        if should_load_command(plan_key):
            setup_func(bot)

    if should_load_module("loja"):
        vendas.setup(bot)

    for setup_func in ALWAYS_ACTIVE_ADMIN:
        setup_func(bot)

    extensions.setup(bot)
