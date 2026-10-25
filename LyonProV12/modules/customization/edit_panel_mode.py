import disnake

from functions.database import database as db
from functions.display_mode import PANEL_LAYOUT_LABELS, get_panel_layout
from functions.emoji import emoji


class EditPanelMode:
    @staticmethod
    def _accent_kwargs():
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")
        if not primary_color_hex:
            return {}
        try:
            return {"accent_colour": disnake.Colour(int(primary_color_hex.replace("#", ""), 16))}
        except Exception:
            return {}

    @staticmethod
    def _options(panel_layout: str):
        return [
            disnake.SelectOption(
                label="Botoes",
                value="buttons",
                description="Exibir todos os sistemas como botoes",
                default=panel_layout == "buttons",
                emoji=emoji.commands,
            ),
            disnake.SelectOption(
                label="Select Menu",
                value="select",
                description="Exibir todos os sistemas em um menu",
                default=panel_layout == "select",
                emoji=emoji.embed,
            ),
            disnake.SelectOption(
                label="Botoes + Select",
                value="both",
                description="Botoes principais e select para extras",
                default=panel_layout == "both",
                emoji=emoji.wand,
            ),
        ]

    @staticmethod
    def _button_row(panel_layout: str):
        return disnake.ui.ActionRow(
            disnake.ui.Button(
                label="Botoes",
                style=disnake.ButtonStyle.green if panel_layout == "buttons" else disnake.ButtonStyle.grey,
                emoji=emoji.commands,
                custom_id="Personalizacao_SetPanelLayout_buttons",
            ),
            disnake.ui.Button(
                label="Select Menu",
                style=disnake.ButtonStyle.green if panel_layout == "select" else disnake.ButtonStyle.grey,
                emoji=emoji.embed,
                custom_id="Personalizacao_SetPanelLayout_select",
            ),
            disnake.ui.Button(
                label="Botoes + Select",
                style=disnake.ButtonStyle.green if panel_layout == "both" else disnake.ButtonStyle.grey,
                emoji=emoji.wand,
                custom_id="Personalizacao_SetPanelLayout_both",
            ),
        )

    @staticmethod
    def panel_mode_change_components(
        inter: disnake.MessageInteraction,
        panel_layout: str | None = None,
    ) -> list[disnake.ui.Container]:
        panel_layout = panel_layout or get_panel_layout()
        selector_component = (
            EditPanelMode._button_row(panel_layout)
            if panel_layout == "buttons"
            else disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    placeholder="Modo de exibicao do painel",
                    custom_id="Personalizacao_EditarModoExibicaoPainel",
                    options=EditPanelMode._options(panel_layout),
                )
            )
        )
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.lyon}\n"
                    "-# Painel > **Personalizacao**"
                ),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("Selecione como o /painel inicial deve exibir os sistemas."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(f"**Modo atual:** `{PANEL_LAYOUT_LABELS.get(panel_layout, panel_layout)}`"),
                selector_component,
                **EditPanelMode._accent_kwargs(),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Painel_Personalizacao",
                ),
            ),
        ]

    @staticmethod
    def panel_mode_change_embed(
        inter: disnake.MessageInteraction,
        panel_layout: str | None = None,
    ):
        panel_layout = panel_layout or get_panel_layout()
        embed = disnake.Embed(
            title="Modo de Exibicao do Painel",
            description="Selecione como o /painel inicial deve exibir os sistemas.",
        )

        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")
        if primary_color_hex:
            try:
                embed.color = int(primary_color_hex.replace("#", ""), 16)
            except Exception:
                pass

        embed.add_field(
            name="Modo atual:",
            value=f"`{PANEL_LAYOUT_LABELS.get(panel_layout, panel_layout)}`",
            inline=False,
        )

        if panel_layout == "buttons":
            components = [EditPanelMode._button_row(panel_layout)]
        else:
            components = [
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Modo de exibicao do painel",
                        custom_id="Personalizacao_EditarModoExibicaoPainel",
                        options=EditPanelMode._options(panel_layout),
                    )
                )
            ]

        components.append(
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Painel_Personalizacao",
                ),
            )
        )
        return embed, components
