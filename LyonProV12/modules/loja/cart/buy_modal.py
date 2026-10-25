import disnake
from disnake.ext import commands
from pathlib import Path
from functions.database import database as db
from functions.emoji import emoji
from functions.bool_utils import as_bool
from functions.plan import should_allow_payment_provider
from functions.payments.manual_payment import get_manual_pix_config
from typing import Optional, Union, Dict
from .stock_manager import StockManager
import time

# Cache simples para métodos de pagamento (TTL de 30 segundos)
_payment_methods_cache_buy = {"data": None, "timestamp": 0, "ttl": 30}


def invalidate_payment_methods_cache() -> None:
    _payment_methods_cache_buy["data"] = None
    _payment_methods_cache_buy["timestamp"] = 0


def ensure_emoji(emoji_value: Union[str, disnake.PartialEmoji, disnake.Emoji, None]) -> Union[str, disnake.PartialEmoji]:
    """
    Garante que o emoji seja convertido para PartialEmoji quando necessário.
    Isso permite que emojis de qualquer servidor funcionem em selects e botões.
    Se o emoji for inválido, retorna emoji.cardbox como fallback.
    """
    def _get_fallback():
        """Retorna o emoji.cardbox processado como fallback."""
        fallback = emoji.cardbox
        if isinstance(fallback, str) and fallback.startswith("<"):
            try:
                return disnake.PartialEmoji.from_str(fallback)
            except:
                pass
        return fallback
    
    # Se for None, usar fallback
    if emoji_value is None:
        return _get_fallback()
    
    # Se já for um objeto PartialEmoji ou Emoji, validar antes de retornar
    if isinstance(emoji_value, (disnake.PartialEmoji, disnake.Emoji)):
        try:
            if isinstance(emoji_value, disnake.Emoji):
                # Validar se tem dados necessários
                if not emoji_value.name or not emoji_value.id:
                    return _get_fallback()
                return disnake.PartialEmoji(name=emoji_value.name, id=emoji_value.id, animated=emoji_value.animated)
            else:
                # Validar PartialEmoji
                if not emoji_value.name or not emoji_value.id:
                    return _get_fallback()
                return emoji_value
        except Exception:
            # Se houver qualquer erro na validação, usar fallback
            return _get_fallback()
    
    # Se for string que começa com < (emoji customizado)
    if isinstance(emoji_value, str) and emoji_value.startswith("<"):
        try:
            # PartialEmoji.from_str funciona com emojis de qualquer servidor
            parsed = disnake.PartialEmoji.from_str(emoji_value)
            # Validar se foi parseado corretamente
            if not parsed.name or not parsed.id:
                return _get_fallback()
            return parsed
        except Exception:
            # Se falhar ao parsear, usar fallback
            return _get_fallback()
    
    # Se for string Unicode (emoji padrão), validar se não está vazia
    if isinstance(emoji_value, str):
        # Se string vazia ou só espaços, usar fallback
        if not emoji_value.strip():
            return _get_fallback()
        # Retornar como está (emoji Unicode válido)
        return emoji_value
    
    # Qualquer outro tipo inválido, usar fallback
    return _get_fallback()


def get_available_payment_methods() -> Dict[str, Dict[str, Union[str, disnake.PartialEmoji]]]:
    """Retorna os métodos de pagamento disponíveis e habilitados."""
    # Usar cache se ainda válido
    global _payment_methods_cache_buy
    current_time = time.time()
    if _payment_methods_cache_buy["data"] is not None and (current_time - _payment_methods_cache_buy["timestamp"]) < _payment_methods_cache_buy["ttl"]:
        return _payment_methods_cache_buy["data"]
    
    # Lista de provedores que estão "em breve" (não devem aparecer)
    providers_coming_soon = [
        "nubank", "inter", "bitcoin", "litecoin", "ethereum", "livepix", "promissepay"
    ]
    
    # Mapeamento de métodos de pagamento
    all_methods = {
        "pix": {
            "label": "PIX",
            "description": "Pagamento instantâneo via PIX",
            "emoji": emoji.pix,
            "providers": ["mercado_pago", "efibank", "pagbank", "picpay", "pushinpay", "misticpay", "nubank_imap", "picpay_imap", "itau_imap", "asaas", "pix_manual"]
        },
        "card": {
            "label": "Cartão de Crédito",
            "description": "Pagamento via cartão de crédito",
            "emoji": emoji.card,
            "providers": ["mercado_pago", "stripe", "efibank", "paypal", "asaas"]
        },
        "crypto": {
            "label": "Criptomoeda",
            "description": "Pagamento via criptomoedas",
            "emoji": emoji.coin,
            "providers": ["coinbase", "nowpayments"]
        }
    }
    
    # Verificar quais provedores estão habilitados
    pagamentos_doc = db.get_document("pagamentos") or {}
    payment_configs = db.get_document("payment_configs") or {}
    
    available: Dict[str, Dict[str, Union[str, disnake.PartialEmoji]]] = {}
    
    for method_key, method_info in all_methods.items():
        if method_key == "card" and not as_bool((payment_configs.get("card") or {}).get("enabled"), False):
            continue
        # Verificar se pelo menos um provedor deste método está habilitado e configurado
        has_provider = False
        for provider in method_info["providers"]:
            # Pular provedores "em breve"
            if provider in providers_coming_soon:
                continue

            if not should_allow_payment_provider(provider):
                continue
            
            provider_config = payment_configs.get(provider, {})
            
            # Verificar se está habilitado (pode estar em pagamentos_doc ou em payment_configs)
            is_enabled = False
            if isinstance(provider_config, dict):
                # Verificar se está habilitado no payment_configs
                is_enabled = as_bool(provider_config.get("enabled"), False)
            
            # Se não estiver habilitado no payment_configs, verificar no documento pagamentos
            if not is_enabled:
                is_enabled = as_bool(pagamentos_doc.get(provider), False)
            
            # Verificar se tem configuração válida (não vazia)
            has_valid_config = False
            if isinstance(provider_config, dict) and provider_config:
                # Verificar configuração específica para cada provedor
                if provider == "mercado_pago":
                    has_valid_config = bool(provider_config.get("access_token"))
                elif provider == "efibank":
                    cert_path = provider_config.get("cert_file")
                    cert_ok = bool(cert_path) and Path(cert_path).exists()
                    has_client = bool(provider_config.get("client_id") or provider_config.get("client"))
                    has_secret = bool(provider_config.get("client_secret") or provider_config.get("token"))
                    has_pix = bool(provider_config.get("pix_key"))
                    has_valid_config = bool(has_client and has_secret and has_pix and cert_ok)
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
                    # Fallback: verificar se tem pelo menos uma chave de configuração importante
                    important_keys = [
                        "access_token", "client_id", "client_secret", "api_key",
                        "public_key", "secret_key", "token", "pix_key"
                    ]
                    has_valid_config = any(provider_config.get(key) for key in important_keys)
            
            if is_enabled and has_valid_config:
                has_provider = True
                break
        
        if has_provider:
            available[method_key] = {
                "label": method_info["label"],
                "description": method_info["description"],
                "emoji": method_info["emoji"],
            }
    
    # Atualizar cache
    _payment_methods_cache_buy["data"] = available
    _payment_methods_cache_buy["timestamp"] = current_time
    
    return available


class BuyProductModal(disnake.ui.Modal):
    """Modal para seleção de campo, quantidade e método de pagamento"""
    
    def _get_available_payment_methods(self) -> dict:
        """Wrapper para manter compatibilidade com o código antigo."""
        return get_available_payment_methods()
    
    def __init__(self, product_id: str, campo_id: Optional[str] = None):
        self.product_id = product_id
        self.campo_id = campo_id
        
        # Carregar informações do produto
        products = db.get_document("loja_products")
        product = products.get(product_id, {})
        product_name = product.get("name", "Produto")
        info = product.get("info") or {}
        delivery_type = info.get("delivery_type", "automatic")
        campos_all = product.get("campos", {})
        
        # Componentes do modal
        components = []
        
        # Se tem múltiplos campos e não foi especificado um, adicionar seletor
        if len(campos_all) > 1 and not campo_id:
            campo_options = []
            for cid, campo in campos_all.items():
                campo_name = campo.get("name", "Campo")
                campo_price = campo.get("price", 0)
                price_str = f"R$ {campo_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                
                # Obter estoque do sistema centralizado
                stock_count = StockManager.get_available_stock(product_id, cid)
                # Verificar se é estoque infinito (999999 indica infinito)
                is_infinite = stock_count == 999999
                
                # Descrição com preço e estoque
                if is_infinite:
                    description = f"{price_str} | Estoque: Infinito"
                else:
                    description = f"{price_str} | Estoque: {stock_count}"
                
                # Processar emoji do campo usando ensure_emoji para garantir compatibilidade
                campo_emoji_raw = campo.get("emoji")
                campo_emoji = ensure_emoji(campo_emoji_raw)
                
                campo_options.append(
                    disnake.SelectOption(
                        label=campo_name,
                        value=cid,
                        description=description[:100],  # Discord limita a 100 caracteres
                        emoji=campo_emoji
                    )
                )
            
            # Só adicionar o select se houver pelo menos uma opção válida
            if campo_options:
                # Limitar a 25 opções (máximo do Discord)
                campo_options_limited = campo_options[:25]
                components.append(
                    disnake.ui.Label(
                        text="Selecione o Campo",
                        component=disnake.ui.StringSelect(
                            placeholder="Escolha uma opção",
                            custom_id="campo_select",
                            options=campo_options_limited,
                            required=True,
                        ),
                        description="Escolha qual item deseja comprar"
                    )
                )
        
        # Determinar campo selecionado para calcular estoque
        campo_sel_id = campo_id if campo_id and campo_id != "none" else (list(campos_all.keys())[0] if campos_all else None)
        stock_count = StockManager.get_available_stock(product_id, campo_sel_id) if campo_sel_id else 0
        # Verificar se é estoque infinito (999999 indica infinito)
        is_infinite_preview = stock_count == 999999
        max_qty = 99 if delivery_type != "automatic" else (99 if is_infinite_preview else stock_count)
        
        # Campo de quantidade
        components.append(
            disnake.ui.Label(
                text="Quantidade",
                component=disnake.ui.TextInput(
                    placeholder=f"Digite a quantidade (máx: {max_qty if max_qty > 0 else 0})",
                    custom_id="quantity",
                    style=disnake.TextInputStyle.short,
                    required=True,
                    min_length=1,
                    max_length=2,
                    value="1"
                ),
            )
        )
        
        # Verificar métodos de pagamento disponíveis
        available_methods = self._get_available_payment_methods()
        
        # Se não houver métodos disponíveis, não criar o modal
        if not available_methods:
            # Será tratado no listener do botão
            self.no_payment_methods = True
        else:
            self.no_payment_methods = False
        
        # ArmaLyonar método único (se houver apenas um)
        self.single_payment_method = None
        
        # Só adicionar select se houver mais de um método
        if len(available_methods) > 1:
            payment_options = []
            for method_key, method_info in available_methods.items():
                # Garantir que o emoji seja convertido para PartialEmoji quando necessário
                payment_emoji = ensure_emoji(method_info["emoji"])
                payment_options.append(
                    disnake.SelectOption(
                        label=method_info["label"],
                        value=method_key,
                        description=method_info["description"],
                        emoji=payment_emoji
                    )
                )
            
            components.append(
                disnake.ui.Label(
                    text="Método de Pagamento",
                    component=disnake.ui.StringSelect(
                        placeholder="Selecione o método de pagamento",
                        custom_id="payment_method",
                        options=payment_options,
                        required=True,
                    ),
                    description="Escolha como deseja pagar"
                )
            )
        elif len(available_methods) == 1:
            # Se só tem um método, usar automaticamente
            self.single_payment_method = list(available_methods.keys())[0]
        
        # Título do modal
        title = f"Comprar: {product_name}"
        
        super().__init__(
            title=title[:45],  # Discord limita a 45 caracteres
            components=components,
            custom_id=f"buy_product_modal:{product_id}:{campo_id or 'none'}"
        )
    
    async def callback(self, inter: disnake.ModalInteraction):
        """Processar a compra após o modal ser enviado"""
        # Fazer defer imediatamente para não expirar a interação durante verificações aLyon
        if not inter.response.is_done():
            await inter.response.defer(ephemeral=True)
        
        # Mostrar mensagem de carregamento enquanto verifica
        loading_msg = await inter.followup.send(f"{emoji.loading} Verificando informações...", ephemeral=True)
        
        # Verificações LENTAS (manutenção, horário, verificação OAuth2)
        try:
            # Verificar se está em manutenção
            from modules.loja.preferences.utils import check_maintenance
            is_maintenance, maintenance_msg = check_maintenance(inter.user.id, inter.guild)
            if is_maintenance:
                await loading_msg.edit(content=maintenance_msg or "🔧 Sistema em manutenção. Por favor, tente novamente mais tarde.")
                return
            
            # Verificar horário de funcionamento
            from modules.loja.preferences.utils import check_store_hours
            is_open, hours_msg = check_store_hours()
            if not is_open:
                await loading_msg.edit(content=hours_msg or "⏰ A loja está fora do horário de funcionamento.")
                return
            
            # Verificar se a verificação OAuth2 é obrigatória
            from modules.cloud.verification_check import is_verification_required, send_verification_required_message, is_user_verified
            
            if is_verification_required():
                # Verificar se o usuário está verificado antes de processar a compra
                if isinstance(inter.user, disnake.Member):
                    member = inter.user
                elif inter.guild:
                    member = inter.guild.get_member(inter.user.id)
                else:
                    member = None
                
                if member:
                    verified = await is_user_verified(member)
                    if not verified:
                        # Deletar mensagem de loading e enviar mensagem de verificação
                        try:
                            await loading_msg.delete()
                        except:
                            pass
                        await send_verification_required_message(inter)
                        return
        except Exception as e:
            # Se houver erro na verificação, continuar normalmente (não bloquear)
            print(f"Erro ao verificar no modal de compra: {e}")
        
        # Deletar mensagem de loading antes de continuar
        try:
            await loading_msg.delete()
        except:
            pass
        
        from .checkout import create_checkout
        
        valores = inter.resolved_values
        
        # Obter campo selecionado (se houver seletor)
        campo_select_value = valores.get("campo_select")
        if campo_select_value:
            # Se é uma lista, pegar o primeiro item
            if isinstance(campo_select_value, (list, tuple)):
                selected_campo_id = campo_select_value[0] if campo_select_value else None
            else:
                selected_campo_id = campo_select_value
        else:
            # Usar o campo_id passado no construtor ou o primeiro campo
            products = db.get_document("loja_products")
            product = products.get(self.product_id, {})
            campos_all = product.get("campos", {})
            selected_campo_id = self.campo_id if self.campo_id and self.campo_id != "none" else (list(campos_all.keys())[0] if campos_all else None)
        
        if not selected_campo_id:
            await inter.followup.send(
                f"{emoji.wrong} Erro ao identificar o campo selecionado!",
                ephemeral=True
            )
            return
        
        # Obter quantidade
        quantity_str = valores.get("quantity", "1")
        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                raise ValueError("Quantidade deve ser maior que 0")
            if quantity >= 100:
                raise ValueError("Quantidade deve ter no máximo 2 dígitos")
        except ValueError:
            await inter.followup.send(
                f"{emoji.wrong} Quantidade inválida! Digite um número válido.",
                ephemeral=True
            )
            return
        
        # Validar limite baseado no estoque e tipo de entrega
        products = db.get_document("loja_products")
        product = products.get(self.product_id, {})
        info = product.get("info") or {}
        delivery_type = info.get("delivery_type", "automatic")
        
        # Obter estoque do sistema centralizado
        stock_count = StockManager.get_available_stock(self.product_id, selected_campo_id)
        # Verificar se é estoque infinito (999999 indica infinito)
        is_infinite = stock_count == 999999
        
        # Definir máximo permitido
        if delivery_type != "automatic":
            max_qty = 99
        else:
            max_qty = 99 if is_infinite else int(stock_count)

        # Bloquear compra automática sem estoque (exceto quando infinito)
        if delivery_type == "automatic" and not is_infinite and int(stock_count) <= 0:
            # Criar botão de notificação (apenas emoji, sem label) - garantir compatibilidade com emojis de qualquer servidor
            notify_emoji = ensure_emoji(emoji.warn)
            notify_button = disnake.ui.Button(
                emoji=notify_emoji,
                label="Receber notificação ao repor estoque",
                style=disnake.ButtonStyle.grey,
                custom_id=f"notify_stock:{self.product_id}:{selected_campo_id}"
            )
            
            # Enviar mensagem não-ephemeral para poder editar depois
            await inter.followup.send(
                content=f"{emoji.wrong} Sem estoque disponível para este item.",
                components=[disnake.ui.ActionRow(notify_button)],
                ephemeral=True
            )
            return

        if quantity > max_qty:
            await inter.followup.send(
                f"{emoji.wrong} Quantidade indisponível. Máximo permitido: {max_qty}.",
                ephemeral=True,
            )
            return

        # Obter método de pagamento
        if self.single_payment_method:
            # Se só tem um método, usar automaticamente
            payment_method = self.single_payment_method
        else:
            # Obter do select
            payment_method_value = valores.get("payment_method", "")
            if isinstance(payment_method_value, (list, tuple)):
                payment_method = payment_method_value[0] if payment_method_value else None
            else:
                payment_method = payment_method_value or None
            
            if not payment_method:
                await inter.followup.send(
                    f"{emoji.wrong} Selecione um método de pagamento!",
                    ephemeral=True
                )
                return
        
        # Criar checkout sem cupom (cupom será aplicado no carrinho)
        await create_checkout(
            inter=inter,
            product_id=self.product_id,
            campo_id=selected_campo_id,
            quantity=quantity,
            payment_method=payment_method,
            coupon_code=None  # Cupom será aplicado no carrinho
        )


async def _validate_before_cart_creation(
    inter: disnake.MessageInteraction,
    product_id: str,
    campo_id: str,
) -> tuple[bool, Optional[str], Optional[Dict]]:
    """
    Valida TUDO antes de criar o carrinho.
    Retorna: (success, error_message, cart_data_dict)
    Se success=True, cart_data_dict contém todos os dados necessários para criar o carrinho.
    """
    # 1. Verificar manutenção
    try:
        from modules.loja.preferences.utils import check_maintenance
        is_maintenance, maintenance_msg = check_maintenance(inter.user.id, inter.guild)
        if is_maintenance:
            return False, maintenance_msg or "🔧 Sistema em manutenção. Por favor, tente novamente mais tarde.", None
    except Exception as e:
        print(f"Erro ao verificar manutenção: {e}")
        # Continuar mesmo com erro na verificação
    
    # 2. Verificar horário de funcionamento
    try:
        from modules.loja.preferences.utils import check_store_hours
        is_open, hours_msg = check_store_hours()
        if not is_open:
            return False, hours_msg or "⏰ A loja está fora do horário de funcionamento.", None
    except Exception as e:
        print(f"Erro ao verificar horário: {e}")
        # Continuar mesmo com erro na verificação
    
    # 3. Verificar verificação OAuth2
    try:
        from modules.cloud.verification_check import is_verification_required, is_user_verified
        if is_verification_required():
            if isinstance(inter.user, disnake.Member):
                member = inter.user
            elif inter.guild:
                member = inter.guild.get_member(inter.user.id)
            else:
                member = None
            
            if member:
                verified = await is_user_verified(member)
                if not verified:
                    return False, None, None  # Será tratado pelo send_verification_required_message
    except Exception as e:
        print(f"Erro ao verificar OAuth2: {e}")
        # Continuar mesmo com erro na verificação
    
    # 4. Carregar e validar produto
    products = db.get_document("loja_products")
    product = products.get(product_id, {})
    if not product:
        return False, f"{emoji.wrong} Produto não encontrado.", None
    
    campos = product.get("campos", {})
    campo = campos.get(campo_id)
    if not campo:
        return False, f"{emoji.wrong} Campo não encontrado para este produto.", None
    
    info = product.get("info") or {}
    delivery_type = info.get("delivery_type", "automatic")
    price = campo.get("price", 0)
    
    # 5. Validar estoque
    stock_count = StockManager.get_available_stock(product_id, campo_id)
    is_infinite = stock_count == 999999
    
    if delivery_type == "automatic" and not is_infinite and int(stock_count) <= 0:
        # Retornar flag especial para mostrar botão de notificação
        return False, "NO_STOCK", {"product_id": product_id, "campo_id": campo_id}
    
    # 6. Verificar métodos de pagamento
    available_methods = get_available_payment_methods()
    if not available_methods:
        return False, f"{emoji.wrong} Nenhum método de pagamento está disponível no momento. Entre em contato com um administrador.", None
    
    # 7. Escolher método padrão
    if "pix" in available_methods:
        payment_method = "pix"
    else:
        payment_method = next(iter(available_methods.keys()))
    
    # 8. Preparar dados do carrinho
    quantity = 1  # Quantidade padrão
    cart_data = {
        "product_id": product_id,
        "campo_id": campo_id,
        "quantity": quantity,
        "price": price,
        "payment_method": payment_method,
        "delivery_type": delivery_type,
        "product": product,
        "campo": campo,
    }
    
    return True, None, cart_data


async def _add_product_to_cart_from_interaction(
    inter: disnake.MessageInteraction,
    product_id: str,
    campo_id: str,
    loading_msg: Optional[disnake.Message] = None,
) -> None:
    """Adiciona um produto (campo específico) ao carrinho com quantidade 1."""
    from .checkout import create_checkout
    
    # VALIDAR TUDO ANTES DE CRIAR O CARRINHO
    success, error_msg, cart_data = await _validate_before_cart_creation(inter, product_id, campo_id)
    
    if not success:
        # Tratar verificação OAuth2 separadamente
        if error_msg is None:
            # Usar a mesma mensagem e botão de verificação que os tickets usam
            from modules.cloud.verification_check import get_verification_message_and_view, send_verification_required_message
            
            message_text, view = get_verification_message_and_view(inter)
            
            # Editar mensagem de loading se existir
            if loading_msg:
                try:
                    if message_text and view:
                        await loading_msg.edit(
                            content=message_text,
                            view=view
                        )
                    else:
                        await loading_msg.edit(
                            content="Esse servidor requer que você seja verificado para usar algumas funcionalidades."
                        )
                except:
                    pass
            else:
                try:
                    await send_verification_required_message(inter)
                except:
                    # Fallback se a função falhar
                    fallback_msg = "Esse servidor requer que você seja verificado para usar algumas funcionalidades."
                    if inter.response.is_done():
                        await inter.followup.send(
                            fallback_msg,
                            ephemeral=True,
                            view=view if view else None
                        )
                    else:
                        await inter.response.send_message(
                            fallback_msg,
                            ephemeral=True,
                            view=view if view else None
                        )
            return
        
        # Tratar estoque sem disponibilidade
        if error_msg == "NO_STOCK":
            notify_emoji = ensure_emoji(emoji.warn)
            notify_button = disnake.ui.Button(
                emoji=notify_emoji,
                label="Receber notificação ao repor estoque",
                style=disnake.ButtonStyle.grey,
                custom_id=f"notify_stock:{cart_data['product_id']}:{cart_data['campo_id']}"
            )
            
            # Editar mensagem de loading se existir
            if loading_msg:
                try:
                    await loading_msg.edit(
                        content=f"{emoji.wrong} Sem estoque disponível para este item.",
                        components=[disnake.ui.ActionRow(notify_button)]
                    )
                except:
                    # Se não conseguir editar, enviar nova mensagem
                    await inter.followup.send(
                        content=f"{emoji.wrong} Sem estoque disponível para este item.",
                        components=[disnake.ui.ActionRow(notify_button)],
                        ephemeral=True
                    )
            else:
                if inter.response.is_done():
                    await inter.followup.send(
                        content=f"{emoji.wrong} Sem estoque disponível para este item.",
                        components=[disnake.ui.ActionRow(notify_button)],
                        ephemeral=True
                    )
                else:
                    await inter.response.send_message(
                        content=f"{emoji.wrong} Sem estoque disponível para este item.",
                        components=[disnake.ui.ActionRow(notify_button)],
                        ephemeral=True
                    )
            return
        
        # Outros erros - editar mensagem de loading se existir
        if loading_msg:
            try:
                await loading_msg.edit(content=error_msg)
            except:
                if inter.response.is_done():
                    await inter.followup.send(error_msg, ephemeral=True)
                else:
                    await inter.response.send_message(error_msg, ephemeral=True)
        else:
            if inter.response.is_done():
                await inter.followup.send(error_msg, ephemeral=True)
            else:
                await inter.response.send_message(error_msg, ephemeral=True)
        return
    
    # Tudo validado! Criar carrinho com dados já preparados
    # Passar loading_msg para create_checkout editar ao invés de criar nova mensagem
    await create_checkout(
        inter=inter,
        product_id=cart_data["product_id"],
        campo_id=cart_data["campo_id"],
        quantity=cart_data["quantity"],
        payment_method=cart_data["payment_method"],
        coupon_code=None,
        loading_msg=loading_msg,  # Passar mensagem de loading para editar
    )


def _format_brl(value: float) -> str:
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _field_option(product_id: str, campo_id: str, campo: dict) -> disnake.SelectOption:
    campo_name = str(campo.get("name") or "Campo")[:100]
    stock_count = StockManager.get_available_stock(product_id, campo_id)
    stock_text = "Infinito" if stock_count == 999999 else str(stock_count)
    description = f"{_format_brl(campo.get('price', 0))} | Estoque: {stock_text}"
    return disnake.SelectOption(
        label=campo_name,
        value=campo_id,
        description=description[:100],
        emoji=ensure_emoji(campo.get("emoji")),
    )


def _category_groups(product: dict, campos: dict) -> list[tuple[str, dict, list[tuple[str, dict]]]]:
    categorias = product.get("categorias") or {}
    groups = []
    used_field_ids = set()

    for category_id, category in categorias.items():
        category_fields = [
            (campo_id, campo)
            for campo_id, campo in campos.items()
            if campo.get("category_id") == category_id
        ]
        if category_fields:
            groups.append((str(category_id), category or {}, category_fields))
            used_field_ids.update(campo_id for campo_id, _ in category_fields)

    uncategorized = [
        (campo_id, campo)
        for campo_id, campo in campos.items()
        if campo_id not in used_field_ids
    ]
    if uncategorized:
        groups.append(("sem_categoria", {"name": "Sem categoria", "emoji": emoji.cardbox}, uncategorized))

    return groups


def _category_select_rows(product_id: str, groups: list[tuple[str, dict, list[tuple[str, dict]]]]) -> list[disnake.ui.ActionRow]:
    rows = []
    for category_id, category, fields in groups[:5]:
        category_name = str(category.get("name") or "Categoria")[:80]
        options = [_field_option(product_id, campo_id, campo) for campo_id, campo in fields[:25]]
        rows.append(
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    placeholder=f"{category_name} - selecione uma opção...",
                    custom_id=f"buy_product_select_category_field:{product_id}:{category_id}",
                    options=options,
                )
            )
        )
    return rows


def _category_picker_row(product_id: str, groups: list[tuple[str, dict, list[tuple[str, dict]]]]) -> disnake.ui.ActionRow:
    options = []
    for category_id, category, fields in groups[:25]:
        category_name = str(category.get("name") or "Categoria")[:100]
        options.append(
            disnake.SelectOption(
                label=category_name,
                value=category_id,
                description=f"{len(fields)} opção(ões) disponível(is)"[:100],
                emoji=ensure_emoji(category.get("emoji")),
            )
        )

    return disnake.ui.ActionRow(
        disnake.ui.StringSelect(
            placeholder="Selecione uma categoria para continuar...",
            custom_id=f"buy_product_select_category:{product_id}",
            options=options,
        )
    )


async def _send_purchase_selects(inter: disnake.MessageInteraction, product_id: str, product: dict, campos: dict) -> None:
    groups = _category_groups(product, campos)

    if groups and (product.get("categorias") or {}):
        if len(groups) <= 5:
            rows = _category_select_rows(product_id, groups)
            content = f"{emoji.cart} **Escolha uma opção do produto:**\n-# Cada select abaixo representa uma categoria configurada pelo vendedor."
        else:
            rows = [_category_picker_row(product_id, groups)]
            content = f"{emoji.cart} **Escolha uma categoria para continuar:**\n-# Este produto possui muitas categorias, então primeiro selecione a categoria."
    else:
        options = [_field_option(product_id, campo_id, campo) for campo_id, campo in list(campos.items())[:25]]
        rows = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    placeholder="Selecione uma opção para continuar...",
                    custom_id=f"buy_product_select_field:{product_id}",
                    options=options,
                )
            )
        ]
        content = None

    await inter.followup.send(content=content, components=rows, ephemeral=True)


async def _send_category_field_select(inter: disnake.MessageInteraction, product_id: str, category_id: str) -> None:
    products = db.get_document("loja_products") or {}
    product = products.get(product_id) or {}
    campos = product.get("campos") or {}
    groups = _category_groups(product, campos)
    group = next((item for item in groups if item[0] == category_id), None)

    if not product or not group:
        await inter.followup.send(f"{emoji.wrong} Categoria não encontrada para este produto.", ephemeral=True)
        return

    category_id, category, fields = group
    category_name = str(category.get("name") or "Categoria")[:80]
    rows = _category_select_rows(product_id, [group])
    await inter.followup.send(
        content=f"{emoji.cart} **{category_name}**\n-# Selecione uma opção para continuar.",
        components=rows,
        ephemeral=True,
    )


class BuyProductButton(commands.Cog):
    """Listener para botões de compra e notificações de estoque"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener("on_button_click")
    async def on_buy_button_click(self, inter: disnake.MessageInteraction):
        """Listener corrigido para botões de compra com defer apropriado"""
        try:
            custom_id = inter.component.custom_id
            
            # ========== HANDLER NOTIFICAÇÕES DE ESTOQUE ==========
            if custom_id.startswith("disable_stock_notification:"):
                try:
                    await inter.response.defer(ephemeral=True)
                    
                    parts = custom_id.split(":")
                    product_id = parts[1] if len(parts) >= 2 else None
                    campo_id = parts[2] if len(parts) >= 3 else None
                    
                    if not product_id or not campo_id:
                        await inter.followup.send(f"{emoji.wrong} Erro ao processar desativação.", ephemeral=True)
                        return
                    
                    notifications_doc = db.get_document("loja_stock_notifications") or {}
                    notifications = notifications_doc.get("notifications", {})
                    
                    user_id_str = str(inter.user.id)
                    notification_key = f"{user_id_str}:{product_id}:{campo_id}"
                    
                    if notification_key in notifications:
                        del notifications[notification_key]
                        notifications_doc["notifications"] = notifications
                        db.save_document("loja_stock_notifications", notifications_doc)
                        message_text = f"{emoji.correct} Notificação de estoque desativada com sucesso!"
                    else:
                        message_text = f"{emoji.wrong} Você não possui notificação ativa para este produto."
                    
                    await inter.followup.send(message_text, ephemeral=True)
                except Exception as e:
                    print(f"[BUY] Erro ao desativar notificação: {e}")
                    if not inter.response.is_done():
                        await inter.response.defer(ephemeral=True)
                    await inter.followup.send(f"{emoji.wrong} Erro ao processar requisição.", ephemeral=True)
                return
            
            if custom_id.startswith("notify_stock:"):
                try:
                    await inter.response.defer(ephemeral=True)
                    
                    parts = custom_id.split(":")
                    product_id = parts[1] if len(parts) >= 2 else None
                    campo_id = parts[2] if len(parts) >= 3 else None
                    
                    if not product_id or not campo_id:
                        await inter.followup.send(f"{emoji.wrong} Erro ao processar notificação.", ephemeral=True)
                        return
                    
                    notifications_doc = db.get_document("loja_stock_notifications") or {}
                    notifications = notifications_doc.get("notifications", {})
                    
                    user_id_str = str(inter.user.id)
                    notification_key = f"{user_id_str}:{product_id}:{campo_id}"
                    
                    if notification_key in notifications:
                        del notifications[notification_key]
                        notifications_doc["notifications"] = notifications
                        db.save_document("loja_stock_notifications", notifications_doc)
                        message_text = f"{emoji.wrong} Notificação de estoque cancelada. Você não será notificado quando o estoque for reposto."
                    else:
                        notifications[notification_key] = {
                            "user_id": user_id_str,
                            "product_id": product_id,
                            "campo_id": campo_id,
                            "created_at": int(disnake.utils.utcnow().timestamp()),
                            "notified": False
                        }
                        notifications_doc["notifications"] = notifications
                        db.save_document("loja_stock_notifications", notifications_doc)
                        message_text = f"{emoji.correct} Você será notificado quando o estoque deste produto estiver disponível!"
                    
                    await inter.followup.send(message_text, ephemeral=True)
                except Exception as e:
                    print(f"[BUY] Erro ao registrar notificação: {e}")
                    if not inter.response.is_done():
                        await inter.response.defer(ephemeral=True)
                    await inter.followup.send(f"{emoji.wrong} Erro ao processar requisição.", ephemeral=True)
                return
            
            # ========== HANDLER BOTÃO COMPRAR ==========
            if custom_id.startswith("buy_product:"):
                try:
                    # PASSO 1: Defer imediatamente para não expirar
                    if not inter.response.is_done():
                        await inter.response.defer(ephemeral=True)
                    
                    parts = custom_id.split(":", 2)
                    product_id = parts[1] if len(parts) >= 2 else None
                    campo_id = parts[2] if len(parts) >= 3 else None
                    
                    if not product_id:
                        print(f"[BUY] Erro: product_id não encontrado em {custom_id}")
                        await inter.followup.send(f"{emoji.wrong} Erro ao processar compra.", ephemeral=True)
                        return
                    
                    print(f"[BUY] Botão clicado - product_id: {product_id}, campo_id: {campo_id}, user: {inter.user.name}")
                    
                    # PASSO 2: Carregar produto e campos
                    products = db.get_document("loja_products") or {}
                    product = products.get(product_id, {})
                    campos = product.get("campos", {})
                    
                    if not product:
                        print(f"[BUY] Produto não encontrado: {product_id}")
                        await inter.followup.send(f"{emoji.wrong} Produto não encontrado.", ephemeral=True)
                        return
                    
                    if not campos:
                        print(f"[BUY] Nenhum campo configurado: {product_id}")
                        await inter.followup.send(f"{emoji.wrong} Não há campos configurados para este produto.", ephemeral=True)
                        return
                    
                    # PASSO 3: Se já veio um campo específico, adicionar direto
                    if campo_id:
                        print(f"[BUY] Campo específico fornecido, adicionando ao carrinho: {campo_id}")
                        await _add_product_to_cart_from_interaction(inter, product_id, campo_id, None)
                        return
                    
                    # PASSO 4: Se só tem um campo, usar diretamente
                    if len(campos) == 1:
                        only_campo_id = next(iter(campos.keys()))
                        print(f"[BUY] Apenas um campo existe, usando: {only_campo_id}")
                        await _add_product_to_cart_from_interaction(inter, product_id, only_campo_id, None)
                        return
                    
                    # PASSO 5: Múltiplos campos - criar selects por categoria quando configurado
                    print(f"[BUY] Criando selects de compra com {len(campos)} opções")
                    await _send_purchase_selects(inter, product_id, product, campos)
                    print(f"[BUY] Select enviado com sucesso")
                
                except Exception as e:
                    print(f"[BUY] Erro ao processar botão comprar: {e}")
                    import traceback
                    traceback.print_exc()
                    if not inter.response.is_done():
                        await inter.response.defer(ephemeral=True)
                    await inter.followup.send(f"{emoji.wrong} Erro ao processar sua compra. Tente novamente.", ephemeral=True)
                return
        
        except Exception as e:
            print(f"[BUY] Erro não tratado no on_buy_button_click: {e}")
            import traceback
            traceback.print_exc()
            try:
                if not inter.response.is_done():
                    await inter.response.defer(ephemeral=True)
                await inter.followup.send(f"{emoji.wrong} Erro ao processar requisição.", ephemeral=True)
            except:
                pass
    
    @commands.Cog.listener("on_dropdown")
    async def on_buy_dropdown(self, inter: disnake.MessageInteraction):
        """Handler para selects relacionados à compra (campos de produto) - CORRIGIDO"""
        try:
            custom_id = inter.component.custom_id or ""

            if custom_id == "buy_product_panel_select":
                try:
                    product_id = inter.values[0] if inter.values else None
                    if not product_id or product_id == "invalid":
                        await inter.response.defer(ephemeral=True)
                        await inter.followup.send(f"{emoji.wrong} Produto invalido.", ephemeral=True)
                        return

                    await inter.response.defer(ephemeral=True)

                    products = db.get_document("loja_products") or {}
                    product = products.get(product_id, {})
                    campos = product.get("campos", {})

                    if not product:
                        await inter.followup.send(f"{emoji.wrong} Produto nao encontrado.", ephemeral=True)
                        return

                    if not campos:
                        await inter.followup.send(f"{emoji.wrong} Nao ha campos configurados para este produto.", ephemeral=True)
                        return

                    if len(campos) == 1:
                        only_campo_id = next(iter(campos.keys()))
                        await _add_product_to_cart_from_interaction(inter, product_id, only_campo_id, None)
                        return

                    await _send_purchase_selects(inter, product_id, product, campos)
                except Exception as e:
                    print(f"[SELECT] Erro ao processar painel de produto: {e}")
                    import traceback
                    traceback.print_exc()
                    if not inter.response.is_done():
                        await inter.response.defer(ephemeral=True)
                    await inter.followup.send(f"{emoji.wrong} Erro ao processar sua compra.", ephemeral=True)
                return

            if custom_id.startswith("buy_product_select_category:"):
                try:
                    parts = custom_id.split(":", 1)
                    product_id = parts[1] if len(parts) == 2 else None
                    category_id = inter.values[0] if inter.values else None

                    if not product_id or not category_id:
                        await inter.response.defer(ephemeral=True)
                        await inter.followup.send(f"{emoji.wrong} Erro ao processar categoria.", ephemeral=True)
                        return

                    print(f"[SELECT] Categoria selecionada - product: {product_id}, category: {category_id}, user: {inter.user.name}")
                    await inter.response.defer(ephemeral=True)
                    await _send_category_field_select(inter, product_id, category_id)
                except Exception as e:
                    print(f"[SELECT] Erro ao processar categoria: {e}")
                    import traceback
                    traceback.print_exc()
                    if not inter.response.is_done():
                        await inter.response.defer(ephemeral=True)
                    await inter.followup.send(f"{emoji.wrong} Erro ao processar sua categoria.", ephemeral=True)
                return

            if custom_id.startswith("buy_product_select_category_field:"):
                try:
                    parts = custom_id.split(":", 2)
                    product_id = parts[1] if len(parts) >= 2 else None

                    if not product_id:
                        print(f"[SELECT] Erro: product_id não encontrado em {custom_id}")
                        await inter.response.defer(ephemeral=True)
                        await inter.followup.send(f"{emoji.wrong} Erro ao processar seleção.", ephemeral=True)
                        return

                    campo_id = inter.values[0] if inter.values else None
                    if not campo_id:
                        print(f"[SELECT] Campo inválido selecionado por {inter.user.name}")
                        await inter.response.defer(ephemeral=True)
                        await inter.followup.send(f"{emoji.wrong} Campo inválido selecionado.", ephemeral=True)
                        return

                    print(f"[SELECT] Campo de categoria selecionado - product: {product_id}, campo: {campo_id}, user: {inter.user.name}")
                    await inter.response.defer(ephemeral=True)
                    await _add_product_to_cart_from_interaction(inter, product_id, campo_id, None)
                except Exception as e:
                    print(f"[SELECT] Erro ao processar campo de categoria: {e}")
                    import traceback
                    traceback.print_exc()
                    if not inter.response.is_done():
                        await inter.response.defer(ephemeral=True)
                    await inter.followup.send(f"{emoji.wrong} Erro ao processar sua seleção.", ephemeral=True)
                return
            
            if custom_id.startswith("buy_product_select_field:"):
                try:
                    parts = custom_id.split(":", 1)
                    product_id = parts[1] if len(parts) == 2 else None
                    
                    if not product_id:
                        print(f"[SELECT] Erro: product_id não encontrado em {custom_id}")
                        await inter.response.defer(ephemeral=True)
                        await inter.followup.send(f"{emoji.wrong} Erro ao processar seleção.", ephemeral=True)
                        return
                    
                    campo_id = inter.values[0] if inter.values else None
                    if not campo_id:
                        print(f"[SELECT] Campo inválido selecionado por {inter.user.name}")
                        await inter.response.defer(ephemeral=True)
                        await inter.followup.send(f"{emoji.wrong} Campo inválido selecionado.", ephemeral=True)
                        return
                    
                    print(f"[SELECT] Campo selecionado - product: {product_id}, campo: {campo_id}, user: {inter.user.name}")
                    
                    # Fazer defer imediatamente para não expirar
                    await inter.response.defer(ephemeral=True)
                    
                    # Adicionar ao carrinho usando followup
                    await _add_product_to_cart_from_interaction(inter, product_id, campo_id, None)
                    
                except Exception as e:
                    print(f"[SELECT] Erro ao processar select: {e}")
                    import traceback
                    traceback.print_exc()
                    if not inter.response.is_done():
                        await inter.response.defer(ephemeral=True)
                    await inter.followup.send(f"{emoji.wrong} Erro ao processar sua seleção.", ephemeral=True)
                return
        
        except Exception as e:
            print(f"[SELECT] Erro não tratado no on_buy_dropdown: {e}")
            import traceback
            traceback.print_exc()
            try:
                if not inter.response.is_done():
                    await inter.response.defer(ephemeral=True)
                await inter.followup.send(f"{emoji.wrong} Erro ao processar requisição.", ephemeral=True)
            except:
                pass


def setup(bot: commands.Bot):
    bot.add_cog(BuyProductButton(bot))
