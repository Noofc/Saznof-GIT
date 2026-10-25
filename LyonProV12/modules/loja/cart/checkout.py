import disnake
import asyncio
import base64
import io
import aiohttp
import time
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from functions.database import database as db
from functions.emoji import emoji
from functions.message import message
from functions.bool_utils import as_bool
from functions.text_utils import wrap_text
from functions.utils import utils

# Cache simples para métodos de pagamento (TTL de 30 segundos)
_payment_methods_cache = {"data": None, "timestamp": 0, "ttl": 30}
from functions.payments import (
    create_mp_payment_from_settings,
    create_mp_site_payment_from_settings,
    create_efi_payment_from_settings,
    create_stripe_payment_from_settings,
    create_coinbase_payment_from_settings,
    create_asaas_pix_payment_from_settings,
    create_manual_pix_payment,
    create_misticpay_payment_from_settings,
    create_nubank_imap_payment,
    create_picpay_imap_payment_from_settings,
    create_itau_imap_payment_from_settings,
    check_mp_payment_from_settings,
    check_efi_payment_from_settings,
    check_pagbank_payment_from_settings,
    check_picpay_payment_from_settings,
    check_pushinpay_payment_from_settings,
    check_stripe_payment_from_settings,
    check_paypal_payment_from_settings,
    check_asaas_payment_from_settings,
    check_coinbase_payment_from_settings,
    check_nowpayments_invoice_from_settings,
    check_manual_pix_payment,
    check_misticpay_payment_from_settings,
    check_nubank_imap_payment,
    check_picpay_imap_payment_from_settings,
    check_itau_imap_payment_from_settings,
    approve_manual_pix_payment,
)
from functions.payments.create_payment import BASE_URL as PAY_API_BASE
from .stock_manager import StockManager
from .delivery import process_automatic_delivery, send_payment_approved_dm
from .purchase_manager import PurchaseManager
from .receipt_renderer import send_purchase_receipt
from .coupon_validator import CouponValidator
from .order_utils import ensure_cart_order_id
from modules.loja.logs.purchase_logs import PurchaseLogsLyon
from .buy_modal import ensure_emoji
from functions.plan import is_free, should_allow_payment_provider
from functions.payments.manual_payment import get_manual_pix_config


def invalidate_payment_methods_cache() -> None:
    _payment_methods_cache["data"] = None
    _payment_methods_cache["timestamp"] = 0


def _payment_provider_enabled(provider: str, pagamentos: dict, payment_configs: dict) -> bool:
    entry = payment_configs.get(provider) or {}
    cfg_enabled = as_bool(entry.get("enabled"), False) if isinstance(entry, dict) else as_bool(entry, False)
    legacy_enabled = provider == "efibank" and as_bool(pagamentos.get("efi"), False)
    return cfg_enabled or as_bool(pagamentos.get(provider), False) or legacy_enabled

def _find_first(data: Any, keys: List[str]) -> Optional[Any]:
    """Busca recursiva por chaves em estrutura de dados"""
    if isinstance(data, dict):
        for k in keys:
            if k in data and data[k]:
                return data[k]
        for v in data.values():
            r = _find_first(v, keys)
            if r:
                return r
    elif isinstance(data, list):
        for it in data:
            r = _find_first(it, keys)
            if r:
                return r
    return None


def _extract_urls(data: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Extrai URLs de checkout e código PIX"""
    checkout = _find_first(data, [
        "checkout_url", "url", "init_point", "init_url",
        "invoice_url", "payment_url", "hosted_url", "link",
        "paymentLinkUrl"  # Lyon Wallet
    ])
    copy_code = _find_first(data, [
        "copy_paste", "pix_copia_cola", "emv", "code",
        "qr_code_text", "qrcode_text",
        "pixCopyPaste", "qrCode"  # Lyon Wallet
    ])
    return str(checkout) if checkout else None, str(copy_code) if copy_code else None


def _extract_qr_image(data: Dict[str, Any]) -> tuple[Optional[bytes], Optional[str]]:
    """Extrai imagem QR Code"""
    # Primeiro tentar qr_code_bytes direto (PushinPay, PagBank, PIX Manual)
    qr_bytes = _find_first(data, ["qr_code_bytes"])
    if isinstance(qr_bytes, bytes):
        return qr_bytes, None
    
    # Tentar base64
    b64 = _find_first(data, ["qr_code_base64", "qrcode_base64", "qr_base64", "base64"])
    if isinstance(b64, str):
        try:
            if b64.startswith("data:") and "," in b64:
                b64 = b64.split(",", 1)[1]
            raw = base64.b64decode(b64)
            return raw, "qrcode.png"
        except Exception:
            pass
    
    # Tentar URL
    url = _find_first(data, ["qr_code_url", "qrcode_url", "qr_url", "image", "qr_code_image_url", "qrCodeImage"])  # Lyon Wallet
    return None, str(url) if url else None


def _api_base_root() -> str:
    """Retorna a URL base da API"""
    base = PAY_API_BASE.rstrip("/")
    if "/api/" in base:
        return base.split("/api/", 1)[0]
    return base




async def _send_whatsapp_notification(product_name: str, value: str, buyer_name: str):
    """Envia notificação de venda para a API do WhatsApp"""
    try:
        # Obter configuração de notificação
        notif_config = db.get_document("notifications_config") or {}
        
        if not notif_config.get("enabled"):
            return
            
        ddd = notif_config.get("ddd")
        number = notif_config.get("number")
        
        if not ddd or not number:
            return
            
        url = "https://notify.Lyonapplications.com.br/notify-sale"
        data = {
            "productName": product_name,
            "value": value,
            "buyerName": buyer_name,
            "ddd": ddd,
            "number": number
        }
        
        print(f"[WhatsApp] Tentando enviar notificação: {data}")
        # Timeout curto para não travar o bot
        t = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=t) as session:
            async with session.post(url, json=data) as resp:
                status = resp.status
                text = await resp.text()
                print(f"[WhatsApp] Status: {status} | Resposta: {text}")
                if status != 200:
                    print(f"[WhatsApp] ❌ Falha na API: {status} - {text}")
                else:
                    print(f"[WhatsApp] ✅ Notificação enviada com sucesso!")
    except Exception as e:
        print(f"[WhatsApp] Erro ao enviar notificação: {e}")


async def _http_get_bytes(url: str, timeout: int = 15) -> Optional[bytes]:
    """Baixa bytes de uma URL"""
    try:
        t = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=t) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        return None
    return None


def _extract_payment_ids(data: Dict[str, Any]) -> Dict[str, str]:
    """Extrai IDs de pagamento"""
    out: Dict[str, str] = {}
    # Incluir txid para Efí, paymentId e correlationID para Lyon Wallet
    for k in ["payment_id", "paymentId", "id", "correlationID", "payment_intent", "charge", "preference_id", "invoice_id", "txid"]:
        v = _find_first(data, [k])
        if v:
            out[k] = str(v)
    return out


def _migrate_cart_to_items(cart: Dict[str, Any]) -> Dict[str, Any]:
    """Migra carrinho antigo (sem items) para nova estrutura com items"""
    if "items" in cart:
        # Verificar se items estão válidos
        items = cart.get("items", [])
        if items and all(item.get("product_id") and item.get("campo_id") for item in items):
            return cart  # Já está na nova estrutura e items são válidos
        elif items:
            # Items existem mas estão inválidos - tentar migrar do formato antigo se possível
            if cart.get("product_id") and cart.get("campo_id"):
                # Criar items válidos do formato antigo
                items = [{
                    "product_id": cart.get("product_id"),
                    "campo_id": cart.get("campo_id"),
                    "quantity": cart.get("quantity", 1),
                    "price_per_unit": cart.get("price_per_unit", 0),
                    "item_total": cart.get("price_per_unit", 0) * cart.get("quantity", 1)
                }]
                cart["items"] = items
                return cart
    
    # Criar estrutura nova com items
    items = [{
        "product_id": cart.get("product_id"),
        "campo_id": cart.get("campo_id"),
        "quantity": cart.get("quantity", 1),
        "price_per_unit": cart.get("price_per_unit", 0),
        "item_total": cart.get("price_per_unit", 0) * cart.get("quantity", 1)
    }]
    
    cart["items"] = items
    return cart


def _migrate_payment_data(cart: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migra payment_data antiga para nova estrutura organizada
    
    Nova estrutura separa:
    - local: Dados de interface do bot (copy_code, qr_url, etc.)
    - provider: Dados específicos do provedor (payment_id, correlation_id, etc.)
    - metadata: Informações contextuais (created_at, payment_method, amount)
    """
    payment_data = cart.get("payment_data", {})
    
    # Se já está na nova estrutura, retornar
    if "local" in payment_data and "provider" in payment_data:
        return cart
    
    # Se não tem payment_data, retornar
    if not payment_data:
        return cart
    
    # Migrar para nova estrutura
    new_payment_data = {
        "local": {
            "copy_code": payment_data.get("copy_code"),
            "qr_url": payment_data.get("qr_url"),
            "qr_bytes": payment_data.get("qr_bytes"),
            "requires_manual_approval": payment_data.get("requires_manual_approval", False)
        },
        "provider": {
            "name": payment_data.get("payment_provider"),
            "raw_response": payment_data.get("raw", {})
        },
        "metadata": {
            "created_at": cart.get("created_at"),
            "payment_method": cart.get("payment_method"),
            "amount": cart.get("total_price"),
            "currency": "BRL"
        }
    }
    
    # Extrair IDs do payment_ids (estrutura antiga)
    payment_ids = payment_data.get("payment_ids", {})
    if payment_ids:
        for key, value in payment_ids.items():
            # Normalizar nomes de chaves
            if key in ["payment_id", "paymentId"]:
                new_payment_data["provider"]["payment_id"] = value
            elif key in ["correlationID", "correlation_id"]:
                new_payment_data["provider"]["correlation_id"] = value
            elif key in ["charge_id", "chargeId"]:
                new_payment_data["provider"]["charge_id"] = value
            elif key == "txid":
                new_payment_data["provider"]["txid"] = value
            else:
                new_payment_data["provider"][key] = value
    
    # Fallback: tentar extrair IDs diretamente do raw
    raw_data = payment_data.get("raw", {})
    if raw_data and not payment_ids:
        if "paymentId" in raw_data:
            new_payment_data["provider"]["payment_id"] = raw_data["paymentId"]
        if "correlationID" in raw_data:
            new_payment_data["provider"]["correlation_id"] = raw_data["correlationID"]
        if "id" in raw_data:
            new_payment_data["provider"]["charge_id"] = raw_data["id"]
        if "txid" in raw_data:
            new_payment_data["provider"]["txid"] = raw_data["txid"]
    
    cart["payment_data"] = new_payment_data
    return cart


async def _find_user_open_cart(user_id: int, guild_id: int, delivery_type: str, bot=None, guild=None, loja_data_cache: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """Encontra carrinho aberto do usuário no servidor (permite tipos de entrega mistos quando em status 'cart')"""
    # Usar cache se fornecido, senão carregar do banco
    if loja_data_cache is None:
        loja_data = db.get_document("loja_data")
    else:
        loja_data = loja_data_cache
    
    carts = loja_data.get("carts", {})
    
    orphaned_carts = []  # Lista de carrinhos órfãos para limpeza
    current_time = int(datetime.utcnow().timestamp())
    
    for cart_id, cart in carts.items():
        cart_user_id = cart.get("user_id")
        cart_guild_id = cart.get("guild_id")
        cart_status = cart.get("status", "pending")
        
        # Comparar user_id e guild_id (garantir tipos compatíveis)
        if (cart_user_id == user_id or str(cart_user_id) == str(user_id)) and \
           (cart_guild_id == guild_id or str(cart_guild_id) == str(guild_id)):
            
            # Aceitar carrinhos em status "cart" (antes do pagamento) - permite tipos de entrega mistos
            # Para status "pending" (em pagamento), não permitir adicionar mais itens
            if cart_status == "cart":
                
                # VERIFICAÇÃO CRÍTICA: Verificar se a thread ainda existe
                thread_id = cart.get("thread_id")
                thread_exists = False
                
                if thread_id:
                    # Verificar se o carrinho foi criado recentemente (últimos 30 segundos)
                    # Se sim, assumir que a thread existe (pode estar sendo criada ainda)
                    created_at = cart.get("created_at", 0)
                    is_recent = (current_time - created_at) < 30  # 30 segundos (aumentado para evitar verificações desnecessárias)
                    
                    if is_recent:
                        thread_exists = True
                    else:
                        # Tentar obter guild se não foi passado
                        check_guild = guild
                        if not check_guild and bot:
                            try:
                                check_guild = bot.get_guild(int(guild_id))
                            except:
                                pass
                        
                        if check_guild:
                            try:
                                # Tentar get_thread primeiro (mais rápido, usa cache)
                                thread = check_guild.get_thread(int(thread_id))
                                if thread:
                                    thread_exists = True
                                # Só fazer fetch_channel se get_thread falhar (mais lento)
                                # Removido para melhorar performance - assumir que thread existe se não está no cache
                                # pois fetch_channel é muito lento
                            except Exception:
                                thread_exists = False
                        else:
                            # Se não temos guild para verificar, assumir que thread existe (evitar falsos positivos)
                            thread_exists = True
                
                if not thread_exists:
                    orphaned_carts.append(cart_id)
                    continue  # Pular este carrinho
                
                # Migrar se necessário
                cart = _migrate_cart_to_items(cart)
                
                # Verificar se tem items válidos
                items = cart.get("items", [])
                
                # Aceitar carrinho mesmo se não tiver items ainda (pode estar sendo criado)
                if not items:
                    return cart_id, cart
                
                if items and all(item.get("product_id") and item.get("campo_id") for item in items):
                    # Retornar o carrinho - permite adicionar produtos com tipos de entrega diferentes
                    return cart_id, cart
                elif items:
                    # Retornar mesmo assim para tentar adicionar
                    return cart_id, cart
    
    # Limpar carrinhos órfãos encontrados (só se não estivermos usando cache)
    if orphaned_carts and loja_data_cache is None:
        loja_data = db.get_document("loja_data")
        for orphan_id in orphaned_carts:
            if orphan_id in loja_data.get("carts", {}):
                del loja_data["carts"][orphan_id]
        db.save_document("loja_data", loja_data)
    
    return None, None


def _build_approved_checkout_message(
    cart: Dict[str, Any],
    items: List[Dict[str, Any]],
    products: Dict[str, Any],
    delivered_automatically: bool,
    manual_items_count: int,
    mode: str = "embed"
) -> tuple[Optional[disnake.Embed], Optional[List], Optional[str]]:
    """
    Constrói mensagem de checkout aprovado em formato embed ou container
    Retorna: (embed, components_list, content_text)
    Se mode == "embed", retorna (embed, components, None)
    Se mode == "components", retorna (None, components, None)
    """
    from functions.utils import utils
    
    # Calcular valores
    total_price = cart.get("total_price", 0)
    discount_amount = cart.get("discount_amount", 0) or 0
    balance_applied = cart.get("balance_applied", 0) or 0
    final_price = max(0, total_price - discount_amount - balance_applied)
    payment_method = cart.get("payment_method", "unknown")
    
    # Formatar preços
    price_display = utils.format_price_brl(final_price)
    
    payment_methods_map = {
        "pix": "PIX",
        "card": "Cartão de Crédito",
        "crypto": "Criptomoeda",
        "free_coupon": "Cupom 100%"
    }
    payment_display = payment_methods_map.get(payment_method, payment_method.upper())
    
    # Obter cor padrão configurada
    color_data = db.get_document("custom_colors") or {}
    primary_color = color_data.get("primary")
    embed_color = None
    container_color = None
    if primary_color:
        try:
            if primary_color.startswith("#"):
                embed_color = disnake.Colour(int(primary_color.replace("#", ""), 16))
            else:
                embed_color = disnake.Colour(int(primary_color, 16))
            container_color = embed_color
        except:
            pass
    
    if not embed_color:
        embed_color = disnake.Color.green()
    
    # Componentes (botões)
    components = []
    if manual_items_count > 0:
        # Adicionar botão "Encerrar Atendimento" apenas se houver entrega manual
        cart_id = cart.get('cart_id') or cart.get('thread_id')
        components.append(
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Encerrar Atendimento",
                    style=disnake.ButtonStyle.red,
                    custom_id=f"close_cart:{cart_id}",
                    emoji=emoji.delete if hasattr(emoji, 'delete') else "🗑️"
                )
            )
        )
    
    if mode == "embed":
        # Modo Embed
        embed = disnake.Embed(
            title=f"{emoji.lyon} Checkout Aprovado",
            color=embed_color,
            timestamp=datetime.utcnow()
        )
        
        # Listar produtos
        products_text = []
        for item in items:
            product_id = item.get("product_id")
            campo_id = item.get("campo_id")
            qty = item.get("quantity", 1)
            item_total = item.get("item_total", 0)
            
            if not product_id or not campo_id:
                continue
            
            product = products.get(product_id, {})
            if not product:
                continue
            
            product_name = product.get("name", "Produto")
            campos = product.get("campos", {}) or {}
            campo = campos.get(campo_id, {})
            campo_name = campo.get("name", "Campo") if campo else "Campo"
            
            # Obter tipo de entrega deste produto
            info = product.get("info") or {}
            item_delivery_type = info.get("delivery_type", "automatic")
            
            item_price_str = utils.format_price_brl(item_total)
            delivery_status = "Entregue" if item_delivery_type == "automatic" and delivered_automatically else ("Pendente" if item_delivery_type == "manual" else "Entregue")
            
            # Buscar instruções do campo
            instructions = campo.get("instructions")
            instructions_text = f"\nInstruções: {instructions}" if instructions else ""
            
            products_text.append(f"**{product_name}** - `{campo_name}`\nQuantidade: `{qty}` | Valor: `{item_price_str}` | Status: {delivery_status}{instructions_text}")
        
        if products_text:
            embed.add_field(
                name=f"{emoji.bag} Produtos",
                value="\n\n".join(products_text),
                inline=False
            )
        
        # Informações de pagamento
        # Montar linha de cupom e método
        coupon_method_line = ""
        if cart.get("coupon_code"):
            coupon_method_line = f"**Cupom:** `{cart.get('coupon_code')}` • **Método:** `{payment_display}`"
        else:
            coupon_method_line = f"**Método:** `{payment_display}`"
        
        payment_info = f"**Total:** `{price_display}`\n{coupon_method_line}"
        if discount_amount > 0 or balance_applied > 0:
            subtotal_str = utils.format_price_brl(total_price)
            payment_info = f"**Subtotal:** `{subtotal_str}`\n"
            if discount_amount > 0:
                discount_str = utils.format_price_brl(discount_amount)
                payment_info += f"**Desconto:** `-{discount_str}`\n"
            if balance_applied > 0:
                balance_str = utils.format_price_brl(balance_applied)
                payment_info += f"**Saldo Usado:** `-{balance_str}`\n"
            payment_info += f"**Total:** `{price_display}`\n{coupon_method_line}"
        
        embed.add_field(
            name=f"{emoji.dollar} Pagamento",
            value=payment_info,
            inline=False
        )
        
        # Status de entrega
        if delivered_automatically and manual_items_count == 0:
            status_text = "Todos os produtos foram entregues automaticamente!"
        elif manual_items_count > 0:
            status_text = f"{manual_items_count} produto(s) aguardando entrega manual"
        else:
            status_text = "Processando entrega..."
        
        embed.add_field(
            name="Status",
            value=status_text,
            inline=False
        )
        
        return embed, components, None
    
    else:
        # Modo Container
        container_components = []
        container_components.append(
            disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# **Checkout Aprovado**")
        )
        container_components.append(disnake.ui.Separator())
        
        # Listar produtos
        for item in items:
            product_id = item.get("product_id")
            campo_id = item.get("campo_id")
            qty = item.get("quantity", 1)
            item_total = item.get("item_total", 0)
            
            if not product_id or not campo_id:
                continue
            
            product = products.get(product_id, {})
            if not product:
                continue
            
            product_name = product.get("name", "Produto")
            campos = product.get("campos", {}) or {}
            campo = campos.get(campo_id, {})
            campo_name = campo.get("name", "Campo") if campo else "Campo"
            
            # Obter tipo de entrega deste produto
            info = product.get("info") or {}
            item_delivery_type = info.get("delivery_type", "automatic")
            
            item_price_str = utils.format_price_brl(item_total)
            delivery_status = "Entregue" if item_delivery_type == "automatic" and delivered_automatically else ("Pendente" if item_delivery_type == "manual" else "Entregue")
            
            # Buscar instruções do campo
            instructions = campo.get("instructions")
            instructions_text = f"\n-# Instruções: {instructions}" if instructions else ""
            
            container_components.append(
                disnake.ui.TextDisplay(
                    f"-# **{product_name}** - `{campo_name}`\n"
                    f"-# Quantidade: `{qty}` | Valor: `{item_price_str}` | Status: {delivery_status}{instructions_text}"
                )
            )
            container_components.append(disnake.ui.Separator())
        
        # Informações de pagamento
        # Montar linha de cupom e método
        coupon_method_line = ""
        if cart.get("coupon_code"):
            coupon_method_line = f"-# **Cupom:** `{cart.get('coupon_code')}` • **Método:** `{payment_display}`"
        else:
            coupon_method_line = f"-# **Método:** `{payment_display}`"
        
        payment_info = f"-# **Total:** `{price_display}`\n{coupon_method_line}"
        if discount_amount > 0:
            subtotal_str = utils.format_price_brl(total_price)
            discount_str = utils.format_price_brl(discount_amount)
            payment_info = f"-# **Subtotal:** `{subtotal_str}`\n-# **Desconto:** `-{discount_str}`\n-# **Total:** `{price_display}`\n{coupon_method_line}"
        
        container_components.append(
            disnake.ui.TextDisplay(f"## **Pagamento:**\n{payment_info}")
        )
        container_components.append(disnake.ui.Separator())
        
        # Status de entrega
        if delivered_automatically and manual_items_count == 0:
            status_text = "Todos os produtos foram entregues automaticamente!"
        elif manual_items_count > 0:
            status_text = f"{manual_items_count} produto(s) aguardando entrega manual"
        else:
            status_text = "Processando entrega..."
        
        container_components.append(
            disnake.ui.TextDisplay(f"## **Status:**\n{status_text}")
        )
        
        container_kwargs = {}
        if container_color:
            container_kwargs["accent_colour"] = container_color
        
        container = disnake.ui.Container(*container_components, **container_kwargs)
        
        return None, [container] + components, None


def _build_cart_components(cart: Dict[str, Any], thread: disnake.Thread, mode: str) -> Dict[str, Any]:
    """Constrói componentes do carrinho sem enviar mensagem - para uso em edições"""
    products = db.get_document("loja_products")
    items = cart.get("items", [])
    
    if not items:
        return {}
    
    # Calcular totais
    total_price = sum(item.get("item_total", 0) for item in items)
    
    # Obter desconto, cupom e método de pagamento do carrinho
    discount_amount = cart.get("discount_amount", 0) or 0
    coupon_code = cart.get("coupon_code")
    balance_applied = cart.get("balance_applied", 0) or 0
    final_price = max(0, total_price - discount_amount - balance_applied)
    payment_method = cart.get("payment_method", "pix")
    
    # Obter informações do saldo do usuário
    balance_info = {"enabled": False, "can_apply": False, "user_balance": 0, "usable_amount": 0}
    try:
        from modules.loja.saldo.checkout_integration import SaldoCheckoutIntegration
        user_id = cart.get("user_id")
        if user_id:
            balance_info = SaldoCheckoutIntegration.get_cart_balance_info(cart, int(user_id))
    except Exception:
        pass
    
    # Calcular cashback que o usuário vai ganhar
    cashback_amount = 0
    try:
        from modules.loja.cashback.manager import CashbackManager
        user_id = cart.get("user_id")
        if user_id and CashbackManager.is_enabled():
            # Obter roles do usuário para aplicar multiplicadores
            user_roles = []
            try:
                guild_id = cart.get("guild_id")
                if guild_id and thread:
                    guild = thread.guild
                    member = guild.get_member(int(user_id))
                    if member:
                        user_roles = [role.id for role in member.roles]
            except Exception:
                pass
            
            # Calcular cashback baseado no total final (após descontos e saldo)
            cashback_amount = CashbackManager.calculate_cashback(final_price, user_roles)
    except Exception:
        pass
    
    # Verificar quantos métodos de pagamento estão disponíveis globalmente
    def _get_available_payment_method_keys() -> list[str]:
        # Usar cache se ainda válido
        global _payment_methods_cache
        current_time = time.time()
        if _payment_methods_cache["data"] is not None and (current_time - _payment_methods_cache["timestamp"]) < _payment_methods_cache["ttl"]:
            return _payment_methods_cache["data"]
        
        pagamentos_doc = db.get_document("pagamentos") or {}
        payment_configs = db.get_document("payment_configs") or {}
        # Mesma lista de métodos usada no fluxo de compra
        providers_coming_soon = [
            "nubank", "inter", "bitcoin", "litecoin", "ethereum", "livepix", "promissepay"
        ]
        all_methods = {
            "pix": {
                "providers": ["mercado_pago", "efibank", "pagbank", "picpay", "pushinpay", "misticpay", "nubank_imap", "picpay_imap", "itau_imap", "asaas", "pix_manual"]
            },
            "card": {
                "providers": ["mercado_pago", "stripe", "efibank", "paypal", "asaas"]
            },
            "crypto": {
                "providers": ["coinbase", "nowpayments"]
            },
        }
        available_keys: list[str] = []
        for method_key, method_info in all_methods.items():
            if method_key == "card" and not as_bool((payment_configs.get("card") or {}).get("enabled"), False):
                continue
            has_provider = False
            for provider in method_info["providers"]:
                if provider in providers_coming_soon:
                    continue
                # Verificar se o provedor é permitido pelo plano atual
                if not should_allow_payment_provider(provider):
                    continue
                provider_config = payment_configs.get(provider, {})
                is_enabled = False
                if isinstance(provider_config, dict):
                    is_enabled = as_bool(provider_config.get("enabled"), False)
                if not is_enabled:
                    is_enabled = as_bool(pagamentos_doc.get(provider), False)
                has_valid_config = False
                if isinstance(provider_config, dict) and provider_config:
                    if provider == "mercado_pago":
                        has_valid_config = bool(provider_config.get("access_token"))
                    elif provider == "efibank":
                        cert_path = provider_config.get("cert_file")
                        cert_ok = bool(cert_path)
                        has_client = bool(provider_config.get("client_id") or provider_config.get("client"))
                        has_secret = bool(provider_config.get("client_secret") or provider_config.get("token"))
                        has_pix = bool(provider_config.get("pix_key"))
                        has_valid_config = bool(cert_ok and has_client and has_secret and has_pix)
                    elif provider in {"pagbank", "picpay", "pushinpay", "asaas", "stripe", "coinbase", "nowpayments"}:
                        token_key = {
                            "pagbank": "token_pagbank",
                            "picpay": "token_picpay",
                            "pushinpay": "token_pushinpay",
                            "asaas": "token_asaas",
                            "stripe": "token_stripe",
                            "coinbase": "token_coinbase",
                            "nowpayments": "token_nowpayments",
                        }.get(provider)
                        has_valid_config = bool(token_key and provider_config.get(token_key))
                    elif provider == "paypal":
                        has_valid_config = bool(provider_config.get("client_id") and provider_config.get("client_secret"))
                    elif provider == "misticpay":
                        client_id = provider_config.get("client_id")
                        client_secret = provider_config.get("client_secret")
                        has_valid_config = bool(client_id and client_secret)
                    elif provider in {"nubank_imap", "picpay_imap", "itau_imap"}:
                        has_valid_config = bool(provider_config.get("email") and provider_config.get("password") and provider_config.get("pix_key"))
                    elif provider == "Lyon_wallet":
                        has_valid_config = bool(provider_config.get("api_key"))
                    elif provider == "pix_manual":
                        manual_cfg = get_manual_pix_config()
                        has_valid_config = bool(manual_cfg.get("pix_key") and manual_cfg.get("pix_key_type"))
                    else:
                        important_keys = [
                            "access_token", "client_id", "client_secret", "api_key",
                            "public_key", "secret_key", "token", "pix_key",
                        ]
                        has_valid_config = any(provider_config.get(k) for k in important_keys)
                if is_enabled and has_valid_config:
                    has_provider = True
                    break
            if has_provider:
                available_keys.append(method_key)
        
        # Atualizar cache
        _payment_methods_cache["data"] = available_keys
        _payment_methods_cache["timestamp"] = current_time
        
        return available_keys
    
    available_payment_keys = _get_available_payment_method_keys()
    
    # Obter cor padrão configurada (não usar cor do produto)
    color_data = db.get_document("custom_colors") or {}
    primary_color = color_data.get("primary")
    product_color = None
    if primary_color:
        try:
            if primary_color.startswith("#"):
                product_color = disnake.Colour(int(primary_color.replace("#", ""), 16))
            else:
                product_color = disnake.Colour(int(primary_color, 16))
        except:
            pass
    
    if mode == "components":
        container_components = []
        
        # Header com botão X para fechar
        try:
            header_text = f"# {emoji.lyon}"
        except:
            header_text = "# 🛒 Carrinho de Compras"
        
        header_section = disnake.ui.Section(
            disnake.ui.TextDisplay(header_text),
            accessory=disnake.ui.Button(
                emoji=emoji.wrong,
                style=disnake.ButtonStyle.danger,
                custom_id=f"cart_close:{thread.id}"
            )
        )
        container_components.append(header_section)
        container_components.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small, divider=True))
        
        # Adicionar cada produto como Section com botão de editar
        for idx, item in enumerate(items):
            product = products.get(item.get("product_id"))
            if not product:
                continue
            
            product_name = product.get("name", "Produto")
            campos = product.get("campos", {})
            campo = campos.get(item.get("campo_id"))
            campo_name = campo.get("name", "") if campo else "Campo"
            quantity = item.get("quantity", 1)
            price_per_unit = item.get("price_per_unit", 0)
            item_total = item.get("item_total", 0)
            
            # Formatar preços
            price_str = f"R$ {price_per_unit:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            total_str = f"R$ {item_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
            # Produto com emoji e quantidade
            product_text = f"{emoji.bag} **{product_name}** (x{quantity})\n"
            product_text += f"-# Campo: {campo_name} | Preço unitário: {price_str} | Total: {total_str}"
            
            # Section com botão de editar ao lado
            item_section = disnake.ui.Section(
                disnake.ui.TextDisplay(product_text),
                accessory=disnake.ui.Button(
                    emoji=emoji.edit,
                    style=disnake.ButtonStyle.secondary,
                    custom_id=f"cart_edit_quantity:{thread.id}:{idx}"
                )
            )
            container_components.append(item_section)
            
            # Separator entre produtos
            container_components.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small, divider=True))
        
        # Resumo do carrinho (cupom, produtos, subtotal, total)
        summary_lines = []
        
        # Cupom (se houver)
        if coupon_code and discount_amount > 0:
            discount_percent = int((discount_amount / total_price) * 100) if total_price > 0 else 0
            discount_str = f"R$ {discount_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            summary_lines.append(f"-# {coupon_code} — {discount_percent}% OFF | Economia: -{discount_str}")
        
        # Contadores
        num_products = len(items)
        total_items = sum(item.get("quantity", 1) for item in items)
        summary_lines.append(f"-# Produtos: {num_products} | Itens: {total_items}")
        
        # Subtotal e Total
        subtotal_str = f"R$ {total_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        final_str = f"R$ {final_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        summary_lines.append(f"-# Subtotal: {subtotal_str} | Total: {final_str}")
        
        container_components.append(
            disnake.ui.TextDisplay("\n".join(summary_lines))
        )
        
        # Container com cor
        container_kwargs = {}
        if product_color:
            container_kwargs["accent_colour"] = product_color
        
        cart_container = disnake.ui.Container(*container_components, **container_kwargs)
        
        # Botões de ação (Aplicar Cupom e Continuar)
        action_buttons = []
        
        # Botão de aplicar/remover cupom
        if coupon_code:
            action_buttons.append(
                disnake.ui.Button(
                    label="Remover Cupom",
                    emoji=emoji.delete,
                    style=disnake.ButtonStyle.secondary,
                    custom_id=f"cart_remove_coupon:{thread.id}"
                )
            )
        else:
            action_buttons.append(
                disnake.ui.Button(
                    label="Aplicar Cupom",
                    emoji=emoji.coupon if hasattr(emoji, "coupon") else "🎫",
                    style=disnake.ButtonStyle.secondary,
                    custom_id=f"cart_apply_coupon:{thread.id}"
                )
            )
        
        # Botão de continuar
        action_buttons.append(
            disnake.ui.Button(
                label="Continuar com o Carrinho",
                emoji=emoji.arrow,
                style=disnake.ButtonStyle.success,
                custom_id=f"cart_continue:{thread.id}"
            )
        )
        
        # Montar lista de componentes
        components_to_send = [cart_container, disnake.ui.ActionRow(*action_buttons)]
        
        return {
            "components": components_to_send,
            "flags": disnake.MessageFlags(is_components_v2=True)
        }
    else:
        # Modo Embed
        embed_color = product_color if product_color else disnake.Color.blue()
        embed = disnake.Embed(
            title=f"{emoji.cart} Carrinho de Compras",
            color=embed_color
        )
        
        # Adicionar cada produto
        for idx, item in enumerate(items):
            product = products.get(item.get("product_id"))
            if not product:
                continue
            
            product_name = product.get("name", "Produto")
            campos = product.get("campos", {})
            campo = campos.get(item.get("campo_id"))
            campo_name = campo.get("name", "") if campo else "Campo"
            quantity = item.get("quantity", 1)
            price_per_unit = item.get("price_per_unit", 0)
            item_total = item.get("item_total", 0)
            
            # Formatar preços
            price_str = f"R$ {price_per_unit:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            total_str = f"R$ {item_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
            embed.add_field(
                name=f"{emoji.bag} {product_name} (x{quantity})",
                value=f"Campo: `{campo_name}`\nUnitário: `{price_str}`\nTotal: `{total_str}`",
                inline=False
            )
        
        # Cashback (acima do subtotal)
        if cashback_amount > 0:
            cashback_str = f"R$ {cashback_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            embed.add_field(
                name=f"{emoji.bank if hasattr(emoji, 'bank') else '🏦'} Cashback",
                value=f"`+{cashback_str}`",
                inline=False
            )
        
        # Subtotal
        subtotal_str = f"R$ {total_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        embed.add_field(
            name=f"{emoji.dollar} Subtotal",
            value=f"`{subtotal_str}`",
            inline=False
        )
        
        # Desconto (se houver)
        if discount_amount > 0:
            discount_str = f"R$ {discount_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            discount_field = f"**Desconto:** `-{discount_str}`"
            if coupon_code:
                discount_field += f"\n**Cupom:** `{coupon_code}`"
            embed.add_field(
                name=f"Desconto",
                value=discount_field,
                inline=False
            )
        
        # Total final
        final_str = f"R$ {final_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        embed.add_field(
            name=f"{emoji.dollar} Total",
            value=f"`{final_str}`",
            inline=False
        )
        
        # Saldo aplicado (se houver)
        if balance_applied > 0:
            balance_str = f"R$ {balance_applied:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            embed.add_field(
                name=f"{emoji.wallet} Saldo Usado",
                value=f"`-{balance_str}`",
                inline=False
            )
        
        # Método de pagamento atual
        method_names = {
            "pix": "PIX",
            "card": "Cartão de Crédito",
            "crypto": "Criptomoeda",
        }
        payment_display = method_names.get(payment_method, payment_method.upper())
        embed.add_field(
            name=f"{emoji.card} Forma de Pagamento",
            value=f"`{payment_display}`",
            inline=False
        )
        
        embed.timestamp = datetime.utcnow()
        
        # Botões para cada item + ações
        components = []
        
        # Criar botões para editar/remover cada item
        for idx, item in enumerate(items):
            components.append(
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Editar Quantidade",
                        emoji=emoji.edit,
                        style=disnake.ButtonStyle.grey,
                        custom_id=f"cart_edit_quantity:{thread.id}:{idx}"
                    ),
                    disnake.ui.Button(
                        label="Remover",
                        emoji=emoji.delete,
                        style=disnake.ButtonStyle.danger,
                        custom_id=f"cart_remove_item:{thread.id}:{idx}"
                    )
                )
            )
        
        # Botões de ação (cupom, forma de pagamento e continuar)
        action_row = []
        
        # Botão de aplicar cupom
        action_row.append(
            disnake.ui.Button(
                label="Aplicar Cupom" if not coupon_code else "Alterar Cupom",
                emoji=emoji.coupon if hasattr(emoji, 'coupon') else "🎫",
                style=disnake.ButtonStyle.grey,
                custom_id=f"cart_apply_coupon:{thread.id}"
            )
        )
        
        # Botão de remover cupom (se houver cupom aplicado)
        if coupon_code:
            action_row.append(
                disnake.ui.Button(
                    label="Remover Cupom",
                    emoji=emoji.delete,
                    style=disnake.ButtonStyle.red,
                    custom_id=f"cart_remove_coupon:{thread.id}"
                )
            )
        
        # Botão para alterar forma de pagamento (somente se houver mais de um método disponível)
        if len(available_payment_keys) > 1:
            action_row.append(
                disnake.ui.Button(
                    label="Forma de Pagamento",
                    emoji=emoji.card if hasattr(emoji, 'card') else None,
                    style=disnake.ButtonStyle.grey,
                    custom_id=f"cart_change_payment:{thread.id}"
                )
            )
        
        # Botão de usar saldo (se sistema habilitado)
        if balance_info.get("enabled"):
            if balance_applied > 0:
                action_row.append(
                    disnake.ui.Button(
                        label="Remover Saldo",
                        emoji=emoji.wrong if hasattr(emoji, "wrong") else None,
                        style=disnake.ButtonStyle.danger,
                        custom_id=f"cart_remove_balance:{thread.id}"
                    )
                )
            elif balance_info.get("can_apply"):
                user_balance = balance_info.get("user_balance", 0)
                action_row.append(
                    disnake.ui.Button(
                        label=f"Usar Saldo (R$ {user_balance:.2f})",
                        emoji=emoji.wallet if hasattr(emoji, "wallet") else None,
                        style=disnake.ButtonStyle.blurple,
                        custom_id=f"cart_apply_balance:{thread.id}"
                    )
                )
        
        # Botão de continuar
        action_row.append(
            disnake.ui.Button(
                label="Continuar com o Carrinho",
                emoji=emoji.arrow,
                style=disnake.ButtonStyle.green,
                custom_id=f"cart_continue:{thread.id}"
            )
        )
        
        components.append(disnake.ui.ActionRow(*action_row))
        
        return {
            "embed": embed,
            "components": components
        }


async def _build_cart_message(cart: Dict[str, Any], thread: disnake.Thread, mode: str) -> disnake.Message:
    """Constrói e envia mensagem do carrinho com produtos e botões"""
    products = db.get_document("loja_products")
    items = cart.get("items", [])
    
    if not items:
        return None
    
    # Calcular totais
    total_price = sum(item.get("item_total", 0) for item in items)
    
    # Obter desconto, cupom e método de pagamento do carrinho
    discount_amount = cart.get("discount_amount", 0) or 0
    coupon_code = cart.get("coupon_code")
    balance_applied = cart.get("balance_applied", 0) or 0
    final_price = max(0, total_price - discount_amount - balance_applied)
    payment_method = cart.get("payment_method", "pix")
    
    # Obter informações do saldo do usuário
    balance_info = {"enabled": False, "can_apply": False, "user_balance": 0, "usable_amount": 0}
    try:
        from modules.loja.saldo.checkout_integration import SaldoCheckoutIntegration
        user_id = cart.get("user_id")
        if user_id:
            balance_info = SaldoCheckoutIntegration.get_cart_balance_info(cart, int(user_id))
    except Exception:
        pass
    
    # Calcular cashback que o usuário vai ganhar
    cashback_amount = 0
    try:
        from modules.loja.cashback.manager import CashbackManager
        user_id = cart.get("user_id")
        if user_id and CashbackManager.is_enabled():
            # Obter roles do usuário para aplicar multiplicadores
            user_roles = []
            try:
                guild_id = cart.get("guild_id")
                if guild_id and thread:
                    guild = thread.guild
                    member = guild.get_member(int(user_id))
                    if member:
                        user_roles = [role.id for role in member.roles]
            except Exception:
                pass
            
            # Calcular cashback baseado no total final (após descontos e saldo)
            cashback_amount = CashbackManager.calculate_cashback(final_price, user_roles)
    except Exception:
        pass
    
    # Verificar quantos métodos de pagamento estão disponíveis globalmente
    def _get_available_payment_method_keys() -> list[str]:
        # Usar cache se ainda válido
        global _payment_methods_cache
        current_time = time.time()
        if _payment_methods_cache["data"] is not None and (current_time - _payment_methods_cache["timestamp"]) < _payment_methods_cache["ttl"]:
            return _payment_methods_cache["data"]
        
        pagamentos_doc = db.get_document("pagamentos") or {}
        payment_configs = db.get_document("payment_configs") or {}
        # Mesma lista de métodos usada no fluxo de compra
        providers_coming_soon = [
            "nubank", "inter", "bitcoin", "litecoin", "ethereum", "livepix", "promissepay"
        ]
        all_methods = {
            "pix": {
                "providers": ["mercado_pago", "efibank", "pagbank", "picpay", "pushinpay", "misticpay", "nubank_imap", "picpay_imap", "itau_imap", "asaas", "pix_manual"]
            },
            "card": {
                "providers": ["mercado_pago", "stripe", "efibank", "paypal", "asaas"]
            },
            "crypto": {
                "providers": ["coinbase", "nowpayments"]
            },
        }
        available_keys: list[str] = []
        for method_key, method_info in all_methods.items():
            if method_key == "card" and not as_bool((payment_configs.get("card") or {}).get("enabled"), False):
                continue
            has_provider = False
            for provider in method_info["providers"]:
                if provider in providers_coming_soon:
                    continue
                # Verificar se o provedor é permitido pelo plano atual
                if not should_allow_payment_provider(provider):
                    continue
                provider_config = payment_configs.get(provider, {})
                is_enabled = False
                if isinstance(provider_config, dict):
                    is_enabled = as_bool(provider_config.get("enabled"), False)
                if not is_enabled:
                    is_enabled = as_bool(pagamentos_doc.get(provider), False)
                has_valid_config = False
                if isinstance(provider_config, dict) and provider_config:
                    if provider == "mercado_pago":
                        has_valid_config = bool(provider_config.get("access_token"))
                    elif provider == "efibank":
                        cert_path = provider_config.get("cert_file")
                        cert_ok = bool(cert_path)
                        has_client = bool(provider_config.get("client_id") or provider_config.get("client"))
                        has_secret = bool(provider_config.get("client_secret") or provider_config.get("token"))
                        has_pix = bool(provider_config.get("pix_key"))
                        has_valid_config = bool(cert_ok and has_client and has_secret and has_pix)
                    elif provider in {"pagbank", "picpay", "pushinpay", "asaas", "stripe", "coinbase", "nowpayments"}:
                        token_key = {
                            "pagbank": "token_pagbank",
                            "picpay": "token_picpay",
                            "pushinpay": "token_pushinpay",
                            "asaas": "token_asaas",
                            "stripe": "token_stripe",
                            "coinbase": "token_coinbase",
                            "nowpayments": "token_nowpayments",
                        }.get(provider)
                        has_valid_config = bool(token_key and provider_config.get(token_key))
                    elif provider == "paypal":
                        has_valid_config = bool(provider_config.get("client_id") and provider_config.get("client_secret"))
                    elif provider == "misticpay":
                        client_id = provider_config.get("client_id")
                        client_secret = provider_config.get("client_secret")
                        has_valid_config = bool(client_id and client_secret)
                    elif provider in {"nubank_imap", "picpay_imap", "itau_imap"}:
                        has_valid_config = bool(provider_config.get("email") and provider_config.get("password") and provider_config.get("pix_key"))
                    elif provider == "Lyon_wallet":
                        has_valid_config = bool(provider_config.get("api_key"))
                    elif provider == "pix_manual":
                        manual_cfg = get_manual_pix_config()
                        has_valid_config = bool(manual_cfg.get("pix_key") and manual_cfg.get("pix_key_type"))
                    else:
                        important_keys = [
                            "access_token", "client_id", "client_secret", "api_key",
                            "public_key", "secret_key", "token", "pix_key",
                        ]
                        has_valid_config = any(provider_config.get(k) for k in important_keys)
                if is_enabled and has_valid_config:
                    has_provider = True
                    break
            if has_provider:
                available_keys.append(method_key)
        
        # Atualizar cache
        _payment_methods_cache["data"] = available_keys
        _payment_methods_cache["timestamp"] = current_time
        
        return available_keys
    
    available_payment_keys = _get_available_payment_method_keys()
    
    # Obter cor padrão configurada (não usar cor do produto)
    color_data = db.get_document("custom_colors") or {}
    primary_color = color_data.get("primary")
    product_color = None
    if primary_color:
        try:
            if primary_color.startswith("#"):
                product_color = disnake.Colour(int(primary_color.replace("#", ""), 16))
            else:
                product_color = disnake.Colour(int(primary_color, 16))
        except:
            pass
    
    if mode == "components":
        container_components = []
        
        # Header com botão X para fechar
        try:
            header_text = f"# {emoji.lyon}"
        except:
            header_text = "# 🛒 Carrinho de Compras"
        
        header_section = disnake.ui.Section(
            disnake.ui.TextDisplay(header_text),
            accessory=disnake.ui.Button(
                emoji=emoji.wrong,
                style=disnake.ButtonStyle.danger,
                custom_id=f"cart_close:{thread.id}"
            )
        )
        container_components.append(header_section)
        container_components.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small, divider=True))
        
        # Adicionar cada produto como Section com botão de editar
        for idx, item in enumerate(items):
            product = products.get(item.get("product_id"))
            if not product:
                continue
            
            product_name = product.get("name", "Produto")
            campos = product.get("campos", {})
            campo = campos.get(item.get("campo_id"))
            campo_name = campo.get("name", "") if campo else "Campo"
            quantity = item.get("quantity", 1)
            price_per_unit = item.get("price_per_unit", 0)
            item_total = item.get("item_total", 0)
            
            # Formatar preços
            price_str = f"R$ {price_per_unit:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            total_str = f"R$ {item_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
            # Produto com emoji e quantidade
            product_text = f"{emoji.bag} **{product_name}** (x{quantity})\n"
            product_text += f"-# Campo: {campo_name} | Preço unitário: {price_str} | Total: {total_str}"
            
            # Section com botão de editar ao lado
            item_section = disnake.ui.Section(
                disnake.ui.TextDisplay(product_text),
                accessory=disnake.ui.Button(
                    emoji=emoji.edit,
                    style=disnake.ButtonStyle.secondary,
                    custom_id=f"cart_edit_quantity:{thread.id}:{idx}"
                )
            )
            container_components.append(item_section)
            
            # Separator entre produtos
            container_components.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small, divider=True))
        
        # Resumo do carrinho (cupom, produtos, subtotal, total)
        summary_lines = []
        
        # Cupom (se houver)
        if coupon_code and discount_amount > 0:
            discount_percent = int((discount_amount / total_price) * 100) if total_price > 0 else 0
            discount_str = f"R$ {discount_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            summary_lines.append(f"-# {coupon_code} — {discount_percent}% OFF | Economia: -{discount_str}")
        
        # Contadores
        num_products = len(items)
        total_items = sum(item.get("quantity", 1) for item in items)
        summary_lines.append(f"-# Produtos: {num_products} | Itens: {total_items}")
        
        # Subtotal e Total
        subtotal_str = f"R$ {total_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        final_str = f"R$ {final_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        summary_lines.append(f"-# Subtotal: {subtotal_str} | Total: {final_str}")
        
        container_components.append(
            disnake.ui.TextDisplay("\n".join(summary_lines))
        )
        
        # Container com cor
        container_kwargs = {}
        if product_color:
            container_kwargs["accent_colour"] = product_color
        
        cart_container = disnake.ui.Container(*container_components, **container_kwargs)
        
        # Botões de ação (Aplicar Cupom e Continuar)
        action_buttons = []
        
        # Botão de aplicar/remover cupom
        if coupon_code:
            action_buttons.append(
                disnake.ui.Button(
                    label="Remover Cupom",
                    emoji=emoji.delete,
                    style=disnake.ButtonStyle.secondary,
                    custom_id=f"cart_remove_coupon:{thread.id}"
                )
            )
        else:
            action_buttons.append(
                disnake.ui.Button(
                    label="Aplicar Cupom",
                    emoji=emoji.coupon if hasattr(emoji, "coupon") else "�",
                    style=disnake.ButtonStyle.secondary,
                    custom_id=f"cart_apply_coupon:{thread.id}"
                )
            )
        
        # Botão de continuar
        action_buttons.append(
            disnake.ui.Button(
                label="Continuar com o Carrinho",
                emoji=emoji.arrow,
                style=disnake.ButtonStyle.success,
                custom_id=f"cart_continue:{thread.id}"
            )
        )
        
        # Montar lista de componentes
        components_to_send = [cart_container, disnake.ui.ActionRow(*action_buttons)]
        
        # Enviar mensagem
        try:
            msg = await thread.send(
                components=components_to_send,
                flags=disnake.MessageFlags(is_components_v2=True)
            )
            return msg
        except Exception as e:
            print(f"❌ [CART] Erro ao enviar mensagem do carrinho: {e}")
            import traceback
            traceback.print_exc()
            raise
    else:
        # Modo Embed
        embed_color = product_color if product_color else disnake.Color.blue()
        embed = disnake.Embed(
            title=f"{emoji.cart} Carrinho de Compras",
            color=embed_color
        )
        
        # Adicionar cada produto
        for idx, item in enumerate(items):
            product = products.get(item.get("product_id"))
            if not product:
                continue
            
            product_name = product.get("name", "Produto")
            campos = product.get("campos", {})
            campo = campos.get(item.get("campo_id"))
            campo_name = campo.get("name", "") if campo else "Campo"
            quantity = item.get("quantity", 1)
            price_per_unit = item.get("price_per_unit", 0)
            item_total = item.get("item_total", 0)
            
            # Formatar preços
            price_str = f"R$ {price_per_unit:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            total_str = f"R$ {item_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
            embed.add_field(
                name=f"{emoji.bag} {product_name} (x{quantity})",
                value=f"Campo: `{campo_name}`\nUnitário: `{price_str}`\nTotal: `{total_str}`",
                inline=False
            )
        
        # Cashback (acima do subtotal)
        if cashback_amount > 0:
            cashback_str = f"R$ {cashback_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            embed.add_field(
                name=f"{emoji.bank if hasattr(emoji, 'bank') else '🏦'} Cashback",
                value=f"`+{cashback_str}`",
                inline=False
            )
        
        # Subtotal
        subtotal_str = f"R$ {total_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        embed.add_field(
            name=f"{emoji.dollar} Subtotal",
            value=f"`{subtotal_str}`",
            inline=False
        )
        
        # Desconto (se houver)
        if discount_amount > 0:
            discount_str = f"R$ {discount_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            discount_field = f"**Desconto:** `-{discount_str}`"
            if coupon_code:
                discount_field += f"\n**Cupom:** `{coupon_code}`"
            embed.add_field(
                name=f"Desconto",
                value=discount_field,
                inline=False
            )
        
        # Total final
        final_str = f"R$ {final_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        embed.add_field(
            name=f"{emoji.dollar} Total",
            value=f"`{final_str}`",
            inline=False
        )
        
        # Saldo aplicado (se houver)
        if balance_applied > 0:
            balance_str = f"R$ {balance_applied:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            embed.add_field(
                name=f"{emoji.wallet} Saldo Usado",
                value=f"`-{balance_str}`",
                inline=False
            )
        
        # Método de pagamento atual
        method_names = {
            "pix": "PIX",
            "card": "Cartão de Crédito",
            "crypto": "Criptomoeda",
        }
        payment_display = method_names.get(payment_method, payment_method.upper())
        embed.add_field(
            name=f"{emoji.card} Forma de Pagamento",
            value=f"`{payment_display}`",
            inline=False
        )
        
        embed.timestamp = datetime.utcnow()
        
        # Botões para cada item + ações
        components = []
        
        # Criar botões para editar/remover cada item
        for idx, item in enumerate(items):
            components.append(
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Editar Quantidade",
                        emoji=emoji.edit,
                        style=disnake.ButtonStyle.grey,
                        custom_id=f"cart_edit_quantity:{thread.id}:{idx}"
                    ),
                    disnake.ui.Button(
                        label="Remover",
                        emoji=emoji.delete,
                        style=disnake.ButtonStyle.danger,
                        custom_id=f"cart_remove_item:{thread.id}:{idx}"
                    )
                )
            )
        
        # Botões de ação (cupom, forma de pagamento e continuar)
        action_row = []
        
        # Botão de aplicar cupom
        action_row.append(
            disnake.ui.Button(
                label="Aplicar Cupom" if not coupon_code else "Alterar Cupom",
                emoji=emoji.coupon if hasattr(emoji, 'coupon') else "🎫",
                style=disnake.ButtonStyle.grey,
                custom_id=f"cart_apply_coupon:{thread.id}"
            )
        )
        
        # Botão de remover cupom (se houver cupom aplicado)
        if coupon_code:
            action_row.append(
                disnake.ui.Button(
                    label="Remover Cupom",
                    emoji=emoji.delete,
                    style=disnake.ButtonStyle.red,
                    custom_id=f"cart_remove_coupon:{thread.id}"
                )
            )
        
        # Botão para alterar forma de pagamento (somente se houver mais de um método disponível)
        if len(available_payment_keys) > 1:
            action_row.append(
                disnake.ui.Button(
                    label="Forma de Pagamento",
                    emoji=emoji.card if hasattr(emoji, 'card') else None,
                    style=disnake.ButtonStyle.grey,
                    custom_id=f"cart_change_payment:{thread.id}"
                )
            )
        
        # Botão de usar saldo (se sistema habilitado)
        if balance_info.get("enabled"):
            if balance_applied > 0:
                action_row.append(
                    disnake.ui.Button(
                        label="Remover Saldo",
                        emoji=emoji.wrong if hasattr(emoji, "wrong") else None,
                        style=disnake.ButtonStyle.danger,
                        custom_id=f"cart_remove_balance:{thread.id}"
                    )
                )
            elif balance_info.get("can_apply"):
                user_balance = balance_info.get("user_balance", 0)
                action_row.append(
                    disnake.ui.Button(
                        label=f"Usar Saldo (R$ {user_balance:.2f})",
                        emoji=emoji.wallet if hasattr(emoji, "wallet") else None,
                        style=disnake.ButtonStyle.blurple,
                        custom_id=f"cart_apply_balance:{thread.id}"
                    )
                )
        
        # Botão de continuar
        action_row.append(
            disnake.ui.Button(
                label="Continuar com o Carrinho",
                emoji=emoji.arrow,
                style=disnake.ButtonStyle.green,
                custom_id=f"cart_continue:{thread.id}"
            )
        )
        
        components.append(disnake.ui.ActionRow(*action_row))
        
        msg = await thread.send(embed=embed, components=components)
        return msg


async def _add_item_to_cart(cart_id: str, product_id: str, campo_id: str, quantity: int, price: float, loja_data_cache: Optional[Dict] = None) -> Dict[str, Any]:
    """Adiciona item a carrinho existente"""
    # Usar cache se fornecido, senão carregar do banco
    if loja_data_cache is None:
        loja_data = db.get_document("loja_data")
    else:
        loja_data = loja_data_cache
    cart = loja_data.get("carts", {}).get(cart_id)
    
    if not cart:
        return None

    ensure_cart_order_id(cart, loja_data.get("carts", {}))
    
    # Migrar se necessário
    cart = _migrate_cart_to_items(cart)
    
    # Verificar estoque ANTES de adicionar ao carrinho
    products = db.get_document("loja_products")
    product = products.get(product_id, {})
    if not product:
        return None
    
    campos = product.get("campos", {})
    campo = campos.get(campo_id, {})
    if not campo:
        return None
    
    info = product.get("info", {})
    delivery_type = info.get("delivery_type", "automatic")
    
    # Verificar se é estoque infinito
    infinite_stock = campo.get("infinite_stock", {})
    is_infinite = infinite_stock.get("enabled", False)
    
    if not is_infinite:
        # Verificar estoque disponível
        stock_count = StockManager.get_available_stock(product_id, campo_id)
        
        # Calcular quantidade total já no carrinho (excluindo o item que será adicionado/modificado)
        items = cart.get("items", [])
        total_quantity_in_cart = sum(
            it.get("quantity", 0) for it in items
            if it.get("product_id") == product_id and it.get("campo_id") == campo_id
        )
        
        # Estoque disponível considerando itens já no carrinho
        available_stock = stock_count - total_quantity_in_cart
        
        # Se for entrega automática e não houver estoque suficiente, não adicionar
        if delivery_type == "automatic" and available_stock < quantity:
            return None
        
        # Se for aumentar quantidade de item existente, verificar se a nova quantidade total não excede estoque
        if total_quantity_in_cart > 0:
            new_total_quantity = total_quantity_in_cart + quantity
            if delivery_type == "automatic" and new_total_quantity > stock_count:
                return None
    
    # Verificar se item já existe (mesmo produto e campo)
    items = cart.get("items", [])
    item_found = False
    for item in items:
        if item.get("product_id") == product_id and item.get("campo_id") == campo_id:
            # Aumentar quantidade
            item["quantity"] = item.get("quantity", 1) + quantity
            item["item_total"] = item["quantity"] * item.get("price_per_unit", price)
            item_found = True
            break
    
    if not item_found:
        # Adicionar novo item
        new_item = {
            "product_id": product_id,
            "campo_id": campo_id,
            "quantity": quantity,
            "price_per_unit": price,
            "item_total": price * quantity
        }
        items.append(new_item)
    
    cart["items"] = items
    cart["updated_at"] = int(datetime.utcnow().timestamp())
    
    # Recalcular total
    cart["total_price"] = sum(item.get("item_total", 0) for item in items)
    
    loja_data["carts"][cart_id] = cart
    db.save_document("loja_data", loja_data)
    
    return cart


async def create_checkout(
    inter: disnake.ModalInteraction,
    product_id: str,
    campo_id: Optional[str],
    quantity: int,
    payment_method: str,
    coupon_code: Optional[str] = None,
    loading_msg: Optional[disnake.Message] = None
):
    """
    Cria um checkout completo com tópico privado e pagamento.
    IMPORTANTE: Todas as validações pesadas (manutenção, horário, OAuth2, estoque) 
    devem ser feitas ANTES de chamar esta função.
    
    Args:
        loading_msg: Mensagem de loading opcional para editar ao invés de criar nova mensagem
    """
    
    # Carregar dados do produto (validação básica apenas)
    products = db.get_document("loja_products")
    product = products.get(product_id)
    
    if not product:
        if inter.response.is_done():
            await inter.followup.send(
                f"{emoji.wrong if hasattr(emoji, 'error') else '❌'} Produto não encontrado!",
                ephemeral=True
            )
        else:
            await inter.response.send_message(
                f"{emoji.wrong if hasattr(emoji, 'error') else '❌'} Produto não encontrado!",
                ephemeral=True
            )
        return
    
    product_name = product.get("name", "Produto")
    campos = product.get("campos", {})
    
    # Se tem campo específico, validar
    if campo_id and campo_id != "none":
        campo = campos.get(campo_id)
        if not campo:
            if inter.response.is_done():
                await inter.followup.send(
                    f"{emoji.wrong if hasattr(emoji, 'error') else '❌'} Campo não encontrado!",
                    ephemeral=True
                )
            else:
                await inter.response.send_message(
                    f"{emoji.wrong if hasattr(emoji, 'error') else '❌'} Campo não encontrado!",
                    ephemeral=True
                )
            return
        campo_name = campo.get("name", "")
        price = campo.get("price", 0)
    else:
        # Se não tem campo específico, pegar o primeiro disponível
        if not campos:
            if inter.response.is_done():
                await inter.followup.send(
                    f"{emoji.wrong if hasattr(emoji, 'error') else '❌'} Produto sem campos disponíveis!",
                    ephemeral=True
                )
            else:
                await inter.response.send_message(
                    f"{emoji.wrong if hasattr(emoji, 'error') else '❌'} Produto sem campos disponíveis!",
                    ephemeral=True
                )
            return
        campo_id = list(campos.keys())[0]
        campo = campos[campo_id]
        campo_name = campo.get("name", "")
        price = campo.get("price", 0)
    
    # Calcular valor total
    total_price = price * quantity

    # Verificar modo de exibição
    mode = db.get_document("custom_mode").get("mode", "embed")
    
    # Obter tipo de entrega do produto
    info = product.get("info") or {}
    delivery_type = info.get("delivery_type", "automatic")
    
    # CRIAR E SALVAR CARRINHO ANTES DE MOSTRAR QUALQUER MENSAGEM
    # Carregar loja_data uma vez e reutilizar
    loja_data = db.get_document("loja_data")
    
    # VERIFICAÇÃO CRÍTICA: Buscar carrinho existente usando cache do banco
    bot_ref = inter.bot if hasattr(inter, 'bot') else None
    existing_cart_id, existing_cart = await _find_user_open_cart(
        inter.author.id, 
        inter.guild.id, 
        delivery_type, 
        bot=bot_ref, 
        guild=inter.guild,
        loja_data_cache=loja_data  # Passar cache para evitar múltiplas leituras
    )
    
    try:
        from functions.antifraud import check_purchase

        allowed, reason = await check_purchase(
            inter,
            amount=total_price,
            action="criar_carrinho",
            ignore_cart_id=existing_cart_id if existing_cart_id and existing_cart else None,
        )
        if not allowed:
            if loading_msg:
                try:
                    await loading_msg.edit(content=reason, components=[])
                except Exception:
                    await inter.followup.send(reason, ephemeral=True)
            elif inter.response.is_done():
                await inter.followup.send(reason, ephemeral=True)
            else:
                await inter.response.send_message(reason, ephemeral=True)
            return
    except Exception as exc:
        print(f"[AntiFraude] Falha ao validar carrinho: {exc}")

    if existing_cart_id and existing_cart:
        
        # Verificar se a thread ainda existe antes de adicionar ao carrinho
        thread_id = existing_cart.get("thread_id")
        thread = None
        if thread_id:
            try:
                thread = inter.guild.get_thread(thread_id)
                if not thread:
                    # Tentar buscar a thread (pode estar em cache)
                    try:
                        thread = await inter.guild.fetch_channel(thread_id)
                        if not isinstance(thread, disnake.Thread):
                            thread = None
                    except:
                        thread = None
            except:
                thread = None
        
        if not thread:
            # Thread não existe mais - deletar carrinho antigo e criar novo
            if existing_cart_id in loja_data.get("carts", {}):
                del loja_data["carts"][existing_cart_id]
                db.save_document("loja_data", loja_data)
            # Continuar para criar novo carrinho
        else:
            # Thread existe - adicionar produto ao carrinho existente
            updated_cart = await _add_item_to_cart(existing_cart_id, product_id, campo_id, quantity, price, loja_data_cache=loja_data)
            
            if not updated_cart:
                # Não conseguiu adicionar (provavelmente falta de estoque)
                # Verificar estoque para dar mensagem apropriada
                stock_count = StockManager.get_available_stock(product_id, campo_id)
                is_infinite = stock_count == 999999
                
                if delivery_type == "automatic" and not is_infinite and stock_count <= 0:
                    # Sem estoque disponível - mostrar botão de notificação
                    notify_emoji = ensure_emoji(emoji.warn)
                    notify_button = disnake.ui.Button(
                        emoji=notify_emoji,
                        label="Receber notificação ao repor estoque",
                        style=disnake.ButtonStyle.grey,
                        custom_id=f"notify_stock:{product_id}:{campo_id}"
                    )
                    
                    if loading_msg:
                        try:
                            await loading_msg.edit(
                                content=f"{emoji.wrong} Sem estoque disponível para este item.",
                                components=[disnake.ui.ActionRow(notify_button)]
                            )
                        except:
                            try:
                                await inter.followup.send(
                                    content=f"{emoji.wrong} Sem estoque disponível para este item.",
                                    components=[disnake.ui.ActionRow(notify_button)],
                                    ephemeral=True
                                )
                            except:
                                pass
                    else:
                        try:
                            await inter.edit_original_message(
                                content=f"{emoji.wrong} Sem estoque disponível para este item.",
                                embed=None,
                                components=[disnake.ui.ActionRow(notify_button)]
                            )
                        except (disnake.NotFound, disnake.HTTPException):
                            try:
                                await inter.followup.send(
                                    content=f"{emoji.wrong} Sem estoque disponível para este item.",
                                    components=[disnake.ui.ActionRow(notify_button)],
                                    ephemeral=True
                                )
                            except:
                                pass
                    return
                else:
                    # Estoque insuficiente para a quantidade solicitada
                    items = existing_cart.get("items", [])
                    total_quantity_in_cart = sum(
                        it.get("quantity", 0) for it in items
                        if it.get("product_id") == product_id and it.get("campo_id") == campo_id
                    )
                    available_stock = stock_count - total_quantity_in_cart
                    
                    if loading_msg:
                        try:
                            await loading_msg.edit(
                                content=f"{emoji.wrong} Estoque insuficiente. Disponível: `{available_stock}`, solicitado: `{quantity}`.",
                                components=[]
                            )
                        except:
                            pass
                    else:
                        try:
                            await inter.edit_original_message(
                                content=f"{emoji.wrong} Estoque insuficiente. Disponível: `{available_stock}`, solicitado: `{quantity}`.",
                                embed=None,
                                components=[]
                            )
                        except (disnake.NotFound, disnake.HTTPException):
                            try:
                                await inter.followup.send(
                                    content=f"{emoji.wrong} Estoque insuficiente. Disponível: `{available_stock}`, solicitado: `{quantity}`.",
                                    ephemeral=True
                                )
                            except:
                                pass
                    return
            
            if updated_cart:
                # Atualizar delivery_type do carrinho baseado nos produtos
                # Reutilizar products já carregado anteriormente se disponível
                products = db.get_document("loja_products")
                items = updated_cart.get("items", [])
                delivery_types = set()
                for item in items:
                    prod = products.get(item.get("product_id"), {})
                    info = prod.get("info") or {}
                    item_delivery = info.get("delivery_type", "automatic")
                    delivery_types.add(item_delivery)
                
                # Se tem tipos mistos, marcar como "mixed", senão usar o tipo único
                if len(delivery_types) > 1:
                    updated_cart["delivery_type"] = "mixed"
                else:
                    updated_cart["delivery_type"] = list(delivery_types)[0] if delivery_types else "automatic"
                
                # Salvar carrinho atualizado (reutilizar loja_data)
                loja_data["carts"][existing_cart_id] = updated_cart
                db.save_document("loja_data", loja_data)
                
                # Atualizar mensagem do carrinho
                try:
                    cart_message_id = existing_cart.get("cart_message_id")
                    if cart_message_id:
                        try:
                            cart_msg = await thread.fetch_message(cart_message_id)
                            # Reconstruir mensagem do carrinho
                            new_cart_msg = await _build_cart_message(updated_cart, thread, mode)
                            # Editar mensagem existente ao invés de deletar
                            await cart_msg.edit(
                                content=new_cart_msg.content if hasattr(new_cart_msg, 'content') else None,
                                embed=new_cart_msg.embeds[0] if new_cart_msg.embeds else None,
                                components=new_cart_msg.components if hasattr(new_cart_msg, 'components') else None,
                                view=new_cart_msg.view if hasattr(new_cart_msg, 'view') else None
                            )
                            # Não precisa atualizar o ID pois é a mesma mensagem
                        except Exception as e:
                            # Se não conseguir editar, criar nova mensagem
                            try:
                                new_cart_msg = await _build_cart_message(updated_cart, thread, mode)
                                loja_data["carts"][existing_cart_id]["cart_message_id"] = new_cart_msg.id
                                db.save_document("loja_data", loja_data)
                            except Exception as e2:
                                pass
                    else:
                        # Criar mensagem do carrinho
                        try:
                            new_cart_msg = await _build_cart_message(updated_cart, thread, mode)
                            loja_data["carts"][existing_cart_id]["cart_message_id"] = new_cart_msg.id
                            db.save_document("loja_data", loja_data)
                        except Exception as e:
                            pass
                    
                    # Enviar mensagem marcando o usuário e depois apagar
                    try:
                        mention_msg = await thread.send(f"{inter.author.mention} Produto adicionado ao carrinho!")
                        await asyncio.sleep(3)
                        try:
                            await mention_msg.delete()
                        except:
                            pass
                    except Exception as e:
                        pass
                    
                    # Editar mensagem de loading se existir, senão usar método padrão
                    if loading_msg:
                        try:
                            await loading_msg.edit(
                                content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                components=[]
                            )
                        except:
                            # Se não conseguir editar loading_msg, tentar método padrão
                            try:
                                await inter.edit_original_message(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                    embed=None,
                                    components=[]
                                )
                            except (disnake.NotFound, disnake.HTTPException):
                                try:
                                    await inter.followup.send(
                                        content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                        ephemeral=True
                                    )
                                except:
                                    pass
                            except Exception:
                                pass
                    else:
                        try:
                            await inter.edit_original_message(
                                content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                embed=None,
                                components=[]
                            )
                        except (disnake.NotFound, disnake.HTTPException):
                            # Enviar mensagem de sucesso via followup
                            try:
                                await inter.followup.send(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                    ephemeral=True
                                )
                            except:
                                pass
                        except Exception:
                            pass
                    
                    return
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    # Mesmo com erro, retornar pois o produto já foi adicionado ao carrinho
                    if loading_msg:
                        try:
                            await loading_msg.edit(
                                content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                components=[]
                            )
                        except:
                            try:
                                await inter.edit_original_message(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                    embed=None,
                                    components=[]
                                )
                            except (disnake.NotFound, disnake.HTTPException):
                                try:
                                    await inter.followup.send(
                                        content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                        ephemeral=True
                                    )
                                except:
                                    pass
                            except:
                                pass
                    else:
                        try:
                            await inter.edit_original_message(
                                content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                embed=None,
                                components=[]
                            )
                        except (disnake.NotFound, disnake.HTTPException):
                            # Enviar mensagem de sucesso via followup
                            try:
                                await inter.followup.send(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                    ephemeral=True
                                )
                            except:
                                pass
                        except:
                            pass
                    return
            else:
                # Se não conseguiu adicionar, continuar para criar novo carrinho
                pass
    else:
        pass
    
    # SEGUNDA VERIFICAÇÃO CRÍTICA: Verificar novamente se não foi criado um carrinho entre a primeira verificação e agora
    # (evitar condição de corrida - duas requisições simultâneas)
    # Recarregar loja_data para pegar atualizações recentes (sem sleep para melhor performance)
    loja_data = db.get_document("loja_data")
    bot_ref = inter.bot if hasattr(inter, 'bot') else None
    existing_cart_id_check, existing_cart_check = await _find_user_open_cart(
        inter.author.id, 
        inter.guild.id, 
        delivery_type, 
        bot=bot_ref, 
        guild=inter.guild,
        loja_data_cache=loja_data  # Usar cache atualizado
    )
    
    if existing_cart_id_check and existing_cart_check:
        # Adicionar produto ao carrinho existente
        updated_cart = await _add_item_to_cart(existing_cart_id_check, product_id, campo_id, quantity, price, loja_data_cache=loja_data)
        
        if not updated_cart:
            # Não conseguiu adicionar (provavelmente falta de estoque)
            # Verificar estoque para dar mensagem apropriada
            stock_count = StockManager.get_available_stock(product_id, campo_id)
            is_infinite = stock_count == 999999
            
            if delivery_type == "automatic" and not is_infinite and stock_count <= 0:
                # Sem estoque disponível - mostrar botão de notificação
                notify_emoji = ensure_emoji(emoji.warn)
                notify_button = disnake.ui.Button(
                    emoji=notify_emoji,
                    label="Receber notificação ao repor estoque",
                    style=disnake.ButtonStyle.grey,
                    custom_id=f"notify_stock:{product_id}:{campo_id}"
                )
                
                if loading_msg:
                    try:
                        await loading_msg.edit(
                            content=f"{emoji.wrong} Sem estoque disponível para este item.",
                            components=[disnake.ui.ActionRow(notify_button)]
                        )
                    except:
                        try:
                            await inter.followup.send(
                                content=f"{emoji.wrong} Sem estoque disponível para este item.",
                                components=[disnake.ui.ActionRow(notify_button)],
                                ephemeral=True
                            )
                        except:
                            pass
                else:
                    try:
                        await inter.edit_original_message(
                            content=f"{emoji.wrong} Sem estoque disponível para este item.",
                            embed=None,
                            components=[disnake.ui.ActionRow(notify_button)]
                        )
                    except (disnake.NotFound, disnake.HTTPException):
                        try:
                            await inter.followup.send(
                                content=f"{emoji.wrong} Sem estoque disponível para este item.",
                                components=[disnake.ui.ActionRow(notify_button)],
                                ephemeral=True
                            )
                        except:
                            pass
                return
            else:
                # Estoque insuficiente para a quantidade solicitada
                items = existing_cart_check.get("items", [])
                total_quantity_in_cart = sum(
                    it.get("quantity", 0) for it in items
                    if it.get("product_id") == product_id and it.get("campo_id") == campo_id
                )
                available_stock = stock_count - total_quantity_in_cart
                
                if loading_msg:
                    try:
                        await loading_msg.edit(
                            content=f"{emoji.wrong} Estoque insuficiente. Disponível: `{available_stock}`, solicitado: `{quantity}`.",
                            components=[]
                        )
                    except:
                        pass
                else:
                    try:
                        await inter.edit_original_message(
                            content=f"{emoji.wrong} Estoque insuficiente. Disponível: `{available_stock}`, solicitado: `{quantity}`.",
                            embed=None,
                            components=[]
                        )
                    except (disnake.NotFound, disnake.HTTPException):
                        try:
                            await inter.followup.send(
                                content=f"{emoji.wrong} Estoque insuficiente. Disponível: `{available_stock}`, solicitado: `{quantity}`.",
                                ephemeral=True
                            )
                        except:
                            pass
                return
        
        if updated_cart:
            # Atualizar delivery_type do carrinho baseado nos produtos
            products = db.get_document("loja_products")
            items = updated_cart.get("items", [])
            delivery_types = set()
            for item in items:
                prod = products.get(item.get("product_id"), {})
                info = prod.get("info") or {}
                item_delivery = info.get("delivery_type", "automatic")
                delivery_types.add(item_delivery)
            
            # Se tem tipos mistos, marcar como "mixed", senão usar o tipo único
            if len(delivery_types) > 1:
                updated_cart["delivery_type"] = "mixed"
            else:
                updated_cart["delivery_type"] = list(delivery_types)[0] if delivery_types else "automatic"
            
            # Salvar carrinho atualizado (reutilizar loja_data)
            loja_data["carts"][existing_cart_id_check] = updated_cart
            db.save_document("loja_data", loja_data)
            
            # Buscar thread
            try:
                thread_id = existing_cart_check.get("thread_id")
                thread = inter.guild.get_thread(thread_id)
                
                if thread:
                    # Atualizar mensagem do carrinho
                    cart_message_id = existing_cart_check.get("cart_message_id")
                    if cart_message_id:
                        try:
                            cart_msg = await thread.fetch_message(cart_message_id)
                            new_cart_msg = await _build_cart_message(updated_cart, thread, mode)
                            # Editar mensagem existente ao invés de deletar
                            await cart_msg.edit(
                                content=new_cart_msg.content if hasattr(new_cart_msg, 'content') else None,
                                embed=new_cart_msg.embeds[0] if new_cart_msg.embeds else None,
                                components=new_cart_msg.components if hasattr(new_cart_msg, 'components') else None,
                                view=new_cart_msg.view if hasattr(new_cart_msg, 'view') else None
                            )
                            # Não precisa atualizar o ID pois é a mesma mensagem
                        except:
                            try:
                                new_cart_msg = await _build_cart_message(updated_cart, thread, mode)
                                loja_data["carts"][existing_cart_id_check]["cart_message_id"] = new_cart_msg.id
                                db.save_document("loja_data", loja_data)
                            except:
                                pass
                    else:
                        try:
                            new_cart_msg = await _build_cart_message(updated_cart, thread, mode)
                            loja_data["carts"][existing_cart_id_check]["cart_message_id"] = new_cart_msg.id
                            db.save_document("loja_data", loja_data)
                        except:
                            pass
                    
                    try:
                        mention_msg = await thread.send(f"{inter.author.mention} Produto adicionado ao carrinho!")
                        await asyncio.sleep(3)
                        try:
                            await mention_msg.delete()
                        except:
                            pass
                    except:
                        pass
                    
                    # Editar mensagem de loading se existir
                    if loading_msg:
                        try:
                            await loading_msg.edit(
                                content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                components=[]
                            )
                        except:
                            try:
                                await inter.edit_original_message(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                    embed=None,
                                    components=[]
                                )
                            except (disnake.NotFound, disnake.HTTPException):
                                try:
                                    await inter.followup.send(
                                        content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                        ephemeral=True
                                    )
                                except:
                                    pass
                            except:
                                pass
                    else:
                        try:
                            await inter.edit_original_message(
                                content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                embed=None,
                                components=[]
                            )
                        except (disnake.NotFound, disnake.HTTPException):
                            # Enviar mensagem de sucesso via followup
                            try:
                                await inter.followup.send(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                                    ephemeral=True
                                )
                            except:
                                pass
                        except:
                            pass
                    
                    return
                else:
                    # Thread não encontrada, mas produto foi adicionado ao carrinho
                    if loading_msg:
                        try:
                            await loading_msg.edit(
                                content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                components=[]
                            )
                        except:
                            try:
                                await inter.edit_original_message(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                    embed=None,
                                    components=[]
                                )
                            except (disnake.NotFound, disnake.HTTPException):
                                try:
                                    await inter.followup.send(
                                        content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                        ephemeral=True
                                    )
                                except:
                                    pass
                            except:
                                pass
                    else:
                        try:
                            await inter.edit_original_message(
                                content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                embed=None,
                                components=[]
                            )
                        except (disnake.NotFound, disnake.HTTPException):
                            # Enviar mensagem de sucesso via followup
                            try:
                                await inter.followup.send(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                    ephemeral=True
                                )
                            except:
                                pass
                        except:
                            pass
                    return
            except Exception as e:
                if loading_msg:
                    try:
                        await loading_msg.edit(
                            content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                            components=[]
                        )
                    except:
                        try:
                            await inter.edit_original_message(
                                content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                embed=None,
                                components=[]
                            )
                        except (disnake.NotFound, disnake.HTTPException):
                            try:
                                await inter.followup.send(
                                    content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                    ephemeral=True
                                )
                            except:
                                pass
                        except:
                            pass
                else:
                    try:
                        await inter.edit_original_message(
                            content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                            embed=None,
                            components=[]
                        )
                    except (disnake.NotFound, disnake.HTTPException):
                        # Enviar mensagem de sucesso via followup
                        try:
                            await inter.followup.send(
                                content=f"{emoji.correct} Produto adicionado ao carrinho existente!",
                                ephemeral=True
                            )
                        except:
                            pass
                    except:
                        pass
                return
        else:
            # Se não conseguiu adicionar, continuar para criar novo carrinho
            pass
    
    try:
        # Obter cargo admin
        cargos_data = db.get_document("cargos")
        cargo_admin_id = cargos_data.get("cargo_admin")
        
        # Nome do tópico - sempre começa com 💱 (pendente)
        # delivery_type já foi obtido acima
        
        # Garantir que product_name não está vazio e limitar tamanho
        safe_product_name = product_name.strip() if product_name else "Produto"
        safe_user_name = inter.author.name[:30] if inter.author.name else "User"
        
        # Sempre começa com 💱 (carrinho pendente)
        thread_name = f"💱・{safe_product_name}・{safe_user_name}"
        
        # Garantir que o nome do tópico tem entre 1 e 100 caracteres
        thread_name = thread_name[:100] if len(thread_name) > 100 else thread_name
        if not thread_name or len(thread_name) < 1:
            thread_name = f"💱・carrinho・{safe_user_name}"
        
        # Criar thread no canal atual
        thread = await inter.channel.create_thread(
            name=thread_name,
            auto_archive_duration=60,  # 1 hora
            type=disnake.ChannelType.private_thread,
            invitable=False
        )
        
        # Pequena pausa para garantir que a thread esteja disponível no cache
        await asyncio.sleep(0.2)
        
    except Exception as e:
        # Mensagem administrativa - sempre content simples
        try:
            await inter.edit_original_message(
                content=f"{emoji.wrong if hasattr(emoji, 'error') else '❌'} Erro ao criar tópico: {e}",
                embed=None,
                components=[]
            )
        except (disnake.NotFound, disnake.HTTPException):
            # Mensagem não existe mais ou não pode ser editada, enviar nova mensagem
            try:
                await inter.followup.send(
                    content=f"{emoji.wrong if hasattr(emoji, 'error') else '❌'} Erro ao criar tópico: {e}",
                    ephemeral=True
                )
            except:
                pass
        return
    
    # Criar estrutura inicial do carrinho com items
    cart_items = [{
        "product_id": product_id,
        "campo_id": campo_id,
        "quantity": quantity,
        "price_per_unit": price,
        "item_total": price * quantity
    }]
    
    
    # Salvar dados do carrinho ANTES de enviar mensagem (para evitar race condition)
    cart_id = str(thread.id)
    timestamp = int(datetime.utcnow().timestamp())
    
    # Reutilizar loja_data já carregado anteriormente
    if "carts" not in loja_data:
        loja_data["carts"] = {}
    
    # Criar estrutura inicial do carrinho (cart_message_id será atualizado depois)
    order_id = ensure_cart_order_id({}, loja_data.get("carts", {}))
    cart_data = {
        "cart_id": cart_id,
        "order_id": order_id,
        "thread_id": thread.id,
        "cart_message_id": None,  # Será atualizado após criar a mensagem
        "channel_id": inter.channel.id,
        "guild_id": inter.guild.id,
        "user_id": inter.author.id,
        "items": cart_items,  # Nova estrutura com array de items
        "total_price": sum(item.get("item_total", 0) for item in cart_items),  # Total sem desconto ainda
        "discount_amount": 0,  # Desconto será aplicado quando continuar
        "coupon_code": None,  # Cupom será aplicado quando continuar
        "coupon_type": None,
        "payment_method": payment_method,  # Método escolhido, mas pagamento ainda não criado
        "payment_data": None,  # Será criado quando clicar em continuar
        "status": "cart",  # Status "cart" = carrinho ainda não foi para pagamento
        "delivery_type": delivery_type,  # Salvar tipo de entrega do carrinho
        "created_at": timestamp,
        "updated_at": timestamp,
        "is_free_purchase": False
    }
    
    
    loja_data["carts"][cart_id] = cart_data
    db.save_document("loja_data", loja_data)
    
    # Enviar mensagem do carrinho (sem pagamento ainda)
    cart_msg = await _build_cart_message(
        {
            "items": cart_items,
            "user_id": inter.author.id,
            "guild_id": inter.guild.id,
            "payment_method": payment_method,
        },
        thread,
        mode
    )
    
    # Atualizar cart_message_id no carrinho salvo (reutilizar loja_data)
    if cart_id in loja_data.get("carts", {}):
        loja_data["carts"][cart_id]["cart_message_id"] = cart_msg.id
        db.save_document("loja_data", loja_data)
    
    # Enviar mensagem marcando o usuário e cargo admin, depois apagar
    # Carregar cargos apenas uma vez (já foi carregado antes, mas reutilizar se possível)
    cargos_data = db.get_document("cargos") or {}
    cargo_admin_id = cargos_data.get("cargo_admin")
    admin_mention = ""
    if cargo_admin_id:
        try:
            role = inter.guild.get_role(int(cargo_admin_id))
            if role:
                admin_mention = f" {role.mention}"
        except Exception:
            pass
    
    mention_msg = await thread.send(f"{inter.author.mention}{admin_mention} Carrinho criado!")
    await asyncio.sleep(3)
    try:
        await mention_msg.delete()
    except:
        pass
    
    # Atualizar mensagem de loading se existir, senão usar método padrão
    if loading_msg:
        try:
            await loading_msg.edit(
                content=f"{emoji.correct} Carrinho criado! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                components=[]
            )
        except:
            # Se não conseguir editar loading_msg, tentar método padrão
            try:
                await inter.edit_original_message(
                    content=f"{emoji.correct} Carrinho criado! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                    embed=None,
                    components=[]
                )
            except (disnake.NotFound, disnake.HTTPException):
                try:
                    await inter.followup.send(
                        content=f"{emoji.correct} Carrinho criado! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                        ephemeral=True
                    )
                except:
                    pass
            except:
                pass
    else:
        # Atualizar mensagem original (se existir)
        try:
            await inter.edit_original_message(
                content=f"{emoji.correct} Carrinho criado! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                embed=None,
                components=[]
            )
        except (disnake.NotFound, disnake.HTTPException):
            # Mensagem original não existe mais ou não pode ser editada
            # Enviar mensagem de sucesso via followup
            try:
                await inter.followup.send(
                    content=f"{emoji.correct} Carrinho criado! Acesse {thread.mention}\n{emoji.arrow} Prossiga com o pagamento ou adicione mais produtos navegando.",
                    ephemeral=True
                )
            except:
                pass
    
    # Enviar DM informando criação do carrinho
    try:
        cart_url = f"https://discord.com/channels/{inter.guild.id}/{thread.id}"
        
        if delivery_type == "manual":
            delivery_text = f"Entrega manual. Ela será realizada no carrinho do servidor."
        else:
            delivery_text = "Entrega automática. Assim que o pagamento for aprovado, você receberá os itens nesta conversa."
        
        if mode == "embed":
            dm_embed = disnake.Embed(
                title=f"Carrinho Criado",
                description=(
                    f"**Produto:** `{product_name}`\n"
                    f"**Campo:** `{campo_name}`\n"
                    f"**Quantidade:** `{quantity}`"
                ),
                color=disnake.Color.blurple()
            )
            dm_embed.add_field(
                name=f"Entrega",
                value=delivery_text,
                inline=False
            )
            await inter.author.send(
                embed=dm_embed,
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.Button(
                            label="Abrir Carrinho",
                            style=disnake.ButtonStyle.url,
                            url=cart_url
                        )
                    )
                ]
            )
        else:
            # Modo Container
            color_data = db.get_document("custom_colors") or {}
            primary_color = color_data.get("primary")
            container_kwargs = {}
            if primary_color:
                container_kwargs["accent_colour"] = disnake.Colour(int(primary_color.replace("#", ""), 16))
            
            await inter.author.send(
                components=[
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(f"# {emoji.cart}\n-# Carrinho Criado"),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(
                            f"-# **Produto:** `{product_name}`\n"
                            f"-# **Campo:** `{campo_name}`\n"
                            f"-# **Quantidade:** `{quantity}`"
                        ),
                        disnake.ui.Separator(),
                        disnake.ui.TextDisplay(f"{delivery_text}"),
                        **container_kwargs
                    ),
                    disnake.ui.ActionRow(
                        disnake.ui.Button(
                            label="Abrir Carrinho",
                            style=disnake.ButtonStyle.url,
                            url=cart_url
                        )
                    )
                ],
                flags=disnake.MessageFlags(is_components_v2=True)
            )
    except Exception:
        pass


def _sanitize_error_for_user(error_msg: str) -> str:
    """
    Remove informações técnicas de mensagens de erro para exibição ao usuário
    """
    msg = str(error_msg)
    
    # Tentar extrair mensagem de erro de JSON se existir
    try:
        json_match = re.search(r'\{[^{}]*"mensagem"[^{}]*\}', msg, re.IGNORECASE)
        if json_match:
            json_str = json_match.group(0)
            json_data = json.loads(json_str)
            if isinstance(json_data, dict) and "mensagem" in json_data:
                return json_data["mensagem"]
    except:
        pass
    
    # Tentar extrair mensagem de erro de JSON com "message"
    try:
        json_match = re.search(r'\{[^{}]*"message"[^{}]*\}', msg, re.IGNORECASE)
        if json_match:
            json_str = json_match.group(0)
            try:
                json_data = json.loads(json_str)
                if isinstance(json_data, dict):
                    if "message" in json_data:
                        msg_data = json_data["message"]
                        if isinstance(msg_data, dict) and "mensagem" in msg_data:
                            return msg_data["mensagem"]
                        elif isinstance(msg_data, str):
                            return msg_data
            except (json.JSONDecodeError, ValueError):
                pass
    except Exception:
        pass
    
    # Remover URLs (http://, https://)
    msg = re.sub(r'https?://[^\s]+', '', msg)
    
    # Remover rotas de API (ex: /api/v1/create-efi-payment)
    msg = re.sub(r'/api/v\d+/[^\s]+', '', msg)
    msg = re.sub(r'/api/[^\s]+', '', msg)
    
    # Remover códigos HTTP no início (ex: 500, 400)
    msg = re.sub(r'^\d+\s+', '', msg)
    
    # Remover referências a BASE_URL ou URLs específicas
    msg = re.sub(r'pay\.Lyonapplications\.com\.br[^\s]*', '', msg, flags=re.IGNORECASE)
    
    # Limpar espaços múltiplos
    msg = re.sub(r'\s+', ' ', msg)
    
    # Remover dois pontos duplos ou pontos isolados no início
    msg = re.sub(r'^:\s*', '', msg)
    msg = msg.strip()
    
    return msg


async def _create_payment(
    payment_method: str,
    amount: float,
    user: disnake.Member,
    description: str,
    cart_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cria um pagamento baseado no método escolhido"""
    
    # Validar valor mínimo
    if amount < 0.01:
        raise ValueError(f"Valor muito baixo: R$ {amount:.2f}. O valor mínimo é R$ 0,01")
    
    # Lista de provedores que estão "em breve" (não devem ser usados)
    providers_coming_soon = [
        "nubank", "inter", "bitcoin", "litecoin", "ethereum", "livepix", "promissepay"
    ]
    
    errors = []
    
    # Verificar quais provedores estão habilitados
    pagamentos = db.get_document("pagamentos") or {}
    payment_configs = db.get_document("payment_configs") or {}
    
    print(f"[_create_payment] Iniciando criação de pagamento: method={payment_method}, amount={amount}")
    print(f"[_create_payment] Pagamentos habilitados: {list(pagamentos.keys())}")
    print(f"[_create_payment] Mercado Pago habilitado: {pagamentos.get('mercado_pago')}")
    
    
    if payment_method == "pix":
        # PIX: Lyon Wallet, Mercado Pago, Efí, Pagbank, Manual, Assas Pix, PushinPay, PicPay
        
        # Tentar Lyon Wallet PIX (prioridade)
        if "Lyon_wallet" not in providers_coming_soon and _payment_provider_enabled("Lyon_wallet", pagamentos, payment_configs):
            try:
                from functions.payments.Lyon_wallet import create_Lyon_payment_from_settings
                result = await create_Lyon_payment_from_settings(
                    value=amount,
                    description=description
                )
                if result:
                    result["_provider"] = "Lyon_wallet"
                return result
            except ValueError as e:
                # Erro de configuração faltando
                error_msg = _sanitize_error_for_user(str(e))
                errors.append(f"Lyon Wallet: {error_msg}")
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"Lyon Wallet: {sanitized}")
        elif "Lyon_wallet" in providers_coming_soon:
            errors.append("Lyon Wallet: Em breve")
        else:
            errors.append("Lyon Wallet: Desabilitado")
        
        # Tentar Mercado Pago PIX
        if "mercado_pago" not in providers_coming_soon and _payment_provider_enabled("mercado_pago", pagamentos, payment_configs):
            try:
                result = await create_mp_payment_from_settings(amount)
                if result:
                    result["_provider"] = "mercado_pago"
                return result
            except ValueError as e:
                # Erro de configuração faltando
                error_msg = _sanitize_error_for_user(str(e))
                errors.append(f"Mercado Pago: {error_msg}")
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"Mercado Pago: {sanitized}")
        elif "mercado_pago" in providers_coming_soon:
            errors.append("Mercado Pago: Em breve")
        else:
            errors.append("Mercado Pago: Desabilitado")
        
        # Tentar Efí (EfiBank)
        if "efibank" not in providers_coming_soon and _payment_provider_enabled("efibank", pagamentos, payment_configs):
            try:
                # Efi Bank: Nome do usuário Discord + CPF fixo
                result = await create_efi_payment_from_settings(
                    price=amount,
                    nome_pagador=user.display_name if user else "Cliente"
                )
                if result:
                    result["_provider"] = "efibank"
                return result
            except ValueError as e:
                # Erro de configuração faltando
                error_msg = _sanitize_error_for_user(str(e))
                errors.append(f"Efí: {error_msg}")
            except Exception as e:
                # Outro erro
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"Efí: {sanitized}")
        elif "efibank" in providers_coming_soon:
            errors.append("Efí: Em breve")
        else:
            errors.append("Efí: Desabilitado")
        
        # Tentar PagBank
        if "pagbank" not in providers_coming_soon and _payment_provider_enabled("pagbank", pagamentos, payment_configs):
            try:
                from functions.payments import create_pagbank_payment_from_settings
                result = await create_pagbank_payment_from_settings(amount)
                if result:
                    result["_provider"] = "pagbank"
                return result
            except ValueError as e:
                error_msg = _sanitize_error_for_user(str(e))
                errors.append(f"PagBank: {error_msg}")
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"PagBank: {sanitized}")
        elif "pagbank" in providers_coming_soon:
            errors.append("PagBank: Em breve")
        else:
            errors.append("PagBank: Desabilitado")
        
        # Tentar Asaas PIX
        if "asaas" not in providers_coming_soon and _payment_provider_enabled("asaas", pagamentos, payment_configs):
            try:
                result = await create_asaas_pix_payment_from_settings(
                    amount,
                    customer=str(user.id),
                    description=description
                )
                if result:
                    result["_provider"] = "asaas"
                return result
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"Asaas PIX: {sanitized}")
        elif "asaas" in providers_coming_soon:
            errors.append("Asaas PIX: Em breve")
        else:
            errors.append("Asaas PIX: Desabilitado")
        
        # Tentar PushinPay
        if "pushinpay" not in providers_coming_soon and _payment_provider_enabled("pushinpay", pagamentos, payment_configs):
            try:
                from functions.payments import create_pushinpay_payment_from_settings
                result = await create_pushinpay_payment_from_settings(int(round(amount * 100)))
                if result:
                    result["_provider"] = "pushinpay"
                return result
            except ValueError as e:
                error_msg = _sanitize_error_for_user(str(e))
                errors.append(f"PushinPay: {error_msg}")
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"PushinPay: {sanitized}")
        elif "pushinpay" in providers_coming_soon:
            errors.append("PushinPay: Em breve")
        else:
            errors.append("PushinPay: Desabilitado")
        
        # Tentar PicPay
        if "picpay" not in providers_coming_soon and _payment_provider_enabled("picpay", pagamentos, payment_configs):
            try:
                from functions.payments import create_picpay_payment_from_settings
                result = await create_picpay_payment_from_settings(amount)
                if result:
                    result["_provider"] = "picpay"
                return result
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"PicPay: {sanitized}")
        elif "picpay" in providers_coming_soon:
            errors.append("PicPay: Em breve")
        else:
            errors.append("PicPay: Desabilitado")
        
        # Tentar MisticPay
        if "misticpay" not in providers_coming_soon and _payment_provider_enabled("misticpay", pagamentos, payment_configs):
            try:
                # Obter nome e documento do usuário
                payer_name = user.display_name or user.name or "Cliente"
                # Usar ID do Discord como documento temporário (ou pode ser configurado)
                payer_document = str(user.id)[:11]  # Limitar a 11 dígitos
                
                result = await create_misticpay_payment_from_settings(
                    amount=amount,
                    payer_name=payer_name,
                    payer_document=payer_document,
                    description=description
                )
                if result:
                    result["_provider"] = "misticpay"
                return result
            except ValueError as e:
                error_msg = _sanitize_error_for_user(str(e))
                errors.append(f"MisticPay: {error_msg}")
            except Exception as e:
                error_msg = str(e)
                # Verificar se é erro de IP não autorizado
                if "IP não autorizado" in error_msg or "não está na lista de permissões" in error_msg or ("IP" in error_msg and "permissões" in error_msg):
                    import re
                    ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', error_msg)
                    ip_address = ip_match.group(0) if ip_match else "seu IP"
                    sanitized = (
                        f"IP não autorizado ({ip_address}). "
                        f"Configure a verificação de 2 fatores e libere todos os IPs nas configurações do MisticPay."
                    )
                else:
                    sanitized = _sanitize_error_for_user(error_msg)
                errors.append(f"MisticPay: {sanitized}")
        elif "misticpay" in providers_coming_soon:
            errors.append("MisticPay: Em breve")
        else:
            errors.append("MisticPay: Desabilitado")

        # Tentar Nubank IMAP
        if as_bool(pagamentos.get("nubank_imap"), False) or as_bool((payment_configs.get("nubank_imap") or {}).get("enabled"), False):
            try:
                result = await create_nubank_imap_payment(
                    amount=amount,
                    cart_id=str(cart_id or user.id),
                    description=description,
                )
                if result:
                    result["_provider"] = "nubank_imap"
                return result
            except Exception as e:
                errors.append(f"Nubank IMAP: {_sanitize_error_for_user(str(e))}")
        else:
            errors.append("Nubank IMAP: Desabilitado")

        # Tentar PicPay IMAP
        if as_bool(pagamentos.get("picpay_imap"), False) or as_bool((payment_configs.get("picpay_imap") or {}).get("enabled"), False):
            try:
                result = await create_picpay_imap_payment_from_settings(
                    amount=amount,
                    cart_id=str(cart_id or user.id),
                    description=description,
                )
                if result:
                    result["_provider"] = "picpay_imap"
                return result
            except Exception as e:
                errors.append(f"PicPay IMAP: {_sanitize_error_for_user(str(e))}")
        else:
            errors.append("PicPay IMAP: Desabilitado")

        # Tentar Itau IMAP
        if as_bool(pagamentos.get("itau_imap"), False) or as_bool((payment_configs.get("itau_imap") or {}).get("enabled"), False):
            try:
                result = await create_itau_imap_payment_from_settings(
                    amount=amount,
                    cart_id=str(cart_id or user.id),
                    description=description,
                )
                if result:
                    result["_provider"] = "itau_imap"
                return result
            except Exception as e:
                errors.append(f"Itau IMAP: {_sanitize_error_for_user(str(e))}")
        else:
            errors.append("Itau IMAP: Desabilitado")
        
        # Tentar PIX Manual
        if "pix_manual" not in providers_coming_soon and _payment_provider_enabled("pix_manual", pagamentos, payment_configs):
            try:
                result = await create_manual_pix_payment(
                    amount,
                    description=description,
                    transaction_id=str(cart_id or user.id),
                )
                if result:
                    result["_provider"] = "pix_manual"
                return result
            except ValueError as e:
                error_msg = _sanitize_error_for_user(str(e))
                errors.append(f"PIX Manual: {error_msg}")
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"PIX Manual: {sanitized}")
        elif "pix_manual" in providers_coming_soon:
            errors.append("PIX Manual: Em breve")
        else:
            errors.append("PIX Manual: Desabilitado")
        
        error_msg = "\n".join(errors) if errors else "Nenhum provedor configurado"
        raise RuntimeError(f"Nenhum provedor de PIX disponível.\n{error_msg}")
    
    elif payment_method == "card":
        card_cfg = payment_configs.get("card") or {}
        if not as_bool(card_cfg.get("enabled"), False):
            raise RuntimeError("Pagamento com cartao esta desativado.")

        preferred_gateway = card_cfg.get("gateway")
        gateway_order = []
        for gateway in [preferred_gateway, "mercado_pago", "stripe", "efibank", "asaas", "paypal"]:
            if gateway and gateway not in gateway_order:
                gateway_order.append(gateway)

        for gateway in gateway_order:
            if gateway in providers_coming_soon:
                errors.append(f"{gateway}: Em breve")
                continue
            if gateway != preferred_gateway and preferred_gateway:
                continue
            if not _payment_provider_enabled(gateway, pagamentos, payment_configs):
                errors.append(f"{gateway}: Desabilitado")
                continue
            try:
                if gateway == "mercado_pago":
                    result = await create_mp_site_payment_from_settings(
                        amount,
                        title=description,
                        description=description,
                    )
                elif gateway == "stripe":
                    result = await create_stripe_payment_from_settings(
                        amount,
                        title=description,
                        description=description,
                    )
                elif gateway == "efibank":
                    result = await create_efi_payment_from_settings(
                        price=amount,
                        nome_pagador=user.display_name if user else "Cliente",
                    )
                elif gateway == "asaas":
                    from functions.payments import create_asaas_payment_link_from_settings
                    result = await create_asaas_payment_link_from_settings(
                        amount,
                        name=description,
                        description=description,
                    )
                elif gateway == "paypal":
                    from functions.payments import create_paypal_payment_from_settings
                    result = await create_paypal_payment_from_settings(
                        amount,
                        title=description,
                        description=description,
                    )
                else:
                    errors.append(f"{gateway}: Nao suportado")
                    continue
                if result:
                    result["_provider"] = gateway
                return result
            except Exception as e:
                errors.append(f"{gateway}: {_sanitize_error_for_user(str(e))}")

        error_msg = "\n".join(errors) if errors else "Nenhum provedor configurado"
        raise RuntimeError(f"Nenhum provedor de cartao disponivel.\n{error_msg}")
        # Cartão: AssasLink, Stripe
        
        # Tentar Asaas Link
        if "asaas" not in providers_coming_soon:
            try:
                from functions.payments import create_asaas_payment_link_from_settings
                result = await create_asaas_payment_link_from_settings(
                    amount,
                    name=description,
                    description=description
                )
                if result:
                    result["_provider"] = "asaas"
                return result
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"AssasLink: {sanitized}")
        else:
            errors.append("AssasLink: Em breve")
        
        # Tentar Stripe
        if "stripe" not in providers_coming_soon:
            try:
                result = await create_stripe_payment_from_settings(
                    amount,
                    title=description,
                    description=description
                )
                if result:
                    result["_provider"] = "stripe"
                return result
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"Stripe: {sanitized}")
        else:
            errors.append("Stripe: Em breve")
        
        error_msg = "\n".join(errors) if errors else "Nenhum provedor configurado"
        raise RuntimeError(f"Nenhum provedor de cartão disponível.\n{error_msg}")
    
    elif payment_method == "crypto":
        # Crypto: Now, Coinbase
        
        # Tentar NOWPayments
        if "nowpayments" not in providers_coming_soon and _payment_provider_enabled("nowpayments", pagamentos, payment_configs):
            try:
                from functions.payments import create_nowpayments_invoice_from_settings
                result = await create_nowpayments_invoice_from_settings(
                    amount,
                    description=description
                )
                if result:
                    result["_provider"] = "nowpayments"
                return result
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"Now: {sanitized}")
        elif "nowpayments" in providers_coming_soon:
            errors.append("Now: Em breve")
        else:
            errors.append("Now: Desabilitado")
        
        # Tentar Coinbase
        if "coinbase" not in providers_coming_soon and _payment_provider_enabled("coinbase", pagamentos, payment_configs):
            try:
                result = await create_coinbase_payment_from_settings(
                    amount,
                    name=description,
                    description=description
                )
                if result:
                    result["_provider"] = "coinbase"
                return result
            except Exception as e:
                sanitized = _sanitize_error_for_user(str(e))
                errors.append(f"Coinbase: {sanitized}")
        elif "coinbase" in providers_coming_soon:
            errors.append("Coinbase: Em breve")
        else:
            errors.append("Coinbase: Desabilitado")
        
        error_msg = "\n".join(errors) if errors else "Nenhum provedor configurado"
        raise RuntimeError(f"Nenhum provedor de crypto disponível.\n{error_msg}")
    
    else:
        raise RuntimeError(f"Método de pagamento desconhecido: {payment_method}")


async def _monitor_payment(cart_id: str, payment_method: str, payment_ids: Dict[str, str], payment_provider: Optional[str], bot):
    """
    Monitora o status do pagamento usando o provedor correto
    
    Sistema de intervalo progressivo para reduzir carga na API:
    - Primeiros 2 minutos: verifica a cada 10 segundos (12 requisições)
    - Próximos 3 minutos: verifica a cada 20 segundos (9 requisições)
    - Próximos 5 minutos: verifica a cada 30 segundos (10 requisições)
    - Próximos 10 minutos: verifica a cada 60 segundos (10 requisições)
    - Restante (40 minutos): verifica a cada 120 segundos (20 requisições)
    
    Total: ~61 requisições em 60 minutos (vs 720 requisições no sistema antigo)
    Redução de 91% nas requisições!
    """
    try:
        # Definir intervalos progressivos (tempo_limite_segundos, intervalo_segundos)
        intervals = [
            (120, 10),    # 0-2 min: a cada 10s
            (300, 10),    # 2-5 min: a cada 10s
            (600, 20),    # 5-10 min: a cada 20s
            (1200, 30),   # 10-20 min: a cada 30s
            (3600, 60),  # 20-60 min: a cada 60s
        ]
        
        start_time = time.time()
        iteration = 0
        
        while True:
            # Calcular tempo decorrido
            elapsed = time.time() - start_time
            
            # Se passou 60 minutos, parar
            if elapsed >= 3600:
                break
            
            # Determinar intervalo atual baseado no tempo decorrido
            current_interval = 120  # Padrão: 2 minutos
            for time_limit, interval in intervals:
                if elapsed < time_limit:
                    current_interval = interval
                    break
            
            # Aguardar o intervalo apropriado
            await asyncio.sleep(current_interval)
            iteration += 1
            
            # Carregar dados do carrinho
            loja_data = db.get_document("loja_data")
            cart = loja_data.get("carts", {}).get(cart_id)
            
            if not cart:
                return
            
            # Se já foi aprovado ou cancelado, parar
            current_status = cart.get("status")
            if current_status in ["approved", "cancelled", "expired"]:
                return
            
            # Tentar obter provedor do payment_data se não foi passado (fazer ANTES de buscar payment_id)
            if not payment_provider:
                payment_data = cart.get("payment_data", {})
                payment_provider = payment_data.get("payment_provider")
                if not payment_provider and payment_data.get("raw"):
                    payment_provider = payment_data.get("raw", {}).get("_provider")
            
            # Obter ID do pagamento (também tentar do payment_data se não estiver em payment_ids)
            # Priorizar txid se o provedor for efibank
            if payment_provider == "efibank":
                payment_id = (
                    payment_ids.get("txid") or
                    payment_ids.get("payment_id") or
                    payment_ids.get("id")
                )
            else:
                payment_id = (
                    payment_ids.get("payment_id") or
                    payment_ids.get("id") or
                    payment_ids.get("payment_intent") or
                    payment_ids.get("invoice_id") or
                    payment_ids.get("preference_id") or
                    payment_ids.get("charge") or
                    payment_ids.get("txid")
                )
            
            # Se ainda não encontrou, tentar do payment_data
            if not payment_id:
                payment_data = cart.get("payment_data", {})
                raw_data = payment_data.get("raw", {})
                
                # Priorizar txid para Efí
                if payment_provider == "efibank":
                    payment_id = (
                        raw_data.get("txid") or
                        raw_data.get("payment_id") or
                        raw_data.get("id")
                    )
                else:
                    payment_id = (
                        raw_data.get("payment_id") or
                        raw_data.get("id") or
                        raw_data.get("txid") or
                        raw_data.get("payment_intent") or
                        raw_data.get("invoice_id")
                    )
            
            if not payment_id:
                continue
            
            # Verificar status do pagamento usando o provedor correto
            chk = {}
            try:
                # Se temos o provedor, usar diretamente
                if payment_provider:
                    provider_checkers = {
                        "Lyon_wallet": lambda pid: __import__('functions.payments.Lyon_wallet', fromlist=['check_Lyon_payment_from_settings']).check_Lyon_payment_from_settings(pid),
                        "mercado_pago": check_mp_payment_from_settings,
                        "efibank": check_efi_payment_from_settings,
                        "pagbank": check_pagbank_payment_from_settings,
                        "picpay": check_picpay_payment_from_settings,
                        "pushinpay": check_pushinpay_payment_from_settings,
                        "misticpay": check_misticpay_payment_from_settings,
                        "nubank_imap": check_nubank_imap_payment,
                        "picpay_imap": check_picpay_imap_payment_from_settings,
                        "itau_imap": check_itau_imap_payment_from_settings,
                        "stripe": check_stripe_payment_from_settings,
                        "paypal": check_paypal_payment_from_settings,
                        "asaas": check_asaas_payment_from_settings,
                        "coinbase": check_coinbase_payment_from_settings,
                        "nowpayments": check_nowpayments_invoice_from_settings,
                        "pix_manual": check_manual_pix_payment,
                    }
                    
                    checker = provider_checkers.get(payment_provider)
                    if checker:
                        try:
                            chk = await checker(payment_id)
                        except Exception:
                            chk = {}
                else:
                    # Se não temos o provedor, tentar todos os disponíveis para o método
                    if payment_method == "pix":
                        # Tentar todos os provedores PIX em ordem de prioridade
                        from functions.payments.Lyon_wallet import check_Lyon_payment_from_settings as check_Lyon
                        pix_providers = [
                            (check_Lyon),
                            ("mercado_pago", check_mp_payment_from_settings),
                            ("efibank", check_efi_payment_from_settings),
                            ("pagbank", check_pagbank_payment_from_settings),
                            ("asaas", check_asaas_payment_from_settings),
                            ("pushinpay", check_pushinpay_payment_from_settings),
                            ("misticpay", check_misticpay_payment_from_settings),
                            ("nubank_imap", check_nubank_imap_payment),
                            ("picpay_imap", check_picpay_imap_payment_from_settings),
                            ("itau_imap", check_itau_imap_payment_from_settings),
                            ("picpay", check_picpay_payment_from_settings),
                            ("pix_manual", check_manual_pix_payment),
                        ]
                        
                        for provider_name, checker_func in pix_providers:
                            try:
                                chk = await checker_func(payment_id)
                                # Se obteve resposta válida, salvar o provedor
                                if chk:
                                    payment_data = cart.get("payment_data", {})
                                    payment_data["payment_provider"] = provider_name
                                    cart["payment_data"] = payment_data
                                    loja_data["carts"][cart_id] = cart
                                    db.save_document("loja_data", loja_data)
                                    break
                            except Exception:
                                continue
                    
                    elif payment_method == "card":
                        # Tentar todos os provedores de cartão
                        card_providers = [
                            ("stripe", check_stripe_payment_from_settings),
                            ("mercado_pago", check_mp_payment_from_settings),
                            ("asaas", check_asaas_payment_from_settings),
                            ("paypal", check_paypal_payment_from_settings),
                        ]
                        
                        for provider_name, checker_func in card_providers:
                            try:
                                chk = await checker_func(payment_id)
                                if chk:
                                    payment_data = cart.get("payment_data", {})
                                    payment_data["payment_provider"] = provider_name
                                    cart["payment_data"] = payment_data
                                    loja_data["carts"][cart_id] = cart
                                    db.save_document("loja_data", loja_data)
                                    break
                            except Exception:
                                continue
                    
                    elif payment_method == "crypto":
                        # Tentar todos os provedores de crypto
                        crypto_providers = [
                            ("coinbase", check_coinbase_payment_from_settings),
                            ("nowpayments", check_nowpayments_invoice_from_settings),
                        ]
                        
                        for provider_name, checker_func in crypto_providers:
                            try:
                                chk = await checker_func(payment_id)
                                if chk:
                                    payment_data = cart.get("payment_data", {})
                                    payment_data["payment_provider"] = provider_name
                                    cart["payment_data"] = payment_data
                                    loja_data["carts"][cart_id] = cart
                                    db.save_document("loja_data", loja_data)
                                    break
                            except Exception:
                                continue
                
            except Exception:
                chk = {}
            
            # Verificar se foi aprovado
            # Buscar status em vários campos possíveis (incluindo raw do Efí e transaction do MisticPay)
            status = _find_first(chk, ["status", "payment_status", "state", "situacao"]) or "pending"
            
            # Se não encontrou no nível superior, tentar em data.status (Lyon Wallet pode retornar result diretamente)
            if status == "pending" and isinstance(chk, dict):
                data = chk.get("data", {})
                if isinstance(data, dict):
                    data_status = data.get("status")
                    if data_status:
                        status = data_status
            
            # Se não encontrou no nível superior, tentar em raw (Efí retorna em raw.status, MisticPay em raw.transaction.transactionState)
            if status == "pending" and isinstance(chk, dict):
                raw_data = chk.get("raw", {})
                if isinstance(raw_data, dict):
                    # Tentar raw.status primeiro (Efí)
                    raw_status_value = raw_data.get("status")
                    if raw_status_value:
                        status = raw_status_value
                    else:
                        # Tentar raw.transaction.transactionState (MisticPay)
                        transaction = raw_data.get("transaction", {})
                        if isinstance(transaction, dict):
                            transaction_state = transaction.get("transactionState")
                            if transaction_state:
                                status = transaction_state
            
            status_lower = str(status).lower()
            
            # Verificar também o campo "paid" se existir (MisticPay retorna isso)
            is_paid = chk.get("paid", False) if isinstance(chk, dict) else False
            
            # Status aprovados (incluindo "concluida" do Efí e "completo" do MisticPay)
            approved_statuses = {
                "approved", "paid", "completed", "completo", "succeeded", "accredited", 
                "concluida", "concluído", "pago", "aprovado"
            }
            
            # Status cancelados/falhados (incluindo "falha" do MisticPay)
            failed_statuses = {
                "canceled", "cancelled", "expired", "failed", "falha", "removida", 
                "removido", "cancelado", "expirado", "falhou"
            }
            
            # Verificar se foi aprovado: status aprovado OU campo paid=True
            if status_lower in approved_statuses or is_paid:
                # Pagamento aprovado!
                await _handle_payment_approved(cart_id, bot)
                return
            
            elif status_lower in failed_statuses:
                # Pagamento falhou
                cart["status"] = status_lower
                cart["updated_at"] = int(datetime.utcnow().timestamp())
                loja_data["carts"][cart_id] = cart
                db.save_document("loja_data", loja_data)
                return
    
    except Exception:
        pass


async def _check_single_payment_status(
    cart_id: str,
    payment_id: str,
    payment_method: str,
    payment_provider: Optional[str],
    bot
) -> tuple[bool, Optional[str]]:
    """
    Verifica o status de um pagamento individual e retorna se foi aprovado/falhou
    
    Returns:
        (is_finished, status) - is_finished=True se pagamento foi aprovado ou falhou,
                                status indica o status final
    """
    try:
        # Verificar status do pagamento usando o provedor correto
        chk = {}
        
        if payment_provider:
            provider_checkers = {
                "Lyon_wallet": lambda pid: __import__('functions.payments.Lyon_wallet', fromlist=['check_Lyon_payment_from_settings']).check_Lyon_payment_from_settings(pid),
                "mercado_pago": check_mp_payment_from_settings,
                "efibank": check_efi_payment_from_settings,
                "pagbank": check_pagbank_payment_from_settings,
                "picpay": check_picpay_payment_from_settings,
                "pushinpay": check_pushinpay_payment_from_settings,
                "misticpay": check_misticpay_payment_from_settings,
                "nubank_imap": check_nubank_imap_payment,
                "picpay_imap": check_picpay_imap_payment_from_settings,
                "itau_imap": check_itau_imap_payment_from_settings,
                "stripe": check_stripe_payment_from_settings,
                "paypal": check_paypal_payment_from_settings,
                "asaas": check_asaas_payment_from_settings,
                "coinbase": check_coinbase_payment_from_settings,
                "nowpayments": check_nowpayments_invoice_from_settings,
                "pix_manual": check_manual_pix_payment,
            }
            
            checker = provider_checkers.get(payment_provider)
            if checker:
                try:
                    chk = await checker(payment_id)
                except Exception as e:
                    print(f"[Check Payment] Erro ao verificar {payment_provider} para cart {cart_id}: {e}")
                    return False, None
        else:
            # Tentar todos os provedores para o método
            if payment_method == "pix":
                from functions.payments.Lyon_wallet import check_Lyon_payment_from_settings as check_Lyon
                pix_providers = [
                    (check_Lyon),
                    ("mercado_pago", check_mp_payment_from_settings),
                    ("efibank", check_efi_payment_from_settings),
                    ("pagbank", check_pagbank_payment_from_settings),
                    ("asaas", check_asaas_payment_from_settings),
                    ("pushinpay", check_pushinpay_payment_from_settings),
                    ("misticpay", check_misticpay_payment_from_settings),
                    ("nubank_imap", check_nubank_imap_payment),
                    ("picpay_imap", check_picpay_imap_payment_from_settings),
                    ("itau_imap", check_itau_imap_payment_from_settings),
                    ("picpay", check_picpay_payment_from_settings),
                    ("pix_manual", check_manual_pix_payment),
                ]
                
                for provider_name, checker_func in pix_providers:
                    try:
                        chk = await checker_func(payment_id)
                        if chk:
                            payment_provider = provider_name
                            break
                    except Exception:
                        continue
        
        if not chk:
            return False, None
        
        # Extrair status
        status = _find_first(chk, ["status", "payment_status", "state", "situacao"]) or "pending"
        
        # Verificar também em data.status (Lyon Wallet pode retornar result diretamente)
        if status == "pending" and isinstance(chk, dict):
            data = chk.get("data", {})
            if isinstance(data, dict):
                data_status = data.get("status")
                if data_status:
                    status = data_status
        
        # Verificar também em raw
        if status == "pending" and isinstance(chk, dict):
            raw_status = chk.get("raw", {})
            if isinstance(raw_status, dict):
                raw_status_value = raw_status.get("status")
                if raw_status_value:
                    status = raw_status_value
        
        status_lower = str(status).lower()
        is_paid = chk.get("paid", False) if isinstance(chk, dict) else False
        
        # Status aprovados
        approved_statuses = {
            "approved", "paid", "completed", "completo", "succeeded", "accredited", 
            "concluida", "concluído", "pago", "aprovado"
        }
        
        # Status cancelados/falhados
        failed_statuses = {
            "canceled", "cancelled", "expired", "failed", "falha", "removida", 
            "removido", "cancelado", "expirado", "falhou"
        }
        
        if status_lower in approved_statuses or is_paid:
            return True, "approved"
        elif status_lower in failed_statuses:
            return True, status_lower
        
        return False, None
        
    except Exception as e:
        print(f"[Check Payment] Erro ao verificar pagamento para cart {cart_id}: {e}")
        import traceback
        traceback.print_exc()
        return False, None


async def _process_free_purchase(cart_id: str, bot):
    """Processa compra gratuita (cupom 100%) automaticamente"""
    # Aguardar 2 segundos para garantir que tudo foi salvo
    await asyncio.sleep(2)
    
    # Processar como pagamento aprovado
    await _handle_payment_approved(cart_id, bot)


async def _handle_payment_approved(cart_id: str, bot):
    """Processa pagamento aprovado"""
    print(f"[CHECKOUT] Iniciando processamento de pagamento aprovado para cart_id: {cart_id}")
    
    try:
        # Carregar dados
        loja_data = db.get_document("loja_data")
        
        cart = loja_data.get("carts", {}).get(cart_id)
        
        if not cart:
            print(f"[CHECKOUT] Carrinho {cart_id} não encontrado!")
            return
        
        # Debug: verificar carrinho antes da migração
        
        if "items" in cart:
            items_raw = cart.get('items')
            if isinstance(items_raw, list) and items_raw:
                for idx, it in enumerate(items_raw):
                    pass
        else:
            pass
        
        # Migrar para estrutura de items se necessário
        cart = _migrate_cart_to_items(cart)
        public_order_id = ensure_cart_order_id(cart, loja_data.get("carts", {}))
        
        # Debug: verificar carrinho depois da migração
        
        # Verificar se items estão válidos
        items = cart.get("items", [])
        if not items or not any(item.get("product_id") and item.get("campo_id") for item in items):
            # Tentar recarregar do banco de dados
            loja_data = db.get_document("loja_data")
            cart = loja_data.get("carts", {}).get(cart_id)
            if cart:
                cart = _migrate_cart_to_items(cart)
                items = cart.get("items", [])
                if not items or not any(item.get("product_id") and item.get("campo_id") for item in items):
                    return
        
        # SALVAR CARRINHO MIGRADO antes de continuar!
        loja_data["carts"][cart_id] = cart
        db.save_document("loja_data", loja_data)
        
        # Atualizar status
        cart["status"] = "approved"
        cart["approved_at"] = int(datetime.utcnow().timestamp())
        cart["updated_at"] = int(datetime.utcnow().timestamp())
        loja_data["carts"][cart_id] = cart
        db.save_document("loja_data", loja_data)
        
        # Deduzir saldo usado (se houver)
        try:
            balance_applied = cart.get("balance_applied", 0)
            balance_user_id = cart.get("balance_user_id")
            if balance_applied > 0 and balance_user_id:
                from modules.loja.saldo.checkout_integration import SaldoCheckoutIntegration
                await SaldoCheckoutIntegration.process_balance_deduction(cart, bot)
        except Exception as e:
            print(f"[CHECKOUT] Erro ao deduzir saldo: {e}")
        
        # Ativar modo rápido no contador de vendas se disponível
        try:
            task_cog = bot.get_cog("ContVendasTaskCog")
            if task_cog and hasattr(task_cog, "trigger_fast_mode"):
                task_cog.trigger_fast_mode(cart["guild_id"])
        except Exception:
            pass
        
        # Buscar thread
        guild = bot.get_guild(cart["guild_id"])
        if not guild:
            print(f"[CHECKOUT] Guild {cart.get('guild_id')} não encontrado!")
            return
        
        thread = guild.get_thread(cart["thread_id"])
        if not thread:
            print(f"[CHECKOUT] Thread {cart.get('thread_id')} não encontrada!")
            return
        
        print(f"[CHECKOUT] Thread encontrada: {thread.name}")
        
        # NOTA: A mensagem de pagamento (QR code) será deletada mais abaixo
        # A mensagem do carrinho será atualizada mais abaixo também
        
        # Enviar mensagem de sucesso e processar entrega
        # Resolver usuário com fallback (cache -> fetch_member -> fetch_user)
        user = guild.get_member(cart["user_id"])
        if not user:
            try:
                user = await guild.fetch_member(int(cart["user_id"]))
            except Exception:
                try:
                    user = await bot.fetch_user(int(cart["user_id"]))
                except Exception:
                    user = None
        # Atribuir cargo de cliente após pagamento aprovado (apenas para Member)
        cargo_atribuido = False
        try:
            cargos_cfg = db.get_document("cargos") or {}
            cliente_role_id = cargos_cfg.get("cargo_cliente")
            if cliente_role_id and isinstance(user, disnake.Member):
                role = guild.get_role(int(cliente_role_id))
                if role and role not in user.roles:
                    await user.add_roles(role, reason="Compra aprovada - cargo cliente")
                    cargo_atribuido = True
        except Exception:
            pass
        
        # Marcar usuário no canal de feedback após receber cargo de cliente
        if cargo_atribuido and user:
            try:
                canais = db.get_document("canais") or {}
                feedback_channel_id = canais.get("canal_de_feedback")
                if feedback_channel_id:
                    feedback_channel = guild.get_channel(int(feedback_channel_id))
                    if feedback_channel:
                        # Enviar mensagem marcando o usuário
                        feedback_msg = await feedback_channel.send(f"{user.mention}")
                        # Apagar a mensagem imediatamente após enviar
                        await feedback_msg.delete()
            except Exception:
                pass

        # Obter tipo de entrega e items ANTES de usar
        delivery_type = cart.get("delivery_type", "automatic")
        products = db.get_document("loja_products")
        items = cart.get("items", [])
        
        # Enviar notificação WhatsApp (Fire and Forget)
        try:
             # Calcular total final
             total_val = sum(item.get("item_total", 0) for item in items)
             disc = cart.get("discount_amount", 0) or 0
             bal = cart.get("balance_applied", 0) or 0
             total_val = max(0, total_val - disc - bal)
             
             # Nome do produto
             first_prod_id = items[0].get("product_id") if items else None
             first_prod_name = products.get(first_prod_id, {}).get("name", "Produto") if first_prod_id else "Produto"
             if len(items) > 1:
                 p_name_str = f"{first_prod_name} + {len(items)-1} itens"
             else:
                 p_name_str = first_prod_name
             
             b_name = user.display_name if user else "Cliente"
             
             # Executar em background para não bloquear
             asyncio.create_task(_send_whatsapp_notification(
                 product_name=p_name_str,
                 value=f"R$ {total_val:,.2f}",
                 buyer_name=b_name
             ))
        except Exception as e:
            print(f"[WhatsApp] Falha ao preparar notificação: {e}")
        
        # Inicializar variáveis de controle de entrega (disponíveis em todo o escopo)
        manual_items = []
        automatic_items = []
        all_delivered = True
        delivered_automatically = False
        
        # Separar itens por tipo de entrega ANTES de processar (independente de user)
        if items:
            for item in items:
                product_id = item.get("product_id")
                campo_id = item.get("campo_id")
                qty = item.get("quantity", 1)
                
                if not product_id or not campo_id:
                    all_delivered = False
                    continue
                
                product = products.get(product_id, {})
                if not product:
                    all_delivered = False
                    continue
                
                # Obter tipo de entrega deste produto específico
                info = product.get("info") or {}
                item_delivery_type = info.get("delivery_type", "automatic")
                
                product_name = product.get("name", "Produto")
                campos = product.get("campos") or {}
                field = campos.get(campo_id, {})
                campo_name = field.get("name", "") if field else ""
                
                if item_delivery_type == "automatic":
                    automatic_items.append({
                        "product_id": product_id,
                        "campo_id": campo_id,
                        "product_name": product_name,
                        "campo_name": campo_name,
                        "quantity": qty,
                        "item": item
                    })
                else:
                    manual_items.append({
                        "product_id": product_id,
                        "campo_id": campo_id,
                        "product_name": product_name,
                        "campo_name": campo_name,
                        "quantity": qty,
                        "item": item
                    })
        
        # Debug: verificar items
        if items:
            for idx, item in enumerate(items):
                pass

        try:
            # DM de pagamento aprovado - sempre enviar para todos os casos
            if user and items:
                try:
                    products_info = db.get_document("loja_products")
                    cart_url = f"https://discord.com/channels/{guild.id}/{cart['thread_id']}"
                    
                    # Verificar tipos de entrega
                    has_manual_items = False
                    has_automatic_items = False
                    for item in items:
                        product_id = item.get("product_id")
                        product_check = products_info.get(product_id, {})
                        info_check = product_check.get("info") or {}
                        if info_check.get("delivery_type", "automatic") == "manual":
                            has_manual_items = True
                        else:
                            has_automatic_items = True
                    
                    # Construir lista de produtos
                    products_list = []
                    for item in items:
                        product_id = item.get("product_id")
                        campo_id = item.get("campo_id")
                        qty = item.get("quantity", 1)
                        
                        prod = products_info.get(product_id, {})
                        campos_info = prod.get("campos", {})
                        field_info = campos_info.get(campo_id, {})
                        campo_name = field_info.get("name", "Campo")
                        product_name = prod.get("name", "Produto")
                        
                        products_list.append(f"**{product_name}** - `{campo_name}` (x{qty})")
                    
                    products_text = "\n".join(products_list)
                    
                    # Definir texto de entrega baseado nos tipos
                    if has_manual_items and has_automatic_items:
                        delivery_text = "Alguns produtos serão entregues automaticamente e outros manualmente no carrinho do servidor."
                    elif has_manual_items:
                        delivery_text = "Entrega manual. Ela será realizada no carrinho do servidor."
                    else:
                        delivery_text = "Seus produtos serão entregues automaticamente em instantes!"
                    
                    mode_dm = db.get_document("custom_mode").get("mode", "embed")
                    color_data = db.get_document("custom_colors") or {}
                    primary_color = color_data.get("primary")
                    
                    if mode_dm == "embed":
                        embed_color = disnake.Color.green()
                        if primary_color:
                            try:
                                embed_color = disnake.Colour(int(primary_color.replace("#", ""), 16))
                            except:
                                pass
                        
                        approved_embed = disnake.Embed(
                            title=f"{emoji.correct} Pagamento Aprovado!",
                            description=f"Seu pagamento foi aprovado com sucesso!\n\n{products_text}",
                            color=embed_color
                        )
                        approved_embed.add_field(
                            name=f"Entrega",
                            value=delivery_text,
                            inline=False
                        )
                        
                        components_list = []
                        if has_manual_items:
                            components_list = [
                                disnake.ui.ActionRow(
                                    disnake.ui.Button(
                                        label="Abrir Carrinho",
                                        style=disnake.ButtonStyle.url,
                                        url=cart_url
                                    )
                                )
                            ]
                        
                        await user.send(
                            embed=approved_embed,
                            components=components_list if components_list else None
                        )
                    else:
                        # Modo Container
                        container_kwargs = {}
                        if primary_color:
                            try:
                                container_kwargs["accent_colour"] = disnake.Colour(int(primary_color.replace("#", ""), 16))
                            except:
                                pass
                        
                        container_items = [
                            disnake.ui.TextDisplay(f"# {emoji.correct}\n-# Pagamento Aprovado!"),
                            disnake.ui.Separator(),
                            disnake.ui.TextDisplay(f"-# {products_text}"),
                            disnake.ui.Separator(),
                            disnake.ui.TextDisplay(delivery_text)
                        ]
                        
                        components = [
                            disnake.ui.Container(
                                *container_items,
                                **container_kwargs
                            )
                        ]
                        
                        if has_manual_items:
                            components.append(
                                disnake.ui.ActionRow(
                                    disnake.ui.Button(
                                        label="Abrir Carrinho",
                                        style=disnake.ButtonStyle.url,
                                        url=cart_url
                                    )
                                )
                            )
                        
                        await user.send(
                            components=components,
                            flags=disnake.MessageFlags(is_components_v2=True)
                        )
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    pass

            # ArmaLyonar itens entregues para logs (chave: (product_id, campo_id))
            delivered_items_map = {}
            
            # Processar entrega para cada item individualmente (suporta tipos mistos)
            if user:
                try:
                    # Processar entrega automática para itens automáticos
                    # (manual_items e automatic_items já foram separados acima)
                    for auto_item in automatic_items:
                        try:
                            # NOTA: NÃO retirar estoque aqui! O process_automatic_delivery
                            # já retira o estoque internamente. Retirar aqui causava
                            # o bug de "produto não encontrado" por duplicação.
                            
                            item_delivered = await process_automatic_delivery(
                                user=user,
                                product_id=auto_item["product_id"],
                                campo_id=auto_item["campo_id"],
                                product_name=auto_item["product_name"],
                                campo_name=auto_item["campo_name"],
                                quantity=auto_item["quantity"],
                                thread=thread,
                                guild=guild
                            )
                            
                            if item_delivered:
                                # Marcar como entregue para o log
                                key = (auto_item["product_id"], auto_item["campo_id"])
                                # O estoque já foi retirado dentro de process_automatic_delivery
                                # Marcamos apenas que foi entregue com sucesso
                                delivered_items_map[key] = True
                            else:
                                all_delivered = False
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            print(f"[Delivery Error] Erro ao entregar item {auto_item.get('product_name')}: {e}")
                            all_delivered = False
                            # Remover da lista se falhou
                            key = (auto_item["product_id"], auto_item["campo_id"])
                            delivered_items_map.pop(key, None)
                            # Continuar com próximo item mesmo se este falhar
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"[Delivery Error] Erro geral no processamento de entrega: {e}")
                
                # Para itens manuais, apenas registrar que precisam de entrega manual
                # A entrega manual será feita no carrinho mais abaixo
                
                # Aplicar cargos dos produtos (adicionar e remover)
                try:
                    for item in items:
                        product_id = item.get("product_id")
                        campo_id = item.get("campo_id")
                        
                        if not product_id or not campo_id:
                            continue
                        
                        product = products.get(product_id, {})
                        if not product:
                            continue
                        
                        campos = product.get("campos") or {}
                        field = campos.get(campo_id, {})
                        if not field:
                            continue
                        
                        # Obter configuração de cargos do campo
                        cargos_config = field.get("cargos", {})
                        roles_to_add = cargos_config.get("adicionar", [])
                        roles_to_remove = cargos_config.get("remover", [])
                        duracao_minutos = cargos_config.get("duracao_minutos")
                        try:
                            duracao_minutos = int(duracao_minutos or 0)
                        except (TypeError, ValueError):
                            duracao_minutos = 0
                        add_role_ids = {str(role_id) for role_id in roles_to_add}
                        roles_to_remove = [role_id for role_id in roles_to_remove if str(role_id) not in add_role_ids]
                        
                        # Adicionar cargos
                        if roles_to_add:
                            for role_id in roles_to_add:
                                try:
                                    role = guild.get_role(int(role_id))
                                    if not role:
                                        continue
                                    if role not in user.roles:
                                        await user.add_roles(role, reason=f"Compra do produto: {product.get('name', 'Produto')}")
                                        
                                        # Se o cargo tem duração, registrar em roles_temp
                                        if duracao_minutos and duracao_minutos > 0:
                                            roles_temp = db.get_document("loja_roles_temp") or {}
                                            now_ts = int(time.time())
                                            expiration_time = now_ts + (duracao_minutos * 60)
                                            
                                            user_id_str = str(user.id)
                                            if user_id_str not in roles_temp:
                                                roles_temp[user_id_str] = []

                                            updated_records = []
                                            for record in roles_temp.get(user_id_str, []):
                                                same_role = (
                                                    str(record.get("guild_id")) == str(guild.id)
                                                    and str(record.get("role_id")) == str(role.id)
                                                )
                                                if same_role:
                                                    try:
                                                        expiration_time = max(expiration_time, int(record.get("expires_at") or 0))
                                                    except (TypeError, ValueError):
                                                        pass
                                                    continue
                                                updated_records.append(record)
                                            
                                            # Adicionar cargo temporário
                                            updated_records.append({
                                                "role_id": role.id,
                                                "expires_at": expiration_time,
                                                "guild_id": guild.id,
                                                "assigned_at": now_ts,
                                                "source": "store_purchase",
                                                "product_id": product_id,
                                                "campo_id": campo_id,
                                                "cart_id": cart_id,
                                            })
                                            roles_temp[user_id_str] = updated_records
                                            db.save_document("loja_roles_temp", roles_temp)
                                except (ValueError, TypeError):
                                    pass
                                except disnake.Forbidden:
                                    print(f"[CHECKOUT] ⚠️ Sem permissão para adicionar cargo {role_id} ao usuário {user.id}")
                                    pass
                                except Exception as e:
                                    print(f"[CHECKOUT] ⚠️ Erro ao adicionar cargo {role_id}: {e}")
                                    pass
                        
                        # Remover cargos
                        if roles_to_remove:
                            for role_id in roles_to_remove:
                                try:
                                    role = guild.get_role(int(role_id))
                                    if role and role in user.roles:
                                        await user.remove_roles(role, reason=f"Compra do produto: {product.get('name', 'Produto')}")
                                except (ValueError, TypeError):
                                    pass
                                except disnake.Forbidden:
                                    print(f"[CHECKOUT] ⚠️ Sem permissão para remover cargo {role_id} do usuário {user.id}")
                                    pass
                                except Exception as e:
                                    print(f"[CHECKOUT] ⚠️ Erro ao remover cargo {role_id}: {e}")
                                    pass
                except Exception as e:
                    print(f"[CHECKOUT] ⚠️ Erro geral ao aplicar cargos: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continuar mesmo se houver erro ao aplicar cargos
                
                # delivered_automatically = True apenas se todos os itens automáticos foram entregues
                # e não há itens manuais (ou se há itens manuais, eles serão entregues no carrinho)
                delivered_automatically = all_delivered and len(automatic_items) > 0 and len(manual_items) == 0
            else:
                # Se não tem user, não pode entregar automaticamente
                delivered_automatically = False
                # Mas ainda precisa calcular manual_items_count corretamente
                # (já foi calculado acima antes do if user)
            
            # Renomear thread após pagamento aprovado (independente de ter user ou não)
            # ✅ se todos os produtos são automáticos e foram entregues
            # ⌚ se há algum produto de entrega manual
            if thread:
                try:
                    old_name = thread.name
                    new_name = None
                    
                    # Verificar se há produtos de entrega manual
                    if len(manual_items) > 0:
                        # Se há itens manuais, usar ⌚
                        if old_name.startswith("💱・"):
                            new_name = old_name.replace("💱・", "⌚・", 1)
                        elif old_name.startswith("✅・"):
                            new_name = old_name.replace("✅・", "⌚・", 1)
                    else:
                        # Se não há itens manuais, usar ✅
                        if old_name.startswith("💱・"):
                            new_name = old_name.replace("💱・", "✅・", 1)
                        elif old_name.startswith("⌚・"):
                            new_name = old_name.replace("⌚・", "✅・", 1)
                    
                    if new_name:
                        await thread.edit(name=new_name)
                except Exception as e:
                    pass
            
            # Registrar compra no histórico para cada item (sempre, independente do tipo de entrega)
            if user and items:
                    try:
                        discount_amount = float(cart.get("discount_amount", 0))
                        total_cart_price = float(cart.get("total_price", 0))
                        payment_data = cart.get("payment_data") or {}
                        payment_provider = payment_data.get("provider") or {}
                        payment_reference = (
                            payment_provider.get("payment_id")
                            or payment_provider.get("txid")
                            or payment_provider.get("correlation_id")
                            or payment_provider.get("charge_id")
                        )
                        
                        # Registrar cada item separadamente
                        for item in items:
                            product_id = item.get("product_id")
                            campo_id = item.get("campo_id")
                            qty = item.get("quantity", 1)
                            unit_price = item.get("price_per_unit", 0)
                            item_total = item.get("item_total", 0)
                            
                            product = products.get(product_id, {})
                            product_name = product.get("name", "Produto")
                            campos = product.get("campos") or {}
                            field = campos.get(campo_id) or {}
                            campo_name = field.get("name", "")
                            
                            # Obter tipo de entrega específico deste item
                            info = product.get("info") or {}
                            item_delivery_type = info.get("delivery_type", "automatic")
                            
                            # Dividir desconto proporcionalmente entre itens
                            item_discount = (discount_amount * item_total / total_cart_price) if total_cart_price > 0 else 0
                            item_final_price = item_total - item_discount
                            
                            purchase_id = PurchaseManager.register_purchase(
                                user_id=user.id,
                                product_id=product_id,
                                product_name=product_name,
                                field_id=campo_id,
                                field_name=campo_name,
                                quantity=qty,
                                unit_price=unit_price,
                                total_price=item_total,
                                discount_amount=item_discount,
                                final_price=item_final_price,
                                payment_method=cart.get("payment_method", "unknown"),
                                coupon_code=cart.get("coupon_code"),
                                items_received=[],
                                metadata={
                                    "order_id": public_order_id,
                                    "cart_id": cart_id,
                                    "thread_id": cart.get("thread_id"),
                                    "payment_id": payment_reference,
                                    "payment_provider": payment_provider.get("name"),
                                    "txid": payment_provider.get("txid"),
                                    "correlation_id": payment_provider.get("correlation_id"),
                                    "charge_id": payment_provider.get("charge_id"),
                                    "guild_id": cart.get("guild_id"),  # Adicionar guild_id diretamente
                                    "delivery_type": item_delivery_type  # Usar o tipo de entrega específico do item
                                }
                            )
                            
                            # Verificar e atribuir condecorações após compra
                            try:
                                from modules.loja.cloud_sales import CloudSales
                                await CloudSales.process_purchase(
                                    bot=bot,
                                    guild=guild,
                                    user=user,
                                    item=item,
                                    product=product,
                                    field=field,
                                    cart_id=cart_id,
                                    purchase_id=purchase_id,
                                )
                            except Exception as e:
                                print(f"[LyonCloud] Erro ao aplicar credito da compra: {e}")

                            try:
                                clientes_cog = bot.get_cog("ClientesLyon")
                                if clientes_cog and hasattr(clientes_cog, "check_user_decorations"):
                                    guild = bot.get_guild(int(cart.get("guild_id")))
                                    if guild:
                                        asyncio.create_task(clientes_cog.check_user_decorations(user.id, guild))
                            except Exception as e:
                                print(f"Erro ao verificar condecorações após compra: {e}")
                            
                            # Atualizar vendas do produto (purchasesIds e total_paid)
                            if product_id in products:
                                product_info = products[product_id].get("info", {})
                                purchases_ids = product_info.get("purchasesIds", [])
                                if purchase_id not in purchases_ids:
                                    purchases_ids.append(purchase_id)
                                product_info["purchasesIds"] = purchases_ids
                                product_info["total_paid"] = product_info.get("total_paid", 0) + item_final_price
                                products[product_id]["info"] = product_info
                                db.save_document("loja_products", products)
                                
                                # Sincronizar mensagens do produto para atualizar vendas
                                try:
                                    from modules.loja.products.product.edit import Lyon_product_messages_silently
                                    asyncio.create_task(Lyon_product_messages_silently(bot, product_id))
                                except Exception as e:
                                    pass
                        
                        # Marcar cupom como usado se houver (apenas se não for compra gratuita, pois já foi marcado)
                        if cart.get("coupon_code") and not cart.get("is_free_purchase"):
                            try:
                                coupon_type = cart.get("coupon_type")
                                # Para cupons globais, usar o primeiro produto; para específicos, usar o produto do cupom
                                first_product_id = items[0].get("product_id") if items else None
                                if coupon_type and first_product_id:
                                    CouponValidator.use_coupon(cart.get("coupon_code"), coupon_type, first_product_id, user.id)
                            except Exception as e:
                                pass
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        print(f"Erro ao registrar compras: {e}")
                        pass

            # Enviar evento público de compra para o canal de eventos de compras
            if user:
                public_receipt_sent = False
                try:
                    logs_cog = bot.get_cog("PurchaseLogsLyon")
                    
                    if logs_cog:
                        # Preparar lista de itens para o evento de compra (uma única imagem)
                        event_items = []
                        for item in items:
                            product_id = item.get("product_id")
                            campo_id = item.get("campo_id")
                            qty = item.get("quantity", 1)
                            item_total = item.get("item_total", 0)
                            
                            product = products.get(product_id, {})
                            product_name = product.get("name", "Produto")
                            campos = product.get("campos") or {}
                            field = campos.get(campo_id) or {}
                            campo_name = field.get("name", "")
                            
                            event_items.append({
                                "product_name": product_name,
                                "campo_name": campo_name,
                                "quantity": qty,
                                "price": float(item_total),
                                "product_id": product_id
                            })
                        
                        # Enviar evento público de compra uma única vez com todos os itens
                        final_price = max(0, total_cart_price - discount_amount - balance_applied)
                        await logs_cog.send_purchase_event_bulk(
                            guild=guild,
                            user=user,
                            items=event_items,
                            total_price=final_price,
                            subtotal=total_cart_price,
                            discount_amount=discount_amount if discount_amount > 0 else None,
                            coupon_code=cart.get("coupon_code"),
                            cart_id=public_order_id
                        )
                        public_receipt_sent = True
                except Exception as e:
                    print(f"[CHECKOUT] ERRO ao enviar evento de compra: {e}")
                    import traceback
                    traceback.print_exc()

                if not public_receipt_sent:
                    try:
                        await send_purchase_receipt(bot, guild, user, cart, items)
                    except Exception as e:
                        print(f"[CHECKOUT] Erro ao enviar recibo de compra publico: {e}")
                        import traceback
                        traceback.print_exc()
            
            # O sistema de logs de pedido foi removido desta etapa.
            # Deixa-se apenas o envio do evento de compra com comprovante e botões no canal de eventos.
            
            # EDITAR mensagem do pagamento (QR code) para mostrar aprovação ao invés de deletar
            print(f"[CHECKOUT] Tentando editar mensagem de pagamento para mostrar aprovação...")
            try:
                payment_message_id = cart.get("message_id")
                print(f"[CHECKOUT] payment_message_id: {payment_message_id}")
                if payment_message_id:
                    try:
                        payment_msg = await thread.fetch_message(payment_message_id)
                        
                        # Criar mensagem de pagamento aprovado simples
                        mode = db.get_document("custom_mode").get("mode", "embed")
                        
                        if mode == "embed":
                            approved_embed = disnake.Embed(
                                title=f"{emoji.correct} Pagamento Aprovado!",
                                description="Seu pagamento foi confirmado com sucesso!",
                                color=disnake.Color.green()
                            )
                            await payment_msg.edit(
                                content=None,
                                embed=approved_embed,
                                components=[],
                            )
                        else:
                            # Modo container
                            await payment_msg.edit(
                                content=None,
                                embed=None,
                                components=[
                                    disnake.ui.Container(
                                        disnake.ui.TextDisplay(f"# {emoji.correct}\n-# Pagamento Aprovado!"),
                                        disnake.ui.Separator(),
                                        disnake.ui.TextDisplay("Seu pagamento foi confirmado com sucesso!")
                                    )
                                ],
                                flags=disnake.MessageFlags(is_components_v2=True)
                            )
                        
                        print(f"[CHECKOUT] ✅ Mensagem de pagamento editada para mostrar aprovação")
                    except disnake.NotFound:
                        print(f"[CHECKOUT] ⚠️ Mensagem de pagamento {payment_message_id} não encontrada")
                    except Exception as e:
                        print(f"[CHECKOUT] ❌ Erro ao editar mensagem de pagamento: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"[CHECKOUT] ⚠️ Nenhuma mensagem de pagamento encontrada no carrinho")
            except Exception as e:
                print(f"[CHECKOUT] ❌ Erro geral ao editar mensagem de pagamento: {e}")
                import traceback
                traceback.print_exc()
            
            # Aplicar cashback ao saldo do usuário
            try:
                from modules.loja.cashback.manager import CashbackManager
                if user and CashbackManager.is_enabled():
                    # Obter valor final pago (após descontos e saldo)
                    total_price = sum(item.get("item_total", 0) for item in items)
                    discount_amount = cart.get("discount_amount", 0) or 0
                    balance_applied = cart.get("balance_applied", 0) or 0
                    final_price = max(0, total_price - discount_amount - balance_applied)
                    
                    # Obter roles do usuário
                    user_roles = []
                    if isinstance(user, disnake.Member):
                        user_roles = [role.id for role in user.roles]
                    
                    # Calcular e aplicar cashback
                    cashback_amount = CashbackManager.calculate_cashback(final_price, user_roles)
                    if cashback_amount > 0:
                        success, message = CashbackManager.apply_cashback(
                            user.id,
                            cashback_amount,
                            purchase_ref=cart_id
                        )
                        if success:
                            print(f"[CHECKOUT] Cashback de R$ {cashback_amount:.2f} creditado ao usuário {user.id}")
                        else:
                            print(f"[CHECKOUT] Erro ao creditar cashback: {message}")
            except Exception as e:
                print(f"[CHECKOUT] Erro ao processar cashback: {e}")
            
            # O comprovante agora é enviado apenas no canal de eventos de compras com os botões
            print(f"[CHECKOUT] ✅ Comprovante será enviado no canal de eventos de compras via sistema de logs")
            
            # Contar itens manuais para determinar se mostrar botão
            # manual_items foi inicializado acima no escopo da função
            manual_items_count = len(manual_items) if manual_items else 0
            
            # EDITAR mensagem do carrinho para mostrar checkout aprovado ao invés de criar nova
            try:
                print(f"[CHECKOUT] Editando mensagem do carrinho para mostrar checkout aprovado...")
                # Obter modo de exibição
                mode = db.get_document("custom_mode").get("mode", "embed")
                
                # Construir mensagem usando função auxiliar
                embed, components_list, content_text = _build_approved_checkout_message(
                    cart=cart,
                    items=items,
                    products=products,
                    delivered_automatically=delivered_automatically,
                    manual_items_count=manual_items_count,
                    mode=mode
                )
                
                # Tentar editar a mensagem do carrinho existente
                cart_message_id = cart.get("cart_message_id")
                if cart_message_id:
                    try:
                        cart_msg = await thread.fetch_message(cart_message_id)
                        
                        # Editar mensagem existente conforme o modo
                        if mode == "embed":
                            await cart_msg.edit(
                                content=None,
                                embed=embed,
                                components=components_list if components_list else []
                            )
                        else:
                            await cart_msg.edit(
                                content=None,
                                embed=None,
                                components=components_list if components_list else [],
                                flags=disnake.MessageFlags(is_components_v2=True)
                            )
                        
                        print(f"[CHECKOUT] ✅ Mensagem do carrinho editada para checkout aprovado: {cart_msg.id}")
                        
                        # Usar a mensagem editada como approved_message
                        new_msg = cart_msg
                        cart["approved_message_id"] = cart_msg.id
                        loja_data["carts"][cart_id] = cart
                        db.save_document("loja_data", loja_data)
                        
                    except disnake.NotFound:
                        print(f"[CHECKOUT] Mensagem do carrinho não encontrada, criando nova...")
                        # Se não encontrou, criar nova mensagem
                        if mode == "embed":
                            new_msg = await thread.send(
                                embed=embed,
                                components=components_list if components_list else None
                            )
                        else:
                            new_msg = await thread.send(
                                components=components_list if components_list else None,
                                flags=disnake.MessageFlags(is_components_v2=True)
                            )
                        
                        cart["approved_message_id"] = new_msg.id
                        loja_data["carts"][cart_id] = cart
                        db.save_document("loja_data", loja_data)
                else:
                    # Se não tem cart_message_id, criar nova mensagem
                    print(f"[CHECKOUT] Nenhuma mensagem do carrinho encontrada, criando nova...")
                    if mode == "embed":
                        new_msg = await thread.send(
                            embed=embed,
                            components=components_list if components_list else None
                        )
                    else:
                        new_msg = await thread.send(
                            components=components_list if components_list else None,
                            flags=disnake.MessageFlags(is_components_v2=True)
                        )
                    
                    cart["approved_message_id"] = new_msg.id
                    loja_data["carts"][cart_id] = cart
                    db.save_document("loja_data", loja_data)
                
                # Enviar mensagem de entrega realizada como reply (se entrega automática)
                if delivered_automatically and user:
                    try:
                        await new_msg.reply(
                            f"**{emoji.correct} Entrega realizada!**\n-# Os itens foram entregues com sucesso na DM de {user.mention}!"
                        )
                        print(f"[CHECKOUT] Reply de entrega enviado com sucesso")
                    except Exception as e:
                        print(f"[CHECKOUT] Erro ao enviar reply de entrega: {e}")
                        import traceback
                        traceback.print_exc()
            except Exception as e:
                print(f"[CHECKOUT] ❌ Erro ao editar/criar mensagem de checkout aprovado: {e}")
                import traceback
                traceback.print_exc()
            
            # Mensagens no tópico conforme resultado
            # Obter cargo admin uma vez (fora do if user para garantir que sempre seja mencionado)
            print(f"[CHECKOUT] Preparando mensagens no tópico...")
            cargos_data = db.get_document("cargos")
            cargo_admin_id = cargos_data.get("cargo_admin")
            admin_mention = ""
            try:
                if cargo_admin_id:
                    role = guild.get_role(int(cargo_admin_id))
                    if role:
                        admin_mention = f" {role.mention}"
                        print(f"[CHECKOUT] Cargo admin encontrado: {role.name}")
                    else:
                        print(f"[CHECKOUT] ⚠️ Cargo admin {cargo_admin_id} não encontrado no servidor")
                else:
                    print(f"[CHECKOUT] ⚠️ Nenhum cargo admin configurado")
            except Exception as e:
                print(f"[CHECKOUT] Erro ao obter cargo admin: {e}")
            
            try:
                if user:
                    if delivered_automatically:
                        # Calcular timestamp para 5 minutos (300 segundos)
                        seconds_to_delete = 300
                        delete_timestamp = int(time.time()) + seconds_to_delete
                        await thread.send(
                            f"{emoji.correct} {user.mention} "
                            f"Como tudo ocorreu bem, esse tópico será excluído em <t:{delete_timestamp}:R>"
                        )
                        print(f"[CHECKOUT] ✅ Mensagem de exclusão automática enviada")
                    else:
                        # Entrega manual ou parcial: mencionar admins
                        if len(manual_items) > 0:
                            print(f"[CHECKOUT] Enviando mensagem de entrega manual para {len(manual_items)} itens")
                            # Avisar que itens de entrega manual aguardam entrega por admin
                            products_list = []
                            for manual_item in manual_items:
                                product_name = manual_item.get("product_name", "Produto")
                                campo_name = manual_item.get("campo_name", "Campo")
                                qty = manual_item.get("quantity", 1)
                                products_list.append(f"{emoji.arrow} **{product_name}** - `{campo_name}` (x{qty})")
                            
                            products_text = "\n".join(products_list)
                            
                            msg_content = f"{emoji.warn} **Itens de entrega manual aguardando entrega.**{admin_mention}\n\n{products_text}"
                            await thread.send(msg_content)
                            print(f"[CHECKOUT] ✅ Mensagem de entrega manual enviada com menção de admins")
                        elif not delivered_automatically:
                            # Se não há itens manuais mas também não foi entregue automaticamente (erro na entrega automática)
                            await thread.send(
                                f"{emoji.warn} **Houve um problema na entrega automática.** Por favor, entre em contato com um administrador.{admin_mention}"
                            )
                            print(f"[CHECKOUT] ⚠️ Mensagem de erro na entrega automática enviada")
                else:
                    # Se não tem user mas há itens manuais, ainda precisa mencionar admins
                    if len(manual_items) > 0:
                        print(f"[CHECKOUT] Enviando mensagem de entrega manual (sem user) para {len(manual_items)} itens")
                        products_list = []
                        for manual_item in manual_items:
                            product_name = manual_item.get("product_name", "Produto")
                            campo_name = manual_item.get("campo_name", "Campo")
                            qty = manual_item.get("quantity", 1)
                            products_list.append(f"{emoji.arrow} **{product_name}** - `{campo_name}` (x{qty})")
                        
                        products_text = "\n".join(products_list)
                        
                        msg_content = f"{emoji.warn} **Itens de entrega manual aguardando entrega.**{admin_mention}\n\n{products_text}"
                        await thread.send(msg_content)
                        print(f"[CHECKOUT] ✅ Mensagem de entrega manual enviada (sem user)")
            except Exception as e:
                print(f"[CHECKOUT] ❌ Erro ao enviar mensagens no tópico: {e}")
                import traceback
                traceback.print_exc()

            # Gerar e enviar transcript se habilitado (antes de deletar)
            try:
                from modules.loja.preferences.generate_transcript import generate_cart_transcript, send_cart_transcript_to_channel
                prefs = db.get_document("loja_preferences") or {}
                if prefs.get("transcript_enabled", False):
                    transcript_channel_id = prefs.get("transcript_channel_id")
                    if transcript_channel_id:
                        transcript_file = await generate_cart_transcript(thread, bot, cart)
                        if transcript_file:
                            await send_cart_transcript_to_channel(bot, transcript_file, int(transcript_channel_id), cart)
            except Exception as e:
                print(f"Erro ao gerar transcript: {e}")
                import traceback
                traceback.print_exc()
            
            # Arquivar thread apenas se houve entrega automática
            if delivered_automatically:
                await asyncio.sleep(300)
                await thread.edit(archived=True)
                # Deletar o tópico após arquivar
                try:
                    await asyncio.sleep(5)
                    await thread.delete()
                except Exception as e:
                    print(f"[CHECKOUT] Erro ao deletar thread: {e}")
            
            print(f"[CHECKOUT] Processamento de pagamento aprovado concluído para cart_id: {cart_id}")
        except Exception as e:
            import traceback
            print(f"[CHECKOUT] Erro no processamento de pagamento aprovado (dentro do try principal): {e}")
            traceback.print_exc()
        
    except Exception as e:
        import traceback
        print(f"[CHECKOUT] Erro crítico no processamento de pagamento aprovado: {e}")
        traceback.print_exc()
