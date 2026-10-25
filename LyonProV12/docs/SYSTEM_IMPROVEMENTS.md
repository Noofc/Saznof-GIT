# Sistema Pro - Documentação de Melhorias Implementadas

## 📋 Visão Geral

Este documento detalha todas as melhorias implementadas nos novos sistemas de economia, parcerias, apostas Free Fire, comunidade e ferramentas avançadas.

---

## 🏦 Sistema de Economia (`modules/economia/`)

### Funcionalidades Principais

#### 1. **Gerenciamento de Saldo**
- `adicionar_saldo()` - Adiciona saldo ao usuário
- `remover_saldo()` - Remove saldo com registro
- `transferir()` - Transferências entre usuários com taxa (5% default)
- `emprestar()` - Empréstimos com juros (2% ao dia)
- `pagar_emprestimo()` - Quitação de empréstimos

#### 2. **Poupança com Juros**
- `depositar_poupanca()` - Transferir saldo para poupança
- `sacar_poupanca()` - Sacar da poupança
- `calcular_juros_poupanca()` - Cálculo automático de juros diários (0.5%)

#### 3. **Cashback e Investimentos**
- `adicionar_cashback()` - Acumular cashback (2% de compras)
- `usar_cashback()` - Usar cashback acumulado
- `criar_investimento()` - Criar investimentos (curto/longo prazo/alto risco)
- `obter_resumo_financeiro()` - Resumo completo financeiro

#### 4. **Configurações de Limite**
```javascript
{
    "limites": {
        "diarios": 10000,        // Limite diário total
        "por_transacao": 5000,   // Limite por transação
        "emprestimos": 2000,     // Limite de empréstimo
        "poupanca_maxima": 50000 // Limite de poupança
    }
}
```

#### 5. **Taxas Aplicadas**
```javascript
{
    "taxas": {
        "transferencia": 0.05,           // 5%
        "saque": 0.02,                   // 2%
        "emprestimo": 0.15,              // 15% (juros)
        "cashback_compra": 0.02          // 2% cashback
    }
}
```

### Comandos Disponíveis

- `/economia` - Painel principal de economia
- `/transferir [usuário] [valor]` - Transferir saldo
- `/emprestar [valor]` - Solicitar empréstimo
- `/ranking_economia` - Ranking de usuários por saldo

---

## 🤝 Sistema de Parcerias (`modules/parcerias/`)

### Funcionalidades Principais

#### 1. **Criação e Gerenciamento de Parcerias**
- `criar_parceria()` - Criar nova parceria com bônus inicial (50)
- `registrar_venda()` - Registrar vendas e calcular comissões com bônus de tier
- `adicionar_afiliado()` - Adicionar afiliado à rede com bônus (25)
- `verificar_bonus_performance()` - Verificar bônus de meta semanal

#### 2. **Sistema de Tiers com Comissões Progressivas**

```javascript
{
    "tiers": {
        "bronze": {
            "vendas_minimas": 0,
            "comissao_extra": 0,
            "bônus_nivel": 50
        },
        "prata": {
            "vendas_minimas": 5000,
            "comissao_extra": 0.02,      // +2% adicional
            "bônus_nivel": 200
        },
        "ouro": {
            "vendas_minimas": 20000,
            "comissao_extra": 0.05,      // +5% adicional
            "bônus_nivel": 500
        },
        "platina": {
            "vendas_minimas": 50000,
            "comissao_extra": 0.10,      // +10% adicional
            "bônus_nivel": 1000
        }
    }
}
```

#### 3. **Estrutura de Comissões**
```javascript
{
    "comissoes": {
        "venda_direta": 0.10,    // 10%
        "indicacao": 0.05,        // 5%
        "compra_afiliado": 0.03,  // 3%
        "referencia": 0.02        // 2%
    }
}
```

#### 4. **Bônus de Performance**
- Meta semanal de 5000 em vendas
- Recompensa: 200 por atingir meta
- Cálculo automático com verificação de tier

### Comando de Exemplo de Comissão

```python
# Venda de 1000 com tier Ouro (comissão extra 5%)
# Comissão base: 1000 * 10% = 100
# Bônus tier: 1000 * 5% = 50
# Total: 150
```

### Comandos Disponíveis

- `/parceria` - Painel de parcerias
- `/criar_parceria [nome] [tipo]` - Criar nova parceria
- `/ranking_parceiros` - Ranking de parceiros por comissão

---

## 🎮 Sistema de Apostas Free Fire (`modules/apostas_ff/`)

### Funcionalidades Principais

#### 1. **Gerenciamento de Partidas**
- `criar_partida()` - Criar partida com poder das equipes (1-100)
- `listar_partidas_abertas()` - Listar partidas disponíveis
- `encerrar_partida()` - Encerrar partida e distribuir prêmios

#### 2. **Sistema de Apostas Dinâmico**
- `fazer_aposta()` - Realizar aposta com odds calculadas dinamicamente
- `calcular_odds_dinamicas()` - Calcular odds em tempo real baseado em volume de apostas
- `get_apostas_usuario()` - Listar apostas ativas do usuário

#### 3. **Odds Dinâmicas com Margem da Casa**

```python
# Cálculo de odd dinâmica:
# odd_e1 = ((total_apostado * 0.95) / apostas_e1) * fator
# - Total apostado: soma de todas as apostas
# - 0.95: margem da casa (5%)
# - Fator: ajuste baseado em poder da equipe
```

#### 4. **Configuração de Limites**
```javascript
{
    "limites": {
        "minima": 10,      // Aposta mínima
        "maxima": 1000     // Aposta máxima
    },
    "tempo_fechamento_apostas": 3600  // 1 hora antes da partida
}
```

#### 5. **Sistema de Estatísticas**
- `obter_estatisticas_apostador()` - Stats do usuário (taxa de acerto, vencidas, perdidas)
- `obter_ranking_apostadores()` - Top 20 apostadores por taxa de acerto

#### 6. **Melhorias Implementadas**

✅ **Odds calculadas antes de registrar aposta**
- Odd armazenada no documento da aposta
- Cálculo dinâmico baseado em volume

✅ **Status de aposta no término**
- "ganhou" ou "perdeu" registrado na aposta
- Prêmio calculado com base na odd armazenada

✅ **Histórico completo de transações**
- Cada aposta registrada no histórico do usuário
- Rastreamento de prêmios por partida

### Comandos Disponíveis

- `/apostas_ff` - Painel de apostas
- `/apostar_ff [partida_id] [valor] [escolha]` - Realizar aposta
- `/criar_partida_ff [equipe1] [equipe2] [poder1] [poder2]` - Criar partida (Admin)

---

## 👥 Sistema de Comunidade (`modules/comunidade/`)

### Funcionalidades Principais

#### 1. **Perfis de Usuários**
- `get_perfil_usuario()` - Obter perfil com nível, pontos, reputação
- `inicializar_missoes_diarias()` - Inicializar missões do dia
- `completar_missao()` - Marcar missão como completa

#### 2. **Sistema de Conquistas**
- Conquistas desbloqueáveis com emojis
- Progressão de nível baseada em pontos
- Reputação acumulada através de ações

#### 3. **Ranking e Eventos**
- `get_ranking_geral()` - Top 10 usuários por pontos
- `get_eventos_ativos()` - Lista de eventos em andamento
- `adicionar_amigo()` - Sistema de amigos com bonificação

#### 4. **Missões Diárias**
Exemplos de missões que podem ser inicializadas:
- Fazer X transações
- Participar de X apostas
- Ganhar X reputação
- Adicionar X amigos

### Comandos Disponíveis

- `/perfil [usuário]` - Ver perfil de usuário
- `/ranking_comunidade` - Ranking geral
- `/eventos` - Ver eventos ativos
- `/adicionar_amigo [usuário]` - Adicionar amigo

---

## 🛠️ Sistema de Ferramentas (`modules/ferramentas/`)

### Calculadoras Implementadas

#### 1. **Calculadora de Lucro de Parceria**
```python
resultado = calcular_lucro_parceria(
    vendas=1000,
    comissao_percentual=0.10,  # 10%
    taxa_casa=0.05             # 5%
)
# Retorna: comissão_bruta, taxa, comissão_líquida
```

#### 2. **Juros Compostos**
```python
resultado = calcular_juros_compostos(
    principal=1000,
    taxa_diaria=0.02,  # 2%
    dias=7
)
# Retorna: juros acumulados, montante total
```

#### 3. **ROI (Return on Investment)**
```python
resultado = calcular_retorno_investimento(
    investimento_inicial=1000,
    investimento_final=1200,
    periodo_dias=30
)
# Retorna: lucro, ROI%, ROI diário
```

#### 4. **Break-Even Point**
```python
resultado = calcular_breakeven(
    custo_fixo=1000,
    custo_variavel_unitario=5,
    preco_venda_unitario=15
)
# Retorna: unidades break-even, receita necessária
```

#### 5. **Meta de Poupança** ✨ NOVO
```python
resultado = calcular_meta_poupanca(
    user_id=123456,
    meta_final=5000,
    prazo_dias=30
)
# Retorna: depósito diário/semanal/mensal necessário
```

#### 6. **Comparação de Taxas** ✨ NOVO
```python
resultado = calcular_taxas_comparativas(valor_base=1000)
# Compara rendimento em: poupança, empréstimo, investimento
```

#### 7. **Sugestão de Investimento**
```python
resultado = sugerir_investimento(
    saldo_usuario=10000,
    risco="moderado"  # conservador/moderado/agressivo
)
# Retorna: alocação recomendada por percentual
```

#### 8. **Relatório de Economia**
```python
relatorio = gerar_relatorio_usuario(user_id=123456)
# Retorna: dados compilados de economia, comunidade, parcerias
```

### Análise de Mercado

#### 1. **Análise de Apostas Free Fire**
- Total apostado
- Total de usuários ativos
- Média por aposta
- Top 5 equipes mais apostadas
- Número de partidas

#### 2. **Análise de Economia Geral**
- Total na economia
- Média de saldo por usuário
- Usuários ativos
- Saldo máximo/mínimo

### Comandos Disponíveis

- `/ferramentas_economia` - Menu principal de ferramentas
- `/calcular_lucro [vendas] [comissão]` - Cálculo de lucro
- `/calcular_juros [valor] [dias] [taxa]` - Juros compostos
- `/meu_relatorio` - Relatório pessoal
- `/analise_mercado` - Análise geral do servidor
- `/meta_poupanca [valor_meta] [prazo_dias]` - ✨ NOVO
- `/comparar_taxas [valor]` - ✨ NOVO

---

## 📊 Estrutura de Dados MongoDB

### Documentos Principais

#### Economia
```javascript
{
    "_id": "economia",
    "usuarios": {
        "123456": {
            "saldo": 1000,
            "saldo_congelado": 0,
            "saldo_poupanca": 500,
            "cashback_acumulado": 50,
            "investimentos": [],
            "emprestimos": [],
            "historico": []
        }
    }
}
```

#### Parcerias
```javascript
{
    "_id": "parcerias",
    "parcerias": {
        "123456": {
            "nome": "Minha Loja",
            "tipo": "loja",
            "tier": "bronze",
            "vendas_totais": 5000,
            "comissoes_ganhas": 500,
            "afiliados": [654321, 789012]
        }
    }
}
```

#### Apostas Free Fire
```javascript
{
    "_id": "apostas_ff",
    "partidas": {
        "ff_1234567890": {
            "equipe1": "Team A",
            "equipe2": "Team B",
            "poder1": 75,
            "poder2": 60,
            "status": "aberta",
            "apostas_total": 5000,
            "apostas_e1": 3000,
            "apostas_e2": 2000
        }
    },
    "apostas": {
        "aposta_123456_ff_1234567890_1234567890": {
            "usuario": 123456,
            "partida": "ff_1234567890",
            "valor": 100,
            "escolha": "equipe1",
            "odd": 1.67,
            "status": "ganhou"
        }
    }
}
```

#### Comunidade
```javascript
{
    "_id": "comunidade",
    "usuarios": {
        "123456": {
            "nivel": 5,
            "pontos": 1500,
            "reputacao": 200,
            "conquistas": ["primeira_aposta", "100_pontos"],
            "amigos": [654321, 789012],
            "missoes_diarias": []
        }
    }
}
```

---

## 🔄 Fluxos de Negócio

### Fluxo de Venda e Comissão
```
1. Registrar Venda
   ↓
2. Calcular Comissão (base + tier bonus)
   ↓
3. Atualizar vendas_totais do parceiro
   ↓
4. Atualizar comissoes_ganhas
   ↓
5. Verificar mudança de tier
   ↓
6. Se mudou de tier: dar bônus de nível
   ↓
7. Transferir comissão para economia
```

### Fluxo de Aposta
```
1. Usuário faz aposta
   ↓
2. Validar saldo
   ↓
3. Calcular odd dinâmica em tempo real
   ↓
4. Remover saldo do usuário
   ↓
5. Registrar aposta com odd calculada
   ↓
6. Atualizar volume de apostas na partida
   ↓
   [Admin encerra partida]
   ↓
7. Marcar apostas como "ganhou" ou "perdeu"
   ↓
8. Calcular prêmio: aposta * odd
   ↓
9. Transferir prêmio para economia
```

### Fluxo de Juros Diários
```
[Task scheduler - executar 1x por dia]
   ↓
1. Para cada usuário com poupança > 0
   ↓
2. Calcular: juros = saldo_poupanca * 0.5%
   ↓
3. Adicionar juros à poupança
   ↓
4. Registrar no histórico
```

---

## ✨ Melhorias Realizadas Nesta Sessão

### 1. **Free Fire Betting (Apostas FF)**
- ✅ Odds dinâmicas calculadas **antes** de registrar aposta (não após)
- ✅ Odd armazenada no documento da aposta para consistência
- ✅ Status de aposta ("ganhou"/"perdeu") atualizado no término da partida
- ✅ Prêmio calculado com a odd armazenada, não com taxa fixa

### 2. **Partnership Lyon (Parcerias)**
- ✅ Método `obter_comissao_com_bonus()` integrado ao registrar_venda()
- ✅ Tier automático incluído no documento de parceria ("bronze" como padrão)
- ✅ Bônus progressivo aplicado automaticamente baseado em tier
- ✅ Verificação de tier mudança integrada

### 3. **Economy Lyon (Economia)**
- ✅ Corrigido acesso ao índice de juros: `config["juros"]["emprestimo"]` ao invés de `config["juros_emprestimo"]`
- ✅ Todos os cálculos de juros agora consistentes

### 4. **Tools Module (Ferramentas)**
- ✅ Novos comandos: `/meta_poupanca` e `/comparar_taxas`
- ✅ Novos métodos: `calcular_meta_poupanca()` e `calcular_taxas_comparativas()`
- ✅ Melhor integração de análise de mercado
- ✅ Relatório consolidado do usuário

### 5. **Code Quality**
- ✅ Imports corrigidos (timedelta adicionado em parcerias)
- ✅ Setup functions verificadas e padronizadas
- ✅ Configurações consolidadas em DEFAULT_* dicts
- ✅ Documentação inline melhorada

---

## 🚀 Como Usar

### Inicializar o Pro
```python
# main.py
from disnake.ext import commands
from modules import setup

bot = commands.Bot(command_prefix="/")

# Carregar módulos
setup(bot)

bot.run("SEU_TOKEN")
```

### Exemplo de Fluxo de Usuário

```python
# 1. Usuário faz uma venda através de parceria
await ParceriasManager.registrar_venda(user_id=123456, valor=1000, tipo_venda="direta")
# → Comissão 10% = 100 + bônus tier automaticamente aplicado

# 2. Usuário aposta em Free Fire
sucesso, msg, premio = await ApostasFFManager.fazer_aposta(
    user_id=123456,
    partida_id="ff_1234567890",
    valor=100,
    escolha="equipe1"
)
# → Odd calculada dinamicamente: 1.67x (exemplo)

# 3. Usuário consulta ferramentas
resultado = FerramentasEconomia.calcular_taxas_comparativas(1000)
# → Compara poupança, empréstimo, investimento
```

---

## 📝 Notas Importantes

1. **MongoDB Collection**: Todos os dados são persistidos em `bot_collection` do MongoDB
2. **Async/Await**: Todas as operações de banco são assíncronas
3. **Validações**: Sempre validam saldo, limites e status antes de transações
4. **Histórico**: Todas as transações deixam registro no histórico do usuário
5. **Taxas**: Aplicadas automaticamente em transferências, empréstimos, etc.

---

## 🔐 Segurança

- ✅ Validação de saldo antes de qualquer transação
- ✅ Congelamento de saldo durante apostas
- ✅ Taxa da casa protege contra perda total de saldo em apostas
- ✅ Limite máximo/mínimo por transação
- ✅ Registro de auditoria em histórico

---

Documento atualizado com as melhorias implementadas em 2024.
