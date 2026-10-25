import secrets
from datetime import datetime, timedelta, timezone

import disnake
from disnake.ext import commands

from functions import auto_setup
from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import load_guild_channels, save_guild_channels
from functions.system_logs import send_system_log


def resolve_custom_emoji(value, bot=None, fallback=""):
    raw = str(value or "").strip()
    if not raw:
        return fallback
    if raw.startswith("<") and raw.endswith(">"):
        return raw
    if raw.isdigit():
        emoji_id = int(raw)
        for stored in getattr(bot, "emojis", []) or []:
            if int(getattr(stored, "id", 0) or 0) == emoji_id:
                return str(stored)
        return fallback
    return raw


def button_style(value):
    return {"green": disnake.ButtonStyle.green, "verde": disnake.ButtonStyle.green, "blue": disnake.ButtonStyle.blurple, "azul": disnake.ButtonStyle.blurple, "red": disnake.ButtonStyle.red, "vermelho": disnake.ButtonStyle.red, "gray": disnake.ButtonStyle.grey, "grey": disnake.ButtonStyle.grey, "cinza": disnake.ButtonStyle.grey, "dark": disnake.ButtonStyle.secondary, "escuro": disnake.ButtonStyle.secondary}.get(str(value or "verde").lower(), disnake.ButtonStyle.green)


def internal_emoji(name, fallback=""):
    value = getattr(emoji, name, None)
    if value:
        return value
    fallback_value = getattr(emoji, fallback, None) if fallback else None
    return fallback_value or fallback


DATA_PATH = "database/keys_system.json"
DEFAULT_TITLE = "Resgate sua Key"
DEFAULT_DESCRIPTION = "Resgate uma key válida para liberar seu acesso."
DEFAULT_EXPIRED_MESSAGE = "Esta key expirou e não pode mais ser resgatada."

STATUS_LABELS = {"active": "Key ativa", "redeemed": "Key resgatada", "expired": "Key expirada", "revoked": "Key revogada"}
STATUS_EMOJIS = {"active": getattr(emoji, "correct", "✅"), "redeemed": getattr(emoji, "save", "💾"), "expired": getattr(emoji, "clock", "🕒"), "revoked": getattr(emoji, "delete", "🗑️")}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def numeric_id(value):
    raw = str(value or "").strip().replace("<#", "").replace("<@&", "").replace(">", "")
    return raw if raw.isdigit() else ""


def status_of(item):
    if item.get("status") == "active" and item.get("expires_at"):
        expires = parse_dt(item["expires_at"])
        if expires and expires <= datetime.now(timezone.utc):
            return "expired"
    return str(item.get("status") or "active")


class KeysConfigModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        cfg = cog.config()
        super().__init__(title="Editar painel de Keys", custom_id="Keys_EditPanelModal", components=[
            disnake.ui.TextInput(label="Título do painel", custom_id="title", value=str(cfg.get("title", DEFAULT_TITLE))[:100], max_length=100),
            disnake.ui.TextInput(label="Descrição", custom_id="description", style=disnake.TextInputStyle.paragraph, value=str(cfg.get("description", DEFAULT_DESCRIPTION))[:900], max_length=900),
            disnake.ui.TextInput(label="ID ou emoji do título", custom_id="title_emoji", value=str(cfg.get("title_emoji", "🔑"))[:30], max_length=30, required=False),
        ])

    async def callback(self, inter):
        values = inter.text_values
        self.cog.update_config({"title": str(values.get("title") or DEFAULT_TITLE).strip()[:100], "description": str(values.get("description") or DEFAULT_DESCRIPTION).strip()[:900], "title_emoji": str(values.get("title_emoji") or "🔑").strip()[:30]})
        await inter.response.send_message(f"{emoji.correct} Painel atualizado. Use **Publicar** para enviar a nova versão.", ephemeral=True)


class KeysButtonModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        cfg = cog.config()
        super().__init__(title="Editar botão de resgate", custom_id="Keys_ButtonModal", components=[
            disnake.ui.TextInput(label="Nome do botão", custom_id="button_label", value=str(cfg.get("button_label", "Resgatar Key"))[:80], max_length=80),
            disnake.ui.TextInput(label="ID ou emoji do botão", custom_id="button_emoji", value=str(cfg.get("button_emoji", "✅"))[:30], max_length=30, required=False),
            disnake.ui.TextInput(label="Cor: verde, azul, vermelho, cinza ou escuro", custom_id="button_color", value={"green": "verde", "blue": "azul", "red": "vermelho", "gray": "cinza", "grey": "cinza", "dark": "escuro"}.get(str(cfg.get("button_color", "green")).lower(), "verde"), max_length=10),
        ])

    async def callback(self, inter):
        values = inter.text_values
        color_input = str(values.get("button_color") or "verde").strip().lower()
        colors = {"verde": "green", "green": "green", "azul": "blue", "blue": "blue", "vermelho": "red", "red": "red", "cinza": "gray", "gray": "gray", "grey": "gray", "escuro": "dark", "dark": "dark"}
        color = colors.get(color_input)
        if not color:
            await inter.response.send_message(f"{emoji.wrong} Cor inválida. Use `verde`, `azul`, `vermelho`, `cinza` ou `escuro`.", ephemeral=True)
            return
        self.cog.update_config({"button_label": str(values.get("button_label") or "Resgatar Key").strip()[:80], "button_emoji": str(values.get("button_emoji") or "✅").strip()[:30], "button_color": color})
        await inter.response.send_message(f"{emoji.correct} Botão de resgate atualizado.", ephemeral=True)


class KeysColorModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        cfg = cog.config()
        super().__init__(title="Editar cor do painel", custom_id="Keys_ColorModal", components=[disnake.ui.TextInput(label="Cor hexadecimal opcional", custom_id="color", value=str(cfg.get("color", "#5865F2"))[:7], placeholder="#5865F2; deixe vazio para remover", required=False, max_length=7)])

    async def callback(self, inter):
        raw = str(inter.text_values.get("color") or "").strip()
        if raw and not (len(raw) == 7 and raw.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in raw[1:])):
            await inter.response.send_message(f"{emoji.wrong} Informe uma cor hexadecimal válida, como `#5865F2`.", ephemeral=True)
            return
        self.cog.update_config({"color": raw})
        await inter.response.send_message(f"{emoji.correct} Cor do painel atualizada.", ephemeral=True)


class KeysBannerModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(title="Editar banner do painel", custom_id="Keys_BannerModal", components=[disnake.ui.TextInput(label="URL da imagem do banner", custom_id="banner_url", value=str(cog.config().get("banner_url") or "")[:500], placeholder="https://...", required=False, max_length=500)])

    async def callback(self, inter):
        url = str(inter.text_values.get("banner_url") or "").strip()
        if url and not url.startswith(("https://", "http://")):
            await inter.response.send_message(f"{emoji.wrong} O banner precisa ser uma URL válida.", ephemeral=True)
            return
        self.cog.update_config({"banner_url": url})
        await inter.response.send_message(f"{emoji.correct} Banner atualizado. Publique novamente para aplicar.", ephemeral=True)


class KeysExpirationModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(title="Mensagem de expiração", custom_id="Keys_ExpirationModal", components=[disnake.ui.TextInput(label="Mensagem enviada quando a key expira", custom_id="message", style=disnake.TextInputStyle.paragraph, value=str(cog.config().get("expired_message", DEFAULT_EXPIRED_MESSAGE))[:900], max_length=900)])

    async def callback(self, inter):
        self.cog.update_config({"expired_message": str(inter.text_values.get("message") or DEFAULT_EXPIRED_MESSAGE).strip()[:900]})
        await inter.response.send_message(f"{emoji.correct} Mensagem de expiração salva.", ephemeral=True)


class CreateKeysModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(title="Criar novas Keys", custom_id="Keys_CreateModal", components=[
            disnake.ui.TextInput(label="Quantidade", custom_id="quantity", value="1", max_length=3),
            disnake.ui.TextInput(label="Dias", custom_id="days", value="30", max_length=4),
            disnake.ui.TextInput(label="Horas", custom_id="hours", value="0", max_length=3),
            disnake.ui.TextInput(label="Minutos", custom_id="minutes", value="0", max_length=3),
            disnake.ui.TextInput(label="Segundos", custom_id="seconds", value="0", max_length=3),
        ])

    async def callback(self, inter):
        try:
            quantity = max(1, min(int(inter.text_values.get("quantity", "1")), 100))
            days = max(0, min(int(inter.text_values.get("days", "30")), 3650))
            hours = max(0, min(int(inter.text_values.get("hours", "0")), 23))
            minutes = max(0, min(int(inter.text_values.get("minutes", "0")), 59))
            seconds = max(0, min(int(inter.text_values.get("seconds", "0")), 59))
            if days == hours == minutes == seconds == 0:
                raise ValueError
        except ValueError:
            await inter.response.send_message(f"{emoji.wrong} Quantidade, dias, horas, minutos e segundos devem ser números válidos; a validade não pode ser zero.", ephemeral=True)
            return
        self.cog.pending_creations[str(inter.user.id)] = {"quantity": quantity, "days": days, "hours": hours, "minutes": minutes, "seconds": seconds, "prefix": "LYON"}
        await inter.response.send_message("Selecione o cargo que será entregue quando estas keys forem resgatadas.", components=[disnake.ui.ActionRow(disnake.ui.RoleSelect(custom_id="Keys_CreateRole", placeholder="Selecionar cargo", min_values=1, max_values=1))], ephemeral=True)


class KeyActionModal(disnake.ui.Modal):
    def __init__(self, cog, action):
        self.cog = cog; self.action = action
        super().__init__(title="Apagar Key" if action == "delete" else "Expirar Key", custom_id=f"Keys_{action}_Modal", components=[disnake.ui.TextInput(label="Key", custom_id="key", placeholder="LYON-XXXX-XXXX", max_length=80)])

    async def callback(self, inter):
        key = str(inter.text_values.get("key") or "").strip().upper()
        found = self.cog.change_key(key, "revoked" if self.action == "delete" else "expired", inter.user)
        if not found:
            await inter.response.send_message(f"{emoji.wrong} Key não encontrada.", ephemeral=True); return
        await self.cog._send_key_log("revoked" if self.action == "delete" else "expired", "Key revogada" if self.action == "delete" else "Key expirada", f"A key `{key}` foi {'revogada' if self.action == 'delete' else 'marcada como expirada' }.", actor=inter.user, guild=inter.guild)
        await inter.response.send_message(f"{emoji.correct} A key `{key}` foi {'apagada/revogada' if self.action == 'delete' else 'marcada como expirada'}.", ephemeral=True)


class RedeemKeyModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(title="Resgatar Key", custom_id="Keys_RedeemModal", components=[disnake.ui.TextInput(label="Digite sua Key", custom_id="key", placeholder="LYON-XXXX-XXXX", max_length=80)])

    async def callback(self, inter):
        key = str(inter.text_values.get("key") or "").strip().upper()
        result = self.cog.redeem_key(key, inter.user)
        if result == "expired":
            await inter.response.send_message(f"🟠 {self.cog.config().get('expired_message', DEFAULT_EXPIRED_MESSAGE)}", ephemeral=True); return
        if not result:
            await inter.response.send_message(f"{emoji.wrong} Esta key é inválida, já foi utilizada ou foi revogada.", ephemeral=True); return
        await self.cog._send_key_log("redeemed", "Key resgatada", f"A key `{key}` foi resgatada com sucesso.", actor=inter.user, guild=inter.guild)
        await inter.response.send_message(f"{emoji.correct} Key resgatada com sucesso. O cargo foi aplicado e os detalhes foram enviados por DM.", ephemeral=True)
        try:
            await inter.user.send(f"{emoji.correct} Sua key `{key}` foi resgatada com sucesso no servidor **{inter.guild.name if inter.guild else 'servidor'}**.")
        except Exception:
            pass


