"""
Sistema de download/envio de transcripts para DM
Lê a URL da API do config_api.json
"""

import disnake
from functions.emoji import emoji
from functions.database import database as db
from functions.transcript_cache import get_cached_link, save_link_to_cache
import json
import os
import aiohttp
from typing import Optional


def get_transcript_api_url() -> str:
    """Carrega a URL da API de transcripts do config_api.json"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), '../../../configs/config_api.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        api_host = config.get('transcripts', 'localhost:22222')
        
        # Garantir que tenha protocolo
        if not api_host.startswith('http'):
            api_host = f'http://{api_host}'
        
        return api_host
    except Exception as e:
        print(f"[TRANSCRIPT] Erro ao carregar config_api.json: {e}")
        return os.getenv("TRANSCRIPT_API_URL", "http://localhost:22222")


async def upload_transcript_to_api(
    transcript_html: str,
    channel_name: str,
    api_url: str = None
) -> Optional[str]:
    """
    Faz upload do transcript para a API.
    
    :param transcript_html: Conteúdo HTML do transcript
    :param channel_name: Nome do canal
    :param api_url: URL base da API
    :return: URL do transcript ou None se falhar
    """
    if api_url is None:
        api_url = get_transcript_api_url()
    
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field(
                'file',
                transcript_html.encode('utf-8'),
                filename=f'transcript-{channel_name}.html',
                content_type='text/html'
            )
            data.add_field('filename', f'transcript-{channel_name}.html')
            data.add_field('channel_name', channel_name)
            
            async with session.post(
                f"{api_url}/api/v1/transcript/upload",
                data=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get("success"):
                        if result.get('fullUrl'):
                            return result['fullUrl']
                        url_path = result['url']
                        if url_path.startswith('/'):
                            return f"{api_url}{url_path}"
                        return url_path
    except Exception as e:
        print(f"[TRANSCRIPT] Erro ao fazer upload: {e}")
    
    return None


async def send_transcript_to_dm(interaction: disnake.ApplicationCommandInteraction, transcript_file: disnake.File):
    """
    Envia o transcript gerado para a DM do usuário via link da API, com sistema de cache.

    :param interaction: A interação do comando para responder.
    :param transcript_file: O arquivo de transcript para enviar.
    """
    config = db.get_document("tickets_config") or {}
    tickets_data = db.get_document("tickets_data") or {}
    
    panel_id = None
    if isinstance(interaction.channel, (disnake.TextChannel, disnake.Thread)):
        for pid, users in tickets_data.get("panels", {}).items():
            for user_id, tickets in users.items():
                for ticket in tickets:
                    if ticket.get("ticket_id") == interaction.channel.id:
                        panel_id = pid
                        break
                if panel_id: break
            if panel_id: break
            
    panel_data = config.get("panels", {}).get(panel_id, {}) if panel_id else {}
    messages = panel_data.get("messages", {})
    
    message_template = messages.get("transcript_dm_message", "Aqui está o transcript que você solicitou para o ticket `{channel_name}`:")
    message_content = message_template.format(
        channel_name=interaction.channel.name,
        guild_name=interaction.guild.name,
        user_mention=interaction.author.mention,
        user_name=interaction.author.name
    )

    try:
        # Sempre gerar um novo transcript (sem cache)
        transcript_file.fp.seek(0)
        transcript_html = transcript_file.fp.read().decode('utf-8')
        
        transcript_url = await upload_transcript_to_api(
            transcript_html,
            interaction.channel.name
        )
        
        if transcript_url:
            # Enviar com URL (seja do cache ou recém-gerada) como botão de link
            await interaction.author.send(
                content=message_content,
                components=[
                    disnake.ui.ActionRow(
                        disnake.ui.Button(
                            label="Ver transcript",
                            style=disnake.ButtonStyle.link,
                            url=transcript_url
                        )
                    )
                ]
            )
            await interaction.followup.send(f"{emoji.double_check} Transcript enviado para sua DM!", ephemeral=True)
        else:
            # Se falhar a API e não houver cache
            await interaction.followup.send(
                f"{emoji.wrong} Não foi possível hospedar o transcript na API no momento. Tente novamente mais tarde.",
                ephemeral=True
            )
        
    except disnake.Forbidden:
        await interaction.followup.send(
            f"{emoji.wrong} Não consegui enviar o transcript para sua DM. Verifique se suas DMs estão abertas.",
            ephemeral=True
        )
    except Exception as e:
        print(f"Erro ao enviar o transcript para o usuário via DM: {e}")
        await interaction.followup.send(
            f"{emoji.wrong} Ocorreu um erro ao processar o transcript.",
            ephemeral=True
        )
