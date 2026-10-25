from disnake.ext import commands
import disnake

from functions.database import database as db
from functions import auto_setup
from functions.emoji import emoji
from functions.guild_channels import load_guild_channels
from functions.message import message, embed_message
from .listar import CANAIS_OPCOES

class ConfigurarCanais(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def canais_components(inter: disnake.MessageInteraction) -> list[disnake.ui.Container]:
        guild = inter.guild
        definicoes = load_guild_channels(guild)
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        options = []

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        for key, label, emoji_icon in CANAIS_OPCOES:
            nome = "Não definido"
            canal = None

            canal_id = definicoes.get(key)
            if guild and canal_id:
                try:
                    canal = guild.get_channel(int(canal_id))
                except (TypeError, ValueError):
                    canal = None

            if canal:
                base = canal.name[:25] + ("..." if len(canal.name) > 25 else "")
                nome = f"{base} ({canal.id})"

            options.append(
                disnake.SelectOption(
                    label=label,
                    value=key,
                    emoji=emoji_icon,
                    description=f"Canal atual: {nome}",
                )
            )

        def chunks(seq, n=25):
            for i in range(0, len(seq), n):
                yield seq[i:i+n]

        select_rows = [
            disnake.ui.ActionRow(
                disnake.ui.Select(
                    placeholder="Escolha o canal para configurar",
                    options=chunk,
                    custom_id=f"Configuracoes_EditarCanal:{i}",
                )
            )
            for i, chunk in enumerate(chunks(options, 25))
        ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Configurações > **Canais**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    "Utilize o painel para gerenciar os canais do servidor.\n"
                    "Você pode criar também os canais automaticamente."
                ),
                disnake.ui.Separator(),
                *select_rows,
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Criar os canais automaticamente",
                        emoji=emoji.wand,
                        style=disnake.ButtonStyle.blurple,
                        custom_id="Configuracoes_CriarTodosCanais",
                    ),
                    disnake.ui.Button(
                        label="Personalizar criacao",
                        emoji=emoji.edit,
                        style=disnake.ButtonStyle.grey,
                        custom_id="Configuracoes_CustomAutoChannels",
                    ),
                ),
                **container_kwargs,
            )
        ]

    @staticmethod
    def canais_embed(inter: disnake.MessageInteraction):
        guild = inter.guild
        definicoes = load_guild_channels(guild)
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        options = []

        for key, label, emoji_icon in CANAIS_OPCOES:
            nome = "Não definido"
            canal = None

            canal_id = definicoes.get(key)
            if guild and canal_id:
                try:
                    canal = guild.get_channel(int(canal_id))
                except (TypeError, ValueError):
                    canal = None

            if canal:
                base = canal.name[:25] + ("..." if len(canal.name) > 25 else "")
                nome = f"{base} ({canal.id})"

            options.append(
                disnake.SelectOption(
                    label=label,
                    value=key,
                    emoji=emoji_icon,
                    description=f"Canal atual: {nome}",
                )
            )

        def chunks(seq, n=25):
            for i in range(0, len(seq), n):
                yield seq[i:i+n]

        select_rows = [
            disnake.ui.ActionRow(
                disnake.ui.Select(
                    placeholder="Escolha o canal para configurar",
                    options=chunk,
                    custom_id=f"Configuracoes_EditarCanal:{i}",
                )
            )
            for i, chunk in enumerate(chunks(options, 25))
        ]

        embed = disnake.Embed(
            title=f"Canais",
            description="Utilize o painel para gerenciar os canais do servidor.\nVocê pode criar também os canais automaticamente.",
            # timestamp=disnake.utils.utcnow()
        )
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color

        # embed.set_footer(text=inter.guild.name, icon_url=inter.guild.icon.url if inter.guild.icon else None)
        
        components = [
            *select_rows,
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Criar os canais automaticamente",
                    emoji=emoji.wand,
                    style=disnake.ButtonStyle.blurple,
                    custom_id="Configuracoes_CriarTodosCanais",
                ),
                disnake.ui.Button(
                    label="Personalizar criacao",
                    emoji=emoji.edit,
                    style=disnake.ButtonStyle.grey,
                    custom_id="Configuracoes_CustomAutoChannels",
                ),
            ),
        ]
        return embed, components

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Configuracoes_CustomAutoChannels":
            cfg = auto_setup.get_config()
            cog = self
            source_message = inter.message

            class AutoChannelsModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Personalizar canais automaticos",
                        custom_id="Configuracoes_CustomAutoChannels_Modal",
                        components=[
                            disnake.ui.TextInput(label="Separador", custom_id="separator", value=str(cfg.get("separator") or "╺╸")[:20], max_length=20, required=True),
                            disnake.ui.TextInput(label="Modelo do nome", custom_id="channel_pattern", value=str(cfg.get("channel_pattern") or "{emoji}{separator}{name}")[:80], max_length=80, required=True, placeholder="{emoji}{separator}{name}"),
                            disnake.ui.TextInput(label="Categoria de logs", custom_id="logs_category", value=str(cfg.get("logs_category") or "╺╸ Logs")[:80], max_length=80, required=True),
                            disnake.ui.TextInput(label="Categoria dos demais canais", custom_id="community_category", value=str(cfg.get("community_category") or "╺╸ Comunidade")[:80], max_length=80, required=True),
                            disnake.ui.TextInput(label="Nomes por chave", custom_id="channel_names", style=disnake.TextInputStyle.paragraph, value=cog._names_to_text(cfg.get("channel_names", {}))[:900], max_length=900, required=False, placeholder="canal_de_feedback=feedbacks\ncanal_de_boas_vindas=boas-vindas"),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = modal_inter.text_values
                    data = auto_setup.get_config()
                    data["separator"] = str(values.get("separator") or "╺╸").strip()[:20]
                    data["channel_pattern"] = str(values.get("channel_pattern") or "{emoji}{separator}{name}").strip()[:80]
                    data["logs_category"] = str(values.get("logs_category") or "╺╸ Logs").strip()[:80]
                    data["community_category"] = str(values.get("community_category") or "╺╸ Comunidade").strip()[:80]
                    data["channel_names"] = cog._parse_names(values.get("channel_names"))
                    auto_setup.save_config(data)

                    mode = db.get_document("custom_mode").get("mode")
                    try:
                        if mode == "embed":
                            embed, components = ConfigurarCanais.canais_embed(modal_inter)
                            await source_message.edit(content=None, embed=embed, components=components)
                        else:
                            await source_message.edit(content=None, embed=None, components=ConfigurarCanais.canais_components(modal_inter), flags=disnake.MessageFlags(is_components_v2=True))
                    except Exception:
                        pass
                    await modal_inter.response.send_message(f"{emoji.correct} Personalizacao da criacao automatica de canais salva.", ephemeral=True)

            await inter.response.send_modal(AutoChannelsModal())
            return

        if inter.component.custom_id == "Configuracoes_EditarCanais":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.canais_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.canais_components(inter))

    @staticmethod
    def _names_to_text(values: dict) -> str:
        if not isinstance(values, dict):
            return ""
        return "\n".join(f"{key}={value}" for key, value in values.items() if value)

    @staticmethod
    def _parse_names(raw: str | None) -> dict:
        result = {}
        for part in str(raw or "").replace(";", "\n").splitlines():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                result[key] = value
        return result
