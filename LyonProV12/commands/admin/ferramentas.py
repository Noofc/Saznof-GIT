from __future__ import annotations

import re
import uuid

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji


KEY_PREFIX = "ferramentas_"


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return value[:40] or uuid.uuid4().hex[:8]


def _safe_code(content: str, limit: int = 1800) -> str:
    content = content.strip()
    if len(content) > limit:
        content = content[:limit] + "\n..."
    return content.replace("```", "'''")


class Ferramentas(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _key(self, guild_id: int) -> str:
        return f"{KEY_PREFIX}{guild_id}"

    def _get_data(self, guild_id: int) -> dict:
        data = db.get_document(self._key(guild_id)) or {}
        data.setdefault("enabled", False)
        data.setdefault("panels_created", 0)
        scripts = data.setdefault("scripts_system", {})
        scripts.setdefault("categories", [])
        scripts.setdefault("scripts", [])
        return data

    def _save_data(self, guild_id: int, data: dict) -> None:
        db.save_document(self._key(guild_id), data)

    def _get_scripts_system(self, guild_id: int) -> dict:
        return self._get_data(guild_id).setdefault("scripts_system", {"categories": [], "scripts": []})

    def _build_ferramentas_panel(self, guild_id: int, data: dict | None = None):
        data = data or self._get_data(guild_id)
        scripts_system = data.get("scripts_system", {})
        categories = scripts_system.get("categories", [])
        scripts = scripts_system.get("scripts", [])
        ativo = data.get("enabled", False)
        status_text = "Ativo" if ativo else "Inativo"

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"## {getattr(emoji, 'tools', getattr(emoji, 'hammer', ''))} Ferramentas"),
            disnake.ui.TextDisplay("-# Painel > Ferramentas"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                "Gerencie utilitarios e o painel publico de scripts Roblox."
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"**Status:** `{status_text}`\n"
                f"**Paineis enviados:** `{data.get('panels_created', 0)}`\n"
                f"**Jogos cadastrados:** `{len(categories)}`\n"
                f"**Scripts cadastrados:** `{len(scripts)}`"
            ),
            disnake.ui.Separator(),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Desativar" if ativo else "Ativar",
                    style=disnake.ButtonStyle.red if ativo else disnake.ButtonStyle.green,
                    emoji=getattr(emoji, "power", None),
                    custom_id=f"Ferramentas_Activate:{guild_id}",
                ),
                disnake.ui.Button(
                    label="Enviar Scripts",
                    style=disnake.ButtonStyle.blurple,
                    emoji=getattr(emoji, "send", None),
                    custom_id=f"Ferramentas_CreatePanel:{guild_id}",
                    disabled=not ativo,
                ),
                disnake.ui.Button(
                    label="Listar",
                    style=disnake.ButtonStyle.grey,
                    emoji=getattr(emoji, "receipt", None),
                    custom_id=f"Ferramentas_ListScripts:{guild_id}",
                ),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Add Jogo",
                    style=disnake.ButtonStyle.success,
                    emoji=getattr(emoji, "plus", None),
                    custom_id=f"Ferramentas_AddCategory:{guild_id}",
                ),
                disnake.ui.Button(
                    label="Add Script",
                    style=disnake.ButtonStyle.success,
                    emoji=getattr(emoji, "javascript", None),
                    custom_id=f"Ferramentas_AddScript:{guild_id}",
                ),
                disnake.ui.Button(
                    label="Preview",
                    style=disnake.ButtonStyle.grey,
                    emoji=getattr(emoji, "image", None),
                    custom_id=f"Ferramentas_ManagePanels:{guild_id}",
                ),
            ),
        )


        return container, buttons2

    def display_ferramentas_panel(self, inter: disnake.MessageInteraction):
        guild_id = inter.guild.id
        container, buttons2 = self._build_ferramentas_panel(guild_id)
        return [container, buttons2]

    def _build_public_scripts_panel(self, guild_id: int) -> list:
        scripts_system = self._get_scripts_system(guild_id)
        categories = scripts_system.get("categories", [])
        scripts = scripts_system.get("scripts", [])

        if not categories:
            return [
                disnake.ui.Container(
                    disnake.ui.TextDisplay("## Painel de Scripts"),
                    disnake.ui.TextDisplay("Nenhum jogo cadastrado ainda."),
                    accent_colour=disnake.Colour.blurple(),
                )
            ]

        options = []
        for category in categories[:25]:
            total = sum(1 for script in scripts if script.get("category_id") == category.get("id"))
            options.append(
                disnake.SelectOption(
                    label=category.get("name", "Jogo")[:100],
                    value=category.get("id"),
                    description=f"{total} script(s) disponivel(is)",
                    emoji=getattr(emoji, "controller", None),
                )
            )

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay("## Painel de Scripts"),
                disnake.ui.TextDisplay("Selecione um jogo para ver os scripts disponiveis."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id=f"Scripts_GameSelect:{guild_id}",
                        placeholder="Selecione um jogo",
                        options=options,
                    )
                ),
                accent_colour=disnake.Colour.blurple(),
            )
        ]

    async def _refresh_panel(self, inter: disnake.MessageInteraction, guild_id: int, data: dict | None = None):
        container, buttons2 = self._build_ferramentas_panel(guild_id, data)
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=[container, buttons2],
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    async def _send_scripts_panel(self, inter: disnake.MessageInteraction, guild_id: int, channel_id: int):
        channel = inter.guild.get_channel(int(channel_id))
        if not isinstance(channel, disnake.TextChannel):
            await inter.response.send_message(f"{emoji.wrong} Canal invalido.", ephemeral=True)
            return

        await channel.send(
            components=self._build_public_scripts_panel(guild_id),
            flags=disnake.MessageFlags(is_components_v2=True),
        )
        data = self._get_data(guild_id)
        data["panels_created"] = data.get("panels_created", 0) + 1
        self._save_data(guild_id, data)
        await inter.response.send_message(f"{emoji.correct} Painel de scripts enviado em {channel.mention}.", ephemeral=True)

    def _category_modal(self, guild_id: int):
        class CategoryModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Adicionar Jogo",
                    custom_id=f"Ferramentas_CategoryModal:{guild_id}",
                    components=[
                        disnake.ui.TextInput(label="Nome do jogo", custom_id="name", max_length=80),
                        disnake.ui.TextInput(label="Imagem URL", custom_id="image_url", required=False, max_length=500),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                name = values.get("name", "").strip()
                image_url = values.get("image_url", "").strip()
                if len(name) < 2:
                    await modal_inter.response.send_message(f"{emoji.wrong} Nome invalido.", ephemeral=True)
                    return

                data = self._get_data(guild_id)
                scripts_system = data["scripts_system"]
                category_id = _slug(name)
                if any(item.get("id") == category_id for item in scripts_system.get("categories", [])):
                    await modal_inter.response.send_message(f"{emoji.wrong} Esse jogo ja esta cadastrado.", ephemeral=True)
                    return

                scripts_system["categories"].append({"id": category_id, "name": name, "image_url": image_url})
                self._save_data(guild_id, data)
                await modal_inter.response.send_message(f"{emoji.correct} Jogo `{name}` cadastrado.", ephemeral=True)

        return CategoryModal()

    def _script_modal(self, guild_id: int):
        class ScriptModal(disnake.ui.Modal):
            def __init__(modal_self):
                super().__init__(
                    title="Adicionar Script",
                    custom_id=f"Ferramentas_ScriptModal:{guild_id}",
                    components=[
                        disnake.ui.TextInput(label="Jogo", custom_id="category", placeholder="Nome exato do jogo cadastrado", max_length=80),
                        disnake.ui.TextInput(label="Nome do script", custom_id="name", max_length=80),
                        disnake.ui.TextInput(label="Conteudo", custom_id="content", style=disnake.TextInputStyle.paragraph, max_length=4000),
                    ],
                )

            async def callback(modal_self, modal_inter: disnake.ModalInteraction):
                values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                category_name = values.get("category", "").strip()
                name = values.get("name", "").strip()
                content = values.get("content", "").strip()
                data = self._get_data(guild_id)
                scripts_system = data["scripts_system"]
                category = next((item for item in scripts_system.get("categories", []) if item.get("id") == _slug(category_name)), None)
                if not category:
                    await modal_inter.response.send_message(f"{emoji.wrong} Jogo nao encontrado. Cadastre o jogo primeiro.", ephemeral=True)
                    return
                if len(name) < 2 or not content:
                    await modal_inter.response.send_message(f"{emoji.wrong} Nome ou conteudo invalido.", ephemeral=True)
                    return

                script_id = uuid.uuid4().hex[:8]
                scripts_system["scripts"].append(
                    {
                        "id": script_id,
                        "name": name,
                        "content": content,
                        "category_id": category["id"],
                        "category_name": category["name"],
                    }
                )
                self._save_data(guild_id, data)
                await modal_inter.response.send_message(f"{emoji.correct} Script `{name}` cadastrado em `{category['name']}`.", ephemeral=True)

        return ScriptModal()

    async def _show_scripts_list(self, inter: disnake.MessageInteraction, guild_id: int):
        scripts_system = self._get_scripts_system(guild_id)
        scripts = scripts_system.get("scripts", [])
        if not scripts:
            await inter.response.send_message(f"{emoji.wrong} Nenhum script cadastrado.", ephemeral=True)
            return

        lines = []
        for item in scripts[:20]:
            lines.append(f"- `{item.get('id')}` **{item.get('name')}** - {item.get('category_name')}")
        await inter.response.send_message("**Scripts cadastrados:**\n" + "\n".join(lines), ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "")

        if cid.startswith("Scripts_Get:"):
            _, _, guild_id_text, script_id = cid.split(":", 3)
            scripts_system = self._get_scripts_system(int(guild_id_text))
            script = next((item for item in scripts_system.get("scripts", []) if item.get("id") == script_id), None)
            if not script:
                await inter.response.send_message(f"{emoji.wrong} Script nao encontrado.", ephemeral=True)
                return
            await inter.response.send_message(
                f"**{script.get('name')}**\n```lua\n{_safe_code(script.get('content', ''))}\n```",
                ephemeral=True,
            )
            return

        if not cid.startswith("Ferramentas_"):
            return

        parts = cid.split(":")
        action = parts[0].split("_", 1)[1]
        guild_id = int(parts[1]) if len(parts) > 1 else inter.guild.id
        data = self._get_data(guild_id)

        if action == "Activate":
            await inter.response.defer(ephemeral=True)
            data["enabled"] = not data.get("enabled", False)
            self._save_data(guild_id, data)
            await self._refresh_panel(inter, guild_id, data)
            await inter.followup.send(f"{emoji.correct} Ferramentas {'ativadas' if data['enabled'] else 'desativadas'}.", ephemeral=True)
            return

        if action == "CreatePanel":
            await inter.response.send_message(
                "Selecione o canal onde o painel publico de scripts sera enviado.",
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.ChannelSelect(
                            custom_id=f"Ferramentas_SendScriptsPanel:{guild_id}",
                            placeholder="Canal do painel de scripts",
                            channel_types=[disnake.ChannelType.text],
                        )
                    )
                ],
                ephemeral=True,
            )
            return

        if action == "ManagePanels":
            await inter.response.send_message(
                components=self._build_public_scripts_panel(guild_id),
                ephemeral=True,
                flags=disnake.MessageFlags(is_components_v2=True),
            )
            return

        if action == "AddCategory":
            await inter.response.send_modal(self._category_modal(guild_id))
            return

        if action == "AddScript":
            await inter.response.send_modal(self._script_modal(guild_id))
            return

        if action == "ListScripts":
            await self._show_scripts_list(inter, guild_id)
            return

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "")
        if cid.startswith("Ferramentas_SendScriptsPanel:"):
            guild_id = int(cid.split(":", 1)[1])
            await self._send_scripts_panel(inter, guild_id, int(inter.values[0]))
            return

        if not cid.startswith("Scripts_GameSelect:"):
            return

        guild_id = int(cid.split(":", 1)[1])
        category_id = inter.values[0]
        scripts_system = self._get_scripts_system(guild_id)
        scripts = [item for item in scripts_system.get("scripts", []) if item.get("category_id") == category_id]
        if not scripts:
            await inter.response.send_message(f"{emoji.wrong} Nenhum script cadastrado para esse jogo.", ephemeral=True)
            return

        rows = []
        for chunk_start in range(0, min(len(scripts), 15), 5):
            row = disnake.ui.ActionRow()
            for item in scripts[chunk_start:chunk_start + 5]:
                row.append_item(
                    disnake.ui.Button(
                        label=item.get("name", "Script")[:80],
                        style=disnake.ButtonStyle.blurple,
                        emoji=getattr(emoji, "javascript", None),
                        custom_id=f"Scripts_Get:{guild_id}:{item.get('id')}",
                    )
                )
            rows.append(row)

        await inter.response.send_message(
            f"**Scripts encontrados:** `{len(scripts)}`\nSelecione um script para receber o conteudo.",
            components=rows,
            ephemeral=True,
        )


def setup(bot: commands.Bot):
    bot.add_cog(Ferramentas(bot))
