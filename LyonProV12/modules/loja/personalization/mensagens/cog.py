"""
Sistema de personalização de mensagens da loja
"""
import disnake
from disnake.ext import commands
from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message


PURCHASE_MODE_INFO = {
    "image": {
        "label": "Imagem",
        "description": "Gerada automaticamente com avatar, produtos e total",
        "summary": "A mensagem sera gerada automaticamente com avatar, nome, produtos e total pago.",
        "emoji": "image",
    },
    "embed": {
        "label": "Embed Normal",
        "description": "Importe um JSON de embed igual ao sistema atual",
        "summary": "Use um JSON de embed com variaveis para montar a mensagem aprovada.",
        "emoji": "embed",
    },
    "v2": {
        "label": "Components V2",
        "description": "Edite a mensagem com texto, variaveis e separadores",
        "summary": "Use texto em Components V2 com variaveis para uma mensagem limpa.",
        "emoji": "wand",
    },
}


def _normalize_purchase_mode(value: str | None) -> str:
    mode = str(value or "").lower().strip()
    aliases = {
        "imagem": "image",
        "image": "image",
        "img": "image",
        "embed": "embed",
        "normal": "embed",
        "components": "v2",
        "componentes": "v2",
        "v2": "v2",
    }
    return aliases.get(mode, "image")


def _get_purchase_event_config() -> dict:
    config = db.get_document("loja_personalization") or {}
    event = config.get("purchase_event") or {}
    event.setdefault("mode", None)
    event.setdefault("event_channel_id", None)
    event.setdefault("feedback_channel_id", None)
    event.setdefault("buy_button_enabled", True)
    event.setdefault("buy_button_label", "Comprar")
    event.setdefault("buy_button_emoji", str(getattr(emoji, "cart", "")) or "")
    event.setdefault("feedback_button_enabled", True)
    event.setdefault("feedback_button_label", "Feedbacks")
    event.setdefault("feedback_button_emoji", str(getattr(emoji, "star", "")) or "")
    return event


def _save_purchase_event_config(event: dict) -> None:
    config = db.get_document("loja_personalization") or {}
    current = config.get("purchase_event") or {}
    current.update(event)
    if "mode" in event:
        current["mode"] = _normalize_purchase_mode(event.get("mode"))
    elif current.get("mode"):
        current["mode"] = _normalize_purchase_mode(current.get("mode"))
    else:
        current.pop("mode", None)
    config["purchase_event"] = current
    db.save_document("loja_personalization", config)


def _channel_label(channel_id) -> str:
    return f"<#{channel_id}>" if channel_id else "`Indefinido`"


def _button_status(enabled: bool) -> str:
    return "Ativo" if enabled else "Desativado"


async def _safe_defer_update(inter: disnake.MessageInteraction) -> bool:
    if inter.response.is_done():
        return True
    try:
        await inter.response.defer(with_message=False)
        return True
    except (disnake.errors.NotFound, disnake.HTTPException):
        return False


def _event_channel_id(event_config: dict):
    if event_config.get("event_channel_id"):
        return event_config.get("event_channel_id")
    if event_config.get("channel_id"):
        return event_config.get("channel_id")
    canais = db.get_document("canais") or {}
    return canais.get("canal_de_evento_de_compras")


class PersonalizarMensagens(commands.Cog):
    """Personalização de mensagens da loja"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @staticmethod
    def panel(inter: disnake.MessageInteraction) -> dict:
        """Retorna o painel de personalização de mensagens"""
        mode = db.get_document("custom_mode").get("mode", "components")
        
        if mode == "embed":
            return PersonalizarMensagens._panel_embed(inter)
        else:
            return PersonalizarMensagens._panel_components(inter)
    
    @staticmethod
    def _panel_components(inter: disnake.MessageInteraction) -> dict:
        """Painel em modo components v2"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))
        
        # Carregar configurações atuais
        config = db.get_document("loja_personalization") or {}
        event_config = _get_purchase_event_config()
        feedback_config = config.get("feedback_incentive", {})
        
        # Status das configurações
        event_configured = bool(event_config.get("mode") or event_config.get("channel_id"))
        feedback_configured = feedback_config.get("message") is not None
        
        return {"components": [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Loja > Personalizar > **Mensagens**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    "Configure as mensagens automáticas da sua loja.\n"
                    "Personalize eventos de compra e incentivos de feedback."
                ),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("**Configurações Disponíveis**"),
                disnake.ui.TextDisplay(
                    f"{emoji.on if event_configured else emoji.off} **Compra Aprovada**\n"
                    f"-# Mensagem pública quando alguém compra\n"
                    f"{emoji.on if feedback_configured else emoji.off} **Incentivo de Feedback**\n"
                    f"-# Mensagem para incentivar avaliações"
                ),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Compra Aprovada",
                        style=disnake.ButtonStyle.blurple,
                        emoji=emoji.sparkles,
                        custom_id="Loja_Personalizar_EventoCompra"
                    ),
                    disnake.ui.Button(
                        label="Incentivo Feedback",
                        style=disnake.ButtonStyle.blurple,
                        emoji=emoji.star,
                        custom_id="Loja_Personalizar_Feedback"
                    ),
                ),
                **container_kwargs
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Loja_Personalizar"
                )
            )
        ]}
    
    @staticmethod
    def _panel_embed(inter: disnake.MessageInteraction) -> dict:
        """Painel em modo embed"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        embed_kwargs = {}
        if primary_color_hex:
            embed_kwargs["color"] = int(primary_color_hex.replace("#", ""), 16)
        
        # Carregar configurações atuais
        config = db.get_document("loja_personalization") or {}
        event_config = _get_purchase_event_config()
        feedback_config = config.get("feedback_incentive", {})
        
        # Status das configurações
        event_configured = bool(event_config.get("mode") or event_config.get("channel_id"))
        feedback_configured = feedback_config.get("message") is not None
        
        embed = disnake.Embed(
            title="Personalizar Mensagens",
            description=(
                "-# Painel > Loja > Personalizar > **Mensagens**\n\n"
                "Configure as mensagens automáticas da sua loja.\n\n"
                f"{emoji.on if event_configured else emoji.off} **Evento de Compra**\n"
                f"Mensagem pública quando alguém compra\n"
                f"{emoji.on if feedback_configured else emoji.off} **Incentivo de Feedback**\n"
                f"Mensagem para incentivar avaliações"
            ),
            **embed_kwargs
        )
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Compra Aprovada",
                    style=disnake.ButtonStyle.blurple,
                    emoji=emoji.sparkles,
                    custom_id="Loja_Personalizar_EventoCompra"
                ),
                disnake.ui.Button(
                    label="Incentivo Feedback",
                    style=disnake.ButtonStyle.blurple,
                    emoji=emoji.star,
                    custom_id="Loja_Personalizar_Feedback"
                ),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Loja_Personalizar"
                )
            )
        ]
        
        return {"embed": embed, "components": components}

    @staticmethod
    def purchase_approved_panel(inter: disnake.MessageInteraction) -> dict:
        """Painel de configuracao da mensagem de compra aprovada."""
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            try:
                container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))
            except (TypeError, ValueError):
                pass

        event_config = _get_purchase_event_config()
        mode_key = _normalize_purchase_mode(event_config.get("mode"))
        mode_info = PURCHASE_MODE_INFO[mode_key]
        channel_id = _event_channel_id(event_config)

        options = []
        for value in ("embed", "v2", "image"):
            info = PURCHASE_MODE_INFO[value]
            options.append(
                disnake.SelectOption(
                    label=info["label"],
                    value=value,
                    description=info["description"],
                    emoji=getattr(emoji, info["emoji"], None),
                    default=value == mode_key,
                )
            )

        buy_enabled = bool(event_config.get("buy_button_enabled", True))
        feedback_enabled = bool(event_config.get("feedback_button_enabled", True))
        buy_label = str(event_config.get("buy_button_label") or "Comprar")
        feedback_label = str(event_config.get("feedback_button_label") or "Feedbacks")

        mode_buttons = []
        if mode_key == "embed":
            mode_buttons.append(
                disnake.ui.Button(
                    label="JSON Embed",
                    style=disnake.ButtonStyle.blurple,
                    emoji=getattr(emoji, "embed", None),
                    custom_id="Loja_CompraAprovada_EmbedJSON",
                )
            )
        elif mode_key == "v2":
            mode_buttons.append(
                disnake.ui.Button(
                    label="Texto V2",
                    style=disnake.ButtonStyle.blurple,
                    emoji=getattr(emoji, "wand", None),
                    custom_id="Loja_CompraAprovada_V2Text",
                )
            )

        children = [
            disnake.ui.TextDisplay(
                f"# {emoji.lyon}\n"
                "-# Painel > Loja > Personalizar > **Mensagem de Compra Aprovada**"
            ),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"**Modo Atual:** `{mode_info['label']}`\n"
                f"{mode_info['summary']}"
            ),
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Loja_CompraAprovada_Modo",
                    placeholder=mode_info["label"],
                    options=options,
                    min_values=1,
                    max_values=1,
                )
            ),
            disnake.ui.TextDisplay(
                f"{getattr(emoji, 'cart', '')} **Comprar:** `{_button_status(buy_enabled)}` | Label: `{buy_label}`\n"
                f"{getattr(emoji, 'star', '')} **Feedbacks:** `{_button_status(feedback_enabled)}` | Label: `{feedback_label}`\n"
                f"{getattr(emoji, 'channel', '')} **Canal da compra aprovada:** {_channel_label(channel_id)}"
            ),
        ]

        if mode_buttons:
            children.append(disnake.ui.ActionRow(*mode_buttons))

        children.extend(
            [
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label=("Desativar Comprar" if buy_enabled else "Ativar Comprar"),
                        style=disnake.ButtonStyle.danger if buy_enabled else disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "off" if buy_enabled else "on", None),
                        custom_id="Loja_CompraAprovada_ToggleBuy",
                    ),
                    disnake.ui.Button(
                        label="Emoji",
                        style=disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, "brush", None),
                        custom_id="Loja_CompraAprovada_BuyEmoji",
                    ),
                    disnake.ui.Button(
                        label="Label",
                        style=disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, "edit", None),
                        custom_id="Loja_CompraAprovada_BuyLabel",
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label=("Desativar Feedbacks" if feedback_enabled else "Ativar Feedbacks"),
                        style=disnake.ButtonStyle.danger if feedback_enabled else disnake.ButtonStyle.success,
                        emoji=getattr(emoji, "off" if feedback_enabled else "on", None),
                        custom_id="Loja_CompraAprovada_ToggleFeedback",
                    ),
                    disnake.ui.Button(
                        label="Emoji",
                        style=disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, "brush", None),
                        custom_id="Loja_CompraAprovada_FeedbackEmoji",
                    ),
                    disnake.ui.Button(
                        label="Label",
                        style=disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, "edit", None),
                        custom_id="Loja_CompraAprovada_FeedbackLabel",
                    ),
                    disnake.ui.Button(
                        label="Definir Canal",
                        style=disnake.ButtonStyle.grey,
                        emoji=getattr(emoji, "link", None),
                        custom_id="Loja_CompraAprovada_ChannelPrompt",
                    ),
                ),
            ]
        )

        return {
            "embed": None,
            "content": None,
            "components": [
                disnake.ui.Container(*children, **container_kwargs),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.back,
                        custom_id="Loja_Personalizar_Mensagens",
                    )
                ),
            ],
            "flags": disnake.MessageFlags(is_components_v2=True),
        }
    
    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Loja_Personalizar_Mensagens":
            mode = db.get_document("custom_mode").get("mode")
            
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)
            
            panel_data = self.panel(inter)
            await inter.edit_original_message(**panel_data)
        
        elif inter.component.custom_id == "Loja_Personalizar_EventoCompra":
            if not await _safe_defer_update(inter):
                return
            await inter.edit_original_message(**self.purchase_approved_panel(inter))
        
        elif inter.component.custom_id == "Loja_Personalizar_Feedback":
            await inter.response.send_modal(ConfigurarFeedbackModal())

        elif inter.component.custom_id == "Loja_CompraAprovada_ToggleBuy":
            event_config = _get_purchase_event_config()
            _save_purchase_event_config({"buy_button_enabled": not bool(event_config.get("buy_button_enabled", True))})
            if not await _safe_defer_update(inter):
                return
            await inter.edit_original_message(**self.purchase_approved_panel(inter))

        elif inter.component.custom_id == "Loja_CompraAprovada_ToggleFeedback":
            event_config = _get_purchase_event_config()
            _save_purchase_event_config({"feedback_button_enabled": not bool(event_config.get("feedback_button_enabled", True))})
            if not await _safe_defer_update(inter):
                return
            await inter.edit_original_message(**self.purchase_approved_panel(inter))

        elif inter.component.custom_id == "Loja_CompraAprovada_BuyEmoji":
            await inter.response.send_modal(CompraAprovadaButtonModal("buy", "emoji"))

        elif inter.component.custom_id == "Loja_CompraAprovada_BuyLabel":
            await inter.response.send_modal(CompraAprovadaButtonModal("buy", "label"))

        elif inter.component.custom_id == "Loja_CompraAprovada_FeedbackEmoji":
            await inter.response.send_modal(CompraAprovadaButtonModal("feedback", "emoji"))

        elif inter.component.custom_id == "Loja_CompraAprovada_FeedbackLabel":
            await inter.response.send_modal(CompraAprovadaButtonModal("feedback", "label"))

        elif inter.component.custom_id == "Loja_CompraAprovada_EmbedJSON":
            await inter.response.send_modal(CompraAprovadaEmbedJSONModal())

        elif inter.component.custom_id == "Loja_CompraAprovada_V2Text":
            await inter.response.send_modal(CompraAprovadaV2TextModal())

        elif inter.component.custom_id == "Loja_CompraAprovada_ChannelPrompt":
            await inter.response.send_message(
                components=[
                    disnake.ui.Container(
                        disnake.ui.TextDisplay(
                            f"## {getattr(emoji, 'channel', '')} Canal da Compra Aprovada\n"
                            "Selecione o canal onde o comprovante publico da compra aprovada sera enviado."
                        ),
                        disnake.ui.ActionRow(
                            disnake.ui.ChannelSelect(
                                placeholder="Selecione um canal",
                                channel_types=[disnake.ChannelType.text],
                                custom_id="Loja_CompraAprovada_Channel",
                                min_values=1,
                                max_values=1,
                            )
                        ),
                    )
                ],
                flags=disnake.MessageFlags(is_components_v2=True),
                ephemeral=True,
            )

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")

        if custom_id == "Loja_CompraAprovada_Modo":
            selected = inter.values[0] if inter.values else "image"
            _save_purchase_event_config({"mode": _normalize_purchase_mode(selected)})
            if not await _safe_defer_update(inter):
                return
            await inter.edit_original_message(**self.purchase_approved_panel(inter))

        elif custom_id == "Loja_CompraAprovada_Channel":
            if not inter.values:
                await inter.response.send_message(f"{emoji.wrong} Nenhum canal selecionado.", ephemeral=True)
                return

            channel_id = int(inter.values[0])
            _save_purchase_event_config({"event_channel_id": channel_id, "channel_id": channel_id})

            canais = db.get_document("canais") or {}
            canais["canal_de_evento_de_compras"] = channel_id
            db.save_document("canais", canais)

            await inter.response.send_message(
                f"{emoji.correct} Canal da compra aprovada definido para <#{channel_id}>.",
                ephemeral=True,
            )


class CompraAprovadaButtonModal(disnake.ui.Modal):
    """Modal para editar label ou emoji dos botoes da compra aprovada."""

    def __init__(self, target: str, field: str):
        self.target = target
        self.field = field
        event_config = _get_purchase_event_config()

        prefix = "buy" if target == "buy" else "feedback"
        readable_target = "Comprar" if target == "buy" else "Feedbacks"
        readable_field = "Emoji" if field == "emoji" else "Label"
        key = f"{prefix}_button_{field}"
        fallback = "Comprar" if target == "buy" and field == "label" else "Feedbacks"

        components = [
            disnake.ui.TextInput(
                label=f"{readable_field} do botao {readable_target}",
                placeholder="Digite o novo valor",
                custom_id="value",
                style=disnake.TextInputStyle.short,
                value=str(event_config.get(key) or fallback),
                required=True,
                max_length=40 if field == "label" else 120,
            )
        ]

        super().__init__(
            title=f"Editar {readable_field}",
            custom_id=f"CompraAprovada_{target}_{field}_Modal",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        value = inter.text_values.get("value", "").strip()
        prefix = "buy" if self.target == "buy" else "feedback"
        key = f"{prefix}_button_{self.field}"
        _save_purchase_event_config({key: value})

        if not await _safe_defer_update(inter):
            return
        await inter.edit_original_message(**PersonalizarMensagens.purchase_approved_panel(inter))


class CompraAprovadaEmbedJSONModal(disnake.ui.Modal):
    """Modal para configurar o JSON do embed da compra aprovada."""

    def __init__(self):
        event_config = _get_purchase_event_config()
        current = event_config.get("embed_json") or (
            '{\n'
            '  "title": "Compra Realizada",\n'
            '  "description": "Cliente: {cliente}\\nCarrinho:\\n{produtos}\\nValor pago: {total}",\n'
            '  "color": 5763719\n'
            '}'
        )

        components = [
            disnake.ui.TextInput(
                label="JSON do Embed",
                placeholder="Cole um JSON de embed com variaveis",
                custom_id="embed_json",
                style=disnake.TextInputStyle.paragraph,
                value=str(current)[:4000],
                required=True,
                max_length=4000,
            )
        ]

        super().__init__(
            title="Mensagem Embed",
            custom_id="CompraAprovada_EmbedJSON_Modal",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        _save_purchase_event_config({
            "mode": "embed",
            "embed_json": inter.text_values.get("embed_json", "").strip(),
        })

        if not await _safe_defer_update(inter):
            return
        await inter.edit_original_message(**PersonalizarMensagens.purchase_approved_panel(inter))


class CompraAprovadaV2TextModal(disnake.ui.Modal):
    """Modal para configurar o texto em Components V2 da compra aprovada."""

    DEFAULT_TEXT = (
        "## Compra Realizada\n"
        "**Cliente:** {cliente}\n"
        "**Carrinho:**\n{produtos}\n"
        "**Valor pago:** `{total}`\n"
        "**Pedido:** `{pedido}`\n"
        "-# {data} BRT"
    )

    def __init__(self):
        event_config = _get_purchase_event_config()
        current = event_config.get("v2_message") or self.DEFAULT_TEXT

        components = [
            disnake.ui.TextInput(
                label="Texto Components V2",
                placeholder="Use variaveis como {cliente}, {produtos}, {total}, {pedido}",
                custom_id="v2_message",
                style=disnake.TextInputStyle.paragraph,
                value=str(current)[:4000],
                required=True,
                max_length=4000,
            )
        ]

        super().__init__(
            title="Mensagem Components V2",
            custom_id="CompraAprovada_V2Text_Modal",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        _save_purchase_event_config({
            "mode": "v2",
            "v2_message": inter.text_values.get("v2_message", "").strip(),
        })

        if not await _safe_defer_update(inter):
            return
        await inter.edit_original_message(**PersonalizarMensagens.purchase_approved_panel(inter))


class ConfigurarEventoCompraModal(disnake.ui.Modal):
    """Modal para configurar visual do evento de compra"""
    
    def __init__(self):
        # Carregar configuração atual
        config = db.get_document("loja_personalization") or {}
        event_config = config.get("purchase_event", {})
        
        current_color = event_config.get("color", "")
        current_image = event_config.get("image", "")
        
        components = [
            disnake.ui.TextInput(
                label="Cor do Evento (Hex)",
                placeholder="Ex: #00FF00 (deixe vazio para cor padrão verde)",
                custom_id="color",
                style=disnake.TextInputStyle.short,
                value=current_color,
                required=False,
                max_length=7
            ),
            disnake.ui.TextInput(
                label="URL da Imagem (Embed)",
                placeholder="https://... (deixe vazio para sem imagem)",
                custom_id="image",
                style=disnake.TextInputStyle.short,
                value=current_image,
                required=False
            )
        ]
        
        super().__init__(
            title="Configurar Visual do Evento",
            custom_id="ConfigurarEventoCompra_Modal",
            components=components
        )
    
    async def callback(self, inter: disnake.ModalInteraction):
        mode = db.get_document("custom_mode").get("mode")
        
        if mode == "embed":
            await embed_message.wait(inter)
        else:
            await message.wait(inter)
        
        # Salvar configuração (apenas cor e imagem)
        _save_purchase_event_config({
            "color": inter.text_values.get("color", "").strip(),
            "image": inter.text_values.get("image", "").strip(),
        })
        
        # Atualizar painel
        panel_data = PersonalizarMensagens.purchase_approved_panel(inter)
        await inter.edit_original_message(**panel_data)


class ConfigurarFeedbackModal(disnake.ui.Modal):
    """Modal para configurar mensagem de incentivo de feedback"""
    
    def __init__(self):
        # Carregar configuração atual
        config = db.get_document("loja_personalization") or {}
        feedback_config = config.get("feedback_incentive", {})
        
        current_message = feedback_config.get(
            "message",
            "**Obrigado pela sua compra!** 🎉\n\n"
            "Que tal deixar uma avaliação sobre sua experiência?\n"
            "-# Seu feedback é muito importante para nós!"
        )
        current_button_text = feedback_config.get("button_text", "Deixar Avaliação")
        
        components = [
            disnake.ui.TextInput(
                label="Mensagem de Incentivo",
                placeholder="Mensagem para incentivar feedback",
                custom_id="message",
                style=disnake.TextInputStyle.paragraph,
                value=current_message,
                required=True,
                max_length=1000
            ),
            disnake.ui.TextInput(
                label="Texto do Botão",
                placeholder="Ex: Deixar Avaliação",
                custom_id="button_text",
                style=disnake.TextInputStyle.short,
                value=current_button_text,
                required=True,
                max_length=30
            )
        ]
        
        super().__init__(
            title="Configurar Incentivo de Feedback",
            custom_id="ConfigurarFeedback_Modal",
            components=components
        )
    
    async def callback(self, inter: disnake.ModalInteraction):
        mode = db.get_document("custom_mode").get("mode")
        
        if mode == "embed":
            await embed_message.wait(inter)
        else:
            await message.wait(inter)
        
        # Salvar configuração
        config = db.get_document("loja_personalization") or {}
        config["feedback_incentive"] = {
            "message": inter.text_values.get("message"),
            "button_text": inter.text_values.get("button_text")
        }
        db.save_document("loja_personalization", config)
        
        # Atualizar painel
        panel_data = PersonalizarMensagens.panel(inter)
        await inter.edit_original_message(**panel_data)


def setup(bot: commands.Bot):
    bot.add_cog(PersonalizarMensagens(bot))
