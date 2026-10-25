# 🗄️ MongoDB Queries & Admin Commands

## 📌 Propósito
Referência rápida de queries MongoDB para gerenciar dados do bot.

---

## 💰 Economia

### Ver Saldo de Usuário
```javascript
db.bot_data.findOne({"_id": "economia"}, {"usuarios.123456": 1})
```

### Ver Top 10 Usuários por Saldo
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "economia"}},
    {$project: {"usuarios": 1}},
    {$set: {usuarios: {$objectToArray: "$usuarios"}}},
    {$unwind: "$usuarios"},
    {$sort: {"usuarios.v.saldo": -1}},
    {$limit: 10}
])
```

### Transferir Saldo Direto (Admin)
```javascript
db.bot_data.updateOne(
    {"_id": "economia"},
    {
        $inc: {"usuarios.123456.saldo": 1000},
        $push: {"usuarios.123456.historico": {
            tipo: "admin_transfer",
            valor: 1000,
            motivo: "Prêmio evento",
            data: new Date()
        }}
    }
)
```

### Resetar Saldo de Usuário
```javascript
db.bot_data.updateOne(
    {"_id": "economia"},
    {$set: {"usuarios.123456": {
        saldo: 0,
        saldo_congelado: 0,
        nivel: 1,
        reputacao: 0,
        historico: [],
        data_criacao: new Date()
    }}}
)
```

### Ver Empréstimos Ativos
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "economia"}},
    {$project: {"usuarios": 1}},
    {$set: {usuarios: {$objectToArray: "$usuarios"}}},
    {$unwind: "$usuarios"},
    {$project: {
        user_id: "$usuarios.k",
        emprestimos: {$filter: {
            input: "$usuarios.v.emprestimos",
            as: "emp",
            cond: {$eq: ["$$emp.status", "ativo"]}
        }}
    }},
    {$match: {emprestimos: {$ne: []}}}
])
```

### Limpar Poupança de Todos
```javascript
db.bot_data.updateOne(
    {"_id": "economia"},
    {$set: {"usuarios.$[].saldo_poupanca": 0}}
)
```

---

## 🤝 Parcerias

### Ver Parceria de Usuário
```javascript
db.bot_data.findOne({"_id": "parcerias"}, {"parcerias.123456": 1})
```

### Ver Ranking de Parceiros
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "parcerias"}},
    {$project: {"parcerias": 1}},
    {$set: {parcerias: {$objectToArray: "$parcerias"}}},
    {$unwind: "$parcerias"},
    {$sort: {"parcerias.v.comissoes_ganhas": -1}},
    {$limit: 20}
])
```

### Atualizar Tier Manualmente
```javascript
db.bot_data.updateOne(
    {"_id": "parcerias"},
    {$set: {"parcerias.123456.tier": "ouro"}}
)
```

### Zerar Comissões (Manutenção)
```javascript
db.bot_data.updateOne(
    {"_id": "parcerias"},
    {$set: {"parcerias.$[].comissoes_ganhas": 0}}
)
```

### Ver Afiliados de um Parceiro
```javascript
db.bot_data.findOne(
    {"_id": "parcerias"},
    {"parcerias.123456.afiliados": 1}
)
```

---

## 🎮 Apostas Free Fire

### Ver Todas as Partidas Abertas
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "apostas_ff"}},
    {$project: {"partidas": 1}},
    {$set: {partidas: {$objectToArray: "$partidas"}}},
    {$unwind: "$partidas"},
    {$match: {"partidas.v.status": "aberta"}}
])
```

### Ver Apostas de um Usuário
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "apostas_ff"}},
    {$project: {"apostas": 1}},
    {$set: {apostas: {$objectToArray: "$apostas"}}},
    {$unwind: "$apostas"},
    {$match: {"apostas.v.usuario": 123456}}
])
```

### Calcular Total Apostado em uma Partida
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "apostas_ff"}},
    {$project: {"apostas": 1}},
    {$set: {apostas: {$objectToArray: "$apostas"}}},
    {$unwind: "$apostas"},
    {$match: {"apostas.v.partida": "ff_1234567890"}},
    {$group: {
        _id: "$apostas.v.partida",
        total_apostado: {$sum: "$apostas.v.valor"},
        total_usuarios: {$sum: 1}
    }}
])
```

### Atualizar Status de Partida
```javascript
db.bot_data.updateOne(
    {"_id": "apostas_ff"},
    {$set: {"partidas.ff_1234567890.status": "encerrada"}}
)
```

### Ver Taxa de Acerto de Usuário
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "apostas_ff"}},
    {$project: {"apostas": 1}},
    {$set: {apostas: {$objectToArray: "$apostas"}}},
    {$unwind: "$apostas"},
    {$match: {"apostas.v.usuario": 123456}},
    {$group: {
        _id: "$apostas.v.usuario",
        total: {$sum: 1},
        vitorias: {
            $sum: {
                $cond: [{$eq: ["$apostas.v.status", "ganhou"]}, 1, 0]
            }
        }
    }},
    {$project: {
        taxa_acerto: {$multiply: [{$divide: ["$vitorias", "$total"]}, 100]}
    }}
])
```

### Deletar Partida
```javascript
db.bot_data.updateOne(
    {"_id": "apostas_ff"},
    {$unset: {"partidas.ff_1234567890": ""}}
)
```

---

## 👥 Comunidade

### Ver Perfil de Usuário
```javascript
db.bot_data.findOne({"_id": "comunidade"}, {"usuarios.123456": 1})
```

### Ver Top 10 Ranking Comunidade
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "comunidade"}},
    {$project: {"usuarios": 1}},
    {$set: {usuarios: {$objectToArray: "$usuarios"}}},
    {$unwind: "$usuarios"},
    {$sort: {"usuarios.v.pontos": -1}},
    {$limit: 10}
])
```

### Dar Conquista a Usuário
```javascript
db.bot_data.updateOne(
    {"_id": "comunidade"},
    {
        $push: {"usuarios.123456.conquistas": "nova_conquista"},
        $inc: {"usuarios.123456.pontos": 100}
    }
)
```

### Remover Pontos de Usuário (Punição)
```javascript
db.bot_data.updateOne(
    {"_id": "comunidade"},
    {$inc: {"usuarios.123456.pontos": -500}}
)
```

### Ver Amigos de Usuário
```javascript
db.bot_data.findOne(
    {"_id": "comunidade"},
    {"usuarios.123456.amigos": 1}
)
```

---

## 🛠️ Queries Administrativas

### Contar Total de Usuários Ativos
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "economia"}},
    {$project: {
        total_usuarios: {$size: {$objectToArray: "$usuarios"}}
    }}
])
```

### Saldo Total no Sistema
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "economia"}},
    {$project: {"usuarios": 1}},
    {$set: {usuarios: {$objectToArray: "$usuarios"}}},
    {$unwind: "$usuarios"},
    {$group: {
        _id: null,
        total_saldo: {$sum: "$usuarios.v.saldo"},
        total_poupanca: {$sum: "$usuarios.v.saldo_poupanca"}
    }}
])
```

### Ver Movimentações Últimas 24h
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "economia"}},
    {$project: {"usuarios": 1}},
    {$set: {usuarios: {$objectToArray: "$usuarios"}}},
    {$unwind: "$usuarios"},
    {$unwind: "$usuarios.v.historico"},
    {$match: {
        "usuarios.v.historico.data": {
            $gte: new Date(Date.now() - 24*60*60*1000)
        }
    }},
    {$limit: 50}
])
```

### Usuários com Saldo > 10000
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "economia"}},
    {$project: {"usuarios": 1}},
    {$set: {usuarios: {$objectToArray: "$usuarios"}}},
    {$unwind: "$usuarios"},
    {$match: {"usuarios.v.saldo": {$gt: 10000}}},
    {$sort: {"usuarios.v.saldo": -1}}
])
```

### Média de Saldo por Usuário
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "economia"}},
    {$project: {"usuarios": 1}},
    {$set: {usuarios: {$objectToArray: "$usuarios"}}},
    {$unwind: "$usuarios"},
    {$group: {
        _id: null,
        media_saldo: {$avg: "$usuarios.v.saldo"},
        total_usuarios: {$sum: 1}
    }}
])
```

---

## 🔄 Operações em Lote

### Aumentar Saldo de Todos os Usuários (Evento)
```javascript
db.bot_data.updateOne(
    {"_id": "economia"},
    {$inc: {"usuarios.$[].saldo": 500}}
)
```

### Adicionar Pontos a Todos (Evento Comunidade)
```javascript
db.bot_data.updateOne(
    {"_id": "comunidade"},
    {$inc: {"usuarios.$[].pontos": 100}}
)
```

### Remover Todas as Apostas Ativas (Manutenção)
```javascript
db.bot_data.aggregate([
    {$match: {"_id": "apostas_ff"}},
    {$project: {"apostas": 1}},
    {$set: {apostas: {$objectToArray: "$apostas"}}},
    {$unwind: "$apostas"},
    {$match: {"apostas.v.status": "ativa"}}
])
```

Depois delete com:
```javascript
db.bot_data.updateOne(
    {"_id": "apostas_ff"},
    {$set: {"apostas": {}}}  // ⚠️ CUIDADO: Remove todas apostas
)
```

---

## 🔐 Backup & Restore

### Export Dados de Usuário Específico
```javascript
db.bot_data.find({
    $or: [
        {"usuarios.123456": {$exists: true}},
        {"parcerias.123456": {$exists: true}},
        {"comunidade.usuarios.123456": {$exists: true}}
    ]
})
```

### Duplicar Dados de um Usuário
```javascript
var source = db.bot_data.findOne(
    {"_id": "economia"},
    {"usuarios.111111": 1}
);

db.bot_data.updateOne(
    {"_id": "economia"},
    {$set: {"usuarios.222222": source.usuarios["111111"]}}
)
```

---

## ⚠️ Operações Destrutivas

### ❌ DELETAR TUDO DE UM USUÁRIO
```javascript
// NÃO EXECUTE SEM BACKUP!
db.bot_data.updateOne(
    {"_id": "economia"},
    {$unset: {"usuarios.123456": ""}}
)
```

### ❌ RESETAR DOCUMENTO INTEIRO
```javascript
// NÃO EXECUTE SEM BACKUP!
db.bot_data.deleteOne({"_id": "apostas_ff"})
db.bot_data.insertOne({"_id": "apostas_ff", "partidas": {}, "apostas": {}})
```

---

## 📋 Comandos Python para Debug

### Listar Todos os Documentos
```python
import asyncio
from connections.mongo_db import collection

async def debug():
    docs = await collection.find({}).to_list(None)
    for doc in docs:
        print(f"{doc['_id']}: {len(str(doc))} chars")

asyncio.run(debug())
```

### Exportar Dados para JSON
```python
import json
from pymongo import MongoClient

client = MongoClient("mongodb://...")
db = client["seu_banco"]

for doc in db.bot_data.find():
    with open(f"{doc['_id']}_backup.json", "w") as f:
        json.dump(doc, f, default=str, indent=2)
```

---

**⚠️ AVISO IMPORTANTE**

- **SEMPRE** faça backup antes de modificações em lote
- Use `upsert: true` para evitar perder dados
- Teste queries em ambiente de desenvolvimento
- Mantenha registros de mudanças administrativas

**Última atualização**: 2024
