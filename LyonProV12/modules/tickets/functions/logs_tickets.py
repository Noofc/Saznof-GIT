import disnake
from functions.database import database as db
from events._common import enviar_log
from functions.emoji import emoji
from functions.guild_channels import clean_channel_id, load_guild_channels


def _find_ticket_by_channel(channel_id: int) -> dict | None:
    tickets_data = db.get_document("tickets_data") or {}

    def scan_panels(panels: dict):
        for _panel_id, users in (panels or {}).items():
            if not isinstance(users, dict):
                continue
            for _user_id, tickets in users.items():
                if not isinstance(tickets, list):
                    continue
                for ticket in tickets:
                    if ticket.get("ticket_id") == channel_id:
                        return ticket
        return None

    ticket = scan_panels(tickets_data.get("panels", {}))
    if ticket:
        return ticket

    legacy_panels = {
        key: value
        for key, value in tickets_data.items()
        if key not in ("panels", "ai_silenced")
    }
    return scan_panels(legacy_panels)


async def log_ticket_creation(bot, ticket_channel, ticket_owner, panel_name, ticket_mode):
    guild = ticket_channel.guild
    canais = load_guild_channels(guild)
    log_channel_id = clean_channel_id(canais.get("canal_de_logs_de_tickets"))

    title = "Logs de Tickets - Abertos"
        
    linhas = [
        f"{emoji.textc} **Painel:** {panel_name}",
        f"{emoji.member} **Criador:** {ticket_owner.mention} (`{ticket_owner.id}`)",
        f"{emoji.textc} **Canal/Tópico:** {ticket_channel.mention} (`{ticket_channel.id}`)",
    ]

    ticket_data = _find_ticket_by_channel(ticket_channel.id)
    if ticket_data and ticket_data.get("product_id"):
        product_name = ticket_data.get("product_name") or "Produto"
        linhas.append(f"{emoji.cardbox} **Produto:** {product_name} (`{ticket_data.get('product_id')}`)")

    await enviar_log(guild, int(log_channel_id) if log_channel_id else None, title, linhas)


async def log_ticket_closure(bot, ticket_channel, closed_by, ticket_owner, ticket_mode, reason=None):
    guild = closed_by.guild
    canais = load_guild_channels(guild)
    log_channel_id = clean_channel_id(canais.get("canal_de_logs_de_tickets"))
        
    title = "Logs de Tickets - Fechados"
    
    linhas = [
        f"{emoji.textc} **Canal/Tópico:** `{ticket_channel.name}` (`{ticket_channel.id}`)",
    ]
    if ticket_owner:
        linhas.append(f"{emoji.member} **Dono do Ticket:** {ticket_owner.mention} (`{ticket_owner.id}`)")

    ticket_data = _find_ticket_by_channel(ticket_channel.id)
    if ticket_data and ticket_data.get("product_id"):
        product_name = ticket_data.get("product_name") or "Produto"
        linhas.append(f"{emoji.cardbox} **Produto:** {product_name} (`{ticket_data.get('product_id')}`)")
    
    linhas.append(f"{emoji.member} **Fechado por:** {closed_by.mention} (`{closed_by.id}`)")

    if reason:
        linhas.append(f"{emoji.ban} **Motivo:** {reason}")

    return await enviar_log(guild, int(log_channel_id) if log_channel_id else None, title, linhas)


async def log_ticket_reminder(bot, ticket_channel, reminded_by, ticket_owner):
    guild = ticket_channel.guild
    canais = load_guild_channels(guild)
    log_channel_id = clean_channel_id(canais.get("canal_de_logs_de_tickets"))

    title = "Logs de Tickets - Lembrete"
    
    linhas = [
        f"{emoji.member} **Lembrado por:** {reminded_by.mention} (`{reminded_by.id}`)",
        f"{emoji.member} **Usuário Lembrado:** {ticket_owner.mention} (`{ticket_owner.id}`)",
        f"{emoji.textc} **Ticket:** {ticket_channel.mention} (`{ticket_channel.id}`)",
    ]

    await enviar_log(guild, int(log_channel_id) if log_channel_id else None, title, linhas)
