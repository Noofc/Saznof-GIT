from disnake.ext import commands
import disnake

from functions.database import database as db
from functions import auto_setup
from functions.emoji import emoji
from functions.message import message, embed_message
from .listar import CARGOS_OPCOES

class ConfigurarCargos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def cargos_components(inter: disnake.MessageInteraction) -> list[disnake.ui.Container]:
        definicoes = db.get_document("cargos") or {}
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        guild = inter.guild
        options = []

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        for key, label, emoji_icon in CARGOS_OPCOES:
            nome = "Não definido"
            cargo = None

            cargo_id = definicoes.get(key)
            if guild and cargo_id:
                try:
                    cargo = guild.get_role(int(cargo_id))
                except (TypeError, ValueError):
                    cargo = None

            if cargo:
                base = cargo.name[:25] + ("..." if len(cargo.name) > 25 else "")
                nome = f"{base} ({cargo.id})"

            options.append(
                disnake.SelectOption(
                    label=label,
                    value=key,
                    emoji=emoji_icon,
                    description=f"Cargo atual: {nome}",
                )
            )

        def chunks(seq, n=25):
            for i in range(0, len(seq), n):
                yield seq[i:i+n]

        select_rows = [
            disnake.ui.ActionRow(
                disnake.ui.Select(
                    placeholder="Escolha o cargo para configurar",
                    options=chunk,
                    custom_id=f"Configuracoes_EditarCargo:{i}",
                )
            )
            for i, chunk in enumerate(chunks(options, 25))
        ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Configurações > **Cargos**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    "Utilize o painel para gerenciar os cargos do servidor.\n"
                    "Você pode criar também os cargos automaticamente."
                ),
                disnake.ui.Separator(),
                *select_rows,
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Criar os cargos automaticamente",
                        emoji=emoji.wand,
                        style=disnake.ButtonStyle.blurple,
                        custom_id="Configuracoes_CriarTodosCargos",
                    ),
                    disnake.ui.Button(
                        label="Personalizar criacao",
                        emoji=emoji.edit,
                        style=disnake.ButtonStyle.grey,
                        custom_id="Configuracoes_CustomAutoRoles",
                    ),
                ),
                **container_kwargs,
            )
        ]

    @staticmethod
    def cargos_embed(inter: disnake.MessageInteraction):
        definicoes = db.get_document("cargos") or {}
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        guild = inter.guild
        options = []

        for key, label, emoji_icon in CARGOS_OPCOES:
            nome = "Não definido"
            cargo = None

            cargo_id = definicoes.get(key)
            if guild and cargo_id:
                try:
                    cargo = guild.get_role(int(cargo_id))
                except (TypeError, ValueError):
                    cargo = None

            if cargo:
                base = cargo.name[:25] + ("..." if len(cargo.name) > 25 else "")
                nome = f"{base} ({cargo.id})"

            options.append(
                disnake.SelectOption(
                    label=label,
                    value=key,
                    emoji=emoji_icon,
                    description=f"Cargo atual: {nome}",
                )
            )

        def chunks(seq, n=25):
            for i in range(0, len(seq), n):
                yield seq[i:i+n]

        select_rows = [
            disnake.ui.ActionRow(
                disnake.ui.Select(
                    placeholder="Escolha o cargo para configurar",
                    options=chunk,
                    custom_id=f"Configuracoes_EditarCargo:{i}",
                )
            )
            for i, chunk in enumerate(chunks(options, 25))
        ]

        embed = disnake.Embed(
            title=f"Cargos",
            description="Utilize o painel para gerenciar os cargos do servidor.\nVocê pode criar também os cargos automaticamente.",
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
                    label="Criar os cargos automaticamente",
                    emoji=emoji.wand,
                    style=disnake.ButtonStyle.blurple,
                    custom_id="Configuracoes_CriarTodosCargos",
                ),
                disnake.ui.Button(
                    label="Personalizar criacao",
                    emoji=emoji.edit,
                    style=disnake.ButtonStyle.grey,
                    custom_id="Configuracoes_CustomAutoRoles",
                ),
            ),
        ]
        return embed, components

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Configuracoes_CustomAutoRoles":
            cfg = auto_setup.get_config()
            cog = self
            source_message = inter.message

            class AutoRolesModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Personalizar cargos automaticos",
                        custom_id="Configuracoes_CustomAutoRoles_Modal",
                        components=[
                            disnake.ui.TextInput(label="Separador", custom_id="separator", value=str(cfg.get("separator") or "╺╸")[:20], max_length=20, required=True),
                            disnake.ui.TextInput(label="Modelo do nome", custom_id="role_pattern", value=str(cfg.get("role_pattern") or "{name}")[:80], max_length=80, required=True, placeholder="{name} ou {separator} {name}"),
                            disnake.ui.TextInput(label="Nomes por chave", custom_id="role_names", style=disnake.TextInputStyle.paragraph, value=cog._names_to_text(cfg.get("role_names", {}))[:900], max_length=900, required=False, placeholder="cargo_cliente=Cliente\ncargo_suporte=Suporte"),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = modal_inter.text_values
                    data = auto_setup.get_config()
                    data["separator"] = str(values.get("separator") or "╺╸").strip()[:20]
                    data["role_pattern"] = str(values.get("role_pattern") or "{name}").strip()[:80]
                    data["role_names"] = cog._parse_names(values.get("role_names"))
                    auto_setup.save_config(data)

                    mode = db.get_document("custom_mode").get("mode")
                    try:
                        if mode == "embed":
                            embed, components = ConfigurarCargos.cargos_embed(modal_inter)
                            await source_message.edit(content=None, embed=embed, components=components)
                        else:
                            await source_message.edit(content=None, embed=None, components=ConfigurarCargos.cargos_components(modal_inter), flags=disnake.MessageFlags(is_components_v2=True))
                    except Exception:
                        pass
                    await modal_inter.response.send_message(f"{emoji.correct} Personalizacao da criacao automatica de cargos salva.", ephemeral=True)

            await inter.response.send_modal(AutoRolesModal())
            return

        if inter.component.custom_id == "Configuracoes_EditarCargos":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.cargos_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.cargos_components(inter))

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
