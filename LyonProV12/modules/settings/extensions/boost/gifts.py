import disnake
import uuid
import hashlib
import io
from datetime import datetime
from functions.emoji import emoji
from functions.database import database as db
from functions.message import message, embed_message
from .websocket_manager import get_websocket_manager


async def show_gifts_panel(inter: disnake.MessageInteraction, bot):
    """Mostra painel de gerenciamento de gifts"""
    mode = db.get_document("custom_mode").get("mode")
    
    # Verificar conexão WebSocket
    ws_manager = get_websocket_manager()
    if not ws_manager.is_connected():
        if mode == "embed":
            await embed_message.error(inter, "WebSocket não está conectado. Aguarde a conexão ser estabelecida.", send=True)
        else:
            await message.error(inter, "WebSocket não está conectado. Aguarde a conexão ser estabelecida.", send=True)
        return
    
    # Obter gifts
    response = await ws_manager.get_gifts()
    
    if not response.get("success"):
        if mode == "embed":
            await embed_message.error(inter, f"Erro ao carregar gifts: {response.get('message', 'Erro desconhecido')}", send=True)
        else:
            await message.error(inter, f"Erro ao carregar gifts: {response.get('message', 'Erro desconhecido')}", send=True)
        return
    
    gifts = response.get("data", {}).get("gifts", [])
    total_gifts = len(gifts)
    active_gifts = len([g for g in gifts if g.get("status") == "active"])
    redeemed_gifts = len([g for g in gifts if g.get("redeemed")])
    
    if mode == "embed":
        await _show_gifts_panel_embed(inter, gifts, total_gifts, active_gifts, redeemed_gifts)
    else:
        await _show_gifts_panel_components(inter, gifts, total_gifts, active_gifts, redeemed_gifts)


async def _show_gifts_panel_embed(inter, gifts, total_gifts, active_gifts, redeemed_gifts):
    """Mostra painel de gifts em modo embed"""
    colors = db.get_document("custom_colors")
    primary_color_hex = colors.get("primary")
    
    embed = disnake.Embed(
        title=f"{emoji.gift} Gerenciar Gifts de Boost",
        description=(
            f"**Total de Gifts:** `{total_gifts}`\n"
            f"**Gifts Ativos:** `{active_gifts}`\n"
            f"**Gifts Resgatados:** `{redeemed_gifts}`\n\n"
            f"Use os botões abaixo para gerenciar seus gifts."
        ),
    )
    
    if primary_color_hex:
        primary_color = int(primary_color_hex.replace("#", ""), 16)
        embed.color = primary_color
    
    # Mostrar últimos 5 gifts
    if gifts:
        gift_list = []
        for gift in gifts[:5]:
            status_emoji = "✅" if gift.get("status") == "active" else "❌"
            gift_list.append(
                f"{status_emoji} **{gift.get('id', 'N/A')[:8]}...** - "
                f"`{gift.get('boost_count', 0)}` boosts"
            )
        embed.add_field(
            name=f"{emoji.receipt} Últimos Gifts",
            value="\n".join(gift_list) if gift_list else "Nenhum gift criado ainda",
            inline=False
        )
    
    components = [
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="Criar Gift",
                style=disnake.ButtonStyle.green,
                emoji=emoji.plus,
                custom_id="Boost_CreateGift"
            ),
            disnake.ui.Button(
                label="Ver Gifts",
                style=disnake.ButtonStyle.grey,
                emoji=emoji.receipt,
                custom_id="Boost_ViewGifts"
            ),
            disnake.ui.Button(
                label="Limpar Todos",
                style=disnake.ButtonStyle.red,
                emoji=emoji.wrong,
                custom_id="Boost_ClearAllGifts"
            ),
        ),
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="",
                style=disnake.ButtonStyle.grey,
                emoji=emoji.back,
                custom_id="Boost_BackToPanel"
            )
        )
    ]
    
    # Editar a mensagem original com embed e componentes
    try:
        await inter.response.edit_message(embed=embed, components=components)
    except Exception as e:
        print(f"Erro ao editar mensagem no modo embed: {e}")
        # Fallback: tentar sem componentes
        await inter.response.edit_message(embed=embed, components=[])


async def _show_gifts_panel_components(inter, gifts, total_gifts, active_gifts, redeemed_gifts):
    """Mostra painel de gifts em modo components"""
    colors = db.get_document("custom_colors")
    primary_color_hex = colors.get("primary")
    
    container_kwargs = {}
    if primary_color_hex:
        primary_color = int(primary_color_hex.replace("#", ""), 16)
        container_kwargs["accent_colour"] = disnake.Colour(primary_color)
    
    # Construir lista de gifts
    gift_list_text = ""
    if gifts:
        for gift in gifts[:5]:
            status_emoji = "✅" if gift.get("status") == "active" else "❌"
            gift_list_text += (
                f"{status_emoji} **{gift.get('id', 'N/A')[:8]}...** - "
                f"`{gift.get('boost_count', 0)}` boosts\n"
            )
    else:
        gift_list_text = "Nenhum gift criado ainda"
    
    container = disnake.ui.Container(
        disnake.ui.TextDisplay(
            f"# {emoji.gift}\n"
            f"-# Gerenciar Gifts de Boost\n\n"
        ),
        disnake.ui.Separator(),
        disnake.ui.TextDisplay(
            f"**Total de Gifts:** `{total_gifts}`\n"
            f"**Gifts Ativos:** `{active_gifts}`\n"
            f"**Gifts Resgatados:** `{redeemed_gifts}`\n\n"
        ),
        disnake.ui.Separator(),
        disnake.ui.TextDisplay(
            f"**{emoji.receipt} Últimos Gifts:**\n"
            f"{gift_list_text}"
        ),
        **container_kwargs
    )
    
    buttons = [
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="Criar Gift",
                style=disnake.ButtonStyle.green,
                emoji=emoji.plus,
                custom_id="Boost_CreateGift"
            ),
            disnake.ui.Button(
                label="Ver Gifts",
                style=disnake.ButtonStyle.grey,
                emoji=emoji.receipt,
                custom_id="Boost_ViewGifts"
            ),
            disnake.ui.Button(
                label="Limpar Todos",
                style=disnake.ButtonStyle.red,
                emoji=emoji.wrong,
                custom_id="Boost_ClearAllGifts"
            ),
        ),
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="",
                style=disnake.ButtonStyle.grey,
                emoji=emoji.back,
                custom_id="Boost_BackToPanel"
            )
        )
    ]
    
    # Editar a mensagem original com container e botões
    try:
        await inter.response.edit_message(components=[container] + buttons)
    except Exception as e:
        print(f"Erro ao editar mensagem no modo components: {e}")
        # Fallback: tentar sem container, apenas texto
        success_message = f"{emoji.gift} **Gerenciar Gifts de Boost**\n\n"
        success_message += f"**Total de Gifts:** `{total_gifts}`\n"
        success_message += f"**Gifts Ativos:** `{active_gifts}`\n"
        success_message += f"**Gifts Resgatados:** `{redeemed_gifts}`\n\n"
        
        await inter.response.edit_message(content=success_message, components=buttons)


class CreateBoostGiftModal(disnake.ui.Modal):
    def __init__(self, bot=None):
        self.bot = bot
        components = [
            disnake.ui.TextInput(
                label="Quantidade de Boosts (deve ser par)",
                placeholder="Ex: 2, 4, 6, 8, 10, 12, 14... (cada conta = 2 boosts)",
                custom_id="boost_count",
                style=disnake.TextInputStyle.short,
                required=True,
                max_length=10
            ),
            disnake.ui.TextInput(
                label="Quantidade de Gifts (Opcional)",
                placeholder="Digite a quantidade de gifts a serem criados (padrão: 1)",
                custom_id="quantity",
                style=disnake.TextInputStyle.short,
                required=False,
                max_length=3
            ),
        ]

        super().__init__(
            title="Criar Gift de Boost",
            components=components
        )

    async def callback(self, inter: disnake.ModalInteraction):
        try:
            mode = db.get_document("custom_mode").get("mode")
            
            valores = inter.resolved_values
            boost_count_str = valores.get("boost_count", "").strip()
            quantity_str = valores.get("quantity", "1").strip()
            
            # Validar entradas
            try:
                boost_count = int(boost_count_str)
                if boost_count <= 0:
                    if mode == "embed":
                        await embed_message.error(inter, "A quantidade de boosts deve ser maior que zero!", send=True)
                    else:
                        await message.error(inter, "A quantidade de boosts deve ser maior que zero!", send=True)
                    return
                # Garantir que a quantidade de boosts é par (cada conta dá 2 boosts)
                if boost_count % 2 != 0:
                    if mode == "embed":
                        await embed_message.error(inter, "A quantidade de boosts deve ser par! Cada conta fornece 2 boosts.", send=True)
                    else:
                        await message.error(inter, "A quantidade de boosts deve ser par! Cada conta fornece 2 boosts.", send=True)
                    return
            except ValueError:
                if mode == "embed":
                    await embed_message.error(inter, "Por favor, digite um número válido para a quantidade de boosts!", send=True)
                else:
                    await message.error(inter, "Por favor, digite um número válido para a quantidade de boosts!", send=True)
                return

            try:
                quantity = int(quantity_str) if quantity_str else 1
                if quantity <= 0:
                    if mode == "embed":
                        await embed_message.error(inter, "A quantidade de gifts deve ser maior que zero!", send=True)
                    else:
                        await message.error(inter, "A quantidade de gifts deve ser maior que zero!", send=True)
                    return
            except ValueError:
                if mode == "embed":
                    await embed_message.error(inter, "Por favor, digite um número válido para a quantidade de gifts!", send=True)
                else:
                    await message.error(inter, "Por favor, digite um número válido para a quantidade de gifts!", send=True)
                return
            
            if mode == "embed":
                await embed_message.wait(inter, send=True)
            else:
                await message.wait(inter, send=True)
            
            # Verificar conexão com o WebSocket
            ws_manager = get_websocket_manager()
            if not ws_manager.is_connected():
                if mode == "embed":
                    await embed_message.error(inter, "WebSocket não está conectado. Verifique a conexão.", send=False)
                else:
                    await message.error(inter, "WebSocket não está conectado. Verifique a conexão.", send=False)
                return

            gift_urls = []
            gift_ids = []
            for i in range(quantity):
                gift_url, gift_id = await self._create_gift(inter, boost_count)
                if not gift_url:
                    if mode == "embed":
                        await embed_message.error(inter, f"Falha ao criar o gift #{i+1}. Operação cancelada.", send=False)
                    else:
                        await message.error(inter, f"Falha ao criar o gift #{i+1}. Operação cancelada.", send=False)
                    return
                gift_urls.append(gift_url)
                gift_ids.append(gift_id)

            if not gift_urls:
                if mode == "embed":
                    await embed_message.error(inter, "Nenhum gift foi criado devido a um erro.", send=False)
                else:
                    await message.error(inter, "Nenhum gift foi criado devido a um erro.", send=False)
                return

            # Enviar resposta de sucesso
            if quantity == 1:
                # No modo embed/components, usamos apenas texto sem componentes para evitar conflitos
                success_message = f"{emoji.correct} **Gift criado com sucesso!**\n\n"
                success_message += f"**ID do Gift:** `{gift_ids[0]}`\n"
                success_message += f"**Boosts:** `{boost_count}`\n"
                success_message += f"**Link:** {gift_urls[0]}\n\n"
                success_message += "Compartilhe este link para que outros possam resgatar o gift!"
                
                # Remover todos os componentes anteriores e usar apenas texto
                await inter.edit_original_response(content=success_message, components=[])
            else:
                gift_lines = [f"{i+1}: {url}" for i, url in enumerate(gift_urls)]
                file_content = "\n".join(gift_lines)
                file_bytes = io.BytesIO(file_content.encode('utf-8'))
                file = disnake.File(file_bytes, filename="boost_gifts.txt")

                # No modo embed/components, usamos apenas texto sem componentes para evitar conflitos
                success_message = f"{emoji.correct} **{quantity} gifts criados com sucesso!**\n\n"
                success_message += f"**Boosts por Gift:** `{boost_count}`\n"
                success_message += f"**Total de Boosts:** `{boost_count * quantity}`\n\n"
                success_message += "Os links dos gifts estão no arquivo anexado."
                
                # Remover todos os componentes anteriores e usar apenas texto com arquivo
                await inter.edit_original_response(content=success_message, components=[], file=file)

        except Exception as e:
            print(f"Erro ao processar criação de gift: {e}")
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.error(inter, f"Erro ao processar criação de gift: {str(e)}", send=False)
            else:
                await message.error(inter, f"Erro ao processar criação de gift: {str(e)}", send=False)

    async def _create_gift(self, inter: disnake.ModalInteraction, boost_count: int) -> tuple:
        """Cria o gift e retorna o link e o id"""
        try:
            # Gerar ID único para o gift
            gift_id = self._generate_gift_id()
            
            # Criar dados do gift
            gift_data = {
                "id": gift_id,
                "boost_count": boost_count,
                "created_by": {
                    "id": str(inter.user.id),
                    "name": inter.user.display_name
                }
            }
            
            # Salvar gift via WebSocket
            ws_manager = get_websocket_manager()
            response = await ws_manager.create_gift(gift_data)
            
            if not response.get("success"):
                print(f"Erro ao criar gift via WebSocket: {response.get('message', 'Erro desconhecido')}")
                return None, None
            
            # Gerar link do gift (você pode personalizar a URL)
            gift_url = f"https://boost.Lyonapplications.com.br/gifts/{gift_id}"
            return gift_url, gift_id
            
        except Exception as e:
            print(f"Erro na função _create_gift: {e}")
            return None, None

    def _generate_gift_id(self) -> str:
        """Gera um ID único para o gift"""
        try:
            # Gerar hash único
            unique_string = f"{uuid.uuid4()}_{datetime.utcnow().timestamp()}"
            gift_id = hashlib.md5(unique_string.encode()).hexdigest()[:12]
            
            return gift_id
        except Exception as e:
            print(f"Erro ao gerar ID do gift: {e}")
            return str(uuid.uuid4())[:12]


async def view_gifts(inter: disnake.MessageInteraction, bot):
    """Mostra lista detalhada de gifts"""
    mode = db.get_document("custom_mode").get("mode")
    
    if mode == "embed":
        await embed_message.wait(inter, send=False)
    else:
        await message.wait(inter, send=False)
    
    # Obter gifts
    ws_manager = get_websocket_manager()
    response = await ws_manager.get_gifts()
    
    if not response.get("success"):
        if mode == "embed":
            await embed_message.error(inter, f"Erro ao carregar gifts: {response.get('message', 'Erro desconhecido')}", send=False)
        else:
            await message.error(inter, f"Erro ao carregar gifts: {response.get('message', 'Erro desconhecido')}", send=False)
        return
    
    gifts = response.get("data", {}).get("gifts", [])
    
    if not gifts:
        if mode == "embed":
            await embed_message.error(inter, "Nenhum gift encontrado!", send=False)
        else:
            await message.error(inter, "Nenhum gift encontrado!", send=False)
        return
    
    # Mostrar primeiros 10 gifts
    gift_list = []
    for i, gift in enumerate(gifts[:10], 1):
        status_emoji = "✅" if gift.get("status") == "active" else "❌"
        redeemed_text = " (Resgatado)" if gift.get("redeemed") else ""
        gift_list.append(
            f"`{i}.` {status_emoji} **{gift.get('id', 'N/A')[:8]}...** - "
            f"`{gift.get('boost_count', 0)}` boosts{redeemed_text}"
        )
    
    total = len(gifts)
    remaining = total - 10 if total > 10 else 0
    
    description = "\n".join(gift_list)
    if remaining > 0:
        description += f"\n\n*E mais {remaining} gifts...*"
    
    if mode == "embed":
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        embed = disnake.Embed(
            title=f"{emoji.receipt} Lista de Gifts",
            description=f"**Total:** {total} gifts\n\n{description}",
        )
        
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Boost_ManageGifts"
                )
            )
        ]
        
        await inter.edit_original_message(content=None, embed=embed, components=components)
    else:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)
        
        container = disnake.ui.Container(
            disnake.ui.TextDisplay(
                f"# {emoji.receipt}\n"
                f"-# Lista de Gifts\n\n"
                f"**Total:** {total} gifts\n\n"
                f"{description}"
            ),
            **container_kwargs
        )
        
        buttons = disnake.ui.ActionRow(
            disnake.ui.Button(
                label="",
                style=disnake.ButtonStyle.grey,
                emoji=emoji.back,
                custom_id="Boost_ManageGifts"
            )
        )
        
        await inter.edit_original_message(content=None, components=[container, buttons])


async def clear_all_gifts(inter: disnake.MessageInteraction, bot):
    """Limpa todos os gifts"""
    mode = db.get_document("custom_mode").get("mode")
    
    if mode == "embed":
        await embed_message.wait(inter, send=False)
    else:
        await message.wait(inter, send=False)
    
    # Deletar todos os gifts
    ws_manager = get_websocket_manager()
    response = await ws_manager.delete_all_gifts()
    
    if not response.get("success"):
        if mode == "embed":
            await embed_message.error(inter, f"Erro ao limpar gifts: {response.get('message', 'Erro desconhecido')}", send=False)
        else:
            await message.error(inter, f"Erro ao limpar gifts: {response.get('message', 'Erro desconhecido')}", send=False)
        return
    
    deleted_count = response.get("data", {}).get("deleted_count", 0)
    
    if mode == "embed":
        await embed_message.success(inter, f"**{deleted_count}** gifts foram deletados com sucesso!", send=False)
    else:
        await message.success(inter, f"**{deleted_count}** gifts foram deletados com sucesso!", send=False)
    
    # Voltar ao painel de gifts
    await show_gifts_panel(inter, bot)
