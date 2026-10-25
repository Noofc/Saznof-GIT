def create_bot(*args, **kwargs):
    from .create_bot import create_bot as func

    return func(*args, **kwargs)


def change_bio(*args, **kwargs):
    from .change_bio import change_bio as func

    return func(*args, **kwargs)


def change_status(*args, **kwargs):
    from .change_status import change_status as func

    return func(*args, **kwargs)


def log_restart(*args, **kwargs):
    from .log_restart import log_restart as func

    return func(*args, **kwargs)


def enable_intents(*args, **kwargs):
    from .enable_intents import enable_intents as func

    return func(*args, **kwargs)


__all__ = [
    "create_bot",
    "change_bio",
    "change_status",
    "log_restart",
    "enable_intents",
]
