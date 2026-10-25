import importlib

from functions.plan import should_load_module


MODULES_BY_PLAN = (
    ("automations", "modules.automations"),
    ("customization", "modules.customization"),
    ("loja", "modules.loja"),
    ("rendimentos", "modules.rendimentos"),
    ("protection", "modules.protection"),
    ("settings", "modules.settings"),
    ("tickets", "modules.tickets"),
    ("giveaways", "modules.giveaways"),
    ("cloud", "modules.cloud"),
)

ALWAYS_ACTIVE_MODULES = ()


def _setup_module(module_path: str, bot):
    module = importlib.import_module(module_path)
    module.setup(bot)


def setup(bot):
    for plan_key, module_path in MODULES_BY_PLAN:
        if should_load_module(plan_key):
            _setup_module(module_path, bot)

    for module_path in ALWAYS_ACTIVE_MODULES:
        _setup_module(module_path, bot)


__all__ = ["setup"]
