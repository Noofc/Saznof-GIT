import disnake
import io
import json
from disnake.ext import commands
from datetime import datetime
from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from modules.loja.gifts.gift_manager import GiftManager


class GiftLyon(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def display_gifts_panel(self, inter: disnake.MessageInteraction):
        guild_id = inter.guild.id
        cfg = db.get_document(f"loja_gifts_{guild_id}") or {}
        created = cfg.get("created_gifts", 0)
        last = cfg.get("last_gift_created", "Nunca")

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {emoji.gift if hasattr(emoji, 'gift') else '🎁'} Painel > Gifts"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"Presentes criados: `{created}`\n"
                f"Última criação: `{last}`"
            ),
        )
        buttons = disnake.ui.ActionRow(
            disnake.ui.Button(label="Criar Gift", style=disnake.ButtonStyle.green, emoji=emoji.gift if hasattr(emoji, 'gift') else None, custom_id="Loja_CreateGift"),
            disnake.ui.Button(label="Listar Gifts", style=disnake.ButtonStyle.grey, emoji=emoji.list if hasattr(emoji, 'list') else None, custom_id="Loja_ListGifts"),
            disnake.ui.Button(label="Apagar Gift", style=disnake.ButtonStyle.grey, emoji=emoji.trash if hasattr(emoji, 'trash') else None, custom_id="Loja_DeleteGift"),
        )
        buttons2 = disnake.ui.ActionRow(
            disnake.ui.Button(label="Buscar Gift", style=disnake.ButtonStyle.secondary, emoji=emoji.search if hasattr(emoji, 'search') else None, custom_id="Loja_SearchGift"),
            disnake.ui.Button(label="Editar Gift", style=disnake.ButtonStyle.secondary, emoji=emoji.edit if hasattr(emoji, 'edit') else None, custom_id="Loja_EditGift"),
            disnake.ui.Button(label="Exportar Gifts", style=disnake.ButtonStyle.secondary, emoji=emoji.download if hasattr(emoji, 'download') else None, custom_id="Loja_ExportGifts"),
        )
        buttons3 = disnake.ui.ActionRow(
            disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Painel_Loja")
        )

        if not inter.response.is_done():
            await inter.response.send_message(components=[container, buttons, buttons2, buttons3], ephemeral=True, flags=disnake.MessageFlags(is_components_v2=True))
        else:
            await inter.followup.send(components=[container, buttons, buttons2, buttons3], ephemeral=True, flags=disnake.MessageFlags(is_components_v2=True))

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        guild_id = inter.guild.id if inter.guild else None
        if cid == "Loja_CreateGift":
            await inter.response.defer(ephemeral=True)

            class CreateGiftModal(disnake.ui.Modal):
                def __init__(self):
                    components = [
                        disnake.ui.TextInput(label="ID do produto", custom_id="product_id", style=disnake.TextInputStyle.short, placeholder="Ex.: produto_123", required=True),
                        disnake.ui.TextInput(label="ID do campo", custom_id="campo_id", style=disnake.TextInputStyle.short, placeholder="Ex.: campo_1", required=True),
                        disnake.ui.TextInput(label="Quantidade", custom_id="quantity", style=disnake.TextInputStyle.short, placeholder="1", required=True, max_length=5),
                        disnake.ui.TextInput(label="Usos máximos", custom_id="max_uses", style=disnake.TextInputStyle.short, placeholder="1", required=False, max_length=5),
                        disnake.ui.TextInput(label="Dias até expirar", custom_id="expires_in", style=disnake.TextInputStyle.short, placeholder="30", required=False, max_length=5),
                    ]
                    super().__init__(title="Criar Gift", components=components, custom_id="Loja_CreateGift_Modal")

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    product_id = modal_inter.resolved_values.get("product_id", "").strip()
                    campo_id = modal_inter.resolved_values.get("campo_id", "").strip()
                    quantity = int(modal_inter.resolved_values.get("quantity", "1").strip() or 1)
                    max_uses = int(modal_inter.resolved_values.get("max_uses", "1").strip() or 1)
                    expires_in = int(modal_inter.resolved_values.get("expires_in", "30").strip() or 30)
                    created = GiftManager.create_gift(guild_id, product_id, campo_id, quantity, max_uses, expires_in)
                    cfg_local = db.get_document(f"loja_gifts_{guild_id}") or {}
                    cfg_local["created_gifts"] = cfg_local.get("created_gifts", 0) + 1
                    cfg_local["last_gift_created"] = disnake.utils.utcnow().strftime("%d/%m/%Y %H:%M:%S")
                    db.save_document(f"loja_gifts_{guild_id}", cfg_local)
                    await modal_inter.response.send_message(f"{emoji.correct} Gift criado com sucesso: `{created['code']}`", ephemeral=True)

            await inter.followup.send_modal(CreateGiftModal())
            return

        if cid == "Loja_ListGifts":
            await inter.response.defer(ephemeral=True)
            gifts = GiftManager.list_gifts(guild_id)
            if not gifts:
                await inter.followup.send(f"{emoji.error} Nenhum gift encontrado.", ephemeral=True)
                return
            text = "\n".join(
                f"`{gift['code']}` → {gift['product_id']} | campo={gift['campo_id']} | qtd={gift['quantity']} | usos={gift.get('current_uses', 0)}/{gift['max_uses']} | expira={datetime.fromtimestamp(gift['expiration']).strftime('%d/%m/%Y') if gift.get('expiration') else 'Nunca' }"
                for gift in gifts
            )
            container = disnake.ui.Container(
                disnake.ui.TextDisplay("Gifts ativos:"),
                disnake.ui.TextDisplay(text[:1900] or "Sem gifts ativos."),
            )
            await inter.followup.send(components=[container], ephemeral=True, flags=disnake.MessageFlags(is_components_v2=True))
            return

        if cid == "Loja_DeleteGift":
            await inter.response.defer(ephemeral=True)

            class DeleteGiftModal(disnake.ui.Modal):
                def __init__(self):
                    components = [
                        disnake.ui.TextInput(label="Código do gift", custom_id="code", style=disnake.TextInputStyle.short, placeholder="Ex.: ABCD1234", required=True)
                    ]
                    super().__init__(title="Apagar Gift", components=components, custom_id="Loja_DeleteGift_Modal")

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    code = modal_inter.resolved_values.get("code", "").strip()
                    removed = GiftManager.delete_gift(guild_id, code)
                    if removed:
                        await modal_inter.response.send_message(f"{emoji.correct} Gift `{code}` removido.", ephemeral=True)
                    else:
                        await modal_inter.response.send_message(f"{emoji.error} Gift `{code}` não encontrado ou já removido.", ephemeral=True)

            await inter.followup.send_modal(DeleteGiftModal())
            return

        if cid == "Loja_SearchGift":
            await inter.response.defer(ephemeral=True)

            class SearchGiftModal(disnake.ui.Modal):
                def __init__(self):
                    components = [
                        disnake.ui.TextInput(label="Código ou product_id", custom_id="query", style=disnake.TextInputStyle.short, placeholder="Código ou parte do product_id", required=True),
                    ]
                    super().__init__(title="Buscar Gift", components=components, custom_id="Loja_SearchGift_Modal")

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    query = modal_inter.resolved_values.get("query", "").strip()
                    results = GiftManager.search_gifts(guild_id, query)
                    if not results:
                        await modal_inter.response.defer()
                        await modal_inter.edit_original_message(content=f"{emoji.error} Nenhum gift encontrado para: `{query}`")
                        await modal_inter.followup.send(f"Pesquisa concluída. Nenhum resultado.", ephemeral=True)
                        return

                    text = "\n".join(
                        f"`{g['code']}` → {g['product_id']} | campo={g['campo_id']} | qtd={g['quantity']} | usos={g.get('current_uses',0)}/{g['max_uses']} | expira={(datetime.fromtimestamp(g['expiration']).strftime('%d/%m/%Y') if g.get('expiration') else 'Nunca') }"
                        for g in results
                    )
                    container = disnake.ui.Container(
                        disnake.ui.TextDisplay("Resultados da busca:"),
                        disnake.ui.TextDisplay(text[:1900] or "Sem resultados."),
                    )
                    await modal_inter.response.defer()
                    await modal_inter.edit_original_message(content=None, components=[container], flags=disnake.MessageFlags(is_components_v2=True))
                    await modal_inter.followup.send(f"{emoji.correct} Pesquisa finalizada.", ephemeral=True)

            await inter.followup.send_modal(SearchGiftModal())
            return

        if cid == "Loja_EditGift":
            await inter.response.defer(ephemeral=True)

            class EditGiftModal(disnake.ui.Modal):
                def __init__(self):
                    components = [
                        disnake.ui.TextInput(label="Código do gift", custom_id="code", style=disnake.TextInputStyle.short, placeholder="Ex.: ABCD1234", required=True),
                        disnake.ui.TextInput(label="Novo product_id (opcional)", custom_id="product_id", style=disnake.TextInputStyle.short, required=False),
                        disnake.ui.TextInput(label="Novo campo_id (opcional)", custom_id="campo_id", style=disnake.TextInputStyle.short, required=False),
                        disnake.ui.TextInput(label="Quantidade (opcional)", custom_id="quantity", style=disnake.TextInputStyle.short, required=False),
                        disnake.ui.TextInput(label="Usos máximos (opcional)", custom_id="max_uses", style=disnake.TextInputStyle.short, required=False),
                        disnake.ui.TextInput(label="Dias até expirar (opcional)", custom_id="expires_in", style=disnake.TextInputStyle.short, required=False),
                    ]
                    super().__init__(title="Editar Gift", components=components, custom_id="Loja_EditGift_Modal")

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    code = modal_inter.resolved_values.get("code", "").strip()
                    product_id = modal_inter.resolved_values.get("product_id") or None
                    campo_id = modal_inter.resolved_values.get("campo_id") or None
                    quantity_raw = modal_inter.resolved_values.get("quantity") or None
                    max_uses_raw = modal_inter.resolved_values.get("max_uses") or None
                    expires_in_raw = modal_inter.resolved_values.get("expires_in") or None

                    try:
                        quantity = int(quantity_raw) if quantity_raw else None
                    except Exception:
                        quantity = None
                    try:
                        max_uses = int(max_uses_raw) if max_uses_raw else None
                    except Exception:
                        max_uses = None

                    updated = GiftManager.update_gift(guild_id, code, product_id=product_id, campo_id=campo_id, quantity=quantity, max_uses=max_uses, expires_in=expires_in_raw)
                    await modal_inter.response.defer()
                    if updated:
                        await modal_inter.edit_original_message(content=f"{emoji.correct} Gift `{code}` atualizado com sucesso.")
                        await modal_inter.followup.send(f"Gift `{code}` atualizado.", ephemeral=True)
                    else:
                        await modal_inter.edit_original_message(content=f"{emoji.error} Gift `{code}` não encontrado.")
                        await modal_inter.followup.send(f"Gift `{code}` não existe.", ephemeral=True)

            await inter.followup.send_modal(EditGiftModal())
            return

        if cid == "Loja_ExportGifts":
            await inter.response.defer(ephemeral=True)
            data = GiftManager.export_gifts(guild_id)
            payload = json.dumps(data, indent=2, ensure_ascii=False)
            bio = io.BytesIO(payload.encode('utf-8'))
            bio.seek(0)
            await inter.followup.send(file=disnake.File(bio, filename=f"gifts_{guild_id}.json"), ephemeral=True)
            return

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        # No dropdown listeners are needed at the moment.
        return


def setup(bot: commands.Bot):
    bot.add_cog(GiftLyon(bot))
