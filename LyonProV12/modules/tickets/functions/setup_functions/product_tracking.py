import time

import disnake
from disnake.ui import Modal, TextInput

from functions.database import database as db
from functions.emoji import emoji
from ..history import log_ticket_event
from ..permissions import check_attendant_permissions


CLEAR_WORDS = {"limpar", "remover", "remove", "clear", "nenhum", "none", "0"}


def _get_products() -> dict:
    products = db.get_document("loja_products") or {}
    if not products:
        products = db.obter("database/loja/products.json") or {}
    return products if isinstance(products, dict) else {}


def _product_name(product_id: str, product: dict | None) -> str:
    product = product or {}
    return product.get("name") or product.get("info", {}).get("name") or product_id


def _find_product(product_id: str) -> tuple[str | None, dict | None]:
    products = _get_products()
    if product_id in products:
        return product_id, products[product_id]

    normalized = product_id.lower()
    for stored_id, product in products.items():
        if str(stored_id).lower() == normalized:
            return str(stored_id), product

    return None, None


def _find_ticket_mutable(channel_id: int) -> tuple[dict, str | None, str | None, dict | None]:
    tickets_data = db.get_document("tickets_data") or {}

    def scan_panels(panels: dict):
        for panel_id, users in (panels or {}).items():
            if not isinstance(users, dict):
                continue
            for user_id, tickets in users.items():
                if not isinstance(tickets, list):
                    continue
                for ticket in tickets:
                    if ticket.get("ticket_id") == channel_id:
                        return str(panel_id), str(user_id), ticket
        return None, None, None

    panel_id, user_id, ticket = scan_panels(tickets_data.get("panels", {}))
    if ticket:
        return tickets_data, panel_id, user_id, ticket

    legacy_panels = {
        key: value
        for key, value in tickets_data.items()
        if key not in ("panels", "ai_silenced")
    }
    panel_id, user_id, ticket = scan_panels(legacy_panels)
    return tickets_data, panel_id, user_id, ticket


def _product_summary(ticket: dict) -> str:
    product_id = ticket.get("product_id")
    if not product_id:
        return f"{emoji.information} Nenhum produto vinculado a este ticket."

    product_name = ticket.get("product_name") or product_id
    linked_at = ticket.get("product_linked_at")
    linked_at_text = f"\n{emoji.clock} Vinculado: <t:{linked_at}:f>" if linked_at else ""
    return f"{emoji.cardbox} **Produto:** {product_name}\n{emoji.search} **ID:** `{product_id}`{linked_at_text}"


class ProductTrackingModal(Modal):
    def __init__(self, current_product_id: str | None = None):
        components = [
            TextInput(
                label="ID do produto",
                placeholder="Cole o ID do produto. Use 'limpar' para remover.",
                custom_id="product_id",
                value=current_product_id or "",
                max_length=80,
                required=True,
            )
        ]
        super().__init__(title="Rastrear Produto no Ticket", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(ephemeral=True)

        has_permission = await check_attendant_permissions(inter.author, inter.channel.id)
        if not has_permission:
            return await inter.followup.send(
                f"{emoji.wrong} Voce nao tem permissao para rastrear produtos neste ticket.",
                ephemeral=True,
            )

        raw_product_id = (inter.text_values.get("product_id") or "").strip()
        tickets_data, _panel_id, _user_id, ticket = _find_ticket_mutable(inter.channel.id)
        if not ticket:
            return await inter.followup.send(
                f"{emoji.wrong} Nao encontrei os dados deste ticket.",
                ephemeral=True,
            )

        if raw_product_id.lower() in CLEAR_WORDS:
            old_product_id = ticket.get("product_id")
            old_product_name = ticket.get("product_name")
            for key in ("product_id", "product_name", "product_linked_at", "product_linked_by"):
                ticket.pop(key, None)

            db.save_document("tickets_data", tickets_data)
            log_ticket_event(
                inter.channel.id,
                "product_unlinked",
                inter.author.id,
                {"product_id": old_product_id, "product_name": old_product_name},
            )

            try:
                await inter.channel.send(
                    f"{emoji.cardbox} Produto removido do rastreio por {inter.author.mention}."
                )
            except Exception:
                pass

            return await inter.followup.send(
                f"{emoji.correct} Produto removido do rastreio deste ticket.",
                ephemeral=True,
            )

        product_id, product = _find_product(raw_product_id)
        if not product_id:
            products = _get_products()
            available = ", ".join(f"`{pid}`" for pid in list(products.keys())[:5])
            if not available:
                available = "`nenhum produto cadastrado`"
            return await inter.followup.send(
                f"{emoji.wrong} Produto `{raw_product_id}` nao encontrado.\n"
                f"{emoji.search} IDs disponiveis: {available}",
                ephemeral=True,
            )

        product_name = _product_name(product_id, product)
        now = int(time.time())

        ticket["product_id"] = product_id
        ticket["product_name"] = product_name
        ticket["product_linked_at"] = now
        ticket["product_linked_by"] = inter.author.id

        db.save_document("tickets_data", tickets_data)
        log_ticket_event(
            inter.channel.id,
            "product_linked",
            inter.author.id,
            {"product_id": product_id, "product_name": product_name},
        )

        try:
            await inter.channel.send(
                f"{emoji.cardbox} **Produto vinculado ao ticket**\n"
                f"{emoji.search} **ID:** `{product_id}`\n"
                f"{emoji.textc} **Nome:** `{product_name}`\n"
                f"{emoji.member} **Responsavel:** {inter.author.mention}"
            )
        except Exception:
            pass

        await inter.followup.send(
            f"{emoji.correct} Produto `{product_name}` (`{product_id}`) vinculado ao ticket.",
            ephemeral=True,
        )


async def set_product_id(inter: disnake.MessageInteraction):
    await inter.response.send_modal(ProductTrackingModal())


async def show_product_tracking(inter: disnake.MessageInteraction):
    _tickets_data, _panel_id, _user_id, ticket = _find_ticket_mutable(inter.channel.id)
    if not ticket:
        return await inter.response.send_message(
            f"{emoji.wrong} Este canal nao parece ser um ticket valido.",
            ephemeral=True,
        )

    await inter.response.send_message(_product_summary(ticket), ephemeral=True)
