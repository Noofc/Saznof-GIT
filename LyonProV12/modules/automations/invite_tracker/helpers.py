from functions.database import database as db

def carregar_config() -> dict:
    """Carrega a configuração da coleção 'automations_invite_tracker'."""
    data = db.get_document("automations_invite_tracker") or {}
    data.setdefault("ativado", False)
    data.setdefault("channel_id", None)
    data.setdefault("welcome_message", "Seja bem-vindo(a) {member}! Você foi convidado(a) por {inviter} que agora possui {invites} convites válidos.")
    data.setdefault("welcome_message_vanity", "Seja bem-vindo(a) {member}! Você entrou através do Vanity URL do servidor.")
    data.setdefault("leave_message", "Que pena, {member} nos deixou. Ele(a) foi convidado(a) por {inviter} que agora possui {invites} convites válidos.")
    return data

def salvar_config(data: dict) -> None:
    """Salva a configuração na coleção 'automations_invite_tracker'."""
    db.save_document("automations_invite_tracker", data)

def get_invites_data() -> dict:
    """Carrega os dados de convites do documento dedicado 'convites'.
    Se estiver vazio, tenta migrar de automations_invite_tracker.invites_data uma única vez.
    """
    data = db.get_document("convites") or {}
    if data:
        return data

    # Fallback de migração: mover invites_data antigo, se existir
    old_conf = db.get_document("automations_invite_tracker") or {}
    old_invites = old_conf.get("invites_data") if isinstance(old_conf, dict) else None
    if isinstance(old_invites, dict) and old_invites:
        db.save_document("convites", old_invites)
        # remove chave antiga para evitar migração repetida
        try:
            old_conf.pop("invites_data", None)
            db.save_document("automations_invite_tracker", old_conf)
        except Exception:
            pass
        return old_invites
    return {}

def save_invites_data(data: dict) -> None:
    """Salva os dados de convites no documento dedicado 'convites'."""
    db.save_document("convites", data)


def carregar_rewards() -> dict:
    data = db.get_document("automations_invite_rewards") or {}
    data.setdefault("enabled", False)
    data.setdefault("points_per_invite", 1)
    data.setdefault("users", {})
    data.setdefault("logs", [])
    return data


def salvar_rewards(data: dict) -> None:
    db.save_document("automations_invite_rewards", data)


def add_invite_reward(guild_id: int, inviter_id: int, invited_id: int, invite_total: int) -> tuple[bool, int, int]:
    data = carregar_rewards()
    if not data.get("enabled", False):
        return False, 0, 0

    guild_key = str(guild_id)
    user_key = str(inviter_id)
    invited_key = str(invited_id)
    users = data.setdefault("users", {}).setdefault(guild_key, {})
    user_data = users.setdefault(user_key, {"points": 0, "valid_invites": 0, "rewarded_members": []})
    rewarded = set(str(x) for x in user_data.get("rewarded_members", []))
    if invited_key in rewarded:
        return False, int(user_data.get("points", 0)), int(user_data.get("valid_invites", 0))

    points = max(0, int(data.get("points_per_invite", 1)))
    user_data["points"] = int(user_data.get("points", 0)) + points
    user_data["valid_invites"] = int(user_data.get("valid_invites", 0)) + 1
    user_data.setdefault("rewarded_members", []).append(invited_key)
    user_data["last_invite_total"] = invite_total
    data.setdefault("logs", []).append({
        "guild_id": guild_id,
        "inviter_id": inviter_id,
        "invited_id": invited_id,
        "points": points,
        "invite_total": invite_total,
    })
    salvar_rewards(data)
    return True, int(user_data["points"]), int(user_data["valid_invites"])


def ranking_rewards(guild_id: int, limit: int = 10) -> list[tuple[str, dict]]:
    data = carregar_rewards()
    users = data.get("users", {}).get(str(guild_id), {})
    return sorted(users.items(), key=lambda item: int(item[1].get("points", 0)), reverse=True)[:limit]
