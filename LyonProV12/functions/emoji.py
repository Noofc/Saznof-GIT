from functions.database import database as db
from core.enable_intents import enable_intents
import json
from pathlib import Path

class emoji:
    _emoji_data = db.obter("database/emojis/emojis.json") or {}
    for key, value in _emoji_data.items():
        locals()[key] = value
    db = _emoji_data

def reload_emoji_class():
    """Recarrega emojis diretamente do disco, sem usar o cache antigo."""
    path = Path("database/emojis/emojis.json")
    try:
        with path.open("r", encoding="utf-8") as f:
            fresh_data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[Emojis] Falha ao recarregar emojis.json: {exc}")
        return
    for old_name in [f"s{i}" for i in range(9)] + ["Lyon"]:
        if hasattr(emoji, old_name):
            delattr(emoji, old_name)
    emoji.db = fresh_data
    for key, value in fresh_data.items():
        setattr(emoji, key, value)
    print(f"[Emojis] Classe emoji recarregada com {len(fresh_data)} emojis; lyon={fresh_data.get('lyon')}")

def init_on_startup(bot_token: str, app_id: str) -> None:
    """Inicializa e sincroniza emojis na inicialização do bot"""
    print("[Emojis] Iniciando sistema de emojis...")
    
    emojis_data = db.obter("database/emojis/emojis_data.json")
    config_emoji = db.obter("configs/config_emoji.json")

    is_configured = config_emoji.get("isConfigured", False)
    
    # Se isConfigured for true, não sincronizar
    if is_configured:
        print("[Emojis] Sistema configurado; verificando assets para alterações incrementais.")
    
    # Se isConfigured for false, verificar os outros requisitos
    configured = emojis_data.get("configured", "false")
    last_token = emojis_data.get("lastToken", "")
    
    print(f"[Emojis] Status: configured={configured}, token_match={last_token == bot_token}")
    
    # Sincronizar se:
    # 1. Nunca foi configurado (configured != "True")
    # 2. Token mudou (last_token diferente do atual)
    # A verificação é sempre incremental: somente assets novos ou alterados geram operações na API.
    should_Lyon = True
    
    if should_Lyon:
        print("[Emojis] Iniciando sincronização de emojis...")
        # Ativar intents privilegiadas antes de sincronizar emojis
        enable_intents(bot_token, app_id)
        
        from functions.emojis import emojis as Emojis
        emoji_manager = Emojis(bot_token, app_id)
        print(f"[Emojis] Total de emojis a sincronizar: {len(emoji_manager.emojis_db)}")
        # Sincronização incremental: preserva os emojis existentes e cria somente os ausentes.
        emoji_manager.Lyon_add_missing()
        
        # Recarregar a classe emoji após sincronização
        reload_emoji_class()
    else:
        print("[Emojis] Emojis já sincronizados com o token atual")