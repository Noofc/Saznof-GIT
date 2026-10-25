import requests
import os
import time
from functions.database import database as db

_COOLDOWN_PATH = "database/system/intents_cooldown.json"


def _load_cooldown() -> dict:
    if not os.path.exists(_COOLDOWN_PATH):
        return {}
    data = db.obter(_COOLDOWN_PATH)
    return data if isinstance(data, dict) else {}


def _save_cooldown(seconds: float, reason: str):
    db.salvar(
        _COOLDOWN_PATH,
        {
            "until": time.time() + max(float(seconds), 0.0),
            "reason": reason,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


def get_application_id(token: str) -> str:
    """
    Obtém o ID da aplicação a partir do token do bot.
    """
    try:
        response = requests.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {token}"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("id")
        raise Exception(f"Erro ao obter ID da aplicação: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Erro de rede ao obter ID da aplicação: {e}") from e


def enable_intents(token: str, app_id: str = None) -> bool:
    """
    Ativa as intents privilegiadas do bot.
    flags 11051008 = GATEWAY_PRESENCE | GATEWAY_GUILD_MEMBERS | GATEWAY_MESSAGE_CONTENT
    """
    cooldown = _load_cooldown()
    until = float(cooldown.get("until") or 0)
    if time.time() < until:
        remaining = int(until - time.time())
        print(f"[Intents] Pulando ativação automática por cooldown ({remaining}s).")
        return False

    try:
        if app_id is None:
            app_id = get_application_id(token)
    except Exception as e:
        print(f"[Intents] Aviso: não foi possível obter o ID da aplicação: {e}")
        print("[Intents] Pulando ativação de intents privilegiadas para permitir que o bot inicie.")
        return False
    
    try:
        response = requests.patch(
            f"https://discord.com/api/v10/applications/{app_id}",
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            },
            json={
                "bot_public": False,
                "bot_require_code_grant": False,
                "flags": 11051008
            },
            timeout=10
        )
        if response.status_code == 200:
            print("[Intents] Intents privilegiadas ativadas com sucesso!")
            _save_cooldown(86400, "success")
            return True
        elif response.status_code == 429:
            retry_after = 3600
            try:
                retry_after = float(response.json().get("retry_after", retry_after))
            except Exception:
                pass
            retry_after = max(retry_after, 3600)
            _save_cooldown(retry_after, "rate_limited")
            print(f"[Intents] Rate limit recebido. Nova tentativa em {int(retry_after)}s.")
            return False
        else:
            print(f"[Intents] Erro ao ativar intents: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[Intents] Erro de rede ao ativar intents: {e}")
        print("[Intents] Pulando ativação de intents privilegiadas para permitir que o bot inicie.")
        return False
