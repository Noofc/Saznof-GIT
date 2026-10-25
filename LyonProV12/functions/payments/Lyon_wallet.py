"""Lyon Wallet temporariamente desativada.

Este provider fica como stub para manter compatibilidade com imports antigos,
sem pedir API Key e sem chamar endpoint externo da carteira.
"""

DISABLED_MESSAGE = "Lyon Wallet esta desativada temporariamente. Use PIX manual, IMAP ou outro gateway."


def _disabled_payload(**extra):
    data = {"status": "disabled", "paid": False, "approved": False, "message": DISABLED_MESSAGE}
    data.update(extra)
    return data


def _raise_disabled(*args, **kwargs):
    raise RuntimeError(DISABLED_MESSAGE)


def _get_Lyon_pay_url(*args, **kwargs):
    return ""


def _sanitize_error_message(error):
    return DISABLED_MESSAGE


async def _request(*args, **kwargs):
    return _disabled_payload()


def _load_config():
    return {}


def _require(*args, **kwargs):
    return None


def _get_api_key(*args, **kwargs):
    return None


async def create_Lyon_payment(*args, **kwargs):
    _raise_disabled()


async def check_Lyon_payment(*args, **kwargs):
    return _disabled_payload()


async def list_Lyon_payments(*args, **kwargs):
    return []


async def cancel_Lyon_payment(*args, **kwargs):
    return _disabled_payload(cancelled=False)


async def refund_Lyon_payment(*args, **kwargs):
    return _disabled_payload(refunded=False)


async def create_Lyon_withdraw(*args, **kwargs):
    _raise_disabled()


async def get_Lyon_withdraw(*args, **kwargs):
    return _disabled_payload()


async def list_Lyon_withdraws(*args, **kwargs):
    return []


async def register_Lyon_user(*args, **kwargs):
    return _disabled_payload()


async def get_Lyon_user(*args, **kwargs):
    return _disabled_payload()


async def update_Lyon_user(*args, **kwargs):
    return _disabled_payload()


async def get_Lyon_balance(*args, **kwargs):
    return {"status": "disabled", "balance": 0, "available": 0, "message": DISABLED_MESSAGE}


async def create_Lyon_payment_from_settings(*args, **kwargs):
    _raise_disabled()


async def check_Lyon_payment_from_settings(*args, **kwargs):
    return _disabled_payload()


async def list_Lyon_payments_from_settings(*args, **kwargs):
    return []


async def cancel_Lyon_payment_from_settings(*args, **kwargs):
    return _disabled_payload(cancelled=False)


async def refund_Lyon_payment_from_settings(*args, **kwargs):
    return _disabled_payload(refunded=False)


async def create_Lyon_withdraw_from_settings(*args, **kwargs):
    _raise_disabled()


async def get_Lyon_withdraw_from_settings(*args, **kwargs):
    return _disabled_payload()


async def list_Lyon_withdraws_from_settings(*args, **kwargs):
    return []


async def get_Lyon_user_from_settings(*args, **kwargs):
    return _disabled_payload()


async def update_Lyon_user_from_settings(*args, **kwargs):
    return _disabled_payload()


async def get_Lyon_balance_from_settings(*args, **kwargs):
    return {"status": "disabled", "balance": 0, "available": 0, "message": DISABLED_MESSAGE}


async def create_wallet_payment_from_settings(*args, **kwargs):
    _raise_disabled()


async def check_wallet_payment_from_settings(*args, **kwargs):
    return _disabled_payload()
