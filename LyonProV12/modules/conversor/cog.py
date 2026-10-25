from __future__ import annotations

import io

import disnake
from disnake.ext import commands, tasks

from functions.emoji import emoji
from .manager import (
    DATA_PATH,
    STATUS_LABELS,
    admin_components,
    ensure_data,
    ensure_log_channel,
    ensure_private_channel,
    channels_due_for_close,
    format_duration,
    log_event,
    mark_channel_activity,
    remove_private_channel,
    process_file,
    option_editor_components,
    option_info,
    processing_components,
    public_components,
    session_components,
    set_config,
    set_option,
    ConversorEditModal,
)


class ConversorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending = {}
        ensure_data()
        self.auto_close_channels.start()

    def cog_unload(self):
        self.auto_close_channels.cancel()

    @tasks.loop(seconds=30)
    async def auto_close_channels(self):
        for channel_id in channels_due_for_close():
            channel = self.bot.get_channel(int(channel_id)) if str(channel_id).isdigit() else None
            if channel is None:
                remove_private_channel(channel_id)
                continue
            try:
                await log_event(self.bot, channel.guild, "Canal do Conversor fechado automaticamente", f"O canal {channel.mention} atingiu o tempo configurado ({format_duration(ensure_data()['config'].get('close_after_seconds'))}).")
                await channel.delete(reason="Tempo de fechamento automático do Conversor atingido")
            except Exception:
                remove_private_channel(channel_id)

    @auto_close_channels.before_loop
    async def before_auto_close_channels(self):
        await self.bot.wait_until_ready()

    def display_conversor_panel(self, inter):
        return admin_components(self.bot)

    async def _publish(self, inter):
        if not inter.guild:
            return await inter.followup.send(f"{emoji.wrong} Use esta ação dentro de um servidor.", ephemeral=True)
        cfg = ensure_data()["config"]
        channel = self.bot.get_channel(int(cfg["channel_id"])) if str(cfg.get("channel_id") or "").isdigit() else None
        channel = channel or inter.channel
        message = await channel.send(components=public_components(self.bot), flags=disnake.MessageFlags(is_components_v2=True))
        await log_event(self.bot, inter.guild, "Painel do Conversor publicado", f"Painel publicado em {channel.mention}. Mensagem: `{message.id}`.", inter.user)
        await inter.followup.send(f"{emoji.correct} Painel do Conversor publicado em {channel.mention}.", ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def on_button(self, inter):
        cid = getattr(inter.component, "custom_id", "")
        if not cid.startswith("Conversor_"):
            return
        if cid == "Conversor_Close":
            channel = getattr(inter, "channel", None)
            if channel and getattr(channel, "guild", None):
                await log_event(self.bot, inter.guild, "Sessão do Conversor encerrada", f"Canal privado {channel.mention} fechado por {inter.user.mention}.", inter.user)
                await inter.response.send_message(f"{emoji.correct} Sessão encerrada. Este canal será removido.", ephemeral=True)
                try:
                    await channel.delete(reason="Sessão do Conversor encerrada")
                except Exception:
                    pass
            return
        if cid == "Conversor_Toggle":
            enabled = not bool(ensure_data()["config"].get("enabled"))
            set_config({"enabled": enabled})
            await log_event(self.bot, inter.guild, "Status do Conversor alterado", f"O sistema foi {'ativado' if enabled else 'desativado'}.", inter.user)
            return await inter.response.edit_message(components=admin_components(self.bot))
        if not ensure_data()["config"].get("enabled"):
            return await inter.response.send_message(f"{emoji.wrong} O Conversor está desativado. Clique em Ativar.", ephemeral=True)
        if cid == "Conversor_Edit":
            return await inter.response.send_modal(ConversorEditModal(self))
        if cid == "Conversor_Time":
            return await inter.response.send_modal(ConversorTimeModal(self))
        if cid == "Conversor_Options":
            return await inter.response.send_message(components=option_editor_components(self.bot), ephemeral=True, flags=disnake.MessageFlags(is_components_v2=True))
        if cid == "Conversor_Channel":
            return await inter.response.send_message("Selecione o canal onde o painel público do Conversor será publicado.", components=[disnake.ui.ActionRow(disnake.ui.ChannelSelect(custom_id="Conversor_ChannelSelect", placeholder="Escolher canal de publicação", channel_types=[disnake.ChannelType.text], min_values=1, max_values=1))], ephemeral=True)
        if cid == "Conversor_Category":
            return await inter.response.send_message("Selecione a categoria onde os canais privados do Conversor serão criados.", components=[disnake.ui.ActionRow(disnake.ui.ChannelSelect(custom_id="Conversor_CategorySelect", placeholder="Escolher categoria privada", channel_types=[disnake.ChannelType.category], min_values=1, max_values=1))], ephemeral=True)
        if cid == "Conversor_Logs":
            if not inter.guild:
                return await inter.response.send_message(f"{emoji.wrong} Use esta ação dentro de um servidor.", ephemeral=True)
            await inter.response.defer(ephemeral=True)
            channel = await ensure_log_channel(self.bot, inter.guild)
            await log_event(self.bot, inter.guild, "Canal de logs do Conversor configurado", f"Canal automático configurado: {channel.mention}.", inter.user)
            return await inter.followup.send(f"{emoji.correct} Canal configurado: {channel.mention}.", ephemeral=True)
        if cid == "Conversor_Publish":
            await inter.response.defer(ephemeral=True)
            return await self._publish(inter)

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter):
        component_id = getattr(inter.component, "custom_id", "")
        if component_id == "Conversor_ChannelSelect":
            selected = inter.values[0] if inter.values else None
            channel_id = str(getattr(selected, "id", selected))
            set_config({"channel_id": channel_id})
            await log_event(self.bot, inter.guild, "Canal do Conversor alterado", f"Canal de publicação definido para <#{channel_id}>.", inter.user)
            return await inter.response.send_message(f"{emoji.correct} Canal de publicação definido para <#{channel_id}>.", ephemeral=True)
        if component_id == "Conversor_CategorySelect":
            selected = inter.values[0] if inter.values else None
            category_id = str(getattr(selected, "id", selected))
            set_config({"category_id": category_id})
            await log_event(self.bot, inter.guild, "Categoria privada do Conversor alterada", f"Categoria definida para <#{category_id}>.", inter.user)
            return await inter.response.send_message(f"{emoji.correct} Categoria privada definida para <#{category_id}>.", ephemeral=True)
        if component_id == "Conversor_OptionSelect":
            action = str(inter.values[0]) if inter.values else "convert"
            return await inter.response.send_modal(ConversorOptionModal(action))
        if component_id != "Conversor_Action":
            return
        if not ensure_data()["config"].get("enabled"):
            return await inter.response.send_message(f"{emoji.wrong} O Conversor está desativado.", ephemeral=True)
        action = str(inter.values[0]) if inter.values else "convert"
        if not inter.guild:
            return await inter.response.send_message(f"{emoji.wrong} O Conversor precisa ser usado dentro de um servidor.", ephemeral=True)
        private_channel = await ensure_private_channel(self.bot, inter.guild, inter.user)
        self.pending[inter.user.id] = {"action": action, "channel_id": private_channel.id}
        mark_channel_activity(private_channel.id)
        await private_channel.send(components=session_components(self.bot, action, private_channel.id), flags=disnake.MessageFlags(is_components_v2=True))
        await inter.response.send_message(f"{emoji.correct} Operação **{STATUS_LABELS.get(action, action)}** selecionada. Envie o arquivo em {private_channel.mention}.", ephemeral=True)

    @commands.Cog.listener("on_message")
    async def on_attachment(self, message):
        if getattr(message.author, "bot", False) or not getattr(message, "attachments", None):
            return
        channel_id = str(getattr(message.channel, "id", ""))
        pending = self.pending.get(message.author.id)
        if not pending:
            configured = set(str(value) for value in ensure_data()["config"].get("private_channel_ids", {}).values())
            if channel_id in configured:
                mark_channel_activity(channel_id)
            return
        if channel_id != str(pending.get("channel_id", "")):
            return
        self.pending.pop(message.author.id, None)
        mark_channel_activity(message.channel.id)
        attachment = message.attachments[0]
        loading = await message.channel.send(components=processing_components(self.bot, pending["action"], attachment.filename, "loading"), flags=disnake.MessageFlags(is_components_v2=True))
        try:
            content = await attachment.read()
            results = process_file(pending["action"], attachment.filename, content, pending.get("format", "PNG"))
            files = [disnake.File(fp=data, filename=name) for data, name in results]
            await loading.edit(components=processing_components(self.bot, pending["action"], attachment.filename, "done"))
            await message.channel.send(f"{emoji.correct} Resultado pronto para `{attachment.filename}`.", files=files)
            mark_channel_activity(message.channel.id, completed=True)
            await log_event(self.bot, message.guild, "Operação do Conversor concluída", f"Usuário {message.author.mention} executou **{STATUS_LABELS.get(pending['action'], pending['action'])}** com `{attachment.filename}`.", message.author)
        except Exception as exc:
            await loading.edit(components=processing_components(self.bot, pending["action"], attachment.filename, "error", exc))
            await log_event(self.bot, message.guild, "Falha no Conversor", f"Falha ao processar `{attachment.filename}`: `{exc}`.", message.author)


class ConversorTimeModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        cfg = ensure_data()["config"]
        total = int(cfg.get("close_after_seconds") or 1800)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        super().__init__(title="Editar tempo de fechamento", custom_id="Conversor_TimeModal", components=[
            disnake.ui.TextInput(label="Horas", custom_id="hours", value=str(hours), placeholder="Ex.: 1", max_length=3),
            disnake.ui.TextInput(label="Minutos", custom_id="minutes", value=str(minutes), placeholder="Ex.: 30", max_length=2),
            disnake.ui.TextInput(label="Segundos", custom_id="seconds", value=str(seconds), placeholder="Ex.: 0", max_length=2),
        ])

    async def callback(self, inter):
        try:
            hours = int(inter.text_values.get("hours", "0") or 0)
            minutes = int(inter.text_values.get("minutes", "0") or 0)
            seconds = int(inter.text_values.get("seconds", "0") or 0)
            if min(hours, minutes, seconds) < 0 or minutes > 59 or seconds > 59:
                raise ValueError
            total = hours * 3600 + minutes * 60 + seconds
            if total <= 0:
                raise ValueError
        except ValueError:
            return await inter.response.send_message(f"{emoji.wrong} Informe um tempo válido. Minutos e segundos devem ficar entre 0 e 59.", ephemeral=True)
        set_config({"close_after_seconds": total})
        await log_event(self.cog.bot, inter.guild, "Tempo do Conversor alterado", f"Canais concluídos ou inativos serão fechados após `{format_duration(total)}`.", inter.user)
        await inter.response.send_message(f"{emoji.correct} Tempo definido para `{format_duration(total)}`.", ephemeral=True)


class ConversorOptionModal(disnake.ui.Modal):
    def __init__(self, action):
        self.action = action
        info = option_info(action)
        super().__init__(title=f"Editar {info['title']}", custom_id=f"Conversor_OptionModal_{action}", components=[
            disnake.ui.TextInput(label="Nome da opção", custom_id="title", value=str(info["title"])[:80], max_length=80),
            disnake.ui.TextInput(label="Descrição", custom_id="description", style=disnake.TextInputStyle.paragraph, value=str(info["description"])[:300], max_length=300),
            disnake.ui.TextInput(label="Emoji interno ou ID", custom_id="emoji", value=str(info["emoji"])[:40], required=False, max_length=40),
        ])

    async def callback(self, inter):
        set_option(self.action, {"title": inter.text_values.get("title", "")[:80], "description": inter.text_values.get("description", "")[:300], "emoji": inter.text_values.get("emoji", "textc")[:40]})
        await inter.response.send_message(f"{emoji.correct} Opção **{self.action}** atualizada.", ephemeral=True)


class ConvertFormatModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(title="Formato de conversão", custom_id="Conversor_FormatModal", components=[
            disnake.ui.TextInput(label="Formato de saída", custom_id="format", value="PNG", placeholder="PNG, JPG ou WEBP", max_length=5)
        ])

    async def callback(self, inter):
        fmt = str(inter.text_values.get("format", "PNG")).upper().replace(".", "")
        if fmt not in {"PNG", "JPG", "JPEG", "WEBP"}:
            return await inter.response.send_message(f"{emoji.wrong} Formato inválido. Use PNG, JPG ou WEBP.", ephemeral=True)
        if not inter.guild:
            return await inter.response.send_message(f"{emoji.wrong} O Conversor precisa ser usado dentro de um servidor.", ephemeral=True)
        private_channel = await ensure_private_channel(self.cog.bot, inter.guild, inter.user)
        self.cog.pending[inter.user.id] = {"action": "convert", "format": fmt, "channel_id": private_channel.id}
        await private_channel.send(components=session_components(self.cog.bot, "convert", private_channel.id), flags=disnake.MessageFlags(is_components_v2=True))
        await inter.response.send_message(f"{emoji.correct} Formato `{fmt}` definido. Envie agora o arquivo em {private_channel.mention}.", ephemeral=True)


def setup(bot):
    bot.add_cog(ConversorCog(bot))
