from __future__ import annotations

from datetime import datetime

import disnake

from functions.database import database as db
from functions.emoji import emoji
from functions.system_logs import send_system_log


DOC_KEY = "antifraud_config"


def _now_ts() -> int:
    return int(datetime.utcnow().timestamp())


def _default_config() -> dict:
    return {
        "enabled": True,
        "min_account_age_days": 3,
        "max_attempts_per_hour": 6,
        "max_pending_carts": 2,
        "auto_close_old_carts": True,
        "open_cart_timeout_minutes": 30,
        "pending_cart_timeout_minutes": 15,
        "manual_pending_cart_timeout_minutes": 1440,
        "block_blacklisted": True,
        "log_channel_id": "",
        "blacklist": {},
        "attempts": {},
        "last_denied": [],
        "last_auto_closed": [],
    }


def load_config() -> dict:
    config = db.get_document(DOC_KEY) or {}
    if not isinstance(config, dict):
        config = {}
    defaults = _default_config()
    changed = False
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
            changed = True
    if changed:
        db.save_document(DOC_KEY, config)
    return config


def save_config(config: dict) -> None:
    db.save_document(DOC_KEY, config)


def _account_age_days(user: disnake.User) -> int:
    created_at = getattr(user, "created_at", None)
    if not created_at:
        return 9999
    now = disnake.utils.utcnow()
    if created_at.tzinfo is None and now.tzinfo is not None:
        created_at = created_at.replace(tzinfo=now.tzinfo)
    return max(int((now - created_at).total_seconds() // 86400), 0)


def _cart_created_at(cart: dict, now: int) -> int:
    try:
        return int(cart.get("created_at") or cart.get("updated_at") or now)
    except (TypeError, ValueError):
        return now


def _is_manual_payment_cart(cart: dict) -> bool:
    payment_method = str(cart.get("payment_method") or "").lower()
    if payment_method == "pix_manual":
        return True

    payment_data = cart.get("payment_data") if isinstance(cart.get("payment_data"), dict) else {}
    local_data = payment_data.get("local") if isinstance(payment_data.get("local"), dict) else {}
    raw_data = payment_data.get("raw") if isinstance(payment_data.get("raw"), dict) else {}
    return bool(local_data.get("requires_manual_approval") or raw_data.get("requires_manual_approval"))


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _cart_timeout_minutes(cart: dict, status: str, config: dict | None = None) -> int:
    config = config or load_config()
    if status == "pending":
        if _is_manual_payment_cart(cart):
            return max(_safe_int(config.get("manual_pending_cart_timeout_minutes"), 1440), 30)
        return max(_safe_int(config.get("pending_cart_timeout_minutes"), 15), 5)

    if status == "cart":
        return max(_safe_int(config.get("open_cart_timeout_minutes"), 30), 5)

    return 0


def _cart_is_expired(cart: dict, status: str, now: int, config: dict | None = None) -> bool:
    age = now - _cart_created_at(cart, now)
    if age < 0:
        return False

    timeout_minutes = _cart_timeout_minutes(cart, status, config)
    if timeout_minutes <= 0:
        return False

    return age > timeout_minutes * 60


def _cart_age_minutes(cart: dict, now: int) -> int:
    return max(int((now - _cart_created_at(cart, now)) // 60), 0)


async def _cart_thread_exists(cart: dict, *, bot=None, guild=None) -> bool:
    thread_id = cart.get("thread_id") or cart.get("cart_id")
    if not thread_id:
        return False

    check_guild = guild
    if not check_guild and bot and cart.get("guild_id"):
        try:
            check_guild = bot.get_guild(int(cart.get("guild_id")))
        except Exception:
            check_guild = None

    if not check_guild:
        return True

    try:
        thread = check_guild.get_thread(int(thread_id))
        if thread:
            return True
        fetched = await check_guild.fetch_channel(int(thread_id))
        return isinstance(fetched, disnake.Thread)
    except (disnake.NotFound, disnake.Forbidden):
        return False
    except Exception:
        return True


async def _fetch_cart_thread(cart: dict, *, bot=None, guild=None):
    thread_id = cart.get("thread_id") or cart.get("cart_id")
    if not thread_id:
        return None

    check_guild = guild
    if not check_guild and bot and cart.get("guild_id"):
        try:
            check_guild = bot.get_guild(int(cart.get("guild_id")))
        except Exception:
            check_guild = None

    if not check_guild:
        return None

    try:
        thread = check_guild.get_thread(int(thread_id))
        if thread:
            return thread
        fetched = await check_guild.fetch_channel(int(thread_id))
        return fetched if isinstance(fetched, disnake.Thread) else None
    except (disnake.NotFound, disnake.Forbidden):
        return None
    except Exception:
        return None


async def _cancel_payment_if_possible(cart: dict) -> None:
    payment_data = cart.get("payment_data") if isinstance(cart.get("payment_data"), dict) else {}
    provider_data = payment_data.get("provider") if isinstance(payment_data.get("provider"), dict) else {}
    payment_provider = provider_data.get("name") or payment_data.get("payment_provider")

    if payment_provider != "Lyon_wallet":
        return

    try:
        from functions.payments.Lyon_wallet import cancel_Lyon_payment_from_settings

        raw_data = payment_data.get("raw") if isinstance(payment_data.get("raw"), dict) else {}
        raw_provider = provider_data.get("raw_response") if isinstance(provider_data.get("raw_response"), dict) else {}
        payment_id = (
            provider_data.get("payment_id")
            or provider_data.get("correlation_id")
            or raw_provider.get("paymentId")
            or raw_provider.get("payment_id")
            or raw_provider.get("id")
            or raw_data.get("paymentId")
            or raw_data.get("payment_id")
            or raw_data.get("id")
            or payment_data.get("payment_id")
        )
        if payment_id:
            await cancel_Lyon_payment_from_settings(payment_id)
    except Exception:
        pass


async def _send_expired_cart_notice(bot, cart: dict, reason: str, *, thread=None) -> None:
    user_id = cart.get("user_id")
    if not user_id or not bot:
        return

    try:
        user = bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
    except Exception:
        user = None
    if not user:
        return

    try:
        cart_url = ""
        guild_id = cart.get("guild_id")
        thread_id = cart.get("thread_id") or cart.get("cart_id")
        if guild_id and thread_id:
            cart_url = f"https://discord.com/channels/{guild_id}/{thread_id}"

        await user.send(
            f"{getattr(emoji, 'warn', '')} **Carrinho fechado automaticamente**\n"
            f"Motivo: `{reason}`\n"
            f"Carrinho: `{thread_id or 'N/A'}`"
            + (f"\nLink antigo: {cart_url}" if cart_url else "")
        )
    except Exception:
        pass


async def _close_cart_record(
    bot,
    cart_id: str,
    cart: dict,
    *,
    reason: str,
    config: dict,
    guild=None,
    notify_user: bool = True,
) -> dict:
    thread = await _fetch_cart_thread(cart, bot=bot, guild=guild)
    now = _now_ts()

    cart["status"] = "expired"
    cart["expired_at"] = now
    cart["closed_by"] = "antifraud"
    cart["close_reason"] = reason
    cart["updated_at"] = now

    await _cancel_payment_if_possible(cart)

    if thread:
        try:
            await thread.send(
                f"{getattr(emoji, 'warn', '')} **Carrinho fechado automaticamente pelo Anti Fraude.**\n"
                f"Motivo: `{reason}`"
            )
        except Exception:
            pass

        try:
            from modules.loja.preferences.generate_transcript import generate_cart_transcript, send_cart_transcript_to_channel

            prefs = db.get_document("loja_preferences") or {}
            transcript_channel_id = prefs.get("transcript_channel_id") if prefs.get("transcript_enabled", False) else None
            if transcript_channel_id:
                transcript_file = await generate_cart_transcript(thread, bot, cart)
                if transcript_file:
                    await send_cart_transcript_to_channel(bot, transcript_file, int(transcript_channel_id), cart)
        except Exception:
            pass

        try:
            await thread.delete()
        except (disnake.NotFound, disnake.Forbidden):
            pass
        except Exception:
            pass

    if notify_user:
        await _send_expired_cart_notice(bot, cart, reason, thread=thread)

    await _send_log(
        bot,
        guild,
        config,
        f"{getattr(emoji, 'shield', getattr(emoji, 'warn', ''))} **Carrinho fechado pelo Anti Fraude**\n"
        f"Carrinho: `{cart_id}`\n"
        f"Usuario: <@{cart.get('user_id')}> (`{cart.get('user_id')}`)\n"
        f"Status anterior: `{cart.get('status_before_close', 'desconhecido')}`\n"
        f"Motivo: `{reason}`",
    )
    return cart


async def close_expired_carts(
    bot=None,
    guild=None,
    *,
    user_id: int | str | None = None,
    force: bool = False,
    limit: int = 50,
    notify_user: bool = True,
) -> dict:
    config = load_config()
    if not force and (not config.get("enabled", True) or not config.get("auto_close_old_carts", True)):
        return {"closed": 0, "removed": 0, "checked": 0}

    loja_data = db.get_document("loja_data") or {}
    carts = loja_data.get("carts") if isinstance(loja_data.get("carts"), dict) else {}
    if not carts:
        return {"closed": 0, "removed": 0, "checked": 0}

    now = _now_ts()
    closed = 0
    removed = 0
    checked = 0
    closed_log = []
    guild_id = getattr(guild, "id", None)

    for cart_id, cart in list(carts.items()):
        if closed >= max(limit, 1):
            break
        if not isinstance(cart, dict):
            continue
        if user_id and str(cart.get("user_id")) != str(user_id):
            continue
        if guild_id and str(cart.get("guild_id")) != str(guild_id):
            continue

        status = str(cart.get("status") or "").lower()
        if status not in {"cart", "pending"}:
            continue

        checked += 1
        reason = ""
        if _cart_is_expired(cart, status, now, config):
            reason = f"aberto ha {_cart_age_minutes(cart, now)} minuto(s)"
        elif not await _cart_thread_exists(cart, bot=bot, guild=guild):
            reason = "topico do carrinho nao existe mais"
        else:
            continue

        cart["status_before_close"] = status
        closed_cart = await _close_cart_record(
            bot,
            str(cart_id),
            cart,
            reason=reason,
            config=config,
            guild=guild,
            notify_user=notify_user,
        )
        carts.pop(cart_id, None)
        closed += 1
        removed += 1
        closed_log.append(
            {
                "cart_id": str(cart_id),
                "user_id": str(closed_cart.get("user_id") or ""),
                "status": status,
                "reason": reason,
                "closed_at": now,
            }
        )

    if removed:
        loja_data["carts"] = carts
        db.save_document("loja_data", loja_data)
        history = config.setdefault("last_auto_closed", [])
        history.extend(closed_log)
        config["last_auto_closed"] = history[-30:]
        save_config(config)

    return {"closed": closed, "removed": removed, "checked": checked}


async def _pending_cart_count(
    user_id: int | str,
    *,
    guild_id: int | str | None = None,
    bot=None,
    guild=None,
    ignore_cart_id: int | str | None = None,
) -> int:
    loja_data = db.get_document("loja_data") or {}
    carts = loja_data.get("carts") if isinstance(loja_data.get("carts"), dict) else {}
    config = load_config()
    if bot:
        if config.get("auto_close_old_carts", True):
            await close_expired_carts(bot, guild, user_id=user_id, limit=10, notify_user=False)
            loja_data = db.get_document("loja_data") or {}
            carts = loja_data.get("carts") if isinstance(loja_data.get("carts"), dict) else {}
    count = 0
    stale_cart_ids = []
    now = _now_ts()

    for cart_id, cart in list(carts.items()):
        if not isinstance(cart, dict):
            continue
        if ignore_cart_id and str(cart_id) == str(ignore_cart_id):
            continue
        if str(cart.get("user_id")) != str(user_id):
            continue
        if guild_id and str(cart.get("guild_id")) != str(guild_id):
            continue

        status = str(cart.get("status") or "").lower()
        if status not in {"cart", "pending"}:
            continue

        if _cart_is_expired(cart, status, now, config):
            stale_cart_ids.append(cart_id)
            continue

        if not await _cart_thread_exists(cart, bot=bot, guild=guild):
            stale_cart_ids.append(cart_id)
            continue

        count += 1

    if stale_cart_ids:
        latest_data = db.get_document("loja_data") or loja_data
        latest_carts = latest_data.get("carts") if isinstance(latest_data.get("carts"), dict) else {}
        changed = False
        for cart_id in stale_cart_ids:
            if cart_id in latest_carts:
                latest_carts.pop(cart_id, None)
                changed = True
        if changed:
            latest_data["carts"] = latest_carts
            db.save_document("loja_data", latest_data)

    return count


def _prune_attempts(config: dict) -> None:
    cutoff = _now_ts() - 3600
    attempts = config.setdefault("attempts", {})
    for user_id, entries in list(attempts.items()):
        clean = [int(ts) for ts in entries if int(ts or 0) >= cutoff]
        if clean:
            attempts[user_id] = clean[-50:]
        else:
            attempts.pop(user_id, None)


async def _send_log(bot, guild, config: dict, text: str) -> None:
    if not bot or not guild:
        return
    await send_system_log(
        bot,
        guild,
        title="Anti Fraude",
        description=text,
        system="Anti Fraude",
        config=config,
        channel_id=config.get("log_channel_id"),
    )


async def check_purchase(
    inter: disnake.Interaction,
    *,
    amount: float = 0,
    action: str = "checkout",
    ignore_cart_id: int | str | None = None,
) -> tuple[bool, str]:
    config = load_config()
    if not config.get("enabled", True):
        return True, ""

    user = getattr(inter, "user", None) or getattr(inter, "author", None)
    if not user:
        return True, ""

    _prune_attempts(config)
    user_id = str(user.id)
    reasons = []

    if config.get("block_blacklisted", True) and user_id in (config.get("blacklist") or {}):
        reason = (config.get("blacklist") or {}).get(user_id, {}).get("reason") or "usuario bloqueado"
        reasons.append(f"bloqueado: {reason}")

    min_age = int(config.get("min_account_age_days", 0) or 0)
    age_days = _account_age_days(user)
    if min_age > 0 and age_days < min_age:
        reasons.append(f"conta com {age_days} dia(s), minimo {min_age}")

    max_pending = int(config.get("max_pending_carts", 0) or 0)
    guild = getattr(inter, "guild", None)
    bot = getattr(inter, "bot", None) or getattr(inter, "client", None)
    pending_count = await _pending_cart_count(
        user.id,
        guild_id=getattr(guild, "id", None),
        bot=bot,
        guild=guild,
        ignore_cart_id=ignore_cart_id,
    )
    if max_pending > 0 and pending_count >= max_pending:
        reasons.append(f"{pending_count} carrinho(s) em aberto")

    attempts = config.setdefault("attempts", {}).setdefault(user_id, [])
    max_attempts = int(config.get("max_attempts_per_hour", 0) or 0)
    if max_attempts > 0 and len(attempts) >= max_attempts:
        reasons.append(f"{len(attempts)} tentativa(s) na ultima hora")

    attempts.append(_now_ts())
    attempts[:] = attempts[-50:]

    if reasons:
        denied = config.setdefault("last_denied", [])
        denied.append(
            {
                "user_id": user_id,
                "user": str(user),
                "amount": float(amount or 0),
                "action": action,
                "reasons": reasons,
                "created_at": _now_ts(),
            }
        )
        config["last_denied"] = denied[-30:]
        save_config(config)
        await _send_log(
            getattr(inter, "bot", None) or getattr(inter, "client", None),
            getattr(inter, "guild", None),
            config,
            f"{getattr(emoji, 'shield', getattr(emoji, 'warn', ''))} **Compra bloqueada pelo Anti Fraude**\n"
            f"Usuario: {user.mention} (`{user_id}`)\n"
            f"Valor: `{amount}`\n"
            f"Acao: `{action}`\n"
            f"Motivos: `{'; '.join(reasons)}`",
        )
        return False, f"{emoji.wrong} Compra bloqueada pelo Anti Fraude: {'; '.join(reasons)}."

    save_config(config)
    return True, ""
