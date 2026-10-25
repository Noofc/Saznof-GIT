# 🎮 Sistema Pro - Novos Sistemas Implementados

Documentação completa dos 5 novos sistemas avançados e funcionais implementados.

---

## 📚 Índice

1. [Sistema de Economia](#sistema-de-economia)
2. [Parcerias Automáticas](#parcerias-automáticas)
3. [Apostas Free Fire](#apostas-free-fire)
4. [Sistema de Comunidade](#sistema-de-comunidade)
5. [Ferramentas Avançadas](#ferramentas-avançadas)

---

## 💰 Sistema de Economia

Sistema completo de gerenciamento de saldo, transações, empréstimos e investimentos.

### Funcionalidades Principais

- **Saldo Principal**: Gerenciamento de moeda única do servidor
- **Saldo Congelado**: Saldo indisponível por apostas/empréstimos
- **Transferências**: Entre usuários com taxa de 5%
- **Empréstimos**: Com juros compostos de 2% ao dia
- **Histórico**: Rastreamento completo de transações
- **Reputação**: Sistema baseado em atividades
- **Níveis**: Progressão conforme saldo aumenta

### Comandos

```
/economia                 - Painel principal de economia
/transferir [usuário] [valor]  - Transferir saldo
/emprestar [valor]        - Solicitar empréstimo
/ranking_economia         - Ver ranking de saldo
```

### Estrutura de Dados

```json
{
  "usuario": {
    "saldo": 1000.50,
    "saldo_congelado": 50.00,
    "reputacao": 100,
    "nivel": 5,
    "historico": [
      {
        "tipo": "deposito|saque|transferencia|emprestimo",
        "valor": 100,
        "motivo": "Razão da transação",
        "data": "2025-05-17T10:30:00"
      }
    ],
    "emprestimos": [
      {
        "valor": 500,
        "juros": 70,
        "total": 570,
        "vencimento": "2025-05-24",
        "status": "ativo|pago"
      }
    ]
  }
}
```

### Taxas e Limites

| Item | Valor |
|------|-------|
| Taxa de Transferência | 5% |
| Taxa de Saque | 2% |
| Juros Empréstimo | 2% ao dia |
| Limite Diário | 10.000 |
| Limite por Transação | 5.000 |
| Limite Empréstimo | 2.000 |

---

## 🤝 Parcerias Automáticas

Sistema de afiliados e comissões automáticas para monetização.

### Funcionalidades Principais

- **Criar Parceria**: Registrar como parceiro (loja, creator, intermediário)
- **Comissões Automáticas**: 
  - Venda direta: 10%
  - Por indicação: 5%
  - Compra de afiliado: 3%
- **Bônus de Ativação**: 50 moedas ao criar parceria
- **Sistema de Níveis**: Sobe com volume de vendas
- **Rede de Afiliados**: Gerencie sua rede de parceiros
- **Recompensas por Nível**: Bônus progressivo

### Comandos

```
/parceria                 - Ver painel de parcerias
/criar_parceria [nome] [tipo]  - Criar nova parceria
/ranking_parceiros        - Ver top parceiros
```

### Tipos de Parceria

1. **Loja**: Revenda de produtos diretos
2. **Creator**: Criador de conteúdo com comissão
3. **Intermediário**: Conexão entre compradores e vendedores

### Progressão de Níveis

- **Nível 1**: 0 - 1.000 em vendas
- **Nível 2**: 1.000 - 2.000 em vendas
- **Nível 3**: 2.000 - 3.000 em vendas
- Cada nível sobe recebe bônus em moedas = nível × 100

---

## 🎮 Apostas Free Fire

Sistema completo de apostas em partidas com odds dinâmicas.

### Funcionalidades Principais

- **Criar Partidas**: Admin cria partidas com equipes e poder
- **Sistema de Odds**: Dinâmico baseado em apostas
- **Múltiplas Escolhas**:
  - Equipe 1
  - Equipe 2
  - Empate
- **Cálculo de Prêmios**: Distribuição automática
- **Histórico de Apostas**: Rastreamento completo
- **Taxa da Casa**: 5% de todas as apostas

### Comandos

```
/apostas_ff               - Painel de apostas
/apostar_ff [partida] [valor] [escolha]  - Fazer aposta
/criar_partida_ff [eq1] [eq2] [poder1] [poder2]  - Admin criar partida
```

### Odds Padrão

| Tipo | Odd |
|------|-----|
| Favorito (maior poder) | 1.5x |
| Underdog (menor poder) | 3.0x |
| Empate | 2.0x |

### Limites de Apostas

- Mínima: 10 moedas
- Máxima: 1.000 moedas
- Fechamento: 1 hora antes da partida

### Fluxo de uma Aposta

```
1. Admin cria partida (FF_1234)
2. Usuários fazem apostas (10-1000 moedas)
3. Partida inicia em 30 minutos
4. Admin marca resultado (equipe1/equipe2/empate)
5. Prêmios distribuídos automaticamente
6. Histórico atualizado
```

---

## 👥 Sistema de Comunidade

Engajamento comunitário com ranking, conquistas e eventos.

### Funcionalidades Principais

- **Perfil de Usuário**:
  - Nível (baseado em pontos)
  - Pontos (100 = 1 nível)
  - Reputação (por atividades)
  - Bio personalizada
  - Título customizável

- **Conquistas**: 5 conquistáveis
  - 🎲 Primeira Aposta
  - 💰 Milionário
  - 🤝 Parceiro
  - 🦋 Social Butterfly
  - 📈 Investidor

- **Sistema de Amigos**:
  - Adicionar/remover amigos
  - Conexões bilaterais
  - Limite: nenhum

- **Eventos Comunitários**:
  - Criados por admins
  - Prêmios automáticos
  - Participação voluntária
  - Duração configurável

- **Ranking Geral**:
  - Top 50 por pontos
  - Inclui reputação como critério secundário

### Comandos

```
/perfil [usuário]        - Ver perfil de comunidade
/ranking_comunidade      - Ver ranking geral
/eventos                 - Listar eventos ativos
/adicionar_amigo [usuário]  - Adicionar amigo
```

### Sistema de Pontos

| Atividade | Pontos |
|-----------|--------|
| Primeira Aposta | 10 |
| Criar Parceria | 50 |
| Social Butterfly | 30 |
| Milionário | 100 |
| Investidor | 75 |

### Progressão

- 0-99 pontos: Nível 1 (Novato)
- 100-199: Nível 2 (Aprendiz)
- 200-299: Nível 3 (Experiente)
- Etc... (100 pontos por nível)

---

## 🛠️ Ferramentas Avançadas

Calculadoras, analisadores e utilitários de economia.

### Ferramentas Disponíveis

#### 1. **Calculador de Lucro de Parceria**
```
Entrada: Vendas, % Comissão
Saída:
- Comissão bruta
- Taxa da casa (5%)
- Lucro líquido
```

#### 2. **Juros Compostos**
```
Entrada: Principal, Taxa Diária, Dias
Saída:
- Juros gerados
- Montante total
- Comparação diária
```

#### 3. **ROI Calculator** (Retorno de Investimento)
```
Entrada: Investimento Inicial, Final, Período
Saída:
- Lucro absoluto
- ROI %
- ROI Diário
```

#### 4. **Breakeven Analysis** (Ponto de Equilíbrio)
```
Entrada: Custo Fixo, Custo Variável, Preço Venda
Saída:
- Unidades para breakeven
- Receita necessária
```

#### 5. **Sugestor de Investimento**
Baseado em risco:
- **Conservador**: 70% reserva, 15% parceria, 10% apostas
- **Moderado**: 40% reserva, 25% parceria, 20% apostas
- **Agressivo**: 10% reserva, 35% apostas, 35% parceria

#### 6. **Relatório de Usuário**
```
- Economia (saldo, nível, reputação)
- Comunidade (pontos, conquistas, amigos)
- Parcerias (vendas, comissões, afiliados)
- Data do relatório
```

#### 7. **Análise de Mercado**
```
Apostas FF:
- Total apostado
- Número de usuários
- Equipes mais apostadas
- Número de partidas

Economia Geral:
- Total em circulação
- Média de saldo
- Usuários ativos
- Distribuição de riqueza
```

### Comandos

```
/ferramentas_economia    - Menu de ferramentas
/calcular_lucro [vendas] [comissao%]
/calcular_juros [valor] [dias] [taxa%]
/meu_relatorio           - Gerar relatório pessoal
/analise_mercado         - Análise geral do servidor
```

---

## 🔄 Integração entre Sistemas

```
┌─────────────────────┐
│   ECONOMIA          │
│ - Saldo Principal   │
│ - Transações        │
│ - Empréstimos       │
└──────────┬──────────┘
           │
      ┌────┴────┐
      │          │
      ▼          ▼
┌────────────┐  ┌──────────────┐
│PARCERIAS   │  │ APOSTAS FF   │
│- Comissões │  │ - Prêmios    │
│- Afiliados │  │ - Taxas      │
└────────────┘  └──────────────┘
      │                 │
      │      ┌──────────┴─────────┐
      │      │                    │
      ▼      ▼                    ▼
   ┌──────────────────────────────────┐
   │  COMUNIDADE                      │
   │  - Pontos por atividades         │
   │  - Reputação                     │
   │  - Conquistas                    │
   │  - Ranking                       │
   └──────────────────────────────────┘
           │
           ▼
   ┌──────────────────────────────────┐
   │  FERRAMENTAS                     │
   │  - Análise de todos os sistemas  │
   │  - Relatórios                    │
   │  - Calculadoras                  │
   │  - Tendências                    │
   └──────────────────────────────────┘
```

---

## 💾 Estrutura de Banco de Dados

### Coleções MongoDB

1. **economia**
   - Saldo de usuários
   - Histórico de transações
   - Empréstimos
   - Configurações

2. **parcerias**
   - Dados de parcerias
   - Comissões
   - Afiliados
   - Histórico de vendas

3. **apostas_ff**
   - Partidas criadas
   - Apostas realizadas
   - Resultados
   - Prêmios

4. **comunidade**
   - Perfis de usuários
   - Pontos e níveis
   - Conquistas desbloqueadas
   - Eventos
   - Amigos

---

## 🚀 Como Usar

### 1. Começar com Economia
```
/economia                    # Ver seu saldo
/transferir @user 100        # Transferir 100 moedas
/emprestar 500               # Pedir empréstimo de 500
```

### 2. Criar Parceria
```
/criar_parceria "Minha Loja" "loja"
                             # Recebe 50 moedas bônus
/ranking_parceiros           # Ver top parceiros
```

### 3. Apostar em Free Fire
```
/apostas_ff                  # Ver partidas abertas
/apostar_ff ff_1234 100 equipe1
                             # Apostar 100 na equipe 1
```

### 4. Participar da Comunidade
```
/perfil                      # Ver seu perfil
/ranking_comunidade          # Ver rankings
/eventos                     # Ver eventos ativos
```

### 5. Usar Ferramentas
```
/ferramentas_economia        # Menu de ferramentas
/calcular_lucro 1000 10      # Calcular lucro
/meu_relatorio              # Gerar relatório completo
```

---

## 📊 Estatísticas e Métricas

Todos os sistemas rastreiam:
- ✅ Transações completas
- ✅ Histórico de atividades
- ✅ Pontos e progressão
- ✅ Reputação
- ✅ Rankings
- ✅ Tendências
- ✅ Análises

---

## 🔐 Segurança

- Validação de saldo antes de transações
- Limite de transações por período
- Histórico auditável
- Estatísticas em tempo real
- Verificação de permissões

---

## 📈 Roadmap Futuro

- [ ] Sistema de investimentos de longo prazo
- [ ] Moeda premium (cosmética)
- [ ] Leilões entre usuários
- [ ] Casino (jogos de azar)
- [ ] Missões diárias
- [ ] Seasonal passes
- [ ] Achievements em Discord
- [ ] Pro Mobile
- [ ] Dashboard web
- [ ] API pública

---

## 🆘 Suporte

Para dúvidas ou problemas:
1. Verifique a documentação
2. Use `/ferramentas_economia` para análises
3. Contacte um administrador
4. Revise seu histórico de transações

---

**Versão**: 1.0.0  
**Data**: 17 de Maio de 2025  
**Status**: ✅ Operacional
