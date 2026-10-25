import random
import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from functions.utils import utils


DOC_KEY = "giveaways_raffles"


def _now() -> int:
    return int(disnake.utils.utcnow().timestamp())


def _load() -> dict:
    data = db.get_document(DOC_KEY) or {}
    data.setdefault("raffles", {})
    return data


def _save(data: dict) -> None:
    db.save_document(DOC_KEY, data)


def _money(value: float) -> str:
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _price(value: str) -> float:
    raw = str(value or "0").replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    return round(max(0.0, float(raw)), 2)


def _active_raffles() -> dict:
    data = _load()
    return {rid: raffle for rid, raffle in data.get("raffles", {}).items() if raffle.get("status") == "open"}


def _raffle_text(raffle: dict) -> str:
    buyers = raffle.get("buyers", {})
    sold = sum(len(numbers) for numbers in buyers.values())
    max_tickets = int(raffle.get("max_tickets", 100))
    return (
        f"{emoji.giveaway} **Premio:** {raffle.get('prize', 'Premio')}\n"
        f"{emoji.coin} **Valor por numero:** `{_money(raffle.get('ticket_price', 0))}`\n"
        f"{emoji.receipt} **Numeros vendidos:** `{sold}/{max_tickets}`\n"
        f"{emoji.clock} **Status:** `{raffle.get('status', 'open')}`"
    )


async def _publish_raffle(bot, channel: disnake.TextChannel, raffle_id: str):
    data = _load()
    raffle = data.get("raffles", {}).get(raffle_id)
    if not raffle:
        return None
    is_open = raffle.get("status") == "open"

    components = [
        disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {emoji.giveaway} {raffle.get('name', 'Rifa')}"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(_raffle_text(raffle)),
            disnake.ui.Separator(),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Comprar Numero", style=disnake.ButtonStyle.green, emoji=emoji.cart, custom_id=f"Raffle_Buy:{raffle_id}", disabled=not is_open),
                disnake.ui.Button(label="Meus Numeros", style=disnake.ButtonStyle.grey, emoji=emoji.receipt, custom_id=f"Raffle_MyNumbers:{raffle_id}"),
                disnake.ui.Button(label="Finalizar", style=disnake.ButtonStyle.red, emoji=emoji.trophy, custom_id=f"Raffle_Draw:{raffle_id}", disabled=not is_open),
            ),
        )
    ]

    if raffle.get("message_id"):
        try:
            msg = await channel.fetch_message(int(raffle["message_id"]))
            await msg.edit(components=components, flags=disnake.MessageFlags(is_components_v2=True))
            return msg
        except Exception:
            pass

    msg = await channel.send(components=components, flags=disnake.MessageFlags(is_components_v2=True))
    raffle["channel_id"] = channel.id
    raffle["message_id"] = msg.id
    data["raffles"][raffle_id] = raffle
    _save(data)
    return msg


class RaffleCreateModal(disnake.ui.Modal):
    def __init__(self):
        super().__init__(
            title="Criar Rifa",
            custom_id="Raffle_CreateModal",
            components=[
                disnake.ui.TextInput(label="Nome da rifa", custom_id="name", placeholder="Ex.: Rifa Nitro Mensal", max_length=80),
                disnake.ui.TextInput(label="Premio", custom_id="prize", placeholder="Ex.: Nitro mensal", max_length=120),
                disnake.ui.TextInput(label="Valor por numero", custom_id="ticket_price", placeholder="Ex.: 2,50", required=True, max_length=12),
                disnake.ui.TextInput(label="Quantidade de numeros", custom_id="max_tickets", placeholder="Ex.: 100", required=True, max_length=6),
                disnake.ui.TextInput(label="Canal ID para publicar", custom_id="channel_id", placeholder="Vazio = canal atual", required=False, max_length=24),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(ephemeral=True)
        try:
            max_tickets = max(1, min(10000, int(inter.text_values.get("max_tickets", "100"))))
            ticket_price = _price(inter.text_values.get("ticket_price", "0"))
        except Exception:
            await inter.followup.send(f"{emoji.wrong} Valor ou quantidade invalida.", ephemeral=True)
            return

        channel = inter.channel
        channel_raw = (inter.text_values.get("channel_id") or "").strip()
        if channel_raw:
            channel = inter.guild.get_channel(int(channel_raw)) if channel_raw.isdigit() else None
        if not isinstance(channel, disnake.TextChannel):
            await inter.followup.send(f"{emoji.wrong} Canal invalido para publicar a rifa.", ephemeral=True)
            return

        raffle_id = utils.gerar_id(10)
        data = _load()
        data["raffles"][raffle_id] = {
            "id": raffle_id,
            "name": inter.text_values.get("name", "Rifa").strip(),
            "prize": inter.text_values.get("prize", "Premio").strip(),
            "ticket_price": ticket_price,
            "max_tickets": max_tickets,
            "status": "open",
            "created_by": inter.author.id,
            "created_at": _now(),
            "buyers": {},
            "logs": [],
        }
        _save(data)
        await _publish_raffle(inter.bot, channel, raffle_id)
        await inter.followup.send(f"{emoji.correct} Rifa criada e publicada em {channel.mention}.", ephemeral=True)


class RafflesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def Panel() -> list[disnake.ui.Container]:
        data = _load()
        raffles = data.get("raffles", {})
        active = _active_raffles()
        recent = list(raffles.values())[-6:]
        lines = [
            f"{emoji.giveaway} **Rifas criadas:** `{len(raffles)}`",
            f"{emoji.on} **Rifas abertas:** `{len(active)}`",
        ]
        for raffle in recent:
            lines.append(f"- `{raffle.get('name')}` | `{raffle.get('status')}` | `{_money(raffle.get('ticket_price', 0))}`")
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.giveaway} Rifas\n-# Painel > Sorteios > **Rifas**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("\n".join(lines)),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Criar Rifa", style=disnake.ButtonStyle.green, emoji=emoji.plus, custom_id="Raffle_Create"),
                    disnake.ui.Button(label="Atualizar", style=disnake.ButtonStyle.grey, emoji=emoji.reload, custom_id="Giveaways_Raffles"),
                ),
            ),
        ]

    @staticmethod
    def PanelEmbed() -> tuple[disnake.Embed, list[disnake.ui.ActionRow]]:
        active = _active_raffles()
        embed = disnake.Embed(
            title="Rifas",
            description=f"{emoji.on} Rifas abertas: `{len(active)}`\nUse o botao abaixo para criar uma rifa.",
        )
        return embed, [
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Criar Rifa", style=disnake.ButtonStyle.green, emoji=emoji.plus, custom_id="Raffle_Create"),
                disnake.ui.Button(label="Atualizar", style=disnake.ButtonStyle.grey, emoji=emoji.reload, custom_id="Giveaways_Raffles"),
            ),
        ]

    @commands.Cog.listener("on_button_click")
    async def on_raffle_button(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        if cid == "Giveaways_Raffles":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.PanelEmbed()
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.Panel(), flags=disnake.MessageFlags(is_components_v2=True))
            return

        if cid == "Raffle_Create":
            await inter.response.send_modal(RaffleCreateModal())
            return

        if not cid.startswith("Raffle_"):
            return

        parts = cid.split(":", 1)
        action = parts[0]
        raffle_id = parts[1] if len(parts) > 1 else ""
        data = _load()
        raffle = data.get("raffles", {}).get(raffle_id)
        if not raffle:
            await inter.response.send_message(f"{emoji.wrong} Rifa nao encontrada.", ephemeral=True)
            return

        if action == "Raffle_MyNumbers":
            numbers = raffle.get("buyers", {}).get(str(inter.author.id), [])
            text = ", ".join(str(n) for n in numbers) if numbers else "Voce ainda nao comprou numeros nesta rifa."
            await inter.response.send_message(f"{emoji.receipt} Seus numeros: {text}", ephemeral=True)
            return

        if action == "Raffle_Buy":
            await inter.response.defer(ephemeral=True)
            if raffle.get("status") != "open":
                await inter.followup.send(f"{emoji.wrong} Esta rifa ja foi encerrada.", ephemeral=True)
                return

            buyers = raffle.setdefault("buyers", {})
            sold_numbers = {n for nums in buyers.values() for n in nums}
            max_tickets = int(raffle.get("max_tickets", 100))
            if len(sold_numbers) >= max_tickets:
                await inter.followup.send(f"{emoji.wrong} Todos os numeros desta rifa ja foram vendidos.", ephemeral=True)
                return

            price = float(raffle.get("ticket_price", 0))
            if price > 0:
                try:
                    from modules.loja.saldo.balance_manager import BalanceManager
                    ok, msg = BalanceManager.use_balance(
                        inter.author.id,
                        price,
                        reference_id=f"raffle_{raffle_id}",
                        description=f"Compra de numero da rifa {raffle.get('name')}",
                    )
                    if not ok:
                        await inter.followup.send(f"{emoji.wrong} {msg}", ephemeral=True)
                        return
                except Exception as exc:
                    await inter.followup.send(f"{emoji.wrong} Nao consegui cobrar o saldo da rifa: {exc}", ephemeral=True)
                    return

            available = [n for n in range(1, max_tickets + 1) if n not in sold_numbers]
            number = random.choice(available)
            buyers.setdefault(str(inter.author.id), []).append(number)
            raffle.setdefault("logs", []).append({"type": "buy", "user_id": inter.author.id, "number": number, "at": _now()})
            data["raffles"][raffle_id] = raffle
            _save(data)

            channel = inter.guild.get_channel(int(raffle.get("channel_id", 0))) if inter.guild else None
            if isinstance(channel, disnake.TextChannel):
                await _publish_raffle(inter.bot, channel, raffle_id)
            await inter.followup.send(f"{emoji.correct} Numero comprado: `{number}`.", ephemeral=True)
            return

        if action == "Raffle_Draw":
            if not getattr(inter.author.guild_permissions, "manage_guild", False):
                await inter.response.send_message(f"{emoji.wrong} Apenas a staff pode finalizar a rifa.", ephemeral=True)
                return
            await inter.response.defer()
            buyers = raffle.get("buyers", {})
            entries = [(int(user_id), number) for user_id, nums in buyers.items() for number in nums]
            if not entries:
                await inter.followup.send(f"{emoji.wrong} Esta rifa ainda nao tem participantes.", ephemeral=True)
                return
            winner_id, number = random.choice(entries)
            raffle["status"] = "closed"
            raffle["winner"] = {"user_id": winner_id, "number": number, "drawn_at": _now(), "drawn_by": inter.author.id}
            data["raffles"][raffle_id] = raffle
            _save(data)
            await inter.channel.send(
                f"{emoji.trophy} **Rifa encerrada:** `{raffle.get('name')}`\n"
                f"Ganhador: <@{winner_id}> com o numero `{number}`.\n"
                f"Premio: **{raffle.get('prize')}**"
            )
            await _publish_raffle(inter.bot, inter.channel, raffle_id)
