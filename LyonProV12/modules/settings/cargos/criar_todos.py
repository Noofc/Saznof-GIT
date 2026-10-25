import random

import disnake
from disnake.ext import commands

from functions import auto_setup
from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from functions.system_logs import send_system_log
from .listar import CARGOS_OPCOES, CARGOS_CORES
from .cog import ConfigurarCargos


class MensagensCargos:
    @staticmethod
    def cargo_criado_components(cargo: disnake.Role, auto: bool) -> disnake.ui.Container:
        origem = "Criar Todos os Cargos Automaticamente" if auto else "Criar Cargo"
        return disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# {origem} > Cargo Criado"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(f"**Informacoes do cargo:**\nID: `{cargo.id}`\nNome: `{cargo.name}`\nMencao: {cargo.mention}"),
        )

    @staticmethod
    def cargos_criados_components(criados: list[disnake.Role]) -> list[disnake.ui.Container]:
        cargos = ", ".join(f"{c.mention} (`{c.id}`)" for c in criados)
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    "**Informacoes dos cargos criados:**\n"
                    f"`{len(criados)}` cargos criados com sucesso."
                ),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(cargos[:3900]),
            )
        ]

    @staticmethod
    def cargo_criado_embed(cargo: disnake.Role, auto: bool):
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")
        embed = disnake.Embed(
            title="Cargo Criado",
            description=f"**Informacoes do cargo:**\nID: `{cargo.id}`\nNome: `{cargo.name}`\nMencao: {cargo.mention}",
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)
        return embed, []

    @staticmethod
    def cargos_criados_embed(criados: list[disnake.Role]):
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")
        embed = disnake.Embed(
            title="Cargos Criados",
            description=f"`{len(criados)}` cargos criados com sucesso.",
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)
        embed.add_field(
            name="Cargos:",
            value=", ".join(f"{c.mention} (`{c.id}`)" for c in criados)[:1024],
        )
        return embed, []


class CriarTodosCargos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener("on_button_click")
    async def criar_todos_cargos(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id != "Configuracoes_CriarTodosCargos":
            return

        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter, send=False)

        defs = db.get_document("cargos") or {}
        setup_cfg = auto_setup.get_config()
        guild = inter.guild
        if not guild:
            return

        criados = []
        for key, label, _ in CARGOS_OPCOES:
            role_id = defs.get(key)
            if role_id:
                try:
                    if guild.get_role(int(role_id)):
                        continue
                except (ValueError, TypeError):
                    pass

            name = auto_setup.role_name(key, label, setup_cfg)
            existing_role_by_name = disnake.utils.get(guild.roles, name=name)
            if existing_role_by_name:
                defs[key] = str(existing_role_by_name.id)
                continue

            try:
                cargo = await guild.create_role(
                    name=name,
                    reason=f"Auto-criacao pelo painel de configuracoes - {inter.author.name} ({inter.author.id})",
                    color=disnake.Color(CARGOS_CORES[random.randint(0, len(CARGOS_CORES) - 1)]),
                )
            except Exception as exc:
                print(f"[Cargos] Falha ao criar {key}: {exc}")
                continue

            defs[key] = str(cargo.id)
            criados.append(cargo)

        db.save_document("cargos", {}, defs)

        if criados:
            await send_system_log(
                self.bot,
                guild,
                title="Cargos automaticos criados",
                system="Configuracoes",
                description=f"Foram criados `{len(criados)}` cargos automaticamente.\n" + "\n".join(f"- {c.mention} (`{c.name}`)" for c in criados[:20]),
                actor=inter.user,
            )

        if mode == "embed":
            embed, components = ConfigurarCargos.cargos_embed(inter)
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            await inter.edit_original_message(components=ConfigurarCargos.cargos_components(inter))

        if criados:
            if mode == "embed":
                embed, components = MensagensCargos.cargos_criados_embed(criados)
                await inter.followup.send(embed=embed, components=components, ephemeral=True)
            else:
                await inter.followup.send(
                    components=MensagensCargos.cargos_criados_components(criados),
                    flags=disnake.MessageFlags(is_components_v2=True),
                    ephemeral=True,
                )
