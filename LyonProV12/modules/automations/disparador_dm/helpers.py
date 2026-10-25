from functions.database import database as db
import uuid
import requests
import disnake
from typing import Optional, List, Dict
import time

TOKEN_STATUS_TTL = 15 * 60

def carregar_config() -> dict:
    """Carrega a configuração do Disparador DM's."""
    dados = db.obter("database/automations/disparador_dm.json") or {}
    dados.setdefault("ativado", False)
    dados.setdefault("tokens", [])
    dados["tokens"] = normalizar_tokens(dados.get("tokens", []))
    dados.setdefault("token_status", {})
    dados.setdefault("mensagem", {})
    return dados

def salvar_config(data: dict) -> None:
    """Salva a configuração do Disparador DM's."""
    if isinstance(data, dict):
        data["tokens"] = normalizar_tokens(data.get("tokens", []))
        data.setdefault("token_status", {})
    db.salvar("database/automations/disparador_dm.json", data)

def normalizar_token(token: str) -> str:
    token = str(token or "").strip().strip('"').strip("'")
    if token.lower().startswith("bot "):
        token = token[4:].strip()
    return token

def normalizar_tokens(tokens: List[str]) -> List[str]:
    result = []
    seen = set()
    for token in tokens or []:
        token = normalizar_token(token)
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result

def mascarar_token(token: str) -> str:
    token = normalizar_token(token)
    return f"{token[:10]}...{token[-10:]}" if len(token) > 20 else f"{token[:10]}..."

def _token_status_template(valid: Optional[bool], motivo: str, status_code: Optional[int] = None) -> dict:
    return {
        "valid": valid,
        "motivo": motivo,
        "status_code": status_code,
        "checked_at": int(time.time()) if valid is not None else None,
    }

def token_status_counts(tokens: List[str], config: Optional[dict] = None) -> tuple[int, int, int, int]:
    config = config or carregar_config()
    status_map = config.get("token_status", {}) if isinstance(config, dict) else {}
    total = len(tokens)
    validos = invalidos = pendentes = 0
    for token in tokens:
        valid = (status_map.get(token) or {}).get("valid")
        if valid is True:
            validos += 1
        elif valid is False:
            invalidos += 1
        else:
            pendentes += 1
    return total, validos, invalidos, pendentes

def preparar_status_pendente(tokens: List[str], config: Optional[dict] = None) -> dict:
    config = config or carregar_config()
    old_status = config.get("token_status", {}) if isinstance(config, dict) else {}
    status = {}
    for token in tokens:
        status[token] = old_status.get(token) or _token_status_template(None, "Aguardando validacao")
    config["tokens"] = tokens
    config["token_status"] = status
    return config

def carregar_temp_db() -> dict:
    """Carrega o banco de dados temporário."""
    try:
        dados = db.obter("database/automations/temp_disparador_dm.json") or {}
        dados.setdefault("usuarios_alvo", [])
        dados.setdefault("usuarios_enviados", [])
        dados.setdefault("tokens_falhos", [])
        dados.setdefault("usuarios_falhos", [])
        return dados
    except Exception:
        return {"usuarios_alvo": [], "usuarios_enviados": [], "tokens_falhos": [], "usuarios_falhos": []}

def salvar_temp_db(data: dict) -> None:
    """Salva o banco de dados temporário."""
    db.salvar("database/automations/temp_disparador_dm.json", data)

def limpar_temp_db() -> None:
    """Limpa o banco de dados temporário."""
    salvar_temp_db({"usuarios_alvo": [], "usuarios_enviados": [], "tokens_falhos": [], "usuarios_falhos": []})

def validar_token_detalhado(token: str) -> tuple[bool, Optional[int], str]:
    """Valida se um token de bot é válido."""
    token = normalizar_token(token)
    if not token:
        return False, None, "Token vazio"
    if token.count(".") < 2:
        return False, None, "Formato invalido"
    try:
        headers = {"Authorization": f"Bot {token}"}
        response = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("bot") is False:
                return False, response.status_code, "Token e de usuario, use token de bot"
            return True, response.status_code, f"OK: {data.get('username', 'Pro')}"
        if response.status_code == 401:
            return False, response.status_code, "Token invalido ou expirado"
        if response.status_code == 403:
            return False, response.status_code, "Token sem permissao"
        if response.status_code == 429:
            return False, response.status_code, "Rate limit do Discord"
        return False, response.status_code, f"Discord retornou HTTP {response.status_code}"
    except requests.Timeout:
        return False, None, "Timeout ao validar token"
    except Exception as exc:
        return False, None, f"Erro de conexao: {type(exc).__name__}"

def validar_token(token: str) -> bool:
    valid, _, _ = validar_token_detalhado(token)
    return valid

def obter_bot_info(token: str) -> Optional[Dict]:
    token = normalizar_token(token)
    """Obtém informações do bot usando o token."""
    try:
        headers = {"Authorization": f"Bot {token}"}
        response = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def validar_tokens(tokens: List[str]) -> tuple[int, int]:
    """Valida uma lista de tokens e retorna (total, válidos)."""
    total, validos, _, _ = validar_tokens_e_salvar(tokens)
    return total, validos

def validar_tokens_e_salvar(tokens: List[str]) -> tuple[int, int, int, int]:
    tokens = normalizar_tokens(tokens)
    config = preparar_status_pendente(tokens)
    status = {}
    validos = invalidos = 0
    for token in tokens:
        valid, status_code, motivo = validar_token_detalhado(token)
        status[token] = _token_status_template(valid, motivo, status_code)
        if valid:
            validos += 1
        else:
            invalidos += 1
    config["tokens"] = tokens
    config["token_status"] = status
    salvar_config(config)
    return len(tokens), validos, invalidos, 0

def set_editor_field(field: str, value):
    """Define um campo no editor de mensagem."""
    config = carregar_config()
    config["mensagem"][field] = value
    salvar_config(config)
    return True

def get_editor_data() -> dict:
    """Obtém os dados do editor."""
    config = carregar_config()
    return config.get("mensagem", {})

def clear_editor_field(field: str):
    """Limpa um campo do editor."""
    config = carregar_config()
    if field in config.get("mensagem", {}):
        del config["mensagem"][field]
        salvar_config(config)
        return True
    return False

def set_editor_data(editor_data: dict):
    """Define os dados completos do editor."""
    config = carregar_config()
    config["mensagem"] = editor_data
    salvar_config(config)
    return True

async def mapear_usuarios_alvo(bot, server_id: Optional[str], role_id: Optional[str], 
                               exclude_roles: List[str], exclude_users: List[str]) -> List[int]:
    """
    Mapeia os usuários que devem receber a mensagem.
    
    Args:
        bot: Instância do bot
        server_id: ID do servidor (None = servidor principal)
        role_id: ID do cargo (None = everyone)
        exclude_roles: Lista de IDs de cargos para excluir
        exclude_users: Lista de IDs de usuários para excluir
    
    Returns:
        Lista de IDs de usuários que devem receber
    """
    try:
        # Obtém o servidor
        if server_id:
            guild = bot.get_guild(int(server_id))
        else:
            # Servidor principal (primeiro servidor do bot)
            guilds = bot.guilds
            guild = guilds[0] if guilds else None
        
        if not guild:
            return []
        
        # Converte IDs para int
        exclude_role_ids = [int(rid) for rid in exclude_roles if rid.strip()]
        exclude_user_ids = [int(uid) for uid in exclude_users if uid.strip()]
        
        usuarios_alvo = []
        
        # Se role_id não foi especificado, pega todos os membros
        if not role_id or role_id.strip() == "":
            members = guild.members
        else:
            # Pega membros com o cargo específico
            role = guild.get_role(int(role_id))
            if not role:
                return []
            members = role.members
        
        # Filtra os membros
        for member in members:
            # Ignora bots
            if member.bot:
                continue
            
            # Ignora se o usuário está na lista de exclusão
            if member.id in exclude_user_ids:
                continue
            
            # Ignora se o usuário tem algum cargo da lista de exclusão
            has_excluded_role = any(role.id in exclude_role_ids for role in member.roles)
            if has_excluded_role:
                continue
            
            usuarios_alvo.append(member.id)
        
        return usuarios_alvo
    
    except Exception as e:
        print(f"Erro ao mapear usuários alvo: {e}")
        return []

def adicionar_usuario_enviado(user_id: int):
    """Adiciona um usuário à lista de enviados."""
    temp_db = carregar_temp_db()
    if user_id not in temp_db["usuarios_enviados"]:
        temp_db["usuarios_enviados"].append(user_id)
        salvar_temp_db(temp_db)

def adicionar_usuario_falho(user_id: int):
    """Adiciona um usuário à lista de falhos."""
    temp_db = carregar_temp_db()
    if user_id not in temp_db["usuarios_falhos"]:
        temp_db["usuarios_falhos"].append(user_id)
        salvar_temp_db(temp_db)

def get_usuarios_pendentes() -> List[int]:
    """Retorna a lista de usuários que ainda não receberam."""
    temp_db = carregar_temp_db()
    alvo = set(temp_db.get("usuarios_alvo", []))
    enviados = set(temp_db.get("usuarios_enviados", []))
    falhos = set(temp_db.get("usuarios_falhos", []))
    return list(alvo - enviados - falhos)

def salvar_usuarios_alvo(usuarios: List[int]):
    """Salva a lista de usuários alvo."""
    temp_db = carregar_temp_db()
    temp_db["usuarios_alvo"] = usuarios
    salvar_temp_db(temp_db)

def adicionar_token_falho(token: str, motivo: str = "Erro ao enviar mensagens"):
    token = normalizar_token(token)
    """Adiciona um token à lista de tokens falhos."""
    temp_db = carregar_temp_db()
    tokens_falhos = temp_db.get("tokens_falhos", [])
    
    # Mascarar o token (mostrar apenas os primeiros e últimos 10 caracteres)
    token_mascarado = mascarar_token(token)
    
    token_info = {
        "token": token,
        "token_mascarado": token_mascarado,
        "motivo": motivo,
        "timestamp": int(__import__("time").time())
    }
    
    # Evitar duplicatas
    if not any(t.get("token") == token for t in tokens_falhos):
        tokens_falhos.append(token_info)
        temp_db["tokens_falhos"] = tokens_falhos
        salvar_temp_db(temp_db)

def obter_tokens_falhos() -> List[Dict]:
    """Retorna a lista de tokens falhos."""
    temp_db = carregar_temp_db()
    return temp_db.get("tokens_falhos", [])

def remover_token_do_config(token: str) -> bool:
    token = normalizar_token(token)
    """Remove um token da configuração principal."""
    try:
        config = carregar_config()
        tokens = config.get("tokens", [])
        if token in tokens:
            tokens.remove(token)
            config["tokens"] = tokens
            salvar_config(config)
            return True
        return False
    except Exception as e:
        print(f"Erro ao remover token: {e}")
        return False

def limpar_tokens_falhos() -> None:
    """Limpa apenas a lista de tokens falhos do temp DB."""
    temp_db = carregar_temp_db()
    temp_db["tokens_falhos"] = []
    salvar_temp_db(temp_db)

