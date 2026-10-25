import random

import disnake
from disnake.ext import commands

from functions import auto_setup
from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from functions.system_logs import send_system_log
from .criar_todos import MensagensCargos
from .listar import CARGOS_OPCOES, CARGOS_CORES


class ConfigurarCargo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def cargo_components(inter: disnake.MessageInteraction, cargo_key: str) -> list[disnake.ui.Container]:
        definicoes = db.get_document("cargos") or {}
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

        try:
            cargo_id = int(definicoes.get(cargo_key))
        except Exception:
            cargo_id = None

        cargo = next((c for c in CARGOS_OPCOES if c[0] == cargo_key), None)
        cargo_nome = cargo[1] if cargo else cargo_key
        cargo_obj = inter.guild.get_role(cargo_id) if inter.guild and cargo_id else None
        cargo_id_str = f"`{cargo_obj.id}`" if cargo_obj else "`Nao definido`"
        cargo_name = cargo_obj.mention if cargo_obj else "`Nao definido`"

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Configuracoes > Cargos > **{cargo_nome}**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("Gerencie o cargo selecionado ou deixe o bot criar usando o modelo personalizado."),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(f"**Cargo selecionado:** `{cargo_nome}`\n**Cargo atual:** {cargo_name} ({cargo_id_str})"),
                disnake.ui.ActionRow(
                    disnake.ui.RoleSelect(
                        placeholder="Selecione um cargo para definir",
                        custom_id=f"Configuracoes_EditarNovoCargo:{cargo_key}",
                        min_values=1,
                        max_values=1,
                    )
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Apagar", emoji=emoji.delete, custom_id=f"Configuracoes_ApagarCargo:{cargo_key}", style=disnake.ButtonStyle.red, disabled=cargo_obj is None),
                    disnake.ui.Button(label="Criar o cargo para mim", emoji=emoji.wand, custom_id=f"Configuracoes_CriarCargo:{cargo_key}", style=disnake.ButtonStyle.blurple),
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(disnake.ui.Button(label="", emoji=emoji.back, custom_id="Configuracoes_EditarCargos")),
        ]

    @staticmethod
    def cargo_embed(inter: disnake.MessageInteraction, cargo_key: str):
        definicoes = db.get_document("cargos") or {}
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        try:
            cargo_id = int(definicoes.get(cargo_key))
        except Exception:
            cargo_id = None

        cargo = next((c for c in CARGOS_OPCOES if c[0] == cargo_key), None)
        cargo_nome = cargo[1] if cargo else cargo_key
        cargo_obj = inter.guild.get_role(cargo_id) if inter.guild and cargo_id else None
        cargo_id_str = f"`{cargo_obj.id}`" if cargo_obj else "`Nao definido`"
        cargo_name = cargo_obj.mention if cargo_obj else "`Nao definido`"

        embed = disnake.Embed(
            title=cargo_nome,
            description="Gerencie o cargo selecionado ou deixe o bot criar usando o modelo personalizado.",
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)
        embed.add_field(name="Cargo selecionado:", value=f"`{cargo_nome}`")
        embed.add_field(name="Cargo atual:", value=f"{cargo_name} ({cargo_id_str})")

        components = [
            disnake.ui.ActionRow(
                disnake.ui.RoleSelect(
                    placeholder="Selecione um cargo para definir",
                    custom_id=f"Configuracoes_EditarNovoCargo:{cargo_key}",
                    min_values=1,
                    max_values=1,
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Apagar", emoji=emoji.delete, custom_id=f"Configuracoes_ApagarCargo:{cargo_key}", style=disnake.ButtonStyle.red, disabled=cargo_obj is None),
                disnake.ui.Button(label="Criar o cargo para mim", emoji=emoji.wand, custom_id=f"Configuracoes_CriarCargo:{cargo_key}", style=disnake.ButtonStyle.blurple),
            ),
            disnake.ui.ActionRow(disnake.ui.Button(label="", emoji=emoji.back, custom_id="Configuracoes_EditarCargos")),
        ]
        return embed, components

    @commands.Cog.listener("on_button_click")
    async def configurar_cargos_button_listener(self, inter: disnake.MessageInteraction):
        mode = db.get_document("custom_mode").get("mode")
        custom_id = inter.component.custom_id

        if custom_id.startswith("Configuracoes_ApagarCargo"):
            cargo_key = custom_id.split(":")[1]
            cargos_db = db.get_document("cargos") or {}
            cargos_db[cargo_key] = None
            db.save_document("cargos", {}, cargos_db)

            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.cargo_embed(inter, cargo_key)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.cargo_components(inter, cargo_key))

        elif custom_id.startswith("Configuracoes_CriarCargo"):
            cargo_key = custom_id.split(":")[1]
            cargo_info = next((c for c in CARGOS_OPCOES if c[0] == cargo_key), None)
            cargo_label = cargo_info[1] if cargo_info else cargo_key
            name = auto_setup.role_name(cargo_key, cargo_label, auto_setup.get_config())
            cargo = None

            try:
                cargo = await inter.guild.create_role(
                    color=disnake.Color(CARGOS_CORES[random.randint(0, len(CARGOS_CORES) - 1)]),
                    name=name,
                    reason=f"Auto-criacao pelo painel de configuracoes - {inter.user.name} ({inter.user.id})",
                )
            except Exception as exc:
                print(f"[Cargos] Falha ao criar {cargo_key}: {exc}")

            if cargo:
                cargos_db = db.get_document("cargos") or {}
                cargos_db[cargo_key] = str(cargo.id)
                db.save_document("cargos", {}, cargos_db)

            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.cargo_embed(inter, cargo_key)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.cargo_components(inter, cargo_key))

            if cargo:
                if mode == "embed":
                    embed, components = MensagensCargos.cargo_criado_embed(cargo, auto=False)
                    await inter.followup.send(embed=embed, components=components, ephemeral=True)
                else:
                    await inter.followup.send(components=MensagensCargos.cargo_criado_components(cargo, auto=False), flags=disnake.MessageFlags(is_components_v2=True), ephemeral=True)
                await send_system_log(
                    self.bot,
                    inter.guild,
                    title="Cargo criado",
                    system="Configuracoes",
                    description=f"Cargo {cargo.mention} (`{cargo.name}`) criado para `{cargo_key}`.",
                    actor=inter.user,
                )

    @commands.Cog.listener("on_dropdown")
    async def configurar_cargos_dropdown_listener(self, inter: disnake.MessageInteraction):
        mode = db.get_document("custom_mode").get("mode")
        custom_id = inter.component.custom_id

        if custom_id.startswith("Configuracoes_EditarCargo"):
            cargo_key = inter.values[0]
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.cargo_embed(inter, cargo_key)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.cargo_components(inter, cargo_key))

        elif custom_id.startswith("Configuracoes_EditarNovoCargo"):
            cargo_key = custom_id.replace("Configuracoes_EditarNovoCargo:", "")
            cargo_id = inter.values[0]
            cargos_db = db.get_document("cargos") or {}
            cargos_db[cargo_key] = cargo_id
            db.save_document("cargos", {}, cargos_db)

            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.cargo_embed(inter, cargo_key)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.cargo_components(inter, cargo_key))
