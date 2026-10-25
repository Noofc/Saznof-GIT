import disnake
import asyncio
from disnake.ext import commands
from functions.emoji import emoji
from functions.database import database as db
from functions.perms import perms
from functions.message import message, embed_message
from functions.utils import utils


class ConectarCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._reconnect_attempted = False

    def _get_connection_status(self, guild_id: int = None) -> dict:
        """Obtém o status atual de conexão do bot"""
        connection_data = db.get_document("bot_connection") or {}
        channel_id = connection_data.get("channel_id")
        
        channel = None
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
        
        is_connected = False
        if channel and self.bot.voice_clients:
            for vc in self.bot.voice_clients:
                if vc.channel and vc.channel.id == int(channel_id):
                    # Se guild_id foi fornecido, verificar se é do mesmo servidor
                    if guild_id is None or vc.guild.id == guild_id:
                        is_connected = True
                        break
        
        return {
            "channel_id": channel_id,
            "channel": channel,
            "is_connected": is_connected
        }

    def ConectarComponents(self, inter: disnake.MessageInteraction) -> list[disnake.ui.Container]:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        connection = self._get_connection_status(inter.guild.id if inter.guild else None)
        channel = connection["channel"]
        is_connected = connection["is_connected"]

        channel_display = channel.mention if channel else "`Nenhum canal configurado`"

        # O bot deve permanecer na call; o botão apenas conecta ou força reconexão.
        connect_button_label = "Conectado" if is_connected else "Conectar"
        connect_button_style = disnake.ButtonStyle.green
        connect_button_emoji = emoji.voice

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# **Gerenciar Conexão do Pro**"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                f"{emoji.voice} **Canal Atual:** {channel_display}"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label=connect_button_label,
                    style=connect_button_style,
                    emoji=connect_button_emoji,
                    custom_id="Conectar_Toggle"
                ),
                disnake.ui.Button(
                    label="Editar Canal",
                    style=disnake.ButtonStyle.blurple,
                    emoji=emoji.edit,
                    custom_id="Conectar_EditChannel"
                ),
            ),
            **container_kwargs
        )

        return [container]

    def ConectarEmbed(self, inter: disnake.MessageInteraction):
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        connection = self._get_connection_status(inter.guild.id if inter.guild else None)
        channel = connection["channel"]
        is_connected = connection["is_connected"]

        channel_display = channel.mention if channel else "`Nenhum canal configurado`"

        embed = disnake.Embed(
            title=f"{emoji.lyon} Gerenciar Conexão do Pro",
            description=f"{emoji.voice} **Canal Atual:** {channel_display}",
        )
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color

        # O bot deve permanecer na call; o botão apenas conecta ou força reconexão.
        connect_button_label = "Conectado" if is_connected else "Conectar"
        connect_button_style = disnake.ButtonStyle.green
        connect_button_emoji = emoji.voice

        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label=connect_button_label,
                    style=connect_button_style,
                    emoji=connect_button_emoji,
                    custom_id="Conectar_Toggle"
                ),
                disnake.ui.Button(
                    label="Editar Canal",
                    style=disnake.ButtonStyle.blurple,
                    emoji=emoji.edit,
                    custom_id="Conectar_EditChannel"
                ),
            )
        ]
        return embed, components

    @commands.slash_command(
        name="conectar",
        description="Gerencia a conexão do bot em canais de voz.",
        guild_ids=utils.obter_guild_ids(),
    )
    async def conectar(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        
        if not await perms.check(inter.user.id):
            await inter.followup.send("Você não tem permissão para usar este comando", ephemeral=True)
            return

        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            embed, components = self.ConectarEmbed(inter)
            await inter.edit_original_response(content=None, embed=embed, components=components)
        else:
            await inter.edit_original_response(
                components=self.ConectarComponents(inter),
            )

    @commands.Cog.listener("on_button_click")
    async def Conectar_Button_Listener(self, inter: disnake.MessageInteraction):
        if not inter.component.custom_id.startswith("Conectar"):
            return

        custom_id = inter.component.custom_id

        if custom_id == "Conectar_Toggle":
            await self._handle_toggle_connection(inter)
        elif custom_id == "Conectar_EditChannel":
            await self._handle_edit_channel(inter)

    async def _handle_toggle_connection(self, inter: disnake.MessageInteraction):
        """Conecta ou desconecta o bot do canal de voz"""
        await inter.response.defer(ephemeral=True)
        
        connection = self._get_connection_status(inter.guild.id if inter.guild else None)
        channel_id = connection["channel_id"]
        is_connected = connection["is_connected"]

        if not channel_id:
            await inter.followup.send("Configure um canal primeiro usando o botão 'Editar Canal'", ephemeral=True)
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await inter.followup.send("Canal não encontrado. Configure um novo canal.", ephemeral=True)
            return

        if not isinstance(channel, disnake.VoiceChannel):
            await inter.followup.send("O canal configurado não é um canal de voz.", ephemeral=True)
            return

        try:
            # Nunca desconectar pelo painel. Se já estiver na call, apenas
            # confirma o estado; se estiver fora, conecta ao canal salvo.
            if is_connected:
                await inter.followup.send("O bot já está conectado a este canal.", ephemeral=True)
                return

            # Se houver uma conexão antiga em outro canal, encerra apenas a
            # conexão conflitante antes de entrar no canal configurado.
            for vc in list(self.bot.voice_clients):
                if vc.guild.id == channel.guild.id and vc.channel and vc.channel.id != channel.id:
                    await vc.disconnect(force=True)

            await channel.connect(reconnect=True)

            connection_data = db.get_document("bot_connection") or {}
            connection_data["channel_id"] = str(channel.id)
            connection_data["guild_id"] = str(channel.guild.id)
            connection_data["was_connected"] = True
            connection_data["keep_connected"] = True
            db.save_document("bot_connection", connection_data)
        except Exception as e:
            error_msg = str(e)
            if "dave.py" in error_msg.lower() or "dave" in error_msg.lower():
                await inter.followup.send(
                    "Erro ao conectar: falta a biblioteca DAVE. Instale `dave.py` junto com `PyNaCl` e reinicie o bot.",
                    ephemeral=True,
                )
            elif "PyNaCl" in error_msg:
                await inter.followup.send("Erro ao conectar: é necessário instalar `PyNaCl`.", ephemeral=True)
            else:
                await inter.followup.send(f"Erro ao {'desconectar' if is_connected else 'conectar'}: {error_msg}", ephemeral=True)
            return

        # Atualizar painel
        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            embed, components = self.ConectarEmbed(inter)
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            await inter.edit_original_message(components=self.ConectarComponents(inter))

    async def _handle_edit_channel(self, inter: disnake.MessageInteraction):
        """Abre seleção de canal de voz"""
        await inter.response.defer(ephemeral=True)
        
        # Criar select de canais de voz
        voice_channels = [ch for ch in inter.guild.channels if isinstance(ch, disnake.VoiceChannel)]
        
        if not voice_channels:
            await inter.followup.send("Não há canais de voz neste servidor.", ephemeral=True)
            return
        
        mode = db.get_document("custom_mode").get("mode")

        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        select_options = [
            disnake.SelectOption(
                label=ch.name,
                value=str(ch.id),
                description=f"ID: {ch.id}"
            )
            for ch in voice_channels[:25]  # Limite do Discord
        ]

        if mode == "components":
            container_kwargs = {}
            if primary_color_hex:
                container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

            container = disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# **Selecionar Canal de Voz**"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(f"{emoji.information} Selecione o canal de voz onde o bot deve se conectar:"),
                disnake.ui.ActionRow(
                    disnake.ui.ChannelSelect(
                        placeholder="Selecione um canal de voz...",
                        custom_id="Conectar_SelectChannel",
                        channel_types=[disnake.ChannelType.voice],
                        min_values=1,
                        max_values=1,
                    )
                ),
                **container_kwargs
            )
            await inter.edit_original_message(components=[container])
        else:
            embed_kwargs = {}
            if primary_color_hex:
                embed_kwargs["color"] = int(primary_color_hex.replace("#", ""), 16)

            embed = disnake.Embed(
                title=f"{emoji.lyon} Selecionar Canal de Voz",
                description=f"{emoji.information} Selecione o canal de voz onde o bot deve se conectar:",
                **embed_kwargs
            )

            components = [
                disnake.ui.ActionRow(
                    disnake.ui.ChannelSelect(
                        placeholder="Selecione um canal de voz...",
                        custom_id="Conectar_SelectChannel",
                        channel_types=[disnake.ChannelType.voice],
                        min_values=1,
                        max_values=1,
                    )
                )
            ]
            await inter.edit_original_message(content=None, embed=embed, components=components)

    @commands.Cog.listener("on_dropdown")
    async def Conectar_Dropdown_Listener(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Conectar_SelectChannel":
            await inter.response.defer(ephemeral=True)
            
            channel_id = int(inter.values[0])
            channel = inter.guild.get_channel(channel_id)

            if not channel or not isinstance(channel, disnake.VoiceChannel):
                await inter.followup.send("Canal inválido.", ephemeral=True)
                return

            # Salvar canal
            connection_data = db.get_document("bot_connection") or {}
            connection_data["channel_id"] = str(channel_id)
            db.save_document("bot_connection", connection_data)

            # Atualizar painel
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                embed, components = self.ConectarEmbed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await inter.edit_original_message(components=self.ConectarComponents(inter))

    async def _connect_saved_channel(self) -> bool:
        """Conecta ao canal salvo sem apagar o estado em caso de erro temporário."""
        connection_data = db.get_document("bot_connection") or {}
        if not connection_data.get("keep_connected", connection_data.get("was_connected", False)):
            return False

        channel_id = connection_data.get("channel_id")
        if not channel_id:
            return False

        channel = self.bot.get_channel(int(channel_id))
        if not channel or not isinstance(channel, disnake.VoiceChannel):
            print(f"[Conectar] Canal salvo não está disponível: {channel_id}")
            return False

        for vc in list(self.bot.voice_clients):
            if vc.channel and vc.channel.id == channel.id and not vc.is_connected():
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass

        if any(vc.channel and vc.channel.id == channel.id and vc.is_connected() for vc in self.bot.voice_clients):
            return True

        try:
            await channel.connect(reconnect=True)
            print(f"[Conectar] Reconectado ao canal {channel.name} ({channel.id})")
            return True
        except Exception as exc:
            message = str(exc)
            if "dave.py" in message.lower() or "dave" in message.lower():
                print("[Conectar] DAVE ausente. Instale dave.py e reinicie o processo.")
            else:
                print(f"[Conectar] Falha temporária ao reconectar: {exc}")
            return False

    async def _voice_watchdog(self):
        """Mantém a conexão de voz enquanto `keep_connected` estiver ativo."""
        await asyncio.sleep(2)
        while True:
            try:
                await self._connect_saved_channel()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[Conectar] Watchdog de voz falhou: {exc}")
            await asyncio.sleep(15)

    @commands.Cog.listener("on_ready")
    async def auto_reconnect(self):
        """Inicia uma única tarefa persistente de reconexão após o startup."""
        if getattr(self, "_voice_watchdog_task", None) is None or self._voice_watchdog_task.done():
            self._voice_watchdog_task = asyncio.create_task(self._voice_watchdog())

    def cog_unload(self):
        # Cancela apenas a tarefa local; não desconecta o bot por decisão do cog.
        task = getattr(self, "_voice_watchdog_task", None)
        if task and not task.done():
            task.cancel()


def setup(bot: commands.Bot):
    bot.add_cog(ConectarCommand(bot))
