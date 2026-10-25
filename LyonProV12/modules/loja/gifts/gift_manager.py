"""
Sistema de Gifts (Cupons de Produtos para Resgate)
Permite criar códigos para que usuários resgatem produtos específicos
"""
import disnake
from functions.database import database as db
from functions.emoji import emoji
from datetime import datetime, timedelta
import secrets
import string
import json
import io

class GiftManager:
    """Gerencia gifts (cupons) de produtos"""

    GIFTS_KEY = "loja_gifts"

    @staticmethod
    def _storage_for_guild(guild_id: int) -> dict:
        gifts = db.get_document(GiftManager.GIFTS_KEY) or {}
        guild_key = str(guild_id)
        if "gifts" not in gifts:
            gifts["gifts"] = {}
        if guild_key not in gifts["gifts"]:
            gifts["gifts"][guild_key] = {}
        return gifts

    @staticmethod
    def generate_gift_code(length=12) -> str:
        """Gera um código de gift aleatório"""
        chars = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))

    @staticmethod
    def create_gift(guild_id: int, product_id: str, campo_id: str, quantity: int = 1, max_uses: int = 1, expires_in_days: int | None = None, created_by_id: int | None = None) -> dict:
        """Cria um novo gift e retorna os dados do código"""
        gifts = GiftManager._storage_for_guild(guild_id)
        guild_key = str(guild_id)
        codes = gifts["gifts"][guild_key]

        code = GiftManager.generate_gift_code()
        while code in codes:
            code = GiftManager.generate_gift_code()

        expiration = None
        if expires_in_days:
            expiration = (datetime.now() + timedelta(days=expires_in_days)).timestamp()

        gift_data = {
            "code": code,
            "product_id": product_id,
            "campo_id": campo_id,
            "quantity": quantity,
            "max_uses": max_uses,
            "current_uses": 0,
            "created_at": datetime.now().timestamp(),
            "created_by": created_by_id,
            "expiration": expiration,
            "used_by": []
        }

        codes[code] = gift_data
        db.save_document(GiftManager.GIFTS_KEY, gifts)
        return gift_data

    @staticmethod
    def get_gift(guild_id: int, code: str) -> dict | None:
        """Obtém dados de um gift por código"""
        gifts = db.get_document(GiftManager.GIFTS_KEY) or {}
        return gifts.get("gifts", {}).get(str(guild_id), {}).get(code)

    @staticmethod
    def redeem_gift(guild_id: int, code: str, user_id: int) -> dict:
        """
        Resgata um gift para um usuário.
        Retorna um dicionário com sucesso, mensagem e itens.
        """
        gifts = db.get_document(GiftManager.GIFTS_KEY) or {}
        guild_gifts = gifts.get("gifts", {}).get(str(guild_id), {})
        gift_data = guild_gifts.get(code)

        if not gift_data:
            return {"success": False, "message": "Código de gift inválido ou expirado."}

        if gift_data.get("expiration") and datetime.now().timestamp() > gift_data["expiration"]:
            return {"success": False, "message": "Código de gift expirou."}

        if gift_data["current_uses"] >= gift_data["max_uses"]:
            return {"success": False, "message": "Este código de gift já atingiu o limite de usos."}

        if user_id in gift_data.get("used_by", []):
            return {"success": False, "message": "Você já resgatou este gift anteriormente."}

        from modules.loja.cart.stock_manager import StockManager
        products = db.get_document("loja_products") or {}
        product = products.get(gift_data["product_id"])

        if not product:
            return {"success": False, "message": "Produto não encontrado."}

        campo = product.get("campos", {}).get(gift_data["campo_id"])
        if not campo:
            return {"success": False, "message": "Campo do produto não encontrado."}

        items = StockManager.get_stock_items(gift_data["product_id"], gift_data["campo_id"], gift_data["quantity"])
        if not items:
            return {"success": False, "message": "Não há estoque disponível para este gift."}

        gift_data["current_uses"] += 1
        gift_data["used_by"].append(user_id)
        guild_gifts[code] = gift_data
        gifts["gifts"][str(guild_id)] = guild_gifts
        db.save_document(GiftManager.GIFTS_KEY, gifts)

        return {"success": True, "message": "Gift resgatado com sucesso.", "items": items}

    @staticmethod
    def delete_gift(guild_id: int, code: str) -> bool:
        """Deleta um gift"""
        gifts = db.get_document(GiftManager.GIFTS_KEY) or {}
        guild_gifts = gifts.get("gifts", {}).get(str(guild_id), {})
        if code in guild_gifts:
            del guild_gifts[code]
            gifts["gifts"][str(guild_id)] = guild_gifts
            db.save_document(GiftManager.GIFTS_KEY, gifts)
            return True
        return False

    @staticmethod
    def list_gifts(guild_id: int) -> list[dict]:
        """Retorna a lista de gifts do servidor"""
        gifts = db.get_document(GiftManager.GIFTS_KEY) or {}
        guild_gifts = gifts.get("gifts", {}).get(str(guild_id), {})
        return list(guild_gifts.values())

    @staticmethod
    def search_gifts(guild_id: int, query: str) -> list[dict]:
        """Procura gifts por código exato ou por product_id parcial (case-insensitive)."""
        query = (query or "").strip()
        if not query:
            return []
        all_gifts = GiftManager.list_gifts(guild_id)
        qlow = query.lower()
        results = [g for g in all_gifts if g.get("code", "").lower() == qlow or qlow in g.get("product_id", "").lower()]
        return results

    @staticmethod
    def update_gift(guild_id: int, code: str, **fields) -> dict | None:
        """Atualiza campos de um gift. Retorna o gift atualizado ou None se não existir."""
        gifts = db.get_document(GiftManager.GIFTS_KEY) or {}
        guild_gifts = gifts.get("gifts", {}).get(str(guild_id), {})
        gift = guild_gifts.get(code)
        if not gift:
            return None

        # Campos permitidos para atualização
        if "product_id" in fields and fields["product_id"]:
            gift["product_id"] = fields["product_id"]
        if "campo_id" in fields and fields["campo_id"]:
            gift["campo_id"] = fields["campo_id"]
        if "quantity" in fields and fields["quantity"] is not None:
            gift["quantity"] = int(fields["quantity"])
        if "max_uses" in fields and fields["max_uses"] is not None:
            gift["max_uses"] = int(fields["max_uses"])
        if "expires_in" in fields and fields["expires_in"] is not None:
            try:
                days = int(fields["expires_in"])
                gift["expiration"] = (datetime.now() + timedelta(days=days)).timestamp()
            except Exception:
                pass

        guild_gifts[code] = gift
        gifts["gifts"][str(guild_id)] = guild_gifts
        db.save_document(GiftManager.GIFTS_KEY, gifts)
        return gift

    @staticmethod
    def export_gifts(guild_id: int) -> dict:
        """Retorna os gifts do servidor como um dict pronto para serializar."""
        gifts = db.get_document(GiftManager.GIFTS_KEY) or {}
        return gifts.get("gifts", {}).get(str(guild_id), {})
