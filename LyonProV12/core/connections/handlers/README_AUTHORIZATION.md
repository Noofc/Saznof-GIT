# Sistema de Autorização para Handlers WebSocket

## Visão Geral

Este sistema implementa controle de acesso para handlers WebSocket sensíveis, garantindo que apenas o dono do bot (owner) possa acessar funcionalidades críticas como:

- **Proteção do Cliente**: Configurações de segurança e proteção do servidor
- **Lyon Cloud**: Gerenciamento de credenciais, gifts, tasks e configurações da Lyon Cloud

## Como Funciona

### 1. Middleware de Autorização

O arquivo `auth_middleware.py` contém:

- `AuthorizationError`: Exception customizada para erros de autorização
- `check_owner_authorization(payload)`: Verifica se o user_id no payload corresponde ao owner_id configurado
- `is_protected_handler(handler_name)`: Verifica se um handler requer autorização
- `PROTECTED_HANDLERS`: Set com todos os handlers protegidos

### 2. Verificação Automática

O `websocket_manager.py` foi modificado para:

1. Interceptar todas as requisições de execução de handlers
2. Verificar se o handler está na lista de protegidos
3. Se protegido, validar a autorização antes de executar
4. Retornar erro `unauthorized` se a autorização falhar

### 3. Configuração do Owner

O owner_id é obtido de `config.json`:

```json
{
  "bot": {
    "owner": "930195432242544701"
  }
}
```

## Handlers Protegidos

### Protection Handlers
- `protection.getConfig`
- `protection.updateConfig`
- `protection.getWhitelist`
- `protection.getBlacklist`

### Cloud Handlers
- `cloud.getConfig`
- `cloud.updateCredentials`
- `cloud.updateLogChannel`
- `cloud.updateVerifiedRole`
- `cloud.getStats`
- `cloud.getAuthLogs`
- `cloud.getGifts`
- `cloud.getGift`
- `cloud.createGift`
- `cloud.updateGift`
- `cloud.deleteGift`
- `cloud.getTasks`
- `cloud.getTask`
- `cloud.createTask`
- `cloud.updateTask`
- `cloud.deleteTask`
- `cloud.getVerificationMessage`
- `cloud.updateVerificationMessage`
- `cloud.updateMessageStyle`
- `cloud.resetVerificationMessage`
- `cloud.sendVerificationMessage`
- `cloud.connectWebSocket`
- `cloud.disconnectWebSocket`
- `cloud.getWebSocketStatus`

## Formato da Requisição

Para acessar handlers protegidos, o payload DEVE incluir o `user_id`:

```json
{
  "requestId": "unique-request-id",
  "type": "protection.getConfig",
  "payload": {
    "user_id": "930195432242544701"
  }
}
```

## Respostas de Erro

### Não Autorizado
```json
{
  "status": "unauthorized",
  "code": "UNAUTHORIZED",
  "error": "Apenas o dono do bot pode acessar esta funcionalidade"
}
```

### User ID Não Fornecido
```json
{
  "status": "unauthorized",
  "code": "UNAUTHORIZED",
  "error": "user_id não fornecido na requisição"
}
```

### Owner ID Não Configurado
```json
{
  "status": "unauthorized",
  "code": "UNAUTHORIZED",
  "error": "owner_id não configurado no sistema"
}
```

## Adicionando Novos Handlers Protegidos

Para proteger um novo handler:

1. Adicione o nome do handler ao set `PROTECTED_HANDLERS` em `auth_middleware.py`:

```python
PROTECTED_HANDLERS = {
    # ... handlers existentes ...
    'meu_modulo.meuHandler',
}
```

2. O handler será automaticamente protegido na próxima requisição

## Removendo Proteção

Para remover a proteção de um handler, simplesmente remova-o do set `PROTECTED_HANDLERS`.

## Logs

O sistema registra:

- ✅ Autorizações bem-sucedidas (nível DEBUG)
- ⚠️ Tentativas de acesso não autorizado (nível WARNING)
- ❌ Erros de verificação (nível ERROR)

## Segurança

- O owner_id é verificado em cada requisição
- Não há cache de autorização (sempre verifica)
- Comparação case-sensitive de IDs
- Logs de todas as tentativas de acesso

## Testando

Para testar a autorização:

1. Tente acessar um handler protegido com o owner_id correto (deve funcionar)
2. Tente acessar com um user_id diferente (deve retornar unauthorized)
3. Tente acessar sem user_id (deve retornar erro)
4. Verifique os logs para confirmar as verificações
