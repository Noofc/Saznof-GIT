"""
Sistema de gerenciamento de cargos temporários
Remove automaticamente cargos que expiraram
"""
import disnake
import time
from datetime import datetime, timezone
from disnake.ext import commands, tasks
from functions.database import database as db


class RolesTempManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _ids_from_roles_like(self, roles_like) -> set[int]:
        ids = set()
        if not roles_like:
            return ids
        try:
            iterator = iter(roles_like)
        except TypeError:
            iterator = iter([roles_like])
        for item in iterator:
            try:
                if hasattr(item, "id"):
                    ids.add(int(item.id))
                elif isinstance(item, dict) and "id" in item:
                    ids.add(int(item["id"]))
                elif hasattr(item, "role") and hasattr(item.role, "id"):
                    ids.add(int(item.role.id))
                elif isinstance(item, int):
                    ids.add(int(item))
            except Exception:
                continue
        return ids

    async def _was_role_reassigned_after_expiration(
        self,
        guild: disnake.Guild,
        member: disnake.Member,
        role_id: int,
        expires_at: int,
    ) -> bool:
        try:
            cutoff = datetime.fromtimestamp(int(expires_at), tz=timezone.utc)
            async for entry in guild.audit_logs(action=disnake.AuditLogAction.member_role_update, limit=20):
                if getattr(getattr(entry, "target", None), "id", None) != member.id:
                    continue
                if entry.created_at <= cutoff:
                    continue
                before_ids = self._ids_from_roles_like(getattr(getattr(entry, "before", None), "roles", None))
                after_ids = self._ids_from_roles_like(getattr(getattr(entry, "after", None), "roles", None))
                if int(role_id) in (after_ids - before_ids):
                    return True
        except Exception:
            return False
        return False

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.check_expired_roles.is_running():
            self.check_expired_roles.start()
    
    def cog_unload(self):
        self.check_expired_roles.cancel()
    
    @tasks.loop(minutes=1)
    async def check_expired_roles(self):
        """Verifica e remove cargos expirados a cada minuto"""
        try:
            roles_temp = db.get_document("loja_roles_temp") or {}
            current_time = int(time.time())
            modified = False
            
            for user_id_str, user_roles in list(roles_temp.items()):
                if not isinstance(user_roles, list):
                    del roles_temp[user_id_str]
                    modified = True
                    continue
                
                roles_to_keep = []
                active_keys = set()
                for role_data in user_roles:
                    try:
                        expires_at = int(role_data.get("expires_at") or 0)
                        role_id = int(role_data.get("role_id") or 0)
                        guild_id = int(role_data.get("guild_id") or 0)
                    except Exception:
                        continue
                    if expires_at > current_time and role_id and guild_id:
                        active_keys.add((guild_id, role_id))
                
                for role_data in user_roles:
                    try:
                        expires_at = int(role_data.get("expires_at") or 0)
                        role_id = int(role_data.get("role_id") or 0)
                        guild_id = int(role_data.get("guild_id") or 0)
                    except Exception:
                        modified = True
                        continue
                    
                    if not expires_at or not role_id or not guild_id:
                        modified = True
                        continue
                    
                    # Se o cargo ainda não expirou, manter
                    if expires_at > current_time:
                        roles_to_keep.append(role_data)
                        continue

                    if (guild_id, role_id) in active_keys:
                        modified = True
                        continue

                    if not role_data.get("assigned_at"):
                        modified = True
                        continue
                    
                    # Cargo expirou - remover do usuário
                    try:
                        guild = self.bot.get_guild(int(guild_id))
                        if not guild:
                            continue
                        
                        member = guild.get_member(int(user_id_str))
                        if not member:
                            # Usuário não está mais no servidor
                            modified = True
                            continue
                        
                        role = guild.get_role(int(role_id))
                        if not role:
                            # Cargo não existe mais
                            modified = True
                            continue
                        
                        if role in member.roles:
                            if await self._was_role_reassigned_after_expiration(guild, member, role_id, expires_at):
                                modified = True
                                continue
                            await member.remove_roles(role, reason="Cargo temporário expirado")
                            modified = True
                    except Exception as e:
                        # Em caso de erro, não manter o cargo na lista
                        modified = True
                        continue
                
                # Atualizar lista de cargos do usuário
                if roles_to_keep:
                    roles_temp[user_id_str] = roles_to_keep
                else:
                    # Se não há mais cargos, remover o usuário do documento
                    del roles_temp[user_id_str]
                    modified = True
            
            # Salvar alterações se houve modificações
            if modified:
                db.save_document("loja_roles_temp", roles_temp)
        
        except Exception as e:
            print(f"Erro ao verificar cargos temporários: {e}")
    
    @check_expired_roles.before_loop
    async def before_check_expired_roles(self):
        """Aguarda o bot estar pronto antes de iniciar a tarefa"""
        await self.bot.wait_until_ready()


def setup(bot: commands.Bot):
    bot.add_cog(RolesTempManager(bot))
