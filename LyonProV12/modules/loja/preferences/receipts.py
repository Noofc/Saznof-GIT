import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji

KEY_PREFIX = "loja_receipt_style_"

STYLE_INFO = {
    "v2": {
        "name": "Componentes V2",
        "summary": "Comprovante em container moderno, sem embed e sem imagem.",
        "preview": (
            "## Compra Realizada\n"
            "**Cliente:** @cliente\n"
            "**Carrinho:** 1x Produto | Campo\n"
            "**Valor pago:** R$ 19,90\n"
            "Botoes: Comprar, Ver Feedbacks e Suporte."
        ),
        "buttons": ("Comprar", "Ver Feedbacks", "Suporte"),
    },
    "image": {
        "name": "Imagem Moderna",
        "summary": "Comprovante em imagem escura no estilo do modelo visual.",
        "preview": (
            "Imagem com avatar, data, status Compra Realizada, carrinho, subtotal, valor pago, "
            "pedido e rodape Powered by Lyon Pro."
        ),
        "buttons": ("Comprar", "Ver Feedbacks", "Suporte"),
    },
    "embed": {
        "name": "Embed",
        "summary": "Comprovante classico em embed para servidores que preferem o formato antigo.",
        "preview": (
            "**Recibo de Compra**\n"
            "Pedido, cliente, produtos, subtotal e total aparecem em campos do embed."
        ),
        "buttons": ("Comprar", "Ver Feedbacks", "Suporte"),
    },
}

STYLE_ALIASES = {
    1: "v2",
    2: "image",
    3: "embed",
    "1": "v2",
    "2": "image",
    "3": "embed",
    "component": "v2",
    "components": "v2",
    "componentes": "v2",
    "v2": "v2",
    "image": "image",
    "imagem": "image",
    "modern": "image",
    "moderno": "image",
    "embed": "embed",
}


def normalize_receipt_style(value) -> str:
    if isinstance(value, dict):
        value = value.get("style", "v2")
    if isinstance(value, str):
        value = value.strip().lower()
    return STYLE_ALIASES.get(value, "v2")


def current_receipt_style(guild_id: int) -> str:
    stored = db.get_document(f"{KEY_PREFIX}{guild_id}")
    return normalize_receipt_style(stored)


def sync_purchase_event_style(style: str) -> None:
    config = db.get_document("loja_personalization") or {}
    event = config.get("purchase_event") or {}
    event["mode"] = normalize_receipt_style(style)
    config["purchase_event"] = event
    db.save_document("loja_personalization", config)


def receipt_style_name(style: str) -> str:
    return STYLE_INFO.get(normalize_receipt_style(style), STYLE_INFO["v2"])["name"]


def _style_button(guild_id: int, style: str, current_style: str) -> disnake.ui.Button:
    applied = style == current_style
    info = STYLE_INFO[style]
    return disnake.ui.Button(
        label=f"{info['name']} aplicado" if applied else info["name"],
        style=disnake.ButtonStyle.success if applied else disnake.ButtonStyle.secondary,
        custom_id=f"Loja_Receipts_Style:{guild_id}:{style}",
        disabled=applied,
    )


def _preview_buttons(style: str) -> disnake.ui.ActionRow:
    buttons = [
        disnake.ui.Button(
            label=label,
            style=disnake.ButtonStyle.grey,
            custom_id=f"Loja_Receipts_Preview_{style}_{index}",
            disabled=True,
        )
        for index, label in enumerate(STYLE_INFO[style]["buttons"])
    ]
    return disnake.ui.ActionRow(*buttons)


class ReceiptPreferences(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def panel(inter: disnake.MessageInteraction):
        guild_id = inter.guild.id
        style = current_receipt_style(guild_id)
        info = STYLE_INFO[style]

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {emoji.receipt} Preferencias de Comprovante"),
            disnake.ui.TextDisplay("-# Painel > Loja > Preferencias > Comprovante"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"{emoji.correct} **Aplicado agora:** `{info['name']}`\n"
                f"-# {info['summary']}"
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                "## Previa de como vai ficar aplicado\n"
                f"{info['preview']}"
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                "Escolha o modelo dos proximos comprovantes enviados apos uma compra."
            ),
        )

        buttons = disnake.ui.ActionRow(
            _style_button(guild_id, "v2", style),
            _style_button(guild_id, "image", style),
            _style_button(guild_id, "embed", style),
        )
        back = disnake.ui.ActionRow(
            disnake.ui.Button(
                label="",
                style=disnake.ButtonStyle.grey,
                custom_id="Loja_Preferencias",
            )
        )

        return {"embed": None, "components": [container, buttons, _preview_buttons(style), back]}

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        if not cid.startswith("Loja_Receipts_"):
            return

        if cid.startswith("Loja_Receipts_Preview_"):
            return

        parts = cid.split(":")
        if len(parts) < 3 or parts[0] != "Loja_Receipts_Style":
            return

        guild_id = int(parts[1]) if parts[1].isdigit() else inter.guild.id
        style = normalize_receipt_style(parts[2])
        db.save_document(f"{KEY_PREFIX}{guild_id}", {"style": style})
        sync_purchase_event_style(style)

        if not inter.response.is_done():
            await inter.response.defer(with_message=False)

        panel = ReceiptPreferences.panel(inter)
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=panel["components"],
            flags=disnake.MessageFlags(is_components_v2=True),
        )
        await inter.followup.send(
            f"{emoji.correct} {STYLE_INFO[style]['name']} aplicado aos proximos comprovantes.",
            ephemeral=True,
        )


def setup(bot: commands.Bot):
    bot.add_cog(ReceiptPreferences(bot))
