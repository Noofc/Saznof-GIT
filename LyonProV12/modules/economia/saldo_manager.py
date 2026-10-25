"""
Sistema de Economia Avançado - Gerenciador de Saldo
Responsável por todas as transações, depósitos, saques, empréstimos
"""

from typing import Optional, Dict, List
from datetime import datetime, timedelta
import json
from functions.database import database as db
from connections.mongo_db import collection as bot_collection

class SaldoManager:
    """Gerenciador completo de saldo e economia"""
    
    # Configurações padrão
    DEFAULT_ECONOMIA = {
        "usuarios": {},
        "transacoes": [],
        "taxas": {
            "transferencia": 0.05,  # 5%
            "saque": 0.02,          # 2%
            "emprestimo": 0.15,     # 15% de juros
            "cashback_compra": 0.02,  # 2% cashback
        },
        "limites": {
            "diarios": 10000,
            "por_transacao": 5000,
            "emprestimos": 2000,
            "poupanca_maxima": 50000,
        },
        "juros": {
            "emprestimo": 0.02,  # 2% ao dia
            "poupanca": 0.005,   # 0.5% ao dia na poupança
            "investimento": 0.01,  # 1% ao dia em investimentos
        },
        "cashback": {
            "ativo": True,
            "taxa_padrao": 0.02,
            "bonus_transferencia": 0.01,
        }
    }
    
    @staticmethod
    async def get_usuario(user_id: int) -> dict:
        """Obtém dados de economia do usuário"""
        doc = await bot_collection.find_one({"_id": "economia"})
        if not doc:
            return SaldoManager._criar_usuario_padrao()
        
        usuarios = doc.get("usuarios", {})
        user_id_str = str(user_id)
        
        if user_id_str not in usuarios:
            return SaldoManager._criar_usuario_padrao()
        
        return usuarios[user_id_str]
    
    @staticmethod
    def _criar_usuario_padrao() -> dict:
        """Cria um novo usuário com saldo padrão"""
        return {
            "saldo": 0,
            "saldo_congelado": 0,
            "saldo_poupanca": 0,  # Poupança com juros
            "reputacao": 0,
            "nivel": 1,
            "cashback_acumulado": 0,  # Cashback para próximas compras
            "data_criacao": datetime.now().isoformat(),
            "historico": [],
            "emprestimos": [],
            "investimentos": [],  # Investimentos de longo prazo
            "despesas_mes": [],  # Rastrear despesas
            "metas_poupanca": [],  # Metas de economia
            "cartoes_credito": [],  # Cartões virtuais
            "ultima_atualizacao_juros": datetime.now().isoformat(),
        }
    
    @staticmethod
    async def adicionar_saldo(user_id: int, valor: float, motivo: str = "Sem motivo") -> bool:
        """Adiciona saldo ao usuário"""
        if valor <= 0:
            return False
        
        try:
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.saldo": valor},
                    "$push": {
                        f"usuarios.{user_id}.historico": {
                            "tipo": "deposito",
                            "valor": valor,
                            "motivo": motivo,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"[Economia] Erro ao adicionar saldo: {e}")
            return False
    
    @staticmethod
    async def remover_saldo(user_id: int, valor: float, motivo: str = "Sem motivo") -> bool:
        """Remove saldo do usuário"""
        usuario = await SaldoManager.get_usuario(user_id)
        
        if usuario["saldo"] < valor:
            return False
        
        try:
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.saldo": -valor},
                    "$push": {
                        f"usuarios.{user_id}.historico": {
                            "tipo": "saque",
                            "valor": valor,
                            "motivo": motivo,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"[Economia] Erro ao remover saldo: {e}")
            return False
    
    @staticmethod
    async def transferir(usuario_origem: int, usuario_destino: int, valor: float) -> tuple[bool, str]:
        """Transfere saldo entre usuários com taxa"""
        origem = await SaldoManager.get_usuario(usuario_origem)
        taxa_percentual = (await SaldoManager.get_config())["taxas"]["transferencia"]
        taxa = valor * taxa_percentual
        total = valor + taxa
        
        if origem["saldo"] < total:
            return False, f"Você precisa de **{total:.2f}** (valor + taxa de {taxa_percentual*100:.1f}%)"
        
        try:
            # Remover da origem
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{usuario_origem}.saldo": -total},
                    "$push": {
                        f"usuarios.{usuario_origem}.historico": {
                            "tipo": "transferencia_enviada",
                            "valor": valor,
                            "taxa": taxa,
                            "destino": usuario_destino,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            # Adicionar ao destino
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{usuario_destino}.saldo": valor},
                    "$push": {
                        f"usuarios.{usuario_destino}.historico": {
                            "tipo": "transferencia_recebida",
                            "valor": valor,
                            "origem": usuario_origem,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            return True, f"✅ **{valor:.2f}** transferidos com sucesso! Taxa: **{taxa:.2f}**"
        except Exception as e:
            return False, f"❌ Erro na transferência: {e}"
    
    @staticmethod
    async def emprestar(user_id: int, valor: float) -> tuple[bool, str]:
        """Empresta saldo ao usuário com juros"""
        usuario = await SaldoManager.get_usuario(user_id)
        config = await SaldoManager.get_config()
        
        if valor > config["limites"]["emprestimos"]:
            return False, f"Limite de empréstimo: **{config['limites']['emprestimos']:.2f}**"
        
        try:
            # Calcular juros
            juros_totais = valor * config["juros"]["emprestimo"] * 7  # 7 dias
            data_vencimento = (datetime.now() + timedelta(days=7)).isoformat()
            
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.saldo": valor},
                    "$push": {
                        f"usuarios.{user_id}.emprestimos": {
                            "valor": valor,
                            "juros": juros_totais,
                            "total": valor + juros_totais,
                            "vencimento": data_vencimento,
                            "status": "ativo",
                            "data_criacao": datetime.now().isoformat(),
                        },
                        f"usuarios.{user_id}.historico": {
                            "tipo": "emprestimo",
                            "valor": valor,
                            "juros": juros_totais,
                            "vencimento": data_vencimento,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            return True, f"💳 Empréstimo aprovado!\n**Valor:** {valor:.2f}\n**Juros (7 dias):** {juros_totais:.2f}\n**Total a pagar:** {valor + juros_totais:.2f}"
        except Exception as e:
            return False, f"❌ Erro ao emprestar: {e}"
    
    @staticmethod
    async def pagar_emprestimo(user_id: int, emprestimo_id: int) -> tuple[bool, str]:
        """Paga um empréstimo específico"""
        usuario = await SaldoManager.get_usuario(user_id)
        
        if emprestimo_id >= len(usuario.get("emprestimos", [])):
            return False, "Empréstimo não encontrado"
        
        emprestimo = usuario["emprestimos"][emprestimo_id]
        total = emprestimo["total"]
        
        if usuario["saldo"] < total:
            return False, f"Saldo insuficiente. Você precisa de **{total:.2f}**"
        
        try:
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.saldo": -total},
                    "$set": {f"usuarios.{user_id}.emprestimos.{emprestimo_id}.status": "pago"},
                    "$push": {
                        f"usuarios.{user_id}.historico": {
                            "tipo": "emprestimo_pago",
                            "valor": total,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            return True, f"✅ Empréstimo pago com sucesso!"
        except Exception as e:
            return False, f"❌ Erro ao pagar empréstimo: {e}"
    
    @staticmethod
    async def depositar_poupanca(user_id: int, valor: float) -> tuple[bool, str]:
        """Transfere saldo para poupança (com juros)"""
        usuario = await SaldoManager.get_usuario(user_id)
        
        if usuario["saldo"] < valor:
            return False, f"Saldo insuficiente para depositar {valor:.2f}"
        
        try:
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {
                        f"usuarios.{user_id}.saldo": -valor,
                        f"usuarios.{user_id}.saldo_poupanca": valor
                    },
                    "$push": {
                        f"usuarios.{user_id}.historico": {
                            "tipo": "deposito_poupanca",
                            "valor": valor,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            return True, f"💰 **{valor:.2f}** depositado na poupança! Você ganhará juros diários."
        except Exception as e:
            return False, f"❌ Erro: {e}"
    
    @staticmethod
    async def sacar_poupanca(user_id: int, valor: float) -> tuple[bool, str]:
        """Saca da poupança"""
        usuario = await SaldoManager.get_usuario(user_id)
        poupanca = usuario.get("saldo_poupanca", 0)
        
        if poupanca < valor:
            return False, f"Poupança insuficiente. Disponível: {poupanca:.2f}"
        
        try:
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {
                        f"usuarios.{user_id}.saldo": valor,
                        f"usuarios.{user_id}.saldo_poupanca": -valor
                    },
                    "$push": {
                        f"usuarios.{user_id}.historico": {
                            "tipo": "saque_poupanca",
                            "valor": valor,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            return True, f"✅ **{valor:.2f}** sacado da poupança!"
        except Exception as e:
            return False, f"❌ Erro: {e}"
    
    @staticmethod
    async def calcular_juros_poupanca(user_id: int) -> float:
        """Calcula e aplica juros da poupança"""
        usuario = await SaldoManager.get_usuario(user_id)
        config = await SaldoManager.get_config()
        
        poupanca = usuario.get("saldo_poupanca", 0)
        if poupanca <= 0:
            return 0
        
        taxa_diaria = config["juros"]["poupanca"]
        juros = poupanca * taxa_diaria
        
        try:
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.saldo_poupanca": juros},
                    "$set": {f"usuarios.{user_id}.ultima_atualizacao_juros": datetime.now().isoformat()}
                },
                upsert=True
            )
            return juros
        except Exception as e:
            print(f"[Economia] Erro ao calcular juros: {e}")
            return 0
    
    @staticmethod
    async def adicionar_cashback(user_id: int, valor: float) -> bool:
        """Adiciona cashback ao usuário"""
        try:
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.cashback_acumulado": valor}
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"[Economia] Erro ao adicionar cashback: {e}")
            return False
    
    @staticmethod
    async def usar_cashback(user_id: int, valor: float) -> tuple[bool, str]:
        """Usa cashback acumulado"""
        usuario = await SaldoManager.get_usuario(user_id)
        cashback = usuario.get("cashback_acumulado", 0)
        
        if cashback < valor:
            return False, f"Cashback insuficiente. Disponível: {cashback:.2f}"
        
        try:
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {
                        f"usuarios.{user_id}.saldo": valor,
                        f"usuarios.{user_id}.cashback_acumulado": -valor
                    },
                    "$push": {
                        f"usuarios.{user_id}.historico": {
                            "tipo": "uso_cashback",
                            "valor": valor,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            return True, f"✅ **{valor:.2f}** de cashback utilizado!"
        except Exception as e:
            return False, f"❌ Erro: {e}"
    
    @staticmethod
    async def criar_investimento(user_id: int, valor: float, tipo: str) -> tuple[bool, str]:
        """Cria um novo investimento"""
        usuario = await SaldoManager.get_usuario(user_id)
        
        if usuario["saldo"] < valor:
            return False, f"Saldo insuficiente para investir {valor:.2f}"
        
        try:
            investimento = {
                "id": f"inv_{user_id}_{int(datetime.now().timestamp())}",
                "tipo": tipo,  # "longo_prazo", "curto_prazo", "alto_risco"
                "valor_inicial": valor,
                "valor_atual": valor,
                "retorno": 0,
                "taxa_esperada": {"longo_prazo": 0.01, "curto_prazo": 0.005, "alto_risco": 0.02}.get(tipo, 0.01),
                "data_criacao": datetime.now().isoformat(),
                "status": "ativo",
            }
            
            await bot_collection.update_one(
                {"_id": "economia"},
                {
                    "$inc": {f"usuarios.{user_id}.saldo": -valor},
                    "$push": {
                        f"usuarios.{user_id}.investimentos": investimento,
                        f"usuarios.{user_id}.historico": {
                            "tipo": "investimento_criado",
                            "valor": valor,
                            "tipo_investimento": tipo,
                            "data": datetime.now().isoformat(),
                        }
                    }
                },
                upsert=True
            )
            
            return True, f"📈 Investimento criado! Tipo: **{tipo}**\nValor: **{valor:.2f}**"
        except Exception as e:
            return False, f"❌ Erro: {e}"
    
    @staticmethod
    async def obter_resumo_financeiro(user_id: int) -> dict:
        """Obtém resumo financeiro completo do usuário"""
        usuario = await SaldoManager.get_usuario(user_id)
        
        saldo_total = usuario.get("saldo", 0)
        poupanca = usuario.get("saldo_poupanca", 0)
        cashback = usuario.get("cashback_acumulado", 0)
        investimentos = usuario.get("investimentos", [])
        valor_investido = sum(i.get("valor_atual", 0) for i in investimentos)
        emprestimos = usuario.get("emprestimos", [])
        dívida_total = sum(e.get("total", 0) for e in emprestimos if e.get("status") == "ativo")
        
        return {
            "saldo_principal": saldo_total,
            "poupanca": poupanca,
            "cashback": cashback,
            "valor_investido": valor_investido,
            "divida_total": dívida_total,
            "saldo_liquido": saldo_total + poupanca + cashback + valor_investido - dívida_total,
            "investimentos": len(investimentos),
            "emprestimos_ativos": len([e for e in emprestimos if e.get("status") == "ativo"]),
        }
    
    @staticmethod
    async def get_config() -> dict:
        """Obtém configuração de economia"""
        doc = await bot_collection.find_one({"_id": "economia"})
        if not doc:
            return SaldoManager.DEFAULT_ECONOMIA
        return doc
    
    @staticmethod
    async def get_ranking() -> List[tuple[int, float]]:
        """Obtém ranking de usuários por saldo"""
        doc = await bot_collection.find_one({"_id": "economia"})
        if not doc:
            return []
        
        usuarios = doc.get("usuarios", {})
        ranking = sorted(
            [(int(uid), data.get("saldo", 0)) for uid, data in usuarios.items()],
            key=lambda x: x[1],
            reverse=True
        )
        return ranking[:20]  # Top 20
