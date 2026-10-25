import disnake
from disnake.ext import commands, tasks
import asyncio
from typing import Optional

from functions.emoji import emoji
from functions.message import message, embed_message
from functions.database import database as db
from . import helpers
from commands.admin.anunciar.builder import Builder
import re
import datetime

# region Modals
class GerenciarTokensModal(disnake.ui.Modal):
    def __init__(self, tokens_atuais: list):
        tokens_text = "\n".join(tokens_atuais) if tokens_atuais else ""
        super().__init__(
            title="Gerenciar Tokens de Pros",
            custom_id="DisparadorDM_GerenciarTokensModal",
            components=[
                disnake.ui.TextInput(
                    label="Tokens (1 por linha)",
                    placeholder="Cole os tokens dos bots aqui, um por linha",
                    custom_id="tokens",
                    style=disnake.TextInputStyle.paragraph,
                    required=False,
                    value=tokens_text,
                    max_length=4000
                )
            ],
        )

class DefinirMensagemModal(disnake.ui.Modal):
    def __init__(self):
        editor_data = helpers.get_editor_data()
        super().__init__(
            title="Definir Mensagem",
            custom_id="DisparadorDM_DefinirMensagemModal",
            components=[
                disnake.ui.TextInput(
                    label="Mensagem",
                    custom_id="message",
                    style=disnake.TextInputStyle.paragraph,
                    placeholder="Digite a mensagem que deseja enviar",
                    value=editor_data.get("content", ""),
                    max_length=2000,
                    required=True
                )
            ],
        )

class DefinirEmbedModal(disnake.ui.Modal):
    def __init__(self):
        editor_data = helpers.get_editor_data()
        embed_data = editor_data.get("embed", {})
        super().__init__(
            title="Definir Embed",
            custom_id="DisparadorDM_DefinirEmbedModal",
            components=[
                disnake.ui.TextInput(
                    label="Título",
                    custom_id="embed_title",
                    style=disnake.TextInputStyle.short,
                    required=False,
                    value=embed_data.get("title", "")
                ),
                disnake.ui.TextInput(
                    label="Descrição",
                    custom_id="embed_description",
                    style=disnake.TextInputStyle.paragraph,
                    placeholder="Descrição do embed aqui",
                    required=True,
                    value=embed_data.get("description", "")
                ),
                disnake.ui.TextInput(
                    label="Cor (Hex)",
                    custom_id="embed_color",
                    style=disnake.TextInputStyle.short,
                    required=False,
                    placeholder="#FFFFFF",
                    value=embed_data.get("color", "")
                ),
                disnake.ui.TextInput(
                    label="Footer",
                    custom_id="embed_footer",
                    style=disnake.TextInputStyle.short,
                    required=False,
                    value=embed_data.get("footer", "")
                ),
            ]
        )

class DefinirImagensModal(disnake.ui.Modal):
    def __init__(self):
        editor_data = helpers.get_editor_data()
        embed_data = editor_data.get("embed", {})
        has_embed = bool(embed_data.get("title") or embed_data.get("description"))

        components = [
            disnake.ui.TextInput(
                label="URL da imagem externa",
                custom_id="externalImage",
                style=disnake.TextInputStyle.short,
                required=False,
                value=editor_data.get("externalImage", "")
            ),
        ]

        if has_embed:
            components.extend([
                disnake.ui.TextInput(
                    label="URL do Banner do Embed",
                    custom_id="banner",
                    style=disnake.TextInputStyle.short,
                    required=False,
                    value=embed_data.get("banner", "")
                ),
                disnake.ui.TextInput(
                    label="URL da Thumbnail do Embed",
                    custom_id="thumbnail",
                    style=disnake.TextInputStyle.short,
                    required=False,
                    value=embed_data.get("thumbnail", "")
                ),
            ])
        
        super().__init__(
            title="Definir Imagens",
            custom_id="DisparadorDM_DefinirImagensModal",
            components=components
        )

class ConfigurarDisparoModal(disnake.ui.Modal):
    def __init__(self):
        super().__init__(
            title="Configurar Disparo",
            custom_id="DisparadorDM_ConfigurarDisparoModal",
            components=[
                disnake.ui.TextInput(
                    label="ID do Servidor (opcional)",
                    custom_id="server_id",
                    style=disnake.TextInputStyle.short,
                    required=False,
                    placeholder="Vazio = servidor principal"
                ),
                disnake.ui.TextInput(
                    label="ID do Cargo (opcional)",
                    custom_id="role_id",
                    style=disnake.TextInputStyle.short,
                    required=False,
                    placeholder="Vazio = enviar para todos"
                ),
                disnake.ui.TextInput(
                    label="Cargos Excluídos (separados por vírgula)",
                    custom_id="exclude_roles",
                    style=disnake.TextInputStyle.paragraph,
                    required=False,
                    placeholder="Ex: 123456789, 987654321"
                ),
                disnake.ui.TextInput(
                    label="Usuários Excluídos (separados por vírgula)",
                    custom_id="exclude_users",
                    style=disnake.TextInputStyle.paragraph,
                    required=False,
                    placeholder="Ex: 123456789, 987654321"
                ),
            ],
        )

class DefinirBotoesModal(disnake.ui.Modal):
    def __init__(self):
        super().__init__(
            title="Adicionar Botão",
            custom_id="DisparadorDM_DefinirBotoesModal",
            components=[
                disnake.ui.TextInput(
                    label="Label",
                    custom_id="button_label",
                    required=True,
                    max_length=80
                ),
                disnake.ui.TextInput(
                    label="URL (Obrigatório para botões de link)",
                    custom_id="button_url",
                    placeholder="https://exemplo.com",
                    required=False
                ),
                disnake.ui.TextInput(
                    label="Emoji (Opcional)",
                    custom_id="button_emoji",
                    required=False
                ),
            ]
        )

# endregion


class DisparadorDMCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.disparo_em_andamento = False
        self.task_disparo = None

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.bio_updater.is_running():
            self.bio_updater.start()

    def cog_unload(self):
        self.bio_updater.cancel()

    @tasks.loop(hours=1)
    async def bio_updater(self):
        """Atualiza a bio dos bots configurados."""
        try:
            config = helpers.carregar_config()
            tokens = config.get("tokens", [])
            
            for token in tokens:
                bot_info = helpers.obter_bot_info(token)
                if bot_info:
                    try:
                        import requests
                        
                        description = (
                            f"{emoji.lyon}\n"
                            f"https://Lyonapplications.com.br"
                        )
                        
                        app_id = bot_info.get("id")
                        url = f"https://discord.com/api/v10/applications/{app_id}"
                        headers = {
                            "authorization": f"Bot {token}",
                            "content-type": "application/json",
                        }
                        payload = {"description": description}
                        requests.patch(url, headers=headers, json=payload, timeout=10)
                    except Exception as e:
                        print(f"Erro ao atualizar bio: {e}")
        except Exception as e:
            print(f"Erro no bio_updater: {e}")

    @bio_updater.before_loop
    async def before_bio_updater(self):
        await self.bot.wait_until_ready()

    @staticmethod
    def Painel() -> list[disnake.ui.Container]:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        config = helpers.carregar_config()
        tokens = config.get("tokens", [])
        total_tokens, tokens_validos, tokens_invalidos, tokens_pendentes = helpers.token_status_counts(tokens, config)
        
        mensagem_data = config.get("mensagem", {})
        mensagem_configurada = bool(
            mensagem_data.get("content") or 
            mensagem_data.get("embed")
        )
        
        temp_db = helpers.carregar_temp_db()
        total_alvo = len(temp_db.get("usuarios_alvo", []))
        total_enviados = len(temp_db.get("usuarios_enviados", []))
        pendentes = total_alvo - total_enviados
        tokens_falhos = len(temp_db.get("tokens_falhos", []))

        total_falhos = len(temp_db.get("usuarios_falhos", []))
        pendentes = total_alvo - total_enviados - total_falhos

        resumo = (
            f"{emoji.robot} **Pros configurados:** `{total_tokens}` (Válidos: `{tokens_validos}` | Inválidos: `{tokens_invalidos}` | Pendentes: `{tokens_pendentes}`)\n"
            f"{emoji.message} **Mensagem:** `{'Configurada' if mensagem_configurada else 'Não configurada'}`\n"
            f"{emoji.members} **Usuários alvo:** `{total_alvo}`\n"
            f"{emoji.correct} **Enviados:** `{total_enviados}`\n"
            f"{emoji.wrong} **Erros:** `{total_falhos}`\n"
            f"{emoji.time} **Pendentes:** `{pendentes}`"
        )
        
        if tokens_falhos > 0:
            resumo += f"\n{emoji.warn} **Tokens falhos:** `{tokens_falhos}`"
        
        # Aviso sobre intents
        if tokens_validos > 0:
            resumo += f"\n\n{emoji.warn} **Aviso:** Certifique-se de que todos os bots têm as intents privilegiadas ativadas no Developer Portal (PRESENCE, SERVER_MEMBERS, MESSAGE_CONTENT)."

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Automações > **Disparador DM's**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("Configure o sistema de disparo de mensagens diretas em massa."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(resumo),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Gerenciar Tokens",
                        style=disnake.ButtonStyle.blurple,
                        emoji=emoji.robot,
                        custom_id="DisparadorDM_GerenciarTokens"
                    ),
                    disnake.ui.Button(
                        label="Mensagem",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.message,
                        custom_id="DisparadorDM_EditarMensagem"
                    ),
                    disnake.ui.Button(
                        label="Atualizar",
                        style=disnake.ButtonStyle.green,
                        emoji=emoji.reload,
                        custom_id="DisparadorDM_AtualizarPainel"
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Iniciar Disparo",
                        style=disnake.ButtonStyle.green,
                        emoji=emoji.correct,
                        custom_id="DisparadorDM_IniciarDisparo",
                        disabled=not mensagem_configurada or tokens_validos == 0
                    ),
                    disnake.ui.Button(
                        label="Limpar DB",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.delete,
                        custom_id="DisparadorDM_LimparDB",
                        disabled=total_alvo == 0 and tokens_falhos == 0
                    ),
                    disnake.ui.Button(
                        label=f"Ver Tokens Falhos ({tokens_falhos})" if tokens_falhos > 0 else "Tokens Falhos",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.warn,
                        custom_id="DisparadorDM_VerTokensFalhos",
                        disabled=tokens_falhos == 0
                    ),
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="DisparadorDM_VoltarAutomacoes"
                ),
            )
        ]

    @staticmethod
    def PainelEmbed() -> tuple[disnake.Embed, list[disnake.ui.ActionRow]]:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        config = helpers.carregar_config()
        tokens = config.get("tokens", [])
        total_tokens, tokens_validos, tokens_invalidos, tokens_pendentes = helpers.token_status_counts(tokens, config)
        
        mensagem_data = config.get("mensagem", {})
        mensagem_configurada = bool(
            mensagem_data.get("content") or 
            mensagem_data.get("embed")
        )
        
        temp_db = helpers.carregar_temp_db()
        total_alvo = len(temp_db.get("usuarios_alvo", []))
        total_enviados = len(temp_db.get("usuarios_enviados", []))
        pendentes = total_alvo - total_enviados

        total_falhos = len(temp_db.get("usuarios_falhos", []))
        pendentes = total_alvo - total_enviados - total_falhos

        description_text = (
            f"**Pros configurados:** `{total_tokens}` (Válidos: `{tokens_validos}` | Inválidos: `{tokens_invalidos}` | Pendentes: `{tokens_pendentes}`)\n"
            f"**Mensagem:** `{'Configurada' if mensagem_configurada else 'Não configurada'}`\n"
            f"**Usuários alvo:** `{total_alvo}`\n"
            f"**Enviados:** `{total_enviados}`\n"
            f"**Erros:** `{total_falhos}`\n"
            f"**Pendentes:** `{pendentes}`"
        )
        
        # Aviso sobre intents
        if tokens_validos > 0:
            description_text += f"\n\n**Aviso:** Certifique-se de que todos os bots têm as intents privilegiadas ativadas no Developer Portal (PRESENCE, SERVER_MEMBERS, MESSAGE_CONTENT)."
        
        embed = disnake.Embed(
            title=f"Disparador DM's",
            description=description_text
        )
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color

        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Gerenciar Tokens",
                    style=disnake.ButtonStyle.blurple,
                    emoji=emoji.robot,
                    custom_id="DisparadorDM_GerenciarTokens"
                ),
                disnake.ui.Button(
                    label="Mensagem",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.message,
                    custom_id="DisparadorDM_EditarMensagem"
                ),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Iniciar Disparo",
                    style=disnake.ButtonStyle.green,
                    emoji=emoji.correct,
                    custom_id="DisparadorDM_IniciarDisparo",
                    disabled=not mensagem_configurada or tokens_validos == 0
                ),
                disnake.ui.Button(
                    label="Limpar DB",
                    style=disnake.ButtonStyle.red,
                    emoji=emoji.delete,
                    custom_id="DisparadorDM_LimparDB",
                    disabled=total_alvo == 0
                ),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="DisparadorDM_VoltarAutomacoes"
                ),
            )
        ]
        return embed, components

    @staticmethod
    def PainelTokensFalhos() -> list[disnake.ui.Container]:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        tokens_falhos = helpers.obter_tokens_falhos()

        if not tokens_falhos:
            return [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Disparador DM's > **Tokens Falhos**"),
                    disnake.ui.Separator(),
                    disnake.ui.TextDisplay("Nenhum token falhou durante o disparo."),
                    **container_kwargs,
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.back,
                        custom_id="DisparadorDM_VoltarPainel"
                    ),
                )
            ]

        # Criar texto com lista de tokens falhos
        lista_tokens = f"**Total de tokens falhos:** `{len(tokens_falhos)}`\n\n"
        
        for idx, tf in enumerate(tokens_falhos, 1):
            token_mask = tf.get("token_mascarado", "Token desconhecido")
            motivo = tf.get("motivo", "Sem motivo especificado")
            timestamp = tf.get("timestamp", 0)
            
            # Converter timestamp para data
            import datetime
            data = datetime.datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y %H:%M") if timestamp else "N/A"
            
            lista_tokens += f"**{idx}.** `{token_mask}`\n"
            lista_tokens += f"  ├ **Motivo:** {motivo}\n"
            lista_tokens += f"  └ **Data:** {data}\n\n"

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Disparador DM's > **Tokens Falhos**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(lista_tokens[:2000]),  # Limitar a 2000 caracteres
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    f"{emoji.warn} Estes tokens foram removidos automaticamente da configuração.\n"
                    f"Eles estão salvos aqui apenas para referência."
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Limpar Tokens Falhos",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.delete,
                        custom_id="DisparadorDM_LimparTokensFalhos"
                    )
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="DisparadorDM_VoltarPainel"
                ),
            )
        ]

    @staticmethod
    def PainelGerenciarBotoes() -> list[disnake.ui.Container]:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        editor_data = helpers.get_editor_data()
        botoes = editor_data.get("botoes", [])

        if not botoes:
            return [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Disparador DM's > **Gerenciar Botões**"),
                    disnake.ui.Separator(),
                    disnake.ui.TextDisplay("Nenhum botão foi adicionado ainda."),
                    disnake.ui.Separator(),
                    disnake.ui.ActionRow(
                        disnake.ui.Button(
                            label="Adicionar Botão",
                            style=disnake.ButtonStyle.green,
                            emoji=emoji.plus,
                            custom_id="DisparadorDM_AdicionarBotao"
                        )
                    ),
                    **container_kwargs,
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.back,
                        custom_id="DisparadorDM_VoltarEditor"
                    ),
                )
            ]

        options = []
        for btn in botoes:
            label = btn.get("label", "Sem label")[:100]
            btn_id = btn.get("id", "")
            btn_type = btn.get("button", {}).get("type", "disabled")
            tipo_desc = "Link" if btn_type == "url" else "Desativado"
            options.append(
                disnake.SelectOption(
                    label=label,
                    value=btn_id,
                    description=f"Tipo: {tipo_desc}",
                    emoji=emoji.route if btn_type == "url" else emoji.wrong
                )
            )

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Disparador DM's > **Gerenciar Botões**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(f"**Total de botões:** `{len(botoes)}`/`5`\n-# Selecione um botão para remover ou adicione um novo."),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Selecione um botão para remover",
                        custom_id="DisparadorDM_RemoverBotao",
                        options=options
                    )
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Adicionar Botão",
                        style=disnake.ButtonStyle.green,
                        emoji=emoji.plus,
                        custom_id="DisparadorDM_AdicionarBotao",
                        disabled=len(botoes) >= 5
                    ),
                    disnake.ui.Button(
                        label="Remover Todos",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.delete,
                        custom_id="DisparadorDM_RemoverTodosBotoes"
                    )
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="DisparadorDM_VoltarEditor"
                ),
            )
        ]

    @staticmethod
    def PainelEditor(bot: commands.Bot) -> list[disnake.ui.Container]:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        editor_data = helpers.get_editor_data()
        
        has_message = bool(editor_data.get("content"))
        embed_data = editor_data.get("embed", {})
        has_embed = any(embed_data.get(k) for k in ("title", "description", "footer"))
        has_image = bool(editor_data.get("externalImage") or embed_data.get("banner") or embed_data.get("thumbnail"))
        botoes = editor_data.get("botoes", [])
        has_buttons = isinstance(botoes, list) and len(botoes) > 0
        limite_botoes = isinstance(botoes, list) and len(botoes) >= 5

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Disparador DM's > **Editor de Mensagem**"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay("Configure a mensagem que será enviada aos usuários."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.delete,
                        custom_id="DisparadorDM_ApagarCampo:content",
                        disabled=not has_message
                    ),
                    disnake.ui.Button(
                        label="Definir Mensagem",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.message,
                        custom_id="DisparadorDM_DefinirMensagem"
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.delete,
                        custom_id="DisparadorDM_ApagarCampo:embed",
                        disabled=not has_embed
                    ),
                    disnake.ui.Button(
                        label="Definir Embed",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.embed,
                        custom_id="DisparadorDM_DefinirEmbed"
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.delete,
                        custom_id="DisparadorDM_ApagarImagensMulti",
                        disabled=not has_image
                    ),
                    disnake.ui.Button(
                        label="Definir Imagens",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.image,
                        custom_id="DisparadorDM_DefinirImagens"
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="",
                        style=disnake.ButtonStyle.red,
                        emoji=emoji.delete,
                        custom_id="DisparadorDM_ApagarCampo:botoes",
                        disabled=not has_buttons
                    ),
                    disnake.ui.Button(
                        label="Gerenciar Botões" if has_buttons else "Adicionar Botão",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.edit if has_buttons else emoji.plus,
                        custom_id="DisparadorDM_GerenciarBotoes",
                        disabled=limite_botoes
                    ),
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="DisparadorDM_VoltarPainel"
                ),
                disnake.ui.Button(
                    label="Visualizar",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.search,
                    custom_id="DisparadorDM_Visualizar",
                    disabled=not (has_message or has_embed or has_image or has_buttons)
                )
            )
        ]

    @staticmethod
    def validar_emoji(emoji_input: str, bot: commands.Bot) -> bool:
        """Valida se um emoji é válido."""
        if not emoji_input or emoji_input.strip() == "":
            return True
        emoji_input = emoji_input.strip()
        DISCORD_EMOJI_RE = re.compile(r"<a?:[a-zA-Z0-9_]{2,32}:\d{17,22}>")
        UNICODE_EMOJI_RE = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U0001F900-\U0001F9FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )
        if hasattr(emoji, emoji_input):
            value = getattr(emoji, emoji_input)
            if isinstance(value, str) and DISCORD_EMOJI_RE.fullmatch(value):
                try:
                    pe = disnake.PartialEmoji.from_str(value)
                    return bool(pe and pe.id)
                except Exception:
                    return False
            return True
        if DISCORD_EMOJI_RE.fullmatch(emoji_input):
            try:
                pe = disnake.PartialEmoji.from_str(emoji_input)
                return bool(pe and pe.id)
            except Exception:
                return False
        if UNICODE_EMOJI_RE.fullmatch(emoji_input):
            return True
        return False

    @staticmethod
    def processar_emoji(emoji_input: str):
        """Processa um emoji para uso em componentes."""
        if not emoji_input or emoji_input.strip() == "":
            return None
        emoji_input = emoji_input.strip()
        DISCORD_EMOJI_RE = re.compile(r"<a?:[a-zA-Z0-9_]{2,32}:\d{17,22}>")
        UNICODE_EMOJI_RE = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U0001F900-\U0001F9FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )
        
        # Handle shortnames from functions.emoji
        if hasattr(emoji, emoji_input):
            emoji_input = getattr(emoji, emoji_input)
        
        if DISCORD_EMOJI_RE.fullmatch(emoji_input):
            try:
                return disnake.PartialEmoji.from_str(emoji_input)
            except Exception:
                return None
        if UNICODE_EMOJI_RE.fullmatch(emoji_input):
            return emoji_input
        return None

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Valida se uma URL é válida."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            if not parsed.netloc or " " in parsed.netloc:
                return False
            if "." not in parsed.netloc:
                return False
            return True
        except Exception:
            return False

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        if not cid.startswith("DisparadorDM_"):
            return

        # Função auxiliar para fazer defer com tratamento de erro
        async def safe_defer():
            try:
                if not inter.response.is_done():
                    await inter.response.defer()
            except disnake.errors.NotFound:
                # Interação expirada ou já respondida, ignorar silenciosamente
                pass
            except Exception as e:
                print(f"Erro ao fazer defer da interação: {e}")

        if cid == "DisparadorDM_VoltarAutomacoes":
            from modules.automations.cog import AutomationModulesCog
            await safe_defer()
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                embed, components = AutomationModulesCog.PainelEmbed()
                await inter.edit_original_message(embed=embed, components=components)
            else:
                components = AutomationModulesCog.PainelComponents()
                await inter.edit_original_message(components=components)
            return

        if cid == "DisparadorDM_AtualizarPainel":
            await safe_defer()
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                embed, components = self.PainelEmbed()
                await inter.edit_original_message(embed=embed, components=components)
            else:
                components = self.Painel()
                await inter.edit_original_message(components=components)

            config = helpers.carregar_config()
            tokens = config.get("tokens", [])
            if tokens:
                await inter.followup.send(f"{emoji.time} Validando tokens configurados...", ephemeral=True)
                try:
                    total, validos, invalidos, _ = await self.bot.loop.run_in_executor(
                        None,
                        helpers.validar_tokens_e_salvar,
                        tokens,
                    )
                    mode = db.get_document("custom_mode").get("mode")
                    if mode == "embed":
                        embed, components = self.PainelEmbed()
                        await inter.edit_original_message(embed=embed, components=components)
                    else:
                        await inter.edit_original_message(components=self.Painel())
                    await inter.followup.send(
                        f"{emoji.correct} Validacao concluida! Total: `{total}`, validos: `{validos}`, invalidos: `{invalidos}`.",
                        ephemeral=True
                    )
                except Exception as exc:
                    print(f"[DisparadorDM] Erro ao validar tokens no atualizar: {exc}")
                    await inter.followup.send(f"{emoji.wrong} Nao consegui validar os tokens agora.", ephemeral=True)

        elif cid == "DisparadorDM_GerenciarTokens":
            config = helpers.carregar_config()
            tokens = config.get("tokens", [])
            await inter.response.send_modal(GerenciarTokensModal(tokens))

        elif cid == "DisparadorDM_EditarMensagem":
            await safe_defer()
            await inter.edit_original_message(components=self.PainelEditor(self.bot))

        elif cid == "DisparadorDM_VoltarPainel":
            await safe_defer()
            await inter.edit_original_message(components=self.Painel())

        elif cid == "DisparadorDM_DefinirMensagem":
            await inter.response.send_modal(DefinirMensagemModal())

        elif cid == "DisparadorDM_DefinirEmbed":
            await inter.response.send_modal(DefinirEmbedModal())

        elif cid == "DisparadorDM_DefinirImagens":
            await inter.response.send_modal(DefinirImagensModal())

        elif cid == "DisparadorDM_GerenciarBotoes":
            await safe_defer()
            await inter.edit_original_message(components=self.PainelGerenciarBotoes())

        elif cid == "DisparadorDM_VoltarEditor":
            await safe_defer()
            await inter.edit_original_message(components=self.PainelEditor(self.bot))

        elif cid == "DisparadorDM_AdicionarBotao":
            await inter.response.send_modal(DefinirBotoesModal())

        elif cid == "DisparadorDM_RemoverTodosBotoes":
            await safe_defer()
            helpers.clear_editor_field("botoes")
            await inter.edit_original_message(components=self.PainelGerenciarBotoes())
            await inter.followup.send(f"{emoji.correct} Todos os botões foram removidos!", ephemeral=True)

        elif cid.startswith("DisparadorDM_ApagarCampo:"):
            await safe_defer()
            field = cid.split(":", 1)[1]
            helpers.clear_editor_field(field)
            await inter.edit_original_message(components=self.PainelEditor(self.bot))

        elif cid == "DisparadorDM_ApagarImagensMulti":
            await safe_defer()
            editor_data = helpers.get_editor_data()
            editor_data["externalImage"] = None
            if "embed" in editor_data:
                editor_data["embed"]["banner"] = None
                editor_data["embed"]["thumbnail"] = None
            helpers.set_editor_data(editor_data)
            await inter.edit_original_message(components=self.PainelEditor(self.bot))

        elif cid == "DisparadorDM_Visualizar":
            await safe_defer()
            editor_data = helpers.get_editor_data()
            if not any(editor_data.get(k) for k in ["content", "embed", "externalImage", "botoes"]):
                await inter.followup.send("Não há nada para visualizar.", ephemeral=True)
                return
            
            data_to_build = editor_data.copy()
            # Remover container se existir (não é suportado)
            data_to_build.pop("container", None)
            
            if "botoes" in data_to_build and data_to_build["botoes"]:
                data_to_build["buttons"] = data_to_build.pop("botoes")
            else:
                data_to_build["buttons"] = []
            
            built = await self.bot.loop.run_in_executor(None, Builder.build_from_cfg, {"message": data_to_build})
            await self._send_built_message(inter, built, ephemeral=True)

        elif cid == "DisparadorDM_IniciarDisparo":
            # Verifica se já existe configuração
            temp_db = helpers.carregar_temp_db()
            if self.disparo_em_andamento:
                await inter.response.send_message(f"{emoji.warn} Já existe um disparo em andamento!", ephemeral=True)
                return
            
            if temp_db.get("usuarios_alvo"):
                # Já tem configuração, iniciar disparo
                await safe_defer()
                await inter.followup.send(f"{emoji.time} Iniciando disparo... Você receberá logs na DM!", ephemeral=True)
                self.task_disparo = asyncio.create_task(self._executar_disparo(inter))
            else:
                # Não tem configuração, abrir modal
                await inter.response.send_modal(ConfigurarDisparoModal())

        elif cid == "DisparadorDM_LimparDB":
            await safe_defer()
            helpers.limpar_temp_db()
            await inter.edit_original_message(components=self.Painel())
            await inter.followup.send(f"{emoji.correct} Base de dados limpa com sucesso!", ephemeral=True)

        elif cid == "DisparadorDM_VerTokensFalhos":
            await safe_defer()
            await inter.edit_original_message(components=self.PainelTokensFalhos())

        elif cid == "DisparadorDM_LimparTokensFalhos":
            await safe_defer()
            helpers.limpar_tokens_falhos()
            await inter.edit_original_message(components=self.PainelTokensFalhos())
            await inter.followup.send(f"{emoji.correct} Lista de tokens falhos limpa!", ephemeral=True)

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        if not cid.startswith("DisparadorDM_"):
            return

        # Função auxiliar para fazer defer com tratamento de erro
        async def safe_defer():
            try:
                if not inter.response.is_done():
                    await inter.response.defer()
            except disnake.errors.NotFound:
                # Interação expirada ou já respondida, ignorar silenciosamente
                pass
            except Exception as e:
                print(f"Erro ao fazer defer da interação: {e}")

        if cid == "DisparadorDM_RemoverBotao":
            await safe_defer()
            button_id = inter.values[0]
            
            editor_data = helpers.get_editor_data()
            botoes = editor_data.get("botoes", [])
            botoes = [b for b in botoes if b.get("id") != button_id]
            helpers.set_editor_field("botoes", botoes)
            
            await inter.edit_original_message(components=self.PainelGerenciarBotoes())
            await inter.followup.send(f"{emoji.correct} Botão removido!", ephemeral=True)

    @commands.Cog.listener("on_modal_submit")
    async def on_modal_submit(self, inter: disnake.ModalInteraction):
        cid = inter.custom_id
        if not cid.startswith("DisparadorDM_"):
            return

        if cid == "DisparadorDM_GerenciarTokensModal":
            tokens_text = inter.text_values.get("tokens", "").strip()
            tokens = helpers.normalizar_tokens([t.strip() for t in tokens_text.split("\n") if t.strip()])
            
            config = helpers.carregar_config()
            config = helpers.preparar_status_pendente(tokens, config)
            helpers.salvar_config(config)
            
            await inter.response.edit_message(components=self.Painel())
            await inter.followup.send(
                f"{emoji.time} Tokens salvos. Validando `{len(tokens)}` token(s) em segundo plano...",
                ephemeral=True
            )

            try:
                total, validos, invalidos, _ = await self.bot.loop.run_in_executor(
                    None,
                    helpers.validar_tokens_e_salvar,
                    tokens,
                )
                await inter.edit_original_message(components=self.Painel())
                await inter.followup.send(
                    f"{emoji.correct} Validacao concluida! Total: `{total}`, validos: `{validos}`, invalidos: `{invalidos}`.",
                    ephemeral=True
                )
            except Exception as exc:
                print(f"[DisparadorDM] Erro ao validar tokens: {exc}")
                await inter.followup.send(
                    f"{emoji.wrong} Tokens salvos, mas nao consegui validar agora. Tente usar Atualizar em alguns instantes.",
                    ephemeral=True
                )

        elif cid == "DisparadorDM_DefinirMensagemModal":
            helpers.set_editor_field("content", inter.text_values["message"])
            await inter.response.edit_message(components=self.PainelEditor(self.bot))

        elif cid == "DisparadorDM_DefinirEmbedModal":
            def validar_hex(codigo: str) -> Optional[str]:
                if not codigo:
                    return None
                codigo = codigo.strip().lstrip("#")
                if len(codigo) not in (3, 6):
                    return None
                try:
                    int(codigo, 16)
                except ValueError:
                    return None
                return f"#{codigo.upper()}"
            
            embed_data = {
                "title": inter.text_values.get("embed_title"),
                "description": inter.text_values.get("embed_description"),
                "color": validar_hex(inter.text_values.get("embed_color")),
                "footer": inter.text_values.get("embed_footer"),
            }
            helpers.set_editor_field("embed", embed_data)
            await inter.response.edit_message(components=self.PainelEditor(self.bot))

        elif cid == "DisparadorDM_DefinirImagensModal":
            editor_data = helpers.get_editor_data()
            editor_data["externalImage"] = inter.text_values.get("externalImage") or None
            if "banner" in inter.text_values:
                if "embed" not in editor_data:
                    editor_data["embed"] = {}
                editor_data["embed"]["banner"] = inter.text_values.get("banner") or None
            if "thumbnail" in inter.text_values:
                if "embed" not in editor_data:
                    editor_data["embed"] = {}
                editor_data["embed"]["thumbnail"] = inter.text_values.get("thumbnail") or None
            helpers.set_editor_data(editor_data)
            await inter.response.edit_message(components=self.PainelEditor(self.bot))

        elif cid == "DisparadorDM_DefinirBotoesModal":
            label = inter.text_values.get("button_label", "").strip()
            url = inter.text_values.get("button_url", "").strip()
            emoji_input = inter.text_values.get("button_emoji", "").strip()
            
            # Validar emoji
            if emoji_input and not self.validar_emoji(emoji_input, self.bot):
                await inter.response.send_message(f"{emoji.warn} Emoji inválido.", ephemeral=True)
                return
            
            # Validar URL se fornecida
            if url and not self._is_valid_url(url):
                await inter.response.send_message(f"{emoji.wrong} URL inválida. Use http(s)://", ephemeral=True)
                return
            
            # Criar botão
            import uuid
            editor_data = helpers.get_editor_data()
            botoes = editor_data.get("botoes", [])
            
            if len(botoes) >= 5:
                await inter.response.send_message("Limite de 5 botões atingido.", ephemeral=True)
                return
            
            button_id = str(uuid.uuid4())
            button_data = {
                "id": button_id,
                "label": label,
                "button": {
                    "type": "url" if url else "disabled",
                    "emoji": emoji_input or None,
                    "url": url or None,
                    "style": "gray" if not url else "url",
                    "disabled": not url,
                }
            }
            
            botoes.append(button_data)
            helpers.set_editor_field("botoes", botoes)
            await inter.response.edit_message(components=self.PainelGerenciarBotoes())
            await inter.followup.send(f"{emoji.correct} Botão adicionado!", ephemeral=True)

        elif cid == "DisparadorDM_ConfigurarDisparoModal":
            server_id = inter.text_values.get("server_id", "").strip()
            role_id = inter.text_values.get("role_id", "").strip()
            exclude_roles = [r.strip() for r in inter.text_values.get("exclude_roles", "").split(",") if r.strip()]
            exclude_users = [u.strip() for u in inter.text_values.get("exclude_users", "").split(",") if u.strip()]
            
            # Mapear usuários alvo
            usuarios_alvo = await helpers.mapear_usuarios_alvo(
                self.bot,
                server_id if server_id else None,
                role_id if role_id else None,
                exclude_roles,
                exclude_users
            )
            
            if not usuarios_alvo:
                await inter.response.send_message(
                    f"{emoji.wrong} Nenhum usuário encontrado com os critérios especificados.",
                    ephemeral=True
                )
                return
            
            # Salvar no temp DB
            helpers.salvar_usuarios_alvo(usuarios_alvo)
            
            # Atualizar painel e enviar mensagem de sucesso
            await inter.response.edit_message(components=self.Painel())
            await inter.followup.send(
                f"{emoji.correct} Disparo configurado! `{len(usuarios_alvo)}` usuários serão notificados.\n"
                f"Clique em **Iniciar Disparo** novamente para começar o envio.",
                ephemeral=True
            )

    async def _executar_disparo(self, inter: disnake.MessageInteraction):
        """Executa o disparo de mensagens."""
        self.disparo_em_andamento = True
        
        try:
            config = helpers.carregar_config()
            tokens = [t for t in config.get("tokens", []) if t.strip()]
            
            # Validar tokens antes de começar
            tokens_validos = []
            for token in tokens:
                if helpers.validar_token(token):
                    tokens_validos.append(token)
                else:
                    # Token inválido, remover da config e adicionar aos falhos
                    helpers.adicionar_token_falho(token, "Token inválido ou expirado")
                    helpers.remover_token_do_config(token)
            
            if not tokens_validos:
                await inter.followup.send(f"{emoji.wrong} Nenhum token válido disponível.", ephemeral=True)
                self.disparo_em_andamento = False
                return
            
            editor_data = helpers.get_editor_data()
            data_to_build = editor_data.copy()
            # Remover container se existir (não é suportado no Disparador DM's)
            data_to_build.pop("container", None)
            
            if "botoes" in data_to_build:
                data_to_build["buttons"] = data_to_build.pop("botoes")
            else:
                data_to_build["buttons"] = []
            
            built = await self.bot.loop.run_in_executor(None, Builder.build_from_cfg, {"message": data_to_build})
            
            pendentes = helpers.get_usuarios_pendentes()
            
            if not pendentes:
                await inter.followup.send(f"{emoji.correct} Todos os usuários já receberam a mensagem!", ephemeral=True)
                self.disparo_em_andamento = False
                return
            
            enviados = 0
            erros = 0
            token_index = 0
            total_usuarios = len(pendentes)
            tokens_com_erro = {}  # Rastrear erros por token
            
            # Enviar mensagem de início
            status_msg = await inter.followup.send(
                f"{emoji.time} Disparo iniciado! `0/{total_usuarios}` enviados...\n"
                f"Tokens ativos: `{len(tokens_validos)}`",
                ephemeral=True
            )
            
            # Preparar DM do usuário para logs
            log_message = None
            dm_channel = None
            dm_user = inter.user
            
            try:
                # Tentar criar o canal DM primeiro
                dm_channel = await dm_user.create_dm()
                
                # Se conseguiu criar o canal DM, enviar mensagem inicial
                if dm_channel:
                    try:
                        log_message = await dm_channel.send(
                            f"**{emoji.correct} Iniciando disparo de DMs**\n"
                            f"> Total de usuários: `{total_usuarios}`\n"
                            f"> Tokens ativos: `{len(tokens_validos)}`"
                        )
                    except Exception as e:
                        print(f"Erro ao enviar mensagem inicial no canal DM: {e}")
                        import traceback
                        traceback.print_exc()
                        # Tentar fallback: enviar diretamente ao usuário
                        try:
                            log_message = await dm_user.send(
                                f"**{emoji.correct} Iniciando disparo de DMs**\n"
                                f"> Total de usuários: `{total_usuarios}`\n"
                                f"> Tokens ativos: `{len(tokens_validos)}`"
                            )
                        except Exception as e2:
                            print(f"Erro no fallback de envio direto: {e2}")
                            dm_channel = None
            except disnake.Forbidden:
                # DMs fechadas ou bloqueadas
                await inter.followup.send(
                    "Não foi possível enviar os logs na sua DM. Verifique se você tem as DMs abertas.",
                    ephemeral=True
                )
                dm_channel = None
            except Exception as e:
                print(f"Erro ao preparar logs na DM: {e}")
                import traceback
                traceback.print_exc()
                # Tentar fallback: enviar diretamente ao usuário
                try:
                    log_message = await dm_user.send(
                        f"**{emoji.correct} Iniciando disparo de DMs**\n"
                        f"> Total de usuários: `{total_usuarios}`\n"
                        f"> Tokens ativos: `{len(tokens_validos)}`"
                    )
                    # Se conseguiu enviar diretamente, usar o usuário como canal
                    dm_channel = dm_user
                except Exception as e2:
                    print(f"Erro no fallback final: {e2}")
                    dm_channel = None

            log_buffer = []
            
            for idx, user_id in enumerate(pendentes, 1):
                if not tokens_validos:  # Se todos os tokens falharam
                    await inter.followup.send(
                        f"{emoji.wrong} Todos os tokens falharam! Disparo interrompido.\n"
                        f"Enviados: `{enviados}`/{total_usuarios}",
                        ephemeral=True
                    )
                    break
                
                # Pegar o token atual
                token_atual = tokens_validos[token_index % len(tokens_validos)]
                
                try:
                    # Buscar informações do usuário
                    user = await self.bot.fetch_user(user_id)
                    if not user:
                        erros += 1
                        continue
                    
                    # Enviar DM usando o token configurado via HTTP
                    success, status_code = await self._send_dm_via_token(token_atual, user_id, built)
                    
                    if success:
                        helpers.adicionar_usuario_enviado(user_id)
                        enviados += 1
                        
                        now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        log_buffer.append(f"{now} - DM enviada para **{user.name}** (ID: `{user_id}`)")

                        if (dm_channel or dm_user) and log_message:
                            try:
                                new_content = "\n".join(log_buffer)
                                current_content = log_message.content

                                if len(current_content) + len(new_content) + 2 > 2000:
                                    await log_message.edit(content=current_content + "\n`[Log continuado em nova mensagem]`")
                                    # Usar dm_channel se disponível, senão usar dm_user
                                    target = dm_channel if dm_channel else dm_user
                                    log_message = await target.send(new_content)
                                    log_buffer = []
                                else:
                                    if len(log_buffer) % 5 == 0 or idx == total_usuarios:
                                        await log_message.edit(content=f"{current_content}\n{new_content}")
                                        # Não limpar o buffer aqui, pois ele é usado para construir a mensagem

                            except Exception as e:
                                print(f"Erro ao atualizar log na DM: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        # Resetar contador de erros para este token
                        tokens_com_erro[token_atual] = 0
                        
                        # Atualizar status a cada 10 envios
                        if enviados % 10 == 0:
                            try:
                                await status_msg.edit(
                                    content=(
                                        f"{emoji.time} Disparo em andamento... `{enviados}/{total_usuarios}` enviados...\n"
                                        f"Tokens ativos: `{len(tokens_validos)}`"
                                    )
                                )
                            except:
                                pass
                        
                        # Rotacionar token (usar próximo token)
                        token_index += 1
                        
                        # Delay para evitar rate limit (menor delay com múltiplos tokens)
                        delay = 1 if len(tokens_validos) > 1 else 2
                        await asyncio.sleep(delay)
                    else:
                        # Falha no envio, simular erro baseado no status
                        if status_code == 403:
                            # Criar um mock response para o Forbidden
                            class MockResponse:
                                def __init__(self, status, reason):
                                    self.status = status
                                    self.reason = reason
                            raise disnake.Forbidden(MockResponse(403, "Cannot send messages to this user"), "Failed to send DM")
                        elif status_code == 429:
                            # Rate limit
                            class MockResponse:
                                def __init__(self, status, reason):
                                    self.status = status
                                    self.reason = reason
                            raise disnake.HTTPException(MockResponse(429, "Rate limited"), "Rate limited")
                        else:
                            raise Exception(f"Failed with status {status_code}")

                except disnake.Forbidden:
                    user = await self.bot.get_or_fetch_user(user_id)
                    user_name = user.name if user else "Nome Desconhecido"
                    error_message = f"`✗` Erro ao enviar para **{user_name}** (`{user_id}`): O usuário não pode receber DMs (provavelmente DMs desativadas ou o bot foi bloqueado)."
                    log_buffer.append(error_message)
                    print(error_message)

                    tokens_com_erro[token_atual] = tokens_com_erro.get(token_atual, 0) + 1

                    if tokens_com_erro[token_atual] >= 3:
                        helpers.adicionar_token_falho(token_atual, "Múltiplos erros Forbidden - Possível spam detectado")
                        helpers.remover_token_do_config(token_atual)
                        if token_atual in tokens_validos:
                            tokens_validos.remove(token_atual)

                        await inter.followup.send(
                            f"{emoji.warn} Token removido por múltiplos erros! Tokens restantes: `{len(tokens_validos)}`",
                            ephemeral=True
                        )

                        if tokens_validos:
                            token_index = token_index % len(tokens_validos)

                    helpers.adicionar_usuario_falho(user_id)
                    erros += 1
                    continue
                    
                except disnake.HTTPException as e:
                    # Rate limit ou outro erro HTTP
                    print(f"HTTPException ao enviar DM para {user_id}: {e}")
                    
                    if e.status == 429:  # Rate limit
                        # Incrementar contador de erros
                        tokens_com_erro[token_atual] = tokens_com_erro.get(token_atual, 0) + 1
                        
                        # Se rate limit persistente (5 vezes), remover token
                        if tokens_com_erro[token_atual] >= 5:
                            helpers.adicionar_token_falho(token_atual, "Rate limit excessivo")
                            helpers.remover_token_do_config(token_atual)
                            tokens_validos.remove(token_atual)
                            
                            if tokens_validos:
                                token_index = token_index % len(tokens_validos)
                        else:
                            # Esperar um pouco mais e rotacionar
                            await asyncio.sleep(5)
                            token_index += 1
                    
                    helpers.adicionar_usuario_falho(user_id)
                    erros += 1
                    continue
                    
                except Exception as e:
                    print(f"Erro ao enviar DM para {user_id}: {e}")
                    helpers.adicionar_usuario_falho(user_id)
                    erros += 1
                    continue
            
            # Enviar logs restantes no buffer
            if (dm_channel or dm_user) and log_message and log_buffer:
                try:
                    current_content = log_message.content
                    final_log_content = f"{current_content}\n" + "\n".join(log_buffer)
                    await log_message.edit(content=final_log_content[:2000])
                except Exception as e:
                    print(f"Erro ao enviar log final na DM: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Obter tokens falhos para relatório
            tokens_falhos = helpers.obter_tokens_falhos()
            
            # Atualizar mensagem final
            mensagem_final = (
                f"{emoji.correct} Disparo concluído!\n"
                f"Enviados: `{enviados}`\n"
                f"Erros: `{erros}`\n"
                f"Tokens finais: `{len(tokens_validos)}`"
            )
            
            if tokens_falhos:
                mensagem_final += f"\n\n{emoji.warn} **Tokens que falharam:** `{len(tokens_falhos)}`"
                for tf in tokens_falhos[-3:]:  # Mostrar últimos 3
                    mensagem_final += f"\n• `{tf.get('token_mascarado')}` - {tf.get('motivo')}"
                if len(tokens_falhos) > 3:
                    mensagem_final += f"\n_... e mais {len(tokens_falhos) - 3} token(s)_"
            
            try:
                await status_msg.edit(content=mensagem_final)
            except:
                await inter.followup.send(mensagem_final, ephemeral=True)
            
            # Enviar relatório final na DM
            if dm_channel or dm_user:
                try:
                    target = dm_channel if dm_channel else dm_user
                    await target.send(
                        f"\n**{emoji.correct} Disparo Concluído!**\n"
                        f"> Enviados: `{enviados}`\n"
                        f"> Erros: `{erros}`\n"
                        f"> Tokens finais: `{len(tokens_validos)}`"
                    )
                except Exception as e:
                    print(f"Erro ao enviar relatório final na DM: {e}")
                    import traceback
                    traceback.print_exc()
            
        except Exception as e:
            print(f"Erro no disparo: {e}")
            await inter.followup.send(f"{emoji.wrong} Erro durante o disparo: {str(e)}", ephemeral=True)
        
        finally:
            self.disparo_em_andamento = False

    async def _send_dm_via_token(self, token: str, user_id: int, built_message: dict) -> tuple[bool, int]:
        """Envia uma DM usando o token configurado via HTTP."""
        try:
            import requests
            
            # Criar o canal de DM primeiro
            create_dm_url = "https://discord.com/api/v10/users/@me/channels"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json"
            }
            dm_payload = {"recipient_id": str(user_id)}
            
            response = await self.bot.loop.run_in_executor(
                None,
                lambda: requests.post(create_dm_url, headers=headers, json=dm_payload, timeout=10)
            )
            
            if response.status_code not in [200, 201]:
                return False, response.status_code
            
            dm_channel = response.json()
            channel_id = dm_channel.get("id")
            
            if not channel_id:
                return False, 0
            
            # Preparar payload da mensagem
            message_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            message_payload = {}
            
            # Função auxiliar para serializar botão
            def serialize_button(button):
                """Serializa um botão do Disnake para dict."""
                if not isinstance(button, disnake.ui.Button):
                    return None
                
                btn_dict = {
                    "type": 2  # BUTTON
                }
                
                if button.label:
                    btn_dict["label"] = button.label
                
                if button.style:
                    btn_dict["style"] = button.style.value if hasattr(button.style, 'value') else int(button.style)
                
                if button.custom_id:
                    btn_dict["custom_id"] = button.custom_id
                
                if button.url:
                    btn_dict["url"] = button.url
                
                if button.disabled:
                    btn_dict["disabled"] = True
                
                if button.emoji:
                    if isinstance(button.emoji, str):
                        btn_dict["emoji"] = {"name": button.emoji}
                    elif hasattr(button.emoji, 'id') and button.emoji.id:
                        btn_dict["emoji"] = {
                            "id": str(button.emoji.id),
                            "name": button.emoji.name,
                            "animated": getattr(button.emoji, 'animated', False)
                        }
                    elif hasattr(button.emoji, 'name'):
                        btn_dict["emoji"] = {"name": button.emoji.name}
                
                return btn_dict
            
            # Função auxiliar para serializar ActionRow manualmente
            def serialize_action_row(action_row):
                """Serializa um ActionRow manualmente (não tem to_dict)."""
                if not isinstance(action_row, disnake.ui.ActionRow):
                    return None
                
                row_dict = {
                    "type": 1,  # ACTION_ROW
                    "components": []
                }
                
                # Serializar cada componente dentro do ActionRow
                if hasattr(action_row, 'children') and action_row.children:
                    for child in action_row.children:
                        if isinstance(child, disnake.ui.Button):
                            btn_dict = serialize_button(child)
                            if btn_dict:
                                row_dict["components"].append(btn_dict)
                        elif hasattr(child, 'to_dict'):
                            try:
                                child_dict = child.to_dict()
                                if isinstance(child_dict, dict):
                                    if 'type' not in child_dict:
                                        child_dict['type'] = 2  # Assumir botão se não tiver type
                                    row_dict["components"].append(child_dict)
                            except Exception as e:
                                print(f"Erro ao serializar child de ActionRow: {e}")
                
                return row_dict if row_dict["components"] else None
            
            # Função de serialização melhorada usando a serialização nativa do Disnake
            def serialize_component(comp):
                """Serializa componentes recursivamente para JSON usando serialização nativa do Disnake."""
                if comp is None:
                    return None
                
                # ActionRow precisa ser serializado manualmente (não tem to_dict)
                if isinstance(comp, disnake.ui.ActionRow):
                    return serialize_action_row(comp)
                
                # Se é um objeto Disnake, usar a serialização nativa
                if hasattr(comp, 'to_dict'):
                    try:
                        result = comp.to_dict()
                        # Validar que o resultado tem o formato correto
                        if isinstance(result, dict):
                            # Garantir que componentes tenham o campo type obrigatório
                            if 'type' not in result:
                                # Tentar inferir o tipo baseado na classe ou estrutura
                                if isinstance(comp, disnake.ui.Container):
                                    result['type'] = 1  # ACTION_ROW para Container
                                elif isinstance(comp, disnake.ui.TextDisplay):
                                    result['type'] = 4  # TEXT_INPUT (mas TextDisplay usa type diferente)
                                elif isinstance(comp, disnake.ui.Button):
                                    result['type'] = 2  # BUTTON
                                elif isinstance(comp, disnake.ui.StringSelect):
                                    result['type'] = 3  # STRING_SELECT
                                elif isinstance(comp, disnake.ui.ActionRow):
                                    result['type'] = 1  # ACTION_ROW
                                elif 'components' in result:
                                    # Se tem components, provavelmente é um ACTION_ROW ou Container
                                    result['type'] = 1
                                elif 'style' in result or 'label' in result:
                                    # Se tem style ou label, provavelmente é um botão
                                    result['type'] = 2
                            return result
                        return result
                    except Exception as e:
                        print(f"Erro ao chamar to_dict em {type(comp)}: {e}")
                        import traceback
                        traceback.print_exc()
                        return None
                elif isinstance(comp, list):
                    serialized_list = []
                    for c in comp:
                        if c is not None:
                            serialized = serialize_component(c)
                            if serialized is not None:
                                serialized_list.append(serialized)
                    return serialized_list if serialized_list else None
                elif isinstance(comp, dict):
                    # Se já é um dict, garantir que tenha type se necessário
                    result = {}
                    for k, v in comp.items():
                        if v is not None:
                            serialized_v = serialize_component(v)
                            if serialized_v is not None:
                                result[k] = serialized_v
                    # Se parece ser um componente mas não tem type, adicionar
                    if result and 'type' not in result:
                        if 'components' in result:
                            result['type'] = 1  # ACTION_ROW ou Container
                        elif 'style' in result or 'label' in result:
                            result['type'] = 2  # BUTTON
                        elif 'options' in result:
                            result['type'] = 3  # STRING_SELECT
                    return result if result else None
                elif isinstance(comp, (str, int, float, bool)):
                    return comp
                return None
            
            # Preparar dados da mensagem seguindo a mesma lógica do preview
            payload_data = {}
            files_data = []
            
            # Verificar modo (v2 ou embed)
            if built_message.get("mode") == "v2":
                # Modo v2: components e flags
                components = built_message.get("components")
                if components:
                    # Serializar componentes do modo v2
                    serialized_components = []
                    for comp in components:
                        try:
                            # ActionRow precisa ser serializado manualmente
                            if isinstance(comp, disnake.ui.ActionRow):
                                comp_dict = serialize_action_row(comp)
                                if comp_dict:
                                    serialized_components.append(comp_dict)
                            elif hasattr(comp, 'to_dict'):
                                comp_dict = comp.to_dict()
                                if comp_dict:
                                    serialized_components.append(comp_dict)
                            else:
                                # Tentar serializar usando função auxiliar
                                serialized = serialize_component(comp)
                                if serialized:
                                    serialized_components.append(serialized)
                        except Exception as e:
                            print(f"Erro ao serializar componente {type(comp)}: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    if serialized_components:
                        payload_data["components"] = serialized_components
                
                # Flags do modo v2
                flags = built_message.get("flags")
                if flags and hasattr(flags, 'value'):
                    payload_data["flags"] = flags.value
            else:
                # Modo embed: content, embed, components, files
                if built_message.get("content") is not None:
                    payload_data["content"] = built_message["content"]
                
                if built_message.get("embed") is not None:
                    embed_data = built_message["embed"]
                    if isinstance(embed_data, disnake.Embed):
                        payload_data["embeds"] = [embed_data.to_dict()]
                    elif isinstance(embed_data, dict):
                        payload_data["embeds"] = [embed_data]
                
                if built_message.get("components"):
                    components = built_message["components"]
                    serialized_components = []
                    for comp in components:
                        try:
                            # ActionRow precisa ser serializado manualmente
                            if isinstance(comp, disnake.ui.ActionRow):
                                comp_dict = serialize_action_row(comp)
                                if comp_dict:
                                    serialized_components.append(comp_dict)
                            elif hasattr(comp, 'to_dict'):
                                comp_dict = comp.to_dict()
                                if comp_dict:
                                    serialized_components.append(comp_dict)
                            else:
                                serialized = serialize_component(comp)
                                if serialized:
                                    serialized_components.append(serialized)
                        except Exception as e:
                            print(f"Erro ao serializar componente {type(comp)}: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    if serialized_components:
                        payload_data["components"] = serialized_components
                
                # Arquivos (imagens externas)
                if built_message.get("files"):
                    # Função auxiliar para determinar content type pela extensão
                    def get_content_type(filename: str) -> str:
                        """Determina o content type baseado na extensão do arquivo."""
                        if not filename:
                            return "application/octet-stream"
                        
                        ext = filename.lower().split('.')[-1] if '.' in filename else ''
                        content_types = {
                            'jpg': 'image/jpeg',
                            'jpeg': 'image/jpeg',
                            'png': 'image/png',
                            'gif': 'image/gif',
                            'webp': 'image/webp',
                            'txt': 'text/plain',
                            'json': 'application/json',
                            'pdf': 'application/pdf',
                        }
                        return content_types.get(ext, 'application/octet-stream')
                    
                    for file_obj in built_message["files"]:
                        if isinstance(file_obj, disnake.File):
                            # Ler o arquivo em memória através do atributo fp
                            try:
                                fp = file_obj.fp
                                if hasattr(fp, 'seek'):
                                    fp.seek(0)
                                    file_data = fp.read()
                                elif hasattr(fp, 'getvalue'):
                                    # Se for BytesIO, usar getvalue()
                                    file_data = fp.getvalue()
                                elif hasattr(fp, 'read'):
                                    file_data = fp.read()
                                else:
                                    # Tentar ler diretamente se for bytes
                                    file_data = fp if isinstance(fp, bytes) else None
                                
                                if file_data:
                                    content_type = get_content_type(file_obj.filename)
                                    files_data.append(
                                        ("file", (file_obj.filename, file_data, content_type))
                                    )
                            except Exception as e:
                                print(f"Erro ao ler arquivo {file_obj.filename}: {e}")
                                continue
            
            # Validar se há conteúdo para enviar
            if not payload_data and not files_data:
                print("Warning: Nenhum conteúdo para enviar")
                return False, 0
            
            # Preparar headers para envio
            send_headers = {"Authorization": f"Bot {token}"}
            
            # Se há arquivos, usar multipart/form-data
            if files_data:
                # Criar payload multipart
                import json
                form_data = {}
                
                # Adicionar payload JSON como campo 'payload_json'
                form_data["payload_json"] = (None, json.dumps(payload_data), "application/json")
                
                # Adicionar arquivos
                for file_tuple in files_data:
                    form_data[file_tuple[0]] = file_tuple[1]
                
                # Enviar com multipart/form-data
                response = await self.bot.loop.run_in_executor(
                    None,
                    lambda: requests.post(message_url, headers=send_headers, files=form_data, timeout=15)
                )
            else:
                # Enviar como JSON normal
                send_headers["Content-Type"] = "application/json"
                response = await self.bot.loop.run_in_executor(
                    None,
                    lambda: requests.post(message_url, headers=send_headers, json=payload_data, timeout=10)
                )
            
            if response.status_code not in [200, 201]:
                try:
                    error_text = response.text[:200] if hasattr(response, 'text') else str(response.status_code)
                    print(f"Erro HTTP ao enviar: {response.status_code} - {error_text}")
                except:
                    print(f"Erro HTTP ao enviar: {response.status_code}")
            
            return response.status_code in [200, 201], response.status_code
            
        except Exception as e:
            print(f"Erro ao enviar DM via token: {e}")
            import traceback
            traceback.print_exc()
            return False, 0

    @staticmethod
    async def _send_built_message(target, built_message: dict, ephemeral: bool = False):
        """Envia uma mensagem construída pelo builder."""
        kwargs = {"allowed_mentions": disnake.AllowedMentions.none()}
        if ephemeral:
            kwargs["ephemeral"] = True

        components = built_message.get("components")
        has_components = bool(components and (isinstance(components, list) and len(components) > 0))
        is_empty = not any([
            built_message.get("content"),
            built_message.get("embed"),
            has_components,
            built_message.get("files")
        ])
        if is_empty:
            if isinstance(target, disnake.Interaction):
                await target.followup.send("A mensagem está vazia.", ephemeral=True)
            return None

        if built_message.get("mode") == "v2":
            kwargs["components"] = components
            kwargs["flags"] = built_message.get("flags")
        else:
            if built_message.get("content"):
                kwargs["content"] = built_message["content"]
            if built_message.get("embed"):
                embed_data = built_message["embed"]
                if isinstance(embed_data, disnake.Embed):
                    kwargs["embed"] = embed_data
                else:
                    kwargs["embed"] = disnake.Embed.from_dict(embed_data)
            if built_message.get("components"):
                kwargs["components"] = built_message["components"]
            if built_message.get("files"):
                kwargs["files"] = built_message["files"]
        
        if isinstance(target, disnake.Interaction):
            return await target.followup.send(**kwargs)
        elif isinstance(target, (disnake.TextChannel, disnake.DMChannel, disnake.User, disnake.Member)):
            return await target.send(**kwargs)
        return None


def setup(bot: commands.Bot):
    bot.add_cog(DisparadorDMCog(bot))

