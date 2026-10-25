import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from functions.utils import utils


DOC_KEY = "loja_systemcloud_sales"


def _now() -> int:
    return int(disnake.utils.utcnow().timestamp())


def _money(value: float) -> str:
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _parse_price(value: str) -> float:
    raw = str(value or "0").replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    return round(max(0.0, float(raw)), 2)


def _load() -> dict:
    data = db.get_document(DOC_KEY) or {}
    data.setdefault("packages", {})
    data.setdefault("entitlements", {})
    data.setdefault("logs", [])
    return data


def _save(data: dict) -> None:
    db.save_document(DOC_KEY, data)


def _package_counts(data: dict) -> tuple[int, int, int]:
    packages = data.get("packages", {})
    entitlements = data.get("entitlements", {})
    active_packages = sum(1 for package in packages.values() if package.get("active", True))
    credits = 0
    for user_data in entitlements.values():
        credits += int(user_data.get("extension_boosts", 0))
        credits += int(user_data.get("cloud_members", 0))
    return len(packages), active_packages, credits


def _type_label(package_type: str) -> str:
    return {
        "extension_boosts": "Impulsos de Extensoes",
        "cloud_members": "Membros LyonCloud",
    }.get(package_type, "LyonCloud")


def _type_emoji(package_type: str):
    return emoji.boost if package_type == "extension_boosts" else emoji.cloud


def _upsert_store_product(package: dict) -> tuple[str, str]:
    products = db.get_document("loja_products") or {}
    product_id = package.get("product_id") or f"cloud_{utils.gerar_id(8)}"
    field_id = package.get("field_id") or f"plan_{utils.gerar_id(8)}"
    timestamp = _now()

    product = products.get(product_id) or {
        "id": product_id,
        "name": package["name"],
        "info": {
            "description": package.get("description", ""),
            "banner": None,
            "hex_color": None,
            "delivery_type": "automatic",
            "created_at": timestamp,
            "updated_at": timestamp,
            "purchasesIds": [],
            "total_paid": 0,
            "display_preferences": {
                "show_sales": True,
                "show_options": True,
                "show_stock": False,
                "cart_duration_minutes": 30,
                "store_hours": "",
                "transcript_enabled": False,
            },
            "buy_button": {"label": "Comprar", "emoji": emoji.cloud},
            "systemcloud_package_id": package["id"],
        },
        "campos": {},
        "categorias": {},
        "messages": [],
        "cupons": {},
    }

    product["name"] = package["name"]
    info = product.setdefault("info", {})
    info["description"] = package.get("description", "")
    info["delivery_type"] = "automatic"
    info["updated_at"] = timestamp
    info["systemcloud_package_id"] = package["id"]
    info.setdefault("display_preferences", {})
    info["display_preferences"]["show_stock"] = False
    info.setdefault("buy_button", {"label": "Comprar", "emoji": emoji.cloud})

    field = (product.setdefault("campos", {}).get(field_id) or {})
    field.update(
        {
            "id": field_id,
            "name": _type_label(package.get("type")),
            "price": float(package.get("price", 0)),
            "emoji": str(_type_emoji(package.get("type"))),
            "pre_description": package.get("description", ""),
            "description": (
                f"Entrega automatica de `{package.get('quantity', 1)}` "
                f"{_type_label(package.get('type')).lower()}."
            ),
            "category_id": None,
            "updated_at": timestamp,
            "advanced": {
                "systemcloud_sale": {
                    "package_id": package["id"],
                    "type": package.get("type", "extension_boosts"),
                    "quantity": int(package.get("quantity", 1)),
                }
            },
            "stock": {},
            "infinite_stock": {
                "enabled": True,
                "value": (
                    f"Credito LyonCloud aplicado: {package.get('quantity', 1)} "
                    f"{_type_label(package.get('type')).lower()}."
                ),
            },
            "stock_info": {"is_infinite": True, "last": timestamp},
            "cargos": field.get("cargos", {"adicionar": [], "remover": []}),
            "condicoes": field.get(
                "condicoes",
                {"valorMin": None, "valorMax": None, "quantidadeMin": None, "quantidadeMax": None},
            ),
        }
    )
    field.setdefault("created_at", timestamp)
    product["campos"][field_id] = field

    products[product_id] = product
    db.save_document("loja_products", products)
    return product_id, field_id


class CloudPackageModal(disnake.ui.Modal):
    def __init__(self):
        super().__init__(
            title="Criar pacote LyonCloud",
            custom_id="CloudSales_CreatePackageModal",
            components=[
                disnake.ui.TextInput(
                    label="Nome do pacote",
                    custom_id="name",
                    placeholder="Ex.: 10 Impulsos de Extensoes",
                    required=True,
                    max_length=80,
                ),
                disnake.ui.TextInput(
                    label="Tipo",
                    custom_id="type",
                    placeholder="extension_boosts ou cloud_members",
                    required=True,
                    max_length=24,
                ),
                disnake.ui.TextInput(
                    label="Quantidade entregue",
                    custom_id="quantity",
                    placeholder="Ex.: 10",
                    required=True,
                    max_length=8,
                ),
                disnake.ui.TextInput(
                    label="Preco",
                    custom_id="price",
                    placeholder="Ex.: 19,90",
                    required=True,
                    max_length=12,
                ),
                disnake.ui.TextInput(
                    label="Descricao",
                    custom_id="description",
                    placeholder="Texto mostrado no produto",
                    required=False,
                    style=disnake.TextInputStyle.paragraph,
                    max_length=800,
                ),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(with_message=False)

        values = inter.text_values
        package_type = str(values.get("type", "")).strip().lower()
        aliases = {
            "boost": "extension_boosts",
            "boosts": "extension_boosts",
            "impulsos": "extension_boosts",
            "extensoes": "extension_boosts",
            "extensoes_boosts": "extension_boosts",
            "membros": "cloud_members",
            "members": "cloud_members",
            "cloud": "cloud_members",
        }
        package_type = aliases.get(package_type, package_type)
        if package_type not in {"extension_boosts", "cloud_members"}:
            await inter.edit_original_message(content=f"{emoji.wrong} Tipo invalido. Use `extension_boosts` ou `cloud_members`.", components=[])
            return

        try:
            quantity = max(1, int(str(values.get("quantity", "1")).strip()))
            price = _parse_price(values.get("price", "0"))
        except Exception:
            await inter.edit_original_message(content=f"{emoji.wrong} Quantidade ou preco invalido.", components=[])
            return

        data = _load()
        package_id = utils.gerar_id(10)
        package = {
            "id": package_id,
            "name": values.get("name", "Pacote LyonCloud").strip(),
            "type": package_type,
            "quantity": quantity,
            "price": price,
            "description": (values.get("description") or "").strip(),
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
        }
        product_id, field_id = _upsert_store_product(package)
        package["product_id"] = product_id
        package["field_id"] = field_id
        data["packages"][package_id] = package
        data.setdefault("logs", []).append(
            {
                "type": "package_created",
                "package_id": package_id,
                "user_id": inter.author.id,
                "created_at": _now(),
            }
        )
        _save(data)

        panel_data = CloudSales.panel(inter)
        if "embed" in panel_data:
            await inter.edit_original_message(content=None, **panel_data)
        else:
            await inter.edit_original_message(**panel_data, flags=disnake.MessageFlags(is_components_v2=True))


class CloudSales(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def panel(inter: disnake.Interaction) -> dict:
        mode = (db.get_document("custom_mode") or {}).get("mode", "components")
        if mode == "embed":
            return CloudSales._panel_embed()
        return CloudSales._panel_components()

    @staticmethod
    def _summary_text() -> str:
        data = _load()
        total, active, credits = _package_counts(data)
        packages = list(data.get("packages", {}).values())[-5:]
        latest = "\n".join(
            f"- `{pkg.get('name')}` | {_type_label(pkg.get('type'))} | "
            f"`{pkg.get('quantity')}` un. | `{_money(pkg.get('price', 0))}`"
            for pkg in packages
        )
        if not latest:
            latest = "- Nenhum pacote criado ainda."
        return (
            f"{emoji.cardbox} **Pacotes:** `{total}`\n"
            f"{emoji.on} **Ativos:** `{active}`\n"
            f"{emoji.cloud} **Creditos entregues:** `{credits}`\n\n"
            f"**Ultimos pacotes**\n{latest}"
        )

    @staticmethod
    def _panel_components() -> dict:
        colors = db.get_document("custom_colors") or {}
        container_kwargs = {}
        if colors.get("primary"):
            container_kwargs["accent_colour"] = disnake.Colour(int(colors["primary"].replace("#", ""), 16))

        return {
            "components": [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(f"# {emoji.cloud} LyonCloud\n-# Painel > Loja > **Vendas LyonCloud**"),
                    disnake.ui.Separator(),
                    disnake.ui.TextDisplay(
                        "Venda impulsos de extensoes e membros do LyonCloud pela loja. "
                        "Cada pacote vira um produto da loja e, quando a compra aprovar, o credito fica registrado."
                    ),
                    disnake.ui.Separator(),
                    disnake.ui.TextDisplay(CloudSales._summary_text()),
                    disnake.ui.Separator(),
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Criar Pacote", style=disnake.ButtonStyle.green, emoji=emoji.plus, custom_id="CloudSales_CreatePackage"),
                        disnake.ui.Button(label="Sincronizar Produtos", style=disnake.ButtonStyle.blurple, emoji=emoji.reload, custom_id="CloudSales_SyncProducts"),
                        disnake.ui.Button(label="Ver Creditos", style=disnake.ButtonStyle.grey, emoji=emoji.receipt, custom_id="CloudSales_ViewCredits"),
                    ),
                    **container_kwargs,
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Loja")
                ),
            ]
        }

    @staticmethod
    def _panel_embed() -> dict:
        colors = db.get_document("custom_colors") or {}
        embed = disnake.Embed(title="LyonCloud", description=CloudSales._summary_text())
        if colors.get("primary"):
            embed.color = disnake.Colour(int(colors["primary"].replace("#", ""), 16))
        return {
            "embed": embed,
            "components": [
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Criar Pacote", style=disnake.ButtonStyle.green, emoji=emoji.plus, custom_id="CloudSales_CreatePackage"),
                    disnake.ui.Button(label="Sincronizar Produtos", style=disnake.ButtonStyle.blurple, emoji=emoji.reload, custom_id="CloudSales_SyncProducts"),
                    disnake.ui.Button(label="Ver Creditos", style=disnake.ButtonStyle.grey, emoji=emoji.receipt, custom_id="CloudSales_ViewCredits"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Loja")
                ),
            ],
        }

    @staticmethod
    async def process_purchase(bot, guild, user, item: dict, product: dict, field: dict, cart_id: str, purchase_id: str) -> None:
        sale = ((field or {}).get("advanced") or {}).get("systemcloud_sale") or {}
        package_id = sale.get("package_id") or (product.get("info") or {}).get("systemcloud_package_id")
        if not package_id or not user:
            return

        data = _load()
        package = data.get("packages", {}).get(package_id, {})
        sale_type = sale.get("type") or package.get("type", "extension_boosts")
        quantity = int(sale.get("quantity") or package.get("quantity") or 1) * int(item.get("quantity", 1))
        user_key = str(user.id)
        user_data = data.setdefault("entitlements", {}).setdefault(
            user_key,
            {"extension_boosts": 0, "cloud_members": 0, "purchases": []},
        )

        if any(p.get("purchase_id") == purchase_id for p in user_data.get("purchases", [])):
            return

        if sale_type == "cloud_members":
            user_data["cloud_members"] = int(user_data.get("cloud_members", 0)) + quantity
        else:
            user_data["extension_boosts"] = int(user_data.get("extension_boosts", 0)) + quantity

        record = {
            "purchase_id": purchase_id,
            "cart_id": cart_id,
            "guild_id": getattr(guild, "id", None),
            "package_id": package_id,
            "type": sale_type,
            "quantity": quantity,
            "created_at": _now(),
        }
        user_data.setdefault("purchases", []).append(record)
        data.setdefault("logs", []).append({"type": "credit_applied", "user_id": user.id, **record})
        _save(data)

        try:
            await user.send(
                f"{emoji.correct} Seu pacote **{package.get('name', 'LyonCloud')}** foi aprovado.\n"
                f"{_type_emoji(sale_type)} Credito aplicado: `{quantity}` {_type_label(sale_type).lower()}."
            )
        except Exception:
            pass

    @commands.Cog.listener("on_button_click")
    async def on_cloud_sales_button(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        if not cid.startswith("CloudSales_"):
            return

        if cid == "CloudSales_CreatePackage":
            await inter.response.send_modal(CloudPackageModal())
            return

        mode = (db.get_document("custom_mode") or {}).get("mode", "components")
        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter, send=False)

        if cid == "CloudSales_SyncProducts":
            data = _load()
            for package in data.get("packages", {}).values():
                product_id, field_id = _upsert_store_product(package)
                package["product_id"] = product_id
                package["field_id"] = field_id
                package["updated_at"] = _now()
            _save(data)
            panel_data = self.panel(inter)
            if "embed" in panel_data:
                await inter.edit_original_message(content=f"{emoji.correct} Produtos sincronizados.", **panel_data)
            else:
                await inter.edit_original_message(**panel_data, flags=disnake.MessageFlags(is_components_v2=True))
            return

        if cid == "CloudSales_ViewCredits":
            data = _load()
            entitlements = data.get("entitlements", {})
            lines = []
            for user_id, credits in list(entitlements.items())[-15:]:
                lines.append(
                    f"<@{user_id}> | impulsos: `{credits.get('extension_boosts', 0)}` | "
                    f"membros: `{credits.get('cloud_members', 0)}`"
                )
            text = "\n".join(lines) if lines else "Nenhum credito entregue ainda."
            if mode == "embed":
                embed = disnake.Embed(title="Creditos LyonCloud", description=text)
                await inter.edit_original_message(content=None, embed=embed, components=[
                ])
            else:
                await inter.edit_original_message(
                    components=[
                        disnake.ui.Container(
                            disnake.ui.TextDisplay(f"# {emoji.cloud} Creditos LyonCloud"),
                            disnake.ui.Separator(),
                            disnake.ui.TextDisplay(text),
                        ),
                    ],
                    flags=disnake.MessageFlags(is_components_v2=True),
                )

    @commands.Cog.listener("on_button_click")
    async def on_loja_systemcloud_button(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id != "Loja_LyonCloud":
            return
        mode = (db.get_document("custom_mode") or {}).get("mode", "components")
        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter, send=False)
        panel_data = self.panel(inter)
        if "embed" in panel_data:
            await inter.edit_original_message(content=None, **panel_data)
        else:
            await inter.edit_original_message(**panel_data, flags=disnake.MessageFlags(is_components_v2=True))


def setup(bot: commands.Bot):
    bot.add_cog(CloudSales(bot))
