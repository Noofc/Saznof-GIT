"""
Painel de personalização da loja
"""
import disnake
from disnake.ext import commands
from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message


class PersonalizarLoja(commands.Cog):
    """Painel de personalização da loja"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @staticmethod
    def panel(inter: disnake.MessageInteraction) -> dict:
        """Retorna o painel de personalização"""
        mode = db.get_document("custom_mode").get("mode", "components")
        
        if mode == "embed":
            return PersonalizarLoja._panel_embed(inter)
        else:
            return PersonalizarLoja._panel_components(inter)
    
    @staticmethod
    def _panel_components(inter: disnake.MessageInteraction) -> dict:
        """Painel em modo components v2"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))
        
        return {"components": [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Loja > **Personalizar**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    "Personalize a experiência da sua loja.\n"
                    "Configure mensagens, marca e muito mais."
                ),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Mensagens",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.message,
                        custom_id="Loja_Personalizar_Mensagens"
                    ),
                    disnake.ui.Button(
                        label="Botão de Dúvidas",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.interrogation,
                        custom_id="Loja_Personalizar_DoubtButton",
                    ),
                    disnake.ui.Button(
                        label="QR Code",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.mobile,
                        custom_id="Loja_Personalizar_QRCode",
                    ),
                ),
                **container_kwargs
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Painel_Loja"
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
        
        embed = disnake.Embed(
            title="Personalizar Loja",
            description=(
                "-# Painel > Loja > **Personalizar**\n\n"
                "Personalize a experiência da sua loja.\n"
                "Configure mensagens, marca e muito mais."
            ),
            **embed_kwargs
        )
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Mensagens",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.message,
                    custom_id="Loja_Personalizar_Mensagens"
                ),
                disnake.ui.Button(
                    label="Botão de Dúvidas",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.interrogation,
                    custom_id="Loja_Personalizar_DoubtButton",
                ),
                disnake.ui.Button(
                    label="QR Code",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.mobile,
                    custom_id="Loja_Personalizar_QRCode",
                ),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Painel_Loja"
                )
            )
        ]
        
        return {"embed": embed, "components": components}
    
    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Loja_Personalizar":
            mode = db.get_document("custom_mode").get("mode")
            
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)
            
            panel_data = self.panel(inter)
            await inter.edit_original_message(**panel_data)
        
        elif inter.component.custom_id == "Loja_Personalizar_DoubtButton":
            from .doubt_button import DoubtButtonLyon
            
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)
            
            panel_data = DoubtButtonLyon.panel_doubt_button(inter)
            await inter.edit_original_message(**panel_data)
        
        elif inter.component.custom_id == "Loja_Personalizar_QRCode":
            from .qr_customization import QRCodeGenerator
            
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)
            
            panel_data = QRCodeGenerator.panel(inter)
            await inter.edit_original_message(**panel_data)
        
        elif inter.component.custom_id == "Loja_DoubtButton_Config":
            from .doubt_button import DoubtButtonModal
            await inter.response.send_modal(DoubtButtonModal())
        
        elif inter.component.custom_id == "Loja_DoubtButton_Toggle":
            data = db.get_document("loja_doubt_button")
            data["enabled"] = not data.get("enabled", False)
            db.save_document("loja_doubt_button", data)
            
            from .doubt_button import DoubtButtonLyon
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)
            
            panel_data = DoubtButtonLyon.panel_doubt_button(inter)
            await inter.edit_original_message(**panel_data)
        
        elif inter.component.custom_id == "Loja_QRCode_Config":
            from .qr_customization import QRCustomizationModal
            await inter.response.send_modal(QRCustomizationModal())
        
        elif inter.component.custom_id == "Loja_QRCode_Toggle":
            from .qr_customization import QRCodeGenerator
            data = db.get_document("loja_qr_customization")
            data["enabled"] = not QRCodeGenerator.get_config().get("enabled", True)
            db.save_document("loja_qr_customization", data)
            
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)
            
            panel_data = QRCodeGenerator.panel(inter)
            await inter.edit_original_message(**panel_data)
        
        elif inter.component.custom_id == "Loja_QRCode_Test":
            from .qr_customization import QRCodeGenerator
            
            await inter.response.defer(ephemeral=True)
            
            # Gerar QR de teste
            qr_bytes = await QRCodeGenerator.generate_custom_qr("https://Lyonapplications.com.br")
            
            if qr_bytes:
                import io
                file = disnake.File(io.BytesIO(qr_bytes), filename="qr_test.png")
                await inter.followup.send(
                    f"{emoji.correct} QR Code de teste gerado!",
                    file=file,
                    ephemeral=True
                )
            else:
                await inter.followup.send(
                    f"{emoji.wrong} Erro ao gerar QR Code de teste!",
                    ephemeral=True
                )
        
        elif inter.component.custom_id == "product_doubt_button":
            from .doubt_button import DoubtButtonLyon
            await DoubtButtonLyon.handle_doubt_button(inter)


def setup(bot: commands.Bot):
    bot.add_cog(PersonalizarLoja(bot))
