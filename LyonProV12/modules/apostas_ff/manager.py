"""
Sistema de Apostas em Free Fire
Gerencia partidas, apostas, odds e prêmios
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta
from enum import Enum
from connections.mongo_db import collection as bot_collection
import random

class StatusPartida(Enum):
    ABERTA = "aberta"
    EM_PROGRESSO = "em_progresso"
    ENCERRADA = "encerrada"
    CANCELADA = "cancelada"

class ApostasFFManager:
    """Gerenciador de apostas em Free Fire"""
    
    DEFAULT_CONFIG = {
        "partidas": {},
        "apostas": {},
        "estatisticas_apostadores": {},
        "odds": {
            "favorito": 1.5,
            "underdog": 3.0,
            "draw": 2.0,
        },
        "taxa_casa": 0.05,  # 5% de taxa
        "limites": {
            "minima": 10,
            "maxima": 1000,
        },
        "tempo_fechamento_apostas": 3600,  # 1 hora antes da partida
        "bonus_vencedor": {
            "3_vitorias_seguidas": 100,
            "maior_odd_ganhou": 250,
        }
    }
    
    @staticmethod
    async def criar_partida(
        equipe1: str,
        equipe2: str,
        data_inicio: str,
        poder1: int = 50,
        poder2: int = 50
    ) -> tuple[bool, str, Optional[str]]:
        """Cria uma nova partida para apostas"""
        try:
            partida_id = f"ff_{int(datetime.now().timestamp())}"
            
            partida = {
                "id": partida_id,
                "equipe1": equipe1,
                "equipe2": equipe2,
                "poder1": poder1,  # 1-100
                "poder2": poder2,
                "data_inicio": data_inicio,
                "status": StatusPartida.ABERTA.value,
                "resultado": None,  # "equipe1", "equipe2", "empate"
                "apostas_total": 0,
                "apostas_e1": 0,
                "apostas_e2": 0,
                "apostas_empate": 0,
                "data_criacao": datetime.now().isoformat(),
            }
            
            await bot_collection.update_one(
                {"_id": "apostas_ff"},
                {
                    "$set": {f"partidas.{partida_id}": partida}
                },
                upsert=True
            )
            
            return True, f"✅ Partida criada: **{equipe1}** vs **{equipe2}**", partida_id
        except Exception as e:
            return False, f"❌ Erro: {e}", None
    
    @staticmethod
    async def fazer_aposta(
        user_id: int,
        partida_id: str,
        valor: float,
        escolha: str  # "equipe1", "equipe2", "empate"
    ) -> tuple[bool, str, Optional[float]]:
        """Realiza uma aposta em uma partida"""
        
        # Validar partida
        doc = await bot_collection.find_one({"_id": "apostas_ff"})
        if not doc or partida_id not in doc.get("partidas", {}):
            return False, "❌ Partida não encontrada", None
        
        partida = doc["partidas"][partida_id]
        config = await ApostasFFManager.get_config()
        
        # Validar status
        if partida["status"] != StatusPartida.ABERTA.value:
            return False, "❌ Apostas fechadas para esta partida", None
        
        # Validar valor
        if valor < config["limites"]["minima"] or valor > config["limites"]["maxima"]:
            return False, f"❌ Aposta deve ser entre {config['limites']['minima']} e {config['limites']['maxima']}", None
        
        # Validar saldo
        usuario = await bot_collection.find_one(
            {"_id": "economia"},
            {f"usuarios.{user_id}": 1}
        )
        
        if not usuario or usuario.get("usuarios", {}).get(str(user_id), {}).get("saldo", 0) < valor:
            return False, "❌ Saldo insuficiente", None
        
        try:
            # Remover saldo
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.saldo": -valor},
                    "$push": {
                        f"usuarios.{user_id}.historico": {
                            "tipo": "aposta_ff",
                            "valor": valor,
                            "partida": partida_id,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            # Calcular odd dinâmico antes de registrar a aposta
            odds = await ApostasFFManager.calcular_odds_dinamicas(partida_id)
            odd = odds.get(escolha)
            if odd is None:
                odd = config["odds"]["draw"]
            
            # Registrar aposta
            aposta_id = f"aposta_{user_id}_{partida_id}_{int(datetime.now().timestamp())}"
            
            await bot_collection.update_one(
                {"_id": "apostas_ff"},
                {
                    "$set": {
                        f"apostas.{aposta_id}": {
                            "usuario": user_id,
                            "partida": partida_id,
                            "valor": valor,
                            "escolha": escolha,
                            "odd": odd,
                            "status": "ativa",
                            "data": datetime.now().isoformat(),
                        }
                    },
                    "$inc": {
                        f"partidas.{partida_id}.apostas_total": valor,
                        f"partidas.{partida_id}.apostas_{escolha}": valor,
                    }
                }
            )
            
            return True, f"✅ Aposta realizada!\n**Valor:** {valor}\n**Odd:** {odd}x", valor * odd
        except Exception as e:
            print(f"[Apostas FF] Erro: {e}")
            return False, f"❌ Erro ao realizar aposta: {e}", None
    
    @staticmethod
    async def encerrar_partida(
        partida_id: str,
        resultado: str  # "equipe1", "equipe2", "empate"
    ) -> tuple[bool, str]:
        """Encerra uma partida e distribui prêmios"""
        try:
            doc = await bot_collection.find_one({"_id": "apostas_ff"})
            if not doc or partida_id not in doc.get("partidas", {}):
                return False, "❌ Partida não encontrada"
            
            partida = doc["partidas"][partida_id]
            config = await ApostasFFManager.get_config()
            
            # Calcular prêmios e atualizar o status das apostas
            apostas = doc.get("apostas", {})
            total_apostado = partida.get("apostas_total", 0)
            taxa = total_apostado * config["taxa_casa"]
            total_premios = total_apostado - taxa
            
            for aposta_id, aposta in apostas.items():
                if aposta.get("partida") != partida_id:
                    continue
                
                status = "ganhou" if aposta.get("escolha") == resultado else "perdeu"
                await bot_collection.update_one(
                    {"_id": "apostas_ff"},
                    {"$set": {f"apostas.{aposta_id}.status": status}}
                )
                
                if status == "ganhou":
                    odd = aposta.get("odd", config["odds"].get("favorito", 1.5))
                    premio = aposta.get("valor", 0) * odd
                    await bot_collection.update_one(
                        {"_id": "economia"},
                        {
                            "$inc": {f"usuarios.{aposta['usuario']}.saldo": premio},
                            "$push": {
                                f"usuarios.{aposta['usuario']}.historico": {
                                    "tipo": "aposta_ff_ganhou",
                                    "valor": premio,
                                    "partida": partida_id,
                                    "data": datetime.now().isoformat(),
                                }
                            }
                        },
                        upsert=True
                    )
            
            await bot_collection.update_one(
                {"_id": "apostas_ff"},
                {
                    "$set": {
                        f"partidas.{partida_id}.status": StatusPartida.ENCERRADA.value,
                        f"partidas.{partida_id}.resultado": resultado,
                    }
                }
            )
            
            return True, f"✅ Partida encerrada! Resultado: **{resultado}**\n💰 Total de prêmios distribuídos: {total_premios:.2f}"
        except Exception as e:
            print(f"[Apostas FF] Erro ao encerrar partida: {e}")
            return False, f"❌ Erro: {e}"
    
    @staticmethod
    async def calcular_odds_dinamicas(partida_id: str) -> dict:
        """Calcula odds em tempo real baseado nas apostas"""
        doc = await bot_collection.find_one({"_id": "apostas_ff"})
        if not doc or partida_id not in doc.get("partidas", {}):
            return {}
        
        partida = doc["partidas"][partida_id]
        apostas_e1 = partida.get("apostas_e1", 0) or 1
        apostas_e2 = partida.get("apostas_e2", 0) or 1
        apostas_empate = partida.get("apostas_empate", 0) or 1
        total_apostas = partida.get("apostas_total", 0) or 1
        
        taxa_casa = 0.05
        
        # Calcular odds dinâmicas com margem da casa
        odd_e1 = ((total_apostas * (1 - taxa_casa)) / apostas_e1) if apostas_e1 > 0 else 1.5
        odd_e2 = ((total_apostas * (1 - taxa_casa)) / apostas_e2) if apostas_e2 > 0 else 1.5
        odd_empate = ((total_apostas * (1 - taxa_casa)) / apostas_empate) if apostas_empate > 0 else 2.0
        
        return {
            "equipe1": round(max(1.1, odd_e1), 2),
            "equipe2": round(max(1.1, odd_e2), 2),
            "empate": round(max(1.1, odd_empate), 2),
        }
    
    @staticmethod
    async def obter_estatisticas_apostador(user_id: int) -> dict:
        """Obtém estatísticas de um apostador"""
        doc = await bot_collection.find_one({"_id": "apostas_ff"})
        if not doc:
            return {"total_apostas": 0, "taxa_acerto": 0, "lucro": 0}
        
        apostas = doc.get("apostas", {})
        user_apostas = [a for a in apostas.values() if a.get("usuario") == user_id]
        
        if not user_apostas:
            return {"total_apostas": 0, "taxa_acerto": 0, "lucro": 0, "vitorias": 0, "derrotas": 0}
        
        total_apostas = len(user_apostas)
        vitorias = sum(1 for a in user_apostas if a.get("status") == "ganhou")
        derrotas = total_apostas - vitorias
        taxa_acerto = (vitorias / total_apostas * 100) if total_apostas > 0 else 0
        
        # Calcular lucro total
        valor_apostado = sum(a.get("valor", 0) for a in user_apostas)
        # Aqui você somaria os prêmios recebidos do histórico
        
        return {
            "total_apostas": total_apostas,
            "vitorias": vitorias,
            "derrotas": derrotas,
            "taxa_acerto": round(taxa_acerto, 2),
            "valor_apostado_total": valor_apostado,
        }
    
    @staticmethod
    async def obter_ranking_apostadores() -> List[tuple[int, dict]]:
        """Obtém ranking de apostadores por taxa de acerto"""
        doc = await bot_collection.find_one({"_id": "apostas_ff"})
        if not doc:
            return []
        
        apostas = doc.get("apostas", {})
        usuarios = {}
        
        for aposta in apostas.values():
            uid = aposta.get("usuario")
            if uid not in usuarios:
                usuarios[uid] = {"vitorias": 0, "total": 0}
            
            usuarios[uid]["total"] += 1
            if aposta.get("status") == "ganhou":
                usuarios[uid]["vitorias"] += 1
        
        # Calcular taxa de acerto
        ranking = []
        for uid, stats in usuarios.items():
            taxa = (stats["vitorias"] / stats["total"] * 100) if stats["total"] > 0 else 0
            ranking.append((uid, {"taxa_acerto": taxa, "total_apostas": stats["total"], "vitorias": stats["vitorias"]}))
        
        ranking.sort(key=lambda x: x[1]["taxa_acerto"], reverse=True)
        return ranking[:20]
    
    @staticmethod
    async def get_config() -> dict:
        """Obtém configuração"""
        doc = await bot_collection.find_one({"_id": "apostas_ff"})
        if not doc:
            return ApostasFFManager.DEFAULT_CONFIG
        return doc
    
    @staticmethod
    async def listar_partidas_abertas() -> List[dict]:
        """Lista partidas abertas para apostas"""
        doc = await bot_collection.find_one({"_id": "apostas_ff"})
        if not doc:
            return []
        
        partidas = doc.get("partidas", {})
        abertas = [p for p in partidas.values() if p["status"] == StatusPartida.ABERTA.value]
        return abertas[:10]
    
    @staticmethod
    async def get_apostas_usuario(user_id: int) -> List[dict]:
        """Obtém apostas ativas de um usuário"""
        doc = await bot_collection.find_one({"_id": "apostas_ff"})
        if not doc:
            return []
        
        apostas = doc.get("apostas", {})
        user_apostas = [
            {**v, "id": k} for k, v in apostas.items()
            if v.get("usuario") == user_id and v.get("status") == "ativa"
        ]
        return user_apostas
