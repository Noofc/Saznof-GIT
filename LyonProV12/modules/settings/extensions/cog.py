import disnake
from disnake.ext import commands, tasks
import aiohttp
from aiohttp import web
import asyncio
import json
import io

from functions.emoji import emoji
from functions.database import database as db
from functions.message import message, embed_message
from functions.systemgen_manager import LyonGenManager
from . import subscription_manager as subs


class ExtensionsPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_url = "https://loopgen.squareweb.app"
        self.bot_secret = "Loop-gen-bot-secret"
        self.systemgen = LyonGenManager()
        self.restock_tasks = {}  # Store active restock tasks
        self.payment_cooldowns = {}  # Store payment cooldowns
        self._systemgen_site_runner = None

    def cog_unload(self):
        if self._systemgen_site_runner:
            self.bot.loop.create_task(self._systemgen_site_runner.cleanup())

    @commands.Cog.listener()
    async def on_ready(self):
        await self._ensure_systemgen_site()

    async def _ensure_systemgen_site(self):
        if self._systemgen_site_runner:
            return

        data = self.systemgen.load()
        settings = data.get("settings", {})
        if not settings.get("site_autostart", True):
            return

        host = str(settings.get("site_host") or "127.0.0.1")
        try:
            port = int(settings.get("site_port", 8765) or 8765)
        except Exception:
            port = 8765

        runner = None
        try:
            from systemgen_site.server import create_app

            runner = web.AppRunner(create_app())
            await runner.setup()
            site = web.TCPSite(runner, host=host, port=port)
            await site.start()
            self._systemgen_site_runner = runner
            self.systemgen.update_settings(site_url=f"http://{host}:{port}")
            print(f"[LyonGen] Site local iniciado em http://{host}:{port}")
        except OSError as exc:
            if runner:
                await runner.cleanup()
            print(f"[LyonGen] Nao foi possivel iniciar o site local em {host}:{port}: {exc}")
        except Exception as exc:
            if runner:
                await runner.cleanup()
            print(f"[LyonGen] Erro ao iniciar site local: {exc}")

    def _get_extensions_config(self) -> dict:
        """Obtém configuração de extensões"""
        return db.obter("configs/config_extensions.json")

    def _get_Lyongen_status(self) -> dict:
        """Obtém status da extensão Lyon Gen"""
        return self.systemgen.load()

    def _get_livestock_config(self) -> dict:
        """Obtém configuração de Live Stock"""
        data = self.systemgen.load()
        return data.get("livestock", {})

    async def _safe_defer(self, inter: disnake.Interaction, *, ephemeral: bool = False, with_message: bool | None = None) -> bool:
        if inter.response.is_done():
            return True
        try:
            kwargs = {"ephemeral": ephemeral}
            if with_message is not None:
                kwargs["with_message"] = with_message
            await inter.response.defer(**kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[Extensions] Interacao expirada/defer ignorado: {exc}")
            return False

    async def _safe_response_send(self, inter: disnake.Interaction, content: str | None = None, **kwargs) -> bool:
        try:
            if inter.response.is_done():
                await inter.followup.send(content, **kwargs)
            else:
                await inter.response.send_message(content, **kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[Extensions] Falha ao responder interacao: {exc}")
            return False

    async def _safe_followup(self, inter: disnake.Interaction, content: str | None = None, **kwargs) -> bool:
        try:
            await inter.followup.send(content, **kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            print(f"[Extensions] Falha ao enviar followup: {exc}")
            return False

    async def _safe_response_edit(self, inter: disnake.Interaction, **kwargs) -> bool:
        try:
            if inter.response.is_done():
                await inter.edit_original_message(**kwargs)
            else:
                await inter.response.edit_message(**kwargs)
            return True
        except (disnake.NotFound, disnake.HTTPException, disnake.InteractionTimedOut, disnake.InteractionResponded) as exc:
            try:
                message_obj = getattr(inter, "message", None)
                if message_obj:
                    await message_obj.edit(**kwargs)
                    return True
            except Exception:
                pass
            print(f"[Extensions] Falha ao editar interacao: {exc}")
            return False

    async def display_extensions_panel(self, inter: disnake.MessageInteraction):
        """Exibe o painel principal de extensões"""
        mode = db.get_document("custom_mode").get("mode")
        extensions_config = self._get_extensions_config()

        if mode == "embed":
            await embed_message.wait(inter, send=False)
            embed, components = self._build_embed_panel(inter, extensions_config)
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            await message.wait(inter, send=False)
            components = self._build_components_panel(inter, extensions_config)
            await inter.edit_original_message(components=components)

    def _build_components_panel(self, inter: disnake.MessageInteraction, extensions_config: dict) -> list:
        """Constrói painel em modo components - Visual moderno"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        # Status das extensões
        boost_enabled = subs.is_extension_active("boost")
        Lyongen_data = self._get_Lyongen_status()
        Lyongen_enabled = Lyongen_data.get("enabled", True)
        Lyongen_integrated = (
            Lyongen_data.get("integrated_user_id") is not None
            or bool(Lyongen_data.get("integrated_user"))
        )

        # Construir status do Lyon Gen
        if Lyongen_enabled and Lyongen_integrated:
            Lyongen_status = f"{emoji.on} Ativo"
            Lyongen_user = Lyongen_data.get("integrated_user", "N/A")
        elif Lyongen_enabled:
            Lyongen_status = f"{emoji.warn} Não integrado"
            Lyongen_user = None
        else:
            Lyongen_status = f"{emoji.off} Desativado"
            Lyongen_user = None

        # Construir status do Boost
        boost_status = f"{emoji.on} Ativo" if boost_enabled else f"{emoji.off} Desativado"

        # Opções para o select menu de extensões
        extension_options = [
            disnake.SelectOption(
                label="Lyon Gen",
                value="Lyongen",
                emoji=emoji.link,
                description=f"{'Ativo' if Lyongen_enabled and Lyongen_integrated else 'Desativado'} - Gerador de contas"
            ),
            disnake.SelectOption(
                label="Lyon Boost",
                value="boost",
                emoji=emoji.boost,
                description=f"{'Ativo' if boost_enabled else 'Desativado'} - Venda de boosts"
            )
        ]

        # Lyon Gen info
        Lyongen_info = f"{emoji.link} **Lyon Gen (Grátis)** — {Lyongen_status}"
        if Lyongen_user:
            Lyongen_info += f"\n-# {emoji.member} Integrado com: `{Lyongen_user}`"
        else:
            Lyongen_info += f"\n-# Gerador de contas com integração ao painel web"

        # Lyon Boost info
        boost_info = f"{emoji.boost} **Lyon Boost** — {boost_status}"
        boost_info += f"\n-# Sistema de venda de boosts para servidores"

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.lyon}\n"
                    f"-# Painel > Configurações > **Extensões**"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"Gerencie as extensões disponíveis do bot.\n"
                    f"Selecione uma extensão abaixo para acessar suas configurações."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(Lyongen_info),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(boost_info),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Extensions_Select",
                        placeholder=f"[2] Extensões disponíveis",
                        options=extension_options
                    )
                ),
                **container_kwargs,
            ),
        ]

    def _build_embed_panel(self, inter: disnake.MessageInteraction, extensions_config: dict) -> tuple:
        """Constrói painel em modo embed"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        # Status das extensões
        boost_enabled = subs.is_extension_active("boost")
        boost_status = f"{emoji.on} Ativada" if boost_enabled else f"{emoji.off} Desativada"

        Lyongen_data = self._get_Lyongen_status()
        Lyongen_enabled = Lyongen_data.get("enabled", True)
        Lyongen_integrated = (
            Lyongen_data.get("integrated_user_id") is not None
            or bool(Lyongen_data.get("integrated_user"))
        )

        if Lyongen_enabled and Lyongen_integrated:
            Lyongen_status = f"{emoji.on} Ativo"
        elif Lyongen_enabled:
            Lyongen_status = f"{emoji.warn} Não integrado"
        else:
            Lyongen_status = f"{emoji.off} Desativado"

        embed = disnake.Embed(
            title=f"{emoji.commands} Extensões",
            description=(
                "Gerencie as extensões disponíveis do bot.\n"
                "Clique em uma extensão para acessar suas configurações."
            ),
        )

        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color

        # Lyon Gen Field
        Lyongen_value = f"**Status:** {Lyongen_status}\n"
        if Lyongen_integrated:
            Lyongen_value += f"**Usuário:** `{Lyongen_data.get('integrated_user', 'N/A')}`\n"
        Lyongen_value += "Gerador de contas com integração ao painel web."

        embed.add_field(
            name=f"{emoji.link} Lyon Gen (Grátis)",
            value=Lyongen_value,
            inline=False
        )

        # Lyon Boost Field
        embed.add_field(
            name=f"{emoji.boost} Lyon Boost",
            value=(
                f"**Status:** {boost_status}\n"
                f"Sistema de venda de boosts para servidores Discord."
            ),
            inline=False
        )




        # Opções para o select menu de extensões
        extension_options = [
            disnake.SelectOption(
                label="Lyon Gen",
                value="Lyongen",
                emoji=emoji.link,
                description=f"{'Ativo' if Lyongen_enabled and Lyongen_integrated else 'Desativado'} - Gerador de contas"
            ),
            disnake.SelectOption(
                label="Lyon Boost",
                value="boost",
                emoji=emoji.boost,
                description=f"{'Ativo' if boost_enabled else 'Desativado'} - Venda de boosts"
            )
        ]

        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Extensions_Select",
                    placeholder=f"[2] Extensões disponíveis",
                    options=extension_options
                )
            ),
        ]

        return embed, components

    # ==================== VISION GEN PANEL ====================

    def _build_Lyongen_panel(self, inter: disnake.MessageInteraction) -> list:
        """Constrói o painel do Lyon Gen"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        status_data = self._get_Lyongen_status()
        integrated_user = status_data.get("integrated_user", "Nenhum")
        is_integrated = status_data.get("integrated_user_id") is not None or bool(status_data.get("integrated_user"))
        project_key = status_data.get("project_key")
        is_enabled = status_data.get("enabled", True)
        settings = status_data.get("settings", {})
        command_enabled = bool(settings.get("command_enabled", False))
        summary = self.systemgen.summary()

        # Status info
        status_text = f"# {emoji.lyon}\n-# Painel > Extensões > **Lyon Gen**"

        info_lines = [
            f"{emoji.on if is_enabled else emoji.off} **Status:** {'Ativo' if is_enabled else 'Desativado'}",
            f"{emoji.member} **Usuário Integrado:** `{integrated_user}`"
        ]
        if project_key:
            info_lines.append(f"{emoji.folder} **Projeto Selecionado:** `{project_key}`")
            info_lines.append(f"-# Se você regenerou a key do projeto, selecione-o novamente.")

        info_lines.extend(
            [
                f"{emoji.cardbox} **Servicos:** `{summary['service_count']}` | **Estoque:** `{summary['stock_total']}`",
                f"{emoji.commands} **Comando /gen:** `{'Ativo' if command_enabled else 'Desativado'}` | **Max:** `{summary['max_generate']}`",
                f"{emoji.website} **Site Local:** `{summary['site_url']}`",
            ]
        )
        info_text = "\n".join(info_lines)

        options = [
            disnake.SelectOption(
                label="Gerar Código",
                value="generate_code",
                emoji=emoji.link,
                description="Gera um código para vincular ao painel"
            ),
            disnake.SelectOption(
                label="Definir Projeto",
                value="select_project",
                emoji=emoji.folder,
                description="Define um projeto padrão para requisições"
            ),
            disnake.SelectOption(
                label="Configurar Extensão",
                value="configure_extension",
                emoji=emoji.settings,
                description="Gerenciar configurações avançadas"
            ),
            disnake.SelectOption(
                label="Tutorial",
                value="tutorial",
                emoji=emoji.fire,
                description="Aprenda a usar a extensão"
            )
        ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(status_text),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(info_text),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="LyonGen_MainSelect",
                        placeholder="[4] Selecione uma das ações.",
                        options=options,
                        disabled=not is_enabled
                    )
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Configuracoes_Extensoes"
                ),
                disnake.ui.Button(
                    label="Desativar" if is_enabled else "Ativar",
                    style=disnake.ButtonStyle.red if is_enabled else disnake.ButtonStyle.green,
                    emoji=emoji.off if is_enabled else emoji.on,
                    custom_id="LyonGen_Toggle"
                )
            )
        ]

    def _build_Lyongen_config_panel(self, inter: disnake.MessageInteraction) -> list:
        """Constrói o painel de configuração do Lyon Gen"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        status_data = self._get_Lyongen_status()
        settings = status_data.get("settings", {})
        command_enabled = bool(settings.get("command_enabled", False))

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        options = [
            disnake.SelectOption(
                label="Gerar Streaming/Gaming",
                value="gen_streaming_gaming",
                emoji=emoji.controller,
                description="Gerar contas de serviços"
            ),
            disnake.SelectOption(
                label="Ativar Live-Stock em Produtos",
                value="live_stock",
                emoji=emoji.cart,
                description="Reabastecer produtos automaticamente"
            ),
            disnake.SelectOption(
                label="Personalizar Embeds",
                value="custom_embeds",
                emoji=emoji.paint,
                description="Em desenvolvimento"
            ),
            disnake.SelectOption(
                label="Desativar comando /gen" if command_enabled else "Ativar comando /gen",
                value="activate_gen",
                emoji=emoji.commands,
                description=f"Status atual: {'Ativo' if command_enabled else 'Desativado'}"
            )
        ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.lyon}\n"
                    f"-# Lyon Gen > **Configurações**"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"-# Selecione uma opcao para configurar.\n"
                    f"{emoji.commands} **/gen:** `{'Ativo' if command_enabled else 'Desativado'}`\n"
                    f"{emoji.cardbox} **Maximo por geracao:** `{settings.get('max_generate', 20)}`"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="LyonGen_ConfigSelect",
                        placeholder="Selecione uma configuração",
                        options=options
                    )
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Extensions_LyonGen"
                )
            )
        ]

    # ==================== BUTTON HANDLERS ====================

    @commands.Cog.listener("on_button_click")
    async def on_extensions_button_click(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id

        if custom_id == "Configuracoes_Extensoes":
            await self.display_extensions_panel(inter)

        elif custom_id == "Extensions_Info":
            await self._safe_response_send(
                inter,
                f"{emoji.information if hasattr(emoji, 'information') else 'ℹ️'} **Sobre as Extensões**\n\n"
                f"Todas as extensões são nomeadas pela **Lyon**, porém são oferecidas através de "
                f"**parcerias externas** com desenvolvedores e empresas especializadas.\n\n"
                f"Cada extensão possui funcionalidades únicas e podem requerer configuração adicional "
                f"ou integração com serviços externos para funcionamento completo.",
                ephemeral=True  
            )

        elif custom_id == "Extensions_Purchase":
            await self._show_purchase_panel(inter)

        elif custom_id == "Extensions_MyPayments":
            await self._show_my_payments(inter)

        elif custom_id == "Extensions_BackFromPurchase":
            await self.display_extensions_panel(inter)

        elif custom_id == "Extensions_BuyBoost":
            await self._create_boost_payment(inter)

        elif custom_id.startswith("Extensions_VerifyPayment_"):
            payment_id = custom_id.replace("Extensions_VerifyPayment_", "")
            await self._verify_payment(inter, payment_id)

        elif custom_id == "Extensions_RenewBoost":
            await self._create_boost_payment(inter)

        elif custom_id == "Extensions_LyonGen":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                # For embed mode, we still use components V2
                components = self._build_Lyongen_panel(inter)
                await inter.edit_original_message(content=None, embed=None, components=components)
            else:
                await message.wait(inter, send=False)
                components = self._build_Lyongen_panel(inter)
                await inter.edit_original_message(components=components)

        elif custom_id == "Extensions_Boost":
            boost_cog = self.bot.get_cog("BoostExtension")
            if boost_cog:
                await boost_cog.display_boost_panel(inter)

        elif custom_id == "LyonGen_Toggle":
            current_data = self.systemgen.load()
            is_enabled = current_data.get("enabled", True)
            self.systemgen.set_enabled(not is_enabled)

            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)
            components = self._build_Lyongen_panel(inter)
            await inter.edit_original_message(components=components)

        elif custom_id == "LyonGen_BackToConfig":
            await message.wait(inter, send=False)
            components = self._build_Lyongen_config_panel(inter)
            await inter.edit_original_message(components=components)

        elif custom_id == "LyonGen_ConfirmLiveStock":
            # Save that user accepted the live stock warning
            current_data = self.systemgen.load()
            if "livestock" not in current_data:
                current_data["livestock"] = {}
            current_data["livestock"]["accepted_warning"] = True
            self.systemgen.save(current_data)

            await self._show_products_for_livestock(inter)

        elif custom_id == "LyonGen_CancelLiveStock":
            await message.wait(inter, send=False)
            components = self._build_Lyongen_config_panel(inter)
            await inter.edit_original_message(components=components)

        elif custom_id == "LyonGen_LiveStockAnalytics":
            await self._show_livestock_analytics(inter)

        elif custom_id == "LyonGen_LiveStockNotifications":
            await self._toggle_livestock_notifications(inter)
        
        elif custom_id == "LyonGen_LiveStockProducts":
            await self._show_products_for_livestock(inter)

        elif custom_id.startswith("check_code_"):
            code = custom_id.replace("check_code_", "")
            await self._check_integration_code(inter, code)

    async def _check_integration_code(self, inter: disnake.MessageInteraction, code: str):
        """Verifica se o código foi integrado"""
        if not await self._safe_defer(inter, ephemeral=True):
            return
        code_data = self.systemgen.check_code(code)
        if not code_data:
            await self._safe_followup(inter, f"{emoji.wrong} Codigo nao encontrado. Gere um novo codigo e tente novamente.", ephemeral=True)
            return

        if not code_data.get("redeemed"):
            await self._safe_followup(
                inter,
                f"{emoji.warn} Este codigo ainda nao foi resgatado no site local.\n\n"
                f"Acesse `{self.systemgen.summary()['site_url']}` e insira o codigo **`{code}`**.",
                ephemeral=True,
            )
            return

        username = code_data.get("username") or "Local"
        await self._safe_followup(
            inter,
            f"{emoji.correct} **Sucesso!** Pro vinculado ao usuario: **{username}**\n\n"
            f"Agora voce pode configurar servicos e gerar itens pelo Lyon Gen.",
            ephemeral=True,
        )
        try:
            await inter.message.edit(components=self._build_Lyongen_panel(inter))
        except Exception:
            pass
        return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/bot/check-code/{code}",
                    headers={"x-bot-secret": self.bot_secret}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("redeemed"):
                            username = data.get("username")
                            user_id = data.get("redeemedBy")

                            # Update database
                            current_data = db.obter("database/Lyongen.json")
                            current_data["integrated_user"] = username
                            current_data["integrated_user_id"] = user_id
                            current_data["project_key"] = None
                            db.salvar("database/Lyongen.json", current_data)

                            await inter.followup.send(
                                f"{emoji.correct} **Sucesso!** Pro vinculado ao usuário: **{username}**\n\n"
                                f"Agora você pode selecionar um projeto em **Definir Projeto**.",
                                ephemeral=True
                            )

                            # Refresh the panel
                            mode = db.get_document("custom_mode").get("mode")
                            if mode == "embed":
                                await embed_message.wait(inter, send=False)
                            components = self._build_Lyongen_panel(inter)
                            await inter.message.edit(components=components)
                        else:
                            await inter.followup.send(
                                f"{emoji.warn} Este código ainda não foi resgatado no site.\n\n"
                                f"Acesse https://loopgen.vercel.app/ e insira o código no dashboard.",
                                ephemeral=True
                            )
                    else:
                        await inter.followup.send(f"Erro ao verificar código: {response.status}", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"Erro de conexão: {str(e)}", ephemeral=True)

    async def _show_my_payments(self, inter: disnake.MessageInteraction):
        """Mostra histórico de pagamentos do usuário"""
        mode = db.get_document("custom_mode").get("mode")
        user_id = str(inter.author.id)
        data = subs.get_user_payments(user_id)
        
        # Cores
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)
            
        pending = data["pending"]
        history = data["history"]
        
        container_items = []
        
        # Header
        container_items.append(disnake.ui.TextDisplay(f"# {emoji.lyon}\nMeus Pagamentos"))
        container_items.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
        
        if not pending and not history:
             container_items.append(disnake.ui.TextDisplay("`Nenhum registro de pagamento encontrado.`"))
        else:
            if pending:
                container_items.append(disnake.ui.TextDisplay(f"### {emoji.time} Pendentes"))
                text = ""
                for p in pending:
                    ext_name = p.get('extension_id', 'Extensão').capitalize()
                    date_str = p.get('created_at', '')[:19].replace('T', ' ')
                    text += f"• **{ext_name}**: R$ {p['value']:.2f}\nCriado em: {date_str}\n"
                container_items.append(disnake.ui.TextDisplay(text))
                container_items.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
                
            if history:
                container_items.append(disnake.ui.TextDisplay(f"### {emoji.correct} Realizados (Últimos 5)"))
                text = ""
                for h in history[:5]:
                    ext_name = h.get('extension_id', 'Extensão').capitalize()
                    date_str = h.get('completed_at', '')[:19].replace('T', ' ')
                    text += f"• **{ext_name}**: R$ {h['value']:.2f}\nStatus: {h.get('status')} - Data: {date_str}\n"
                container_items.append(disnake.ui.TextDisplay(text))

        container = disnake.ui.Container(*container_items, **container_kwargs)
        
        components = [
            container,
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Extensions_Purchase"
                )
            )
        ]
        
        if mode == "embed":
             await self._safe_response_edit(inter, embed=None, components=components)
        else:
             await self._safe_response_edit(inter, content=None, components=components)

    async def _show_purchase_panel(self, inter: disnake.MessageInteraction):
        """Mostra as extensões ativas para compra"""
        mode = db.get_document("custom_mode").get("mode")
        
        # Verificar status do Boost
        is_active = subs.is_extension_active("boost")
        expiry_date = subs.get_expiry_date("boost")
        
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)
            
        # Select Menu de Compra
        purchase_select = disnake.ui.StringSelect(
            placeholder="[2] Selecione uma extensão...",
            custom_id="Extensions_Purchase_Select",
            min_values=1,
            max_values=1,
            options=[
                disnake.SelectOption(
                    label="Lyon Gen (Grátis)",
                    value="purchase_Lyongen",
                    description="Gerador de contas com integração web",
                    emoji=emoji.link
                ),
                disnake.SelectOption(
                    label="Lyon Boost",
                    value="purchase_boost",
                    description="R$ 50,00 / mês - Sistema de boosts",
                    emoji=emoji.boost
                )
            ]
        )

        # Texto do Lyon Boost (com expiração se ativo)
        boost_title = f"{emoji.boost} **Lyon Boost (R$50 per/month)**"
        if is_active and expiry_date:
            boost_title = f"{emoji.boost} **Lyon Boost (Expira: {expiry_date})**"

        container = disnake.ui.Container(
            disnake.ui.TextDisplay(
                f"# {emoji.lyon}\n"
                f"-# Configurações > Extensões > **Comprar**"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(
                f"Adquira ou renove assinaturas para as extensões do bot."
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            
            # Lyon Gen Text
            disnake.ui.TextDisplay(
                f"{emoji.link} **Lyon Gen (Grátis)**\n"
                f"-# Gerador de contas com integração ao painel web"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            
            # Lyon Boost Text
            disnake.ui.TextDisplay(
                f"{boost_title}\n"
                f"-# Sistema completo de vendas de boosts"
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            
            # Select Menu (Inside Container - Wrapped in ActionRow)
            disnake.ui.ActionRow(purchase_select),
            
            **container_kwargs
        )
        
        components = [
            container,
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Extensions_BackFromPurchase"
                ),
                disnake.ui.Button(
                    label="Meus Pagamentos",
                    style=disnake.ButtonStyle.secondary,
                    emoji=emoji.wallet,
                    custom_id="Extensions_MyPayments"
                )
            )
        ]
        
        if mode == "embed":
             await self._safe_response_edit(inter, embed=None, components=components)
        else:
             await self._safe_response_edit(inter, content=None, components=components)

    async def _create_boost_payment(self, inter: disnake.MessageInteraction):
        """Cria pagamento para o Boost"""
        import time
        user_id = str(inter.author.id)
        current_time = time.time()
        
        if user_id in self.payment_cooldowns:
            expiration = self.payment_cooldowns[user_id]
            if current_time < expiration:
                 await self._safe_response_send(
                     inter,
                     f"{emoji.time} Aguarde {int(expiration - current_time)}s para gerar outro pagamento.",
                     ephemeral=True
                 )
                 return

        self.payment_cooldowns[user_id] = current_time + 30

        if not await self._safe_defer(inter, ephemeral=True):
            return
        
        # Criar pagamento
        result = await subs.create_payment("boost", user_id)
        
        if not result["success"]:
            await self._safe_followup(
                inter,
                f"{emoji.wrong} Erro ao criar pagamento: {result.get('error')}",
                ephemeral=True
            )
            return
            
        # Converter base64 para arquivo
        import base64
        import io
        
        qr_code_base64 = result["qrcode_url"]
        qr_code_data = qr_code_base64.split(",")[1]
        qr_code_bytes = base64.b64decode(qr_code_data)
        file = disnake.File(io.BytesIO(qr_code_bytes), filename="qrcode.png")
        
        payment_id = result["payment_id"]
        copy_paste = result["copy_paste"]
        
        # Embed de pagamento
        embed = disnake.Embed(
            title=f"{emoji.dollar} Pagamento Gerado",
            description=(
                f"Realize o pagamento via PIX para ativar o **Lyon Boost**.\n\n"
                f"**Valor:** R$ {result['value']:.2f}\n"
                f"**Expiração:** 30 minutos"
            ),
            color=disnake.Color.green()
        )
        embed.set_image(url="attachment://qrcode.png")
        embed.add_field(name="Copia e Cola", value=f"```{copy_paste}```", inline=False)
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Já efetuei o pagamento!",
                    style=disnake.ButtonStyle.success,
                    emoji=emoji.correct,
                    custom_id=f"Extensions_VerifyPayment_{payment_id}"
                )
            )
        ]
        
        await self._safe_followup(inter, embed=embed, file=file, components=components, ephemeral=True)

    async def _verify_payment(self, inter: disnake.MessageInteraction, payment_id: str):
        """Verifica se o pagamento foi realizado"""
        if not await self._safe_defer(inter, ephemeral=True):
            return
        
        result = await subs.check_payment(payment_id)
        
        if not result["success"]:
            await self._safe_followup(
                inter,
                f"{emoji.wrong} Erro ao verificar pagamento: {result.get('error')}",
                ephemeral=True
            )
            return
            
        status = result.get("status")
        
        if status == "COMPLETED":
            await self._safe_followup(
                inter,
                f"{emoji.correct} **Pagamento Confirmado!**\n\n"
                f"A extensão **Lyon Boost** foi ativada com sucesso.\n"
                f"Expira em: **{result.get('expires_at')}**",
                ephemeral=True
            )
            
            # Atualizar painel de compra
            await self._show_purchase_panel(inter)
            
        elif status == "PENDING" or status == "ACTIVE":
            await self._safe_followup(
                inter,
                f"{emoji.time} **Pagamento Pendente**\n"
                f"Aguardando confirmação bancária...",
                ephemeral=True
            )
        else:
            await self._safe_followup(
                inter,
                f"{emoji.wrong} Pagamento falhou ou expirou (Status: {status})",
                ephemeral=True
            )

    # ==================== DROPDOWN HANDLERS ====================

    @commands.Cog.listener("on_dropdown")
    async def on_Lyongen_dropdown(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id

        # Handler para o select menu de compra
        if custom_id == "Extensions_Purchase_Select":
            choice = inter.values[0]
            
            if choice == "purchase_Lyongen":
                 await self._safe_response_send(
                     inter,
                     f"{emoji.link} **Lyon Gen** é uma extensão gratuita e já está disponível para uso.",
                     ephemeral=True
                 )
            elif choice == "purchase_boost":
                 await self._create_boost_payment(inter)
            return

        # Handler para o select menu de extensões principais
        if custom_id == "Extensions_Select":
            choice = inter.values[0]

            if choice == "Lyongen":
                mode = db.get_document("custom_mode").get("mode")
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                else:
                    await message.wait(inter, send=False)
                components = self._build_Lyongen_panel(inter)
                await inter.edit_original_message(content=None, embed=None, components=components)

            elif choice == "boost":
                boost_cog = self.bot.get_cog("BoostExtension")
                if boost_cog:
                    await boost_cog.display_boost_panel(inter)
                else:
                    await self._safe_response_send(
                        inter,
                        f"{emoji.warn} Extensão Lyon Boost não está disponível.",
                        ephemeral=True
                    )

            elif choice in ["members", "robux", "mods", "tools"]:
                await self._safe_response_send(
                    inter,
                    f"{emoji.warn} Esta extensão está **desativada** e será liberada em breve!",
                    ephemeral=True
                )
            return

        if custom_id == "LyonGen_MainSelect":
            choice = inter.values[0]

            if choice == "generate_code":
                await self._generate_code(inter)


            elif choice == "select_project":
                await self._show_project_selection(inter)

            elif choice == "configure_extension":
                status_data = self._get_Lyongen_status()
                if not status_data.get("integrated_user_id") and not status_data.get("integrated_user"):
                    await self._safe_response_send(
                        inter,
                        f"{emoji.wrong} Você precisa vincular o bot a um usuário primeiro.\n\n"
                        f"Use a opção **Gerar Código** e siga o tutorial.",
                        ephemeral=True
                    )
                    return

                await message.wait(inter, send=False)
                components = self._build_Lyongen_config_panel(inter)
                await inter.edit_original_message(components=components)

            elif choice == "tutorial":
                summary = self.systemgen.summary()
                tutorial_text = (
                    f"# {emoji.fire} Tutorial do Lyon Gen Local\n\n"
                    f"**1.** Abra o site local: `{summary['site_url']}`\n"
                    f"**2.** Crie ou selecione um projeto.\n"
                    f"**3.** Cadastre um servico e adicione contas no estoque.\n"
                    f"**4.** Use **Gerar Streaming/Gaming** no painel ou ative o comando `/gen`.\n"
                    f"**5.** O bot entrega as contas por arquivo no privado ou de forma efemera."
                )
                await self._safe_response_send(inter, tutorial_text, ephemeral=True)

        elif custom_id == "LyonGen_ConfigSelect":
            choice = inter.values[0]

            if choice == "gen_streaming_gaming":
                await inter.response.send_modal(GenServiceModal(self))

            elif choice == "live_stock":
                await self._handle_live_stock_option(inter)

            elif choice == "activate_gen":
                data = self.systemgen.load()
                current = bool(data.get("settings", {}).get("command_enabled", False))
                self.systemgen.set_command_enabled(not current)
                await message.wait(inter, send=False)
                components = self._build_Lyongen_config_panel(inter)
                await inter.edit_original_message(components=components)
                await self._safe_followup(
                    inter,
                    f"{emoji.correct} Comando `/gen` {'ativado' if not current else 'desativado'} com sucesso.",
                    ephemeral=True,
                )

            elif choice == "custom_embeds":
                await self._safe_response_send(
                    inter,
                    f"{emoji.warn} Esta funcionalidade está em desenvolvimento e será liberada em breve!",
                    ephemeral=True
                )

        elif custom_id == "LyonGen_ProjectSelect":
            val = inter.values[0]
            key = val.replace("proj_", "")

            self.systemgen.select_project(key)

            await self._safe_response_send(
                inter,
                f"{emoji.correct} Projeto selecionado com sucesso! Key: `{key}`",
                ephemeral=True
            )

            # Refresh panel
            components = self._build_Lyongen_panel(inter)
            try:
                await inter.message.edit(components=components)
            except (disnake.NotFound, disnake.HTTPException):
                pass

        elif custom_id == "LyonGen_LiveStockProduct":
            product_id = inter.values[0].replace("prod_", "")
            await inter.response.send_modal(LiveStockConfigModal(self, product_id))

    # ==================== HELPER METHODS ====================

    async def _generate_code(self, inter: disnake.MessageInteraction):
        if not await self._safe_defer(inter, ephemeral=True):
            return

        code = self.systemgen.create_code(bot_id=getattr(self.bot.user, "id", ""), created_by=inter.author.id)
        summary = self.systemgen.summary()
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.link} Codigo de Vinculo\n\n"
                    f"Seu codigo e: **`{code}`**\n\n"
                    f"-# Abra o site local do Gen: `{summary['site_url']}`\n"
                    f"-# Cole o codigo na area de integracao e depois clique em **Ja integrei**."
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Ja integrei",
                    style=disnake.ButtonStyle.green,
                    emoji=emoji.correct,
                    custom_id=f"check_code_{code}",
                )
            ),
        ]
        await self._safe_followup(inter, components=components, ephemeral=True)

    async def _show_project_selection(self, inter: disnake.MessageInteraction):
        """Mostra seleção de projetos"""
        status_data = self._get_Lyongen_status()
        if not status_data.get("integrated_user_id"):
            await self._safe_response_send(
                inter,
                f"{emoji.wrong} Você precisa vincular o bot a um usuário primeiro.",
                ephemeral=True
            )
            return

        if not await self._safe_defer(inter):
            return

        discord_id = status_data.get("integrated_user_id")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/projects/user/{discord_id}",
                    headers={"x-bot-secret": self.bot_secret}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        projects = data.get("projects", [])

                        if not projects:
                            await inter.followup.send(
                                f"{emoji.warn} Você não possui projetos criados no painel.\n\n"
                                f"Acesse https://loopgen.vercel.app/ e crie um novo projeto.",
                                ephemeral=True
                            )
                            return

                        options = []
                        for p in projects:
                            options.append(disnake.SelectOption(
                                label=p.get("name"),
                                value=f"proj_{p.get('key')}",
                                description=f"Key: {p.get('key')} | Uso: {p.get('usage', 0)}",
                                emoji=emoji.folder
                            ))

                        colors = db.get_document("custom_colors")
                        primary_color_hex = colors.get("primary")
                        container_kwargs = {}
                        if primary_color_hex:
                            primary_color = int(primary_color_hex.replace("#", ""), 16)
                            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

                        components = [
                            disnake.ui.Container(
                                disnake.ui.TextDisplay(
                                    f"# {emoji.lyon}\n"
                                    f"-# Lyon Gen > **Projetos**"
                                ),
                                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                                disnake.ui.TextDisplay(
                                    f"-# Selecione um projeto padrão para usar nas requisições."
                                ),
                                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                                disnake.ui.ActionRow(
                                    disnake.ui.StringSelect(
                                        custom_id="LyonGen_ProjectSelect",
                                        placeholder="Selecione um projeto",
                                        options=options
                                    )
                                ),
                                **container_kwargs
                            ),
                            disnake.ui.ActionRow(
                                disnake.ui.Button(
                                    label="",
                                    style=disnake.ButtonStyle.grey,
                                    emoji=emoji.back,
                                    custom_id="Extensions_LyonGen"
                                )
                            )
                        ]

                        await inter.edit_original_message(components=components)
                    else:
                        await inter.followup.send(f"Erro ao buscar projetos: {response.status}", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"Erro de conexão: {str(e)}", ephemeral=True)

    async def _show_project_selection(self, inter: disnake.MessageInteraction):
        if not await self._safe_defer(inter):
            return
        data = self.systemgen.load()
        projects = list(data.get("projects", {}).values())
        if not projects:
            projects = [self.systemgen.create_project("Projeto Local")]

        options = [
            disnake.SelectOption(
                label=str(project.get("name", project.get("key", "Projeto")))[:100],
                value=f"proj_{project.get('key')}",
                description=f"Uso: {project.get('usage', 0)}",
                emoji=emoji.folder,
                default=project.get("key") == data.get("project_key"),
            )
            for project in projects[:25]
        ]

        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.lyon}\n"
                    f"-# Lyon Gen > **Projetos Locais**"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay("Selecione o projeto que recebera o uso das geracoes locais."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="LyonGen_ProjectSelect",
                        placeholder="Selecione um projeto",
                        options=options,
                    )
                ),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Extensions_LyonGen",
                )
            ),
        ]
        await self._safe_response_edit(inter, components=components)

    async def _handle_live_stock_option(self, inter: disnake.MessageInteraction):
        """Handle Live Stock option"""
        livestock_config = self._get_livestock_config()

        if livestock_config.get("accepted_warning"):
            # User already accepted, show products
            await self._show_products_for_livestock(inter)
        else:
            # Show warning message
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary")
            container_kwargs = {}
            if primary_color_hex:
                primary_color = int(primary_color_hex.replace("#", ""), 16)
                container_kwargs["accent_colour"] = disnake.Colour(primary_color)

            # Fetch auto-check services
            supported_services = []
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://loopchecker.squareweb.app/services") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            supported_services = data.get("services", [])
            except:
                pass

            services_text = ""
            if supported_services:
                services_str = ", ".join([f"**{s.capitalize()}**" for s in supported_services])
                services_text = f"Os serviços {services_str} já contam com o sistema de **auto-check** ativo.\n\n"

            components = [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(
                        f"# {emoji.warn} Aviso Importante\n\n"
                        f"{services_text}"
                        f"Para os demais serviços, a **Loop** (fornecedora desta extensão) lançará o sistema de **auto-check** "
                        f"apenas no dia **20/12/2025**.\n\n"
                        f"Por enquanto, essas contas geradas **não estão sendo verificadas automaticamente**, "
                        f"porém ainda possuem **altas possibilidades de funcionarem** devido à qualidade "
                        f"das fontes utilizadas.\n\n"
                        f"-# Deseja prosseguir mesmo sabendo desta informação?"
                    ),
                    **container_kwargs,
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Sim, prosseguir",
                        style=disnake.ButtonStyle.green,
                        emoji=emoji.correct,
                        custom_id="LyonGen_ConfirmLiveStock"
                    ),
                    disnake.ui.Button(
                        label="Cancelar",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.wrong,
                        custom_id="LyonGen_CancelLiveStock"
                    )
                )
            ]

            await message.wait(inter, send=False)
            await inter.edit_original_message(components=components)

    async def _show_products_for_livestock(self, inter: disnake.MessageInteraction):
        """Show products for Live Stock configuration"""
        # Get products from MongoDB
        products_dict = db.get_document("loja_products") or {}

        if not products_dict:
            await inter.response.send_message(
                f"{emoji.warn} Nenhum produto encontrado. Crie produtos primeiro na loja.",
                ephemeral=True
            )
            return

        options = []
        count = 0
        for product_id, p in products_dict.items():
            if count >= 25:  # Max 25 options
                break
            product_name = p.get("name", "Sem nome")
            campos = p.get("campos", {})
            
            # ONLY show products that have at least one campo configured
            if not campos or len(campos) == 0:
                continue  # Skip products without campos
            
            if product_name:
                # Get current live stock status
                Lyongen_data = self._get_Lyongen_status()
                livestock = Lyongen_data.get("livestock", {})
                product_config = livestock.get("products", {}).get(product_id, {})
                is_enabled = product_config.get("enabled", False)
                
                status_emoji = emoji.on if is_enabled else emoji.off
                status_text = "Ativo" if is_enabled else "Inativo"
                
                options.append(disnake.SelectOption(
                    label=product_name[:100],
                    value=f"prod_{product_id}",
                    description=f"{status_text} | Campos: {len(campos)}",
                    emoji=status_emoji
                ))
                count += 1

        if not options:
            await inter.response.send_message(
                f"{emoji.warn} Nenhum produto com campos configurados encontrado.\n\n"
                f"**Produtos precisam ter pelo menos um campo para usar o Live Stock.**\n"
                f"Vá em **Loja > Produtos > [Produto] > Campos** e crie um campo primeiro.",
                ephemeral=True
            )
            return

        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.lyon}\n"
                    f"-# Lyon Gen > **Live Stock**"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    f"Selecione um produto para configurar o reabastecimento automático.\n"
                    f"-# Apenas produtos com campos configurados são exibidos."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="LyonGen_LiveStockProduct",
                        placeholder="Selecione um produto",
                        options=options
                    )
                ),
                **container_kwargs
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="LyonGen_BackToConfig"
                ),
                disnake.ui.Button(
                    label="Análise",
                    style=disnake.ButtonStyle.blurple,
                    emoji=emoji.chart,
                    custom_id="LyonGen_LiveStockAnalytics"
                ),
                disnake.ui.Button(
                    label="Notificações",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.announcement if hasattr(emoji, 'announcement') else emoji.message,
                    custom_id="LyonGen_LiveStockNotifications"
                )
            )
        ]

        if hasattr(inter, 'response') and not inter.response.is_done():
            await message.wait(inter, send=False)
        await inter.edit_original_message(components=components)
    
    async def _show_livestock_analytics(self, inter: disnake.MessageInteraction):
        """Show Live Stock analytics panel"""
        Lyongen_data = self._get_Lyongen_status()
        livestock = Lyongen_data.get("livestock", {})
        products_config = livestock.get("products", {})
        
        products_dict = db.get_document("loja_products") or {}
        
        if not products_config:
            await inter.response.send_message(
                f"{emoji.warn} Nenhum produto configurado com Live Stock ainda.",
                ephemeral=True
            )
            return
        
        # Build analytics text
        analytics_lines = []
        total_products = 0
        total_active = 0
        
        for product_id, config in products_config.items():
            product = products_dict.get(product_id, {})
            product_name = product.get("name", f"ID: {product_id}")
            
            is_enabled = config.get("enabled", False)
            service = config.get("service", "N/A")
            category = config.get("category", "N/A")
            gen_count = config.get("gen_count", 0)
            interval = config.get("interval_hours", 0)
            last_restock = config.get("last_restock", "Nunca")
            
            total_products += 1
            if is_enabled:
                total_active += 1
            
            status = f"{emoji.on}" if is_enabled else f"{emoji.off}"
            
            line = (
                f"{status} **{product_name}**\n"
                f"-# Serviço: `{service}` | Categoria: `{category}`\n"
                f"-# Gerar: `{gen_count} contas` a cada `{interval}h`\n"
                f"-# Último restock: `{last_restock[:19] if last_restock and last_restock != 'Nunca' else 'Nunca'}`"
            )
            analytics_lines.append(line)
        
        analytics_text = "\n\n".join(analytics_lines) if analytics_lines else "Nenhum produto configurado."
        
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)
        
        components = [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    f"# {emoji.chart} Análise Live Stock\n"
                    f"-# {total_active}/{total_products} produtos ativos"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(analytics_text),
                **container_kwargs
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="LyonGen_LiveStockProducts"
                )
            )
        ]
        
        if hasattr(inter, 'response') and not inter.response.is_done():
            await message.wait(inter, send=False)
        await inter.edit_original_message(components=components)
    
    async def _toggle_livestock_notifications(self, inter: disnake.MessageInteraction):
        """Toggle Live Stock DM notifications"""
        Lyongen_data = self.systemgen.load()
        livestock = Lyongen_data.setdefault("livestock", {})
        
        # Toggle notification setting
        current = livestock.get("dm_notifications", False)
        livestock["dm_notifications"] = not current
        
        self.systemgen.save(Lyongen_data)
        
        new_status = "ativadas" if not current else "desativadas"
        emoji_status = emoji.on if not current else emoji.off
        
        await inter.response.send_message(
            f"{emoji_status} **Notificações de Live Stock {new_status}!**\n\n"
            f"{'Você receberá uma DM sempre que o Live Stock adicionar estoque a um produto.' if not current else 'Você não receberá mais notificações de Live Stock.'}",
            ephemeral=True
        )


# ==================== MODALS ====================

class GenServiceModal(disnake.ui.Modal):
    def __init__(self, cog):
        self.cog = cog
        components = [
            disnake.ui.TextInput(
                label="Nome do Serviço",
                placeholder="Ex: Netflix, Spotify, Steam, Epic Games...",
                custom_id="service_name",
                style=disnake.TextInputStyle.short,
                max_length=50,
                required=True
            ),
            disnake.ui.TextInput(
                label="Quantidade",
                placeholder="1-20",
                custom_id="quantity",
                style=disnake.TextInputStyle.short,
                max_length=2,
                required=True,
                value="1"
            ),
            disnake.ui.Label(
                text="Categoria",
                component=disnake.ui.StringSelect(
                    placeholder="Selecione a categoria",
                    custom_id="category_select",
                    options=[
                        disnake.SelectOption(label="Streaming", value="streaming", emoji=emoji.play),
                        disnake.SelectOption(label="Gaming", value="gaming", emoji=emoji.controller),
                    ],
                    min_values=1,
                    max_values=1
                ),
                description="Selecione se é um serviço de Streaming ou Gaming.",
            ),
        ]
        super().__init__(title="Gerar Contas", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        service_name = inter.text_values["service_name"]

        # Try to get category from components
        category = "streaming"
        for component in inter.data.get("components", []):
            for child in component.get("components", []):
                if child.get("custom_id") == "category_select":
                    if "values" in child and child["values"]:
                        category = child["values"][0]

        try:
            quantity = max(1, min(20, int(inter.text_values.get("quantity", "1"))))
        except Exception:
            quantity = 1

        if not await self.cog._safe_defer(inter, ephemeral=True):
            return
        result = self.cog.systemgen.generate(
            service_name,
            category,
            quantity,
            user_id=inter.author.id,
            source="bot-panel",
        )
        if not result.get("ok"):
            await inter.followup.send(
                f"{emoji.warn} {result.get('reason')}\n\n"
                f"Adicione estoque pelo site local do Gen: `{self.cog.systemgen.summary()['site_url']}`",
                ephemeral=True,
            )
            return

        items = result.get("items", [])
        content = "\n".join(items)
        try:
            await inter.author.send(
                file=disnake.File(io.BytesIO(content.encode("utf-8")), filename=f"{service_name}_gen.txt")
            )
            await inter.followup.send(
                f"{emoji.correct} Gerei `{len(items)}` item(ns) de **{service_name}** e enviei no seu privado.\n"
                f"Estoque restante: `{result.get('available', 0)}`.",
                ephemeral=True,
            )
            return
        except disnake.Forbidden:
            pass

        try:
            await inter.followup.send(
                f"{emoji.warn} Nao consegui enviar no privado, entao deixei o arquivo aqui de forma efemera.",
                file=disnake.File(io.BytesIO(content.encode("utf-8")), filename=f"{service_name}_gen.txt"),
                ephemeral=True,
            )
        except Exception:
            self.cog.systemgen.return_stock(service_name, items)
            await inter.followup.send(
                f"{emoji.wrong} Nao consegui entregar o arquivo. O estoque foi devolvido para **{service_name}**.",
                ephemeral=True,
            )
        return

        # Check if project is configured
        data = db.obter("database/Lyongen.json")
        project_key = data.get("project_key")

        if not project_key:
            await inter.response.send_message(
                f"{emoji.wrong} Nenhum projeto selecionado. Selecione um projeto nas configurações primeiro.",
                ephemeral=True
            )
            return

        await inter.response.send_message(
            f"{emoji.reload} Gerando contas de **{service_name}** ({category})...\n\n"
            f"-# Enviarei um `.txt` no seu privado quando terminar!",
            ephemeral=True
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.cog.api_url}/scrape-project",
                    headers={"x-project-key": project_key},
                    json={
                        "service": service_name,
                        "category": category,
                        "threads": 1,
                        "timeout": 600000
                    },
                    timeout=aiohttp.ClientTimeout(total=700)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        credentials = result.get("credentials", [])
                        count = len(credentials) if isinstance(credentials, list) else len(credentials.keys()) if isinstance(credentials, dict) else 0

                        if count > 0:
                            # Create file content
                            if isinstance(credentials, dict):
                                content = "\n".join([f"{email}:{password}" for email, password in credentials.items()])
                            else:
                                content = "\n".join([f"{c.get('email')}:{c.get('password')}" for c in credentials])

                            file = disnake.File(io.BytesIO(content.encode("utf-8")), filename=f"{service_name}_contas.txt")

                            try:
                                colors = db.get_document("custom_colors")
                                primary_color_hex = colors.get("primary")
                                container_kwargs = {}
                                if primary_color_hex:
                                    primary_color = int(primary_color_hex.replace("#", ""), 16)
                                    container_kwargs["accent_colour"] = disnake.Colour(primary_color)

                                components = [
                                    disnake.ui.Container(
                                        disnake.ui.TextDisplay(
                                            f"# {emoji.correct} Geração Concluída!\n\n"
                                            f"{emoji.website if hasattr(emoji, 'website') else emoji.link} **Serviço:** `{service_name}`\n"
                                            f"{emoji.folder} **Categoria:** `{category.capitalize()}`\n"
                                            f"{emoji.cart} **Quantidade:** `{count}`"
                                        ),
                                        **container_kwargs
                                    )
                                ]

                                await inter.author.send(components=components)
                                await inter.author.send(file=file)

                                await inter.edit_original_message(
                                    content=f"{emoji.correct} **Sucesso!** As contas foram enviadas no seu privado."
                                )
                            except disnake.Forbidden:
                                await inter.edit_original_message(
                                    content=f"{emoji.warn} Gerei {count} contas, mas não consegui te enviar no privado. Verifique suas configurações de privacidade."
                                )
                        else:
                            await inter.edit_original_message(
                                content=f"{emoji.warn} O processo terminou, mas nenhuma conta foi encontrada para **{service_name}**."
                            )
                    else:
                        text = await response.text()
                        try:
                            err_json = json.loads(text)
                            err_msg = err_json.get("error", text)
                        except:
                            err_msg = text
                        await inter.edit_original_message(content=f"{emoji.wrong} **Erro na API:** {response.status}\n{err_msg}")
        except asyncio.TimeoutError:
            await inter.edit_original_message(content=f"{emoji.wrong} **Timeout:** A requisição demorou muito tempo.")
        except Exception as e:
            await inter.edit_original_message(content=f"{emoji.wrong} **Erro de conexão:** {str(e)}")


class LiveStockConfigModal(disnake.ui.Modal):
    def __init__(self, cog, product_id: str):
        self.cog = cog
        self.product_id = product_id

        # Get product to check for auto-fill
        products = db.get_document("loja_products") or {}
        product = products.get(product_id, {})
        product_name = product.get("name", "")

        # Check for known streaming/gaming services in product name
        known_services = ["netflix", "spotify", "disney", "hbo", "paramount", "prime", "steam", "epic", "xbox", "playstation", "ubisoft", "ea", "origin", "crunchyroll", "funimation"]
        service_default = ""
        for service in known_services:
            if service.lower() in product_name.lower():
                service_default = service.capitalize()
                break

        # Get existing config if any
        livestock_config = cog._get_livestock_config()
        product_config = livestock_config.get("products", {}).get(product_id, {})

        components = [
            disnake.ui.TextInput(
                label="Nome do Serviço",
                placeholder="Ex: Netflix, Spotify, Steam...",
                custom_id="service_name",
                style=disnake.TextInputStyle.short,
                max_length=50,
                required=True,
                value=product_config.get("service", service_default)
            ),
            disnake.ui.TextInput(
                label="Quantas vezes gerar (máx 5)",
                placeholder="1-5",
                custom_id="gen_count",
                style=disnake.TextInputStyle.short,
                max_length=1,
                required=True,
                value=str(product_config.get("gen_count", 1))
            ),
            disnake.ui.TextInput(
                label="Intervalo de reabastecimento (horas, mín 6)",
                placeholder="6-168",
                custom_id="interval_hours",
                style=disnake.TextInputStyle.short,
                max_length=3,
                required=True,
                value=str(product_config.get("interval_hours", 6))
            ),
            disnake.ui.Label(
                text="Categoria",
                component=disnake.ui.StringSelect(
                    placeholder="Selecione a categoria",
                    custom_id="category_select",
                    options=[
                        disnake.SelectOption(label="Streaming", value="streaming", emoji=emoji.play),
                        disnake.SelectOption(label="Gaming", value="gaming", emoji=emoji.controller),
                    ],
                    min_values=1,
                    max_values=1
                ),
                description="Selecione se é um serviço de Streaming ou Gaming.",
            ),
        ]
        super().__init__(title="Configurar Live Stock", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        service_name = inter.text_values["service_name"]
        gen_count_str = inter.text_values["gen_count"]
        interval_str = inter.text_values["interval_hours"]

        # Validate gen count
        try:
            gen_count = int(gen_count_str)
            if gen_count < 1:
                gen_count = 1
            elif gen_count > 5:
                gen_count = 5
        except:
            gen_count = 1

        # Validate interval
        try:
            interval_hours = int(interval_str)
            if interval_hours < 6:
                interval_hours = 6
        except:
            interval_hours = 6

        # Get category
        category = "streaming"
        for component in inter.data.get("components", []):
            for child in component.get("components", []):
                if child.get("custom_id") == "category_select":
                    if "values" in child and child["values"]:
                        category = child["values"][0]

        # Get project key
        data = self.cog.systemgen.load()
        project_key = data.get("project_key") or "local"

        # Save config
        if "livestock" not in data:
            data["livestock"] = {}
        if "products" not in data["livestock"]:
            data["livestock"]["products"] = {}

        data["livestock"]["products"][self.product_id] = {
            "service": service_name,
            "category": category,
            "gen_count": gen_count,
            "interval_hours": interval_hours,
            "last_restock": None,
            "enabled": True
        }
        self.cog.systemgen.save(data)

        await inter.response.send_message(
            f"{emoji.correct} **Live Stock configurado!**\n\n"
            f"{emoji.link} **Serviço:** `{service_name}`\n"
            f"{emoji.folder} **Categoria:** `{category}`\n"
            f"{emoji.cart} **Gerações por ciclo:** `{gen_count}`\n"
            f"{emoji.clock if hasattr(emoji, 'clock') else '⏰'} **Intervalo:** `{interval_hours} horas`\n\n"
            f"-# O reabastecimento começará em breve!",
            ephemeral=True
        )

        # Start restock task
        self.cog.bot.loop.create_task(
            run_restock_task(self.cog, self.product_id, service_name, category, gen_count, interval_hours, project_key)
        )


# ==================== RESTOCK FUNCTIONS ====================

async def run_restock_task(cog, product_id: str, service: str, category: str, gen_count: int, interval_hours: int, project_key: str):
    """Run the restock task for a product"""
    from modules.loja.cart.stock_manager import StockManager
    
    while True:
        try:
            # Check if still enabled
            data = LyonGenManager().load()
            product_config = data.get("livestock", {}).get("products", {}).get(product_id)

            if not product_config or not product_config.get("enabled"):
                print(f"[LiveStock] Task for product {product_id} stopped - disabled or not found")
                break

            # Run generation
            credentials_list = []
            local_generation = LyonGenManager().generate(
                service,
                category,
                gen_count,
                source=f"livestock:{product_id}",
            )
            if local_generation.get("ok"):
                credentials_list.extend(local_generation.get("items", []))
            else:
                print(f"[LiveStock] Local generation skipped: {local_generation.get('reason')}")

            for _ in range(0):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{cog.api_url}/scrape-project",
                            headers={"x-project-key": project_key},
                            json={
                                "service": service,
                                "category": category,
                                "threads": 1,
                                "timeout": 300000
                            },
                            timeout=aiohttp.ClientTimeout(total=400)
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                credentials = result.get("credentials", [])
                                if isinstance(credentials, dict):
                                    for email, password in credentials.items():
                                        credentials_list.append(f"{email}:{password}")
                                elif isinstance(credentials, list):
                                    for c in credentials:
                                        credentials_list.append(f"{c.get('email')}:{c.get('password')}")
                except Exception as gen_err:
                    print(f"[LiveStock] Generation error: {gen_err}")

            # Add to product stock using StockManager
            if credentials_list:
                # Get product from MongoDB to find the first campo_id
                products = db.get_document("loja_products") or {}
                product = products.get(product_id, {})
                product_name = product.get("name", product_id)
                campos = product.get("campos", {})
                
                # Use the first campo_id if exists
                if campos:
                    campo_id = list(campos.keys())[0]
                    StockManager.add_stock_items(product_id, campo_id, credentials_list)
                    print(f"[LiveStock] Added {len(credentials_list)} items to product {product_id}, campo {campo_id}")
                    
                    # Send DM notification if enabled
                    data = LyonGenManager().load()
                    livestock = data.get("livestock", {})
                    if livestock.get("dm_notifications", False):
                        integrated_user_id = data.get("integrated_user_id")
                        if integrated_user_id and hasattr(cog, 'bot'):
                            try:
                                user = await cog.bot.fetch_user(int(integrated_user_id))
                                if user:
                                    await user.send(
                                        f"📦 **Live Stock - Estoque Adicionado!**\n\n"
                                        f"**Produto:** `{product_name}`\n"
                                        f"**Contas adicionadas:** `{len(credentials_list)}`\n"
                                        f"**Serviço:** `{service}`\n"
                                        f"**Categoria:** `{category}`\n\n"
                                        f"-# Próximo restock em {interval_hours} horas"
                                    )
                                    print(f"[LiveStock] DM notification sent to user {integrated_user_id}")
                            except Exception as dm_err:
                                print(f"[LiveStock] Failed to send DM notification: {dm_err}")

                # Update last restock time
                data = LyonGenManager().load()
                if "livestock" in data and "products" in data["livestock"] and product_id in data["livestock"]["products"]:
                    data["livestock"]["products"][product_id]["last_restock"] = disnake.utils.utcnow().isoformat()
                    LyonGenManager().save(data)

            # Wait for next interval
            print(f"[LiveStock] Waiting {interval_hours} hours for next restock of product {product_id}")
            await asyncio.sleep(interval_hours * 3600)

        except Exception as e:
            print(f"[LiveStock] Error in restock task for product {product_id}: {e}")
            await asyncio.sleep(3600)  # Wait 1 hour on error


class LiveStockMonitor(commands.Cog):
    """Monitor Live Stock configurations and manage restock tasks"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_url = "https://loopgen.squareweb.app"
        self.systemgen = LyonGenManager()
        self.active_tasks = {}  # Track active restock tasks: product_id -> task
    
    def cog_unload(self):
        self.monitor_task.cancel()
    
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.monitor_task.is_running():
            self.monitor_task.start()
        print("[LiveStock Monitor] Starting...")
        await self._check_and_start_restocks()
    
    @tasks.loop(minutes=1)
    async def monitor_task(self):
        """Check every minute for products that need restock"""
        await self._check_and_start_restocks()
    
    @monitor_task.before_loop
    async def before_monitor(self):
        await self.bot.wait_until_ready()
    
    async def _check_and_start_restocks(self):
        """Check all configured Live Stock products and start tasks if needed"""
        try:
            data = self.systemgen.load()
            if not data:
                return
            
            # Check if the extension is enabled first
            extension_enabled = data.get("enabled", True)
            if not extension_enabled:
                # If extension is disabled, cancel all active tasks and don't start new ones
                for product_id, task in list(self.active_tasks.items()):
                    task.cancel()
                    del self.active_tasks[product_id]
                return
            
            livestock = data.get("livestock", {})
            products_config = livestock.get("products", {})
            project_key = data.get("project_key")
            
            if not project_key:
                return
            
            for product_id, config in products_config.items():
                if not config.get("enabled"):
                    # Cancel task if disabled
                    if product_id in self.active_tasks:
                        self.active_tasks[product_id].cancel()
                        del self.active_tasks[product_id]
                        print(f"[LiveStock Monitor] Cancelled task for product {product_id}")
                    continue
                
                # Check if task already running
                if product_id in self.active_tasks:
                    task = self.active_tasks[product_id]
                    if not task.done():
                        continue  # Task still running
                
                # Check if it's time to restock
                last_restock = config.get("last_restock")
                interval_hours = config.get("interval_hours", 6)
                
                should_start = False
                
                if not last_restock:
                    # Never restocked, start now
                    should_start = True
                else:
                    # Check if enough time has passed
                    try:
                        from datetime import datetime
                        last_time = datetime.fromisoformat(last_restock.replace("Z", "+00:00"))
                        now = disnake.utils.utcnow()
                        hours_passed = (now - last_time).total_seconds() / 3600
                        
                        if hours_passed >= interval_hours:
                            should_start = True
                        elif hours_passed >= interval_hours - 0.1:  # Within 6 minutes of next restock
                            print(f"[LiveStock Monitor] Product {product_id} restock coming up in {int((interval_hours - hours_passed) * 60)} minutes")
                    except Exception as parse_err:
                        print(f"[LiveStock Monitor] Error parsing date for {product_id}: {parse_err}")
                        should_start = True
                
                if should_start:
                    service = config.get("service", "netflix")
                    category = config.get("category", "streaming")
                    gen_count = config.get("gen_count", 1)
                    
                    print(f"[LiveStock Monitor] Starting restock task for product {product_id}")
                    
                    # Create a temporary cog-like object for the function
                    class CogProxy:
                        def __init__(self, api_url, bot):
                            self.api_url = api_url
                            self.bot = bot
                    
                    cog_proxy = CogProxy(self.api_url, self.bot)
                    
                    task = self.bot.loop.create_task(
                        run_restock_task(cog_proxy, product_id, service, category, gen_count, interval_hours, project_key)
                    )
                    self.active_tasks[product_id] = task
        
        except Exception as e:
            print(f"[LiveStock Monitor] Error in check: {e}")


def setup(bot: commands.Bot):
    # Import tasks extension
    from disnake.ext import tasks
    bot.add_cog(ExtensionsPanel(bot))
    bot.add_cog(LiveStockMonitor(bot))

