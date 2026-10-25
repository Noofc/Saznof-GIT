from functions.database import database as db
from disnake.ext import commands, tasks
import disnake
import requests
import asyncio
import base64
import os

_DEFERRED_TASK_START_PATCHED = False


def _apply_deferred_task_start_patch():
    global _DEFERRED_TASK_START_PATCHED
    if _DEFERRED_TASK_START_PATCHED:
        return
    _DEFERRED_TASK_START_PATCHED = True

    original_start = tasks.Loop.start

    def safe_start(loop_self, *args, **kwargs):
        try:
            asyncio.get_running_loop()
        except RuntimeError as exc:
            if "no running event loop" not in str(exc).lower() and "no current event loop" not in str(exc).lower():
                raise

            cog = getattr(loop_self, "_injected", None)
            bot = getattr(cog, "bot", None)
            if bot is None or not hasattr(bot, "add_listener"):
                raise

            flag_name = "_system_deferred_start_registered"
            if getattr(loop_self, flag_name, False):
                return None
            setattr(loop_self, flag_name, True)

            async def start_after_ready():
                if getattr(loop_self, "_system_deferred_start_done", False):
                    return
                setattr(loop_self, "_system_deferred_start_done", True)

                try:
                    bot.remove_listener(start_after_ready, "on_ready")
                except Exception:
                    pass

                if not loop_self.is_running():
                    original_start(loop_self, *args, **kwargs)

            bot.add_listener(start_after_ready, "on_ready")
            return None

        return original_start(loop_self, *args, **kwargs)

    tasks.Loop.start = safe_start

def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return ""

def _bot_id_from_token(token: str) -> str:
    token = str(token or "").strip()
    if "." not in token:
        return ""
    first_part = token.split(".", 1)[0]
    try:
        padding = "=" * ((4 - len(first_part) % 4) % 4)
        decoded = base64.urlsafe_b64decode((first_part + padding).encode()).decode()
        return decoded if decoded.isdigit() else ""
    except Exception:
        return ""

def _runtime_bot_info(config_db: dict) -> dict:
    info = dict(config_db.get("bot") or {})
    token = _first_env("BOT_TOKEN", "TOKEN", "DISCORD_TOKEN") or info.get("token") or config_db.get("botToken") or ""
    bot_id = _first_env("BOT_ID", "CLIENT_ID", "APPLICATION_CLIENT_ID") or info.get("id") or config_db.get("botID") or _bot_id_from_token(token) or ""
    owner = _first_env("OWNER_ID", "OWNERID", "OWNER", "BOT_OWNER") or info.get("owner") or ""
    server = _first_env("BOT_SERVER_ID", "SERVER_ID", "GUILD_ID") or info.get("server") or ""

    if not token:
        raise RuntimeError("BOT_TOKEN nao informado. Configure a variavel de ambiente BOT_TOKEN na hospedagem.")

    info["token"] = token
    info["id"] = str(bot_id or "")
    info["owner"] = str(owner or "")
    info["server"] = str(server or "")
    info.setdefault("perms", [])
    info["version"] = "LyonPro V12.5"

    config_db["botToken"] = token
    config_db["botID"] = info["id"]
    config_db["bot"] = info
    db.salvar("config.json", config_db)

    return info

def obter_info():
        data = db.obter("config.json")
        token = _first_env("BOT_TOKEN", "TOKEN", "DISCORD_TOKEN") or data.get("botToken", "")
        bot_id = _first_env("BOT_ID", "CLIENT_ID", "APPLICATION_CLIENT_ID") or data.get("botID", "") or _bot_id_from_token(token)
        headers = {"authorization": token, "content-type": "application/json"}
        url = f"{data['apiURL']}/api/bot/{bot_id}/info"

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        
        print(f"[ObterInfo] Erro na requisição. Status: {response.status_code}")
        exit(1)

def salvar_info(info: dict):
    config_db = db.obter("config.json")
    # A versão definida localmente pelo administrador tem prioridade sobre a API.
    version = "LyonPro V12.5"
    config_db["version"] = version
    config_db["bot"] = {k: info[k] for k in ("token", "owner", "id", "perms", "server") if k in info}
    config_db["bot"]["version"] = version
    db.salvar("config.json", config_db)

def create_bot() -> tuple[commands.Bot, str, str]:
    config_db = db.obter("config.json")
    print(f"[CreatePro] saveConfig = {config_db.get('saveConfig')}")
    
    if config_db["saveConfig"] == True:
        print("[CreatePro] saveConfig está True, obtendo info da API...")
        info = obter_info()
        print("[CreatePro] Tentando salvar info no config.json...")
        salvar_info(info)
    else:
        print("[CreatePro] saveConfig esta False, usando BOT_TOKEN do ambiente/local")
        info = _runtime_bot_info(config_db)
        info["version"] = "LyonPro V12.5"

    intents = disnake.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True

    bot = commands.Bot(
        command_prefix=commands.when_mentioned,
        intents=intents,
        help_command=None,
        reload=True
    )
    _apply_deferred_task_start_patch()
    return bot, info["token"], info["id"]
