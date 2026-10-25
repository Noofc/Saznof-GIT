# -*- coding: utf-8 -*-
"""
Comando /settimezone para configurar timezone do servidor
"""

import disnake
from disnake.ext import commands
from functions import emoji
from functions.timezone_manager import TimezoneManager, ALLOWED_TIMEZONES


class TimezoneCommands(commands.Cog):
    """Comandos de configuração de timezone"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.slash_command(
        name="settimezone",
        description="Configura o timezone do servidor para recibos e logs",
        default_member_permissions=disnake.Permissions(administrator=True)
    )
    @commands.has_permissions(administrator=True)
    async def set_timezone(
        self,
        inter: disnake.ApplicationCommandInteraction,
        timezone: str = commands.Param(
            description="Timezone desejado",
            choices=[
                "America/Sao_Paulo (Brasília - Padrão)",
                "America/Manaus (Manaus)",
                "America/Rio_Branco (Rio Branco)",
                "America/Bahia (Bahia)",
                "America/Fortaleza (Fortaleza)",
                "America/Araguaina (Araguaína)",
                "America/Maceio (Maceió)",
                "America/Recife (Recife)",
                "America/Anchorage (Anchorage)",
                "America/Chicago (Chicago)",
                "America/Denver (Denver)",
                "America/Los_Angeles (Los Angeles)",
                "America/New_York (Nova York)",
                "Europe/London (Londres)",
                "Europe/Paris (Paris)",
                "Europe/Berlin (Berlim)",
                "Europe/Madrid (Madri)",
                "Asia/Tokyo (Tóquio)",
                "Asia/Shanghai (Xangai)",
                "Asia/Hong_Kong (Hong Kong)",
                "Asia/Singapore (Singapura)",
                "Australia/Sydney (Sydney)",
            ]
        )
    ):
        """Configura timezone para o servidor"""
        
        try:
            # Extrair timezone (primeiro valor da string)
            tz_name = timezone.split(" ")[0]
            
            # Validar timezone
            if tz_name not in ALLOWED_TIMEZONES:
                await inter.response.send_message(
                    f"{emoji.wrong} Timezone '{tz_name}' não é válido.",
                    ephemeral=True
                )
                return
            
            # Salvar no banco de dados
            success = TimezoneManager.set_server_timezone(inter.guild.id, tz_name)
            
            if not success:
                await inter.response.send_message(
                    f"{emoji.wrong} Erro ao salvar timezone. Tente novamente.",
                    ephemeral=True
                )
                return
            
            # Apresentar horário local
            from datetime import datetime
            from functions.timezone_manager import TimezoneManager
            utc_now = TimezoneManager.get_utc_now()
            display_dt = TimezoneManager.utc_to_display(utc_now, tz_name)
            
            await inter.response.send_message(
                f"{emoji.correct} **Timezone atualizado com sucesso!**\n\n"
                f"**Timezone:** {tz_name}\n"
                f"**Horário atual:** {display_dt.strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                f"Todos os recibos e logs agora usarão este timezone.",
                ephemeral=False
            )
            
            print(f"[TIMEZONE] Servidor {inter.guild.name} (ID: {inter.guild.id}) configurado com timezone: {tz_name}")
            
        except Exception as e:
            print(f"[TIMEZONE] Erro ao configurar timezone: {e}")
            import traceback
            traceback.print_exc()
            
            await inter.response.send_message(
                f"{emoji.wrong} Erro ao processar comando. Tente novamente.",
                ephemeral=True
            )
    
    @commands.slash_command(
        name="gettimezone",
        description="Mostra o timezone configurado do servidor"
    )
    async def get_timezone(self, inter: disnake.ApplicationCommandInteraction):
        """Mostra timezone atual"""
        
        try:
            tz = TimezoneManager.get_server_timezone(inter.guild.id)
            
            # Apresentar horário local
            from functions.timezone_manager import TimezoneManager
            utc_now = TimezoneManager.get_utc_now()
            display_dt = TimezoneManager.utc_to_display(utc_now, tz)
            
            await inter.response.send_message(
                f"**Timezone do servidor:** {tz}\n"
                f"**Horário atual:** {display_dt.strftime('%d/%m/%Y %H:%M:%S')}",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"[TIMEZONE] Erro ao obter timezone: {e}")
            await inter.response.send_message(
                f"{emoji.wrong} Erro ao processar comando.",
                ephemeral=True
            )


def setup(bot: commands.Bot):
    bot.add_cog(TimezoneCommands(bot))
