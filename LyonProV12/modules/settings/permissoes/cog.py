import disnake
from disnake.ext import commands
from functions.emoji import emoji
from functions.database import database as db
from functions.message import message, embed_message
from functions.perms import perms

MAX_SELECT_OPTIONS = 25
MAX_MODAL_SELECTS = 5


class GerenciarPermissoes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def get_perms_users():
        """Retorna a lista de IDs de usuários com permissão (do MongoDB)"""
        return perms.get_all_users()

    @staticmethod
    def get_owner_id():
        """Retorna o ID do owner do bot"""
        return perms.get_owner_id()

    @staticmethod
    async def panel_aLyon(inter: disnake.MessageInteraction, bot: commands.Bot = None):
        """Retorna o painel de gerenciamento de permissões (versão aLyon para buscar nomes)"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)
        
        # Obter lista de usuários com permissão
        perms_users = GerenciarPermissoes.get_perms_users()
        
        # Formatar lista de usuários
        if perms_users:
            users_text = ""
            for user_id in perms_users:
                users_text += f"{emoji.members} <@{user_id}>\n"
        else:
            users_text = f"{emoji.wrong} Nenhum usuário com acesso."
        
        # Criar opções do select menu para configurar usuários
        select_options = []
        if perms_users and bot:
            for user_id in perms_users[:25]:  # Limite de 25 opções
                try:
                    user = await bot.fetch_user(int(user_id))
                    label = user.name
                    description = f"ID: {user_id}"
                except:
                    label = f"Usuário {user_id[:8]}..."
                    description = f"ID: {user_id}"
                
                select_options.append(
                    disnake.SelectOption(
                        label=label,
                        value=user_id,
                        description=description,
                        emoji=emoji.members
                    )
                )
        
        # Criar componentes do container principal
        container_components = [
            disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Configurações > **Gerenciar Permissões**"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(f"**Usuários com Acesso:**\n{users_text}"),
            disnake.ui.Separator(),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Adicionar",
                    style=disnake.ButtonStyle.green,
                    emoji=emoji.plus,
                    custom_id="Permissoes_Adicionar"
                ),
                disnake.ui.Button(
                    label="Remover",
                    style=disnake.ButtonStyle.danger,
                    emoji=emoji.minus,
                    custom_id="Permissoes_Remover"
                ),
            ),
        ]
        
        # Adicionar select menu no mesmo container se houver usuários
        if select_options:
            container_components.extend([
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("**Configurar Permissões:**"),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Permissoes_SelectUser",
                        placeholder="Selecione um usuário para configurar...",
                        options=select_options
                    )
                ),
            ])
        
        components = [
            disnake.ui.Container(
                *container_components,
                **container_kwargs,
            ),
        ]
        
        return {"components": components}
    
    @staticmethod
    def panel(inter: disnake.MessageInteraction, bot: commands.Bot = None):
        """Retorna o painel de gerenciamento de permissões"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)
        
        # Obter lista de usuários com permissão
        perms_users = GerenciarPermissoes.get_perms_users()
        
        # Formatar lista de usuários
        if perms_users:
            users_text = ""
            for user_id in perms_users:
                users_text += f"{emoji.members} <@{user_id}>\n"
        else:
            users_text = f"{emoji.wrong} Nenhum usuário com acesso."
        
        # Criar opções do select menu para configurar usuários
        select_options = []
        if perms_users:
            for user_id in perms_users[:25]:  # Limite de 25 opções
                select_options.append(
                    disnake.SelectOption(
                        label=f"ID: {user_id}",
                        value=user_id,
                        description=f"Configurar permissões",
                        emoji=emoji.members
                    )
                )
        
        # Criar componentes do container principal
        container_components = [
            disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Configurações > **Gerenciar Permissões**"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(f"**Usuários com Acesso:**\n{users_text}"),
            disnake.ui.Separator(),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Adicionar",
                    style=disnake.ButtonStyle.green,
                    emoji=emoji.plus,
                    custom_id="Permissoes_Adicionar"
                ),
                disnake.ui.Button(
                    label="Remover",
                    style=disnake.ButtonStyle.danger,
                    emoji=emoji.minus,
                    custom_id="Permissoes_Remover"
                ),
            ),
        ]
        
        # Adicionar select menu no mesmo container se houver usuários
        if select_options:
            container_components.extend([
                disnake.ui.Separator(),
                disnake.ui.TextDisplay("**Configurar Permissões:**"),
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Permissoes_SelectUser",
                        placeholder="Selecione um usuário para configurar...",
                        options=select_options
                    )
                ),
            ])
        
        components = [
            disnake.ui.Container(
                *container_components,
                **container_kwargs,
            ),
        ]
        
        return {"components": components}

    @staticmethod
    def panel_embed(inter: disnake.MessageInteraction, bot: commands.Bot = None):
        """Retorna o painel em formato embed"""
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        
        # Obter lista de usuários com permissão
        perms_users = GerenciarPermissoes.get_perms_users()
        
        # Formatar lista de usuários
        if perms_users:
            users_text = ""
            for user_id in perms_users:
                users_text += f"{emoji.members} <@{user_id}>\n"
        else:
            users_text = f"{emoji.wrong} Nenhum usuário com acesso."
        
        embed = disnake.Embed(
            title="Gerenciar Permissões",
            description=(
                f"-# Painel > Configurações > **Gerenciar Permissões**\n\n"
                f"**Usuários com Acesso:**\n{users_text}"
            )
        )
        
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            embed.color = primary_color
        
        # Criar opções do select menu para configurar usuários
        select_options = []
        if perms_users:
            for user_id in perms_users[:25]:  # Limite de 25 opções
                select_options.append(
                    disnake.SelectOption(
                        label=f"Usuário {user_id[:8]}...",
                        value=user_id,
                        description=f"Configurar permissões do usuário",
                        emoji=emoji.members
                    )
                )
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Adicionar",
                    style=disnake.ButtonStyle.green,
                    emoji=emoji.plus,
                    custom_id="Permissoes_Adicionar"
                ),
                disnake.ui.Button(
                    label="Remover",
                    style=disnake.ButtonStyle.danger,
                    emoji=emoji.minus,
                    custom_id="Permissoes_Remover"
                ),
            ),
        ]
        
        # Adicionar select menu se houver usuários
        if select_options:
            components.append(
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id="Permissoes_SelectUser",
                        placeholder="Selecione um usuário para configurar...",
                        options=select_options
                    )
                )
            )
        
        components.append(
        )
        
        return embed, components

    @staticmethod
    def _chunk_panel_options(all_panels: dict, blocked_panels: list[str]) -> list[list[disnake.SelectOption]]:
        blocked_set = {str(panel_id) for panel_id in blocked_panels}
        option_chunks = []
        current = []
        for panel_id, panel_info in all_panels.items():
            current.append(
                disnake.SelectOption(
                    label=str(panel_info["label"])[:100],
                    value=str(panel_id),
                    description="Bloqueado" if str(panel_id) in blocked_set else "Permitido",
                    emoji=panel_info["emoji"],
                    default=str(panel_id) in blocked_set,
                )
            )
            if len(current) >= MAX_SELECT_OPTIONS:
                option_chunks.append(current)
                current = []
        if current:
            option_chunks.append(current)
        return option_chunks[:MAX_MODAL_SELECTS]

    @staticmethod
    def config_user_components(user_id: str, user_name: str | None = None) -> list:
        from functions.user_permissions import user_permissions, DEFAULT_BLOCKED_PANELS

        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))

        user_perms = user_permissions.get_user_permissions(user_id)
        blocked_panels = list(dict.fromkeys(user_perms.get("blocked_panels", list(DEFAULT_BLOCKED_PANELS)) + list(DEFAULT_BLOCKED_PANELS)))
        all_panels = user_permissions.get_all_panels_info()
        option_chunks = GerenciarPermissoes._chunk_panel_options(all_panels, blocked_panels)
        user_label = user_name or f"Usuario {user_id}"

        container_items = [
            disnake.ui.TextDisplay(f"# {emoji.settings} Configurar Permissoes\n-# Painel > Configuracoes > Gerenciar Permissoes > **{user_label}**"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(
                f"{emoji.members} **Usuario:** <@{user_id}> (`{user_id}`)\n"
                f"{emoji.lock} **Como funciona:** marque os paineis que este usuario NAO pode acessar.\n"
                f"{emoji.shield} **Protegidos:** Lyon Cloud e Permissao ficam sempre bloqueados para quem nao e owner."
            ),
            disnake.ui.Separator(),
        ]

        for index, chunk in enumerate(option_chunks, start=1):
            container_items.append(
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id=f"Permissoes_ConfigPanels:{user_id}:{index}",
                        placeholder=f"Paineis bloqueados {index}/{len(option_chunks)}",
                        options=chunk,
                        min_values=0,
                        max_values=max(1, min(len(chunk), MAX_SELECT_OPTIONS)),
                    )
                )
            )

        container_items.append(
            disnake.ui.ActionRow(
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Permissoes_Voltar"),
            )
        )

        return [disnake.ui.Container(*container_items, **container_kwargs)]

    @staticmethod
    def config_user_embed(user_id: str, user_name: str | None = None):
        from functions.user_permissions import user_permissions, DEFAULT_BLOCKED_PANELS

        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        user_perms = user_permissions.get_user_permissions(user_id)
        blocked_panels = list(dict.fromkeys(user_perms.get("blocked_panels", list(DEFAULT_BLOCKED_PANELS)) + list(DEFAULT_BLOCKED_PANELS)))
        all_panels = user_permissions.get_all_panels_info()
        option_chunks = GerenciarPermissoes._chunk_panel_options(all_panels, blocked_panels)
        user_label = user_name or f"Usuario {user_id}"

        embed = disnake.Embed(
            title="Configurar Permissoes",
            description=(
                f"Usuario: <@{user_id}> (`{user_id}`)\n"
                "Marque os paineis que este usuario NAO pode acessar.\n"
                "Lyon Cloud e Permissao ficam sempre bloqueados para quem nao e owner."
            ),
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)
        embed.set_footer(text=user_label)

        components = []
        for index, chunk in enumerate(option_chunks, start=1):
            components.append(
                disnake.ui.ActionRow(
                    disnake.ui.StringSelect(
                        custom_id=f"Permissoes_ConfigPanels:{user_id}:{index}",
                        placeholder=f"Paineis bloqueados {index}/{len(option_chunks)}",
                        options=chunk,
                        min_values=0,
                        max_values=max(1, min(len(chunk), MAX_SELECT_OPTIONS)),
                    )
                )
            )
        return embed, components

    @staticmethod
    def user_select_panel(action: str):
        colors = db.get_document("custom_colors")
        primary_color_hex = colors.get("primary")
        mode = db.get_document("custom_mode").get("mode")
        is_add = action == "add"
        title = "Adicionar Usuario" if is_add else "Remover Usuario"
        description = (
            "Selecione quem vai receber permissao para mexer no bot."
            if is_add else
            "Selecione quem vai perder a permissao de mexer no bot."
        )
        custom_id = "Permissoes_AddUserSelect" if is_add else "Permissoes_RemoveUserSelect"

        select = disnake.ui.UserSelect(
            custom_id=custom_id,
            placeholder="Selecione usuario(s)...",
            min_values=1,
            max_values=25 if is_add else max(1, min(len(GerenciarPermissoes.get_perms_users()), 25)),
        )
        back = disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="Permissoes_Voltar")

        if mode == "embed":
            embed = disnake.Embed(title=title, description=description)
            if primary_color_hex:
                embed.color = int(primary_color_hex.replace("#", ""), 16)
            return {"embed": embed, "components": [disnake.ui.ActionRow(select), disnake.ui.ActionRow(back)]}

        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))
        return {
            "components": [
                disnake.ui.Container(
                    disnake.ui.TextDisplay(f"# {emoji.members} {title}\n-# Painel > Configuracoes > Gerenciar Permissoes"),
                    disnake.ui.Separator(),
                    disnake.ui.TextDisplay(description),
                    disnake.ui.Separator(),
                    disnake.ui.ActionRow(select),
                    **container_kwargs,
                ),
                disnake.ui.ActionRow(back),
            ]
        }

    async def _refresh_permissions_panel(self, inter: disnake.MessageInteraction | disnake.ModalInteraction):
        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            embed, components = self.panel_embed(inter, self.bot)
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            panel = await self.panel_aLyon(inter, self.bot)
            await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))

    async def _show_user_config_panel(self, inter: disnake.MessageInteraction, user_id: str, *, respond: bool = True, user_name: str | None = None):
        mode = db.get_document("custom_mode").get("mode")
        if respond:
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)

        if not user_name:
            member = inter.guild.get_member(int(user_id)) if inter.guild else None
            cached_user = self.bot.get_user(int(user_id))
            user_name = getattr(member or cached_user, "name", None) or f"Usuario {user_id}"

        if mode == "embed":
            embed, components = self.config_user_embed(user_id, user_name)
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            await inter.edit_original_message(
                content=None,
                embed=None,
                components=self.config_user_components(user_id, user_name),
                flags=disnake.MessageFlags(is_components_v2=True),
            )

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "Permissoes_Adicionar":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                panel = self.user_select_panel("add")
                await inter.edit_original_message(content=None, **panel)
            else:
                await message.wait(inter, send=False)
                panel = self.user_select_panel("add")
                await inter.edit_original_message(content=None, embed=None, **panel, flags=disnake.MessageFlags(is_components_v2=True))
        
        elif inter.component.custom_id == "Permissoes_Remover":
            # Verificar se há usuários para remover
            perms_users = self.get_perms_users()
            
            if not perms_users:
                await inter.response.send_message(
                    f"{emoji.wrong} Não há usuários com permissão para remover.",
                    ephemeral=True
                )
                return
            
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                panel = self.user_select_panel("remove")
                await inter.edit_original_message(content=None, **panel)
            else:
                await message.wait(inter, send=False)
                panel = self.user_select_panel("remove")
                await inter.edit_original_message(content=None, embed=None, **panel, flags=disnake.MessageFlags(is_components_v2=True))
        
        elif inter.component.custom_id == "Permissoes_Voltar":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.panel_embed(inter, self.bot)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                panel = await self.panel_aLyon(inter, self.bot)
                await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))

    @commands.Cog.listener("on_modal_submit")
    async def on_modal_submit(self, inter: disnake.ModalInteraction):
        if inter.custom_id == "Permissoes_Adicionar_Modal":
            # Obter usuário selecionado do UserSelect
            valores = inter.resolved_values
            user_select_values = valores.get("user_select", [])
            
            if not user_select_values:
                await inter.response.send_message(
                    f"{emoji.wrong} Você precisa selecionar um usuário!",
                    ephemeral=True
                )
                return
            
            # Extrair o ID do usuário selecionado
            selected_user = user_select_values[0] if isinstance(user_select_values, list) else user_select_values
            user_id = str(selected_user.id if hasattr(selected_user, 'id') else selected_user)
            
            # Verificar se usuário já tem permissão
            perms_users = self.get_perms_users()
            if user_id in perms_users:
                await inter.response.send_message(
                    f"{emoji.wrong} Este usuário já possui permissão!",
                    ephemeral=True
                )
                return
            
            # Adicionar usuário usando a nova classe perms
            perms.add_user(user_id)
            
            # Responder com sucesso - o painel será atualizado na próxima interação
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.panel_embed(inter, self.bot)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                panel = await self.panel_aLyon(inter, self.bot)
                await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))
        
        elif inter.custom_id == "Permissoes_Remover_Modal":
            # Obter usuário selecionado do UserSelect
            valores = inter.resolved_values
            user_select_values = valores.get("user_select", [])
            
            if not user_select_values:
                await inter.response.send_message(
                    f"{emoji.wrong} Você precisa selecionar um usuário!",
                    ephemeral=True
                )
                return
            
            # Extrair o ID do usuário selecionado
            selected_user = user_select_values[0] if isinstance(user_select_values, list) else user_select_values
            user_id = str(selected_user.id if hasattr(selected_user, 'id') else selected_user)
            
            # Verificar se usuário tem permissão
            perms_users = self.get_perms_users()
            if user_id not in perms_users:
                await inter.response.send_message(
                    f"{emoji.wrong} Este usuário não possui permissão!",
                    ephemeral=True
                )
                return
            
            # Verificar se é o owner (owner tem permissão automática, não está na lista)
            owner_id = self.get_owner_id()
            if user_id == owner_id:
                await inter.response.send_message(
                    f"{emoji.wrong} O dono do bot tem permissão automática e não está na lista!",
                    ephemeral=True
                )
                return
            
            # Remover usuário usando a nova classe perms
            perms.remove_user(user_id)
            
            # Responder com sucesso - o painel será atualizado na próxima interação
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.panel_embed(inter, self.bot)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                panel = await self.panel_aLyon(inter, self.bot)
                await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))
        
        elif inter.custom_id.startswith("Permissoes_ConfigModal_"):
            # Salvar configuração de painéis bloqueados do modal
            user_id = inter.custom_id.replace("Permissoes_ConfigModal_", "")
            
            # Obter valores do select menu
            valores = inter.resolved_values
            blocked_panels = []
            for key, value in valores.items():
                if not key.startswith("blocked_panels"):
                    continue
                if isinstance(value, list):
                    blocked_panels.extend(str(item) for item in value)
                elif value:
                    blocked_panels.append(str(value))
            
            # Importar sistema de permissões
            from functions.user_permissions import user_permissions, DEFAULT_BLOCKED_PANELS
            
            # Painéis sensíveis continuam bloqueados para usuários comuns.
            blocked_panels = list(dict.fromkeys(blocked_panels + list(DEFAULT_BLOCKED_PANELS)))
            
            # Salvar permissões
            user_permissions.set_user_permissions(user_id, blocked_panels)
            
            # Voltar para o painel de permissões
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = self.panel_embed(inter, self.bot)
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                panel = await self.panel_aLyon(inter, self.bot)
                await inter.edit_original_message(**panel, flags=disnake.MessageFlags(is_components_v2=True))

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""

        if cid == "Permissoes_SelectUser":
            await self._show_user_config_panel(inter, str(inter.values[0]))
            return

        if cid == "Permissoes_AddUserSelect":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)

            added = 0
            for user_id in inter.values:
                user_id = str(user_id)
                if user_id not in self.get_perms_users():
                    perms.add_user(user_id)
                    added += 1
            await self._refresh_permissions_panel(inter)
            await inter.followup.send(f"{emoji.correct} {added} usuario(s) adicionados.", ephemeral=True)
            return

        if cid == "Permissoes_RemoveUserSelect":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)

            removed = 0
            owner_id = self.get_owner_id()
            for user_id in inter.values:
                user_id = str(user_id)
                if user_id == owner_id:
                    continue
                if user_id in self.get_perms_users():
                    perms.remove_user(user_id)
                    removed += 1
            await self._refresh_permissions_panel(inter)
            await inter.followup.send(f"{emoji.correct} {removed} usuario(s) removidos.", ephemeral=True)
            return

        if cid.startswith("Permissoes_ConfigPanels:"):
            from functions.user_permissions import user_permissions, DEFAULT_BLOCKED_PANELS

            if not inter.response.is_done():
                try:
                    await inter.response.defer(with_message=False)
                except (disnake.NotFound, disnake.HTTPException):
                    return

            _, user_id, chunk_index = cid.split(":", 2)
            all_panel_ids = list(user_permissions.get_all_panels_info().keys())
            chunks = [all_panel_ids[i:i + MAX_SELECT_OPTIONS] for i in range(0, len(all_panel_ids), MAX_SELECT_OPTIONS)]
            try:
                chunk_ids = set(chunks[int(chunk_index) - 1])
            except (ValueError, IndexError):
                await inter.response.send_message(f"{emoji.wrong} Grupo de permissoes invalido.", ephemeral=True)
                return

            current = user_permissions.get_user_permissions(user_id)
            blocked = set(current.get("blocked_panels", list(DEFAULT_BLOCKED_PANELS)))
            blocked.difference_update(chunk_ids)
            blocked.update(str(value) for value in inter.values)
            blocked.update(DEFAULT_BLOCKED_PANELS)
            user_permissions.set_user_permissions(user_id, list(blocked))

            await self._show_user_config_panel(inter, user_id, respond=False)
            try:
                await inter.followup.send(f"{emoji.correct} Permissoes atualizadas para <@{user_id}>.", ephemeral=True)
            except disnake.HTTPException:
                pass
            return

        if inter.component.custom_id == "Permissoes_SelectUser":
            # Usuário selecionado para configurar permissões
            selected_user_id = inter.values[0]
            
            # Importar sistema de permissões
            from functions.user_permissions import user_permissions, DEFAULT_BLOCKED_PANELS
            
            # Obter permissões atuais do usuário
            user_perms = user_permissions.get_user_permissions(selected_user_id)
            blocked_panels = user_perms.get("blocked_panels", list(DEFAULT_BLOCKED_PANELS))
            
            # Criar opções do select menu com todos os painéis
            all_panels = user_permissions.get_all_panels_info()
            options = []
            
            for panel_id, panel_info in all_panels.items():
                is_blocked = panel_id in blocked_panels
                
                options.append(
                    disnake.SelectOption(
                        label=panel_info["label"],
                        value=panel_id,
                        description="Bloqueado" if is_blocked else "Permitido",
                        emoji=panel_info["emoji"],
                        default=is_blocked  # Marcar como selecionado se estiver bloqueado
                    )
                )
            
            # Buscar nome do usuário
            try:
                user = await self.bot.fetch_user(int(selected_user_id))
                user_name = user.name
            except:
                user_name = f"Usuário {selected_user_id}"
            
            components = []
            option_chunks = [
                options[i:i + MAX_SELECT_OPTIONS]
                for i in range(0, len(options), MAX_SELECT_OPTIONS)
            ]
            visible_chunks = option_chunks[:MAX_MODAL_SELECTS]
            for index, chunk in enumerate(visible_chunks, start=1):
                chunk = chunk[:MAX_SELECT_OPTIONS]
                if not chunk:
                    continue
                components.append(
                    disnake.ui.Label(
                        text=f"Painéis Bloqueados {index}/{len(option_chunks)}",
                        component=disnake.ui.StringSelect(
                            custom_id=f"blocked_panels_{index}",
                            placeholder="Selecione painéis para BLOQUEAR...",
                            options=chunk,
                            min_values=0,
                            max_values=max(1, min(len(chunk), MAX_SELECT_OPTIONS))
                        ),
                        description="Selecione os painéis que o usuário NÃO pode acessar.",
                    )
                )
            
            if not components:
                await inter.response.send_message(
                    f"{emoji.wrong} Nenhum painel foi encontrado para configurar.",
                    ephemeral=True
                )
                return
            
            # Abrir modal com selects divididos em grupos de 25, limite imposto pelo Discord.
            await inter.response.send_modal(
                title=f"Configurar: {user_name[:40]}",
                custom_id=f"Permissoes_ConfigModal_{selected_user_id}",
                components=components
            )
        
        elif inter.component.custom_id.startswith("Permissoes_ConfigPanels_"):
            # Este código não será mais usado, mas mantido por compatibilidade
            pass


def setup(bot: commands.Bot):
    bot.add_cog(GerenciarPermissoes(bot))

