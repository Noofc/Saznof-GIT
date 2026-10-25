import disnake
from disnake.ext import commands

from functions import auto_setup
from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import load_guild_channels, save_guild_channels
from functions.message import message, embed_message
from functions.system_logs import send_system_log
from .criar_todos import MensagensCanais
from .listar import CANAIS_OPCOES


class ConfigurarCanal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def canal_components(inter: disnake.MessageInteraction, canal_key: str) -> list[disnake.ui.Container]:
        definicoes = load_guild_channels(inter.guild)
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

        try:
            canal_id = int(definicoes.get(canal_key))
        except Exception:
            canal_id = None

        canal = next((c for c in CANAIS_OPCOES if c[0] == canal_key), None)
        canal_nome = canal[1] if canal else canal_key
        canal_obj = inter.guild.get_channel(canal_id) if inter.guild and canal_id else None
        canal_id_str = f"`{canal_obj.id}`" if canal_obj else "`Nao definido`"
        canal_name = canal_obj.mention if canal_obj else "`Nao definido`"

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Configuracoes > Canais > **{canal_nome}**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("Gerencie o canal selecionado ou deixe o bot criar usando o modelo personalizado."),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(f"**Canal selecionado:** `{canal_nome}`\n**Canal atual:** {canal_name} ({canal_id_str})"),
                disnake.ui.ActionRow(
                    disnake.ui.ChannelSelect(
                        channel_types=[disnake.ChannelType.text],
                        placeholder="Selecione um canal para definir",
                        custom_id=f"Configuracoes_EditarNovoCanal:{canal_key}",
                        min_values=1,
                        max_values=1,
                    )
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Apagar", emoji=emoji.delete, custom_id=f"Configuracoes_ApagarCanal:{canal_key}", style=disnake.ButtonStyle.red, disabled=canal_obj is None),
                    disnake.ui.Button(label="Criar o canal para mim", emoji=emoji.wand, custom_id=f"Configuracoes_CriarCanal:{canal_key}", style=disnake.ButtonStyle.blurple),
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(disnake.ui.Button(label="", emoji=emoji.back, custom_id="Configuracoes_EditarCanais")),
        ]

    @staticmethod
    def canal_embed(inter: disnake.MessageInteraction, canal_key: str):
        definicoes = load_guild_channels(inter.guild)
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        try:
            canal_id = int(definicoes.get(canal_key))
        except Exception:
            canal_id = None

        canal = next((c for c in CANAIS_OPCOES if c[0] == canal_key), None)
        canal_nome = canal[1] if canal else canal_key
        canal_obj = inter.guild.get_channel(canal_id) if inter.guild and canal_id else None
        canal_id_str = f"`{canal_obj.id}`" if canal_obj else "`Nao definido`"
        canal_name = canal_obj.mention if canal_obj else "`Nao definido`"

        embed = disnake.Embed(
            title=canal_nome,
            description="Gerencie o canal selecionado ou deixe o bot criar usando o modelo personalizado.",
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)
        embed.add_field(name="Canal selecionado:", value=f"`{canal_nome}`")
        embed.add_field(name="Canal atual:", value=f"{canal_name} ({canal_id_str})")

        components = [
            disnake.ui.ActionRow(
                disnake.ui.ChannelSelect(
                    channel_types=[disnake.ChannelType.text],
                    placeholder="Selecione um canal para definir",
                    custom_id=f"Configuracoes_EditarNovoCanal:{canal_key}",
                    min_values=1,
                    max_values=1,
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Apagar", emoji=emoji.delete, custom_id=f"Configuracoes_ApagarCanal:{canal_key}", style=disnake.ButtonStyle.red, disabled=canal_obj is None),
                disnake.ui.Button(label="Criar o canal para mim", emoji=emoji.wand, custom_id=f"Configuracoes_CriarCanal:{canal_key}", style=disnake.ButtonStyle.blurple),
            ),
            disnake.ui.ActionRow(disnake.ui.Button(label="", emoji=emoji.back, custom_id="Configuracoes_EditarCanais")),
        ]
        return embed, components

    async def _create_channel(self, inter: disnake.MessageInteraction, canal_key: str):
        canal = next((c for c in CANAIS_OPCOES if c[0] == canal_key), None)
        canal_label = canal[1] if canal else canal_key
        setup_cfg = auto_setup.get_config()
        name = auto_setup.channel_name(canal_key, canal_label, setup_cfg)
        is_log_channel = auto_setup.is_logs_key(canal_key)
        category_name = setup_cfg.get("logs_category") if is_log_channel else setup_cfg.get("community_category")

        category = None
        if category_name:
            category = next((c for c in inter.guild.categories if c.name.lower() == str(category_name).lower()), None)
            if category is None:
                try:
                    category = await inter.guild.create_category(str(category_name)[:100])
                except Exception:
                    category = None

        overwrites = None
        if is_log_channel and setup_cfg.get("private_logs", True):
            overwrites = {inter.guild.default_role: disnake.PermissionOverwrite(view_channel=False)}

        return await inter.guild.create_text_channel(
            name,
            category=category,
            overwrites=overwrites,
            reason=f"Auto-criacao pelo painel de configuracoes - {inter.user.name} ({inter.user.id})",
        )

    @commands.Cog.listener("on_button_click")
    async def configurar_canais_button_listener(self, inter: disnake.MessageInteraction):
        mode = db.get_document("custom_mode").get("mode")
        custom_id = inter.component.custom_id

        if custom_id.startswith("Configuracoes_ApagarCanal"):
            canal_key = custom_id.split(":")[1]
            canais_db = load_guild_channels(inter.guild)
            canais_db[canal_key] = None
            save_guild_channels(inter.guild, canais_db)

            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.canal_embed(inter, canal_key)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.canal_components(inter, canal_key))

        elif custom_id.startswith("Configuracoes_CriarCanal"):
            canal_key = custom_id.split(":")[1]
            try:
                ch = await self._create_channel(inter, canal_key)
            except Exception as exc:
                ch = None
                print(f"[Canais] Falha ao criar {canal_key}: {exc}")

            if ch:
                canais_db = load_guild_channels(inter.guild)
                canais_db[canal_key] = str(ch.id)
                save_guild_channels(inter.guild, canais_db)

            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.canal_embed(inter, canal_key)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.canal_components(inter, canal_key))

            if ch:
                if mode == "embed":
                    embed, components = MensagensCanais.canal_criado_embed(ch, auto=False)
                    await inter.followup.send(embed=embed, components=components, ephemeral=True)
                else:
                    await ch.send(components=MensagensCanais.canal_criado_components(ch, auto=False), flags=disnake.MessageFlags(is_components_v2=True))
                await send_system_log(
                    self.bot,
                    inter.guild,
                    title="Canal criado",
                    system="Configuracoes",
                    description=f"Canal {ch.mention} (`{ch.name}`) criado para `{canal_key}`.",
                    actor=inter.user,
                )

    @commands.Cog.listener("on_dropdown")
    async def configurar_canais_dropdown_listener(self, inter: disnake.MessageInteraction):
        mode = db.get_document("custom_mode").get("mode")
        custom_id = inter.component.custom_id

        if custom_id.startswith("Configuracoes_EditarCanal"):
            canal_key = inter.values[0]
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.canal_embed(inter, canal_key)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.canal_components(inter, canal_key))

        elif custom_id.startswith("Configuracoes_EditarNovoCanal"):
            canal_key = custom_id.replace("Configuracoes_EditarNovoCanal:", "")
            canal_id = inter.values[0]
            canais_db = load_guild_channels(inter.guild)
            canais_db[canal_key] = canal_id
            save_guild_channels(inter.guild, canais_db)

            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.canal_embed(inter, canal_key)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.canal_components(inter, canal_key))
