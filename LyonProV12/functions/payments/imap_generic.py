import asyncio
import email
import imaplib
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Any, Dict, List, Optional

from functions.database import database as db
from modules.loja.personalization.qr_customization import QRCodeGenerator
from .manual_payment import _generate_pix_payload


PROVIDERS = {
    "picpay_imap": {
        "label": "PicPay",
        "keywords": ["picpay", "pix"],
    },
    "itau_imap": {
        "label": "Itau",
        "keywords": ["itau", "itaú", "pix"],
    },
}


def _load_config() -> dict:
    return db.get_document("payment_configs") or {}


def _pending_doc() -> Dict[str, Any]:
    return db.get_document("bank_imap_pending_payments") or {}


def _save_pending(data: Dict[str, Any]) -> None:
    db.save_document("bank_imap_pending_payments", {}, data)


def _clean_txid(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:25]


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = []
    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            parts.append(part.decode(encoding or "utf-8", errors="ignore"))
        else:
            parts.append(str(part))
    return "".join(parts)


def _body_from_message(msg: email.message.Message) -> str:
    if msg.is_multipart():
        chunks = []
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition:
                continue
            if content_type in {"text/plain", "text/html"}:
                payload = part.get_payload(decode=True)
                if payload:
                    chunks.append(payload.decode("utf-8", errors="ignore"))
        return "\n".join(chunks)
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8", errors="ignore") if payload else ""


def _parse_money(text: str) -> Optional[float]:
    patterns = [
        r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"R\$\s*(\d+(?:,\d{2})?)",
        r"(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"(\d+,\d{2})",
        r"(\d+\.\d{2})",
    ]
    values = []
    for pattern in patterns:
        values.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    for raw in values:
        value = str(raw)
        if "." in value and "," in value:
            value = value.replace(".", "").replace(",", ".")
        elif "," in value:
            value = value.replace(",", ".")
        try:
            amount = float(value)
            if amount > 0:
                return amount
        except Exception:
            continue
    return None


def _parse_txid(text: str) -> Optional[str]:
    patterns = [
        r"txid[:\s#-]*([A-Za-z0-9]{8,32})",
        r"identificador[:\s#-]*([A-Za-z0-9]{8,32})",
        r"codigo[:\s#-]*([A-Za-z0-9]{8,32})",
        r"código[:\s#-]*([A-Za-z0-9]{8,32})",
        r"id[:\s#-]*([A-Za-z0-9]{8,32})",
        r"E2E[:\s#-]*([A-Za-z0-9]{8,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_txid(match.group(1))
    return None


def _scan_gmail(provider_key: str, email_address: str, password: str) -> List[Dict[str, Any]]:
    provider = PROVIDERS.get(provider_key) or {"keywords": ["pix"]}
    keywords = [keyword.lower() for keyword in provider.get("keywords", [])]
    found: List[Dict[str, Any]] = []
    mail = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email_address, password)
        mail.select("INBOX")
        since = (datetime.utcnow() - timedelta(days=7)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{since}")')
        if status != "OK" or not messages or not messages[0]:
            return found
        ids = messages[0].split()[-80:]
        for mail_id in reversed(ids):
            status, msg_data = mail.fetch(mail_id, "(BODY.PEEK[])")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)
            subject = _decode_header(msg.get("Subject", ""))
            sender = _decode_header(msg.get("From", ""))
            body = _body_from_message(msg)
            haystack = f"{subject}\n{sender}\n{body}".lower()
            if "pix" not in haystack:
                continue
            if keywords and not any(keyword in haystack for keyword in keywords):
                continue
            amount = _parse_money(haystack)
            if amount is None:
                continue
            found.append(
                {
                    "amount": amount,
                    "txid": _parse_txid(haystack),
                    "email_id": mail_id.decode(errors="ignore") if isinstance(mail_id, bytes) else str(mail_id),
                    "subject": subject,
                    "received_at": datetime.utcnow().isoformat(),
                }
            )
    finally:
        if mail:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass
    return found


async def create_imap_pix_payment_from_settings(
    provider_key: str,
    amount: float,
    cart_id: str,
    description: Optional[str] = None,
    merchant_name: str = "Loja",
    merchant_city: str = "Sao Paulo",
) -> Dict[str, Any]:
    config = _load_config()
    provider_config = config.get(provider_key) or {}
    if not provider_config.get("enabled"):
        raise ValueError(f"{provider_key} nao esta habilitado")
    pix_key = provider_config.get("pix_key")
    if not pix_key:
        raise ValueError("Chave PIX nao configurada")

    payment_id = _clean_txid(cart_id) or _clean_txid(str(uuid.uuid4()))
    pix_payload = _generate_pix_payload(
        pix_key=pix_key,
        merchant_name=merchant_name,
        merchant_city=merchant_city,
        amount=amount,
        transaction_id=payment_id,
        pix_key_type=provider_config.get("pix_key_type"),
        description=description,
    )
    try:
        qr_bytes = await QRCodeGenerator.generate_custom_qr(pix_payload)
    except Exception:
        qr_bytes = await QRCodeGenerator.generate_simple_qr(pix_payload)

    pending = _pending_doc()
    pending[payment_id] = {
        "provider": provider_key,
        "payment_id": payment_id,
        "cart_id": cart_id,
        "txid": payment_id,
        "status": "pending",
        "amount": amount,
        "description": description,
        "created_at": datetime.utcnow().isoformat(),
    }
    _save_pending(pending)

    return {
        "payment_id": payment_id,
        "id": payment_id,
        "txid": payment_id,
        "status": "pending",
        "amount": amount,
        "currency": "BRL",
        "pix_copia_cola": pix_payload,
        "copy_paste": pix_payload,
        "emv": pix_payload,
        "qr_code_bytes": qr_bytes,
        "payment_method": provider_key,
        "requires_manual_approval": False,
        "imap_monitored": True,
    }


async def check_imap_pix_payment_from_settings(provider_key: str, payment_id: str) -> Dict[str, Any]:
    payment_id = _clean_txid(payment_id)
    pending = _pending_doc()
    payment = pending.get(payment_id)
    if not payment:
        return {"payment_id": payment_id, "status": "not_found", "payment_status": "not_found"}
    if payment.get("status") == "approved":
        return {
            "payment_id": payment_id,
            "status": "approved",
            "payment_status": "approved",
            "amount": payment.get("amount"),
            "approved_at": payment.get("approved_at"),
        }

    config = _load_config()
    provider_config = config.get(provider_key) or {}
    email_address = provider_config.get("email")
    password = provider_config.get("password")
    if not email_address or not password:
        return {"payment_id": payment_id, "status": "pending", "payment_status": "pending"}

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        detected = await loop.run_in_executor(executor, _scan_gmail, provider_key, email_address, password)

    expected_amount = float(payment.get("amount") or 0)
    for item in detected:
        detected_txid = _clean_txid(item.get("txid"))
        detected_amount = float(item.get("amount") or 0)
        txid_matches = detected_txid and detected_txid == payment_id
        amount_matches = expected_amount > 0 and abs(detected_amount - expected_amount) < 0.01
        if txid_matches or amount_matches:
            payment["status"] = "approved"
            payment["approved_at"] = datetime.utcnow().isoformat()
            payment["detected_amount"] = detected_amount
            payment["detected_txid"] = detected_txid
            pending[payment_id] = payment
            _save_pending(pending)
            return {
                "payment_id": payment_id,
                "status": "approved",
                "payment_status": "approved",
                "amount": detected_amount or expected_amount,
                "approved_at": payment["approved_at"],
            }

    return {"payment_id": payment_id, "status": "pending", "payment_status": "pending", "amount": expected_amount}


async def create_picpay_imap_payment_from_settings(amount: float, cart_id: str, description: Optional[str] = None) -> Dict[str, Any]:
    return await create_imap_pix_payment_from_settings("picpay_imap", amount, cart_id, description)


async def check_picpay_imap_payment_from_settings(payment_id: str) -> Dict[str, Any]:
    return await check_imap_pix_payment_from_settings("picpay_imap", payment_id)


async def create_itau_imap_payment_from_settings(amount: float, cart_id: str, description: Optional[str] = None) -> Dict[str, Any]:
    return await create_imap_pix_payment_from_settings("itau_imap", amount, cart_id, description)


async def check_itau_imap_payment_from_settings(payment_id: str) -> Dict[str, Any]:
    return await check_imap_pix_payment_from_settings("itau_imap", payment_id)


__all__ = [
    "create_imap_pix_payment_from_settings",
    "check_imap_pix_payment_from_settings",
    "create_picpay_imap_payment_from_settings",
    "check_picpay_imap_payment_from_settings",
    "create_itau_imap_payment_from_settings",
    "check_itau_imap_payment_from_settings",
]
