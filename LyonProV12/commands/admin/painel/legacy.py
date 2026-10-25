import disnake
from disnake.ext import commands

from datetime import datetime
from functions.emoji import emoji
from functions.database import database as db
from functions.perms import perms
from functions.email_utils import owner_email_is_verified
from functions.message import message, embed_message
from functions.utils import utils
from functions.plan import should_enable_panel_button
from functions.user_permissions import user_permissions
import aiohttp
import io
import os
import pathlib

class PainelCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _can_user_access_panel(self, user_id: str, panel_id: str) -> bool:
        """Verifica se um usuário pode acessar um painel específico"""
        # Owner sempre pode acessar tudo
        if str(user_id) == perms.get_owner_id():
            return True
        if owner_email_is_verified(user_id):
            return True
        
        # Verificar se usuário tem permissão geral
        if str(user_id) not in perms.get_all_users():
            return False
        
        # Verificar permissões específicas do painel
        return user_permissions.can_access_panel(str(user_id), panel_id)

    def _get_salutation(self) -> str:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "bom dia! ☀️"
        elif 12 <= hour < 18:
            return "boa tarde! 🌞"
        else:
            return "boa noite! 🌙"

    def PainelComponents(self, inter: disnake.MessageInteraction, primary_color_hex: str = None, button_states: dict = None) -> list[disnake.ui.Container]:
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        # Usar estados pré-calculados dos botões se fornecidos
        if button_states is None:
            button_states = {
                "loja": should_enable_panel_button("loja"),
                "ticket": should_enable_panel_button("ticket"),
                "cloud": should_enable_panel_button("cloud"),
                "personalizacao": should_enable_panel_button("personalizacao"),
                "automacoes": should_enable_panel_button("automacoes"),
                "protection": should_enable_panel_button("protection"),
                "sorteios": should_enable_panel_button("sorteios"),
                "configuracoes": should_enable_panel_button("configuracoes"),
                "boasvindas": True,
                "giftcard": True,
                "sistemaai": True,
                "filasapostas": True,
                "moderacao": True,
                "verificacao": True,
                "gifs": True,
                "ranking": True,
                "stock": True,
                "feedback": True,
            }

        # Verificar modo de exibição do painel
        panel_mode_config = db.get_document("custom_panel_mode") or {}
        panel_mode = panel_mode_config.get("mode", "buttons")

        def _emoji(key, default=None):
            return getattr(emoji, key, None) or getattr(emoji, "commands", None) or default

        # Mostrar apenas os sistemas novos no select menu
        select_options = []
        select_options.append(disnake.SelectOption(label="Economia", value="Painel_Economia", emoji=emoji.coin if hasattr(emoji, 'coin') else emoji.dollar, description="Gerencie o sistema de economia"))
        select_options.append(disnake.SelectOption(label="Comunidade", value="Painel_Comunidade", emoji=emoji.members if hasattr(emoji, 'members') else emoji.users, description="Recursos de comunidade"))
        select_options.append(disnake.SelectOption(label="Ferramentas", value="Painel_Ferramentas", emoji=emoji.hammer if hasattr(emoji, 'hammer') else emoji.wand, description="Ferramentas e utilitários"))
        select_options.append(disnake.SelectOption(label="Parcerias", value="Painel_Parcerias", emoji=emoji.partner if hasattr(emoji, 'partner') else emoji.link, description="Parcerias automáticas"))
        select_options.append(disnake.SelectOption(label="Apostado Free Fire", value="Painel_ApostadoFF", emoji=emoji.Uzi, description="Gerencie o sistema de apostas Free Fire"))
        # Novos sistemas integrados do Pro_completinho
        select_options.append(disnake.SelectOption(label="Boas Vindas", value="Painel_BoasVindas", emoji=_emoji('members', '👋'), description="Configure mensagens de boas-vindas"))
        select_options.append(disnake.SelectOption(label="Gift Cards", value="Painel_GiftCard", emoji=_emoji('gift', '🎁'), description="Gerencie gift cards"))
        select_options.append(disnake.SelectOption(label="Sistema IA", value="Painel_SistemaIA", emoji=_emoji('robot', '🤖'), description="Configure sua inteligência artificial"))
        select_options.append(disnake.SelectOption(label="Moderação", value="Painel_Moderacao", emoji=_emoji('shield', '🛡️'), description="Ferramentas de moderação"))
        select_options.append(disnake.SelectOption(label="Verificação", value="Painel_Verificacao", emoji=_emoji('lock', '🔒'), description="Sistema de verificação captcha"))
        select_options.append(disnake.SelectOption(label="GIFs Automáticos", value="Painel_GIFs", emoji=_emoji('image', '📡'), description="Configure GIFs automáticos"))
        select_options.append(disnake.SelectOption(label="Ranking", value="Painel_Ranking", emoji=_emoji('trophy', '🏆'), description="Ranking de compradores"))
        select_options.append(disnake.SelectOption(label="Aviso Stock", value="Painel_Stock", emoji=_emoji('cardbox', '📦'), description="Sistema de aviso de stock"))
        select_options.append(disnake.SelectOption(label="Monitor Feedback", value="Painel_Feedback", emoji=_emoji('speech', '📋'), description="Monitore feedbacks"))

        if panel_mode == "select":
            return [
                disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.Lyon}\nOlá senhor(a) **{inter.user.name}**, {self._get_salutation()} \n-# Aqui você pode **configurar** e **personalizar** as funcionalidades do seu **Lyon Pro**."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Selecione uma opção do painel",
                        custom_id="Painel_Select",
                        options=select_options if select_options else [
                            disnake.SelectOption(label="Nenhuma opção disponível", value="none", emoji=emoji.wrong)
                        ]
                    )
                ),
                **container_kwargs,
            ),
            ]
        else:
            # Modo Botões (padrão)
            return [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(f"# {emoji.Lyon}\nOlá senhor(a) **{inter.user.name}**, {self._get_salutation()} \n-# Aqui você pode **configurar** e **personalizar** as funcionalidades do seu **Lyon Pro**."),
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Gerenciar Loja", style=disnake.ButtonStyle.grey, emoji=emoji.cart, custom_id="Painel_Loja", disabled=not button_states["loja"]),
                        disnake.ui.Button(label="Gerenciar Ticket", style=disnake.ButtonStyle.grey, emoji=emoji.ticket, custom_id="Painel_Ticket", disabled=not button_states["ticket"]),
                        disnake.ui.Button(label="Lyon Cloud", style=disnake.ButtonStyle.grey, emoji=emoji.cloud, custom_id="Painel_Cloud", disabled=not button_states["cloud"]),
                    ),
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Rendimentos Lyon", style=disnake.ButtonStyle.grey, emoji=emoji.chart, custom_id="Painel_Rendimentos", disabled=not button_states["ticket"]),
                        disnake.ui.Button(label="Themes", style=disnake.ButtonStyle.grey, emoji=emoji.wand, custom_id="Painel_Personalizacao", disabled=not button_states["personalizacao"]),
                        disnake.ui.Button(label="Automações", style=disnake.ButtonStyle.grey, emoji=emoji.reload, custom_id="Painel_Automações", disabled=not button_states["automacoes"]),
                    ),
                    # Novos sistemas integrados do Pro_completinho - Grupo 1
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Boas Vindas", style=disnake.ButtonStyle.grey, emoji=emoji.members if hasattr(emoji, 'members') else "👋", custom_id="Painel_BoasVindas", disabled=not button_states["boasvindas"]),
                        disnake.ui.Button(label="Gift Cards", style=disnake.ButtonStyle.grey, emoji=emoji.gift if hasattr(emoji, 'gift') else "🎁", custom_id="Painel_GiftCard", disabled=not button_states["giftcard"]),
                        disnake.ui.Button(label="Sistema IA", style=disnake.ButtonStyle.grey, emoji=emoji.robot if hasattr(emoji, 'robot') else "🤖", custom_id="Painel_SistemaIA", disabled=not button_states["sistemaai"]),
                    ),
                    # Novos sistemas integrados do Pro_completinho - Grupo 2
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Moderação", style=disnake.ButtonStyle.grey, emoji="🛡️", custom_id="Painel_Moderacao", disabled=not button_states["moderacao"]),
                        disnake.ui.Button(label="Verificação", style=disnake.ButtonStyle.grey, emoji="🔒", custom_id="Painel_Verificacao", disabled=not button_states["verificacao"]),
                    ),
                    # Novos sistemas integrados do Pro_completinho - Grupo 3
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="GIFs Auto", style=disnake.ButtonStyle.grey, emoji="📡", custom_id="Painel_GIFs", disabled=not button_states["gifs"]),
                        disnake.ui.Button(label="Ranking", style=disnake.ButtonStyle.grey, emoji="🏆", custom_id="Painel_Ranking", disabled=not button_states["ranking"]),
                        disnake.ui.Button(label="Stock", style=disnake.ButtonStyle.grey, emoji="📦", custom_id="Painel_Stock", disabled=not button_states["stock"]),
                    ),
                    # Novos sistemas integrados do Pro_completinho - Grupo 4
                    disnake.ui.ActionRow(
                        disnake.ui.Button(label="Feedback", style=disnake.ButtonStyle.grey, emoji="📋", custom_id="Painel_Feedback", disabled=not button_states["feedback"]),
                    ),
                    disnake.ui.ActionRow(
                        disnake.ui.StringSelect(
                            placeholder="Selecione uma opção do painel",
                            custom_id="Painel_Select",
                            options=select_options if select_options else [
                                disnake.SelectOption(label="Nenhuma opção disponível", value="none", emoji=emoji.wrong)
                            ]
                        )
                    ),
                    **container_kwargs,
                ),
                # disnake.ui.ActionRow(
                #     disnake.ui.Button(label="Acesse a Dashboard", style=disnake.ButtonStyle.grey, url="https://Lyonapplications.com.br"),
                # )
            ]

    def PainelEmbed(self, inter: disnake.MessageInteraction, primary_color_hex: str = None, button_states: dict = None):
        embed = disnake.Embed(
            title=f"Painel",
            description=f"Olá senhor(a) **{inter.user.name}**, {self._get_salutation()} \n-# Aqui você pode **configurar** e **personalizar** as funcionalidades do seu **Lyon Pro**.",
        )
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color
        
        # Usar estados pré-calculados dos botões se fornecidos
        if button_states is None:
            button_states = {
                "loja": should_enable_panel_button("loja"),
                "ticket": should_enable_panel_button("ticket"),
                "cloud": should_enable_panel_button("cloud"),
                "personalizacao": should_enable_panel_button("personalizacao"),
                "automacoes": should_enable_panel_button("automacoes"),
                "protection": should_enable_panel_button("protection"),
                "sorteios": should_enable_panel_button("sorteios"),
                "configuracoes": should_enable_panel_button("configuracoes"),
                "boasvindas": True,
                "giftcard": True,
                "sistemaai": True,
                "filasapostas": True,
                "moderacao": True,
                "verificacao": True,
                "gifs": True,
                "ranking": True,
                "stock": True,
                "feedback": True,
            }
        
        # Verificar modo de exibição do painel
        panel_mode_config = db.get_document("custom_panel_mode") or {}
        panel_mode = panel_mode_config.get("mode", "buttons")

        def _emoji(key, default):
            return getattr(emoji, key, default)

        select_options = []
        if button_states["loja"]:
            select_options.append(disnake.SelectOption(label="Gerenciar Loja", value="Painel_Loja", emoji=emoji.cart, description="Configure sua loja"))
        if button_states["ticket"]:
            select_options.append(disnake.SelectOption(label="Gerenciar Ticket", value="Painel_Ticket", emoji=emoji.ticket, description="Configure o sistema de tickets"))
        if button_states["cloud"]:
            select_options.append(disnake.SelectOption(label="Lyon Cloud", value="Painel_Cloud", emoji=emoji.cloud, description="Acesse o Lyon Cloud"))
        if button_states["ticket"]:
            select_options.append(disnake.SelectOption(label="Rendimentos Lyon", value="Painel_Rendimentos", emoji=emoji.chart, description="Veja seus rendimentos"))
        if button_states["personalizacao"]:
            select_options.append(disnake.SelectOption(label="Themes", value="Painel_Personalizacao", emoji=emoji.wand, description="Personalize o bot"))
        select_options.append(disnake.SelectOption(label="Economia", value="Painel_Economia", emoji=emoji.coin if hasattr(emoji, 'coin') else emoji.dollar, description="Gerencie o sistema de economia"))
        select_options.append(disnake.SelectOption(label="Comunidade", value="Painel_Comunidade", emoji=emoji.members if hasattr(emoji, 'members') else emoji.users, description="Recursos de comunidade"))
        select_options.append(disnake.SelectOption(label="Ferramentas", value="Painel_Ferramentas", emoji=emoji.hammer if hasattr(emoji, 'hammer') else emoji.wand, description="Ferramentas e utilitários"))
        select_options.append(disnake.SelectOption(label="Parcerias", value="Painel_Parcerias", emoji=emoji.partner if hasattr(emoji, 'partner') else emoji.link, description="Parcerias automáticas"))
        if button_states["automacoes"]:
            select_options.append(disnake.SelectOption(label="Automações", value="Painel_Automações", emoji=_emoji('reload', '🔄'), description="Configure automações"))
        if button_states["protection"]:
            select_options.append(disnake.SelectOption(label="Proteção Do Cliente", value="Painel_Protection", emoji=_emoji('shield', '🛡️'), description="Configure proteções"))
        if button_states["sorteios"]:
            select_options.append(disnake.SelectOption(label="Giveaways", value="Painel_Giveaways", emoji=_emoji('giveaway', '🎉'), description="Gerencie sorteios"))
        if button_states["configuracoes"]:
            select_options.append(disnake.SelectOption(label="Configurações", value="Painel_Configuracoes", emoji=_emoji('config', '⚙️'), description="Configurações gerais"))
        select_options.append(disnake.SelectOption(label="Apostado Free Fire", value="Painel_ApostadoFF", emoji=_emoji('Uzi', '🕹️'), description="Gerencie o sistema de apostas Free Fire"))
        # Novos sistemas integrados do Pro_completinho
        select_options.append(disnake.SelectOption(label="Boas Vindas", value="Painel_BoasVindas", emoji=_emoji('members', '👋'), description="Configure mensagens de boas-vindas"))
        select_options.append(disnake.SelectOption(label="Gift Cards", value="Painel_GiftCard", emoji=_emoji('gift', '🎁'), description="Gerencie gift cards"))
        select_options.append(disnake.SelectOption(label="Sistema IA", value="Painel_SistemaIA", emoji=_emoji('robot', '🤖'), description="Configure sua inteligência artificial"))
        select_options.append(disnake.SelectOption(label="Moderação", value="Painel_Moderacao", emoji=_emoji('shield', '🛡️'), description="Ferramentas de moderação"))
        select_options.append(disnake.SelectOption(label="Verificação", value="Painel_Verificacao", emoji=_emoji('lock', '🔒'), description="Sistema de verificação captcha"))
        select_options.append(disnake.SelectOption(label="GIFs Automáticos", value="Painel_GIFs", emoji=_emoji('image', '📡'), description="Configure GIFs automáticos"))
        select_options.append(disnake.SelectOption(label="Ranking", value="Painel_Ranking", emoji=_emoji('trophy', '🏆'), description="Ranking de compradores"))
        select_options.append(disnake.SelectOption(label="Aviso Stock", value="Painel_Stock", emoji=_emoji('cardbox', '📦'), description="Sistema de aviso de stock"))
        select_options.append(disnake.SelectOption(label="Monitor Feedback", value="Painel_Feedback", emoji=_emoji('speech', '📋'), description="Monitore feedbacks"))

        if panel_mode == "select":
            components = [
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Selecione uma opção do painel",
                        custom_id="Painel_Select",
                        options=select_options if select_options else [
                            disnake.SelectOption(label="Nenhuma opção disponível", value="none", emoji=emoji.wrong)
                        ]
                    )
                )
            ]
        else:
            components = [
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Gerenciar Loja", style=disnake.ButtonStyle.grey, emoji=emoji.cart, custom_id="Painel_Loja", disabled=not button_states["loja"]),
                    disnake.ui.Button(label="Gerenciar Ticket", style=disnake.ButtonStyle.grey, emoji=emoji.ticket, custom_id="Painel_Ticket", disabled=not button_states["ticket"]),
                    disnake.ui.Button(label="Lyon Cloud", style=disnake.ButtonStyle.grey, emoji=emoji.cloud, custom_id="Painel_Cloud", disabled=not button_states["cloud"]),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Rendimentos Lyon", style=disnake.ButtonStyle.grey, emoji=emoji.chart, custom_id="Painel_Rendimentos", disabled=not button_states["ticket"]),
                    disnake.ui.Button(label="Themes", style=disnake.ButtonStyle.grey, emoji=emoji.wand, custom_id="Painel_Personalizacao", disabled=not button_states["personalizacao"]),
                    disnake.ui.Button(label="Automações", style=disnake.ButtonStyle.grey, emoji=emoji.reload, custom_id="Painel_Automações", disabled=not button_states["automacoes"]),
                ),
                # Novos sistemas integrados do Pro_completinho - Grupo 1
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Boas Vindas", style=disnake.ButtonStyle.grey, emoji=_emoji('members', '👋'), custom_id="Painel_BoasVindas", disabled=not button_states["boasvindas"]),
                    disnake.ui.Button(label="Gift Cards", style=disnake.ButtonStyle.grey, emoji=_emoji('gift', '🎁'), custom_id="Painel_GiftCard", disabled=not button_states["giftcard"]),
                    disnake.ui.Button(label="Sistema IA", style=disnake.ButtonStyle.grey, emoji=_emoji('robot', '🤖'), custom_id="Painel_SistemaIA", disabled=not button_states["sistemaai"]),
                ),
                # Novos sistemas integrados do Pro_completinho - Grupo 2
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Moderação", style=disnake.ButtonStyle.grey, emoji=_emoji('shield', '🛡️'), custom_id="Painel_Moderacao", disabled=not button_states["moderacao"]),
                    disnake.ui.Button(label="Verificação", style=disnake.ButtonStyle.grey, emoji=_emoji('lock', '🔒'), custom_id="Painel_Verificacao", disabled=not button_states["verificacao"]),
                ),
                # Novos sistemas integrados do Pro_completinho - Grupo 3
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="GIFs Auto", style=disnake.ButtonStyle.grey, emoji=_emoji('image', '📡'), custom_id="Painel_GIFs", disabled=not button_states["gifs"]),
                    disnake.ui.Button(label="Ranking", style=disnake.ButtonStyle.grey, emoji=_emoji('trophy', '🏆'), custom_id="Painel_Ranking", disabled=not button_states["ranking"]),
                    disnake.ui.Button(label="Stock", style=disnake.ButtonStyle.grey, emoji=_emoji('cardbox', '📦'), custom_id="Painel_Stock", disabled=not button_states["stock"]),
                ),
                # Novos sistemas integrados do Pro_completinho - Grupo 4
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Feedback", style=disnake.ButtonStyle.grey, emoji=_emoji('speech', '📋'), custom_id="Painel_Feedback", disabled=not button_states["feedback"]),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        placeholder="Selecione uma opção do painel",
                        custom_id="Painel_Select",
                        options=select_options if select_options else [
                            disnake.SelectOption(label="Nenhuma opção disponível", value="none", emoji=emoji.wrong)
                        ]
                    )
                ),
            ]

        # embed.set_footer(text=inter.guild.name, icon_url=inter.guild.icon.url if inter.guild.icon else None)
        return embed, components

    @commands.slash_command(
        name="painel",
        description="Abre o painel de controle do bot.",
        guild_ids=utils.obter_guild_ids(),
    )
    async def painel(self, inter: disnake.ApplicationCommandInteraction):
        # Buscar dados do banco uma única vez
        mode_data = db.get_document("custom_mode")
        mode = mode_data.get("mode") if mode_data else "components"
        
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary") if colors else None

        if mode == "embed":
            await embed_message.wait(inter, send=True)
        else:
            await message.wait(inter, send=True)

        if not await perms.check(inter.user.id):
            if mode == "embed":
                await embed_message.error(inter, "Você não tem permissão para usar este comando", send=False)
            else:
                await message.error(inter, "Você não tem permissão para usar este comando", send=False)
            return

        # Pré-calcular estados dos botões uma única vez
        button_states = {
            "loja": should_enable_panel_button("loja"),
            "ticket": should_enable_panel_button("ticket"),
            "cloud": should_enable_panel_button("cloud"),
            "personalizacao": should_enable_panel_button("personalizacao"),
            "automacoes": should_enable_panel_button("automacoes"),
            "protection": should_enable_panel_button("protection"),
            "sorteios": should_enable_panel_button("sorteios"),
            "configuracoes": should_enable_panel_button("configuracoes"),
        }

        if mode == "embed":
            embed, components = self.PainelEmbed(inter, primary_color_hex, button_states)
            await inter.edit_original_response(content=None, embed=embed, components=components)
        else:
            # Tentar usar imagem local primeiro, depois fallback para URL
            base_dir = pathlib.Path(__file__).resolve().parent.parent.parent
            image_path = base_dir / "database" / "emojis" / "assets" / "painellyonapplications.png"
            image_url = "https://i.ibb.co/tw2k3MqB/Picsart-26-08-15-14-57-50-031.jpg"
            
            print(f"[PAINEL] Tentando carregar imagem de: {image_path}")
            print(f"[PAINEL] Arquivo existe: {image_path.exists()}")
            
            try:
                # Tentar usar arquivo local
                if image_path.exists():
                    print(f"[PAINEL] ✅ Usando imagem local")
                    file = disnake.File(str(image_path), filename="painellyonapplications.png")
                    panel_embed, _ = self.PainelEmbed(inter, primary_color_hex, button_states)
                    panel_embed.set_image(url="attachment://painellyonapplications.png")
                    await inter.edit_original_response(
                        file=file,
                        embed=panel_embed,
                        components=self.PainelComponents(inter, primary_color_hex, button_states),
                    )
                    return
                
                # Se não existir localmente, baixar da URL
                print(f"[PAINEL] 📥 Baixando imagem da URL")
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            image_buffer = io.BytesIO(await resp.read())
                            file = disnake.File(image_buffer, filename="painellyonapplications.png")
                            panel_embed, _ = self.PainelEmbed(inter, primary_color_hex, button_states)
                            panel_embed.set_image(url="attachment://painellyonapplications.png")
                            await inter.edit_original_response(
                                file=file,
                                embed=panel_embed,
                                components=self.PainelComponents(inter, primary_color_hex, button_states),
                            )
                        else:
                            # Fallback sem imagem
                            print(f"[PAINEL] ❌ Erro ao baixar: status {resp.status}")
                            panel_embed, _ = self.PainelEmbed(inter, primary_color_hex, button_states)
                            await inter.edit_original_response(
                                embed=panel_embed,
                                components=self.PainelComponents(inter, primary_color_hex, button_states),
                            )
            except Exception as e:
                print(f"[PAINEL] ❌ Erro ao carregar imagem: {e}")
                import traceback
                traceback.print_exc()
                panel_embed, _ = self.PainelEmbed(inter, primary_color_hex, button_states)
                await inter.edit_original_response(
                    embed=panel_embed,
                    components=self.PainelComponents(inter, primary_color_hex, button_states),
                )

    @commands.Cog.listener("on_message_interaction")
    async def Painel_Button_Listener(self, inter: disnake.MessageInteraction):
        if not inter.component.custom_id.startswith("Painel"):
            return
        
        # Verificar permissão para acessar o painel específico
        panel_id = inter.component.custom_id
        if panel_id != "PainelInicial" and not self._can_user_access_panel(inter.user.id, panel_id):
            await inter.response.send_message(
                f"{emoji.wrong} Você não tem permissão para acessar este painel.",
                ephemeral=True
            )
            return

        if inter.component.custom_id == "PainelInicial":
            # Buscar dados do banco uma única vez
            mode_data = db.get_document("custom_mode")
            mode = mode_data.get("mode") if mode_data else "components"
            
            colors = db.get_document("custom_colors")
            primary_color_hex = colors.get("primary") if colors else None

            if mode == "embed":
                await embed_message.wait(inter)
            else:
                await message.wait(inter)

            # Pré-calcular estados dos botões uma única vez
            button_states = {
                "loja": should_enable_panel_button("loja"),
                "ticket": should_enable_panel_button("ticket"),
                "cloud": should_enable_panel_button("cloud"),
                "personalizacao": should_enable_panel_button("personalizacao"),
                "automacoes": should_enable_panel_button("automacoes"),
                "protection": should_enable_panel_button("protection"),
                "sorteios": should_enable_panel_button("sorteios"),
                "configuracoes": should_enable_panel_button("configuracoes"),
            }

            if mode == "embed":
                embed, components = self.PainelEmbed(inter, primary_color_hex, button_states)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await inter.edit_original_message(
                    components=self.PainelComponents(inter, primary_color_hex, button_states),
                )
        elif inter.component.custom_id == "Painel_Protection":
            # Verificar se é owner
            config = db.obter("config.json")
            owner_id = config.get("bot", {}).get("owner")
            
            if str(inter.user.id) != str(owner_id) and not owner_email_is_verified(inter.user.id):
                await inter.response.send_message(
                    f"{emoji.wrong} Apenas o dono do bot pode acessar esta funcionalidade.",
                    ephemeral=True
                )
                return
            
            protection_cog = self.bot.get_cog("ProtectionCog")
            if protection_cog:
                await protection_cog.display_protection_panel(inter)
        elif inter.component.custom_id == "Painel_Automacoes":
            automations_cog = self.bot.get_cog("AutomationModulesCog")
            if automations_cog:
                await automations_cog.display_automations_panel(inter)
        elif inter.component.custom_id == "Painel_Economia":
            economia_cog = self.bot.get_cog("Economia")
            if economia_cog:
                await economia_cog.display_economia_panel(inter)
        elif inter.component.custom_id == "Painel_Comunidade":
            comunidade_cog = self.bot.get_cog("Comunidade")
            if comunidade_cog:
                await comunidade_cog.display_comunidade_panel(inter)
        elif inter.component.custom_id == "Painel_Ferramentas":
            ferramentas_cog = self.bot.get_cog("Ferramentas")
            if ferramentas_cog:
                await ferramentas_cog.display_ferramentas_panel(inter)
        elif inter.component.custom_id == "Painel_Parcerias":
            parcerias_cog = self.bot.get_cog("Parcerias")
            if parcerias_cog:
                await parcerias_cog.display_parcerias_panel(inter)
        elif inter.component.custom_id == "Painel_Ticket":
            ticket_cog = self.bot.get_cog("TicketConfigCog")
            if ticket_cog:
                await ticket_cog.display_ticket_panel(inter)
        elif inter.component.custom_id == "Painel_ApostadoFF":
            apostado_cog = self.bot.get_cog("ApostadoFreeFire")
            if apostado_cog:
                await apostado_cog.display_apostado_panel(inter)
        elif inter.component.custom_id == "Painel_Sorteios":
            giveaways_cog = self.bot.get_cog("Giveaways")
            if giveaways_cog:
                await giveaways_cog.display_giveaways_panel(inter)
        elif inter.component.custom_id == "Painel_Cloud":
            # Verificar se é o owner
            config = db.obter("config.json") or {}
            owner_id = config.get("bot", {}).get("owner")
            
            if str(inter.user.id) != str(owner_id) and not owner_email_is_verified(inter.user.id):
                await inter.response.send_message(
                    f"{emoji.wrong} Apenas o dono do bot pode acessar esta funcionalidade.",
                    ephemeral=True
                )
                return
            
            cloud_cog = self.bot.get_cog("Cloud")
            if cloud_cog:
                await cloud_cog.display_cloud_panel(inter)
        elif inter.component.custom_id == "Painel_Rendimentos":
            rendimentos_cog = self.bot.get_cog("RendimentosLyon")
            if rendimentos_cog:
                # Buscar dados do banco uma única vez
                mode_data = db.get_document("custom_mode")
                mode = mode_data.get("mode") if mode_data else "components"
                
                if mode == "embed":
                    await embed_message.wait(inter)
                else:
                    await message.wait(inter)
                
                panel_data = rendimentos_cog.panel(inter)
                if mode == "embed":
                    embed, components = panel_data
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await inter.edit_original_message(**panel_data)
        
        # Novos sistemas integrados do Pro_completinho
        elif inter.component.custom_id == "Painel_BoasVindas":
            boasvindas_cog = self.bot.get_cog("BoasVindasPanel")
            if boasvindas_cog:
                embed, components = boasvindas_cog.display_boasvindas_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
        
        elif inter.component.custom_id == "Painel_GiftCard":
            giftcard_cog = self.bot.get_cog("GiftCardPanel")
            if giftcard_cog:
                embed, components = giftcard_cog.display_giftcard_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
        
        elif inter.component.custom_id == "Painel_SistemaIA":
            sistemaai_cog = self.bot.get_cog("SistemaIAPanel")
            if sistemaai_cog:
                embed, components = sistemaai_cog.display_sistemaai_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
        
        elif inter.component.custom_id == "Painel_FilasApostas":
            apostado_cog = self.bot.get_cog("ApostadoFreeFire")
            if apostado_cog:
                components = apostado_cog.display_apostado_panel(inter)
                await inter.edit_original_message(content=None, embed=None, components=components, flags=disnake.MessageFlags(is_components_v2=True))
        
        elif inter.component.custom_id == "Painel_Moderacao":
            moderacao_cog = self.bot.get_cog("ModeradorPanel")
            if moderacao_cog:
                embed, components = moderacao_cog.display_moderacao_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
        
        elif inter.component.custom_id == "Painel_Verificacao":
            verificacao_cog = self.bot.get_cog("VerificacaoPanel")
            if verificacao_cog:
                embed, components = verificacao_cog.display_verificacao_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
        
        elif inter.component.custom_id == "Painel_GIFs":
            gifs_cog = self.bot.get_cog("GIFsPanel")
            if gifs_cog:
                embed, components = gifs_cog.display_gifs_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
        
        elif inter.component.custom_id == "Painel_Ranking":
            ranking_cog = self.bot.get_cog("RanksPanel")
            if ranking_cog:
                embed, components = ranking_cog.display_ranking_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
        
        elif inter.component.custom_id == "Painel_Stock":
            stock_cog = self.bot.get_cog("StockPanel")
            if stock_cog:
                embed, components = stock_cog.display_stock_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
        
        elif inter.component.custom_id == "Painel_Feedback":
            feedback_cog = self.bot.get_cog("FeedbackPanel")
            if feedback_cog:
                embed, components = feedback_cog.display_feedback_panel(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)

    @commands.Cog.listener("on_message_interaction")
    async def Painel_Dropdown_Listener(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Painel_Select":
            choice = inter.values[0]
            
            if choice == "none":
                return
            
            # Verificar permissão para acessar o painel específico
            if not self._can_user_access_panel(inter.user.id, choice):
                await inter.response.send_message(
                    f"{emoji.wrong} Você não tem permissão para acessar este painel.",
                    ephemeral=True
                )
                return
            
            # Processar cada opção diretamente
            if choice == "Painel_Loja":
                loja_cog = self.bot.get_cog("Loja")
                if loja_cog:
                    mode = db.get_document("custom_mode").get("mode")
                    msg_handler = embed_message if mode == "embed" else message
                    await msg_handler.wait(inter, send=False)

                    panel_data = loja_cog.panel(inter)
                    if "embed" in panel_data:
                        await inter.edit_original_message(content=None, **panel_data)
                    else:
                        await inter.edit_original_message(**panel_data, flags=disnake.MessageFlags(is_components_v2=True))
            
            elif choice == "Painel_Ticket":
                ticket_cog = self.bot.get_cog("TicketConfigCog")
                if ticket_cog:
                    await ticket_cog.display_ticket_panel(inter)
            
            elif choice == "Painel_Cloud":
                # Verificar se é o owner
                config = db.obter("config.json") or {}
                owner_id = config.get("bot", {}).get("owner")
                
                if str(inter.user.id) != str(owner_id) and not owner_email_is_verified(inter.user.id):
                    await inter.response.send_message(
                        f"{emoji.wrong} Apenas o dono do bot pode acessar esta funcionalidade.",
                        ephemeral=True
                    )
                    return
                
                cloud_cog = self.bot.get_cog("Cloud")
                if cloud_cog:
                    await cloud_cog.display_cloud_panel(inter)
            
            elif choice == "Painel_Rendimentos":
                rendimentos_cog = self.bot.get_cog("RendimentosLyon")
                if rendimentos_cog:
                    mode_data = db.get_document("custom_mode")
                    mode = mode_data.get("mode") if mode_data else "components"
                    
                    if mode == "embed":
                        await embed_message.wait(inter)
                    else:
                        await message.wait(inter)
                    
                    panel_data = rendimentos_cog.panel(inter)
                    if mode == "embed":
                        embed, components = panel_data
                        await inter.edit_original_message(content=None, embed=embed, components=components)
                    else:
                        await inter.edit_original_message(**panel_data)
            
            elif choice == "Painel_Personalizacao":
                personalizacao_cog = self.bot.get_cog("Personalizacao")
                if personalizacao_cog:
                    mode_data = db.get_document("custom_mode")
                    mode = mode_data.get("mode") if mode_data else "components"
                    
                    if mode == "embed":
                        await embed_message.wait(inter, send=False)
                        embed, components = personalizacao_cog.personalizacao_embed(inter)
                        await inter.edit_original_message(content=None, embed=embed, components=components)
                    else:
                        await message.wait(inter, send=False)
                        await inter.edit_original_message(components=personalizacao_cog.personalizacao_components(inter))
            
            elif choice == "Painel_Automacoes":
                automations_cog = self.bot.get_cog("AutomationModulesCog")
                if automations_cog:
                    await automations_cog.display_automations_panel(inter)
            elif choice == "Painel_Economia":
                economia_cog = self.bot.get_cog("Economia")
                if economia_cog:
                    await economia_cog.display_economia_panel(inter)
            elif choice == "Painel_Comunidade":
                comunidade_cog = self.bot.get_cog("Comunidade")
                if comunidade_cog:
                    await comunidade_cog.display_comunidade_panel(inter)
            elif choice == "Painel_Ferramentas":
                ferramentas_cog = self.bot.get_cog("Ferramentas")
                if ferramentas_cog:
                    await ferramentas_cog.display_ferramentas_panel(inter)
            
            # Novos sistemas integrados do Pro_completinho
            elif choice == "Painel_BoasVindas":
                boasvindas_cog = self.bot.get_cog("BoasVindasPanel")
                if boasvindas_cog:
                    embed, components = boasvindas_cog.display_boasvindas_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            
            elif choice == "Painel_GiftCard":
                giftcard_cog = self.bot.get_cog("GiftCardPanel")
                if giftcard_cog:
                    embed, components = giftcard_cog.display_giftcard_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            
            elif choice == "Painel_SistemaIA":
                sistemaai_cog = self.bot.get_cog("SistemaIAPanel")
                if sistemaai_cog:
                    embed, components = sistemaai_cog.display_sistemaai_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            
            elif choice == "Painel_FilasApostas":
                apostado_cog = self.bot.get_cog("ApostadoFreeFire")
                if apostado_cog:
                    components = apostado_cog.display_apostado_panel(inter)
                    await inter.edit_original_message(content=None, embed=None, components=components, flags=disnake.MessageFlags(is_components_v2=True))
            
            elif choice == "Painel_Moderacao":
                moderacao_cog = self.bot.get_cog("ModeradorPanel")
                if moderacao_cog:
                    embed, components = moderacao_cog.display_moderacao_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            
            elif choice == "Painel_Verificacao":
                verificacao_cog = self.bot.get_cog("VerificacaoPanel")
                if verificacao_cog:
                    embed, components = verificacao_cog.display_verificacao_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            
            elif choice == "Painel_GIFs":
                gifs_cog = self.bot.get_cog("GIFsPanel")
                if gifs_cog:
                    embed, components = gifs_cog.display_gifs_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            
            elif choice == "Painel_Ranking":
                ranking_cog = self.bot.get_cog("RanksPanel")
                if ranking_cog:
                    embed, components = ranking_cog.display_ranking_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            
            elif choice == "Painel_Stock":
                stock_cog = self.bot.get_cog("StockPanel")
                if stock_cog:
                    embed, components = stock_cog.display_stock_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            
            elif choice == "Painel_Feedback":
                feedback_cog = self.bot.get_cog("FeedbackPanel")
                if feedback_cog:
                    embed, components = feedback_cog.display_feedback_panel(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
            elif choice == "Painel_Parcerias":
                parcerias_cog = self.bot.get_cog("Parcerias")
                if parcerias_cog:
                    await parcerias_cog.display_parcerias_panel(inter)
            elif choice == "Painel_ApostadoFF":
                apostado_cog = self.bot.get_cog("ApostadoFreeFire")
                if apostado_cog:
                    await apostado_cog.display_apostado_panel(inter)
            
            elif choice == "Painel_Protection":
                # Verificar se é owner
                config = db.obter("config.json")
                owner_id = config.get("bot", {}).get("owner")
                
                if str(inter.user.id) != str(owner_id) and not owner_email_is_verified(inter.user.id):
                    await inter.response.send_message(
                        f"{emoji.wrong} Apenas o dono do bot pode acessar esta funcionalidade.",
                        ephemeral=True
                    )
                    return
                
                protection_cog = self.bot.get_cog("ProtectionCog")
                if protection_cog:
                    await protection_cog.display_protection_panel(inter)
            
            elif choice == "Painel_Giveaways":
                giveaways_cog = self.bot.get_cog("Giveaways")
                if giveaways_cog:
                    await giveaways_cog.display_giveaways_panel(inter)
            
            elif choice == "Painel_Configuracoes":
                settings_cog = self.bot.get_cog("Settings")
                if settings_cog:
                    mode = db.get_document("custom_mode").get("mode")
                    
                    if mode == "embed":
                        await embed_message.wait(inter, send=False)
                        embed, components = settings_cog.settings_embed(inter)
                        await inter.edit_original_message(content=None, embed=embed, components=components)
                    else:
                        await message.wait(inter, send=False)
                        components = settings_cog.settings_components(inter)
                        await inter.edit_original_message(components=components, flags=disnake.MessageFlags(is_components_v2=True))

def setup(bot: commands.Bot):
    bot.add_cog(PainelCommand(bot))
