"""
Sistema de Parcerias Automáticas
Gerencia parcerias, comissões, recompensas e afiliados
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta
from connections.mongo_db import collection as bot_collection

class ParceriasManager:
    """Gerenciador de parcerias e afiliados"""
    
    DEFAULT_PARCERIAS = {
        "parcerias": {},
        "afiliados": {},
        "comissoes": {
            "venda_direta": 0.10,      # 10%
            "indicacao": 0.05,          # 5%
            "compra_afiliado": 0.03,    # 3%
            "referencia": 0.02,         # 2%
        },
        "bonus_ativacao": 50,           # Bônus ao ativar parceria
        "tiers": {
            "bronze": {"vendas_minimas": 0, "comissao_extra": 0, "bônus_nivel": 50},
            "prata": {"vendas_minimas": 5000, "comissao_extra": 0.02, "bônus_nivel": 200},
            "ouro": {"vendas_minimas": 20000, "comissao_extra": 0.05, "bônus_nivel": 500},
            "platina": {"vendas_minimas": 50000, "comissao_extra": 0.10, "bônus_nivel": 1000},
        },
        "requerimentos": {
            "vendas_minimas": 100,
            "reputacao_minima": 50,
            "dias_servidor": 30,
        },
        "bonus_performance": {
            "meta_semanal": 5000,
            "recompensa": 200,
        }
    }
    
    @staticmethod
    async def criar_parceria(user_id: int, nome_empresa: str, tipo: str) -> tuple[bool, str]:
        """Cria uma nova parceria"""
        try:
            parceria = {
                "usuario": user_id,
                "nome": nome_empresa,
                "tipo": tipo,  # "loja", "creator", "intermediario"
                "status": "ativo",
                "data_criacao": datetime.now().isoformat(),
                "vendas_totais": 0,
                "comissoes_ganhas": 0,
                "afiliados": [],
                "nivel": 1,
                "tier": "bronze",
            }
            
            # Adicionar bônus de ativação
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.saldo": 50}
                },
                upsert=True
            )
            
            await bot_collection.update_one(
                {"_id": "parcerias"},
                {
                    "$set": {f"parcerias.{user_id}": parceria},
                    "$inc": {"total_parcerias": 1}
                },
                upsert=True
            )
            
            return True, f"✅ Parceria criada! Você recebeu **50** como bônus de ativação!"
        except Exception as e:
            return False, f"❌ Erro: {e}"
    
    @staticmethod
    async def registrar_venda(parceiro_id: int, valor: float, tipo_venda: str = "direta") -> bool:
        """Registra uma venda e calcula comissão"""
        config = await ParceriasManager.get_config()
        comissao = await ParceriasManager.obter_comissao_com_bonus(parceiro_id, valor, tipo_venda)
        
        try:
            # Atualizar parceria com vendas e comissões
            await bot_collection.update_one(
                {"_id": "parcerias"},
                {
                    "$inc": {
                        f"parcerias.{parceiro_id}.vendas_totais": valor,
                        f"parcerias.{parceiro_id}.comissoes_ganhas": comissao,
                    }
                }
            )
            
            # Transferir comissão para economia
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{parceiro_id}.saldo": comissao},
                    "$push": {
                        f"usuarios.{parceiro_id}.historico": {
                            "tipo": "comissao_parceria",
                            "valor": comissao,
                            "venda": valor,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            # Checar se sobe de nível
            await ParceriasManager._verificar_nivel(parceiro_id)
            
            return True
        except Exception as e:
            print(f"[Parcerias] Erro ao registrar venda: {e}")
            return False
    
    @staticmethod
    async def adicionar_afiliado(parceiro_id: int, afiliado_id: int) -> tuple[bool, str]:
        """Adiciona um afiliado à rede de parcerias"""
        try:
            await bot_collection.update_one(
                {"_id": "parcerias"},
                {
                    "$push": {f"parcerias.{parceiro_id}.afiliados": afiliado_id},
                    "$inc": {f"afiliados.{afiliado_id}.rede_tamanho": 1}
                },
                upsert=True
            )
            
            # Bônus de indicação
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{parceiro_id}.saldo": 25}
                },
                upsert=True
            )
            
            return True, "✅ Afiliado adicionado com sucesso!"
        except Exception as e:
            return False, f"❌ Erro: {e}"
    
    @staticmethod
    async def _verificar_nivel(user_id: int):
        """Verifica se o parceiro sobe de nível"""
        config = await ParceriasManager.get_config()
        parceria_doc = await bot_collection.find_one(
            {"_id": "parcerias"},
            {f"parcerias.{user_id}": 1}
        )
        
        if not parceria_doc or str(user_id) not in parceria_doc.get("parcerias", {}):
            return
        
        parceria_data = parceria_doc["parcerias"][str(user_id)]
        vendas = parceria_data.get("vendas_totais", 0)
        tier_atual = parceria_data.get("tier", "bronze")
        
        # Verificar próximo tier
        novo_tier = "bronze"
        for tier_nome, tier_data in config["tiers"].items():
            if vendas >= tier_data["vendas_minimas"]:
                novo_tier = tier_nome
        
        # Se mudou de tier, dar bônus
        if novo_tier != tier_atual:
            tier_info = config["tiers"][novo_tier]
            bonus = tier_info["bônus_nivel"]
            
            await bot_collection.update_one(
                {"_id": "parcerias"},
                {
                    "$set": {f"parcerias.{user_id}.tier": novo_tier},
                    "$inc": {f"usuarios.{user_id}.saldo": bonus}
                }
            )
    
    @staticmethod
    async def obter_comissao_com_bonus(parceiro_id: int, valor: float, tipo_venda: str = "direta") -> float:
        """Calcula comissão considerando tier do parceiro"""
        config = await ParceriasManager.get_config()
        parceria = await ParceriasManager.get_parceria(parceiro_id)
        
        # Comissão base
        comissao_percentual = config["comissoes"].get(f"venda_{tipo_venda}", 0.10)
        comissao = valor * comissao_percentual
        
        # Bônus por tier
        if parceria:
            tier = parceria.get("tier", "bronze")
            bonus_tier = config["tiers"][tier].get("comissao_extra", 0)
            comissao += valor * bonus_tier
        
        return comissao
    
    @staticmethod
    async def verificar_bonus_performance(parceiro_id: int) -> tuple[bool, float]:
        """Verifica se atingiu meta semanal e distribui bônus"""
        config = await ParceriasManager.get_config()
        parceria = await ParceriasManager.get_parceria(parceiro_id)
        
        if not parceria:
            return False, 0
        
        meta = config["bonus_performance"]["meta_semanal"]
        recompensa = config["bonus_performance"]["recompensa"]
        
        # Vendas da última semana
        uma_semana_atras = (datetime.now() - timedelta(days=7)).isoformat()
        # Aqui você verificaria no histórico de vendas
        
        return True, recompensa
    
    @staticmethod
    async def get_config() -> dict:
        """Obtém configuração de parcerias"""
        doc = await bot_collection.find_one({"_id": "parcerias"})
        if not doc:
            return ParceriasManager.DEFAULT_PARCERIAS
        return doc
    
    @staticmethod
    async def get_parceria(user_id: int) -> Optional[dict]:
        """Obtém dados da parceria de um usuário"""
        doc = await bot_collection.find_one({"_id": "parcerias"})
        if not doc:
            return None
        
        parcerias = doc.get("parcerias", {})
        return parcerias.get(str(user_id))
    
    @staticmethod
    async def get_ranking_parceiros() -> List[tuple[int, float]]:
        """Obtém ranking de parceiros por comissões"""
        doc = await bot_collection.find_one({"_id": "parcerias"})
        if not doc:
            return []
        
        parcerias = doc.get("parcerias", {})
        ranking = sorted(
            [(int(uid), data.get("comissoes_ganhas", 0)) for uid, data in parcerias.items()],
            key=lambda x: x[1],
            reverse=True
        )
        return ranking[:10]
