import disnake

from functions.database import database as db
from functions.display_mode import (
    BOT_STYLE_LABELS,
    PANEL_LAYOUT_LABELS,
    get_display_config,
)
from functions.emoji import emoji


class EditMode:
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
    def _style_options(style: str):
        return [
            disnake.SelectOption(
                label="Full Comp V2",
                value="full_v2",
                description="Todo o bot em Components V2/containers",
                default=style == "full_v2",
                emoji=emoji.commands,
            ),
            disnake.SelectOption(
                label="Embed",
                value="embed",
                description="Paineis em embed com botoes",
                default=style == "embed",
                emoji=emoji.embed,
            ),
            disnake.SelectOption(
                label="Comp V2 + Embed",
                value="hybrid",
                description="Components V2 com compatibilidade para embeds",
                default=style == "hybrid",
                emoji=emoji.wand,
            ),
        ]

    @staticmethod
    def _panel_layout_options(panel_layout: str):
        return [
            disnake.SelectOption(
                label="Botoes",
                value="buttons",
                description="Mostrar os sistemas como botoes",
                default=panel_layout == "buttons",
                emoji=emoji.commands,
            ),
            disnake.SelectOption(
                label="Select Menu",
                value="select",
                description="Mostrar os sistemas em um menu",
                default=panel_layout == "select",
                emoji=emoji.embed,
            ),
            disnake.SelectOption(
                label="Botoes + Select",
                value="both",
                description="Botoes principais e select com extras",
                default=panel_layout == "both",
                emoji=emoji.wand,
            ),
        ]

    @staticmethod
    def _style_button_row(style: str):
        return disnake.ui.ActionRow(
            disnake.ui.Button(
                label="Full Comp V2",
                style=disnake.ButtonStyle.green if style == "full_v2" else disnake.ButtonStyle.grey,
                emoji=emoji.commands,
                custom_id="Personalizacao_SetStyle_full_v2",
            ),
            disnake.ui.Button(
                label="Embed",
                style=disnake.ButtonStyle.green if style == "embed" else disnake.ButtonStyle.grey,
                emoji=emoji.embed,
                custom_id="Personalizacao_SetStyle_embed",
            ),
            disnake.ui.Button(
                label="Comp V2 + Embed",
                style=disnake.ButtonStyle.green if style == "hybrid" else disnake.ButtonStyle.grey,
                emoji=emoji.wand,
                custom_id="Personalizacao_SetStyle_hybrid",
            ),
        )

    @staticmethod
    def _panel_layout_button_row(panel_layout: str):
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
    def _button_rows(style: str, panel_layout: str):
        return [
            EditMode._style_button_row(style),
            EditMode._panel_layout_button_row(panel_layout),
        ]

    @staticmethod
    def mode_change_components(
        inter: disnake.MessageInteraction,
        display_config: dict | None = None,
    ) -> list[disnake.ui.Container]:
        display_config = display_config or get_display_config()
        style = display_config["style"]
        panel_layout = display_config["panel_layout"]

        if panel_layout == "buttons":
            return [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(
                        f"# {emoji.lyon}\n"
                        "-# Painel > **Personalizacao**"
                    ),
                    disnake.ui.Separator(),
                    disnake.ui.TextDisplay(
                        "Escolha o estilo geral do bot e como o painel inicial deve navegar."
                    ),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    disnake.ui.TextDisplay(
                        f"**Estilo atual:** `{BOT_STYLE_LABELS.get(style, style)}`\n"
                        f"**Painel inicial:** `{PANEL_LAYOUT_LABELS.get(panel_layout, panel_layout)}`"
                    ),
                    *EditMode._button_rows(style, panel_layout),
                    **EditMode._accent_kwargs(),
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

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.lyon}\n"
                    "-# Painel > **Personalizacao**"
                ),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    "Escolha o estilo geral do bot e como o painel inicial deve navegar."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"**Estilo atual:** `{BOT_STYLE_LABELS.get(style, style)}`\n"
                    f"**Painel inicial:** `{PANEL_LAYOUT_LABELS.get(panel_layout, panel_layout)}`"
                ),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Estilo do bot",
                        custom_id="Personalizacao_EditarModoExibicao",
                        options=EditMode._style_options(style),
                    )
                ),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Modo do painel inicial",
                        custom_id="Personalizacao_EditarModoExibicaoPainel",
                        options=EditMode._panel_layout_options(panel_layout),
                    )
                ),
                **EditMode._accent_kwargs(),
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
    def mode_change_embed(
        inter: disnake.MessageInteraction,
        display_config: dict | None = None,
    ):
        display_config = display_config or get_display_config()
        style = display_config["style"]
        panel_layout = display_config["panel_layout"]

        embed = disnake.Embed(
            title="Modo de Exibicao",
            description="Escolha o estilo geral do bot e como o painel inicial deve navegar.",
        )

        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")
        if primary_color_hex:
            try:
                embed.color = int(primary_color_hex.replace("#", ""), 16)
            except Exception:
                pass

        embed.add_field(
            name="Configuracao atual:",
            value=(
                f"**Estilo:** `{BOT_STYLE_LABELS.get(style, style)}`\n"
                f"**Painel inicial:** `{PANEL_LAYOUT_LABELS.get(panel_layout, panel_layout)}`"
            ),
            inline=False,
        )

        if panel_layout == "buttons":
            components = EditMode._button_rows(style, panel_layout)
        else:
            components = [
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Estilo do bot",
                        custom_id="Personalizacao_EditarModoExibicao",
                        options=EditMode._style_options(style),
                    )
                ),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Modo do painel inicial",
                        custom_id="Personalizacao_EditarModoExibicaoPainel",
                        options=EditMode._panel_layout_options(panel_layout),
                    )
                ),
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
