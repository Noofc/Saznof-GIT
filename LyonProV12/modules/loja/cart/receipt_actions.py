# -*- coding: utf-8 -*-
"""
View com botões de ação para o recibo de compra (Comprar Tambem, Ver Feedbacks, Suporte)
"""
import disnake
from typing import Optional, Dict, Any
from functions.emoji import emoji


class ReceiptActionsView(disnake.ui.View):
    """View com botões de ação para o recibo"""
    
    def __init__(self, 
                 support_channel_id: Optional[int] = None,
                 feedback_link: Optional[str] = None,
                 store_command_mention: Optional[str] = None):
        super().__init__(timeout=None)
        self.support_channel_id = support_channel_id
        self.feedback_link = feedback_link
        self.store_command_mention = store_command_mention
    
    @disnake.ui.button(
        label="Comprar",
        style=disnake.ButtonStyle.grey,
        emoji=emoji.cart,
        custom_id="receipt_buy_again"
    )
    async def buy_again_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        """Botão para comprar mais produtos"""
        try:
            await inter.response.defer(ephemeral=True)
            
            # Enviar comando para abrir a loja
            if self.store_command_mention:
                await inter.followup.send(
                    f"Abra a loja clicando em: {self.store_command_mention}",
                    ephemeral=True
                )
            else:
                # Fallback: enviar instrução genérica
                await inter.followup.send(
                    "Use o comando `/loja` para ver mais produtos!",
                    ephemeral=True
                )
        except Exception as e:
            print(f"[RECEIPT ACTIONS] Erro no botão Comprar Tambem: {e}")
    
    @disnake.ui.button(
        label="Ver Feedbacks",
        style=disnake.ButtonStyle.grey,
        emoji=emoji.arrow,
        custom_id="receipt_feedbacks"
    )
    async def view_feedbacks_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        """Botão para ver feedbacks de clientes"""
        try:
            await inter.response.defer(ephemeral=True)
            
            if self.feedback_link:
                await inter.followup.send(
                    f"Veja os feedbacks e avaliações de clientes aqui: {self.feedback_link}",
                    ephemeral=True
                )
            else:
                # Fallback: mensagem genérica
                await inter.followup.send(
                    "Não há um link de feedbacks configurado no momento.",
                    ephemeral=True
                )
        except Exception as e:
            print(f"[RECEIPT ACTIONS] Erro no botão Ver Feedbacks: {e}")
    
    @disnake.ui.button(
        label="Suporte",
        style=disnake.ButtonStyle.grey,
        emoji=emoji.shield,
        custom_id="receipt_support"
    )
    async def support_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        """Botão para acessar canal de suporte"""
        try:
            await inter.response.defer(ephemeral=True)
            
            if self.support_channel_id:
                channel = inter.bot.get_channel(self.support_channel_id)
                if channel:
                    await inter.followup.send(
                        f"Canal de suporte: {channel.mention}",
                        ephemeral=True
                    )
                else:
                    await inter.followup.send(
                        "Canal de suporte não encontrado.",
                        ephemeral=True
                    )
            else:
                await inter.followup.send(
                    "Canal de suporte não configurado.",
                    ephemeral=True
                )
        except Exception as e:
            print(f"[RECEIPT ACTIONS] Erro no botão Suporte: {e}")


def create_receipt_actions_view(
    guild_config: Optional[Dict[str, Any]] = None
) -> ReceiptActionsView:
    """Factory function para criar View com as configurações do servidor"""
    support_channel_id = None
    feedback_link = None
    store_command_mention = "</loja:0>"
    
    if guild_config:
        # Obter IDs da configuração do servidor
        support_channel_id = guild_config.get("support_channel_id")
        feedback_link = guild_config.get("feedback_link")
        store_command_mention = guild_config.get("store_command_mention", "</loja:0>")
    
    return ReceiptActionsView(
        support_channel_id=support_channel_id,
        feedback_link=feedback_link,
        store_command_mention=store_command_mention
    )
