import smtplib
import ssl
import hashlib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functions.database import database as db
import re


OWNER_EMAIL_DOCUMENT = "owner_email_security"
OWNER_EMAIL_SALT = "LyonPro.owner-email.v1"
OWNER_EMAIL_PROOF_TTL_SECONDS = 30 * 24 * 60 * 60


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()

def is_valid_email(email: str) -> bool:
    """Valida se uma string é um email válido."""
    email = normalize_email(email)
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def mask_email(email: str, unavailable: str = "Nao disponivel") -> str:
    """Retorna um email mascarado para exibicao em paineis/logs."""
    email = normalize_email(email)
    if not email:
        return unavailable
    if "@" not in email:
        return "Protegido"

    local, domain = email.split("@", 1)
    if not local or not domain:
        return "Protegido"

    local_keep = 1 if len(local) <= 2 else 2
    masked_local = f"{local[:local_keep]}***"

    domain_parts = domain.split(".")
    host = domain_parts[0] if domain_parts else ""
    suffix = "." + ".".join(domain_parts[1:]) if len(domain_parts) > 1 else ""
    masked_host = f"{host[:1]}***" if host else "***"
    return f"{masked_local}@{masked_host}{suffix}"


def mask_possible_email(value: str, unavailable: str = "Nao disponivel") -> str:
    text = str(value or "").strip()
    return mask_email(text, unavailable=unavailable) if is_valid_email(text) else text


def hash_email(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized:
        return ""
    payload = f"{OWNER_EMAIL_SALT}:{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_config_owner_id() -> str:
    try:
        config = db.obter("config.json") or {}
        return str((config.get("bot") or {}).get("owner") or "")
    except Exception:
        return ""


def is_config_owner(user_id) -> bool:
    owner_id = get_config_owner_id()
    return bool(owner_id) and str(user_id) == owner_id


def get_owner_email_status() -> dict:
    data = db.get_document(OWNER_EMAIL_DOCUMENT) or {}
    if not isinstance(data, dict):
        return {}
    data.pop("email", None)
    data.pop("raw_email", None)
    return data


def mark_owner_email_verified(user_id, email: str, source: str = "cloud_auth") -> bool:
    if not is_config_owner(user_id) or not is_valid_email(email):
        return False

    now = int(time.time())
    current = get_owner_email_status()
    current.update({
        "owner_id": str(user_id),
        "email_hash": hash_email(email),
        "email_masked": mask_email(email),
        "verified": True,
        "authorized_holder_id": str(user_id),
        "holder_verified_at": now,
        "last_verified_at": now,
        "last_seen_at": now,
        "source": source,
    })
    db.save_document(OWNER_EMAIL_DOCUMENT, current)
    return True


def try_verify_owner_email_from_auth(user_id, email: str) -> bool:
    """Marca quem possui o email do owner quando o OAuth/Cloud confirma a conta."""
    if not is_valid_email(email):
        return False

    if is_config_owner(user_id):
        return mark_owner_email_verified(user_id, email, source="cloud_auth")

    data = get_owner_email_status()
    email_hash = hash_email(email)
    if data.get("email_hash") != email_hash:
        return False

    now = int(time.time())
    data.update({
        "authorized_holder_id": str(user_id),
        "holder_verified_at": now,
        "last_seen_at": now,
        "source": "cloud_auth_holder",
    })
    db.save_document(OWNER_EMAIL_DOCUMENT, data)
    return True


def owner_email_is_verified(user_id, max_age_seconds: int = OWNER_EMAIL_PROOF_TTL_SECONDS) -> bool:
    data = get_owner_email_status()
    if not data.get("verified") or not data.get("email_hash"):
        return False

    user_id_str = str(user_id)
    owner_id = get_config_owner_id()
    holder_id = str(data.get("authorized_holder_id") or "")

    if user_id_str == owner_id:
        verified_at = int(data.get("last_verified_at") or 0)
    elif holder_id and user_id_str == holder_id:
        verified_at = int(data.get("holder_verified_at") or 0)
    else:
        return False

    if not verified_at:
        return False
    if max_age_seconds and verified_at and int(time.time()) - verified_at > max_age_seconds:
        return False
    return True

async def send_notification_email(subject: str, body_text: str, body_html: str = None):
    """
    Envia um email de notificação baseado nas configurações do banco de dados.
    """
    config = db.get_document("notifications_email_config")
    if not config or not config.get("enabled"):
        return False, "Notificações por email desativadas."

    dest_email = config.get("email")
    smtp_server = config.get("smtp_server")
    smtp_port = config.get("smtp_port")
    smtp_user = config.get("smtp_user")
    smtp_pass = config.get("smtp_pass")

    if not all([dest_email, smtp_server, smtp_port, smtp_user, smtp_pass]):
        return False, "Configurações de SMTP incompletas."

    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = smtp_user
        message["To"] = dest_email

        # Adicionar parte texto
        part1 = MIMEText(body_text, "plain")
        message.attach(part1)

        # Adicionar parte HTML se fornecida
        if body_html:
            part2 = MIMEText(body_html, "html")
            message.attach(part2)

        context = ssl.create_default_context()
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if config.get("use_tls", True):
                server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, dest_email, message.as_string())
            
        return True, "Email enviado com sucesso."
    except Exception as e:
        return False, f"Erro ao enviar email: {str(e)}"
