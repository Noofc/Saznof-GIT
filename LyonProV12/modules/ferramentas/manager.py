"""
Sistema de Ferramentas Avançadas para Economia
Calculadoras, conversores, análises e utilitários
"""

from typing import Optional, Dict, List
from datetime import datetime, timedelta
from connections.mongo_db import collection as bot_collection

class FerramentasEconomia:
    """Ferramentas para análise de economia"""
    
    @staticmethod
    async def calcular_lucro_parceria(
        vendas: float,
        comissao_percentual: float = 0.10,
        taxa_casa: float = 0.05
    ) -> dict:
        """Calcula lucro de uma parceria"""
        lucro_bruto = vendas * comissao_percentual
        taxa = lucro_bruto * taxa_casa
        lucro_liquido = lucro_bruto - taxa
        
        return {
            "vendas": vendas,
            "comissao_percentual": comissao_percentual * 100,
            "comissao_bruta": lucro_bruto,
            "taxa": taxa,
            "comissao_liquida": lucro_liquido,
            "taxa_percentual": taxa_casa * 100,
        }
    
    @staticmethod
    def calcular_juros_compostos(
        principal: float,
        taxa_diaria: float = 0.02,
        dias: int = 7
    ) -> dict:
        """Calcula juros compostos de um empréstimo"""
        montante = principal * ((1 + taxa_diaria) ** dias)
        juros = montante - principal
        
        return {
            "principal": principal,
            "taxa_diaria": taxa_diaria * 100,
            "dias": dias,
            "juros": juros,
            "montante_total": montante,
        }
    
    @staticmethod
    def calcular_odd_aposta(
        apostas_vencedoras: float,
        apostas_totais: float,
        margem_casa: float = 0.05
    ) -> float:
        """Calcula a odd de uma aposta"""
        if apostas_vencedoras == 0:
            return 1.0
        
        odd_pura = apostas_totais / apostas_vencedoras
        odd_com_margem = odd_pura * (1 - margem_casa)
        
        return round(odd_com_margem, 2)
    
    @staticmethod
    def calcular_retorno_investimento(
        investimento_inicial: float,
        investimento_final: float,
        periodo_dias: int = 30
    ) -> dict:
        """Calcula retorno de investimento"""
        lucro = investimento_final - investimento_inicial
        roi_percentual = (lucro / investimento_inicial * 100) if investimento_inicial > 0 else 0
        roi_diario = roi_percentual / periodo_dias if periodo_dias > 0 else 0
        
        return {
            "investimento_inicial": investimento_inicial,
            "investimento_final": investimento_final,
            "lucro": lucro,
            "roi_percentual": roi_percentual,
            "roi_diario": roi_diario,
            "periodo_dias": periodo_dias,
        }
    
    @staticmethod
    def calcular_breakeven(
        custo_fixo: float,
        custo_variavel_unitario: float,
        preco_venda_unitario: float
    ) -> dict:
        """Calcula ponto de equilíbrio"""
        margem_contribuicao = preco_venda_unitario - custo_variavel_unitario
        
        if margem_contribuicao <= 0:
            return {"erro": "Preço de venda deve ser maior que custo variável"}
        
        unidades_breakeven = custo_fixo / margem_contribuicao
        receita_breakeven = unidades_breakeven * preco_venda_unitario
        
        return {
            "custo_fixo": custo_fixo,
            "custo_variavel": custo_variavel_unitario,
            "preco_venda": preco_venda_unitario,
            "margem_contribuicao": margem_contribuicao,
            "unidades_breakeven": round(unidades_breakeven, 2),
            "receita_breakeven": round(receita_breakeven, 2),
        }
    
    @staticmethod
    def sugerir_investimento(saldo_usuario: float, risco: str = "moderado") -> dict:
        """Sugere estratégia de investimento baseada no saldo"""
        estrategias = {
            "conservador": {
                "apostas": 0.10,           # 10%
                "emprestimos": 0.05,       # 5%
                "parceria": 0.15,          # 15%
                "reserva": 0.70,           # 70%
            },
            "moderado": {
                "apostas": 0.20,
                "emprestimos": 0.15,
                "parceria": 0.25,
                "reserva": 0.40,
            },
            "agressivo": {
                "apostas": 0.35,
                "emprestimos": 0.20,
                "parceria": 0.35,
                "reserva": 0.10,
            }
        }
        
        perfil = estrategias.get(risco, estrategias["moderado"])
        
        return {
            "saldo_total": saldo_usuario,
            "perfil_risco": risco,
            "alocacao": {
                k: round(saldo_usuario * v, 2)
                for k, v in perfil.items()
            },
            "descricao": f"Estratégia {risco}: " + ", ".join([
                f"{k}: {v*100:.0f}%" for k, v in perfil.items()
            ])
        }
    
    @staticmethod
    async def gerar_relatorio_usuario(user_id: int) -> dict:
        """Gera relatório completo de economia do usuário"""
        
        # Dados de economia
        econ_doc = await bot_collection.find_one(
            {"_id": "economia"},
            {f"usuarios.{user_id}": 1}
        )
        usuario_econ = econ_doc.get("usuarios", {}).get(str(user_id), {}) if econ_doc else {}
        
        # Dados de comunidade
        com_doc = await bot_collection.find_one(
            {"_id": "comunidade"},
            {f"usuarios.{user_id}": 1}
        )
        usuario_com = com_doc.get("usuarios", {}).get(str(user_id), {}) if com_doc else {}
        
        # Dados de parcerias
        par_doc = await bot_collection.find_one(
            {"_id": "parcerias"},
            {f"parcerias.{user_id}": 1}
        )
        usuario_par = par_doc.get("parcerias", {}).get(str(user_id), {}) if par_doc else {}
        
        return {
            "usuario_id": user_id,
            "data_relatorio": datetime.now().isoformat(),
            "economia": {
                "saldo": usuario_econ.get("saldo", 0),
                "saldo_congelado": usuario_econ.get("saldo_congelado", 0),
                "nivel": usuario_econ.get("nivel", 1),
                "reputacao": usuario_econ.get("reputacao", 0),
                "emprestimos_ativos": len([e for e in usuario_econ.get("emprestimos", []) if e["status"] == "ativo"]),
            },
            "comunidade": {
                "nivel": usuario_com.get("nivel", 1),
                "pontos": usuario_com.get("pontos", 0),
                "conquistas": len(usuario_com.get("conquistas", [])),
                "amigos": len(usuario_com.get("amigos", [])),
            },
            "parcerias": {
                "nome": usuario_par.get("nome", "Sem parceria"),
                "vendas_totais": usuario_par.get("vendas_totais", 0),
                "comissoes_ganhas": usuario_par.get("comissoes_ganhas", 0),
                "afiliados": len(usuario_par.get("afiliados", [])),
            }
        }
    
    @staticmethod
    @staticmethod
    def calcular_meta_poupanca(user_id: int, meta_final: float, prazo_dias: int = 30) -> dict:
        """Calcula estratégia para atingir meta de poupança"""
        deposito_necessario = meta_final / prazo_dias if prazo_dias > 0 else meta_final
        
        return {
            "usuario_id": user_id,
            "meta": meta_final,
            "prazo_dias": prazo_dias,
            "deposito_diario": deposito_necessario,
            "deposito_semanal": deposito_necessario * 7,
            "deposito_mensal": deposito_necessario * 30,
        }
    
    @staticmethod
    def calcular_taxas_comparativas(valor_base: float) -> dict:
        """Compara diferentes investimentos no mesmo valor"""
        poupanca_7dias = valor_base * (1 + 0.005) ** 7
        emprestimo_7dias = valor_base * (1 + 0.02) ** 7
        investimento_longo_7dias = valor_base * (1 + 0.01) ** 7
        
        return {
            "poupanca": {
                "taxa": 0.5,
                "rendimento": poupanca_7dias - valor_base,
                "retorno_percentual": ((poupanca_7dias - valor_base) / valor_base * 100) if valor_base > 0 else 0,
            },
            "emprestimo": {
                "taxa": 2.0,
                "rendimento": emprestimo_7dias - valor_base,
                "retorno_percentual": ((emprestimo_7dias - valor_base) / valor_base * 100) if valor_base > 0 else 0,
            },
            "investimento": {
                "taxa": 1.0,
                "rendimento": investimento_longo_7dias - valor_base,
                "retorno_percentual": ((investimento_longo_7dias - valor_base) / valor_base * 100) if valor_base > 0 else 0,
            }
        }

class AnalisadorMercado:
    """Analisa tendências e padrões de mercado"""
    
    @staticmethod
    async def analisar_apostas_ff() -> dict:
        """Analisa tendências de apostas em Free Fire"""
        doc = await bot_collection.find_one({"_id": "apostas_ff"})
        if not doc:
            return {"erro": "Sem dados de apostas"}
        
        partidas = doc.get("partidas", {})
        apostas = doc.get("apostas", {})
        
        total_apostado = sum(p.get("apostas_total", 0) for p in partidas.values())
        total_usuarios = len(set(a.get("usuario") for a in apostas.values()))
        
        # Equipes mais apostadas
        equipes_apostas = {}
        for partida in partidas.values():
            e1 = partida.get("equipe1")
            e2 = partida.get("equipe2")
            equipes_apostas[e1] = equipes_apostas.get(e1, 0) + partida.get("apostas_e1", 0)
            equipes_apostas[e2] = equipes_apostas.get(e2, 0) + partida.get("apostas_e2", 0)
        
        return {
            "total_apostado": total_apostado,
            "total_usuarios": total_usuarios,
            "media_aposta": total_apostado / total_usuarios if total_usuarios > 0 else 0,
            "equipes_top": sorted(equipes_apostas.items(), key=lambda x: x[1], reverse=True)[:5],
            "numero_partidas": len(partidas),
        }
    
    @staticmethod
    async def analisar_economia_geral() -> dict:
        """Analisa saúde econômica geral do servidor"""
        doc = await bot_collection.find_one({"_id": "economia"})
        if not doc:
            return {"erro": "Sem dados de economia"}
        
        usuarios = doc.get("usuarios", {})
        
        saldos = [u.get("saldo", 0) for u in usuarios.values()]
        total_economia = sum(saldos)
        media_saldo = total_economia / len(usuarios) if usuarios else 0
        
        return {
            "total_economia": total_economia,
            "media_saldo": media_saldo,
            "usuarios_ativos": len(usuarios),
            "saldo_maximo": max(saldos) if saldos else 0,
            "saldo_minimo": min(saldos) if saldos else 0,
        }
