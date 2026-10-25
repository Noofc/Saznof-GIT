"""
Sistema de entrega automática de produtos
"""
import disnake
import io
from datetime import datetime
from typing import List, Optional
from functions.emoji import emoji
from functions.database import database as db
from functions.utils import utils
from .stock_manager import StockManager


def _create_stock_file(items: List[str]) -> disnake.File:
    """Cria arquivo .txt com os itens do estoque (apenas conteúdo)"""
    content = "\n".join(items)

    file_buffer = io.BytesIO(content.encode('utf-8'))
    file_buffer.seek(0)
    return disnake.File(file_buffer, filename="seus_itens.txt")


async def deliver_product_to_user(
    user: disnake.User,
    product_name: str,
    campo_name: str,
    quantity: int,
    items: List[str],
    thread: Optional[disnake.Thread] = None,
    guild: Optional[disnake.Guild] = None,
    instructions: Optional[str] = None,
    product_id: Optional[str] = None,
    campo_id: Optional[str] = None
) -> bool:
    """
    Entrega o produto ao usuário via DM
    Retorna True se a entrega foi bem-sucedida
    """
    try:
        mode = (db.get_document("custom_mode") or {}).get("mode", "components")
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        color = None
        if primary_color_hex:
            try:
                color = int(primary_color_hex.replace("#", ""), 16)
            except:
                pass

        # Calcular conteúdo puro (sem numeração) - cada item em uma linha com `
        items_content = "\n".join([f"`{item}`" for item in items])
        content_length = len(items_content)
        
        # Verificar se precisa criar arquivo
        stock_file = None
        use_file = content_length > 2000
        
        # Verificar se deve mostrar botão de copiar (só se conteúdo <= 2000 caracteres)
        show_copy_button = content_length <= 2000

        if use_file:
            stock_file = _create_stock_file(items)
            display_text = f"*Arquivo anexado com {len(items)} item(s)*"
        else:
            display_text = items_content

        if mode == "embed":
            # Modo Embed - mostrar apenas o conteúdo
            embed = disnake.Embed(
                title=f"{emoji.cardbox} Produto Entregue",
                color=color or disnake.Color.green()
            )

            if not use_file:
                embed.add_field(
                    name=f"Seus Itens",
                    value=display_text[:1024],
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"Seus Itens",
                    value=display_text,
                    inline=False
                )

            embed.set_footer(text=f"Obrigado pela compra! {emoji.gift}")
            
            # Adicionar instruções se existirem
            instructions_truncated = None
            if instructions:
                # Truncar instruções para exibição (limite do Discord para embed field value é 1024)
                if len(instructions) > 1024:
                    instructions_truncated = instructions[:1021] + "..."
                else:
                    instructions_truncated = instructions
                embed.add_field(
                    name=f"{emoji.info if hasattr(emoji, 'info') else '📋'} Instruções",
                    value=instructions_truncated,
                    inline=False
                )
            
            # Adicionar botões de copiar
            components = []
            button_row = []
            
            # Botão de copiar conteúdo do produto
            if show_copy_button:
                button_row.append(
                    disnake.ui.Button(
                        label="Copiar Conteúdo",
                        emoji=emoji.cardbox,
                        style=disnake.ButtonStyle.grey,
                        custom_id=f"copy_delivered_content:{user.id}"
                    )
                )
            
            # Botão de copiar instruções (se houver instruções e product_id/campo_id disponíveis)
            if instructions and product_id and campo_id:
                button_row.append(
                    disnake.ui.Button(
                        label="Copiar Instruções",
                        emoji=emoji.info if hasattr(emoji, 'info') else "📋",
                        style=disnake.ButtonStyle.grey,
                        custom_id=f"copy_instructions:{user.id}:{product_id}:{campo_id}"
                    )
                )
            
            if button_row:
                components = [
                    disnake.ui.ActionRow(*button_row)
                ]

            if stock_file:
                await user.send(embed=embed, file=stock_file, components=components if components else None)
            else:
                await user.send(embed=embed, components=components if components else None)

        else:
            # Modo Container - mostrar apenas o conteúdo
            container_kwargs = {}
            if color:
                container_kwargs["accent_colour"] = disnake.Colour(color)

            container_items = [
                disnake.ui.TextDisplay(f"# {emoji.cardbox}\n-# Produto Entregue"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(f"### Seus Itens\n{display_text[:1900]}") if not use_file else disnake.ui.TextDisplay(f"### Seus Itens\n{display_text}")
            ]
            
            # Adicionar instruções se existirem
            instructions_truncated = None
            if instructions:
                container_items.append(disnake.ui.Separator())
                # Truncar instruções para exibição (limite seguro para TextDisplay é ~1900 caracteres)
                if len(instructions) > 1900:
                    instructions_truncated = instructions[:1897] + "..."
                else:
                    instructions_truncated = instructions
                container_items.append(
                    disnake.ui.TextDisplay(f"### {emoji.info if hasattr(emoji, 'info') else '📋'} Instruções\n{instructions_truncated}")
                )
            
            # Adicionar botões de copiar
            button_row = []
            
            # Botão de copiar conteúdo do produto
            if show_copy_button:
                button_row.append(
                    disnake.ui.Button(
                        label="Copiar Conteúdo",
                        emoji=emoji.cardbox,
                        style=disnake.ButtonStyle.grey,
                        custom_id=f"copy_delivered_content:{user.id}"
                    )
                )
            
            # Botão de copiar instruções (se houver instruções e product_id/campo_id disponíveis)
            if instructions and product_id and campo_id:
                button_row.append(
                    disnake.ui.Button(
                        label="Copiar Instruções",
                        emoji=emoji.info if hasattr(emoji, 'info') else "📋",
                        style=disnake.ButtonStyle.grey,
                        custom_id=f"copy_instructions:{user.id}:{product_id}:{campo_id}"
                    )
                )
            
            if button_row:
                container_items.append(
                    disnake.ui.ActionRow(*button_row)
                )

            components = [
                disnake.ui.Container(
                    *container_items,
                    **container_kwargs
                )
            ]

            # Enviar container primeiro
            await user.send(components=components, flags=disnake.MessageFlags(is_components_v2=True))
            
            # Enviar arquivo separadamente se necessário (components v2 não aceita files)
            if stock_file:
                await user.send(file=stock_file)

        # Enviar mensagem de incentivo de feedback
        await _send_feedback_incentive(user, guild)

        # Se houver thread, enviar confirmação (content simples)
        # Não enviar aqui - será enviado em _handle_payment_approved como reply

        return True

    except disnake.Forbidden:
        # Usuário bloqueou DMs - Entregar no carrinho (content simples)
        if thread:
            # Calcular conteúdo puro (sem numeração) - cada item em uma linha com `
            items_content = "\n".join([f"`{item}`" for item in items])
            content_length = len(items_content)
            use_file = content_length > 2000
            
            if use_file:
                stock_file = _create_stock_file(items)
                display_text = f"*Arquivo anexado com {len(items)} item(s)*"
            else:
                stock_file = None
                display_text = items_content
            
            # Avisar que a DM está fechada
            await thread.send(
                f"{emoji.warn} **DM Fechada**\n{user.mention}, suas mensagens diretas estão desativadas!\nOs itens serão entregues aqui no carrinho."
            )
            
            # Entregar os itens no carrinho (apenas conteúdo)
            delivery_message = f"# {emoji.correct} **Produto Entregue!**\n\n"
            
            if use_file:
                delivery_message += f"**Seus Itens:** *Arquivo anexado com {len(items)} item(s)*"
            else:
                delivery_message += f"**Seus Itens:**\n{display_text}"
            
            # Adicionar instruções se existirem
            if instructions:
                delivery_message += f"\n\n**Instruções:**\n{instructions}"
            
            if use_file:
                await thread.send(
                    content=delivery_message,
                    file=stock_file
                )
            else:
                await thread.send(content=delivery_message)
            
            return True  # Entrega bem-sucedida no carrinho
        
        return False

    except Exception as e:
        if thread:
            # Mensagem de erro (content simples)
            await thread.send(
                f"{emoji.wrong} **Erro na Entrega**\nErro ao entregar produto: {str(e)}"
            )
        return False


async def _send_feedback_incentive(user: disnake.User, guild: Optional[disnake.Guild]):
    """Envia mensagem de incentivo de feedback"""
    try:
        config = db.get_document("loja_personalization") or {}
        feedback_config = config.get("feedback_incentive", {})

        if not feedback_config.get("message"):
            return

        mode = (db.get_document("custom_mode") or {}).get("mode", "components")
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        color = None
        if primary_color_hex:
            try:
                color = int(primary_color_hex.replace("#", ""), 16)
            except:
                pass

        message_text = feedback_config.get("message", "")
        button_text = feedback_config.get("button_text", "Deixar Avaliação")

        # Obter canal de avaliações se existir
        canais = db.get_document("canais") or {}
        feedback_channel_id = canais.get("canal_de_feedback")

        components_list = []
        if feedback_channel_id and guild:
            feedback_url = f"https://discord.com/channels/{guild.id}/{feedback_channel_id}"
            components_list = [
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label=button_text,
                        style=disnake.ButtonStyle.link,
                        url=feedback_url,
                        emoji=emoji.star
                    )
                )
            ]

        if mode == "embed":
            embed = disnake.Embed(
                description=message_text,
                color=color or disnake.Color.blurple()
            )
            await user.send(embed=embed, components=components_list if components_list else None)
        else:
            container_kwargs = {}
            if color:
                container_kwargs["accent_colour"] = disnake.Colour(color)

            main_components = [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(message_text),
                    **container_kwargs
                )
            ]

            if components_list:
                main_components.extend(components_list)

            await user.send(components=main_components, flags=disnake.MessageFlags(is_components_v2=True))

    except Exception:
        pass


async def process_automatic_delivery(
    user: disnake.User,
    product_id: str,
    campo_id: str,
    product_name: str,
    campo_name: str,
    quantity: int,
    thread: Optional[disnake.Thread] = None,
    guild: Optional[disnake.Guild] = None
) -> bool:
    """
    Processa a entrega automática de um produto
    Retorna True se a entrega foi bem-sucedida
    """
    
    # Verificar estoque disponível antes de tentar retirar
    available_stock = StockManager.get_available_stock(product_id, campo_id)
    
    # Retirar itens do estoque
    items = StockManager.get_stock_items(product_id, campo_id, quantity)

    if items is None:
        # Sem estoque suficiente
        if thread:
            mode = (db.get_document("custom_mode") or {}).get("mode", "components")
            if mode == "embed":
                error_embed = disnake.Embed(
                    title=f"{emoji.wrong} Estoque Insuficiente",
                    description=(
                        f"Não há estoque suficiente para entregar este produto.\n"
                        f"Por favor, entre em contato com um administrador."
                    ),
                    color=disnake.Color.red()
                )
                await thread.send(embed=error_embed)
            else:
                await thread.send(
                    components=[
                        disnake.ui.Container(
                            disnake.ui.TextDisplay(f"# {emoji.wrong} Estoque Insuficiente"),
                            disnake.ui.Separator(),
                            disnake.ui.TextDisplay(
                                f"Não há estoque suficiente para entregar este produto.\n"
                                f"Por favor, entre em contato com um administrador."
                            ),
                            accent_colour=disnake.Colour.red()
                        )
                    ],
                    flags=disnake.MessageFlags(is_components_v2=True)
                )
        return False

    # Buscar instruções do campo
    products = db.get_document("loja_products")
    product = products.get(product_id, {})
    campo = product.get("campos", {}).get(campo_id, {})
    instructions = campo.get("instructions")
    
    # Entregar ao usuário
    success = await deliver_product_to_user(
        user=user,
        product_name=product_name,
        campo_name=campo_name,
        quantity=quantity,
        items=items,
        thread=thread,
        guild=guild,
        instructions=instructions,
        product_id=product_id,
        campo_id=campo_id
    )

    if not success:
        # Devolver itens ao estoque
        StockManager.return_stock_items(product_id, campo_id, items)
        return False

    try:
        remaining_stock = StockManager.get_available_stock(product_id, campo_id)
        if available_stock > 0 and remaining_stock <= 0:
            state = getattr(thread or guild, "_state", None)
            bot_ref = state._get_client() if state and hasattr(state, "_get_client") else None
            await StockManager._announce_stock_empty(product_id, campo_id, bot=bot_ref)
    except Exception:
        pass
    
    # Logs são enviados centralmente em _handle_payment_approved para evitar duplicação
    # Não enviar logs aqui para evitar duplicação quando há múltiplos produtos no carrinho
    
    return success


async def send_payment_approved_dm(
    user: disnake.User,
    product_name: str,
    campo_name: str,
    quantity: int,
    delivery_type: str,
    thread_url: Optional[str] = None
):
    """Envia DM informando que o pagamento foi aprovado"""
    try:
        mode = (db.get_document("custom_mode") or {}).get("mode", "components")
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        color = None
        if primary_color_hex:
            try:
                color = int(primary_color_hex.replace("#", ""), 16)
            except:
                pass

        delivery_text = ""
        if delivery_type == "automatic":
            delivery_text = "Seu produto será entregue automaticamente em instantes!"
        else:
            delivery_text = f"Entrega manual. Um administrador irá entregar seu produto em breve.\nAcompanhe no carrinho: {thread_url if thread_url else 'Verifique o servidor'}"

        if mode == "embed":
            embed = disnake.Embed(
                title=f"{emoji.correct} Pagamento Aprovado!",
                description=(
                    f"Seu pagamento foi aprovado com sucesso!\n\n"
                    f"**Produto:** {product_name}\n"
                    f"**Campo:** {campo_name}\n"
                    f"**Quantidade:** {quantity}"
                ),
                color=color or disnake.Color.green()
            )

            embed.add_field(
                name="Entrega",
                value=delivery_text,
                inline=False
            )

            await user.send(embed=embed)

        else:
            container_kwargs = {}
            if color:
                container_kwargs["accent_colour"] = disnake.Colour(color)

            await user.send(
                components=[
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(f"# {emoji.correct} Pagamento Aprovado!"),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(
                            f"Seu pagamento foi aprovado com sucesso!\n\n"
                            f"**Produto:** {product_name}\n"
                            f"**Campo:** {campo_name}\n"
                            f"**Quantidade:** {quantity}"
                        ),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(f"**Entrega:** {delivery_text}"),
                        **container_kwargs
                    )
                ],
                flags=disnake.MessageFlags(is_components_v2=True)
            )

    except disnake.Forbidden:
        pass  # Usuário bloqueou DMs
    except Exception:
        pass  # Ignorar outros erros
