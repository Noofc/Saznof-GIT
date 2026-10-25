import secrets

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from .panel_v2 import build_panel_card


class GiftCardPanel(commands.Cog):
    """Sistema de Gift Cards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def display_giftcard_panel(self, inter: disnake.MessageInteraction):
        giftcards = db.get_document("giftcards_list") or {}
        cards = giftcards.get("cards", [])
        title_emoji = getattr(emoji, "gift", "")

        return build_panel_card(
            title=f"{title_emoji} Gift Cards".strip(),
            breadcrumb="Painel > Gift Cards",
            description="Crie e gerencie codigos de gift card para sua loja.",
            status_lines=[
                f"**Total:** `{len(cards)}`",
                f"**Disponiveis:** `{len([card for card in cards if not card.get('redeemed_by')])}`",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Criar", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "plus", None), custom_id="GiftCard_Criar"),
                    disnake.ui.Button(label="Resgatar", style=disnake.ButtonStyle.success, emoji=getattr(emoji, "gift", None), custom_id="GiftCard_Resgatar", disabled=not cards),
                    disnake.ui.Button(label="Listar", style=disnake.ButtonStyle.blurple, emoji=getattr(emoji, "receipt", None), custom_id="GiftCard_Listar", disabled=not cards),
                    disnake.ui.Button(label="Config", style=disnake.ButtonStyle.grey, emoji=getattr(emoji, "settings2", None), custom_id="GiftCard_Config"),
                )
            ],
        )

    @commands.Cog.listener("on_message_interaction")
    async def GiftCard_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if not custom_id.startswith("GiftCard"):
            return

        if custom_id == "GiftCard_Criar":
            class GiftCardModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Criar gift card",
                        custom_id="GiftCard_CreateModal",
                        components=[
                            disnake.ui.TextInput(label="Codigo", custom_id="code", required=False, max_length=32, placeholder="Vazio para gerar automatico"),
                            disnake.ui.TextInput(label="Valor", custom_id="value", required=True, max_length=16, placeholder="10.00"),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    code = values.get("code", "").strip().upper() or secrets.token_hex(4).upper()
                    value = values.get("value", "0").replace(",", ".").strip()
                    data = db.get_document("giftcards_list") or {}
                    cards = data.setdefault("cards", [])
                    cards.append({"code": code, "value": value, "created_by": str(modal_inter.user.id)})
                    db.save_document("giftcards_list", data)
                    await modal_inter.response.send_message(f"{emoji.correct} Gift card `{code}` criado com valor `R$ {value}`.", ephemeral=True)

            await inter.response.send_modal(GiftCardModal())
            return

        if custom_id == "GiftCard_Resgatar":
            class RedeemGiftCardModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Resgatar gift card",
                        custom_id="GiftCard_RedeemModal",
                        components=[
                            disnake.ui.TextInput(label="Codigo", custom_id="code", max_length=32),
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    code = values.get("code", "").strip().upper()
                    data = db.get_document("giftcards_list") or {}
                    cards = data.get("cards", [])

                    for card in cards:
                        if str(card.get("code", "")).upper() != code:
                            continue
                        if card.get("redeemed_by"):
                            await modal_inter.response.send_message(f"{emoji.wrong} Esse gift card ja foi resgatado.", ephemeral=True)
                            return

                        card["redeemed_by"] = str(modal_inter.user.id)
                        card["redeemed_at"] = int(disnake.utils.utcnow().timestamp())
                        db.save_document("giftcards_list", data)
                        await modal_inter.response.send_message(
                            f"{emoji.correct} Gift card `{code}` resgatado com valor `R$ {card.get('value', '?')}`.",
                            ephemeral=True,
                        )
                        return

                    await modal_inter.response.send_message(f"{emoji.wrong} Gift card `{code}` nao encontrado.", ephemeral=True)

            await inter.response.send_modal(RedeemGiftCardModal())
            return

        if custom_id == "GiftCard_Listar":
            giftcards = db.get_document("giftcards_list") or {}
            cards = giftcards.get("cards", [])
            if not cards:
                await inter.response.send_message(f"{emoji.wrong} Nenhum gift card encontrado.", ephemeral=True)
                return

            card_list = "\n".join(
                f"- `{card.get('code', 'SEM-CODIGO')}` - R$ {card.get('value', '?')}"
                for card in cards[:10]
            )
            await inter.response.send_message(f"**Gift Cards ({len(cards)}):**\n{card_list}", ephemeral=True)
            return

        if custom_id == "GiftCard_Config":
            await inter.response.send_message("Use **Criar** para cadastrar novos codigos e **Listar** para consultar os existentes.", ephemeral=True)


def setup(bot):
    bot.add_cog(GiftCardPanel(bot))
