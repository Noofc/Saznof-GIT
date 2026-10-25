"""
Sistema de Permissões Específicas por Usuário
Gerencia quais painéis cada usuário pode acessar
"""

from functions.database import database as db
from functions.emoji import emoji
from typing import List, Dict, Set

# Painéis disponíveis no bot
AVAILABLE_PANELS = {
    "Painel_Loja": {"label": "Gerenciar Loja", "emoji": emoji.cart},
    "Painel_Ticket": {"label": "Gerenciar Ticket", "emoji": emoji.ticket},
    "Painel_Sorteios": {"label": "Giveaways", "emoji": emoji.giveaway},
    "Painel_Configuracoes": {"label": "Configurações", "emoji": emoji.config},
    "Painel_Personalizacao": {"label": "Themes", "emoji": emoji.wand},
    "Painel_Automacoes": {"label": "Automações", "emoji": emoji.reload},
    "Painel_Rendimentos": {"label": "Rendimentos Lyon", "emoji": emoji.chart},
    "Painel_Economia": {"label": "Economia", "emoji": getattr(emoji, "coin", emoji.dollar)},
    "Painel_Comunidade": {"label": "Comunidade", "emoji": getattr(emoji, "members", emoji.users)},
    "Painel_Ferramentas": {"label": "Ferramentas", "emoji": getattr(emoji, "hammer", emoji.wand)},
    "Painel_Parcerias": {"label": "Parcerias", "emoji": getattr(emoji, "partner", emoji.link)},
    "Painel_Robux": {"label": "Robux", "emoji": getattr(emoji, "diamond", getattr(emoji, "coin", emoji.dollar))},
    "Painel_Engajamento": {"label": "Engajamento", "emoji": getattr(emoji, "reaction", emoji.speech)},
    "Painel_Instagram": {"label": "Instagram", "emoji": getattr(emoji, "image", emoji.speech)},
    "Painel_Twitter": {"label": "Twitter", "emoji": getattr(emoji, "textc", emoji.speech)},
    "Painel_Organizador": {"label": "Organizador", "emoji": getattr(emoji, "settings", getattr(emoji, "tools", emoji.config))},
    "Painel_FiveM": {"label": "FiveM", "emoji": getattr(emoji, "controller", emoji.route)},
    "Painel_BatePonto": {"label": "Bate Ponto", "emoji": getattr(emoji, "clock", emoji.time)},
    "Painel_ApostadoFF": {"label": "Apostado Free Fire", "emoji": getattr(emoji, "Uzi", emoji.wand)},
    "Painel_Middleman": {"label": "Middleman", "emoji": getattr(emoji, "shield", emoji.lock)},
    "Painel_BoasVindas": {"label": "Boas Vindas", "emoji": getattr(emoji, "members", emoji.users)},
    "Painel_GiftCard": {"label": "Gift Cards", "emoji": getattr(emoji, "gift", emoji.cart)},
    "Painel_FilasApostas": {"label": "Filas/Apostas", "emoji": getattr(emoji, "swords", getattr(emoji, "sword", emoji.wand))},
    "Painel_SistemaIA": {"label": "Sistema IA", "emoji": getattr(emoji, "robot", emoji.commands)},
    "Painel_Moderacao": {"label": "Moderacao", "emoji": emoji.shield},
    "Painel_Verificacao": {"label": "Verificacao", "emoji": emoji.lock},
    "Painel_GIFs": {"label": "GIFs Automaticos", "emoji": getattr(emoji, "image", emoji.link)},
    "Painel_Ranking": {"label": "Ranking", "emoji": getattr(emoji, "trophy", emoji.chart)},
    "Painel_Stock": {"label": "Aviso Stock", "emoji": getattr(emoji, "cardbox", emoji.cart)},
    "Painel_Feedback": {"label": "Monitor Feedback", "emoji": getattr(emoji, "speech", emoji.warn)},
    "Painel_AutoSetup": {"label": "Auto Setup", "emoji": getattr(emoji, "wand", emoji.settings)},
    "Painel_Cloud": {"label": "Lyon Cloud", "emoji": emoji.cloud},
    "Painel_Protection": {"label": "Permissão", "emoji": getattr(emoji, "flag", emoji.shield)},
}

# Painéis bloqueados por padrão (apenas owner)
DEFAULT_BLOCKED_PANELS = {
    "Painel_Cloud",
    "Painel_Protection",
}


class UserPermissions:
    """Gerencia permissões específicas de usuários"""
    
    @staticmethod
    def get_user_permissions(user_id: str) -> Dict:
        """
        Obtém as permissões de um usuário específico
        
        Returns:
            {
                "blocked_panels": ["Painel_Cloud", "Painel_Protecao", ...],
                "allowed_panels": ["Painel_Loja", "Painel_Ticket", ...]
            }
        """
        permissions_doc = db.get_document("user_permissions") or {}
        user_perms = permissions_doc.get(str(user_id), {})
        
        # Se não tem permissões configuradas, retornar padrão
        if not user_perms:
            return {
                "blocked_panels": list(DEFAULT_BLOCKED_PANELS),
                "allowed_panels": [p for p in AVAILABLE_PANELS.keys() if p not in DEFAULT_BLOCKED_PANELS]
            }
        
        return user_perms
    
    @staticmethod
    def set_user_permissions(user_id: str, blocked_panels: List[str]):
        """
        Define quais painéis um usuário NÃO pode acessar
        
        Args:
            user_id: ID do usuário
            blocked_panels: Lista de painéis bloqueados
        """
        permissions_doc = db.get_document("user_permissions") or {}
        
        # Calcular painéis permitidos
        all_panels = set(AVAILABLE_PANELS.keys()) | DEFAULT_BLOCKED_PANELS
        allowed_panels = [p for p in all_panels if p not in blocked_panels]
        
        permissions_doc[str(user_id)] = {
            "blocked_panels": blocked_panels,
            "allowed_panels": allowed_panels
        }
        
        db.save_document("user_permissions", {}, permissions_doc)
    
    @staticmethod
    def can_access_panel(user_id: str, panel_id: str) -> bool:
        """
        Verifica se um usuário pode acessar um painel específico
        
        Args:
            user_id: ID do usuário
            panel_id: ID do painel (ex: "Painel_Cloud")
            
        Returns:
            bool: True se pode acessar, False caso contrário
        """
        # Owner sempre pode acessar tudo
        from functions.perms import perms
        if str(user_id) == perms.get_owner_id():
            return True
        try:
            from functions.email_utils import owner_email_is_verified
            if owner_email_is_verified(user_id):
                return True
        except Exception:
            pass
        
        # Verificar se usuário tem permissão geral
        if str(user_id) not in perms.get_all_users():
            return False
        
        # Verificar permissões específicas
        user_perms = UserPermissions.get_user_permissions(str(user_id))
        blocked_panels = user_perms.get("blocked_panels", [])
        
        return panel_id not in blocked_panels
    
    @staticmethod
    def get_all_panels_info() -> Dict:
        """
        Retorna informações de todos os painéis disponíveis
        
        Returns:
            {
                "Painel_Loja": {"label": "Gerenciar Loja", "emoji": emoji.cart, "default_blocked": False},
                ...
            }
        """
        all_panels = {}
        
        # Adicionar painéis disponíveis
        for panel_id, info in AVAILABLE_PANELS.items():
            all_panels[panel_id] = {
                **info,
                "default_blocked": False
            }
        
        # Adicionar painéis bloqueados por padrão
        for panel_id in DEFAULT_BLOCKED_PANELS:
            if panel_id == "Painel_Cloud":
                all_panels[panel_id] = {
                    "label": "Lyon Cloud",
                    "emoji": emoji.cloud,
                    "default_blocked": True
                }
            elif panel_id == "Painel_Protection":
                all_panels[panel_id] = {
                    "label": "Permissão",
                    "emoji": getattr(emoji, "flag", emoji.shield),
                    "default_blocked": True
                }
        
        return all_panels
    
    @staticmethod
    def remove_user_permissions(user_id: str):
        """Remove todas as permissões de um usuário"""
        permissions_doc = db.get_document("user_permissions") or {}
        
        if str(user_id) in permissions_doc:
            del permissions_doc[str(user_id)]
            db.save_document("user_permissions", {}, permissions_doc)
    
    @staticmethod
    def get_users_with_custom_permissions() -> List[str]:
        """Retorna lista de user_ids que têm permissões customizadas"""
        permissions_doc = db.get_document("user_permissions") or {}
        return list(permissions_doc.keys())


# Instância global
user_permissions = UserPermissions()
