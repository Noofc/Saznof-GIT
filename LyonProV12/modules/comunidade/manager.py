"""
Sistema de Comunidade
Gerencia ranking, reputação, conquistas e eventos
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta
from enum import Enum
from connections.mongo_db import collection as bot_collection

class TipoConquista(Enum):
    PRIMEIRA_APOSTA = "primeira_aposta"
    MILIONARIO = "milionario"
    PARCEIRO = "parceiro"
    SOCIAL_BUTTERFLY = "social_butterfly"
    INVESTIDOR = "investidor"

class ComunidadeManager:
    """Gerenciador de comunidade e engagement"""
    
    CONQUISTAS = {
        "primeira_aposta": {
            "nome": "Primeira Aposta",
            "descricao": "Realize sua primeira aposta",
            "emoji": "🎲",
            "pontos": 10,
        },
        "milionario": {
            "nome": "Milionário",
            "descricao": "Acumule 1.000.000 em saldo",
            "emoji": "💰",
            "pontos": 100,
        },
        "parceiro": {
            "nome": "Parceiro",
            "descricao": "Crie uma parceria",
            "emoji": "🤝",
            "pontos": 50,
        },
        "social_butterfly": {
            "nome": "Social Butterfly",
            "descricao": "Tenha 10 transações com usuários diferentes",
            "emoji": "🦋",
            "pontos": 30,
        },
        "investidor": {
            "nome": "Investidor",
            "descricao": "Faça investimentos totalizando 10.000",
            "emoji": "📈",
            "pontos": 75,
        },
        "colecionador": {
            "nome": "Colecionador",
            "descricao": "Desbloqueie 10 conquistas",
            "emoji": "🏆",
            "pontos": 150,
        },
        "apostador_sorte": {
            "nome": "Apostador de Sorte",
            "descricao": "Ganhe 5 apostas seguidas",
            "emoji": "🍀",
            "pontos": 80,
        },
        "rei_da_comunidade": {
            "nome": "Rei da Comunidade",
            "descricao": "Fique no topo do ranking por 7 dias",
            "emoji": "👑",
            "pontos": 200,
        },
    }
    
    MISSOES_DIARIAS = {
        "aposta_diaria": {
            "nome": "Apostador Diário",
            "descricao": "Faça uma aposta",
            "emoji": "🎲",
            "recompensa": 20,
            "tipo": "aposta",
        },
        "transferencia_diaria": {
            "nome": "Generoso",
            "descricao": "Transfira saldo para 2 usuários",
            "emoji": "💸",
            "recompensa": 30,
            "tipo": "transferencia",
        },
        "venda_diaria": {
            "nome": "Vendedor",
            "descricao": "Realize uma venda",
            "emoji": "🛒",
            "recompensa": 50,
            "tipo": "venda",
        },
        "achado_diario": {
            "nome": "Explorador",
            "descricao": "Explore 5 seções diferentes do bot",
            "emoji": "🔍",
            "recompensa": 25,
            "tipo": "explorar",
        },
        "social_diario": {
            "nome": "Social",
            "descricao": "Adicione 3 novos amigos",
            "emoji": "👥",
            "recompensa": 35,
            "tipo": "amigos",
        },
    }
    
    DEFAULT_CONFIG = {
        "usuarios": {},
        "eventos": [],
        "temporada_atual": 1,
        "data_inicio_temporada": datetime.now().isoformat(),
        "premios_temporada": {
            "1_lugar": 5000,
            "2_lugar": 3000,
            "3_lugar": 1000,
        }
    }
    
    @staticmethod
    async def get_perfil_usuario(user_id: int) -> dict:
        """Obtém perfil completo de um usuário"""
        doc = await bot_collection.find_one({"_id": "comunidade"})
        if not doc:
            return ComunidadeManager._perfil_padrao()
        
        usuarios = doc.get("usuarios", {})
        user_id_str = str(user_id)
        
        if user_id_str not in usuarios:
            return ComunidadeManager._perfil_padrao()
        
        return usuarios[user_id_str]
    
    @staticmethod
    def _perfil_padrao() -> dict:
        """Perfil padrão de um novo usuário"""
        return {
            "nivel": 1,
            "pontos": 0,
            "reputacao": 0,
            "conquistas": [],
            "conectados": 0,
            "data_entrada": datetime.now().isoformat(),
            "atividades": [],
            "amigos": [],
            "bloqueados": [],
            "bio": "",
            "titulo": "Novato",
        }
    
    @staticmethod
    async def desbloquear_conquista(user_id: int, conquista_id: str) -> tuple[bool, str]:
        """Desbloqueia uma conquista para o usuário"""
        if conquista_id not in ComunidadeManager.CONQUISTAS:
            return False, "Conquista não encontrada"
        
        conquista = ComunidadeManager.CONQUISTAS[conquista_id]
        
        # Verificar se já tem
        usuario = await ComunidadeManager.get_perfil_usuario(user_id)
        if conquista_id in usuario.get("conquistas", []):
            return False, "Você já tem esta conquista"
        
        try:
            await bot_collection.update_one(
                {"_id": "comunidade"},
                {
                    "$push": {
                        f"usuarios.{user_id}.conquistas": conquista_id,
                        f"usuarios.{user_id}.atividades": {
                            "tipo": "conquista",
                            "conquista": conquista_id,
                            "data": datetime.now().isoformat(),
                        }
                    },
                    "$inc": {
                        f"usuarios.{user_id}.pontos": conquista["pontos"],
                        f"usuarios.{user_id}.reputacao": 10,
                    }
                },
                upsert=True
            )
            
            # Verificar e fazer levelup
            await ComunidadeManager._verificar_levelup(user_id)
            
            return True, f"🏆 Conquista desbloqueada: **{conquista['nome']}**\n+{conquista['pontos']} pontos!"
        except Exception as e:
            return False, f"Erro: {e}"
    
    @staticmethod
    async def _verificar_levelup(user_id: int):
        """Verifica se o usuário deve fazer levelup"""
        usuario = await ComunidadeManager.get_perfil_usuario(user_id)
        pontos = usuario.get("pontos", 0)
        nivel_atual = usuario.get("nivel", 1)
        
        # 100 pontos por nível
        novo_nivel = max(1, int(pontos / 100) + 1)
        
        if novo_nivel > nivel_atual:
            await bot_collection.update_one(
                {"_id": "comunidade"},
                {
                    "$set": {f"usuarios.{user_id}.nivel": novo_nivel},
                    "$inc": {f"usuarios.{user_id}.reputacao": 50}
                }
            )
    
    @staticmethod
    async def adicionar_amigo(user_id: int, amigo_id: int) -> tuple[bool, str]:
        """Adiciona um amigo à lista"""
        try:
            # Verificar se já são amigos
            usuario = await ComunidadeManager.get_perfil_usuario(user_id)
            if amigo_id in usuario.get("amigos", []):
                return False, "Você já são amigos"
            
            # Adicionar mutuamente
            await bot_collection.update_one(
                {"_id": "comunidade"},
                {
                    "$push": {
                        f"usuarios.{user_id}.amigos": amigo_id,
                        f"usuarios.{amigo_id}.amigos": user_id,
                    }
                },
                upsert=True
            )
            
            return True, f"✅ Amizade adicionada!"
        except Exception as e:
            return False, f"Erro: {e}"
    
    @staticmethod
    async def inicializar_missoes_diarias(user_id: int) -> bool:
        """Inicializa as missões diárias de um usuário"""
        try:
            missoes_usuario = {}
            for missao_id, missao_info in ComunidadeManager.MISSOES_DIARIAS.items():
                missoes_usuario[missao_id] = {
                    "nome": missao_info["nome"],
                    "descricao": missao_info["descricao"],
                    "recompensa": missao_info["recompensa"],
                    "progresso": 0,
                    "meta": 1,  # Meta padrão (específica por tipo de missão)
                    "completa": False,
                    "data_inicio": datetime.now().isoformat(),
                    "data_reset": (datetime.now() + timedelta(days=1)).isoformat(),
                }
            
            await bot_collection.update_one(
                {"_id": "comunidade"},
                {
                    "$set": {f"usuarios.{user_id}.missoes_diarias": missoes_usuario}
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"[Comunidade] Erro ao inicializar missões: {e}")
            return False
    
    @staticmethod
    async def completar_missao(user_id: int, missao_id: str) -> tuple[bool, int]:
        """Completa uma missão diária e retorna a recompensa"""
        usuario = await ComunidadeManager.get_perfil_usuario(user_id)
        missoes = usuario.get("missoes_diarias", {})
        
        if missao_id not in missoes:
            return False, 0
        
        missao = missoes[missao_id]
        if missao.get("completa"):
            return False, 0
        
        recompensa = missao.get("recompensa", 0)
        
        try:
            # Marcar como completa e dar recompensa
            await bot_collection.update_one(
                {"_id": "comunidade"},
                {
                    "$set": {f"usuarios.{user_id}.missoes_diarias.{missao_id}.completa": True},
                    "$inc": {
                        f"usuarios.{user_id}.pontos": recompensa,
                        f"usuarios.{user_id}.reputacao": 5,
                    }
                },
                upsert=True
            )
            
            # Verificar levelup
            await ComunidadeManager._verificar_levelup(user_id)
            
            return True, recompensa
        except Exception as e:
            print(f"[Comunidade] Erro ao completar missão: {e}")
            return False, 0
    
    @staticmethod
    async def criar_evento(nome: str, descricao: str, premio: float, duracao_horas: int = 24) -> tuple[bool, str]:
        """Cria um novo evento comunitário"""
        try:
            evento = {
                "id": f"evento_{int(datetime.now().timestamp())}",
                "nome": nome,
                "descricao": descricao,
                "premio": premio,
                "inicio": datetime.now().isoformat(),
                "fim": (datetime.now() + timedelta(hours=duracao_horas)).isoformat(),
                "participantes": [],
                "status": "ativo",
            }
            
            await bot_collection.update_one(
                {"_id": "comunidade"},
                {
                    "$push": {"eventos": evento}
                },
                upsert=True
            )
            
            return True, f"📢 Evento criado: **{nome}**"
        except Exception as e:
            return False, f"Erro: {e}"
    
    @staticmethod
    async def participar_evento(user_id: int, evento_id: str) -> tuple[bool, str]:
        """Usuário participa de um evento"""
        try:
            await bot_collection.update_one(
                {"_id": "comunidade"},
                {
                    "$push": {
                        f"eventos.$[evento].participantes": user_id
                    }
                },
                array_filters=[{"evento.id": evento_id}],
                upsert=True
            )
            
            return True, "✅ Você está participando do evento!"
        except Exception as e:
            return False, f"Erro: {e}"
    
    @staticmethod
    async def get_ranking_geral() -> List[tuple[int, dict]]:
        """Obtém ranking geral de usuários"""
        doc = await bot_collection.find_one({"_id": "comunidade"})
        if not doc:
            return []
        
        usuarios = doc.get("usuarios", {})
        ranking = sorted(
            [(int(uid), data) for uid, data in usuarios.items()],
            key=lambda x: (x[1].get("pontos", 0), x[1].get("reputacao", 0)),
            reverse=True
        )
        return ranking[:50]
    
    @staticmethod
    async def get_eventos_ativos() -> List[dict]:
        """Obtém eventos ativos"""
        doc = await bot_collection.find_one({"_id": "comunidade"})
        if not doc:
            return []
        
        eventos = doc.get("eventos", [])
        agora = datetime.now().isoformat()
        ativos = [e for e in eventos if e.get("status") == "ativo" and e.get("fim") > agora]
        return ativos
