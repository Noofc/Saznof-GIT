from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Any

import disnake
from disnake.ext import commands, tasks

from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import load_guild_channels
from functions.perms import perms
from functions.bool_utils import as_bool
from functions.system_logs import ensure_guild_log_channel
from .panel_v2 import build_panel_card, channel_label, configured_label, status_label


CONFIG_KEY = "moderacao_config"
WARNS_KEY_PREFIX = "moderation_warns_"


def _duration_to_seconds(value: str) -> int | None:
    value = (value or "").strip().lower()
    match = re.fullmatch(r"(\d+)\s*([smhd])", value)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return amount * multipliers[unit]


def _format_duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


class ModeradorPanel(commands.Cog):
    """Sistema de moderacao por componentes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not self.tempban_checker.is_running():
            self.tempban_checker.start()

    def cog_unload(self):
        self.tempban_checker.cancel()

    def _get_config(self) -> dict:
        config = db.get_document(CONFIG_KEY) or {}
        config.setdefault("enabled", False)
        config["enabled"] = as_bool(config.get("enabled"), False)
        config.setdefault("logs_channel_id", None)
        config.setdefault("report_channel_id", None)
        config.setdefault("moderator_role_id", None)
        config.setdefault("total_warns", 0)
        config.setdefault("total_mutes", 0)
        config.setdefault("total_bans", 0)
        return config

    def _save_config(self, config: dict) -> None:
        db.save_document(CONFIG_KEY, config)

    def _warns_key(self, guild_id: int) -> str:
        return f"{WARNS_KEY_PREFIX}{guild_id}"

    def _get_warns_doc(self, guild_id: int) -> dict:
        data = db.get_document(self._warns_key(guild_id)) or {}
        data.setdefault("users", {})
        return data

    def _save_warns_doc(self, guild_id: int, data: dict) -> None:
        db.save_document(self._warns_key(guild_id), data)

    async def _is_panel_admin(self, inter: disnake.MessageInteraction) -> bool:
        if await perms.check(inter.user.id):
            return True
        if getattr(inter.user.guild_permissions, "manage_guild", False):
            return True

        config = self._get_config()
        role_id = config.get("moderator_role_id")
        if role_id and any(role.id == int(role_id) for role in getattr(inter.user, "roles", [])):
            return True
        return False

    async def _require_panel_admin(self, inter: disnake.MessageInteraction) -> bool:
        if await self._is_panel_admin(inter):
            return True
        await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para usar a moderacao.", ephemeral=True)
        return False

    def _can_act_on(self, inter: disnake.MessageInteraction, member: disnake.Member, action: str) -> tuple[bool, str]:
        if member.id == inter.guild.owner_id:
            return False, "Voce nao pode aplicar isso no dono do servidor."
        if member.id == inter.user.id and action not in {"warns"}:
            return False, "Voce nao pode aplicar isso em voce mesmo."
        if inter.user.id != inter.guild.owner_id and inter.user.top_role <= member.top_role:
            return False, "O alvo possui cargo igual ou superior ao seu."
        if inter.guild.me.top_role <= member.top_role:
            return False, "Meu cargo esta abaixo do cargo do alvo."
        return True, ""

    async def _fetch_member(self, guild: disnake.Guild, user_id: int) -> disnake.Member | None:
        member = guild.get_member(int(user_id))
        if member:
            return member
        try:
            return await guild.fetch_member(int(user_id))
        except disnake.HTTPException:
            return None

    async def _send_log(self, guild: disnake.Guild, title: str, lines: list[str]):
        config = self._get_config()
        canais = load_guild_channels(guild)
        channel_id = config.get("logs_channel_id") or canais.get("canal_de_logs_de_castigos")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, disnake.TextChannel):
            channel = await ensure_guild_log_channel(guild)
        if not isinstance(channel, disnake.TextChannel):
            return

        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {title}"),
                disnake.ui.TextDisplay("\n".join(lines)),
                accent_colour=disnake.Colour.orange(),
            )
        ]
        try:
            await channel.send(components=components, flags=disnake.MessageFlags(is_components_v2=True))
        except disnake.HTTPException:
            pass

    def display_moderacao_panel(self, inter: disnake.MessageInteraction):
        config = self._get_config()

        return build_panel_card(
            title="Moderacao",
            breadcrumb="Painel > Moderacao",
            description="Gerencie punicoes, avisos, logs, cargo moderador e acoes em massa.",
            status_lines=[
                f"**Status:** {status_label(as_bool(config.get('enabled'), False))}",
                f"**Avisos aplicados:** `{config.get('total_warns', 0)}`",
                f"**Mutes aplicados:** `{config.get('total_mutes', 0)}`",
                f"**Banimentos:** `{config.get('total_bans', 0)}`",
                f"**Cargo moderador:** {configured_label(config.get('moderator_role_id'))}",
                f"**Canal logs:** {channel_label(config.get('logs_channel_id'))}",
                f"**Canal reports:** {channel_label(config.get('report_channel_id'))}",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Desativar" if as_bool(config.get("enabled"), False) else "Ativar",
                        style=disnake.ButtonStyle.danger if as_bool(config.get("enabled"), False) else disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "power", None),
                        custom_id="Moderacao_Toggle",
                    ),
                    disnake.ui.Button(label="Logs", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "receipt", None), custom_id="Moderacao_Logs"),
                    disnake.ui.Button(label="Reports", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "warn", None), custom_id="Moderacao_Reports"),
                    disnake.ui.Button(label="Cargo", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "role", None), custom_id="Moderacao_Roles"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Warn", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "warn", None), custom_id="Moderacao_Warn"),
                    disnake.ui.Button(label="Warns", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "receipt", None), custom_id="Moderacao_Warns"),
                    disnake.ui.Button(label="Mute", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "lock", None), custom_id="Moderacao_Mute"),
                    disnake.ui.Button(label="Unmute", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "unlock", None), custom_id="Moderacao_Unmute"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Slowmode", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "time", None), custom_id="Moderacao_Slowmode"),
                    disnake.ui.Button(label="Tempban", style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "ban", None), custom_id="Moderacao_Tempban"),
                    disnake.ui.Button(label="Softban", style=disnake.ButtonStyle.danger, emoji=getattr(emoji, "trash", None), custom_id="Moderacao_Softban"),
                    disnake.ui.Button(label="Cargo All", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "role", None), custom_id="Moderacao_CargoAll"),
                ),
            ],
        )

    async def _refresh_panel(self, inter: disnake.MessageInteraction):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.display_moderacao_panel(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    async def _apply_warn(self, inter: disnake.ModalInteraction, member_id: int, reason: str):
        member = await self._fetch_member(inter.guild, member_id)
        if not member:
            await inter.response.send_message(f"{emoji.wrong} Usuario nao encontrado.", ephemeral=True)
            return

        ok, error = self._can_act_on(inter, member, "warn")
        if not ok:
            await inter.response.send_message(f"{emoji.wrong} {error}", ephemeral=True)
            return

        warns_doc = self._get_warns_doc(inter.guild.id)
        user_warns = warns_doc["users"].setdefault(str(member.id), [])
        warn_id = uuid.uuid4().hex[:8].upper()
        user_warns.append(
            {
                "id": warn_id,
                "reason": reason,
                "moderator_id": inter.user.id,
                "created_at": disnake.utils.utcnow().isoformat(),
            }
        )
        self._save_warns_doc(inter.guild.id, warns_doc)

        config = self._get_config()
        config["total_warns"] = int(config.get("total_warns", 0)) + 1
        self._save_config(config)

        try:
            await member.send(
                f"Voce recebeu um aviso no servidor **{inter.guild.name}**.\n"
                f"Motivo: {reason}\nTotal de avisos: {len(user_warns)}"
            )
        except disnake.HTTPException:
            pass

        await self._send_log(
            inter.guild,
            "Warn Aplicado",
            [
                f"**Usuario:** {member.mention} (`{member.id}`)",
                f"**Moderador:** {inter.user.mention}",
                f"**Aviso:** `{warn_id}`",
                f"**Motivo:** {reason}",
                f"**Total:** `{len(user_warns)}`",
            ],
        )
        await inter.response.send_message(f"{emoji.correct} Aviso aplicado em {member.mention}. Total: `{len(user_warns)}`.", ephemeral=True)

    async def _show_warns(self, inter: disnake.MessageInteraction, member_id: int):
        member = await self._fetch_member(inter.guild, member_id)
        if not member:
            await inter.response.send_message(f"{emoji.wrong} Usuario nao encontrado.", ephemeral=True)
            return

        warns_doc = self._get_warns_doc(inter.guild.id)
        user_warns = warns_doc.get("users", {}).get(str(member.id), [])
        if not user_warns:
            await inter.response.send_message(f"{emoji.correct} {member.mention} nao possui avisos.", ephemeral=True)
            return

        lines = []
        for index, item in enumerate(user_warns[-10:], start=1):
            reason = item.get("reason", "Sem motivo")
            mod_id = item.get("moderator_id")
            lines.append(f"**{index}.** `{item.get('id')}` - {reason} - <@{mod_id}>")

        await inter.response.send_message(
            f"**Avisos de {member.mention}**\nTotal: `{len(user_warns)}`\n\n" + "\n".join(lines),
            ephemeral=True,
        )

    async def _apply_mute(self, inter: disnake.ModalInteraction, member_id: int, duration_text: str, reason: str):
        member = await self._fetch_member(inter.guild, member_id)
        seconds = _duration_to_seconds(duration_text)
        if not seconds or seconds <= 0:
            await inter.response.send_message(f"{emoji.wrong} Duracao invalida. Use `10m`, `1h`, `7d`.", ephemeral=True)
            return
        if seconds > 28 * 86400:
            await inter.response.send_message(f"{emoji.wrong} O mute do Discord permite no maximo 28 dias.", ephemeral=True)
            return
        if not member:
            await inter.response.send_message(f"{emoji.wrong} Usuario nao encontrado.", ephemeral=True)
            return

        ok, error = self._can_act_on(inter, member, "mute")
        if not ok:
            await inter.response.send_message(f"{emoji.wrong} {error}", ephemeral=True)
            return

        try:
            await member.timeout(duration=timedelta(seconds=seconds), reason=f"[Lyon] {reason} - {inter.user}")
        except disnake.HTTPException as exc:
            await inter.response.send_message(f"{emoji.wrong} Nao foi possivel mutar: `{exc}`", ephemeral=True)
            return

        config = self._get_config()
        config["total_mutes"] = int(config.get("total_mutes", 0)) + 1
        self._save_config(config)

        await self._send_log(
            inter.guild,
            "Mute Aplicado",
            [
                f"**Usuario:** {member.mention} (`{member.id}`)",
                f"**Moderador:** {inter.user.mention}",
                f"**Duracao:** `{_format_duration(seconds)}`",
                f"**Motivo:** {reason}",
            ],
        )
        await inter.response.send_message(f"{emoji.correct} {member.mention} foi mutado por `{_format_duration(seconds)}`.", ephemeral=True)

    async def _apply_unmute(self, inter: disnake.MessageInteraction, member_id: int):
        member = await self._fetch_member(inter.guild, member_id)
        if not member:
            await inter.response.send_message(f"{emoji.wrong} Usuario nao encontrado.", ephemeral=True)
            return
        try:
            await member.timeout(duration=None, reason=f"[Lyon] Unmute por {inter.user}")
        except disnake.HTTPException as exc:
            await inter.response.send_message(f"{emoji.wrong} Nao foi possivel remover mute: `{exc}`", ephemeral=True)
            return
        await self._send_log(
            inter.guild,
            "Unmute",
            [f"**Usuario:** {member.mention} (`{member.id}`)", f"**Moderador:** {inter.user.mention}"],
        )
        await inter.response.send_message(f"{emoji.correct} Mute removido de {member.mention}.", ephemeral=True)

    async def _apply_slowmode(self, inter: disnake.ModalInteraction, channel_id: int, duration_text: str):
        channel = inter.guild.get_channel(int(channel_id))
        if not isinstance(channel, disnake.TextChannel):
            await inter.response.send_message(f"{emoji.wrong} Canal invalido.", ephemeral=True)
            return
        if duration_text.strip() in {"0", "off", "desativar"}:
            seconds = 0
        else:
            seconds = _duration_to_seconds(duration_text)
        if seconds is None or seconds < 0 or seconds > 21600:
            await inter.response.send_message(f"{emoji.wrong} Tempo invalido. Use `0`, `5s`, `10m` ou ate `6h`.", ephemeral=True)
            return

        try:
            await channel.edit(slowmode_delay=seconds, reason=f"Slowmode por {inter.user}")
        except disnake.HTTPException as exc:
            await inter.response.send_message(f"{emoji.wrong} Nao foi possivel alterar slowmode: `{exc}`", ephemeral=True)
            return

        text = "desativado" if seconds == 0 else f"definido para `{_format_duration(seconds)}`"
        await inter.response.send_message(f"{emoji.correct} Slowmode de {channel.mention} {text}.", ephemeral=True)

    async def _apply_tempban(self, inter: disnake.ModalInteraction, member_id: int, duration_text: str, reason: str):
        member = await self._fetch_member(inter.guild, member_id)
        seconds = _duration_to_seconds(duration_text)
        if not seconds or seconds <= 0:
            await inter.response.send_message(f"{emoji.wrong} Duracao invalida. Use `1h`, `1d`, `7d`.", ephemeral=True)
            return
        if not member:
            await inter.response.send_message(f"{emoji.wrong} Usuario nao encontrado.", ephemeral=True)
            return

        ok, error = self._can_act_on(inter, member, "tempban")
        if not ok:
            await inter.response.send_message(f"{emoji.wrong} {error}", ephemeral=True)
            return

        try:
            await member.ban(reason=f"[TempBan {_format_duration(seconds)}] {reason}")
        except disnake.HTTPException as exc:
            await inter.response.send_message(f"{emoji.wrong} Nao foi possivel banir: `{exc}`", ephemeral=True)
            return

        data = db.get_document("moderation_tempbans") or {"items": []}
        items = data.get("items", []) if isinstance(data, dict) else []
        items.append(
            {
                "guild_id": inter.guild.id,
                "user_id": member.id,
                "expires_at": disnake.utils.utcnow().timestamp() + seconds,
                "reason": reason,
            }
        )
        db.save_document("moderation_tempbans", {"items": items})

        config = self._get_config()
        config["total_bans"] = int(config.get("total_bans", 0)) + 1
        self._save_config(config)
        await self._send_log(
            inter.guild,
            "Tempban",
            [
                f"**Usuario:** {member.mention} (`{member.id}`)",
                f"**Moderador:** {inter.user.mention}",
                f"**Duracao:** `{_format_duration(seconds)}`",
                f"**Motivo:** {reason}",
            ],
        )
        await inter.response.send_message(f"{emoji.correct} {member.mention} banido por `{_format_duration(seconds)}`.", ephemeral=True)

    async def _apply_softban(self, inter: disnake.ModalInteraction, member_id: int, days: int, reason: str):
        member = await self._fetch_member(inter.guild, member_id)
        if not member:
            await inter.response.send_message(f"{emoji.wrong} Usuario nao encontrado.", ephemeral=True)
            return
        ok, error = self._can_act_on(inter, member, "softban")
        if not ok:
            await inter.response.send_message(f"{emoji.wrong} {error}", ephemeral=True)
            return
        days = max(1, min(days, 7))

        try:
            await member.ban(reason=f"[Softban] {reason}", delete_message_days=days)
            await inter.guild.unban(member, reason="Softban - desbanimento automatico")
        except disnake.HTTPException as exc:
            await inter.response.send_message(f"{emoji.wrong} Nao foi possivel aplicar softban: `{exc}`", ephemeral=True)
            return

        await self._send_log(
            inter.guild,
            "Softban",
            [
                f"**Usuario:** {member.mention} (`{member.id}`)",
                f"**Moderador:** {inter.user.mention}",
                f"**Dias apagados:** `{days}`",
                f"**Motivo:** {reason}",
            ],
        )
        await inter.response.send_message(f"{emoji.correct} Softban aplicado em {member.mention}.", ephemeral=True)

    def _warn_modal(self, member_id: int):
        class WarnModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Aplicar Warn",
                    custom_id=f"Moderacao_WarnModal:{member_id}",
                    components=[
                        disnake.ui.TextInput(label="Motivo", custom_id="reason", style=disnake.TextInputStyle.paragraph, max_length=500),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                await self._apply_warn(modal_inter, member_id, values.get("reason", "Sem motivo"))

        return WarnModal()

    def _mute_modal(self, member_id: int):
        class MuteModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Aplicar Mute",
                    custom_id=f"Moderacao_MuteModal:{member_id}",
                    components=[
                        disnake.ui.TextInput(label="Duracao", custom_id="duration", placeholder="10m, 1h, 7d", max_length=10),
                        disnake.ui.TextInput(label="Motivo", custom_id="reason", style=disnake.TextInputStyle.paragraph, max_length=500),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                await self._apply_mute(modal_inter, member_id, values.get("duration", ""), values.get("reason", "Sem motivo"))

        return MuteModal()

    def _slowmode_modal(self, channel_id: int):
        class SlowmodeModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Configurar Slowmode",
                    custom_id=f"Moderacao_SlowmodeModal:{channel_id}",
                    components=[
                        disnake.ui.TextInput(label="Tempo", custom_id="duration", placeholder="0, 5s, 10m, 6h", max_length=10),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                await self._apply_slowmode(modal_inter, channel_id, values.get("duration", "0"))

        return SlowmodeModal()

    def _tempban_modal(self, member_id: int):
        class TempbanModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Aplicar Tempban",
                    custom_id=f"Moderacao_TempbanModal:{member_id}",
                    components=[
                        disnake.ui.TextInput(label="Duracao", custom_id="duration", placeholder="1h, 1d, 7d", max_length=10),
                        disnake.ui.TextInput(label="Motivo", custom_id="reason", style=disnake.TextInputStyle.paragraph, max_length=500),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                await self._apply_tempban(modal_inter, member_id, values.get("duration", ""), values.get("reason", "Sem motivo"))

        return TempbanModal()

    def _softban_modal(self, member_id: int):
        class SoftbanModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Aplicar Softban",
                    custom_id=f"Moderacao_SoftbanModal:{member_id}",
                    components=[
                        disnake.ui.TextInput(label="Dias de mensagens para apagar", custom_id="days", placeholder="1 a 7", max_length=1),
                        disnake.ui.TextInput(label="Motivo", custom_id="reason", style=disnake.TextInputStyle.paragraph, max_length=500),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                try:
                    days = int(values.get("days", "1"))
                except ValueError:
                    days = 1
                await self._apply_softban(modal_inter, member_id, days, values.get("reason", "Softban"))

        return SoftbanModal()

    async def _send_user_select(self, inter: disnake.MessageInteraction, custom_id: str, placeholder: str):
        await inter.response.send_message(
            "Selecione o usuario.",
            components=[disnake.ui.ActionRow(disnake.ui.UserSelect(custom_id=custom_id, placeholder=placeholder))],
            ephemeral=True,
        )

    @commands.Cog.listener("on_message_interaction")
    async def Moderacao_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("Moderacao"):
            return

        if custom_id not in {"Moderacao_Warns"} and not await self._require_panel_admin(inter):
            return

        if custom_id == "Moderacao_Toggle":
            await inter.response.defer(ephemeral=True)
            config = self._get_config()
            if not as_bool(config.get("enabled"), False) and not config.get("logs_channel_id"):
                await inter.followup.send(f"{emoji.wrong} Configure o canal de logs antes de ativar.", ephemeral=True)
                return
            config["enabled"] = not as_bool(config.get("enabled"), False)
            self._save_config(config)
            await self._refresh_panel(inter)
            await inter.followup.send(f"{emoji.correct} Moderacao {'ativada' if config['enabled'] else 'desativada'}.", ephemeral=True)
            return

        if custom_id == "Moderacao_Logs":
            await inter.response.send_message(
                "Selecione o canal de logs da moderacao.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(custom_id="Moderacao_SelectLogs", placeholder="Canal de logs", channel_types=[disnake.ChannelType.text])
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Moderacao_Reports":
            await inter.response.send_message(
                "Selecione o canal de reports.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(custom_id="Moderacao_SelectReports", placeholder="Canal de reports", channel_types=[disnake.ChannelType.text])
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Moderacao_Roles":
            await inter.response.send_message(
                "Selecione o cargo de moderador.",
                components=[disnake.ui.ActionRow(disnake.ui.RoleSelect(placeholder="Cargo moderador", custom_id="Moderacao_SelectRole"))],
                ephemeral=True,
            )
            return

        if custom_id == "Moderacao_SelectLogs":
            config = self._get_config()
            config["logs_channel_id"] = int(inter.values[0])
            self._save_config(config)
            await inter.response.send_message(f"{emoji.correct} Canal de logs salvo: <#{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "Moderacao_SelectReports":
            config = self._get_config()
            config["report_channel_id"] = int(inter.values[0])
            self._save_config(config)
            await inter.response.send_message(f"{emoji.correct} Canal de reports salvo: <#{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "Moderacao_SelectRole":
            config = self._get_config()
            config["moderator_role_id"] = int(inter.values[0])
            self._save_config(config)
            await inter.response.send_message(f"{emoji.correct} Cargo de moderador salvo: <@&{inter.values[0]}>.", ephemeral=True)
            return

        if custom_id == "Moderacao_Warn":
            await self._send_user_select(inter, "Moderacao_WarnSelect", "Usuario que recebera warn")
            return

        if custom_id == "Moderacao_Warns":
            if not await self._is_panel_admin(inter):
                await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para ver avisos.", ephemeral=True)
                return
            await self._send_user_select(inter, "Moderacao_WarnsSelect", "Usuario para consultar avisos")
            return

        if custom_id == "Moderacao_Mute":
            await self._send_user_select(inter, "Moderacao_MuteSelect", "Usuario que sera mutado")
            return

        if custom_id == "Moderacao_Unmute":
            await self._send_user_select(inter, "Moderacao_UnmuteSelect", "Usuario que tera mute removido")
            return

        if custom_id == "Moderacao_Slowmode":
            await inter.response.send_message(
                "Selecione o canal para alterar o slowmode.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(custom_id="Moderacao_SlowmodeSelect", placeholder="Canal", channel_types=[disnake.ChannelType.text])
                    )
                ],
                ephemeral=True,
            )
            return

        if custom_id == "Moderacao_Tempban":
            await self._send_user_select(inter, "Moderacao_TempbanSelect", "Usuario que sera banido temporariamente")
            return

        if custom_id == "Moderacao_Softban":
            await self._send_user_select(inter, "Moderacao_SoftbanSelect", "Usuario que recebera softban")
            return

        if custom_id == "Moderacao_CargoAll":
            await inter.response.send_message(
                "Selecione o cargo que sera adicionado a todos os membros sem bot.",
                components=[disnake.ui.ActionRow(disnake.ui.RoleSelect(custom_id="Moderacao_CargoAllSelect", placeholder="Cargo"))],
                ephemeral=True,
            )
            return

        if custom_id == "Moderacao_WarnSelect":
            await inter.response.send_modal(self._warn_modal(int(inter.values[0])))
            return

        if custom_id == "Moderacao_WarnsSelect":
            await self._show_warns(inter, int(inter.values[0]))
            return

        if custom_id == "Moderacao_MuteSelect":
            await inter.response.send_modal(self._mute_modal(int(inter.values[0])))
            return

        if custom_id == "Moderacao_UnmuteSelect":
            await self._apply_unmute(inter, int(inter.values[0]))
            return

        if custom_id == "Moderacao_SlowmodeSelect":
            await inter.response.send_modal(self._slowmode_modal(int(inter.values[0])))
            return

        if custom_id == "Moderacao_TempbanSelect":
            await inter.response.send_modal(self._tempban_modal(int(inter.values[0])))
            return

        if custom_id == "Moderacao_SoftbanSelect":
            await inter.response.send_modal(self._softban_modal(int(inter.values[0])))
            return

        if custom_id == "Moderacao_CargoAllSelect":
            await inter.response.defer(ephemeral=True)
            role = inter.guild.get_role(int(inter.values[0]))
            if not role:
                await inter.followup.send(f"{emoji.wrong} Cargo nao encontrado.", ephemeral=True)
                return
            if role >= inter.guild.me.top_role:
                await inter.followup.send(f"{emoji.wrong} Meu cargo esta abaixo do cargo selecionado.", ephemeral=True)
                return

            try:
                await inter.guild.chunk(cache=True)
            except Exception:
                pass

            success = 0
            failed = 0
            for member in inter.guild.members:
                if member.bot or role in member.roles:
                    continue
                try:
                    await member.add_roles(role, reason=f"Cargo All por {inter.user}")
                    success += 1
                except disnake.HTTPException:
                    failed += 1

            await self._send_log(
                inter.guild,
                "Cargo All",
                [
                    f"**Cargo:** {role.mention}",
                    f"**Executor:** {inter.user.mention}",
                    f"**Adicionados:** `{success}`",
                    f"**Falhas:** `{failed}`",
                ],
            )
            await inter.followup.send(f"{emoji.correct} Cargo All concluido. Sucesso: `{success}` | Falhas: `{failed}`.", ephemeral=True)

    @tasks.loop(minutes=1)
    async def tempban_checker(self):
        data = db.get_document("moderation_tempbans") or {}
        if isinstance(data, list):
            items = data
        else:
            items = data.get("items", [])
        if not items:
            return

        now = disnake.utils.utcnow().timestamp()
        remaining = []
        changed = False
        for item in items:
            if float(item.get("expires_at", 0)) > now:
                remaining.append(item)
                continue

            guild = self.bot.get_guild(int(item.get("guild_id", 0)))
            if not guild:
                remaining.append(item)
                continue

            try:
                await guild.unban(disnake.Object(id=int(item["user_id"])), reason="Tempban expirado")
                changed = True
                await self._send_log(
                    guild,
                    "Tempban Expirado",
                    [f"**Usuario:** <@{item['user_id']}> (`{item['user_id']}`)", "**Acao:** desbanido automaticamente"],
                )
            except disnake.HTTPException:
                remaining.append(item)

        if changed:
            db.save_document("moderation_tempbans", {"items": remaining})

    @tempban_checker.before_loop
    async def before_tempban_checker(self):
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(ModeradorPanel(bot))
