import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.display_mode import get_bot_mode, get_panel_layout, save_bot_style, save_panel_layout
from functions.emoji import emoji
from functions.message import message, embed_message
from .edit_info import edit_info_bot_modal
from .edit_status import edit_status
from .edit_colors import EditColorsCog, EditColorsModal
from .edit_mode import EditMode
from .edit_panel_mode import EditPanelMode

class Personalizacao(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _safe_defer(
        self,
        inter: disnake.MessageInteraction,
        ephemeral: bool = False,
        with_message: bool = False,
    ) -> bool:
        if inter.response.is_done():
            return True
        try:
            await inter.response.defer(with_message=with_message, ephemeral=ephemeral)
            return True
        except (disnake.NotFound, disnake.HTTPException):
            return False

    def _v2_flags(self) -> disnake.MessageFlags:
        return disnake.MessageFlags(is_components_v2=True)

    def _button_layout_enabled(self) -> bool:
        return get_panel_layout() == "buttons"

    def _main_button_rows(self) -> list[disnake.ui.ActionRow]:
        return [
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Editar Status", style=disnake.ButtonStyle.grey, emoji=emoji.edit, custom_id="Personalizacao_EditarStatus"),
                disnake.ui.Button(label="Editar Info", style=disnake.ButtonStyle.grey, emoji=emoji.coupon, custom_id="Personalizacao_EditarInfo"),
                disnake.ui.Button(label="Modo do Pro", style=disnake.ButtonStyle.grey, emoji=emoji.embed, custom_id="Personalizacao_ModoExibicao"),
            ),
        ]

    def _main_select_rows(self) -> list[disnake.ui.ActionRow]:
        return [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Personalizacao_Select",
                    placeholder="Selecione uma secao para configurar",
                    options=[
                        disnake.SelectOption(label="Editar Status", value="editar_status", description="Atualize tipo e nomes do status", emoji=emoji.edit),
                        disnake.SelectOption(label="Editar Informacoes", value="editar_info", description="Atualize nome, avatar e informacoes do bot", emoji=emoji.coupon),
                        disnake.SelectOption(label="Modo de Exibicao", value="modo_exibicao", description="Alterne entre embed e components", emoji=emoji.embed),
                        disnake.SelectOption(label="Modo do Painel", value="modo_exibicao_painel", description="Alterne entre botoes e select menu", emoji=emoji.commands),
                        disnake.SelectOption(label="Editar Cores", value="editar_cores", description="Personalize as cores do bot", emoji=emoji.wand),
                    ],
                )
            ),
        ]

    async def _edit_v2(self, inter: disnake.MessageInteraction, components: list):
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=components,
            flags=self._v2_flags(),
        )

    async def _edit_response_v2(self, inter: disnake.MessageInteraction, components: list):
        await inter.edit_original_response(
            content=None,
            embed=None,
            components=components,
            flags=self._v2_flags(),
        )

    def personalizacao_components(self, inter: disnake.MessageInteraction) -> list[disnake.ui.Container]:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        primary_hex = primary_color_hex or "#5c5ef0"
        try:
            primary_color = int(primary_hex.replace("#", ""), 16)
        except Exception:
            primary_color = int("5c5ef0", 16)
        container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        if self._button_layout_enabled():
            return [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > **Personalizacao**"),
                    disnake.ui.Separator(),
                    disnake.ui.TextDisplay(
                        "Configure e personalize o status, informacoes, cores e o modo de exibicao do bot.\n"
                        "Escolha uma secao abaixo para configurar."
                    ),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    *self._main_button_rows(),
                    **container_kwargs,
                ),
            ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > **Personalização**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    "Configure e personalize o status, informações, cores e o modo de exibição do bot.\n"
                    "Selecione uma seção abaixo para configurar."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Personalizacao_Select",
                        placeholder="Selecione uma seção para configurar",
                        options=[
                            disnake.SelectOption(label="Editar Status", value="editar_status", description="Atualize tipo e nomes do status", emoji=emoji.edit),
                            disnake.SelectOption(label="Editar Informações", value="editar_info", description="Atualize nome, avatar e informações do bot", emoji=emoji.coupon),
                            disnake.SelectOption(label="Modo de Exibição", value="modo_exibicao", description="Alterne entre embed e components", emoji=emoji.embed),
                            disnake.SelectOption(label="Modo de Exibição do Painel", value="modo_exibicao_painel", description="Alterne entre botões e select menu", emoji=emoji.commands),
                            disnake.SelectOption(label="Editar Cores", value="editar_cores", description="Personalize as cores do bot", emoji=emoji.wand),
                        ],
                    )
                ),
                **container_kwargs,
            ),
        ]
        
    def personalizacao_embed(self, inter: disnake.MessageInteraction):
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        embed = disnake.Embed(
            title=f"Personalização",
            description="Configure e personalize o status, informações, cores e o modo de exibição do bot.\nSelecione uma seção abaixo para configurar.",
            # timestamp=disnake.utils.utcnow()
        )
        primary_hex = primary_color_hex or "#5c5ef0"
        try:
            primary_color = int(primary_hex.replace("#", ""), 16)
        except Exception:
            primary_color = int("5c5ef0", 16)
        embed.color = primary_color
        
        # embed.set_footer(text=inter.guild.name, icon_url=inter.guild.icon.url if inter.guild.icon else None)
        if self._button_layout_enabled():
            return embed, self._main_button_rows()

        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Personalizacao_Select",
                    placeholder="Selecione uma seção para configurar",
                    options=[
                        disnake.SelectOption(label="Editar Status", value="editar_status", description="Atualize tipo e nomes do status", emoji=emoji.edit),
                        disnake.SelectOption(label="Editar Informações", value="editar_info", description="Atualize nome, avatar e informações do bot", emoji=emoji.coupon),
                        disnake.SelectOption(label="Modo de Exibição", value="modo_exibicao", description="Alterne entre embed e components", emoji=emoji.embed),
                        disnake.SelectOption(label="Modo de Exibição do Painel", value="modo_exibicao_painel", description="Alterne entre botões e select menu", emoji=emoji.commands),
                        disnake.SelectOption(label="Editar Cores", value="editar_cores", description="Personalize as cores do bot", emoji=emoji.wand),
                    ],
                )
            ),
        ]
        return embed, components

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        mode = "components"

        if inter.component.custom_id == "Painel_Personalizacao":
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.personalizacao_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await self._edit_v2(inter, self.personalizacao_components(inter))

        elif inter.component.custom_id == "Personalizacao_EditarCores":
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = EditColorsCog.get_panel_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await self._edit_v2(inter, EditColorsCog.get_panel_components(inter))

        elif inter.component.custom_id == "Personalizacao_EditarCores_Modal":
            await inter.response.send_modal(EditColorsModal())

        elif inter.component.custom_id == "Personalizacao_VisualizarCores":
            if not await self._safe_defer(inter, ephemeral=True, with_message=True):
                return
            if mode == "embed":
                embeds, components = EditColorsCog.get_preview_embed(inter)
                await inter.edit_original_response(embeds=embeds, components=components)
            else:
                components = EditColorsCog.get_preview_components(inter)
                await self._edit_response_v2(inter, components)

        elif inter.component.custom_id == "Personalizacao_VisualizarCores_Voltar":
            if not await self._safe_defer(inter):
                return
            if mode == "embed":
                embed, components = EditColorsCog.get_panel_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                components = EditColorsCog.get_panel_components(inter)
                await self._edit_v2(inter, components)

        elif inter.component.custom_id == "Personalizacao_ModoExibicao":
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = EditMode.mode_change_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await self._edit_v2(inter, EditMode.mode_change_components(inter))

        elif inter.component.custom_id == "Personalizacao_ModoExibicaoPainel":
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = EditPanelMode.panel_mode_change_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await self._edit_v2(inter, EditPanelMode.panel_mode_change_components(inter))

        elif inter.component.custom_id.startswith("Personalizacao_SetStyle_"):
            if not await self._safe_defer(inter):
                return
            style = inter.component.custom_id.replace("Personalizacao_SetStyle_", "", 1)
            config = save_bot_style(style)
            await self._edit_v2(inter, EditMode.mode_change_components(inter, config))

        elif inter.component.custom_id.startswith("Personalizacao_SetPanelLayout_"):
            if not await self._safe_defer(inter):
                return
            layout = inter.component.custom_id.replace("Personalizacao_SetPanelLayout_", "", 1)
            config = save_panel_layout(layout)
            await self._edit_v2(inter, EditPanelMode.panel_mode_change_components(inter, config.get("panel_layout")))

        elif inter.component.custom_id == "Personalizacao_EditarInfo":
            default_name = (inter.bot.user.name if getattr(inter.bot, 'user', None) and inter.bot.user else None)
            await inter.response.send_modal(edit_info_bot_modal(default_name=default_name))

        elif inter.component.custom_id == "Personalizacao_EditarStatus":
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = edit_status.get_edit_status_panel_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await self._edit_v2(inter, edit_status.get_edit_status_panel_components(inter))

        elif inter.component.custom_id.startswith("Personalizacao_SetStatus_"):
            if not await self._safe_defer(inter):
                return
            status_type = inter.component.custom_id.replace("Personalizacao_SetStatus_", "", 1)
            try:
                await edit_status.save_status(status_type, inter)
            except Exception as exc:
                print(f"[Status] Erro ao salvar status: {type(exc).__name__}: {exc}")
                await inter.followup.send(f"{emoji.wrong} Não foi possível salvar esse status agora.", ephemeral=True)
                return
            try:
                await self._edit_v2(inter, edit_status.get_edit_status_panel_components(inter))
            except Exception as exc:
                print(f"[Status] Status atualizado, mas o painel não foi atualizado: {type(exc).__name__}: {exc}")
                await inter.followup.send(f"{emoji.correct} Status atualizado. Reabra o painel para visualizar a alteração.", ephemeral=True)

        elif inter.component.custom_id == "Personalizacao_EditarStatus_Nome":
            await inter.response.send_modal(edit_status.edit_name_status_modal())

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        mode = get_bot_mode()
        if inter.component.custom_id == "Personalizacao_Select":
            choice = inter.values[0]
            if choice == "editar_info":
                default_name = (inter.bot.user.name if getattr(inter.bot, 'user', None) and inter.bot.user else None)
                await inter.response.send_modal(edit_info_bot_modal(default_name=default_name))
                return
            elif choice == "editar_cores":
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = EditColorsCog.get_panel_embed(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    await self._edit_v2(inter, EditColorsCog.get_panel_components(inter))
                return
            elif choice == "modo_exibicao":
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = EditMode.mode_change_embed(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    await self._edit_v2(inter, EditMode.mode_change_components(inter))
                return
            elif choice == "modo_exibicao_painel":
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = EditPanelMode.panel_mode_change_embed(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    await self._edit_v2(inter, EditPanelMode.panel_mode_change_components(inter))
                return
            elif choice == "editar_status":
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = edit_status.get_edit_status_panel_embed(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    await self._edit_v2(inter, edit_status.get_edit_status_panel_components(inter))
                return
        if inter.component.custom_id == "Personalizacao_EditarStatus_Tipo":
            if not await self._safe_defer(inter):
                return
            try:
                await edit_status.save_status(inter.values[0], inter)
            except Exception as exc:
                print(f"[Status] Erro ao salvar status selecionado: {type(exc).__name__}: {exc}")
                await inter.followup.send(f"{emoji.wrong} Não foi possível salvar esse status agora.", ephemeral=True)
                return
            try:
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = edit_status.get_edit_status_panel_embed(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    await self._edit_v2(inter, edit_status.get_edit_status_panel_components(inter))
            except Exception as exc:
                print(f"[Status] Status selecionado, mas o painel não foi atualizado: {type(exc).__name__}: {exc}")
                await inter.followup.send(f"{emoji.correct} Status atualizado. Reabra o painel para visualizar a alteração.", ephemeral=True)

        elif inter.component.custom_id == "Personalizacao_EditarModoExibicao":
            if not await self._safe_defer(inter):
                return

            config = save_bot_style(inter.values[0])
            components = EditMode.mode_change_components(inter, config)
            await self._edit_v2(inter, components)

        elif inter.component.custom_id == "Personalizacao_EditarModoExibicaoPainel":
            if not await self._safe_defer(inter):
                return

            config = save_panel_layout(inter.values[0])
            
            # Atualizar a mensagem atual para refletir a mudança
            components = EditPanelMode.panel_mode_change_components(inter, config.get("panel_layout"))
            await self._edit_v2(inter, components)
