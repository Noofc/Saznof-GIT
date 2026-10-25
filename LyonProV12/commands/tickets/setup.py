import disnake
from disnake.ext import commands
from modules.tickets.functions.setup_team import build_attendant_select
from modules.tickets.functions.setup_member import build_member_select
from modules.tickets.functions.permissions import check_attendant_permissions as check_perms
from functions.emoji import emoji
from functions.utils import utils
from commands.tickets.ticket import get_ticket_context
from functions.perms import perms

class SetupCog(commands.Cog):
    """Cog for attendant setup commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(
        name="setup",
        guild_ids=utils.obter_guild_ids()
    )
    async def setup(self, inter: disnake.ApplicationCommandInteraction):
        """Parent command for setup commands."""
        pass

    @setup.sub_command(name="atendente", description="Exibe o painel de gerenciamento para a equipe de atendimento em um ticket.")
    async def atendente(self, inter: disnake.ApplicationCommandInteraction):
        """Displays the management panel for the support team in a ticket."""
        ticket_info, _, _, panel_config = await get_ticket_context(inter)
        if not ticket_info:
            return

        # Verificar permissões usando sistema centralizado
        has_permission = await check_perms(inter.author, inter.channel.id)
        if not has_permission:
            return await inter.response.send_message(
                f"{emoji.wrong} Você não tem permissão para usar este comando.",
                ephemeral=True
            )

        option_id = ticket_info.get("option_id")
        option_data = next((opt for opt in panel_config.get("options", []) if str(opt.get("id")) == str(option_id)), None) if option_id else None

        select = build_attendant_select(panel_config, option_data)
        
        if not select:
            return await inter.response.send_message("Essa função está desativada.", ephemeral=True)
            
        await inter.response.send_message(components=[disnake.ui.ActionRow(select)], ephemeral=True)

    @setup.sub_command(name="usuario", description="Exibe o painel de gerenciamento para o usuário em um ticket.")
    async def usuario(self, inter: disnake.ApplicationCommandInteraction):
        """Displays the management panel for the user in a ticket."""
        ticket_info, ticket_owner_id, _, panel_config = await get_ticket_context(inter)
        if not ticket_info:
            return

        is_bot_admin = await perms.check(inter.author.id)

        if not is_bot_admin and str(inter.author.id) != str(ticket_owner_id):
            return await inter.response.send_message(
                f"{emoji.wrong} Apenas o dono do ticket ou um administrador pode usar este comando.",
                ephemeral=True
            )

        option_id = ticket_info.get("option_id")
        option_data = next((opt for opt in panel_config.get("options", []) if str(opt.get("id")) == str(option_id)), None) if option_id else None

        select = build_member_select(panel_config, option_data)

        if not select:
            return await inter.response.send_message("Essa função está desativada.", ephemeral=True)

        await inter.response.send_message(components=[disnake.ui.ActionRow(select)], ephemeral=True)


def setup(bot: commands.Bot):
    """Loads the SetupAtendente cog."""
    bot.add_cog(SetupCog(bot))
