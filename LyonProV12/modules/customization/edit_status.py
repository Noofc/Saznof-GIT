import disnake
from disnake import *

from functions.database import database as db
from functions.display_mode import get_panel_layout
from functions.emoji import emoji
from functions.message import message, embed_message
import core

class edit_status:
    @staticmethod
    def _use_buttons() -> bool:
        return get_panel_layout() == "buttons"

    @staticmethod
    def _type_components(status_type: str) -> list[disnake.ui.ActionRow]:
        return [
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Online", style=disnake.ButtonStyle.green if status_type == "online" else disnake.ButtonStyle.grey, emoji=emoji.online, custom_id="Personalizacao_SetStatus_online"),
                disnake.ui.Button(label="Ausente", style=disnake.ButtonStyle.green if status_type == "idle" else disnake.ButtonStyle.grey, emoji=emoji.idle, custom_id="Personalizacao_SetStatus_idle"),
                disnake.ui.Button(label="DND", style=disnake.ButtonStyle.green if status_type == "dnd" else disnake.ButtonStyle.grey, emoji=emoji.dnd, custom_id="Personalizacao_SetStatus_dnd"),
                disnake.ui.Button(label="Streaming", style=disnake.ButtonStyle.green if status_type == "streaming" else disnake.ButtonStyle.grey, emoji=emoji.streaming, custom_id="Personalizacao_SetStatus_streaming"),
            )
        ]

    @staticmethod
    def _type_select_components(status_type: str) -> list[disnake.ui.ActionRow]:
        return [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    placeholder="Selecione o status desejado",
                    custom_id="Personalizacao_EditarStatus_Tipo",
                    options=[
                        disnake.SelectOption(label="Online", value="online", emoji=emoji.online, default=status_type == "online"),
                        disnake.SelectOption(label="Ausente", value="idle", emoji=emoji.idle, default=status_type == "idle"),
                        disnake.SelectOption(label="Nao Perturbar", value="dnd", emoji=emoji.dnd, default=status_type == "dnd"),
                        disnake.SelectOption(label="Transmitindo", value="streaming", emoji=emoji.streaming, default=status_type == "streaming"),
                    ],
                ),
            )
        ]

    class edit_name_status_modal(disnake.ui.Modal):
        def __init__(self):
            database = db.get_document("custom_status")
            names = database.get("names", [database.get("name", "")])
            current_names = "\n".join([name for name in names if name])[:3900]

            components = [
                disnake.ui.TextInput(
                    label="Status personalizados",
                    placeholder="Digite um status por linha",
                    custom_id="status_names",
                    value=current_names,
                    style=TextInputStyle.paragraph,
                    required=False,
                    max_length=4000,
                ),
            ]
            super().__init__(title="Editar Nomes do Status Rotativo", components=components)

        async def callback(self, inter: disnake.ModalInteraction):
            mode = db.get_document("custom_mode").get("mode")

            database = db.get_document("custom_status")
            
            raw_names = inter.text_values.get("status_names", "")
            status_names = []
            seen = set()
            for line in raw_names.splitlines():
                name = line.strip()
                if not name:
                    continue
                marker = name.lower()
                if marker in seen:
                    continue
                seen.add(marker)
                status_names.append(name[:100])
            
            database["names"] = status_names
            if "name" in database:
                del database["name"]

            db.save_document("custom_status", {}, database)
            
            await core.change_status(inter.bot)
            
            if mode == "embed":
                embed, components = edit_status.get_edit_status_panel_embed(inter)
                await inter.response.edit_message(content=None, embed=embed, components=components)
            else:
                await inter.response.edit_message(
                    components=edit_status.get_edit_status_panel_components(inter),
                )

    @staticmethod
    def get_edit_status_panel_components(inter: disnake.MessageInteraction) -> list[disnake.ui.Container]:
        status = db.get_document("custom_status")
        names = status.get("names", [status.get("name", "Nenhum")])
        display_names = names[:12] if isinstance(names, list) else []
        names_display = " | ".join(display_names) if display_names and display_names != ["Nenhum"] else "Nao configurado"
        if isinstance(names, list) and len(names) > 12:
            names_display += f" | ... (+{len(names) - 12})"

        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        statusname = {
            "online": "Online",
            "idle": "Ausente",
            "dnd": "Não Perturbar",
            "streaming": "Transmitindo",
            "offline": "Offline",
        }
        statusemoji = {
            "online": emoji.online,
            "idle": emoji.idle,
            "dnd": emoji.dnd,
            "streaming": emoji.streaming,
            "offline": emoji.off,
        }

        if edit_status._use_buttons():
            return [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(f"""
# {emoji.lyon}
-# Painel > Personalizacao > **Editar Status**
                    """),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    disnake.ui.TextDisplay(f"""
**Informacoes salvas:**
-# Tipo: {statusemoji[status["type"]]} `{statusname[status["type"]]}`
-# Nomes: `{names_display}`
                    """),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    *edit_status._type_components(status["type"]),
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Editar nome do status", emoji=emoji.edit, custom_id="Personalizacao_EditarStatus_Nome"),
                    ),
                    **container_kwargs,
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Personalizacao"),
                ),
            ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"""
# {emoji.lyon}
-# Painel > Personalização > **Editar Status**
                """),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(f"""
**Informações salvas:**
-# Tipo: {statusemoji[status["type"]]} `{statusname[status["type"]]}`
-# Nomes: `{names_display}`
                """),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Selecione o status desejado",
                        custom_id="Personalizacao_EditarStatus_Tipo",
                        options=[
                            disnake.SelectOption(label="Online", value="online", emoji=emoji.online, default=status["type"] == "online"),
                            disnake.SelectOption(label="Ausente", value="idle", emoji=emoji.idle, default=status["type"] == "idle"),
                            disnake.SelectOption(label="Não Perturbar", value="dnd", emoji=emoji.dnd, default=status["type"] == "dnd"),
                            disnake.SelectOption(label="Transmitindo", value="streaming", emoji=emoji.streaming, default=status["type"] == "streaming"),
                        ],
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Editar nome do status", emoji=emoji.edit, custom_id="Personalizacao_EditarStatus_Nome"),
                ),
                **container_kwargs,
            ),
            disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Personalizacao"),
        ]
        
    @staticmethod
    def get_edit_status_panel_embed(inter: disnake.MessageInteraction):
        status = db.get_document("custom_status")
        names = status.get("names", [status.get("name", "Nenhum")])
        display_names = names[:12] if isinstance(names, list) else []
        names_display = " | ".join(display_names) if display_names and display_names != ["Nenhum"] else "Nao configurado"
        if isinstance(names, list) and len(names) > 12:
            names_display += f" | ... (+{len(names) - 12})"
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        statusname = {
            "online": "Online",
            "idle": "Ausente",
            "dnd": "Não Perturbar",
            "streaming": "Transmitindo",
            "offline": "Offline",
        }
        statusemoji = {
            "online": emoji.online,
            "idle": emoji.idle,
            "dnd": emoji.dnd,
            "streaming": emoji.streaming,
            "offline": emoji.off,
        }
        
        embed = disnake.Embed(
            title=f"Editar Status",
            description=f"**Informações salvas:**\n-# Tipo: {statusemoji[status['type']]} `{statusname[status['type']]}`\n-# Nomes: `{names_display}`",
            # timestamp=disnake.utils.utcnow()
        )
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color

        # embed.set_footer(text=inter.guild.name, icon_url=inter.guild.icon.url if inter.guild.icon else None)
        
        if edit_status._use_buttons():
            components = [
                *edit_status._type_components(status["type"]),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Editar nome do status", emoji=emoji.edit, custom_id="Personalizacao_EditarStatus_Nome"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Personalizacao"),
                ),
            ]
            return embed, components

        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    placeholder="Selecione o status desejado",
                    custom_id="Personalizacao_EditarStatus_Tipo",
                    options=[
                        disnake.SelectOption(label="Online", value="online", emoji=emoji.online, default=status["type"] == "online"),
                        disnake.SelectOption(label="Ausente", value="idle", emoji=emoji.idle, default=status["type"] == "idle"),
                        disnake.SelectOption(label="Não Perturbar", value="dnd", emoji=emoji.dnd, default=status["type"] == "dnd"),
                        disnake.SelectOption(label="Transmitindo", value="streaming", emoji=emoji.streaming, default=status["type"] == "streaming"),
                    ],
                ),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Editar nome do status", emoji=emoji.edit, custom_id="Personalizacao_EditarStatus_Nome"),
            ),
            disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Personalizacao"),
        ]
        return embed, components

    @staticmethod
    async def save_status(tipo: str, inter: disnake.MessageInteraction):
        status = db.get_document("custom_status") or {}
        status["type"] = tipo
        db.save_document("custom_status", {}, status)

        # O status já foi salvo. Uma falha ao iniciar/atualizar a tarefa
        # de presença não deve transformar uma operação bem-sucedida em
        # uma mensagem falsa de erro para o usuário.
        try:
            await core.change_status(inter.bot)
        except Exception as exc:
            print(f"[Status] Status salvo, mas a presença não foi atualizada imediatamente: {type(exc).__name__}: {exc}")

        return status
