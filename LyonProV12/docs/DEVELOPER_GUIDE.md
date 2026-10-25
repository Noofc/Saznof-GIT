# 📖 Guia Rápido de Desenvolvimento - Lyon Pro

## 🎯 Objetivo
Guia prático para adicionar novos recursos aos sistemas já implementados.

---

## 📦 Estrutura de Módulos

```
modules/
├── economia/              # Sistema de saldo, poupança, investimentos
│   ├── __init__.py       # Setup cog
│   ├── cog.py            # Comandos Discord
│   └── saldo_manager.py  # Lógica de negócio
├── parcerias/            # Sistema de parceiros e comissões
│   ├── __init__.py
│   ├── cog.py
│   └── manager.py
├── apostas_ff/           # Apostas em Free Fire
│   ├── __init__.py
│   ├── cog.py
│   └── manager.py
├── comunidade/           # Comunidade e eventos
│   ├── __init__.py
│   ├── cog.py
│   └── manager.py
└── ferramentas/          # Calculadoras e análises
    ├── __init__.py
    ├── cog.py
    └── manager.py
```

---

## 🔧 Como Adicionar um Novo Comando

### Passo 1: Implementar no Manager
```python
# modules/economia/saldo_manager.py

@staticmethod
async def meu_novo_recurso(user_id: int, parametro: float) -> tuple[bool, str]:
    """Descrição do recurso"""
    try:
        # Validações
        usuario = await SaldoManager.get_usuario(user_id)
        if parametro <= 0:
            return False, "Parâmetro inválido"
        
        # Lógica
        resultado = usuario["saldo"] * parametro
        
        # Atualizar no MongoDB
        await bot_collection.update_one(
            {"_id": "economia"},
            {
                "$inc": {f"usuarios.{user_id}.saldo": resultado},
                "$push": {
                    f"usuarios.{user_id}.historico": {
                        "tipo": "meu_novo_recurso",
                        "valor": resultado,
                        "data": datetime.now().isoformat(),
                    }
                }
            },
            upsert=True
        )
        
        return True, f"✅ Sucesso! Resultado: {resultado:.2f}"
    except Exception as e:
        return False, f"❌ Erro: {e}"
```

### Passo 2: Criar Comando no Cog
```python
# modules/economia/cog.py

@commands.slash_command(name="meu_comando", description="Descrição do comando")
async def meu_comando(
    self,
    inter: disnake.AppCommandInteraction,
    parametro: float
):
    """Meu novo comando"""
    sucesso, mensagem = await self.saldo_manager.meu_novo_recurso(
        inter.author.id,
        parametro
    )
    
    embed = disnake.Embed(
        title="Título",
        description=mensagem,
        color=disnake.Colour.green() if sucesso else disnake.Colour.red()
    )
    
    await inter.response.send_message(embed=embed, ephemeral=True)
```

---

## 🔌 Padrão de Banco de Dados

### Padrão CRUD com MongoDB

```python
# Criar
await bot_collection.update_one(
    {"_id": "documento_id"},
    {"$set": {f"campo.{user_id}": valor}},
    upsert=True
)

# Ler
doc = await bot_collection.find_one({"_id": "documento_id"})
dados = doc.get("campo", {}).get(str(user_id), {})

# Atualizar
await bot_collection.update_one(
    {"_id": "documento_id"},
    {"$inc": {f"campo.{user_id}.valor": quantidade}}
)

# Deletar
await bot_collection.update_one(
    {"_id": "documento_id"},
    {"$unset": {f"campo.{user_id}": ""}}
)
```

---

## 💡 Exemplos Práticos

### Exemplo 1: Adicionar Bônus ao Saldo
```python
# Simples - quando não precisa de validação complexa
await SaldoManager.adicionar_saldo(user_id, 100, "Bônus especial")
```

### Exemplo 2: Transferência com Validação
```python
sucesso, mensagem = await SaldoManager.transferir(
    usuario_origem=123456,
    usuario_destino=654321,
    valor=100
)

if sucesso:
    # Fazer algo após sucesso
    pass
```

### Exemplo 3: Registrar Venda e Calcular Comissão
```python
# Automaticamente calcula comissão + bônus de tier
await ParceriasManager.registrar_venda(
    parceiro_id=123456,
    valor=1000,
    tipo_venda="direta"
)

# Verificar se mudou de tier
await ParceriasManager._verificar_nivel(123456)
```

### Exemplo 4: Criar Aposta e Calcular Odd
```python
sucesso, mensagem, premio = await ApostasFFManager.fazer_aposta(
    user_id=123456,
    partida_id="ff_1234567890",
    valor=100,
    escolha="equipe1"  # ou "equipe2", "empate"
)

# Premio já é calculado com a odd dinâmica
print(f"Possível prêmio: {premio:.2f}")
```

---

## 📊 Configurações Customizáveis

### Alterar Taxa de Transferência
```python
# modules/economia/saldo_manager.py
DEFAULT_ECONOMIA = {
    "taxas": {
        "transferencia": 0.05,  # Mude para 0.03 (3%)
        # ...
    }
}
```

### Alterar Limites de Aposta
```python
# modules/apostas_ff/manager.py
DEFAULT_CONFIG = {
    "limites": {
        "minima": 10,      # Mude para 5
        "maxima": 1000     # Mude para 5000
    }
}
```

### Alterar Tiers de Parceria
```python
# modules/parcerias/manager.py
DEFAULT_PARCERIAS = {
    "tiers": {
        "bronze": {"vendas_minimas": 0, "comissao_extra": 0, "bônus_nivel": 50},
        # Mude conforme necessário
    }
}
```

---

## 🧪 Testes Manuais

### Testar Economia
```
1. /economia                          → Ver saldo
2. /transferir @usuario 100           → Transferir
3. /emprestar 500                      → Pedir empréstimo
4. /ranking_economia                  → Ver ranking
```

### Testar Parcerias
```
1. /parceria                           → Ver parceria
2. /criar_parceria MinhaLoja loja     → Criar parceria
3. /ranking_parceiros                 → Ver ranking
```

### Testar Apostas FF
```
1. /criar_partida_ff TeamA TeamB 75 60  → Criar partida (admin)
2. /apostas_ff                           → Ver partidas
3. /apostar_ff ff_id 100 equipe1        → Fazer aposta
4. /comando_admin encerrar_partida      → Encerrar (admin)
```

### Testar Ferramentas
```
1. /ferramentas_economia             → Menu
2. /calcular_lucro 1000 10           → Cálculo
3. /comparar_taxas 1000              → ✨ NOVO
4. /meta_poupanca 5000 30            → ✨ NOVO
```

---

## 🐛 Debugging

### Ver Logs do Banco
```python
# Antes de atualizar, verificar dados
doc = await bot_collection.find_one({"_id": "economia"})
print(json.dumps(doc.get("usuarios", {}).get(str(user_id), {}), indent=2))
```

### Validar Estrutura de Dados
```python
# Garantir que usuário existe
usuario = await SaldoManager.get_usuario(user_id)
assert usuario.get("saldo") is not None
assert usuario.get("historico") is not None
```

### Testar Manager Diretamente
```python
# Em um script separado
import asyncio
from modules.economia.saldo_manager import SaldoManager

async def test():
    sucesso = await SaldoManager.adicionar_saldo(123456, 100, "Teste")
    print(f"Sucesso: {sucesso}")

asyncio.run(test())
```

---

## 📝 Checklist para Novo Recurso

- [ ] Implementar método no Manager (com validações)
- [ ] Adicionar comando no Cog (com embed bonito)
- [ ] Testar comando manualmente
- [ ] Verificar dados no MongoDB
- [ ] Adicionar ao histórico do usuário
- [ ] Documentar no README ou guia
- [ ] Testar com múltiplos usuários
- [ ] Verificar edge cases (saldo 0, valores negativos, etc)

---

## 🎨 Padrão de Embed

```python
embed = disnake.Embed(
    title="Título Principal",
    description="Descrição ou mensagem",
    color=disnake.Colour.green()  # green, red, blue, gold, purple, etc
)

embed.add_field(
    name="Campo 1",
    value="Valor com `código` e **negrito**",
    inline=True  # True para lado a lado, False para nova linha
)

embed.set_thumbnail(url="https://...")  # Imagem pequena
embed.set_image(url="https://...")      # Imagem grande

await inter.response.send_message(embed=embed, ephemeral=True)
```

---

## 🚨 Erros Comuns

### ❌ Erro: `KeyError: 'usuarios'`
**Causa**: Documento não inicializado no MongoDB
**Solução**: Use `upsert=True` ao atualizar

### ❌ Erro: `TypeError: 'NoneType' object is not subscriptable`
**Causa**: Variável não validada antes de usar
**Solução**: Sempre faça `if doc:` antes de acessar campos

### ❌ Erro: `RuntimeError: cannot use 'await' outside async function`
**Causa**: Método não é async
**Solução**: Adicione `async` e `await` corretamente

### ❌ Comando não aparece no Discord
**Causa**: Cog não está registrado
**Solução**: Verifique se `setup()` está no `__init__.py` e no `modules/__init__.py`

---

## 📚 Referências Úteis

- [Disnake Docs](https://docs.disnake.dev/)
- [MongoDB PyMongo](https://pymongo.readthedocs.io/)
- [Asyncio Python](https://docs.python.org/3/library/asyncio.html)

---

**Última atualização**: 2024
**Versão**: 2.0 (Com melhorias de apostas, parcerias e ferramentas)
