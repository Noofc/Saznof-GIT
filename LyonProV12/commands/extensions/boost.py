import disnake
from disnake.ext import commands
import aiohttp
from datetime import datetime
import uuid

from functions.emoji import emoji
from functions.database import database as db
from functions.message import message, embed_message
from functions.utils import utils
from functions.perms import perms


class BoostCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_url = "https://getvyenx.cloud/api/v1"
        self.webhook_token = "seu_token_aqui"  # TODO: Configurar no painel

    def _check_extension_enabled(self) -> bool:
        """Verifica se a extensão boost está habilitada"""
        config = db.obter("configs/config_extensions.json")
        return config.get("boost", False)

    def _get_boost_data(self) -> dict:
        """Obtém dados do boost"""
        data = db.obter("database/extensions/data.json")
        if "boost" not in data:
            data["boost"] = {
                "total_accounts": 0,
                "total_boosts_sent": 0,
                "orders": {}
            }
            db.salvar("database/extensions/data.json", data)
        return data["boost"]

    def _save_boost_data(self, boost_data: dict):
        """Salva dados do boost"""
        data = db.obter("database/extensions/data.json")
        data["boost"] = boost_data
        db.salvar("database/extensions/data.json", data)

    def _get_stock(self) -> list:
        """Obtém estoque de tokens"""
        stock = db.obter("database/extensions/stock.json")
        return stock.get("tokens", [])

    def _save_stock(self, tokens: list):
        """Salva estoque de tokens"""
        db.salvar("database/extensions/stock.json", {"tokens": tokens})

    async def _send_boost_request(self, tokens: list, invite: str, name: str = None, bio: str = None, order_id: str = None) -> dict:
        """Envia requisição para API de boost"""
        headers = {
            "x-webhook-signature": self.webhook_token,
            "Content-Type": "application/json"
        }

        campos = [{"invite": invite}]
        if name:
            campos.append({"name": name})
        if bio:
            campos.append({"bio": bio})

        body = {
            "event_name": "sale",
            "pedido": {
                "id": order_id or str(uuid.uuid4())
            },
            "campos": campos,
            "tokens": tokens
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/boost/convite",
                    headers=headers,
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    result["status_code"] = response.status
                    return result
        except Exception as e:
            return {
                "success": False,
                "message": f"Erro ao conectar com a API: {str(e)}",
                "status_code": 500
            }

    async def _check_order_status(self, order_id: str) -> dict:
        """Verifica status de uma ordem"""
        headers = {
            "x-webhook-signature": self.webhook_token,
            "Content-Type": "application/json"
        }

        body = {
            "order_id": order_id
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/order/status",
                    headers=headers,
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    result["status_code"] = response.status
                    return result
        except Exception as e:
            return {
                "success": False,
                "message": f"Erro ao conectar com a API: {str(e)}",
                "status_code": 500
            }

    @commands.slash_command(
        name="boost",
        description="Gerenciar sistema de boosts",
        guild_ids=utils.obter_guild_ids(),
    )
    async def boost(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @boost.sub_command(
        name="enviar",
        description="Enviar boosts para um servidor"
    )
    async def boost_enviar(
        self,
        inter: disnake.ApplicationCommandInteraction,
        quantidade: int = commands.Param(description="Quantidade de tokens a usar", ge=1, le=100),
        convite: str = commands.Param(description="Link de convite do servidor"),
        nome: str = commands.Param(description="Nome opcional para os boosts", default=None),
        bio: str = commands.Param(description="Bio opcional para os boosts", default=None)
    ):
        """Envia boosts para um servidor"""
        mode = db.get_document("custom_mode").get("mode")

        if mode == "embed":
            await embed_message.wait(inter, send=True)
        else:
            await message.wait(inter, send=True)

        # Verificar permissão
        if not await perms.check(inter.user.id):
            if mode == "embed":
                await embed_message.error(inter, "Você não tem permissão para usar este comando!", send=False)
            else:
                await message.error(inter, "Você não tem permissão para usar este comando!", send=False)
            return

        # Verificar se extensão está ativada
        if not self._check_extension_enabled():
            if mode == "embed":
                await embed_message.error(inter, "A extensão de Boost não está ativada!", send=False)
            else:
                await message.error(inter, "A extensão de Boost não está ativada!", send=False)
            return

        # Verificar estoque
        stock = self._get_stock()
        if len(stock) < quantidade:
            if mode == "embed":
                await embed_message.error(
                    inter,
                    f"Estoque insuficiente! Disponível: **{len(stock)}** tokens\nNecessário: **{quantidade}** tokens",
                    send=False
                )
            else:
                await message.error(
                    inter,
                    f"Estoque insuficiente! Disponível: **{len(stock)}** tokens\nNecessário: **{quantidade}** tokens",
                    send=False
                )
            return

        # Separar tokens para usar
        tokens_to_use = stock[:quantidade]
        remaining_stock = stock[quantidade:]

        # Gerar order_id único
        order_id = str(uuid.uuid4())[:8]

        # Enviar requisição
        result = await self._send_boost_request(tokens_to_use, convite, nome, bio, order_id)

        if result.get("success"):
            # Atualizar estoque
            self._save_stock(remaining_stock)

            # Salvar ordem
            boost_data = self._get_boost_data()
            boost_data["orders"][order_id] = {
                "created_at": datetime.now().isoformat(),
                "quantidade": quantidade,
                "convite": convite,
                "nome": nome,
                "bio": bio,
                "status": "processing",
                "api_order_id": result.get("message", "").split("Ordem: ")[-1] if "Ordem:" in result.get("message", "") else order_id
            }
            boost_data["total_boosts_sent"] += quantidade
            boost_data["total_accounts"] = len(remaining_stock)
            self._save_boost_data(boost_data)

            # Mensagem de sucesso
            api_order_id = boost_data["orders"][order_id]["api_order_id"]
            
            if mode == "embed":
                colors = db.get_document("custom_colors")
                primary_color_hex = colors.get("primary")

                embed = disnake.Embed(
                    title=f"{emoji.double_check} Boost Iniciado!",
                    description=(
                        f"**Order ID:** `{order_id}`\n"
                        f"**API Order ID:** `{api_order_id}`\n"
                        f"**Quantidade:** {quantidade} tokens\n"
                        f"**Convite:** {convite}\n"
                        f"**Status:** Processando\n\n"
                        f"Use `/boost status {order_id}` para verificar o progresso."
                    ),
                )

                if primary_color_hex:
                    primary_color = int(primary_color_hex.replace("#", ""), 16)
                    embed.color = primary_color

                await inter.edit_original_response(content=None, embed=embed)
            else:
                colors = db.get_document("custom_colors")
                primary_color_hex = colors.get("primary")

                container_kwargs = {}
                if primary_color_hex:
                    primary_color = int(primary_color_hex.replace("#", ""), 16)
                    container_kwargs["accent_colour"] = disnake.Colour(primary_color)

                container = disnake.ui.Container(
                    disnake.ui.TextDisplay(
                        f"# {emoji.double_check}\n"
                        f"-# Boost Iniciado!\n\n"
                        f"**Order ID:** `{order_id}`\n"
                        f"**API Order ID:** `{api_order_id}`\n"
                        f"**Quantidade:** {quantidade} tokens\n"
                        f"**Convite:** {convite}\n"
                        f"**Status:** Processando\n\n"
                        f"Use `/boost status {order_id}` para verificar o progresso."
                    ),
                    **container_kwargs
                )

                await inter.edit_original_response(content=None, components=[container])
        else:
            # Erro na API
            error_msg = result.get("message", "Erro desconhecido")
            
            if mode == "embed":
                await embed_message.error(
                    inter,
                    f"Erro ao enviar boost:\n{error_msg}",
                    send=False
                )
            else:
                await message.error(
                    inter,
                    f"Erro ao enviar boost:\n{error_msg}",
                    send=False
                )

    @boost.sub_command(
        name="status",
        description="Verificar status de uma ordem de boost"
    )
    async def boost_status(
        self,
        inter: disnake.ApplicationCommandInteraction,
        order_id: str = commands.Param(description="ID da ordem para verificar")
    ):
        """Verifica status de uma ordem"""
        mode = db.get_document("custom_mode").get("mode")

        if mode == "embed":
            await embed_message.wait(inter, send=True)
        else:
            await message.wait(inter, send=True)

        # Verificar permissão
        if not await perms.check(inter.user.id):
            if mode == "embed":
                await embed_message.error(inter, "Você não tem permissão para usar este comando!", send=False)
            else:
                await message.error(inter, "Você não tem permissão para usar este comando!", send=False)
            return

        # Verificar se extensão está ativada
        if not self._check_extension_enabled():
            if mode == "embed":
                await embed_message.error(inter, "A extensão de Boost não está ativada!", send=False)
            else:
                await message.error(inter, "A extensão de Boost não está ativada!", send=False)
            return

        # Buscar ordem local
        boost_data = self._get_boost_data()
        local_order = boost_data.get("orders", {}).get(order_id)

        if not local_order:
            if mode == "embed":
                await embed_message.error(inter, f"Ordem `{order_id}` não encontrada!", send=False)
            else:
                await message.error(inter, f"Ordem `{order_id}` não encontrada!", send=False)
            return

        # Verificar status na API
        api_order_id = local_order.get("api_order_id", order_id)
        result = await self._check_order_status(api_order_id)

        if result.get("success") and "order" in result:
            order_info = result["order"]
            
            # Atualizar ordem local
            local_order["status"] = order_info.get("status", "unknown")
            local_order["successful_boosts"] = order_info.get("successful_boosts", 0)
            local_order["failed_boosts"] = order_info.get("failed_boosts", 0)
            local_order["token_type"] = order_info.get("token_type", "Desconhecido")
            
            if order_info.get("status") == "completed":
                local_order["completed_at"] = order_info.get("timeCompleted", datetime.now().isoformat())
            
            boost_data["orders"][order_id] = local_order
            self._save_boost_data(boost_data)

            # Montar mensagem de status
            status_emoji = {
                "processing": emoji.reload,
                "completed": emoji.double_check,
                "failed": emoji.wrong
            }.get(order_info.get("status", "unknown"), emoji.information)

            status_text = {
                "processing": "Processando",
                "completed": "Concluído",
                "failed": "Falhou"
            }.get(order_info.get("status", "unknown"), "Desconhecido")

            description = (
                f"**Order ID:** `{order_id}`\n"
                f"**API Order ID:** `{api_order_id}`\n"
                f"**Status:** {status_emoji} {status_text}\n"
                f"**Tipo de Token:** {order_info.get('token_type', 'Desconhecido')}\n"
                f"**Boosts Enviados:** {order_info.get('boost_amount', 0)}\n"
                f"**Boosts Bem-sucedidos:** {order_info.get('successful_boosts', 0)}\n"
                f"**Boosts Falhados:** {order_info.get('failed_boosts', 0)}\n"
            )

            if order_info.get("status") == "completed":
                description += f"\n**Concluído em:** {order_info.get('timeCompleted', 'N/A')}"

            # Mostrar erros se houver
            if order_info.get("token_erros"):
                errors = order_info["token_erros"][:3]  # Mostrar apenas 3 primeiros erros
                description += "\n\n**Erros:**\n"
                for error in errors:
                    description += f"• {error}\n"
                if len(order_info["token_erros"]) > 3:
                    description += f"*E mais {len(order_info['token_erros']) - 3} erros...*"

            if mode == "embed":
                colors = db.get_document("custom_colors")
                primary_color_hex = colors.get("primary")

                embed = disnake.Embed(
                    title=f"{status_emoji} Status da Ordem",
                    description=description,
                )

                if primary_color_hex:
                    primary_color = int(primary_color_hex.replace("#", ""), 16)
                    embed.color = primary_color

                await inter.edit_original_response(content=None, embed=embed)
            else:
                colors = db.get_document("custom_colors")
                primary_color_hex = colors.get("primary")

                container_kwargs = {}
                if primary_color_hex:
                    primary_color = int(primary_color_hex.replace("#", ""), 16)
                    container_kwargs["accent_colour"] = disnake.Colour(primary_color)

                container = disnake.ui.Container(
                    disnake.ui.TextDisplay(
                        f"# {status_emoji}\n"
                        f"-# Status da Ordem\n\n"
                        f"{description}"
                    ),
                    **container_kwargs
                )

                await inter.edit_original_response(content=None, components=[container])
        else:
            # Erro ao verificar status
            error_msg = result.get("message", "Erro desconhecido")
            
            if mode == "embed":
                await embed_message.error(
                    inter,
                    f"Erro ao verificar status:\n{error_msg}",
                    send=False
                )
            else:
                await message.error(
                    inter,
                    f"Erro ao verificar status:\n{error_msg}",
                    send=False
                )


def setup(bot: commands.Bot):
    bot.add_cog(BoostCommands(bot))
