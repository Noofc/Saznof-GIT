"""
Task que envia informações do servidor principal para o Backend
para exibição no site (Server Showcase).
"""

import aiohttp
import json
import os
import asyncio
import time
from disnake.ext import tasks
from functions.database import database as db
from functions.utils import utils

_backend_warning_shown = False
_invite_cache = {}
_invite_rate_limit_until = 0
_invite_warning_shown = False


def _is_rate_limited(exc) -> bool:
    text = str(exc).lower()
    return getattr(exc, "status", None) == 429 or "429" in text or "rate limit" in text or "too many requests" in text or "error 1015" in text



def _get_backend_url():
    """Carrega a URL do backend do config_api.json"""
    try:
        config = db.obter("configs/config_api.json") or {}
        url = config.get("backend", "")
        if url and not url.startswith("http"):
            url = f"https://{url}"
        return url
    except Exception:
        return ""


@tasks.loop(minutes=5)
async def server_showcase_task(bot):
    global _backend_warning_shown
    """Envia informações do servidor principal para o backend"""
    try:
        backend_url = _get_backend_url()
        if not backend_url:
            return

        # Obter servidor principal
        try:
            guild_id = utils.obter_server_principal()
            guild = bot.get_guild(guild_id)
        except Exception:
            guild = None

        if not guild:
            return

        # Coletar informações do servidor
        icon_url = guild.icon.url if guild.icon else ""
        member_count = guild.member_count or len(guild.members)
        online_count = sum(
            1 for m in guild.members
            if m.status and str(m.status) != "offline"
        )

        # Criar convite valido com cache/cooldown para nao cair em rate limit.
        invite_url = ""
        now = time.time()
        cached = _invite_cache.get(str(guild.id)) or {}
        if cached.get("url") and cached.get("expires_at", 0) > now:
            invite_url = cached["url"]

        try:
            global _invite_rate_limit_until, _invite_warning_shown
            if not invite_url and now < _invite_rate_limit_until:
                invite_url = cached.get("url", "")
            elif not invite_url:
                # Tentar usar o vanity invite primeiro
                if hasattr(guild, 'vanity_url_code') and guild.vanity_url_code:
                    invite_url = f"https://discord.gg/{guild.vanity_url_code}"
                else:
                    try:
                        invites = await guild.invites()
                    except Exception as e:
                        if _is_rate_limited(e):
                            _invite_rate_limit_until = time.time() + 3600
                            if not _invite_warning_shown:
                                print("[ServerShowcase] Discord limitou os convites. Pausando busca/criacao por 1 hora.")
                                _invite_warning_shown = True
                            invites = []
                        else:
                            raise

                    for inv in invites:
                        if inv.max_age == 0 and inv.max_uses == 0:
                            invite_url = str(inv)
                            break

                    if not invite_url and now >= _invite_rate_limit_until:
                        for channel in guild.text_channels:
                            try:
                                invite = await channel.create_invite(
                                    max_age=0,
                                    max_uses=0,
                                    unique=False,
                                    reason="Server Showcase - Site Lyon"
                                )
                                invite_url = str(invite)
                                break
                            except Exception as e:
                                if _is_rate_limited(e):
                                    _invite_rate_limit_until = time.time() + 3600
                                    if not _invite_warning_shown:
                                        print("[ServerShowcase] Discord limitou a criacao de convites. Pausando por 1 hora.")
                                        _invite_warning_shown = True
                                    break
                                continue

            if invite_url:
                _invite_cache[str(guild.id)] = {"url": invite_url, "expires_at": time.time() + 86400}
                _invite_warning_shown = False
        except Exception as e:
            text = str(e)
            if _is_rate_limited(e):
                _invite_rate_limit_until = time.time() + 3600
                if not _invite_warning_shown:
                    print("[ServerShowcase] Discord limitou os convites. Pausando por 1 hora.")
                    _invite_warning_shown = True
            else:
                print(f"[ServerShowcase] Erro ao obter invite: {text[:180]}")

        # Montar payload
        payload = {
            "guild_id": str(guild.id),
            "name": guild.name,
            "icon": icon_url,
            "member_count": member_count,
            "online_count": online_count,
            "invite_url": invite_url,
        }

        # Enviar para o backend
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{backend_url}/servers/update",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    pass  # Sucesso silencioso
                else:
                    text = await resp.text()
                    print(f"[ServerShowcase] Backend retornou {resp.status}: {text[:100]}")

    except (aiohttp.ClientConnectorError, aiohttp.ClientConnectorDNSError, asyncio.TimeoutError) as e:
        if not _backend_warning_shown:
            print(f"[ServerShowcase] Backend indisponivel ({e}). O bot vai continuar sem enviar showcase.")
            _backend_warning_shown = True
    except Exception as e:
        print(f"[ServerShowcase] ❌ Erro: {e}")


@server_showcase_task.before_loop
async def before_server_showcase(bot=None):
    """Aguarda o bot estar pronto antes de iniciar"""
    pass
