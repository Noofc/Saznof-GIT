from disnake.ext import commands
import disnake

from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from functions.email_utils import owner_email_is_verified
from functions.plan import should_enable_settings_button

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def display_configuracoes_panel(self, inter: disnake.MessageInteraction):
        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            await embed_message.wait(inter, send=False)
            embed, components = self.settings_embed(inter)
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            await message.wait(inter, send=False)
            await inter.edit_original_message(
                content=None,
                embed=None,
                components=self.settings_components(inter),
                flags=disnake.MessageFlags(is_components_v2=True),
            )

    def settings_components(self, inter: disnake.MessageInteraction) -> list[disnake.ui.Container]:
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        options = [
            disnake.SelectOption(label="Cargos", value="cargos", emoji=emoji.role, description="Gerencie cargos do servidor"),
            disnake.SelectOption(label="Canais", value="canais", emoji=emoji.textc, description="Gerencie canais do servidor"),
            disnake.SelectOption(label="Formas de Pagamento", value="pagamentos", emoji=emoji.wallet, description="Configure provedores e status"),
            disnake.SelectOption(label="Anti-Fake", value="antifake", emoji=emoji.members, description="Configure proteção contra contas falsas"),
            disnake.SelectOption(label="Gerenciar Permissões", value="permissoes", emoji=emoji.members, description="Adicione ou remova permissões de usuários"),
            disnake.SelectOption(label="Extensões", value="extensoes", emoji=emoji.commands, description="Gerencie as extensões do bot"),
            disnake.SelectOption(label="Notificações", value="notificacoes", emoji=emoji.warn, description="Configure as notificações de vendas"),
            disnake.SelectOption(label="Bloquear Usuários", value="blacklist", emoji=emoji.lock, description="Bloqueie usuários de Comprar em Seu Pro"),
        ]

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > **Configurações**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    "Configure e personalize os canais, cargos e formas de pagamento.\n"
                    "Selecione uma seção abaixo para configurar."
                ),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Configuracoes_Select",
                        placeholder="Selecione uma seção para configurar",
                        options=options,
                    )
                ),
                **container_kwargs,
            )
        ]

    def settings_embed(self, inter: disnake.MessageInteraction):
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")

        embed = disnake.Embed(
            title=f"Configurações",
            description="Configure e personalize os canais, cargos e formas de pagamento.\nSelecione uma seção abaixo para configurar.",
            # timestamp=disnake.utils.utcnow()
        )
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color

        # embed.set_footer(text=inter.guild.name, icon_url=inter.guild.icon.url if inter.guild.icon else None)
        options = [
            disnake.SelectOption(label="Cargos", value="cargos", emoji=emoji.role, description="Gerencie cargos do servidor"),
            disnake.SelectOption(label="Canais", value="canais", emoji=emoji.textc, description="Gerencie canais do servidor"),
            disnake.SelectOption(label="Formas de Pagamento", value="pagamentos", emoji=emoji.wallet, description="Configure provedores e status"),
            disnake.SelectOption(label="Anti-Fake", value="antifake", emoji=emoji.members, description="Configure proteção contra contas falsas"),
            disnake.SelectOption(label="Gerenciar Permissões", value="permissoes", emoji=emoji.members, description="Adicione ou remova permissões de usuários"),
            disnake.SelectOption(label="Extensões", value="extensoes", emoji=emoji.commands, description="Gerencie as extensões do bot"),
            disnake.SelectOption(label="Notificações", value="notificacoes", emoji=emoji.warn, description="Configure as notificações de vendas"),
            disnake.SelectOption(label="Bloquear Usuários", value="blacklist", emoji=emoji.lock, description="Bloqueie usuários de Comprar em Seu Pro"),
        ]

        components = [
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="Configuracoes_Select",
                    placeholder="Selecione uma seção para configurar",
                    options=options,
                )
            ),
        ]
        return embed, components

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Painel_Configuracoes":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.settings_embed(inter)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await inter.edit_original_message(
                    content=None,
                    embed=None,
                    components=self.settings_components(inter),
                    flags=disnake.MessageFlags(is_components_v2=True),
                )

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Configuracoes_Select":
            choice = inter.values[0]

            coming_soon = {}
            if choice in coming_soon:
                await inter.response.send_message(
                    "Essa funcionalidade será implementada em breve em próximas atualizações.",
                    ephemeral=True
                )
                return

            mode = db.get_document("custom_mode").get("mode")
            if choice == "notificacoes":
                from .notificacoes.cog import ConfigureNotifications
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    panel = ConfigureNotifications.panel(inter)
                    await inter.edit_original_message(content=None, **panel)
                else:
                    await message.wait(inter, send=False)
                    panel = ConfigureNotifications.panel(inter)
                    await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))
            elif choice == "blacklist":
                from .bloquear.cog import ConfigurarBlacklist
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    panel = ConfigurarBlacklist.panel(inter)
                    await inter.edit_original_message(content=None, **panel)
                else:
                    await message.wait(inter, send=False)
                    panel = ConfigurarBlacklist.panel(inter)
                    await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))
            elif choice == "antifake":
                from .antifake.cog import AntiFakeConfig
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    panel = AntiFakeConfig.panel(inter)
                    await inter.edit_original_message(content=None, **panel)
                else:
                    await message.wait(inter, send=False)
                    panel = AntiFakeConfig.panel(inter)
                    await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))
            elif choice == "cargos":
                from .cargos.cog import ConfigurarCargos
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = ConfigurarCargos.cargos_embed(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    await inter.edit_original_message(
                        content=None,
                        embed=None,
                        components=ConfigurarCargos.cargos_components(inter),
                        flags=disnake.MessageFlags(is_components_v2=True),
                    )
            elif choice == "canais":
                from .canais.cog import ConfigurarCanais
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = ConfigurarCanais.canais_embed(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    await inter.edit_original_message(
                        content=None,
                        embed=None,
                        components=ConfigurarCanais.canais_components(inter),
                        flags=disnake.MessageFlags(is_components_v2=True),
                    )
            elif choice == "pagamentos":
                from .payments.cog import ConfigurarPagamentos
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = ConfigurarPagamentos.pagamentos_embed(inter)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    await inter.edit_original_message(
                        content=None,
                        embed=None,
                        components=ConfigurarPagamentos.pagamentos_components(inter),
                        flags=disnake.MessageFlags(is_components_v2=True),
                    )
            elif choice == "extensoes":
                extensions_cog = self.bot.get_cog("ExtensionsPanel")
                if extensions_cog:
                    await extensions_cog.display_extensions_panel(inter)
                else:
                    await inter.response.send_message(
                        f"{emoji.wrong} Não foi possível carregar o painel de extensões no momento.",
                        ephemeral=True
                    )
            elif choice == "permissoes":
                # Verificar se é o owner - apenas owner pode acessar gerenciar permissões
                config = db.obter("config.json") or {}
                owner_id = config.get("bot", {}).get("owner")
                
                if str(inter.user.id) != str(owner_id) and not owner_email_is_verified(inter.user.id):
                    await inter.response.send_message(
                        f"{emoji.wrong} Apenas o dono do bot pode gerenciar permissões.",
                        ephemeral=True
                    )
                    return
                
                from .permissoes.cog import GerenciarPermissoes
                if mode == "embed":
                    await embed_message.wait(inter, send=False)
                    embed, components = GerenciarPermissoes.panel_embed(inter, self.bot)
                    await inter.edit_original_message(content=None, embed=embed, components=components)
                else:
                    await message.wait(inter, send=False)
                    panel = await GerenciarPermissoes.panel_aLyon(inter, self.bot)
                    await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))
