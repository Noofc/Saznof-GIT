from __future__ import annotations

import io
import math
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncio
import aiohttp
import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import load_guild_channels
from functions.perms import perms
from functions.bool_utils import as_bool
from functions.system_logs import ensure_guild_log_channel
from .panel_v2 import build_panel_card, channel_label, configured_label, status_label
from modules.loja.cart.checkout import (
    _api_base_root,
    _check_single_payment_status,
    _create_payment,
    _extract_payment_ids,
    _extract_qr_image,
    _extract_urls,
    _http_get_bytes,
)


ROBux_CONFIG_KEY = "robux_config"
ROBux_ORDERS_KEY = "robux_orders"


DEFAULT_CONFIG = {
    "enabled": False,
    "valor_robux": 32.0,
    "valor_gamepass": 42.0,
    "valor_grupo": 37.76,
    "minimo_robux": 100,
    "maximo_robux": 20000,
    "public_channel_id": None,
    "calculator_channel_id": None,
    "log_channel_id": None,
    "category_id": None,
    "group_verification_enabled": False,
    "group_id": None,
    "group_min_days": 14,
    "group_block_orders": True,
    "auto_payment_enabled": True,
    "auto_delivery_enabled": True,
    "delete_order_channel_on_finish": True,
}


def _money(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _int_text(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _as_float(value: Any, default: float) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return default


def _clean_channel_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.lower()).strip("-")
    return value[:40] or "pedido"


def _is_group_order(tipo: str) -> bool:
    value = str(tipo or "").lower()
    return "grupo" in value or "group" in value


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class RobuxPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._pending_confirmations: dict[str, dict] = {}

    def _get_config(self) -> dict:
        data = db.get_document(ROBux_CONFIG_KEY) or {}
        config = DEFAULT_CONFIG.copy()
        config.update(data)
        config["enabled"] = as_bool(config.get("enabled"), False)
        if not config.get("valor_grupo"):
            config["valor_grupo"] = round(float(config["valor_robux"]) * 1.18, 2)
        return config

    def _save_config(self, config: dict) -> None:
        db.save_document(ROBux_CONFIG_KEY, config)

    def _get_orders(self) -> dict:
        data = db.get_document(ROBux_ORDERS_KEY) or {}
        data.setdefault("orders", {})
        data.setdefault("group_memberships", {})
        return data

    def _save_orders(self, data: dict) -> None:
        db.save_document(ROBux_ORDERS_KEY, data)

    async def _roblox_json(self, method: str, url: str, **kwargs) -> tuple[dict | None, str | None]:
        timeout = aiohttp.ClientTimeout(total=8)
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("User-Agent", "LyonProPro/1.0")

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.request(method, url, **kwargs) as resp:
                    if resp.status < 200 or resp.status >= 300:
                        return None, f"Roblox retornou HTTP {resp.status}."
                    try:
                        return await resp.json(content_type=None), None
                    except Exception:
                        return None, "Roblox retornou uma resposta invalida."
        except Exception as exc:
            return None, f"Falha ao consultar Roblox: {exc}"

    def _cleanup_pending_confirmations(self) -> None:
        now = time.time()
        expired = [
            token
            for token, payload in self._pending_confirmations.items()
            if payload.get("expires_at", 0) <= now
        ]
        for token in expired:
            self._pending_confirmations.pop(token, None)

    async def _get_roblox_avatar_url(self, user_id: int) -> tuple[str | None, str | None]:
        data, error = await self._roblox_json(
            "GET",
            "https://thumbnails.roblox.com/v1/users/avatar-headshot",
            params={
                "userIds": str(int(user_id)),
                "size": "420x420",
                "format": "Png",
                "isCircular": "false",
            },
        )
        if error:
            return None, error

        items = data.get("data", []) if isinstance(data, dict) else []
        for item in items:
            image_url = item.get("imageUrl")
            if image_url:
                return image_url, None

        return None, "Avatar Roblox indisponivel."

    async def _resolve_roblox_profile(self, roblox_user: str) -> tuple[dict | None, str | None]:
        profile, error = await self._resolve_roblox_user(roblox_user)
        if error or not profile:
            return None, error or "Usuario Roblox nao encontrado."

        avatar_url, avatar_error = await self._get_roblox_avatar_url(profile["id"])
        profile["avatar_url"] = avatar_url
        profile["avatar_error"] = avatar_error
        return profile, None

    def _format_roblox_profile(self, profile: dict | None, fallback: str) -> str:
        if not profile:
            return f"`{fallback}`"

        display_name = profile.get("display_name") or profile.get("name") or fallback
        username = profile.get("name") or fallback
        user_id = profile.get("id")

        if display_name and username and display_name != username:
            label = f"`{display_name}` (@{username})"
        else:
            label = f"`@{username}`"

        if user_id:
            label += f" | ID `{user_id}`"
        return label

    async def _resolve_roblox_user(self, roblox_user: str) -> tuple[dict | None, str | None]:
        value = str(roblox_user or "").strip()
        if not value or value.lower() in {"nao informado", "n/a", "none"}:
            return None, "Informe o usuario ou ID Roblox."

        profile_match = re.search(r"roblox\.com/users/(\d+)", value, flags=re.IGNORECASE)
        user_id = profile_match.group(1) if profile_match else (value if value.isdigit() else None)

        if user_id:
            data, error = await self._roblox_json("GET", f"https://users.roblox.com/v1/users/{int(user_id)}")
            if error:
                return None, error
            if data and data.get("id"):
                return {
                    "id": int(data["id"]),
                    "name": data.get("name") or str(user_id),
                    "display_name": data.get("displayName") or data.get("name") or str(user_id),
                }, None
            return None, "Usuario Roblox nao encontrado."

        username = value.lstrip("@").strip()
        data, error = await self._roblox_json(
            "POST",
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": True},
        )
        if error:
            return None, error

        users = data.get("data", []) if isinstance(data, dict) else []
        if not users:
            return None, "Usuario Roblox nao encontrado."

        user = users[0]
        return {
            "id": int(user["id"]),
            "name": user.get("name") or username,
            "display_name": user.get("displayName") or user.get("name") or username,
        }, None

    async def _get_group_membership(self, user_id: int, group_id: int) -> tuple[dict | None, str | None]:
        data, error = await self._roblox_json(
            "GET",
            f"https://groups.roblox.com/v2/users/{int(user_id)}/groups/roles",
        )
        if error:
            return None, error

        for membership in (data.get("data", []) if isinstance(data, dict) else []):
            group = membership.get("group") or {}
            try:
                if int(group.get("id")) == int(group_id):
                    return membership, None
            except (TypeError, ValueError):
                continue

        return None, "Usuario nao esta no grupo configurado."

    def _group_config_text(self, config: dict) -> str:
        if not as_bool(config.get("group_verification_enabled"), False):
            return "`Desativada`"

        group_id = config.get("group_id") or "Nao configurado"
        min_days = _as_int(config.get("group_min_days"), DEFAULT_CONFIG["group_min_days"])
        block = "bloqueia" if as_bool(config.get("group_block_orders"), True) else "avisa"
        delivery = "entrega auto" if as_bool(config.get("auto_delivery_enabled"), True) else "entrega manual"
        return f"`Ativa` | Grupo: `{group_id}` | Minimo: `{min_days} dias` | Modo: `{block}` | `{delivery}`"

    def _format_group_check(self, check: dict | None) -> str:
        if not check:
            return "**Verificacao grupo:** `Nao aplicada`"

        if not check.get("enabled"):
            return "**Verificacao grupo:** `Desativada`"

        status = "Aprovado" if check.get("eligible") else "Pendente"
        if check.get("error"):
            status = "Reprovado"

        lines = [
            f"**Verificacao grupo:** `{status}`",
            f"**Motivo:** {check.get('reason', 'Sem detalhes')}",
        ]
        if check.get("roblox_user"):
            lines.append(f"**Roblox:** `{check['roblox_user']}` (`{check.get('roblox_user_id')}`)")
        if check.get("role_name"):
            lines.append(f"**Cargo no grupo:** `{check['role_name']}`")
        if check.get("days_seen") is not None:
            lines.append(f"**Tempo registrado pelo bot:** `{check['days_seen']:.1f} dias`")
        return "\n".join(lines)

    async def _verify_group_purchase(self, roblox_user: str, config: dict) -> dict:
        enabled = as_bool(config.get("group_verification_enabled"), False)
        if not enabled:
            return {"enabled": False, "allowed": True, "eligible": True, "reason": "Verificacao desativada."}

        group_id = _as_int(config.get("group_id"), 0)
        min_days = max(0, _as_int(config.get("group_min_days"), DEFAULT_CONFIG["group_min_days"]))
        block_orders = as_bool(config.get("group_block_orders"), True)
        if group_id <= 0:
            return {
                "enabled": True,
                "allowed": not block_orders,
                "eligible": False,
                "error": True,
                "reason": "ID do grupo Roblox nao configurado.",
            }

        user, error = await self._resolve_roblox_user(roblox_user)
        if error or not user:
            return {
                "enabled": True,
                "allowed": not block_orders,
                "eligible": False,
                "error": True,
                "reason": error or "Usuario Roblox nao encontrado.",
            }

        membership, error = await self._get_group_membership(user["id"], group_id)
        if error or not membership:
            return {
                "enabled": True,
                "allowed": not block_orders,
                "eligible": False,
                "error": True,
                "reason": error or "Usuario nao esta no grupo configurado.",
                "roblox_user": user["name"],
                "roblox_user_id": user["id"],
                "group_id": group_id,
            }

        now = disnake.utils.utcnow()
        orders_doc = self._get_orders()
        memberships = orders_doc.setdefault("group_memberships", {})
        membership_key = f"{group_id}:{user['id']}"
        cached = memberships.get(membership_key, {})
        first_seen = _parse_datetime(cached.get("first_seen_at")) or now
        role = membership.get("role") or {}

        memberships[membership_key] = {
            "group_id": group_id,
            "user_id": user["id"],
            "username": user["name"],
            "display_name": user["display_name"],
            "role_name": role.get("name"),
            "role_rank": role.get("rank"),
            "first_seen_at": first_seen.isoformat(),
            "last_checked_at": now.isoformat(),
        }
        self._save_orders(orders_doc)

        days_seen = max((now - first_seen).total_seconds() / 86400, 0)
        eligible = days_seen >= min_days
        allowed = eligible or not block_orders

        if eligible:
            reason = f"Usuario esta no grupo e cumpriu o minimo de {min_days} dias."
        elif min_days <= 0:
            reason = "Usuario esta no grupo."
            eligible = True
            allowed = True
        else:
            remaining = max(min_days - days_seen, 0)
            reason = f"Usuario esta no grupo, mas faltam {remaining:.1f} dias no registro do bot."

        return {
            "enabled": True,
            "allowed": allowed,
            "eligible": eligible,
            "error": False,
            "reason": reason,
            "roblox_user": user["name"],
            "roblox_display_name": user["display_name"],
            "roblox_user_id": user["id"],
            "group_id": group_id,
            "role_name": role.get("name"),
            "role_rank": role.get("rank"),
            "first_seen_at": first_seen.isoformat(),
            "last_checked_at": now.isoformat(),
            "days_seen": days_seen,
            "required_days": min_days,
        }

    def _calculate(self, quantidade: int, config: dict | None = None) -> dict:
        config = config or self._get_config()
        valor_robux = _as_float(config.get("valor_robux"), DEFAULT_CONFIG["valor_robux"])
        valor_gamepass = _as_float(config.get("valor_gamepass"), DEFAULT_CONFIG["valor_gamepass"])
        valor_grupo = _as_float(config.get("valor_grupo"), valor_robux * 1.18)

        preco_sem_taxa = (quantidade / 1000) * valor_robux
        recebe_sem_taxa = math.floor(quantidade * 0.7)
        preco_com_taxa = math.ceil(preco_sem_taxa / 0.75)
        gamepass_necessario = math.ceil(quantidade / 0.7)
        preco_grupo = (quantidade / 1000) * valor_grupo
        preco_gamepass = (quantidade / 1000) * valor_gamepass

        return {
            "sem_taxa": {"preco": preco_sem_taxa, "recebe": recebe_sem_taxa},
            "com_taxa": {"preco": preco_com_taxa, "gamepass": gamepass_necessario},
            "grupo": {"preco": preco_grupo},
            "gamepass_produto": {"preco": preco_gamepass},
        }

    def _order_price_summary(self, tipo: str, calc: dict) -> str:
        normalized = str(tipo or "").lower()
        if "grupo" in normalized or "group" in normalized:
            return f"`{_money(calc['grupo']['preco'])}` via grupo"
        if "gamepass" in normalized:
            return f"`{_money(calc['gamepass_produto']['preco'])}` em gamepass produto"
        if "sem" in normalized and "taxa" in normalized:
            return (
                f"`{_money(calc['sem_taxa']['preco'])}` "
                f"recebendo `{_int_text(calc['sem_taxa']['recebe'])} Robux`"
            )
        return (
            f"`{_money(calc['com_taxa']['preco'])}` "
            f"com gamepass de `{_int_text(calc['com_taxa']['gamepass'])} Robux`"
        )

    def _order_price_value(self, tipo: str, calc: dict) -> float:
        normalized = str(tipo or "").lower()
        if "grupo" in normalized or "group" in normalized:
            return float(calc["grupo"]["preco"])
        if "gamepass" in normalized:
            return float(calc["gamepass_produto"]["preco"])
        if "sem" in normalized and "taxa" in normalized:
            return float(calc["sem_taxa"]["preco"])
        return float(calc["com_taxa"]["preco"])

    def _roblox_cookie(self) -> str | None:
        cookie = os.getenv("SYSTEM_ROBLOX_COOKIE") or os.getenv("ROBLOX_SECURITY_COOKIE")
        if not cookie:
            return None

        cookie = str(cookie).strip()
        match = re.search(r"\.ROBLOSECURITY=([^;\s]+)", cookie)
        if match:
            return match.group(1)
        return cookie

    def _select_payment_id(self, payment_data: dict) -> str | None:
        provider = payment_data.get("provider")
        ids = payment_data.get("ids") or {}
        raw = payment_data.get("raw") or {}

        if provider == "efibank":
            return (
                ids.get("txid")
                or ids.get("payment_id")
                or ids.get("id")
                or raw.get("txid")
                or raw.get("payment_id")
                or raw.get("id")
            )

        return (
            ids.get("payment_id")
            or ids.get("id")
            or ids.get("payment_intent")
            or ids.get("invoice_id")
            or ids.get("preference_id")
            or ids.get("charge")
            or ids.get("txid")
            or raw.get("payment_id")
            or raw.get("paymentId")
            or raw.get("id")
            or raw.get("txid")
        )

    def _safe_payment_payload(self, value: Any) -> Any:
        if isinstance(value, (bytes, bytearray)):
            return None
        if isinstance(value, dict):
            return {str(k): self._safe_payment_payload(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._safe_payment_payload(item) for item in value]
        return value

    async def _resolve_discord_user(self, guild: disnake.Guild, user_id: int):
        user = guild.get_member(int(user_id))
        if user:
            return user
        try:
            return await guild.fetch_member(int(user_id))
        except Exception:
            try:
                return await self.bot.fetch_user(int(user_id))
            except Exception:
                return None

    async def _roblox_group_payout(self, group_id: int, roblox_user_id: int, amount: int) -> dict:
        cookie = self._roblox_cookie()
        if not cookie:
            return {
                "success": False,
                "pending": True,
                "reason": "Cookie Roblox nao configurado no ambiente. Use SYSTEM_ROBLOX_COOKIE ou ROBLOX_SECURITY_COOKIE.",
            }

        headers = {
            "Cookie": f".ROBLOSECURITY={cookie}",
            "User-Agent": "LyonProPro/1.0",
        }
        timeout = aiohttp.ClientTimeout(total=15)

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post("https://auth.roblox.com/v2/logout") as resp:
                    csrf_token = resp.headers.get("x-csrf-token")

                if not csrf_token:
                    return {
                        "success": False,
                        "pending": True,
                        "reason": "Nao consegui obter o token CSRF do Roblox. Verifique se o cookie esta valido.",
                    }

                payout_headers = {
                    **headers,
                    "x-csrf-token": csrf_token,
                    "Content-Type": "application/json",
                }
                payload = {
                    "PayoutType": "FixedAmount",
                    "Recipients": [
                        {
                            "recipientId": int(roblox_user_id),
                            "recipientType": "User",
                            "amount": int(amount),
                        }
                    ],
                }
                async with session.post(
                    f"https://groups.roblox.com/v1/groups/{int(group_id)}/payouts",
                    json=payload,
                    headers=payout_headers,
                ) as resp:
                    text = await resp.text()
                    if resp.status in {200, 201, 204}:
                        return {"success": True, "reason": "Payout enviado pelo grupo Roblox."}

                    safe_text = re.sub(r"\s+", " ", text or "").strip()
                    if len(safe_text) > 240:
                        safe_text = safe_text[:240] + "..."
                    return {
                        "success": False,
                        "pending": True,
                        "reason": f"Roblox retornou HTTP {resp.status}. {safe_text or 'Sem detalhes.'}",
                    }
        except Exception as exc:
            return {
                "success": False,
                "pending": True,
                "reason": f"Falha ao enviar payout Roblox: {exc}",
            }

    def _calculator_components(self, quantidade: int, config: dict | None = None) -> list:
        config = config or self._get_config()
        calc = self._calculate(quantidade, config)
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay("## Calculadora Robux"),
                disnake.ui.TextDisplay(f"-# Preco estimado para `{_int_text(quantidade)}` Robux"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"**Robux sem taxa**\n"
                    f"> Preco: `{_money(calc['sem_taxa']['preco'])}`\n"
                    f"> Recebe: `{_int_text(calc['sem_taxa']['recebe'])} Robux`\n\n"
                    f"**Robux com taxa**\n"
                    f"> Preco: `{_money(calc['com_taxa']['preco'])}`\n"
                    f"> Gamepass necessaria: `{_int_text(calc['com_taxa']['gamepass'])} Robux`\n\n"
                    f"**Via grupo**\n"
                    f"> Preco: `{_money(calc['grupo']['preco'])}`\n\n"
                    f"**Gamepass produto**\n"
                    f"> Preco: `{_money(calc['gamepass_produto']['preco'])}`"
                ),
                accent_colour=disnake.Colour.green(),
            )
        ]

    def _public_panel_components(self, config: dict | None = None) -> list:
        config = config or self._get_config()
        min_robux = _as_int(config.get("minimo_robux"), DEFAULT_CONFIG["minimo_robux"])
        max_robux = _as_int(config.get("maximo_robux"), DEFAULT_CONFIG["maximo_robux"])
        group_notice = ""
        if as_bool(config.get("group_verification_enabled"), False):
            group_notice = (
                f"\n**Venda via grupo:** precisa estar no grupo `{config.get('group_id') or 'nao configurado'}` "
                f"por `{_as_int(config.get('group_min_days'), DEFAULT_CONFIG['group_min_days'])} dias`"
            )
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay("## Robux"),
                disnake.ui.TextDisplay(
                    "Calcule valores e abra pedidos de Robux automaticamente."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"**Status:** {status_label(as_bool(config.get('enabled'), False))}\n"
                    f"**Robux sem taxa:** `{_money(_as_float(config.get('valor_robux'), 32.0))} / 1000`\n"
                    f"**Gamepass produto:** `{_money(_as_float(config.get('valor_gamepass'), 42.0))} / 1000`\n"
                    f"**Limites:** `{_int_text(min_robux)}` a `{_int_text(max_robux)}` Robux"
                    f"{group_notice}"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Calcular",
                        style=disnake.ButtonStyle.blurple,
                        emoji=getattr(emoji, "calculator", None),
                        custom_id="Robux_PublicCalc",
                        disabled=not as_bool(config.get("enabled"), False),
                    ),
                    disnake.ui.Button(
                        label="Comprar",
                        style=disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "cart", None),
                        custom_id="Robux_PublicBuy",
                        disabled=not as_bool(config.get("enabled"), False),
                    ),
                ),
                accent_colour=disnake.Colour.green(),
            )
        ]

    def _roblox_confirmation_components(
        self,
        token: str,
        profile: dict,
        quantidade: int,
        tipo: str,
        observacao: str,
        config: dict | None = None,
    ) -> list:
        config = config or self._get_config()
        calc = self._calculate(quantidade, config)
        display_name = profile.get("display_name") or profile.get("name") or "Roblox"
        username = profile.get("name") or display_name
        user_id = profile.get("id") or "N/A"
        avatar_url = profile.get("avatar_url")
        profile_url = f"https://www.roblox.com/users/{user_id}/profile" if user_id != "N/A" else None
        price_summary = self._order_price_summary(tipo, calc)

        if avatar_url:
            children = [
                disnake.ui.Section(
                    disnake.ui.TextDisplay(
                        "## Perfil Roblox encontrado\n"
                        "### Esse aqui e voce?\n"
                        f"-# Confirme se a conta abaixo e a conta que vai receber os Robux."
                    ),
                    accessory=disnake.ui.Thumbnail(media=avatar_url),
                )
            ]
        else:
            children = [
                disnake.ui.TextDisplay(
                    "## Perfil Roblox encontrado\n"
                    "### Esse aqui e voce?\n"
                    "-# Confirme se a conta abaixo e a conta que vai receber os Robux."
                ),
                disnake.ui.TextDisplay(
                    f"-# Encontrei o usuario, mas nao consegui carregar a foto do avatar agora. "
                    f"{profile.get('avatar_error') or ''}".strip()
                ),
            ]

        profile_lines = [
            f"**Nome:** `{display_name}`",
            f"**Usuario:** `@{username}`",
            f"**ID Roblox:** `{user_id}`",
        ]
        if profile_url:
            profile_lines.append(f"**Perfil:** {profile_url}")

        children.extend(
            [
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay("\n".join(profile_lines)),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay("### Resumo do pedido"),
                disnake.ui.TextDisplay(
                    f"**Quantidade:** `{_int_text(quantidade)} Robux`\n"
                    f"**Tipo:** `{tipo}`\n"
                    f"**Valor estimado:** {price_summary}\n"
                    f"**Observacao:** {observacao or '`Nenhuma`'}"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Confirmar Pedido",
                        style=disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "correct", None),
                        custom_id=f"Robux_Confirm:{token}",
                    ),
                    disnake.ui.Button(
                        label="Trocar Usuario",
                        style=disnake.ButtonStyle.blurple,
                        emoji=getattr(emoji, "edit", None),
                        custom_id=f"Robux_EditConfirm:{token}",
                    ),
                    disnake.ui.Button(
                        label="Cancelar",
                        style=disnake.ButtonStyle.danger,
                        emoji=getattr(emoji, "wrong", None),
                        custom_id=f"Robux_CancelConfirm:{token}",
                    ),
                ),
            ]
        )

        return [disnake.ui.Container(*children, accent_colour=disnake.Colour(0x0082FF))]

    async def _show_roblox_confirmation(
        self,
        inter: disnake.ModalInteraction,
        quantidade: int,
        tipo: str,
        roblox_user: str,
        observacao: str,
    ) -> None:
        config = self._get_config()
        min_robux = _as_int(config.get("minimo_robux"), DEFAULT_CONFIG["minimo_robux"])
        max_robux = _as_int(config.get("maximo_robux"), DEFAULT_CONFIG["maximo_robux"])
        if quantidade < min_robux or quantidade > max_robux:
            await inter.response.send_message(
                f"{emoji.wrong} A quantidade precisa ficar entre `{min_robux}` e `{max_robux}` Robux.",
                ephemeral=True,
            )
            return

        await inter.response.defer(ephemeral=True)

        profile, error = await self._resolve_roblox_profile(roblox_user)
        if error or not profile:
            await inter.followup.send(
                f"{emoji.wrong} Nao consegui encontrar esse usuario no Roblox: {error or 'usuario invalido'}",
                ephemeral=True,
            )
            return

        self._cleanup_pending_confirmations()
        token = uuid.uuid4().hex[:12].upper()
        self._pending_confirmations[token] = {
            "guild_id": inter.guild.id if inter.guild else None,
            "user_id": inter.user.id,
            "quantidade": quantidade,
            "tipo": tipo,
            "roblox_user": roblox_user,
            "observacao": observacao,
            "roblox_profile": profile,
            "created_at": time.time(),
            "expires_at": time.time() + 900,
        }

        await inter.followup.send(
            components=self._roblox_confirmation_components(token, profile, quantidade, tipo, observacao, config),
            ephemeral=True,
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    def display_robux_panel(self, inter: disnake.MessageInteraction):
        config = self._get_config()
        orders = self._get_orders().get("orders", {})
        open_orders = sum(1 for order in orders.values() if order.get("status") == "open")

        return build_panel_card(
            title="Robux",
            breadcrumb="Painel > Robux",
            description="Sistema de calculadora e pedidos de Robux via componentes V2.",
            status_lines=[
                f"**Status:** {status_label(as_bool(config.get('enabled'), False))}",
                f"**Canal painel:** {channel_label(config.get('public_channel_id'))}",
                f"**Canal calculadora:** {channel_label(config.get('calculator_channel_id'))}",
                f"**Canal logs:** {channel_label(config.get('log_channel_id'))}",
                f"**Categoria carrinhos:** {configured_label(config.get('category_id'))}",
                f"**Verificacao grupo:** {self._group_config_text(config)}",
                f"**Pagamento automatico:** {status_label(as_bool(config.get('auto_payment_enabled'), True))}",
                f"**Entrega automatica:** {status_label(as_bool(config.get('auto_delivery_enabled'), True))}",
                f"**Pedidos abertos:** `{open_orders}`",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Desativar" if as_bool(config.get("enabled"), False) else "Ativar",
                        style=disnake.ButtonStyle.danger if as_bool(config.get("enabled"), False) else disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "power", None),
                        custom_id="Robux_Toggle",
                    ),
                    disnake.ui.Button(
                        label="Valores",
                        style=disnake.ButtonStyle.blurple,
                        emoji=getattr(emoji, "coin", None),
                        custom_id="Robux_ConfigValores",
                    ),
                    disnake.ui.Button(
                        label="Canais",
                        style=disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, "textc", None),
                        custom_id="Robux_ConfigCanais",
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Verificacao Grupo",
                        style=disnake.ButtonStyle.blurple,
                        emoji=getattr(emoji, "group", None),
                        custom_id="Robux_ConfigGrupo",
                    ),
                    disnake.ui.Button(
                        label="Testar Grupo",
                        style=disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, "search", None),
                        custom_id="Robux_TestGrupo",
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Enviar Painel",
                        style=disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "send", None),
                        custom_id="Robux_SendPanel",
                    ),
                    disnake.ui.Button(
                        label="Preview",
                        style=disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, "image", None),
                        custom_id="Robux_Preview",
                    ),
                ),
            ],
        )

    async def _refresh_admin_panel(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_robux_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    async def _send_log(self, guild: disnake.Guild, content: str = None, components: list | None = None):
        config = self._get_config()
        canais = load_guild_channels(guild)
        channel = None
        for channel_id in (
            config.get("log_channel_id"),
            canais.get("canal_de_logs_de_robux"),
            canais.get("canal_de_logs_de_pedidos"),
        ):
            try:
                channel = guild.get_channel(int(channel_id)) if channel_id else None
            except (TypeError, ValueError):
                channel = None
            if isinstance(channel, disnake.TextChannel):
                break
        if not isinstance(channel, disnake.TextChannel):
            channel = await ensure_guild_log_channel(guild, "canal_de_logs_de_robux")
        if isinstance(channel, disnake.TextChannel):
            try:
                if components:
                    if content:
                        components = [
                            disnake.ui.Container(
                                disnake.ui.TextDisplay(content),
                                accent_colour=disnake.Colour.blurple(),
                            ),
                            *components,
                        ]
                    await channel.send(
                        components=components,
                        flags=disnake.MessageFlags(is_components_v2=True),
                    )
                else:
                    await channel.send(content)
            except disnake.HTTPException:
                pass

    async def _send_robux_payment_message(
        self,
        channel: disnake.TextChannel,
        order_id: str,
        order: dict,
        payment_data: dict,
        qr_bytes: bytes | None = None,
        qr_url: str | None = None,
    ) -> disnake.Message | None:
        amount = _as_float(payment_data.get("amount"), 0)
        copy_code = payment_data.get("copy_code")
        checkout_url = payment_data.get("checkout_url")
        provider = payment_data.get("provider") or "pix"

        embed = disnake.Embed(
            title=f"Pagamento Robux `{order_id}`",
            description=(
                f"Cliente: <@{order.get('user_id')}>\n"
                f"Roblox: {self._format_roblox_profile(order.get('roblox_profile'), order.get('roblox_user', 'N/A'))}\n"
                f"Quantidade: `{_int_text(_as_int(order.get('quantidade'), 0))} Robux`\n\n"
                "Pague pela opcao abaixo. Assim que o pagamento aprovar, o bot vai processar a entrega automaticamente."
            ),
            color=disnake.Colour(0x0082FF),
        )
        embed.add_field(name="Valor", value=_money(amount), inline=True)
        embed.add_field(name="Metodo", value=f"`PIX` | `{provider}`", inline=True)
        payment_id = self._select_payment_id(payment_data)
        if payment_id:
            embed.add_field(name="Referencia", value=f"`{payment_id}`", inline=False)

        if copy_code:
            try:
                from modules.loja.personalization.qr_customization import QRCodeGenerator
                if QRCodeGenerator.is_enabled():
                    custom_qr = await QRCodeGenerator.generate_custom_qr(copy_code)
                    if custom_qr:
                        qr_bytes = custom_qr
                        qr_url = None
            except Exception as exc:
                print(f"[Robux] Falha ao aplicar QR personalizado: {exc}")

        full_qr_url = qr_url
        if full_qr_url and str(full_qr_url).startswith("/"):
            full_qr_url = _api_base_root() + str(full_qr_url)

        if full_qr_url and not qr_bytes:
            fetched = await _http_get_bytes(str(full_qr_url))
            if fetched:
                qr_bytes = fetched
                full_qr_url = None

        files = None
        if qr_bytes:
            files = [disnake.File(io.BytesIO(qr_bytes), filename=f"robux-{order_id}-qrcode.png")]
            embed.set_image(url=f"attachment://robux-{order_id}-qrcode.png")
        elif full_qr_url:
            embed.set_image(url=str(full_qr_url))

        buttons = []
        if copy_code:
            buttons.append(
                disnake.ui.Button(
                    label="Copiar PIX",
                    style=disnake.ButtonStyle.grey,
                    emoji=getattr(emoji, "pix", None),
                    custom_id=f"Robux_CopyPix:{order_id}",
                )
            )
        if checkout_url:
            buttons.append(
                disnake.ui.Button(
                    label="Abrir Checkout",
                    style=disnake.ButtonStyle.url,
                    url=str(checkout_url),
                )
            )
        buttons.extend(
            [
                disnake.ui.Button(
                    label="Verificar Pagamento",
                    style=disnake.ButtonStyle.success,
                    emoji=getattr(emoji, "correct", None),
                    custom_id=f"Robux_CheckPayment:{order_id}",
                ),
                disnake.ui.Button(
                    label="Cancelar Pedido",
                    style=disnake.ButtonStyle.danger,
                    emoji=getattr(emoji, "wrong", None),
                    custom_id=f"Robux_OrderCancel:{order_id}",
                ),
            ]
        )

        try:
            return await channel.send(
                embed=embed,
                components=[disnake.ui.ActionRow(*buttons[:5])],
                files=files,
            )
        except disnake.HTTPException:
            return None

    async def _start_order_payment(self, guild: disnake.Guild, order_id: str) -> tuple[bool, str]:
        orders_doc = self._get_orders()
        order = orders_doc.get("orders", {}).get(order_id)
        if not order:
            return False, "Pedido nao encontrado."

        if order.get("payment_data"):
            return True, "Pagamento ja foi gerado."

        channel = guild.get_channel(int(order.get("channel_id") or 0))
        if not isinstance(channel, disnake.TextChannel):
            return False, "Canal do pedido nao encontrado."

        buyer = await self._resolve_discord_user(guild, int(order.get("user_id", 0)))
        if not buyer:
            return False, "Cliente Discord nao encontrado."

        config = self._get_config()
        calc = self._calculate(_as_int(order.get("quantidade"), 0), config)
        amount = self._order_price_value(order.get("tipo"), calc)
        description = f"Pedido Robux {order_id} - {_int_text(_as_int(order.get('quantidade'), 0))} Robux"

        try:
            raw_payment = await _create_payment(
                "pix",
                amount,
                buyer,
                description,
                cart_id=f"robux_{order_id}",
            )
        except Exception as exc:
            order["status"] = "payment_error"
            order["payment_error"] = str(exc)
            order["updated_at"] = disnake.utils.utcnow().isoformat()
            orders_doc["orders"][order_id] = order
            self._save_orders(orders_doc)
            await channel.send(f"{emoji.wrong} Nao consegui gerar o pagamento: {exc}")
            await self._send_log(guild, f"{emoji.wrong} Pedido Robux `{order_id}` falhou ao gerar pagamento: `{exc}`.")
            return False, str(exc)

        checkout_url, copy_code = _extract_urls(raw_payment or {})
        qr_bytes, qr_url = _extract_qr_image(raw_payment or {})
        ids = _extract_payment_ids(raw_payment or {})
        provider = (raw_payment or {}).get("_provider") or "pix"

        payment_data = {
            "method": "pix",
            "provider": provider,
            "amount": amount,
            "description": description,
            "checkout_url": checkout_url,
            "copy_code": copy_code,
            "qr_url": qr_url,
            "ids": ids,
            "raw": self._safe_payment_payload(raw_payment or {}),
            "created_at": disnake.utils.utcnow().isoformat(),
        }

        msg = await self._send_robux_payment_message(channel, order_id, order, payment_data, qr_bytes, qr_url)
        if msg:
            payment_data["message_id"] = msg.id

        order["status"] = "payment_pending"
        order["payment_data"] = payment_data
        order["updated_at"] = disnake.utils.utcnow().isoformat()
        orders_doc["orders"][order_id] = order
        self._save_orders(orders_doc)

        await self._send_log(
            guild,
            (
                f"{getattr(emoji, 'pix', '')} Pagamento PIX gerado para o pedido Robux `{order_id}`.\n"
                f"**Valor:** `{_money(amount)}`\n"
                f"**Provider:** `{provider}`\n"
                f"**Canal:** {channel.mention}"
            ),
        )
        asyncio.create_task(self._monitor_robux_payment(order_id))
        return True, "Pagamento gerado."

    async def _deliver_robux(self, guild: disnake.Guild, order_id: str, order: dict) -> dict:
        config = self._get_config()
        if not as_bool(config.get("auto_delivery_enabled"), True):
            return {"success": False, "pending": True, "reason": "Entrega automatica desativada no painel Robux."}

        profile = order.get("roblox_profile") or {}
        roblox_user_id = profile.get("id") or (order.get("group_check") or {}).get("roblox_user_id")
        if not roblox_user_id:
            return {"success": False, "pending": True, "reason": "ID Roblox do comprador nao encontrado."}

        group_id = config.get("delivery_group_id") or config.get("group_id")
        group_id = _as_int(group_id, 0)
        if group_id <= 0:
            return {
                "success": False,
                "pending": True,
                "reason": "Grupo de entrega nao configurado. Configure o ID do grupo no painel Robux.",
            }

        amount = _as_int(order.get("quantidade"), 0)
        if amount <= 0:
            return {"success": False, "pending": True, "reason": "Quantidade de Robux invalida."}

        return await self._roblox_group_payout(group_id, int(roblox_user_id), amount)

    async def _close_order_channel(self, guild: disnake.Guild, order: dict, reason: str) -> None:
        config = self._get_config()
        if not as_bool(config.get("delete_order_channel_on_finish"), True):
            return

        channel = guild.get_channel(int(order.get("channel_id") or 0))
        if not isinstance(channel, disnake.TextChannel):
            return

        try:
            await channel.send(f"{emoji.loading} {reason} Este canal sera fechado em 5 segundos...")
            await asyncio.sleep(5)
            await channel.delete(reason=reason)
        except disnake.HTTPException:
            pass

    async def _process_paid_order(self, guild: disnake.Guild, order_id: str, actor: Any | None = None, forced: bool = False) -> None:
        orders_doc = self._get_orders()
        order = orders_doc.get("orders", {}).get(order_id)
        if not order:
            return

        if order.get("status") in {"delivered", "delivery_pending"}:
            return

        order["status"] = "paid"
        order["paid_at"] = disnake.utils.utcnow().isoformat()
        if actor:
            order["paid_by"] = actor.id
        order["payment_forced"] = bool(forced)
        orders_doc["orders"][order_id] = order
        self._save_orders(orders_doc)

        channel = guild.get_channel(int(order.get("channel_id") or 0))
        await self._send_log(
            guild,
            (
                f"{emoji.correct} Pagamento Robux `{order_id}` aprovado.\n"
                f"**Cliente:** <@{order.get('user_id')}>\n"
                f"**Quantidade:** `{_int_text(_as_int(order.get('quantidade'), 0))} Robux`\n"
                f"**Aprovacao manual:** `{'Sim' if forced else 'Nao'}`"
            ),
        )
        if isinstance(channel, disnake.TextChannel):
            try:
                await channel.send(f"{emoji.correct} Pagamento do pedido `{order_id}` aprovado. Iniciando entrega dos Robux...")
            except disnake.HTTPException:
                pass

        delivery = await self._deliver_robux(guild, order_id, order)
        orders_doc = self._get_orders()
        order = orders_doc.get("orders", {}).get(order_id, order)
        order["delivery_result"] = delivery
        order["delivered_at" if delivery.get("success") else "delivery_updated_at"] = disnake.utils.utcnow().isoformat()
        order["status"] = "delivered" if delivery.get("success") else "delivery_pending"
        orders_doc["orders"][order_id] = order
        self._save_orders(orders_doc)

        buyer = await self._resolve_discord_user(guild, int(order.get("user_id", 0)))
        if delivery.get("success"):
            text = f"{emoji.correct} Pedido Robux `{order_id}` entregue automaticamente: `{_int_text(_as_int(order.get('quantidade'), 0))} Robux`."
            await self._send_log(guild, text)
            if isinstance(channel, disnake.TextChannel):
                try:
                    await channel.send(text)
                except disnake.HTTPException:
                    pass
            if buyer:
                try:
                    await buyer.send(text)
                except disnake.HTTPException:
                    pass
            asyncio.create_task(self._close_order_channel(guild, order, f"Pedido Robux {order_id} entregue"))
            return

        reason = delivery.get("reason") or "Entrega automatica pendente."
        text = (
            f"{emoji.warn} Pedido Robux `{order_id}` pago, mas a entrega automatica ficou pendente.\n"
            f"**Motivo:** {reason}\n"
            "A staff precisa concluir a entrega manualmente ou ajustar a configuracao de payout."
        )
        await self._send_log(guild, text)
        if isinstance(channel, disnake.TextChannel):
            try:
                await channel.send(text)
            except disnake.HTTPException:
                pass

    async def _monitor_robux_payment(self, order_id: str) -> None:
        intervals = [(120, 10), (300, 10), (600, 20), (1200, 30), (3600, 60)]
        started_at = time.time()

        while time.time() - started_at < 3600:
            current_interval = 60
            elapsed = time.time() - started_at
            for limit, interval in intervals:
                if elapsed < limit:
                    current_interval = interval
                    break
            await asyncio.sleep(current_interval)

            orders_doc = self._get_orders()
            order = orders_doc.get("orders", {}).get(order_id)
            if not order or order.get("status") in {"cancelled", "delivered", "delivery_pending"}:
                return

            guild = self.bot.get_guild(int(order.get("guild_id", 0)))
            if not guild:
                return

            payment_data = order.get("payment_data") or {}
            payment_id = self._select_payment_id(payment_data)
            if not payment_id:
                continue

            finished, final_status = await _check_single_payment_status(
                order_id,
                payment_id,
                payment_data.get("method", "pix"),
                payment_data.get("provider"),
                self.bot,
            )
            if not finished:
                continue

            if final_status == "approved":
                await self._process_paid_order(guild, order_id)
                return

            order["status"] = "payment_failed"
            order["payment_status"] = final_status
            order["updated_at"] = disnake.utils.utcnow().isoformat()
            orders_doc["orders"][order_id] = order
            self._save_orders(orders_doc)
            await self._send_log(guild, f"Pedido Robux `{order_id}` finalizado como `{final_status}`.")
            return

    async def _cancel_order(self, inter: disnake.MessageInteraction, order_id: str) -> None:
        orders_doc = self._get_orders()
        order = orders_doc.get("orders", {}).get(order_id)
        if not order:
            await inter.followup.send(f"{emoji.wrong} Pedido nao encontrado.", ephemeral=True)
            return

        is_staff = await perms.check(inter.user.id) or inter.user.guild_permissions.manage_guild
        is_buyer = int(order.get("user_id", 0)) == inter.user.id
        if not is_staff and not is_buyer:
            await inter.followup.send(f"{emoji.wrong} Voce nao tem permissao para cancelar este pedido.", ephemeral=True)
            return

        if order.get("status") in {"delivered"} and not is_staff:
            await inter.followup.send(f"{emoji.wrong} Este pedido ja foi entregue.", ephemeral=True)
            return

        order["status"] = "cancelled"
        order["cancelled_at"] = disnake.utils.utcnow().isoformat()
        order["cancelled_by"] = inter.user.id
        orders_doc["orders"][order_id] = order
        self._save_orders(orders_doc)

        await inter.followup.send(f"{emoji.correct} Pedido `{order_id}` cancelado.", ephemeral=True)
        await self._send_log(inter.guild, f"Pedido Robux `{order_id}` cancelado por {inter.user.mention}.")
        asyncio.create_task(self._close_order_channel(inter.guild, order, f"Pedido Robux {order_id} cancelado"))

    async def _check_order_payment_now(self, inter: disnake.MessageInteraction, order_id: str) -> None:
        orders_doc = self._get_orders()
        order = orders_doc.get("orders", {}).get(order_id)
        if not order:
            await inter.followup.send(f"{emoji.wrong} Pedido nao encontrado.", ephemeral=True)
            return

        is_staff = await perms.check(inter.user.id) or inter.user.guild_permissions.manage_guild
        is_buyer = int(order.get("user_id", 0)) == inter.user.id
        if not is_staff and not is_buyer:
            await inter.followup.send(f"{emoji.wrong} Voce nao tem permissao para verificar este pedido.", ephemeral=True)
            return

        payment_data = order.get("payment_data") or {}
        payment_id = self._select_payment_id(payment_data)
        if not payment_id:
            await inter.followup.send(f"{emoji.wrong} Este pedido ainda nao tem pagamento gerado.", ephemeral=True)
            return

        finished, final_status = await _check_single_payment_status(
            order_id,
            payment_id,
            payment_data.get("method", "pix"),
            payment_data.get("provider"),
            self.bot,
        )
        if finished and final_status == "approved":
            await inter.followup.send(f"{emoji.correct} Pagamento aprovado. Vou iniciar a entrega automaticamente.", ephemeral=True)
            await self._process_paid_order(inter.guild, order_id, inter.user)
            return

        if finished:
            order["status"] = "payment_failed"
            order["payment_status"] = final_status
            order["updated_at"] = disnake.utils.utcnow().isoformat()
            orders_doc["orders"][order_id] = order
            self._save_orders(orders_doc)
            await inter.followup.send(f"{emoji.wrong} Pagamento finalizado como `{final_status}`.", ephemeral=True)
            return

        await inter.followup.send(f"{emoji.loading} Pagamento ainda pendente. Assim que aprovar, o bot entrega automaticamente.", ephemeral=True)

    async def _create_order_channel(
        self,
        inter: disnake.MessageInteraction,
        order_id: str,
        quantidade: int,
        tipo: str,
        roblox_user: str,
        observacao: str,
        group_check: dict | None = None,
        roblox_profile: dict | None = None,
    ) -> disnake.TextChannel | None:
        config = self._get_config()
        category = inter.guild.get_channel(int(config["category_id"])) if config.get("category_id") else None
        if category is not None and not isinstance(category, disnake.CategoryChannel):
            category = None

        overwrites = {
            inter.guild.default_role: disnake.PermissionOverwrite(view_channel=False),
            inter.user: disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            inter.guild.me: disnake.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }

        for role in inter.guild.roles:
            if role.permissions.administrator:
                overwrites[role] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            channel = await inter.guild.create_text_channel(
                name=f"robux-{_clean_channel_name(inter.user.name)}-{order_id[:4]}",
                category=category,
                overwrites=overwrites,
                reason=f"Pedido Robux {order_id}",
            )
        except disnake.HTTPException:
            return None

        calc = self._calculate(quantidade, config)
        children = [
            disnake.ui.TextDisplay(f"## Pedido Robux `{order_id}`"),
            disnake.ui.TextDisplay(
                f"**Cliente:** {inter.user.mention}\n"
                f"**Quantidade:** `{_int_text(quantidade)} Robux`\n"
                f"**Tipo:** `{tipo}`\n"
                f"**Roblox:** {self._format_roblox_profile(roblox_profile, roblox_user)}\n"
                f"**Estimativa com taxa:** `{_money(calc['com_taxa']['preco'])}`\n"
                f"**Gamepass necessaria:** `{_int_text(calc['com_taxa']['gamepass'])} Robux`\n"
                f"**Observacao:** {observacao or '`Nenhuma`'}\n\n"
                f"{self._format_group_check(group_check)}"
            ),
        ]
        if roblox_profile and roblox_profile.get("avatar_url"):
            children.append(
                disnake.ui.MediaGallery(
                    disnake.MediaGalleryItem(
                        media=roblox_profile["avatar_url"],
                        description=f"Avatar Roblox de {roblox_profile.get('name', roblox_user)}",
                    )
                )
            )
        children.extend(
            [
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Forcar Pago", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "correct", None), custom_id=f"Robux_OrderPaid:{order_id}"),
                    disnake.ui.Button(label="Cancelar Pedido", style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "wrong", None), custom_id=f"Robux_OrderCancel:{order_id}"),
                ),
            ]
        )

        components = [disnake.ui.Container(*children, accent_colour=disnake.Colour.green())]
        await channel.send(components=components, flags=disnake.MessageFlags(is_components_v2=True))
        return channel

    async def _create_order(
        self,
        inter: disnake.ModalInteraction,
        quantidade: int,
        tipo: str,
        roblox_user: str,
        observacao: str,
        roblox_profile: dict | None = None,
        response_already_deferred: bool = False,
    ):
        config = self._get_config()
        min_robux = _as_int(config.get("minimo_robux"), DEFAULT_CONFIG["minimo_robux"])
        max_robux = _as_int(config.get("maximo_robux"), DEFAULT_CONFIG["maximo_robux"])
        if quantidade < min_robux or quantidade > max_robux:
            await inter.response.send_message(
                f"{emoji.wrong} A quantidade precisa ficar entre `{min_robux}` e `{max_robux}` Robux.",
                ephemeral=True,
            )
            return

        if not response_already_deferred:
            await inter.response.defer(ephemeral=True)
        group_check = None
        if _is_group_order(tipo):
            group_check = await self._verify_group_purchase(roblox_user, config)
            if not group_check.get("allowed", True):
                await self._send_log(
                    inter.guild,
                    (
                        f"Pedido Robux via grupo bloqueado para {inter.user.mention}.\n"
                        f"{self._format_group_check(group_check)}"
                    ),
                )
                await inter.followup.send(
                    f"{emoji.wrong} Nao foi possivel abrir o pedido via grupo.\n{self._format_group_check(group_check)}",
                    ephemeral=True,
                )
                return

        order_id = uuid.uuid4().hex[:8].upper()
        channel = await self._create_order_channel(
            inter,
            order_id,
            quantidade,
            tipo,
            roblox_user,
            observacao,
            group_check,
            roblox_profile,
        )

        orders_doc = self._get_orders()
        orders_doc["orders"][order_id] = {
            "id": order_id,
            "guild_id": inter.guild.id,
            "user_id": inter.user.id,
            "quantidade": quantidade,
            "tipo": tipo,
            "roblox_user": roblox_user,
            "roblox_profile": roblox_profile or {},
            "observacao": observacao,
            "group_check": group_check,
            "status": "open",
            "channel_id": channel.id if channel else None,
            "created_at": disnake.utils.utcnow().isoformat(),
        }
        self._save_orders(orders_doc)

        calc = self._calculate(quantidade, config)
        log_components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## Novo pedido Robux `{order_id}`"),
                disnake.ui.TextDisplay(
                    f"**Cliente:** {inter.user.mention} (`{inter.user.id}`)\n"
                    f"**Quantidade:** `{_int_text(quantidade)} Robux`\n"
                    f"**Tipo:** `{tipo}`\n"
                    f"**Roblox:** {self._format_roblox_profile(roblox_profile, roblox_user)}\n"
                    f"**Estimativa com taxa:** `{_money(calc['com_taxa']['preco'])}`\n"
                    f"**Canal:** {channel.mention if channel else '`Nao criado`'}\n\n"
                    f"{self._format_group_check(group_check)}"
                ),
                accent_colour=disnake.Colour.green(),
            )
        ]
        await self._send_log(inter.guild, components=log_components)

        payment_note = ""
        if channel and as_bool(config.get("auto_payment_enabled"), True):
            payment_ok, payment_msg = await self._start_order_payment(inter.guild, order_id)
            if payment_ok:
                payment_note = "\nPagamento PIX gerado automaticamente no canal do pedido."
            else:
                payment_note = f"\nNao consegui gerar o pagamento automatico: {payment_msg}"
        elif channel:
            payment_note = "\nPagamento automatico desativado no painel Robux."

        extra = f"\nCanal do pedido: {channel.mention}" if channel else "\nO pedido foi registrado nos logs."
        await inter.followup.send(f"{emoji.correct} Pedido `{order_id}` criado com sucesso.{extra}{payment_note}", ephemeral=True)

    def _values_modal(self):
        config = self._get_config()

        class ValuesModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Configurar Robux",
                    custom_id="Robux_ValuesModal",
                    components=[
                        disnake.ui.TextInput(label="Valor Robux / 1000", custom_id="valor_robux", value=str(config.get("valor_robux", 32)), max_length=12),
                        disnake.ui.TextInput(label="Valor Gamepass / 1000", custom_id="valor_gamepass", value=str(config.get("valor_gamepass", 42)), max_length=12),
                        disnake.ui.TextInput(label="Valor Grupo / 1000", custom_id="valor_grupo", value=str(config.get("valor_grupo", 37.76)), required=False, max_length=12),
                        disnake.ui.TextInput(label="Minimo Robux", custom_id="minimo", value=str(config.get("minimo_robux", 100)), max_length=8),
                        disnake.ui.TextInput(label="Maximo Robux", custom_id="maximo", value=str(config.get("maximo_robux", 20000)), max_length=8),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                new_config = self._get_config()
                new_config["valor_robux"] = _as_float(values.get("valor_robux"), DEFAULT_CONFIG["valor_robux"])
                new_config["valor_gamepass"] = _as_float(values.get("valor_gamepass"), DEFAULT_CONFIG["valor_gamepass"])
                new_config["valor_grupo"] = _as_float(values.get("valor_grupo"), new_config["valor_robux"] * 1.18)
                new_config["minimo_robux"] = _as_int(values.get("minimo"), DEFAULT_CONFIG["minimo_robux"])
                new_config["maximo_robux"] = _as_int(values.get("maximo"), DEFAULT_CONFIG["maximo_robux"])
                self._save_config(new_config)
                await modal_inter.response.send_message(f"{emoji.correct} Valores do sistema Robux salvos.", ephemeral=True)

        return ValuesModal()

    def _group_config_modal(self):
        config = self._get_config()

        class GroupConfigModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Verificacao de Grupo",
                    custom_id="Robux_GroupConfigModal",
                    components=[
                        disnake.ui.TextInput(
                            label="Ativar verificacao? (sim/nao)",
                            custom_id="enabled",
                            value="sim" if as_bool(config.get("group_verification_enabled"), False) else "nao",
                            max_length=10,
                        ),
                        disnake.ui.TextInput(
                            label="ID do grupo Roblox",
                            custom_id="group_id",
                            value=str(config.get("group_id") or ""),
                            required=False,
                            max_length=20,
                        ),
                        disnake.ui.TextInput(
                            label="Dias minimos no grupo",
                            custom_id="min_days",
                            value=str(config.get("group_min_days", DEFAULT_CONFIG["group_min_days"])),
                            max_length=5,
                        ),
                        disnake.ui.TextInput(
                            label="Bloquear se nao cumprir? (sim/nao)",
                            custom_id="block_orders",
                            value="sim" if as_bool(config.get("group_block_orders"), True) else "nao",
                            max_length=10,
                        ),
                        disnake.ui.TextInput(
                            label="Entrega automatica? (sim/nao)",
                            custom_id="auto_delivery",
                            value="sim" if as_bool(config.get("auto_delivery_enabled"), True) else "nao",
                            max_length=10,
                        ),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                new_config = self._get_config()
                group_id = _as_int(values.get("group_id"), 0)
                new_config["group_verification_enabled"] = as_bool(values.get("enabled"), False)
                new_config["group_id"] = group_id if group_id > 0 else None
                new_config["group_min_days"] = max(0, _as_int(values.get("min_days"), DEFAULT_CONFIG["group_min_days"]))
                new_config["group_block_orders"] = as_bool(values.get("block_orders"), True)
                new_config["auto_delivery_enabled"] = as_bool(values.get("auto_delivery"), True)
                self._save_config(new_config)
                await modal_inter.response.send_message(
                    f"{emoji.correct} Verificacao de grupo salva.\n{self._group_config_text(new_config)}",
                    ephemeral=True,
                )

        return GroupConfigModal()

    def _group_test_modal(self):
        class GroupTestModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Testar Usuario no Grupo",
                    custom_id="Robux_GroupTestModal",
                    components=[
                        disnake.ui.TextInput(
                            label="Usuario, ID ou link Roblox",
                            custom_id="roblox_user",
                            max_length=100,
                            placeholder="Ex: builderman ou 156",
                        ),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                await modal_inter.response.defer(ephemeral=True)
                test_config = self._get_config()
                test_config["group_verification_enabled"] = True
                check = await self._verify_group_purchase(values.get("roblox_user", ""), test_config)
                await modal_inter.followup.send(self._format_group_check(check), ephemeral=True)

        return GroupTestModal()

    def _calc_modal(self):
        class CalcModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Calcular Robux",
                    custom_id="Robux_CalcModal",
                    components=[
                        disnake.ui.TextInput(label="Quantidade de Robux", custom_id="quantidade", max_length=8, placeholder="Ex: 1500"),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                quantidade = _as_int(values.get("quantidade"), 0)
                if quantidade <= 0:
                    await modal_inter.response.send_message(f"{emoji.wrong} Informe uma quantidade valida.", ephemeral=True)
                    return
                await modal_inter.response.send_message(
                    components=self._calculator_components(quantidade),
                    ephemeral=True,
                    flags=disnake.MessageFlags(is_components_v2=True),
                )

        return CalcModal()

    def _buy_modal(self, defaults: dict | None = None):
        defaults = defaults or {}

        class BuyModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Comprar Robux",
                    custom_id="Robux_BuyModal",
                    components=[
                        disnake.ui.TextInput(
                            label="Quantidade de Robux",
                            custom_id="quantidade",
                            value=str(defaults.get("quantidade") or "") or None,
                            max_length=8,
                            placeholder="Ex: 1500",
                        ),
                        disnake.ui.TextInput(
                            label="Tipo",
                            custom_id="tipo",
                            value=str(defaults.get("tipo") or "com taxa"),
                            max_length=30,
                            placeholder="com taxa, sem taxa, grupo, gamepass",
                        ),
                        disnake.ui.TextInput(
                            label="Usuario Roblox",
                            custom_id="roblox_user",
                            value=str(defaults.get("roblox_user") or "") or None,
                            max_length=80,
                        ),
                        disnake.ui.TextInput(
                            label="Observacao/Gamepass",
                            custom_id="observacao",
                            value=str(defaults.get("observacao") or "") or None,
                            style=disnake.TextInputStyle.paragraph,
                            required=False,
                            max_length=500,
                        ),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                quantidade = _as_int(values.get("quantidade"), 0)
                await self._show_roblox_confirmation(
                    modal_inter,
                    quantidade,
                    values.get("tipo", "com taxa").strip() or "com taxa",
                    values.get("roblox_user", "").strip() or "Nao informado",
                    values.get("observacao", "").strip(),
                )

        return BuyModal()

    async def _send_public_panel_to(self, inter: disnake.MessageInteraction, channel_id: int):
        channel = inter.guild.get_channel(int(channel_id))
        if not isinstance(channel, disnake.TextChannel):
            await inter.response.send_message(f"{emoji.wrong} Canal invalido.", ephemeral=True)
            return

        config = self._get_config()
        config["public_channel_id"] = int(channel_id)
        self._save_config(config)
        await channel.send(
            components=self._public_panel_components(config),
            flags=disnake.MessageFlags(is_components_v2=True),
        )
        await inter.response.send_message(f"{emoji.correct} Painel Robux enviado em {channel.mention}.", ephemeral=True)

    async def _set_order_status(self, inter: disnake.MessageInteraction, order_id: str, status: str):
        if not await perms.check(inter.user.id) and not inter.user.guild_permissions.manage_guild:
            await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para alterar pedidos.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        orders_doc = self._get_orders()
        order = orders_doc.get("orders", {}).get(order_id)
        if not order:
            await inter.followup.send(f"{emoji.wrong} Pedido nao encontrado.", ephemeral=True)
            return

        if status == "paid":
            await inter.followup.send(
                f"{emoji.correct} Pedido `{order_id}` marcado como pago. Vou iniciar a entrega automatica.",
                ephemeral=True,
            )
            await self._send_log(inter.guild, f"Pedido Robux `{order_id}` forcado como pago por {inter.user.mention}.")
            await self._process_paid_order(inter.guild, order_id, inter.user, forced=True)
            return

        if status == "cancelled":
            order["status"] = "cancelled"
            order["cancelled_at"] = disnake.utils.utcnow().isoformat()
            order["cancelled_by"] = inter.user.id
            order["updated_at"] = disnake.utils.utcnow().isoformat()
            orders_doc["orders"][order_id] = order
            self._save_orders(orders_doc)

            await inter.followup.send(f"{emoji.correct} Pedido `{order_id}` cancelado.", ephemeral=True)
            await self._send_log(inter.guild, f"Pedido Robux `{order_id}` cancelado por {inter.user.mention}.")
            asyncio.create_task(self._close_order_channel(inter.guild, order, f"Pedido Robux {order_id} cancelado"))
            return

        order["status"] = status
        order["updated_at"] = disnake.utils.utcnow().isoformat()
        order["updated_by"] = inter.user.id
        self._save_orders(orders_doc)

        label = "pago" if status == "paid" else "cancelado"
        await inter.followup.send(f"{emoji.correct} Pedido `{order_id}` marcado como `{label}`.", ephemeral=True)
        await self._send_log(inter.guild, f"Pedido Robux `{order_id}` marcado como `{label}` por {inter.user.mention}.")

        buyer = inter.guild.get_member(int(order.get("user_id", 0)))
        if buyer:
            try:
                await buyer.send(f"Seu pedido Robux `{order_id}` foi marcado como `{label}`.")
            except disnake.HTTPException:
                pass

    @commands.Cog.listener("on_message_interaction")
    async def Robux_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Robux_"):
            return

        if custom_id == "Robux_Toggle":
            await inter.response.defer(ephemeral=True)
            config = self._get_config()
            config["enabled"] = not as_bool(config.get("enabled"), False)
            self._save_config(config)
            await self._refresh_admin_panel(inter)
            await inter.followup.send(f"{emoji.correct} Sistema Robux {'ativado' if config['enabled'] else 'desativado'}.", ephemeral=True)
            return

        if custom_id == "Robux_ConfigValores":
            await inter.response.send_modal(self._values_modal())
            return

        if custom_id == "Robux_ConfigGrupo":
            await inter.response.send_modal(self._group_config_modal())
            return

        if custom_id == "Robux_TestGrupo":
            await inter.response.send_modal(self._group_test_modal())
            return

        if custom_id == "Robux_ConfigCanais":
            await inter.response.send_message(
                "Configure os canais do sistema Robux.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Canal da calculadora automatica",
                            custom_id="Robux_SelectChannel:calculator_channel_id",
                            channel_types=[disnake.ChannelType.text],
                        )
                    ),
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Canal de logs/pedidos",
                            custom_id="Robux_SelectChannel:log_channel_id",
                            channel_types=[disnake.ChannelType.text],
                        )
                    ),
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Categoria dos carrinhos",
                            custom_id="Robux_SelectChannel:category_id",
                            channel_types=[disnake.ChannelType.category],
                        )
                    ),
                ],
                ephemeral=True,
            )
            return

        if custom_id.startswith("Robux_SelectChannel:"):
            field = custom_id.split(":", 1)[1]
            config = self._get_config()
            config[field] = int(inter.values[0])
            self._save_config(config)
            await inter.response.send_message(f"{emoji.correct} Configuracao salva: <#{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "Robux_SendPanel":
            await inter.response.send_message(
                "Selecione o canal onde o painel publico de Robux sera enviado.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            placeholder="Canal do painel Robux",
                            custom_id="Robux_SendPanel_Select",
                            channel_types=[disnake.ChannelType.text],
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Robux_SendPanel_Select":
            await self._send_public_panel_to(inter, int(inter.values[0]))
            return

        if custom_id == "Robux_Preview":
            await inter.response.send_message(
                components=self._public_panel_components(),
                ephemeral=True,
                flags=disnake.MessageFlags(is_components_v2=True),
            )
            return

        if custom_id == "Robux_PublicCalc":
            await inter.response.send_modal(self._calc_modal())
            return

        if custom_id == "Robux_PublicBuy":
            config = self._get_config()
            if not as_bool(config.get("enabled"), False):
                await inter.response.send_message(f"{emoji.wrong} O sistema Robux esta desativado.", ephemeral=True)
                return
            await inter.response.send_modal(self._buy_modal())
            return

        if custom_id.startswith("Robux_Confirm:"):
            token = custom_id.split(":", 1)[1]
            self._cleanup_pending_confirmations()
            pending = self._pending_confirmations.pop(token, None)
            if not pending:
                await inter.response.send_message(f"{emoji.wrong} Esta confirmacao expirou. Abra a compra novamente.", ephemeral=True)
                return
            if pending.get("user_id") != inter.user.id or pending.get("guild_id") != inter.guild.id:
                await inter.response.send_message(f"{emoji.wrong} Essa confirmacao pertence a outro usuario.", ephemeral=True)
                return

            await inter.response.defer(ephemeral=True)
            try:
                await inter.edit_original_message(
                    components=[
                        disnake.ui.Container(
                            disnake.ui.TextDisplay(f"{emoji.loading} Criando seu pedido Robux..."),
                            accent_colour=disnake.Colour.green(),
                        )
                    ]
                )
            except disnake.HTTPException:
                pass

            await self._create_order(
                inter,
                pending["quantidade"],
                pending["tipo"],
                pending["roblox_user"],
                pending["observacao"],
                pending.get("roblox_profile"),
                response_already_deferred=True,
            )
            return

        if custom_id.startswith("Robux_EditConfirm:"):
            token = custom_id.split(":", 1)[1]
            self._cleanup_pending_confirmations()
            pending = self._pending_confirmations.pop(token, None)
            if not pending:
                await inter.response.send_message(f"{emoji.wrong} Esta confirmacao expirou. Abra a compra novamente.", ephemeral=True)
                return
            if pending.get("user_id") != inter.user.id or pending.get("guild_id") != inter.guild.id:
                await inter.response.send_message(f"{emoji.wrong} Essa confirmacao pertence a outro usuario.", ephemeral=True)
                return
            await inter.response.send_modal(self._buy_modal(pending))
            return

        if custom_id.startswith("Robux_CancelConfirm:"):
            token = custom_id.split(":", 1)[1]
            self._pending_confirmations.pop(token, None)
            await inter.response.edit_message(
                components=[
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(f"{emoji.wrong} Pedido Robux cancelado."),
                        accent_colour=disnake.Colour.red(),
                    )
                ]
            )
            return

        if custom_id.startswith("Robux_CopyPix:"):
            order_id = custom_id.split(":", 1)[1]
            order = self._get_orders().get("orders", {}).get(order_id) or {}
            copy_code = ((order.get("payment_data") or {}).get("copy_code") or "").strip()
            if not copy_code:
                await inter.response.send_message(f"{emoji.wrong} Codigo PIX nao encontrado para este pedido.", ephemeral=True)
                return
            await inter.response.send_message(copy_code, ephemeral=True)
            return

        if custom_id.startswith("Robux_CheckPayment:"):
            await inter.response.defer(ephemeral=True)
            await self._check_order_payment_now(inter, custom_id.split(":", 1)[1])
            return

        if custom_id.startswith("Robux_OrderPaid:"):
            await self._set_order_status(inter, custom_id.split(":", 1)[1], "paid")
            return

        if custom_id.startswith("Robux_OrderCancel:"):
            await inter.response.defer(ephemeral=True)
            await self._cancel_order(inter, custom_id.split(":", 1)[1])
            return

    @commands.Cog.listener("on_message")
    async def Robux_Auto_Calculator(self, msg: disnake.Message):
        if msg.author.bot or not msg.guild:
            return

        config = self._get_config()
        if not as_bool(config.get("enabled"), False):
            return

        calculator_channel_id = config.get("calculator_channel_id")
        if not calculator_channel_id or msg.channel.id != int(calculator_channel_id):
            return

        content = msg.content.strip().replace(".", "").replace(",", "")
        if not content.isdigit():
            return

        quantidade = int(content)
        min_robux = _as_int(config.get("minimo_robux"), DEFAULT_CONFIG["minimo_robux"])
        max_robux = _as_int(config.get("maximo_robux"), DEFAULT_CONFIG["maximo_robux"])
        if quantidade < min_robux or quantidade > max_robux:
            return

        try:
            await msg.channel.send(
                components=self._calculator_components(quantidade, config),
                flags=disnake.MessageFlags(is_components_v2=True),
            )
        except disnake.HTTPException:
            pass


def setup(bot: commands.Bot):
    bot.add_cog(RobuxPanel(bot))
