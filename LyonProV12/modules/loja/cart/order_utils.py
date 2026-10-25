import re

from functions.utils import utils


ORDER_PREFIX = "SA"


def normalize_order_reference(value) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""

    text = re.sub(r"^(PEDIDO|ORDER|COMPRA|CARRINHO|ID)\s*#?\s*:?\s*", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def is_public_order_id(value) -> bool:
    normalized = normalize_order_reference(value)
    return bool(normalized and not normalized.isdigit() and len(normalized) >= 6)


def generate_order_id(existing_carts: dict | None = None) -> str:
    existing_refs = set()
    for key, cart in (existing_carts or {}).items():
        existing_refs.add(normalize_order_reference(key))
        if isinstance(cart, dict):
            existing_refs.add(normalize_order_reference(cart.get("order_id")))

    while True:
        suffix = utils.gerar_id(8).upper()
        order_id = f"{ORDER_PREFIX}-{suffix}"
        if normalize_order_reference(order_id) not in existing_refs:
            return order_id


def ensure_cart_order_id(cart: dict, existing_carts: dict | None = None) -> str:
    current = str(cart.get("order_id") or "").strip()
    if is_public_order_id(current):
        return current

    order_id = generate_order_id(existing_carts)
    cart["order_id"] = order_id
    return order_id


def order_id_for_cart(cart: dict | None, fallback=None) -> str:
    cart = cart or {}
    current = str(cart.get("order_id") or "").strip()
    if is_public_order_id(current):
        return current

    fallback_text = str(fallback or cart.get("cart_id") or cart.get("thread_id") or "N/A").strip()
    return fallback_text or "N/A"


def reference_matches(value, reference: str) -> bool:
    expected = normalize_order_reference(reference)
    return bool(expected and normalize_order_reference(value) == expected)
