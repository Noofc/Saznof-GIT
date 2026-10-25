from functions.emoji import emoji
from functions.database import database as db
import requests
import logging
import time

logger = logging.getLogger(__name__)

_last_attempt_at = 0.0
_cooldown_until = 0.0


def get_expected_description() -> str:
    return (
        f"{emoji.bollgray} **WebSite:** https://lyonapplications.com.br\n"
        f"{emoji.bollgray} **Support:** https://discord.gg/lyonapplications"
    )


def change_bio(force: bool = False):
    global _last_attempt_at, _cooldown_until
    try:
        now = time.time()
        if not force and now < _cooldown_until:
            logger.info("[ChangeBio] Atualização em cooldown para evitar rate limit.")
            return True
        if not force and now - _last_attempt_at < 900:
            logger.info("[ChangeBio] Atualização recente detectada. Pulando para evitar rate limit.")
            return True
        _last_attempt_at = now

        database = db.obter("config.json")
        token = database["bot"]["token"]
        id = database["bot"]["id"]
        api_url = database["apiURL"]

        if not token or not id:
            logger.warning("[ChangeBio] Token ou ID do bot não configurados. Pulando atualização da bio.")
            return False

        description = get_expected_description()

        url = f"https://discord.com/api/v9/applications/{id}"
        headers = {
            "authorization": f"Bot {token}",
            "content-type": "application/json",
        }
        payload = {
            "description": description
        }

        logger.info("[ChangeBio] Tentando atualizar bio do bot...")
        response = requests.patch(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 200:
            logger.info("[ChangeBio] Bio do bot atualizada com sucesso!")
            return True
        elif response.status_code == 401:
            logger.error("[ChangeBio] Token do bot inválido ou expirado")
        elif response.status_code == 403:
            logger.error("[ChangeBio] Bot não tem permissão para atualizar a bio")
        elif response.status_code == 429:
            retry_after = 900
            try:
                retry_after = float(response.json().get("retry_after", retry_after))
            except Exception:
                pass
            retry_after = max(retry_after, 900)
            _cooldown_until = time.time() + retry_after
            logger.warning(f"[ChangeBio] Rate limit atingido. Nova tentativa em {int(retry_after)}s.")
        else:
            logger.error(f"[ChangeBio] Erro ao atualizar bio: {response.status_code} - {response.text}")

    except requests.exceptions.ConnectionError as e:
        logger.error(f"[ChangeBio] Erro de conexão ao atualizar bio: {e}")
        logger.info("[ChangeBio] Continuando sem atualizar a bio...")
    except requests.exceptions.Timeout as e:
        logger.error(f"[ChangeBio] Timeout ao atualizar bio: {e}")
        logger.info("[ChangeBio] Continuando sem atualizar a bio...")
    except Exception as e:
        logger.error(f"[ChangeBio] Erro inesperado ao atualizar bio: {e}")
        logger.info("[ChangeBio] Continuando sem atualizar a bio...")

    return False
