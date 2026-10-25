from disnake.ext import commands
import disnake
import json
from pathlib import Path
import aiohttp

from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from functions.bool_utils import as_bool
from functions import plan


class ConfigurarPagamentos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _providers():
        return {
            "pix_manual": ("Pagamento Manual", getattr(emoji, "pix", None)),
            "mercado_pago": ("Mercado Pago", getattr(emoji, "mercado_pago", None)),
            "efibank": ("Efi Bank", getattr(emoji, "efi_bank", None)),
            "pushinpay": ("Pushin Pay", getattr(emoji, "pushin_pay", None)),
            "misticpay": ("MisticPay", getattr(emoji, "pix", None)),
            "promissepay": ("PromissePay (Em breve)", getattr(emoji, "wallet", None)),
            "Lyon_wallet": ("Carteira", getattr(emoji, "carteira", getattr(emoji, "wallet", None))),
            "livepix": ("Live Pix (Em breve)", getattr(emoji, "wallet", None)),
            "pagbank": ("PagBank", getattr(emoji, "pagbank", None)),
            "picpay": ("PicPay API", getattr(emoji, "picpay", None)),
            "picpay_imap": ("PicPay", getattr(emoji, "picpay", None)),
            "stripe": ("Stripe", getattr(emoji, "stripe", None)),
            "nowpayments": ("NowPayments", getattr(emoji, "wallet", None)),
            "coinbase": ("Coinbase", getattr(emoji, "wallet", None)),
            "asaas": ("Asaas", getattr(emoji, "card", None)),
            "paypal": ("PayPal", getattr(emoji, "wallet", None)),
            "nubank": ("Nubank Antigo", getattr(emoji, "bank", None)),
            "nubank_imap": ("Nubank", getattr(emoji, "nubank", getattr(emoji, "bank", None))),
            "itau_imap": ("Itau", getattr(emoji, "itauE", getattr(emoji, "bank", None))),
            "inter": ("Inter (Em breve)", getattr(emoji, "bank", None)),
            "card": ("Cartao", getattr(emoji, "card", None)),
            "bitcoin": ("Bitcoin (Em breve)", getattr(emoji, "wallet", None)),
            "litecoin": ("Litecoin (Em breve)", getattr(emoji, "wallet", None)),
            "ethereum": ("Ethereum (Em breve)", getattr(emoji, "wallet", None)),
        }
        """Retorna todos os provedores com suas informações"""
        return {
            "pix_manual": ("Pix Manual", emoji.pix),
            "mercado_pago": ("Mercado Pago", emoji.mercado_pago),
            "efibank": ("Efi Bank", emoji.efi_bank),
            "pushinpay": ("Pushin Pay", emoji.pushin_pay),
            "misticpay": ("MisticPay", emoji.pix),
            "Lyon_wallet": ("Lyon Wallet", emoji.wallet),
            "livepix": ("Live Pix", emoji.wallet),
            "pagbank": ("PagBank", emoji.pagbank),
            "picpay": ("PicPay", emoji.picpay),
            "stripe": ("Stripe", emoji.stripe),
            "nowpayments": ("NowPayments", emoji.wallet),
            "coinbase": ("Coinbase", emoji.wallet),
            "asaas": ("Asaas", emoji.card),
            "paypal": ("PayPal", emoji.wallet),
            "nubank": ("Nubank", emoji.bank),
            "inter": ("Inter", emoji.bank),
            "bitcoin": ("Bitcoin (Em breve)", emoji.wallet),
            "litecoin": ("Litecoin (Em breve)", emoji.wallet),
            "ethereum": ("Ethereum (Em breve)", emoji.wallet),
        }

    @staticmethod
    def _providers_by_category():
        return {
            "pix": [
                "pix_manual",
                "mercado_pago",
                "efibank",
                "pagbank",
                "picpay",
                "pushinpay",
                "misticpay",
                "promissepay",
                "nubank_imap",
                "picpay_imap",
                "itau_imap",
                "livepix",
                "asaas",
                "inter",
            ],
            "cartao": [
                "card",
                "mercado_pago",
                "efibank",
                "asaas",
                "stripe",
                "paypal",
            ],
            "crypto": [
                "stripe",
                "nowpayments",
                "coinbase",
                "bitcoin",
                "litecoin",
                "ethereum",
            ],
        }
        """Retorna os provedores organizados por categoria de pagamento"""
        return {
            "pix": [
                "pix_manual",
                "mercado_pago",
                "efibank",
                "pushinpay",
                "misticpay",
                "livepix",
                "asaas",
                "nubank",
                "inter",
            ],
            "cartao": [
                "asaas",
                "stripe",
                "paypal",
            ],
            "crypto": [
                "stripe",
                "nowpayments",
                "coinbase",
                "bitcoin",
                "litecoin",
                "ethereum",
            ],
        }

    @staticmethod
    def _providers_coming_soon():
        return [
            "nubank", "bitcoin", "litecoin", "ethereum", "livepix", "inter", "promissepay"
        ]
        """Lista de provedores que estão em breve"""
        return [
            "nubank", "bitcoin", "litecoin", "ethereum", "livepix", "inter", "promissepay"
        ]

    @staticmethod
    def _load_config() -> dict:
        """Carrega configurações de pagamento do database"""
        return db.get_document("payment_configs") or {}

    @staticmethod
    def _invalidate_payment_method_caches() -> None:
        try:
            from modules.loja.cart.buy_modal import invalidate_payment_methods_cache as invalidate_buy_cache
            from modules.loja.cart.checkout import invalidate_payment_methods_cache as invalidate_checkout_cache
            invalidate_buy_cache()
            invalidate_checkout_cache()
        except Exception:
            pass

    @staticmethod
    def _status_badge(enabled: bool, configured: bool = False) -> str:
        if enabled:
            return f"{getattr(emoji, 'on', '🟢')} `Ativo`"
        if configured:
            return f"{getattr(emoji, 'off', '🔴')} `Desativado`"
        return f"{getattr(emoji, 'off', '🔴')} `Desativado`"

    @staticmethod
    def _status_label(enabled: bool, configured: bool = False) -> str:
        if enabled:
            return "Ativo"
        if configured:
            return "Desativado"
        return "Nao configurado"

    @classmethod
    def _provider_configured(cls, key: str, config: dict) -> bool:
        entry = config.get(key) or {}
        if not isinstance(entry, dict):
            return False
        if key == "mercado_pago":
            return bool(entry.get("access_token"))
        if key == "efibank":
            cert_path = entry.get("cert_file")
            cert_ok = bool(cert_path) and Path(cert_path).exists()
            has_client = bool(entry.get("client_id") or entry.get("client"))
            has_secret = bool(entry.get("client_secret") or entry.get("token"))
            has_pix = bool(entry.get("pix_key"))
            return bool(has_client and has_secret and has_pix and cert_ok)
        if key in {"pagbank", "picpay", "pushinpay", "asaas", "stripe", "coinbase", "nowpayments", "livepix", "inter", "promissepay"}:
            token_key = {
                "pagbank": "token_pagbank",
                "picpay": "token_picpay",
                "pushinpay": "token_pushinpay",
                "asaas": "token_asaas",
                "stripe": "token_stripe",
                "coinbase": "token_coinbase",
                "nowpayments": "token_nowpayments",
                "livepix": "token_livepix",
                "inter": "token_inter",
                "promissepay": "token_promissepay",
            }[key]
            return bool(entry.get(token_key))
        if key == "paypal":
            return bool(entry.get("client_id") and entry.get("client_secret"))
        if key == "misticpay":
            return bool(entry.get("client_id") and entry.get("client_secret"))
        if key in {"nubank", "nubank_imap", "picpay_imap", "itau_imap"}:
            return bool(entry.get("email") and entry.get("password") and entry.get("pix_key"))
        if key == "pix_manual":
            return bool(entry.get("pix_key") and entry.get("pix_key_type"))
        if key == "Lyon_wallet":
            return False
        if key == "card":
            gateway = entry.get("gateway")
            return bool(gateway and cls._provider_configured(gateway, config))
        return False

    @staticmethod
    def _component_emoji(value):
        if value is None:
            return None
        if isinstance(value, str) and value.startswith("<"):
            try:
                return disnake.PartialEmoji.from_str(value)
            except Exception:
                return None
        return value

    @classmethod
    def _provider_icon(cls, key: str):
        return cls._providers().get(key, (key, None))[1]

    @classmethod
    def _button(cls, label: str, key: str, custom_id: str, style=disnake.ButtonStyle.grey):
        return disnake.ui.Button(
            label=label,
            emoji=cls._component_emoji(cls._provider_icon(key)),
            style=style,
            custom_id=custom_id,
        )

    @staticmethod
    def _container_kwargs() -> dict:
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")
        if not primary_color_hex:
            return {}
        try:
            return {"accent_colour": disnake.Colour(int(primary_color_hex.replace("#", ""), 16))}
        except Exception:
            return {}

    @staticmethod
    def _user_display(inter) -> str:
        user = getattr(inter, "author", None) or getattr(inter, "user", None)
        if user:
            return getattr(user, "display_name", str(user))
        return "admin"

    @classmethod
    def _line(cls, label: str, key: str, config: dict, pagamentos: dict, icon_key: str | None = None) -> str:
        enabled, configured, _ = cls._get_provider_status(key, config, pagamentos)
        icon = cls._provider_icon(icon_key or key) or ""
        return f"{icon} **{label}:** {cls._status_badge(enabled, configured)}"

    @classmethod
    def _main_payment_components(cls, inter: disnake.MessageInteraction) -> list:
        pagamentos = db.get_document("pagamentos") or {}
        config = cls._load_config()
        user_name = cls._user_display(inter)

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(
                f"# {getattr(emoji, 'ghost', '')} Configurar Forma de Pagamento\n"
                f"Boa noite **{user_name}**, aqui voce podera configurar **forma de pagamento** que voce utilizara para receber os pagamentos das compras."
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                "**Gateways de Pagamento**\n"
                f"{cls._line('Mercado Pago', 'mercado_pago', config, pagamentos)}\n"
                f"{cls._line('Efi Bank', 'efibank', config, pagamentos)}\n"
                f"{cls._line('MisticPay', 'misticpay', config, pagamentos)}"
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                "**Bancos Tradicionais**\n"
                f"{cls._line('Itau', 'itau_imap', config, pagamentos)}\n"
                f"{cls._line('Nubank', 'nubank_imap', config, pagamentos)}\n"
                f"{cls._line('PicPay', 'picpay_imap', config, pagamentos)}"
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                "**Outros**\n"
                f"{cls._line('Pagamento Manual', 'pix_manual', config, pagamentos)}\n"
                f"{cls._line('Cartao', 'card', config, pagamentos)}\n"
                "**Carteira:** `Desativado temporariamente`"
            ),
            disnake.ui.Separator(),
            disnake.ui.ActionRow(
                cls._button("Mercado Pago", "mercado_pago", "Configuracoes_Pagamento_Provider:mercado_pago"),
                cls._button("Efi Bank", "efibank", "Configuracoes_Pagamento_Provider:efibank"),
                cls._button("MisticPay", "misticpay", "Configuracoes_Pagamento_Provider:misticpay"),
            ),
            disnake.ui.ActionRow(
                cls._button("Itau", "itau_imap", "Configuracoes_Pagamento_Provider:itau_imap"),
                cls._button("PicPay", "picpay_imap", "Configuracoes_Pagamento_Provider:picpay_imap"),
                cls._button("Nubank", "nubank_imap", "Configuracoes_Pagamento_Provider:nubank_imap"),
            ),
            disnake.ui.ActionRow(
                cls._button("Pagamento Manual", "pix_manual", "Configuracoes_Pagamento_Provider:pix_manual"),
                cls._button("Cartao", "card", "Configuracoes_Pagamento_Card"),
                cls._button("Carteira", "Lyon_wallet", "Configuracoes_Pagamento_Wallet"),
            ),
            **cls._container_kwargs(),
        )
        return [container]

    @classmethod
    def _card_components(cls, inter: disnake.MessageInteraction) -> list:
        config = cls._load_config()
        card_cfg = config.get("card") or {}
        gateway = card_cfg.get("gateway")
        enabled = as_bool(card_cfg.get("enabled"), False)
        configured = cls._provider_configured("card", config)
        gateway_names = {
            "mercado_pago": "Mercado Pago",
            "stripe": "Stripe",
            "efibank": "Efibank",
            "asaas": "Asaas",
            "paypal": "PayPal",
        }

        status_lines = []
        for key in ("mercado_pago", "stripe", "efibank", "asaas", "paypal"):
            p_enabled, p_configured, _ = cls._get_provider_status(key, config, db.get_document("pagamentos") or {})
            icon = cls._provider_icon(key) or ""
            selected = " (selecionado)" if key == gateway else ""
            status_lines.append(f"{icon} **{gateway_names[key]}** - {cls._status_badge(p_enabled, p_configured)}{selected}")

        options = [
            disnake.SelectOption(
                label=gateway_names[key],
                value=key,
                emoji=cls._component_emoji(cls._provider_icon(key)),
                description=f"Configurar pagamento com cartao via {gateway_names[key]}",
                default=(gateway == key),
            )
            for key in ("mercado_pago", "stripe", "efibank", "asaas", "paypal")
        ]

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(
                f"# {getattr(emoji, 'card', '')} Pagamento com Cartao\n"
                "Escolha seu **gateway de pagamento** preferido para processar transacoes com cartoes de **credito e debito** de forma segura e rapida."
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay("**Gateways Disponiveis:**\n\n" + "\n".join(status_lines)),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(f"**Status do Cartao:** {cls._status_badge(enabled, configured)}"),
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Configuracoes_Pagamento_Card_Select",
                    placeholder="Selecione um Gateway",
                    options=options,
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Ativo" if enabled else "Desativado",
                    style=disnake.ButtonStyle.green if enabled else disnake.ButtonStyle.red,
                    emoji=cls._component_emoji(getattr(emoji, "on" if enabled else "off", None)),
                    custom_id="Configuracoes_Pagamento_Card_Toggle",
                ),
                disnake.ui.Button(label="", style=disnake.ButtonStyle.blurple, emoji=cls._component_emoji(getattr(emoji, "back", None)), custom_id="Configuracoes_Pagamentos"),
            ),
            **cls._container_kwargs(),
        )
        return [container]

    @classmethod
    def _imap_components(cls, inter: disnake.MessageInteraction, provider_key: str) -> list:
        config = cls._load_config()
        pagamentos = db.get_document("pagamentos") or {}
        entry = config.get(provider_key) or {}
        enabled, configured, _ = cls._get_provider_status(provider_key, config, pagamentos)
        label, icon = cls._providers().get(provider_key, (provider_key, getattr(emoji, "bank", "")))
        pix_label = {
            "nubank_imap": "Chave PIX Nubank",
            "picpay_imap": "Chave PIX PicPay",
            "itau_imap": "Chave PIX Itau",
        }.get(provider_key, "Chave PIX")

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(
                f"# {icon or ''} {label} - Monitoramento IMAP\n"
                f"Configure o **{label}** para receber pagamentos via PIX usando monitoramento de e-mail."
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"{getattr(emoji, 'warn', '')} **Atencao:** Este metodo utiliza **IMAP** para verificar pagamentos atraves do Gmail. Pode haver atraso na confirmacao e requer senha de app do Google."
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"{getattr(emoji, 'chart', '')} **Status do Sistema:** {cls._status_badge(enabled, configured)}\n"
                f"{getattr(emoji, 'mail2', '')} **Conta Gmail:** {'`Configurada`' if entry.get('email') else '`Nao configurado`'}\n"
                f"{getattr(emoji, 'tools', '')} **Senha de App Google:** {'`Configurada`' if entry.get('password') else '`Nao configurada`'}\n"
                f"{getattr(emoji, 'dollar', '')} **{pix_label}:** {'`Configurada`' if entry.get('pix_key') else '`Nao vinculada`'}"
            ),
            disnake.ui.Separator(),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Habilitado" if enabled else "Desabilitado",
                    style=disnake.ButtonStyle.green if enabled else disnake.ButtonStyle.red,
                    emoji=cls._component_emoji(getattr(emoji, "on" if enabled else "off", None)),
                    custom_id=f"Configuracoes_Pagamento_Toggle:{provider_key}:imap",
                ),
                disnake.ui.Button(label="Configurar Credenciais", style=disnake.ButtonStyle.grey, emoji=cls._component_emoji(getattr(emoji, "tools", None)), custom_id=f"Configuracoes_Pagamento_Config:{provider_key}:imap"),
                disnake.ui.Button(label="", style=disnake.ButtonStyle.blurple, emoji=cls._component_emoji(getattr(emoji, "back", None)), custom_id="Configuracoes_Pagamentos"),
            ),
            **cls._container_kwargs(),
        )
        return [container]

    @classmethod
    def _wallet_components(cls, inter: disnake.MessageInteraction) -> list:
        config = cls._load_config()
        pagamentos = db.get_document("pagamentos") or {}
        entry = config.get("Lyon_wallet") or {}
        enabled, configured, _ = cls._get_provider_status("Lyon_wallet", config, pagamentos)
        balance = entry.get("balance", 0) or 0
        cover_fee = as_bool(entry.get("cover_fee"), False)
        enabled = False
        configured = False

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(
                f"# {getattr(emoji, 'carteira', getattr(emoji, 'wallet', ''))} Sistema de Carteira\n"
                "Carteira desativada temporariamente. Use PIX manual, IMAP ou outro gateway."
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                "> **Como funciona:**\n"
                "> Ideal para menores de idade ou quem nao tem CNPJ\n"
                "> Saque para sua chave PIX quando quiser\n\n"
                "> **Taxas do sistema aplicadas**"
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"{getattr(emoji, 'chart', '')} **Status:** {cls._status_badge(enabled, configured)}\n"
                f"{getattr(emoji, 'pix', '')} **Chave PIX:** {'`Configurada`' if entry.get('pix_key') else '`Nao configurado`'}\n"
                f"{getattr(emoji, 'coin', '')} **Saldo Disponivel:** `R$ {float(balance):.2f}`\n"
                f"{getattr(emoji, 'warn', '')} **Repassar Taxa:** {'`Ativado`' if cover_fee else '`Desativado`'}"
            ),
            disnake.ui.Separator(),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Ativado" if enabled else "Desativado",
                    style=disnake.ButtonStyle.green if enabled else disnake.ButtonStyle.red,
                    emoji=cls._component_emoji(getattr(emoji, "on" if enabled else "off", None)),
                    custom_id="Configuracoes_Pagamento_Toggle:Lyon_wallet:wallet",
                    disabled=True,
                ),
                disnake.ui.Button(label="Configurar PIX", style=disnake.ButtonStyle.grey, emoji=cls._component_emoji(getattr(emoji, "pix", None)), custom_id="Configuracoes_Pagamento_Config:Lyon_wallet:wallet", disabled=True),
                disnake.ui.Button(label="Repassar Taxa", style=disnake.ButtonStyle.grey, emoji=cls._component_emoji(getattr(emoji, "warn", None)), custom_id="Configuracoes_Pagamento_Wallet_Fee", disabled=True),
                disnake.ui.Button(label="Sacar", style=disnake.ButtonStyle.grey, emoji=cls._component_emoji(getattr(emoji, "coin", None)), custom_id="Configuracoes_Pagamento_Wallet_Withdraw", disabled=True),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Historico", style=disnake.ButtonStyle.grey, emoji=cls._component_emoji(getattr(emoji, "receipt", None)), custom_id="Configuracoes_Pagamento_Wallet_History", disabled=True),
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=cls._component_emoji(getattr(emoji, "back", None)), custom_id="Configuracoes_Pagamentos"),
            ),
            **cls._container_kwargs(),
        )
        return [container]

    @classmethod
    def _get_provider_status(cls, key: str, config: dict, pagamentos: dict) -> tuple[bool, bool, str]:
        entry = config.get(key)
        if isinstance(entry, dict):
            enabled = as_bool(entry.get("enabled"), False)
            configured = cls._provider_configured(key, config)
        elif isinstance(entry, bool):
            enabled = as_bool(entry, False)
            configured = False
        else:
            enabled = as_bool(pagamentos.get(key), False)
            configured = False

        if enabled:
            status_text = "Ativo"
        elif configured:
            status_text = "Desativado"
        else:
            status_text = "Nao configurado"

        return enabled, configured, status_text
        """Retorna (enabled, configured, status_text) para um provedor"""
        entry = config.get(key)
        if isinstance(entry, dict):
            enabled = bool(entry.get("enabled", False))
            if key == "mercado_pago":
                configured = bool(entry.get("access_token"))
            elif key == "efibank":
                cert_path = entry.get("cert_file")
                cert_ok = bool(cert_path) and Path(cert_path).exists()
                has_client = bool(entry.get("client_id") or entry.get("client"))
                has_secret = bool(entry.get("client_secret") or entry.get("token"))
                has_pix = bool(entry.get("pix_key"))
                configured = bool(has_client and has_secret and has_pix and cert_ok)
            elif key in {"pagbank", "picpay", "pushinpay", "asaas", "stripe", "coinbase", "nowpayments", "livepix", "inter"}:
                token_key = {
                    "pagbank": "token_pagbank",
                    "picpay": "token_picpay",
                    "pushinpay": "token_pushinpay",
                    "asaas": "token_asaas",
                    "stripe": "token_stripe",
                    "coinbase": "token_coinbase",
                    "nowpayments": "token_nowpayments",
                    "livepix": "token_livepix",
                    "inter": "token_inter",
                }[key]
                configured = bool(entry.get(token_key))
            elif key == "paypal":
                configured = bool(entry.get("client_id") and entry.get("client_secret"))
            elif key == "misticpay":
                configured = bool(entry.get("client_id") and entry.get("client_secret"))
            elif key == "nubank":
                configured = bool(entry.get("email") and entry.get("password") and entry.get("pix_key"))
            elif key == "pix_manual":
                configured = bool(entry.get("pix_key") and entry.get("pix_key_type"))
            elif key == "Lyon_wallet":
                configured = bool(entry.get("api_key"))
            else:
                configured = False
        elif isinstance(entry, bool):
            enabled = entry
            configured = False
        else:
            enabled = bool(pagamentos.get(key, False))
            configured = False
        
        if enabled:
            status_text = "Ativado"
        elif configured:
            status_text = "Desativado"
        else:
            status_text = "Não Configurado"
        
        return enabled, configured, status_text

    @classmethod
    def categoria_pagamentos_components(cls, inter: disnake.MessageInteraction) -> list[disnake.ui.Container]:
        return cls._main_payment_components(inter)
        """Componentes para seleção inicial de categoria de pagamento"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Configurações > **Formas de Pagamento**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    f"{emoji.pix} **Pix**"
                ),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Configuracoes_Pagamentos_Categoria_Select",
                        placeholder="Selecione o tipo de pagamento",
                        options=[
                            disnake.SelectOption(
                                label="Pix",
                                value="pix",
                                emoji=emoji.pix,
                                description="Configure métodos de pagamento via Pix"
                            ),
                            # Cartão e Crypto desabilitados temporariamente
                            # disnake.SelectOption(
                            #     label="Cartão",
                            #     value="cartao",
                            #     emoji=emoji.card,
                            #     description="Configure métodos de pagamento com cartão"
                            # ),
                            # disnake.SelectOption(
                            #     label="Crypto",
                            #     value="crypto",
                            #     emoji=emoji.wallet,
                            #     description="Configure métodos de pagamento em criptomoedas"
                            # ),
                        ],
                    )
                ),
                **container_kwargs,
            ),
        ]

    @classmethod
    def categoria_pagamentos_embed(cls, inter: disnake.MessageInteraction):
        """Embed para seleção inicial de categoria de pagamento"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        embed = disnake.Embed(
            title="Formas de Pagamento",
            description="Selecione o tipo de pagamento que deseja configurar.",
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)

        embed.description = (
            f"-# Painel > Configurações > **Formas de Pagamento**\n\n"
            f"{emoji.pix} **Pix**"
        )

        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Configuracoes_Pagamentos_Categoria_Select",
                    placeholder="Selecione o tipo de pagamento",
                    options=[
                        disnake.SelectOption(
                            label="Pix",
                            value="pix",
                            emoji=emoji.pix,
                            description="Configure métodos de pagamento via Pix"
                        ),
                        # Cartão e Crypto desabilitados temporariamente
                        # disnake.SelectOption(
                        #     label="Cartão",
                        #     value="cartao",
                        #     emoji=emoji.card,
                        #     description="Configure métodos de pagamento com cartão"
                        # ),
                        # disnake.SelectOption(
                        #     label="Crypto",
                        #     value="crypto",
                        #     emoji=emoji.wallet,
                        #     description="Configure métodos de pagamento em criptomoedas"
                        # ),
                    ],
                )
            ),
        ]
        return embed, components

    @classmethod
    def pagamentos_components(cls, inter: disnake.MessageInteraction, categoria: str = None) -> list[disnake.ui.Container]:
        """Componentes para listar provedores de uma categoria específica"""
        pagamentos = db.get_document("pagamentos") or {}
        config = cls._load_config()
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        # Se não especificou categoria, mostra a tela de seleção de categoria
        if not categoria:
            return cls.categoria_pagamentos_components(inter)

        # Obter provedores da categoria
        providers_dict = cls._providers()
        providers_by_cat = cls._providers_by_category()
        provider_keys = providers_by_cat.get(categoria, [])

        # Mapear nomes de categoria para exibição
        categoria_names = {
            "pix": "Pix",
            "cartao": "Cartão",
            "crypto": "Crypto",
        }
        categoria_name = categoria_names.get(categoria, categoria.capitalize())

        status_lines = []
        options = []
        for key in provider_keys:
            if key not in providers_dict:
                continue
            label, icon = providers_dict[key]
            enabled, configured, status_text = cls._get_provider_status(key, config, pagamentos)
            
            status_lines.append(f"{emoji.on if enabled else emoji.off} **{label}**")
            options.append(
                disnake.SelectOption(
                    label=f"Configurar {label}",
                    value=key,
                    emoji=icon,
                    description=f"Status: {status_text}",
                )
            )

        result = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Configurações > **Formas de Pagamento** > **{categoria_name}**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("\n".join(status_lines) if status_lines else "Nenhum provedor disponível nesta categoria."),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id=f"Configuracoes_Pagamentos_Select:{categoria}",
                        placeholder="Selecione uma forma de pagamento para configurar",
                        options=options,
                    )
                ),
                **container_kwargs,
            ),
        ]

        # Construir botões do ActionRow filtrando None
        back_button = disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Configuracoes_Pagamentos")
        tutorial_button = disnake.ui.Button(label="Tutorial PIX", style=disnake.ButtonStyle.blurple, emoji=emoji.information, custom_id="Configuracoes_Pagamentos_Tutorial_Pix") if categoria == "pix" else None
        
        buttons = [back_button, tutorial_button]
        buttons = [btn for btn in buttons if btn is not None]
        
        result.append(disnake.ui.ActionRow(*buttons))

        return result


    @classmethod
    def pagamentos_embed(cls, inter: disnake.MessageInteraction, categoria: str = None):
        """Embed para listar provedores de uma categoria específica"""
        # Se não especificou categoria, mostra a tela de seleção de categoria
        if not categoria:
            return cls.categoria_pagamentos_embed(inter)

        pagamentos = db.get_document("pagamentos") or {}
        config = cls._load_config()
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        # Obter provedores da categoria
        providers_dict = cls._providers()
        providers_by_cat = cls._providers_by_category()
        provider_keys = providers_by_cat.get(categoria, [])

        # Mapear nomes de categoria para exibição
        categoria_names = {
            "pix": "Pix",
            "cartao": "Cartão",
            "crypto": "Crypto",
        }
        categoria_name = categoria_names.get(categoria, categoria.capitalize())

        embed = disnake.Embed(
            title=f"Formas de Pagamento - {categoria_name}",
            description="Selecione uma forma de pagamento para configurar.",
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)

        status_lines = []
        options = []
        for key in provider_keys:
            if key not in providers_dict:
                continue
            label, icon = providers_dict[key]
            enabled, configured, status_text = cls._get_provider_status(key, config, pagamentos)
            
            status_lines.append(f"{emoji.on if enabled else emoji.off} **{label}**")
            options.append(
                disnake.SelectOption(
                    label=f"Configurar {label}",
                    value=key,
                    emoji=icon,
                    description=f"Status: {status_text}",
                )
            )

        embed.description = f"-# Painel > Configurações > **Formas de Pagamento** > **{categoria_name}**\n\n" + "\n".join(status_lines) if status_lines else "Nenhum provedor disponível nesta categoria."

        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id=f"Configuracoes_Pagamentos_Select:{categoria}",
                    placeholder="Selecione uma forma de pagamento para configurar",
                    options=options,
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Configuracoes_Pagamentos"),
                disnake.ui.Button(label="Tutorial PIX", style=disnake.ButtonStyle.blurple, emoji=emoji.information, custom_id="Configuracoes_Pagamentos_Tutorial_Pix") if categoria == "pix" else None,
            ),
        ]

        # Filtrar None dos botões no ActionRow
        components[-1] = disnake.ui.ActionRow(
            *[btn for btn in components[-1].children if btn is not None]
        )

        return embed, components

    async def _edit_payment_components(self, inter: disnake.MessageInteraction, components: list):
        if not inter.response.is_done():
            await inter.response.defer(with_message=False)
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=components,
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    async def display_payments_panel(self, inter: disnake.MessageInteraction):
        await message.wait(inter)
        await inter.edit_original_message(
            content=None,
            embed=None,
            components=self.categoria_pagamentos_components(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )

    async def _send_wallet_disabled(self, inter):
        content = f"{getattr(emoji, 'warn', '')} Carteira desativada temporariamente. Use PIX manual, IMAP ou outro gateway."
        if not inter.response.is_done():
            await inter.response.send_message(content, ephemeral=True)
        else:
            await inter.followup.send(content, ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if custom_id == "Configuracoes_Pagamentos":
            await self._edit_payment_components(inter, self.categoria_pagamentos_components(inter))

        elif custom_id == "Configuracoes_Pagamento_Card":
            await self._edit_payment_components(inter, self._card_components(inter))

        elif custom_id == "Configuracoes_Pagamento_Wallet":
            await self._edit_payment_components(inter, self._wallet_components(inter))

        elif custom_id == "Configuracoes_Pagamento_Card_Toggle":
            config = self._load_config()
            card_cfg = config.get("card") or {}
            gateway = card_cfg.get("gateway")
            was_enabled = as_bool(card_cfg.get("enabled"), False)
            can_enable = bool(gateway and self._provider_configured(gateway, config))
            card_cfg["enabled"] = False if was_enabled else can_enable
            config["card"] = card_cfg
            db.save_document("payment_configs", config)
            pagamentos = db.get_document("pagamentos") or {}
            pagamentos["card"] = as_bool(card_cfg["enabled"], False)
            db.save_document("pagamentos", {}, pagamentos)
            self._invalidate_payment_method_caches()
            await self._edit_payment_components(inter, self._card_components(inter))
            if not was_enabled and not can_enable:
                await message.error(inter, "Configure um gateway antes de ativar o cartao.", followup=True)

        elif custom_id == "Configuracoes_Pagamento_Wallet_Fee":
            await self._send_wallet_disabled(inter)
            return

        elif custom_id == "Configuracoes_Pagamento_Wallet_History":
            if not inter.response.is_done():
                await inter.response.defer(ephemeral=True)
            await inter.followup.send("Historico da carteira sera exibido quando a API da carteira responder com movimentacoes.", ephemeral=True)

        elif custom_id == "Configuracoes_Pagamento_Wallet_Withdraw":
            await self._send_wallet_disabled(inter)
            return

        elif custom_id.startswith("Configuracoes_Pagamento_Toggle:"):
            _, provider_key, panel = custom_id.split(":", 2)
            if provider_key == "Lyon_wallet":
                await self._send_wallet_disabled(inter)
                return
            config = self._load_config()
            entry = config.get(provider_key) or {}
            enabled = not as_bool(entry.get("enabled"), False)
            if enabled and not self._provider_configured(provider_key, config):
                await inter.response.send_message("Configure esta forma de pagamento antes de ativar.", ephemeral=True)
                return
            entry["enabled"] = enabled
            config[provider_key] = entry
            db.save_document("payment_configs", config)
            pagamentos = db.get_document("pagamentos") or {}
            pagamentos[provider_key] = enabled
            db.save_document("pagamentos", {}, pagamentos)
            self._invalidate_payment_method_caches()
            components = self._wallet_components(inter) if panel == "wallet" else self._imap_components(inter, provider_key)
            await self._edit_payment_components(inter, components)

        elif custom_id.startswith("Configuracoes_Pagamento_Config:"):
            _, provider_key, panel = custom_id.split(":", 2)
            await inter.response.send_modal(PaymentProviderModal(provider_key, panel))

        elif custom_id.startswith("Configuracoes_Pagamento_Provider:"):
            provider_key = custom_id.split(":", 1)[1]
            if provider_key in self._providers_coming_soon():
                await inter.response.send_message(
                    f"{emoji.information} Essa forma de pagamento estara disponivel em breve nas proximas atualizacoes.",
                    ephemeral=True
                )
                return
            if provider_key in {"nubank_imap", "picpay_imap", "itau_imap"}:
                await self._edit_payment_components(inter, self._imap_components(inter, provider_key))
            else:
                await inter.response.send_modal(PaymentProviderModal(provider_key, "main"))
        
        elif custom_id == "Configuracoes_Pagamentos_Tutorial_Pix":
            await inter.response.send_message(
                f"Acesse a documentação completa para configurar o pagamento via PIX:\n"
                f"O grande diferencial da Lyon Wallet é que aceita menores e não tem MEDs.\n"
                f"https://docs.Lyonwallet.com.br/tutoriais/integrar-Lyon-bot",
                ephemeral=True
            )

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if custom_id == "Configuracoes_Pagamento_Card_Select":
            gateway = inter.values[0]
            config = self._load_config()
            card_cfg = config.get("card") or {}
            card_cfg["gateway"] = gateway
            card_cfg["enabled"] = self._provider_configured(gateway, config)
            config["card"] = card_cfg
            db.save_document("payment_configs", config)
            pagamentos = db.get_document("pagamentos") or {}
            pagamentos["card"] = as_bool(card_cfg["enabled"], False)
            db.save_document("pagamentos", {}, pagamentos)
            self._invalidate_payment_method_caches()
            await self._edit_payment_components(inter, self._card_components(inter))
            if not card_cfg["enabled"]:
                await message.error(inter, "Gateway salvo, mas ele ainda precisa estar configurado e ativo para aparecer no checkout.", followup=True)
            return
        # Seleção de categoria
        if inter.component.custom_id == "Configuracoes_Pagamentos_Categoria_Select":
            categoria = inter.values[0]
            mode = db.get_document("custom_mode").get("mode")
            
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.pagamentos_embed(inter, categoria)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(components=self.pagamentos_components(inter, categoria))
        
        # Seleção de provedor (pode ter categoria no custom_id)
        elif inter.component.custom_id.startswith("Configuracoes_Pagamentos_Select"):
            # Extrair categoria do custom_id se existir
            parts = inter.component.custom_id.split(":")
            categoria = parts[1] if len(parts) > 1 else None
            key = inter.values[0]
            
            # Verificar se é um provedor "em breve"
            if key in self._providers_coming_soon():
                await inter.response.send_message(
                    f"{emoji.information} Essa forma de pagamento estará disponível em breve nas próximas atualizações.",
                    ephemeral=True
                )
                return
            
            # Verificar se o plano permite este provedor
            if not plan.should_allow_payment_provider(key):
                await inter.response.send_message(
                    f"{emoji.wrong} O plano **Free** permite apenas a forma de pagamento **Lyon Wallet**.\n"
                    f"{emoji.arrow} Acesse https://Lyonwallet.com.br para criar sua conta.",
                    ephemeral=True
                )
                return
            
            await inter.response.send_modal(PaymentProviderModal(key, categoria))


class PaymentProviderModal(disnake.ui.Modal):
    def __init__(self, provider_key: str, categoria: str = None):
        self.provider_key = provider_key
        self.categoria = categoria

        config = ConfigurarPagamentos._load_config()
        entry = config.get(provider_key) or {}
        if isinstance(entry, bool):
            entry = {"enabled": as_bool(entry, False)}

        enabled = as_bool(entry.get("enabled"), False)

        providers_dict = ConfigurarPagamentos._providers()
        label = providers_dict.get(provider_key, (provider_key.capitalize(), ""))[0]

        components = [
            disnake.ui.Label(
                text="Status do provedor",
                component=disnake.ui.StringSelect(
                    placeholder="Ativar ou desativar",
                    custom_id="payment_status",
                    required=True,
                    options=[
                        disnake.SelectOption(label="Ativado", description="O provedor ficará ativado",emoji=emoji.on , value="enabled_True", default=enabled),
                        disnake.SelectOption(label="Desativado", description="O provedor ficará desativado", emoji=emoji.off, value="enabled_False", default=not enabled),
                    ],
                ),
                description="Define se o provedor estará ativo.",
            ),
        ]

        if provider_key == "mercado_pago":
            components.append(
                disnake.ui.Label(
                    text="Token Access",
                    component=disnake.ui.TextInput(
                        placeholder="Cole o Access Token do MercadoPago",
                        custom_id="mercado_pago_access_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("access_token") or ""),
                    ),
                    description="Access Token da sua conta Mercado Pago.",
                )
            )
        elif provider_key == "efibank":
            components.append(
                disnake.ui.Label(
                    text="Client ID",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o Client ID da Efi",
                        custom_id="efibank_client_id",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("client_id") or entry.get("client") or ""),
                    ),
                    description="Identificador do cliente (Client ID).",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Client Secret",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o Client Secret da Efi",
                        custom_id="efibank_client_secret",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("client_secret") or entry.get("token") or ""),
                    ),
                    description="Segredo do cliente (Client Secret).",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Chave Pix Aleatória",
                    component=disnake.ui.TextInput(
                        placeholder="Informe a Chave Pix Aleatória",
                        custom_id="efibank_pix_key",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("pix_key") or ""),
                    ),
                    description="Sua chave Pix aleatória cadastrada na Efi.",
                )
            )
            # Adicionar campo de upload de arquivo para o certificado .p12
            cert_path = entry.get("cert_file")
            cert_exists = bool(cert_path) and Path(cert_path).exists()
            components.append(
                disnake.ui.Label(
                    text="Certificado .p12",
                    component=disnake.ui.FileUpload(
                        custom_id="efibank_cert_file",
                        required=False,
                    ),
                    description="Envie o arquivo de certificado .p12 da Efi. Deixe vazio para manter o atual." if cert_exists else "Envie o arquivo de certificado .p12 da Efi.",
                )
            )
        elif provider_key == "pagbank":
            components.append(
                disnake.ui.Label(
                    text="Token PagBank",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do PagBank",
                        custom_id="pagbank_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_pagbank") or ""),
                    ),
                    description="Token de API do PagBank.",
                )
            )
        elif provider_key == "picpay":
            components.append(
                disnake.ui.Label(
                    text="Token PicPay",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do PicPay",
                        custom_id="picpay_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_picpay") or ""),
                    ),
                    description="Token de API do PicPay.",
                )
            )
        elif provider_key == "pushinpay":
            components.append(
                disnake.ui.Label(
                    text="Token PushinPay",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do PushinPay",
                        custom_id="pushinpay_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_pushinpay") or ""),
                    ),
                    description="Token de API do PushinPay.",
                )
            )
        elif provider_key == "misticpay":
            components.append(
                disnake.ui.Label(
                    text="Client ID",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o Client ID do MisticPay",
                        custom_id="misticpay_client_id",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("client_id") or ""),
                    ),
                    description="Client ID do MisticPay.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Client Secret",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o Client Secret do MisticPay",
                        custom_id="misticpay_client_secret",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("client_secret") or ""),
                    ),
                    description="Client Secret do MisticPay.",
                )
            )
        elif provider_key == "promissepay":
            components.append(
                disnake.ui.Label(
                    text="Token PromissePay",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do PromissePay",
                        custom_id="promissepay_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_promissepay") or ""),
                    ),
                    description="Token de API do PromissePay.",
                )
            )
        elif provider_key == "asaas":
            components.append(
                disnake.ui.Label(
                    text="Token Asaas",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do Asaas",
                        custom_id="asaas_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_asaas") or ""),
                    ),
                    description="Token de API do Asaas.",
                )
            )
        elif provider_key == "livepix":
            components.append(
                disnake.ui.Label(
                    text="Token Live Pix",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do Live Pix",
                        custom_id="livepix_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_livepix") or ""),
                    ),
                    description="Token de API do Live Pix.",
                )
            )
        elif provider_key == "nubank":
            components.append(
                disnake.ui.Label(
                    text="Email Nubank",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o email da conta Nubank",
                        custom_id="nubank_email",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("email") or ""),
                    ),
                    description="Email da conta Nubank.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Senha de App Nubank",
                    component=disnake.ui.TextInput(
                        placeholder="Informe a senha de app Nubank",
                        custom_id="nubank_password",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("password") or ""),
                    ),
                    description="Senha de aplicativo Nubank.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Chave PIX Nubank",
                    component=disnake.ui.TextInput(
                        placeholder="Informe a chave PIX Nubank",
                        custom_id="nubank_pix_key",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("pix_key") or ""),
                    ),
                    description="Chave PIX cadastrada na conta Nubank.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Tipo da Chave PIX",
                    component=disnake.ui.StringSelect(
                        placeholder="Selecione o tipo da chave",
                        custom_id="nubank_pix_key_type",
                        required=False,
                        options=[
                            disnake.SelectOption(label="Email", value="email", emoji=emoji.mail2, default=entry.get("pix_key_type") == "email"),
                            disnake.SelectOption(label="Telefone", value="telefone", emoji=emoji.mobile, default=entry.get("pix_key_type") == "telefone"),
                            disnake.SelectOption(label="CPF", value="cpf", emoji=emoji.member, default=entry.get("pix_key_type") == "cpf"),
                            disnake.SelectOption(label="CNPJ", value="cnpj", emoji=emoji.store, default=entry.get("pix_key_type") == "cnpj"),
                            disnake.SelectOption(label="Aleatória", value="aleatoria", emoji=emoji.link, default=entry.get("pix_key_type") == "aleatoria"),
                        ],
                    ),
                    description="Tipo da chave PIX Nubank.",
                )
            )
        elif provider_key in {"nubank_imap", "picpay_imap", "itau_imap"}:
            label = ConfigurarPagamentos._providers().get(provider_key, ("Banco", None))[0]
            prefix = provider_key
            components.append(
                disnake.ui.Label(
                    text=f"Conta Gmail {label}",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o Gmail que recebera os avisos PIX",
                        custom_id=f"{prefix}_email",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("email") or ""),
                    ),
                    description="Gmail usado no monitoramento IMAP.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Senha de App Google",
                    component=disnake.ui.TextInput(
                        placeholder="Informe a senha de app do Google",
                        custom_id=f"{prefix}_password",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("password") or ""),
                    ),
                    description="Senha de app gerada na conta Google.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text=f"Chave PIX {label}",
                    component=disnake.ui.TextInput(
                        placeholder="Informe a chave PIX para receber",
                        custom_id=f"{prefix}_pix_key",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("pix_key") or ""),
                    ),
                    description="Chave PIX usada para gerar o copia e cola.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Tipo da Chave PIX",
                    component=disnake.ui.StringSelect(
                        placeholder="Selecione o tipo da chave",
                        custom_id=f"{prefix}_pix_key_type",
                        required=False,
                        options=[
                            disnake.SelectOption(label="Email", value="email", emoji=emoji.mail2, default=entry.get("pix_key_type") == "email"),
                            disnake.SelectOption(label="Telefone", value="telefone", emoji=emoji.mobile, default=entry.get("pix_key_type") == "telefone"),
                            disnake.SelectOption(label="CPF", value="cpf", emoji=emoji.member, default=entry.get("pix_key_type") == "cpf"),
                            disnake.SelectOption(label="CNPJ", value="cnpj", emoji=emoji.store, default=entry.get("pix_key_type") == "cnpj"),
                            disnake.SelectOption(label="Aleatoria", value="aleatoria", emoji=emoji.link, default=entry.get("pix_key_type") == "aleatoria"),
                        ],
                    ),
                    description="Tipo da chave PIX informada.",
                )
            )
        elif provider_key == "inter":
            components.append(
                disnake.ui.Label(
                    text="Token Inter",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do Inter",
                        custom_id="inter_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_inter") or ""),
                    ),
                    description="Token de API do Inter.",
                )
            )
        elif provider_key == "stripe":
            components.append(
                disnake.ui.Label(
                    text="Token Stripe",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do Stripe",
                        custom_id="stripe_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_stripe") or ""),
                    ),
                    description="Token de API do Stripe.",
                )
            )
        elif provider_key == "coinbase":
            components.append(
                disnake.ui.Label(
                    text="Token Coinbase",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do Coinbase",
                        custom_id="coinbase_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_coinbase") or ""),
                    ),
                    description="Token de API do Coinbase.",
                )
            )
        elif provider_key == "nowpayments":
            components.append(
                disnake.ui.Label(
                    text="Token NOWPayments",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o token do NOWPayments",
                        custom_id="nowpayments_token",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("token_nowpayments") or ""),
                    ),
                    description="Token de API do NOWPayments.",
                )
            )
        elif provider_key == "paypal":
            components.append(
                disnake.ui.Label(
                    text="Client ID",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o Client ID do PayPal",
                        custom_id="paypal_client_id",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("client_id") or ""),
                    ),
                    description="Client ID do PayPal.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Client Secret",
                    component=disnake.ui.TextInput(
                        placeholder="Informe o Client Secret do PayPal",
                        custom_id="paypal_client_secret",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value=str(entry.get("client_secret") or ""),
                    ),
                    description="Client Secret do PayPal.",
                )
            )
        elif provider_key == "Lyon_wallet":
            components.append(
                disnake.ui.Label(
                    text="Carteira desativada",
                    component=disnake.ui.TextInput(
                        placeholder="Lyon Wallet desativada temporariamente",
                        custom_id="Lyon_wallet_disabled",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        value="Desativada",
                    ),
                    description="Use PIX manual, IMAP ou outro gateway.",
                )
            )
        elif provider_key == "pix_manual":
            components.append(
                disnake.ui.Label(
                    text="Chave PIX",
                    component=disnake.ui.TextInput(
                        placeholder="Digite sua chave PIX",
                        custom_id="pix_manual_key",
                        style=disnake.TextInputStyle.short,
                        required=False,
                        max_length=50,
                        value=str(entry.get("pix_key") or ""),
                    ),
                    description="Sua chave PIX para receber pagamentos.",
                )
            )
            components.append(
                disnake.ui.Label(
                    text="Tipo da Chave PIX",
                    component=disnake.ui.StringSelect(
                        placeholder="Selecione o tipo da chave",
                        custom_id="pix_manual_key_type",
                        required=False,
                        options=[
                            disnake.SelectOption(label="Email", value="email", emoji=emoji.mail2, default=entry.get("pix_key_type") == "email"),
                            disnake.SelectOption(label="Telefone", value="telefone", emoji=emoji.mobile, default=entry.get("pix_key_type") == "telefone"),
                            disnake.SelectOption(label="CPF", value="cpf", emoji=emoji.member, default=entry.get("pix_key_type") == "cpf"),
                            disnake.SelectOption(label="CNPJ", value="cnpj", emoji=emoji.store, default=entry.get("pix_key_type") == "cnpj"),
                            disnake.SelectOption(label="Aleatória", value="aleatoria", emoji=emoji.link, default=entry.get("pix_key_type") == "aleatoria"),
                        ],
                    ),
                    description="Tipo da chave PIX informada.",
                )
            )

        super().__init__(title=f"Configurar {label}", components=components, custom_id=f"payment_provider_modal:{provider_key}")

    async def callback(self, inter: disnake.ModalInteraction):
        # Use the correct wait function based on mode to avoid Components V2 conflicts
        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter)

        valores = inter.resolved_values

        status_value = valores.get("payment_status")
        if isinstance(status_value, (list, tuple)):
            status_value = status_value[0] if status_value else None
        enabled = True if status_value == "enabled_True" else False

        access_token = valores.get("mercado_pago_access_token") if self.provider_key == "mercado_pago" else None
        efibank_client_id = valores.get("efibank_client_id") if self.provider_key == "efibank" else None
        efibank_client_secret = valores.get("efibank_client_secret") if self.provider_key == "efibank" else None
        efibank_pix_key = valores.get("efibank_pix_key") if self.provider_key == "efibank" else None
        efibank_cert_file = None
        cert_path = None  # Inicializar cert_path no escopo correto
        if self.provider_key == "efibank":
            # Processar arquivo de certificado se fornecido
            # Em modais, arquivos são acessados através de resolved_values
            cert_file_value = valores.get("efibank_cert_file")
            if cert_file_value:
                # Pode ser um único arquivo ou uma lista
                if isinstance(cert_file_value, (list, tuple)):
                    efibank_cert_file = cert_file_value[0] if cert_file_value else None
                else:
                    efibank_cert_file = cert_file_value
        pagbank_token = valores.get("pagbank_token") if self.provider_key == "pagbank" else None
        picpay_token = valores.get("picpay_token") if self.provider_key == "picpay" else None
        pushinpay_token = valores.get("pushinpay_token") if self.provider_key == "pushinpay" else None
        misticpay_client_id = valores.get("misticpay_client_id") if self.provider_key == "misticpay" else None
        misticpay_client_secret = valores.get("misticpay_client_secret") if self.provider_key == "misticpay" else None
        promissepay_token = valores.get("promissepay_token") if self.provider_key == "promissepay" else None
        asaas_token = valores.get("asaas_token") if self.provider_key == "asaas" else None
        stripe_token = valores.get("stripe_token") if self.provider_key == "stripe" else None
        coinbase_token = valores.get("coinbase_token") if self.provider_key == "coinbase" else None
        nowpayments_token = valores.get("nowpayments_token") if self.provider_key == "nowpayments" else None
        paypal_client_id = valores.get("paypal_client_id") if self.provider_key == "paypal" else None
        paypal_client_secret = valores.get("paypal_client_secret") if self.provider_key == "paypal" else None
        livepix_token = valores.get("livepix_token") if self.provider_key == "livepix" else None
        nubank_email = valores.get("nubank_email") if self.provider_key == "nubank" else None
        nubank_password = valores.get("nubank_password") if self.provider_key == "nubank" else None
        nubank_pix_key = valores.get("nubank_pix_key") if self.provider_key == "nubank" else None
        nubank_pix_key_type = valores.get("nubank_pix_key_type") if self.provider_key == "nubank" else None
        if isinstance(nubank_pix_key_type, (list, tuple)):
            nubank_pix_key_type = nubank_pix_key_type[0] if nubank_pix_key_type else None
        imap_email = valores.get(f"{self.provider_key}_email") if self.provider_key in {"nubank_imap", "picpay_imap", "itau_imap"} else None
        imap_password = valores.get(f"{self.provider_key}_password") if self.provider_key in {"nubank_imap", "picpay_imap", "itau_imap"} else None
        imap_pix_key = valores.get(f"{self.provider_key}_pix_key") if self.provider_key in {"nubank_imap", "picpay_imap", "itau_imap"} else None
        imap_pix_key_type = valores.get(f"{self.provider_key}_pix_key_type") if self.provider_key in {"nubank_imap", "picpay_imap", "itau_imap"} else None
        if isinstance(imap_pix_key_type, (list, tuple)):
            imap_pix_key_type = imap_pix_key_type[0] if imap_pix_key_type else None
        inter_token = valores.get("inter_token") if self.provider_key == "inter" else None
        Lyon_wallet_api_key = valores.get("Lyon_wallet_api_key") if self.provider_key == "Lyon_wallet" else None
        Lyon_wallet_cover_fee = valores.get("Lyon_wallet_cover_fee") if self.provider_key == "Lyon_wallet" else None
        if isinstance(Lyon_wallet_cover_fee, (list, tuple)):
            Lyon_wallet_cover_fee = Lyon_wallet_cover_fee[0] if Lyon_wallet_cover_fee else None
        Lyon_wallet_pix_key = valores.get("Lyon_wallet_pix_key") if self.provider_key == "Lyon_wallet" else None
        Lyon_wallet_pix_key_type = valores.get("Lyon_wallet_pix_key_type") if self.provider_key == "Lyon_wallet" else None
        if isinstance(Lyon_wallet_pix_key_type, (list, tuple)):
            Lyon_wallet_pix_key_type = Lyon_wallet_pix_key_type[0] if Lyon_wallet_pix_key_type else None
        pix_manual_key = valores.get("pix_manual_key") if self.provider_key == "pix_manual" else None
        pix_manual_key_type = valores.get("pix_manual_key_type") if self.provider_key == "pix_manual" else None
        if isinstance(pix_manual_key_type, (list, tuple)):
            pix_manual_key_type = pix_manual_key_type[0] if pix_manual_key_type else None
        configured = False
        error_text = None
        
        if self.provider_key == "Lyon_wallet":
            configured = False
            enabled = False
            error_text = "Lyon Wallet desativada temporariamente. Use PIX manual, IMAP ou outro gateway."

        if self.provider_key == "mercado_pago":
            if access_token:
                # Validação via API oficial do Mercado Pago
                try:
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        headers = {"Authorization": f"Bearer {access_token}"}
                        async with session.get("https://api.mercadopago.com/users/me", headers=headers) as resp:
                            if resp.status == 200:
                                configured = True
                            else:
                                configured = False
                                error_text = "Token do Mercado Pago inválido ou expirado. Não foi possível ativar."
                except Exception:
                    configured = False
                    error_text = "Erro ao validar o token do Mercado Pago. Tente novamente."
            else:
                configured = False
                if enabled:
                    error_text = "Para ativar o Mercado Pago, informe um Access Token válido."
        elif self.provider_key == "efibank":
            config = ConfigurarPagamentos._load_config()
            current = config.get(self.provider_key) or {}
            cert_path = current.get("cert_file")
            cert_exists = bool(cert_path) and Path(cert_path).exists()
        elif self.provider_key == "livepix":
            existing = ConfigurarPagamentos._load_config().get("livepix") or {}
            configured = bool((livepix_token is not None and livepix_token) or existing.get("token_livepix"))
            if enabled and not configured:
                enabled = False
                error_text = "Para ativar o Live Pix, informe o token do Live Pix."
        elif self.provider_key == "nubank":
            existing = ConfigurarPagamentos._load_config().get("nubank") or {}
            have_email = bool(nubank_email or existing.get("email"))
            have_password = bool(nubank_password or existing.get("password"))
            have_pix = bool(nubank_pix_key or existing.get("pix_key"))
            configured = bool(have_email and have_password and have_pix)
            if enabled and not configured:
                enabled = False
                error_text = "Para ativar o Nubank, informe email, senha de app e chave PIX."
        elif self.provider_key in {"nubank_imap", "picpay_imap", "itau_imap"}:
            existing = ConfigurarPagamentos._load_config().get(self.provider_key) or {}
            have_email = bool(imap_email or existing.get("email"))
            have_password = bool(imap_password or existing.get("password"))
            have_pix = bool(imap_pix_key or existing.get("pix_key"))
            configured = bool(have_email and have_password and have_pix)
            if enabled and not configured:
                enabled = False
                error_text = "Para ativar este IMAP, informe Gmail, senha de app e chave PIX."
        elif self.provider_key == "inter":
            existing = ConfigurarPagamentos._load_config().get("inter") or {}
            configured = bool((inter_token is not None and inter_token) or existing.get("token_inter"))
            if enabled and not configured:
                enabled = False
                error_text = "Para ativar o Inter, informe o token do Inter."
        if self.provider_key == "efibank":
            config = ConfigurarPagamentos._load_config()
            current = config.get(self.provider_key) or {}
            cert_path = current.get("cert_file")
            cert_exists = bool(cert_path) and Path(cert_path).exists()
            
            # Processar arquivo de certificado se fornecido
            if efibank_cert_file:
                try:
                    # Validar que é um arquivo .p12
                    if not efibank_cert_file.filename.lower().endswith(".p12"):
                        error_text = "O arquivo deve ser um certificado .p12"
                        configured = False
                    else:
                        # Salvar o arquivo
                        base_dir = Path(__file__).resolve().parents[3] / "database" / "payments" / "certs" / "efibank"
                        base_dir.mkdir(parents=True, exist_ok=True)
                        save_path = base_dir / f"cert_{inter.author.id}.p12"
                        data = await efibank_cert_file.read()
                        with save_path.open("wb") as fp:
                            fp.write(data)
                        cert_path = str(save_path)
                        cert_exists = True
                except Exception as e:
                    error_text = f"Erro ao processar o certificado: {str(e)}"
                    configured = False
            
            have_client = bool((efibank_client_id or current.get("client_id") or current.get("client")))
            have_secret = bool((efibank_client_secret or current.get("client_secret") or current.get("token")))
            have_pix = bool((efibank_pix_key or current.get("pix_key")))
            configured = bool(have_client and have_secret and have_pix and cert_exists)
            if enabled and not configured:
                enabled = False
                if not error_text:
                    error_text = "Para ativar a Efi, forneça Client ID, Client Secret, Chave Pix e o certificado .p12."

        elif self.provider_key in {"pagbank", "picpay", "pushinpay", "asaas", "stripe", "coinbase", "nowpayments", "promissepay"}:
            existing = ConfigurarPagamentos._load_config().get(self.provider_key) or {}
            token_key = {
                "pagbank": "token_pagbank",
                "picpay": "token_picpay",
                "pushinpay": "token_pushinpay",
                "asaas": "token_asaas",
                "stripe": "token_stripe",
                "coinbase": "token_coinbase",
                "nowpayments": "token_nowpayments",
                "promissepay": "token_promissepay",
            }[self.provider_key]
            token_value = {
                "pagbank": pagbank_token,
                "picpay": picpay_token,
                "pushinpay": pushinpay_token,
                "asaas": asaas_token,
                "stripe": stripe_token,
                "coinbase": coinbase_token,
                "nowpayments": nowpayments_token,
                "promissepay": promissepay_token,
            }[self.provider_key]
            configured = bool((token_value is not None and token_value) or existing.get(token_key))
            if enabled and not configured:
                enabled = False
                error_text = "Informe o token para ativar este provedor."

        elif self.provider_key == "paypal":
            existing = ConfigurarPagamentos._load_config().get("paypal") or {}
            have_client = bool(paypal_client_id or existing.get("client_id"))
            have_secret = bool(paypal_client_secret or existing.get("client_secret"))
            configured = bool(have_client and have_secret)
            if enabled and not configured:
                enabled = False
                error_text = "Para ativar o PayPal, informe Client ID e Client Secret."

        elif self.provider_key == "misticpay":
            existing = ConfigurarPagamentos._load_config().get("misticpay") or {}
            have_client = bool(misticpay_client_id or existing.get("client_id"))
            have_secret = bool(misticpay_client_secret or existing.get("client_secret"))
            configured = bool(have_client and have_secret)
            
            # Se tem credenciais e está sendo ativado, validar com a API
            if enabled and configured:
                try:
                    from functions.payments.misticpay import create_misticpay_payment
                    import uuid
                    
                    # Usar credenciais novas ou existentes
                    client_id = misticpay_client_id or existing.get("client_id")
                    client_secret = misticpay_client_secret or existing.get("client_secret")
                    
                    # Tentar criar um pagamento de teste (valor mínimo)
                    try:
                        await create_misticpay_payment(
                            client_id=client_id,
                            client_secret=client_secret,
                            amount=1.0,  # Valor mínimo para teste
                            payer_name="Teste",
                            payer_document="12345678901",
                            description="Teste de configuração",
                            transaction_id=str(uuid.uuid4())
                        )
                        # Se chegou aqui, as credenciais estão válidas
                        configured = True
                    except RuntimeError as e:
                        error_msg = str(e)
                        # Verificar se é erro de IP não autorizado
                        if "IP não autorizado" in error_msg or "não está na lista de permissões" in error_msg or "IP" in error_msg and "permissões" in error_msg:
                            configured = False
                            enabled = False
                            
                            error_text = (
                                f"{emoji.wrong} **IP não autorizado**\n"
                                f"**Para resolver:**\n"
                                f"1. Ative a verificação de 2 fatores na sua conta MisticPay\n"
                                f"2. Libere todos os IPs nas configurações de segurança\n"
                                f"Após configurar, tente novamente."
                            )
                        else:
                            # Outro erro, mas as credenciais podem estar corretas
                            # Não bloquear a ativação, apenas avisar
                            configured = True  # Permitir ativar mesmo com erro (pode ser temporário)
                    except Exception as e:
                        # Erro inesperado, não bloquear
                        configured = True
                except Exception as e:
                    # Erro ao importar ou validar, não bloquear
                    configured = True
            
            if enabled and not configured:
                enabled = False
                if not error_text:
                    error_text = "Para ativar o MisticPay, informe Client ID e Client Secret."

        elif self.provider_key == "pix_manual":
            import re
            existing = ConfigurarPagamentos._load_config().get("pix_manual") or {}
            key = pix_manual_key or existing.get("pix_key")
            key_type = pix_manual_key_type or existing.get("pix_key_type")
            
            if key and key_type:
                # Validar formato da chave PIX
                key = key.strip()
                is_valid = False
                
                if key_type == "email":
                    is_valid = bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", key))
                    if not is_valid:
                        error_text = "Email inválido! Formato esperado: usuario@dominio.com"
                elif key_type == "telefone":
                    clean_phone = re.sub(r"[^\d]", "", key)
                    is_valid = len(clean_phone) >= 10 and len(clean_phone) <= 11
                    if not is_valid:
                        error_text = "Telefone inválido! Use formato: (11) 98765-4321 ou 11987654321"
                elif key_type == "cpf":
                    clean_cpf = re.sub(r"[^\d]", "", key)
                    is_valid = len(clean_cpf) == 11
                    if is_valid:
                        # Validar dígitos verificadores do CPF
                        cpf_digits = [int(d) for d in clean_cpf]
                        # Primeiro dígito
                        sum1 = sum(cpf_digits[i] * (10 - i) for i in range(9))
                        digit1 = 0 if (sum1 % 11) < 2 else 11 - (sum1 % 11)
                        # Segundo dígito
                        sum2 = sum(cpf_digits[i] * (11 - i) for i in range(10))
                        digit2 = 0 if (sum2 % 11) < 2 else 11 - (sum2 % 11)
                        is_valid = cpf_digits[9] == digit1 and cpf_digits[10] == digit2
                    if not is_valid:
                        error_text = "CPF inválido! Use 11 dígitos: 123.456.789-00 ou 12345678900"
                elif key_type == "cnpj":
                    clean_cnpj = re.sub(r"[^\d]", "", key)
                    is_valid = len(clean_cnpj) == 14
                    if is_valid:
                        # Validar dígitos verificadores do CNPJ
                        cnpj_digits = [int(d) for d in clean_cnpj]
                        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
                        sum1 = sum(cnpj_digits[i] * weights1[i] for i in range(12))
                        digit1 = 0 if (sum1 % 11) < 2 else 11 - (sum1 % 11)
                        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
                        sum2 = sum(cnpj_digits[i] * weights2[i] for i in range(13))
                        digit2 = 0 if (sum2 % 11) < 2 else 11 - (sum2 % 11)
                        is_valid = cnpj_digits[12] == digit1 and cnpj_digits[13] == digit2
                    if not is_valid:
                        error_text = "CNPJ inválido! Use 14 dígitos: 12.345.678/0001-00 ou 12345678000100"
                elif key_type == "aleatoria":
                    # Chave aleatória: geralmente UUID ou string alfanumérica
                    is_valid = len(key) >= 8 and len(key) <= 50
                    if not is_valid:
                        error_text = "Chave aleatória inválida! Deve ter entre 8 e 50 caracteres"
                
                configured = is_valid
                if enabled and not configured:
                    enabled = False
                    if not error_text:
                        error_text = "Chave PIX inválida para o tipo selecionado."
            else:
                configured = False
                if enabled:
                    enabled = False
                    error_text = "Para ativar o PIX Manual, informe a chave PIX e o tipo."

        config = ConfigurarPagamentos._load_config()
        entry = config.get(self.provider_key)
        if not isinstance(entry, dict):
            entry = {}
        old_token = str(entry.get("access_token") or "")
        entry["enabled"] = enabled
        if self.provider_key == "mercado_pago":
            final_token = old_token
            if access_token is not None:
                if access_token == "":
                    # user cleared the token
                    final_token = ""
                elif configured:
                    # new valid token provided
                    final_token = access_token
                else:
                    # invalid/new token provided - keep old one
                    final_token = old_token
            entry["access_token"] = final_token
        elif self.provider_key == "efibank":
            if efibank_client_id is not None:
                entry["client_id"] = efibank_client_id
            if efibank_client_secret is not None:
                entry["client_secret"] = efibank_client_secret
            if efibank_pix_key is not None:
                entry["pix_key"] = efibank_pix_key
            # Salvar caminho do certificado se foi processado
            if cert_path:
                entry["cert_file"] = cert_path
        elif self.provider_key == "Lyon_wallet":
            entry["enabled"] = False
            entry["api_key"] = ""
            entry["cover_fee"] = False
            entry["pix_key"] = ""
            entry["pix_key_type"] = ""
        elif self.provider_key in {"livepix", "asaas", "pagbank", "picpay", "pushinpay", "stripe", "coinbase", "nowpayments", "inter", "promissepay"}:
            token_key = {
                "livepix": "token_livepix",
                "asaas": "token_asaas",
                "pagbank": "token_pagbank",
                "picpay": "token_picpay",
                "pushinpay": "token_pushinpay",
                "stripe": "token_stripe",
                "coinbase": "token_coinbase",
                "nowpayments": "token_nowpayments",
                "inter": "token_inter",
                "promissepay": "token_promissepay",
            }[self.provider_key]
            new_value = {
                "livepix": livepix_token,
                "asaas": asaas_token,
                "pagbank": pagbank_token,
                "picpay": picpay_token,
                "pushinpay": pushinpay_token,
                "stripe": stripe_token,
                "coinbase": coinbase_token,
                "nowpayments": nowpayments_token,
                "inter": inter_token,
                "promissepay": promissepay_token,
            }[self.provider_key]
            old_value = str(entry.get(token_key) or "")
            final_value = old_value
            if new_value is not None:
                if new_value == "":
                    final_value = ""
                else:
                    final_value = new_value
            entry[token_key] = final_value
        elif self.provider_key == "nubank":
            if nubank_email is not None:
                entry["email"] = nubank_email.strip() if nubank_email else ""
            if nubank_password is not None:
                entry["password"] = nubank_password
            if nubank_pix_key is not None:
                entry["pix_key"] = nubank_pix_key.strip() if nubank_pix_key else ""
            if nubank_pix_key_type is not None:
                entry["pix_key_type"] = nubank_pix_key_type
        elif self.provider_key in {"nubank_imap", "picpay_imap", "itau_imap"}:
            if imap_email is not None:
                entry["email"] = imap_email.strip() if imap_email else ""
            if imap_password is not None:
                entry["password"] = imap_password
            if imap_pix_key is not None:
                entry["pix_key"] = imap_pix_key.strip() if imap_pix_key else ""
            if imap_pix_key_type is not None:
                entry["pix_key_type"] = imap_pix_key_type
        elif self.provider_key == "paypal":
            if paypal_client_id is not None:
                entry["client_id"] = paypal_client_id
            if paypal_client_secret is not None:
                entry["client_secret"] = paypal_client_secret
        elif self.provider_key == "misticpay":
            if misticpay_client_id is not None:
                entry["client_id"] = misticpay_client_id
            if misticpay_client_secret is not None:
                entry["client_secret"] = misticpay_client_secret
        elif self.provider_key == "pix_manual":
            if pix_manual_key is not None:
                entry["pix_key"] = pix_manual_key.strip() if pix_manual_key else ""
            if pix_manual_key_type is not None:
                entry["pix_key_type"] = pix_manual_key_type
        config[self.provider_key] = entry

        # Salvar configurações no database
        db.save_document("payment_configs", config)

        # Atualizar status de habilitado no documento pagamentos
        pagamentos = db.get_document("pagamentos") or {}
        pagamentos[self.provider_key] = enabled
        db.save_document("pagamentos", {}, pagamentos)
        ConfigurarPagamentos._invalidate_payment_method_caches()

        if self.categoria == "wallet":
            components = ConfigurarPagamentos._wallet_components(inter)
        elif self.categoria == "imap":
            components = ConfigurarPagamentos._imap_components(inter, self.provider_key)
        elif self.categoria == "main" or not self.categoria:
            components = ConfigurarPagamentos.categoria_pagamentos_components(inter)
        else:
            components = ConfigurarPagamentos.pagamentos_components(inter, self.categoria)

        await inter.edit_original_message(
            content=None,
            embed=None,
            components=components,
            flags=disnake.MessageFlags(is_components_v2=True),
        )

        # Feedback ao usuário (ephemeral) se houve problema na validação
        if error_text:
            await message.error(inter, error_text, followup=True)


class WalletWithdrawModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.Label(
                text="Valor do saque",
                component=disnake.ui.TextInput(
                    placeholder="Ex: 25.00",
                    custom_id="wallet_withdraw_amount",
                    style=disnake.TextInputStyle.short,
                    required=True,
                ),
                description="Informe o valor em reais.",
            )
        ]
        super().__init__(title="Sacar da Carteira", components=components, custom_id="wallet_withdraw_modal")

    async def callback(self, inter: disnake.ModalInteraction):
        await message.wait(inter)
        raw_amount = str(inter.resolved_values.get("wallet_withdraw_amount") or "").replace(",", ".").strip()
        try:
            amount = float(raw_amount)
            if amount <= 0:
                raise ValueError
        except Exception:
            await inter.edit_original_message(
                content=None,
                embed=None,
                components=ConfigurarPagamentos._wallet_components(inter),
                flags=disnake.MessageFlags(is_components_v2=True),
            )
            await message.error(inter, "Informe um valor de saque valido.", followup=True)
            return

        try:
            from functions.payments.Lyon_wallet import create_Lyon_withdraw_from_settings
            result = await create_Lyon_withdraw_from_settings(amount)
            status = result.get("status") or result.get("success") or "solicitado"
            feedback = f"Saque solicitado. Status: `{status}`"
        except Exception as exc:
            feedback = f"Nao foi possivel solicitar o saque agora: {exc}"

        await inter.edit_original_message(
            content=None,
            embed=None,
            components=ConfigurarPagamentos._wallet_components(inter),
            flags=disnake.MessageFlags(is_components_v2=True),
        )
        await message.plain(inter, feedback, followup=True)


def setup(bot: commands.Bot):
    bot.add_cog(ConfigurarPagamentos(bot))
