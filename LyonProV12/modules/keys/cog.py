from .manager import *
class KeysPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot; self.pending_creations = {}; self.pending_log_types = {}; self.ensure_data()

    def ensure_data(self):
        data = db.obter(DATA_PATH)
        if not isinstance(data, dict): data = {}
        cfg = data.setdefault("config", {})
        defaults = {"enabled": True, "title": DEFAULT_TITLE, "description": DEFAULT_DESCRIPTION, "button_label": "Resgatar Key", "title_emoji": "🔑", "button_emoji": "✅", "button_color": "green", "channel_id": "", "panel_message_id": "", "banner_url": "", "color": "#5865F2", "expired_message": DEFAULT_EXPIRED_MESSAGE, "log_channels": {}}
        for key, value in defaults.items(): cfg.setdefault(key, value)
        data.setdefault("keys", []); data.setdefault("logs", []); data.setdefault("last_published_at", None)
        migrated = False
        for item in data["keys"]:
            if not isinstance(item, dict):
                continue
            if "role_id" not in item:
                item["role_id"] = ""
                migrated = True
            if "status" not in item:
                item["status"] = "active"
                migrated = True
            if "redeemed_by" not in item:
                item["redeemed_by"] = None
                migrated = True
            if "redeemed_at" not in item:
                item["redeemed_at"] = None
                migrated = True
        if migrated:
            data["logs"].append({"action": "migrate_keys_schema", "at": now_iso()})
        db.salvar(DATA_PATH, data); return data

    def load(self): return self.ensure_data()
    def save(self, data): db.salvar(DATA_PATH, data)
    def config(self): return self.load()["config"].copy()
    def update_config(self, changes):
        data = self.load(); data["config"].update(changes); self.save(data)

    def _guild_for_user(self, user):
        for guild in getattr(self.bot, "guilds", []) or []:
            if guild.get_member(getattr(user, "id", 0)):
                return guild
        return None

    async def _send_key_log(self, event, title, description, actor=None, guild=None):
        if guild is None:
            return False
        channel = await self._ensure_key_log_channel(guild)
        if channel is None:
            return False
        return await send_system_log(self.bot, guild, title=title, description=description, system="Keys", actor=actor, channel_id=channel.id)

    async def _ensure_key_log_channel(self, guild):
        if guild is None:
            return None
        channel_key = "canal_de_logs_de_keys"
        definitions = load_guild_channels(guild)
        raw_id = definitions.get(channel_key)
        channel = guild.get_channel(int(raw_id)) if str(raw_id or "").isdigit() else None
        if channel is not None:
            data = self.load()
            data["config"].setdefault("log_channels", {})["all"] = str(channel.id)
            self.save(data)
            return channel

        setup_cfg = auto_setup.get_config()
        label = "Logs de Keys"
        name = auto_setup.channel_name(channel_key, label, setup_cfg, emoji_icon="🔑")
        category_name = setup_cfg.get("logs_category") or "╺╸ Logs"
        category = next((item for item in guild.categories if str(item.name or "").lower() == str(category_name).lower()), None)
        if category is None:
            try:
                category = await guild.create_category(str(category_name)[:100], reason="Criando categoria de logs de Keys")
            except Exception:
                category = None
        overwrites = None
        if setup_cfg.get("private_logs", True):
            overwrites = {guild.default_role: disnake.PermissionOverwrite(view_channel=False)}
        try:
            channel = await guild.create_text_channel(
                name,
                category=category,
                overwrites=overwrites,
                reason="Criando canal de logs de Keys pelo padrão de Configurações > Canais",
            )
        except Exception as exc:
            print(f"[Keys] Falha ao criar canal oficial de logs: {exc}")
            return None
        definitions[channel_key] = str(channel.id)
        save_guild_channels(guild, definitions)
        data = self.load()
        data["config"].setdefault("log_channels", {})["all"] = str(channel.id)
        self.save(data)
        return channel

    def create_keys(self, quantity, days, hours, minutes, seconds, prefix, role_id, user):
        data = self.load(); created = []
        validity = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        for _ in range(quantity):
            value = f"{prefix.upper()[:12]}-{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}"
            item = {"key": value, "status": "active", "created_at": now_iso(), "expires_at": (datetime.now(timezone.utc) + validity).isoformat(timespec="seconds"), "validity": {"days": days, "hours": hours, "minutes": minutes, "seconds": seconds}, "created_by": str(user.id), "role_id": str(role_id or ""), "redeemed_by": None, "redeemed_at": None}
            data["keys"].append(item); created.append(item)
        data["logs"].append({"action": "create", "quantity": quantity, "role_id": str(role_id or ""), "actor_id": str(user.id), "at": now_iso()}); self.save(data); return created

    def change_key(self, key, status, user):
        data = self.load()
        for item in data["keys"]:
            if item.get("key", "").upper() == key:
                item["status"] = status; item["updated_at"] = now_iso(); data["logs"].append({"action": status, "key": key, "actor_id": str(user.id), "at": now_iso()}); self.save(data); return item
        return None

    def redeem_key(self, key, user):
        data = self.load()
        for item in data["keys"]:
            if item.get("key", "").upper() != key: continue
            current = status_of(item)
            if current == "expired": return "expired"
            if current != "active": return None
            item.update({"status": "redeemed", "redeemed_by": str(user.id), "redeemed_at": now_iso()})
            role_id = numeric_id(item.get("role_id")); guild = getattr(user, "guild", None)
            role = guild.get_role(int(role_id)) if role_id and guild else None
            member = user if guild else None
            if role_id and role is None:
                for candidate in getattr(self.bot, "guilds", []):
                    candidate_role = candidate.get_role(int(role_id))
                    candidate_member = candidate.get_member(user.id)
                    if candidate_role and candidate_member:
                        guild, role, member = candidate, candidate_role, candidate_member
                        break
            if role and member:
                try:
                    import asyncio
                    asyncio.create_task(member.add_roles(role, reason=f"Key resgatada por {user}"))
                except Exception:
                    pass
            data["logs"].append({"action": "redeem", "key": key, "actor_id": str(user.id), "at": now_iso()}); self.save(data); return item
        return None

    def _channel(self, inter):
        cid = numeric_id(self.config().get("channel_id"))
        if cid: return self.bot.get_channel(int(cid)) or (inter.guild.get_channel(int(cid)) if getattr(inter, "guild", None) else None)
        return getattr(inter, "channel", None)

    def _stats(self):
        counts = {key: 0 for key in STATUS_LABELS}
        for item in self.load()["keys"]: counts[status_of(item)] = counts.get(status_of(item), 0) + 1
        return counts, sum(counts.values())

    def _admin_components(self, filter_status="all"):
        data = self.load()
        cfg = data["config"]
        counts, total = self._stats()
        channel = f"<#{cfg['channel_id']}>" if cfg.get("channel_id") else "Canal atual"
        status = "Ativo" if cfg.get("enabled") else "Desativado"
        users = {str(item.get("redeemed_by")) for item in data.get("keys", []) if item.get("redeemed_by")}
        log_channels = cfg.get("log_channels") if isinstance(cfg.get("log_channels"), dict) else {}
        log_channel = f"<#{log_channels.get('all')}>" if log_channels.get("all") else "Não configurado"
        info = (
            f"{internal_emoji('power', 'power')} **Status:** `{status}`\n"
            f"{internal_emoji('textc', 'textc')} **Publicação:** {channel}\n"
            f"{internal_emoji('chart', 'chart')} **Registros:** `{total}` | **Usuários:** `{len(users)}`\n"
            f"{internal_emoji('clock', 'clock')} **Última publicação:** `{data.get('last_published_at') or 'Nunca'}`\n"
            f"{internal_emoji('settings', 'settings')} **Canal de logs:** {log_channel}\n"
            f"**Ativas:** `{counts['active']}` · **Resgatadas:** `{counts['redeemed']}` · **Expiradas:** `{counts['expired']}` · **Revogadas:** `{counts['revoked']}`"
        )
        container_kwargs = {}
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary") if isinstance(colors, dict) else None
        if primary_color_hex:
            try:
                container_kwargs["accent_colour"] = disnake.Colour(int(str(primary_color_hex).replace("#", ""), 16))
            except (TypeError, ValueError):
                pass
        enabled = bool(cfg.get("enabled"))
        admin_emoji = internal_emoji("save", "💾")
        children = [
            disnake.ui.TextDisplay(f"# {admin_emoji} Gerenciar Key\n-# Painel > Sistemas > **Key**\n\n{info}"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Desativar" if enabled else "Ativar", emoji=internal_emoji("power", "⚡"), style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.green, custom_id="Keys_Toggle"),
                disnake.ui.Button(label="Criar Key", emoji=internal_emoji("save", "💾"), style=disnake.ButtonStyle.green, custom_id="Keys_Create", disabled=not enabled),
                disnake.ui.Button(label="Apagar Key", emoji=internal_emoji("delete", ""), style=disnake.ButtonStyle.danger, custom_id="Keys_Delete", disabled=not enabled),
                disnake.ui.Button(label="Expirar Key", emoji=internal_emoji("clock", "🕒"), style=disnake.ButtonStyle.secondary, custom_id="Keys_Expire", disabled=not enabled),
                disnake.ui.Button(label="Editar canal", emoji=internal_emoji("textc", "📋"), style=disnake.ButtonStyle.secondary, custom_id="Keys_Channel", disabled=not enabled),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Publicar", emoji=internal_emoji("announcement", ""), style=disnake.ButtonStyle.green, custom_id="Keys_Publish", disabled=not enabled),
                disnake.ui.Button(label="Editar painel", emoji=internal_emoji("settings", "⚙️"), style=disnake.ButtonStyle.secondary, custom_id="Keys_EditPanel", disabled=not enabled),
                disnake.ui.Button(label="Editar botão", emoji=internal_emoji("edit", "✏️"), style=disnake.ButtonStyle.secondary, custom_id="Keys_Button", disabled=not enabled),
                disnake.ui.Button(label="Editar banner", emoji=internal_emoji("image", "🖼️"), style=disnake.ButtonStyle.secondary, custom_id="Keys_Banner", disabled=not enabled),
                disnake.ui.Button(label="Editar cor", emoji=internal_emoji("paint", "🎨"), style=disnake.ButtonStyle.secondary, custom_id="Keys_Color", disabled=not enabled),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Mensagem de expiração", emoji=internal_emoji("clock", "🕒"), style=disnake.ButtonStyle.secondary, custom_id="Keys_Expiration", disabled=not enabled),
                disnake.ui.Button(label="Configurar logs", emoji=internal_emoji("textc", "📋"), style=disnake.ButtonStyle.secondary, custom_id="Keys_LogChannelConfig", disabled=not enabled),
                disnake.ui.Button(label="Criar canal de logs", emoji=internal_emoji("textc", "📋"), style=disnake.ButtonStyle.secondary, custom_id="Keys_Logs", disabled=not enabled),
            ),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(disnake.ui.StringSelect(placeholder="Consultar registro de keys", custom_id="Keys_Filter", disabled=not enabled, options=[disnake.SelectOption(label="Todas as keys", value="all", emoji=internal_emoji("textc", "📝")), *[disnake.SelectOption(label=label, value=status, emoji=STATUS_EMOJIS[status]) for status, label in STATUS_LABELS.items()]])),
        ]
        return [disnake.ui.Container(*children, **container_kwargs)]

    def _record_text(self, filter_status="all"):
        data = self.load()
        visible = [item for item in data.get("keys", []) if filter_status == "all" or status_of(item) == filter_status][-25:]
        if not visible:
            return "Nenhuma key encontrada nesse filtro."
        lines = []
        for item in visible:
            role_id = numeric_id(item.get("role_id"))
            role_label = f"<@&{role_id}>" if role_id else "Cargo não definido"
            expires_at = str(item.get("expires_at") or "N/A")[:10]
            current_status = status_of(item)
            lines.append(f"{STATUS_EMOJIS.get(current_status, internal_emoji('textc', ''))} `{item.get('key', 'N/A')}` · **{STATUS_LABELS.get(current_status, current_status)}** · cargo {role_label} · expira `{expires_at}`")
        return "\n".join(lines)

    def _record_components(self, filter_status="all"):
        label = STATUS_LABELS.get(filter_status, "Todas as keys")
        record_emoji = STATUS_EMOJIS.get(filter_status, internal_emoji("textc", "📝"))
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {internal_emoji('save', '💾')} Registro de Keys\n-# Gerenciar Key > Consulta de registro\n\n{record_emoji} **Filtro:** `{label}`\n\n{self._record_text(filter_status)}"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(f"{internal_emoji('clock', '🕒')} Os dados acima são carregados do registro persistente do sistema."),
            )
        ]

    def _color(self):
        raw = str(self.config().get("color") or "").lstrip("#")
        try: return disnake.Colour(int(raw, 16))
        except Exception: return disnake.Colour.blurple()

    def _public_components(self):
        cfg = self.config(); title = f"{resolve_custom_emoji(cfg.get('title_emoji'), bot=self.bot, fallback='🔑')} {cfg.get('title', DEFAULT_TITLE)}"; children = []
        banner = str(cfg.get("banner_url") or "")
        if banner.startswith(("http://", "https://")):
            try:
                children.append(disnake.ui.MediaGallery(disnake.MediaGalleryItem(banner, description="Banner do painel de resgate")))
                children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))
            except Exception: pass
        children.extend([disnake.ui.TextDisplay(f"# {title}\n\n{cfg.get('description', DEFAULT_DESCRIPTION)}\n\nClique no botão abaixo para validar sua key."), disnake.ui.ActionRow(disnake.ui.Button(label=cfg.get("button_label", "Resgatar Key"), style=button_style(cfg.get("button_color", "green")), emoji=resolve_custom_emoji(cfg.get("button_emoji"), bot=self.bot, fallback="✅"), custom_id="Keys_Redeem"))])
        return [disnake.ui.Container(*children, accent_colour=self._color())]

    def display_keys_panel(self, inter): return self._admin_components()

    async def _publish(self, inter):
        channel = self._channel(inter)
        if channel is None:
            await inter.followup.send(f"{emoji.wrong} Canal não encontrado. Use **Editar canal**.", ephemeral=True); return
        message = await channel.send(components=self._public_components(), flags=disnake.MessageFlags(is_components_v2=True))
        data = self.load(); data["config"]["panel_message_id"] = str(message.id); data["last_published_at"] = now_iso(); self.save(data)
        await self._send_key_log("published", "Painel de Keys publicado", f"O painel de resgate foi publicado em {channel.mention}.", actor=inter.user, guild=inter.guild)
        await inter.followup.send(f"{emoji.correct} Painel de resgate publicado em {channel.mention}.", ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def on_keys_button(self, inter):
        cid = getattr(inter.component, "custom_id", "")
        if not cid.startswith("Keys_"): return
        if cid == "Keys_Create": return await inter.response.send_modal(CreateKeysModal(self))
        if cid == "Keys_Delete": return await inter.response.send_modal(KeyActionModal(self, "delete"))
        if cid == "Keys_Expire": return await inter.response.send_modal(KeyActionModal(self, "expire"))
        if cid == "Keys_EditPanel": return await inter.response.send_modal(KeysConfigModal(self))
        if cid == "Keys_Button": return await inter.response.send_modal(KeysButtonModal(self))
        if cid == "Keys_Banner": return await inter.response.send_modal(KeysBannerModal(self))
        if cid == "Keys_Color": return await inter.response.send_modal(KeysColorModal(self))
        if cid == "Keys_Expiration": return await inter.response.send_modal(KeysExpirationModal(self))
        if cid == "Keys_Toggle":
            enabled = not bool(self.config().get("enabled"))
            self.update_config({"enabled": enabled})
            await self._send_key_log("status", "Status do sistema de Keys alterado", f"O sistema de Keys foi {'ativado' if enabled else 'desativado'}.", actor=inter.user, guild=inter.guild)
            return await inter.response.edit_message(components=self._admin_components())
        if not self.config().get("enabled"):
            return await inter.response.send_message(f"{emoji.wrong} O sistema de Keys está desativado. Clique em Ativar para continuar.", ephemeral=True)
        if cid == "Keys_LogChannelConfig":
            return await inter.response.send_message("Escolha o canal que receberá todos os logs de Keys.", components=[disnake.ui.ActionRow(disnake.ui.ChannelSelect(custom_id="Keys_LogChannelSelect", placeholder="Selecionar canal de logs", channel_types=[disnake.ChannelType.text], min_values=1, max_values=1))], ephemeral=True)
        if cid == "Keys_Logs":
            if not inter.guild:
                return await inter.response.send_message(f"{emoji.wrong} Essa ação precisa ser usada dentro de um servidor.", ephemeral=True)
            await inter.response.defer(ephemeral=True)
            channel = await self._ensure_key_log_channel(inter.guild)
            if channel:
                description = ("Foi criado/verificado `1` canal automaticamente.\n" "Canais de logs atualizados: `1`\n" f"- {channel.mention} (`{channel.name}`)")
                await self._send_key_log("all", "Canal automático de Keys criado", description, actor=inter.user, guild=inter.guild)
            return await inter.followup.send(f"{emoji.correct} Canal de logs de Keys criado/verificado: {channel.mention if channel else 'nenhum canal disponível'}.", ephemeral=True)
        if cid == "Keys_Channel":
            return await inter.response.send_message("Selecione o canal onde o painel de resgate será publicado.", components=[disnake.ui.ActionRow(disnake.ui.ChannelSelect(custom_id="Keys_ChannelSelect", placeholder="Selecionar canal", channel_types=[disnake.ChannelType.text], min_values=1, max_values=1))], ephemeral=True)
        if cid == "Keys_Redeem": return await inter.response.send_modal(RedeemKeyModal(self))
        if cid == "Keys_Publish":
            await inter.response.defer(ephemeral=True); return await self._publish(inter)

    @commands.Cog.listener("on_dropdown")
    async def on_keys_dropdown(self, inter):
        cid = getattr(inter.component, "custom_id", "")
        if cid == "Keys_Filter":
            if not self.config().get("enabled"):
                return await inter.response.send_message(f"{emoji.wrong} O sistema de Keys está desativado.", ephemeral=True)
            selected_status = inter.values[0] if inter.values else "all"
            return await inter.response.send_message(components=self._record_components(selected_status), flags=disnake.MessageFlags(is_components_v2=True), ephemeral=True)
        if cid == "Keys_ChannelSelect":
            selected = inter.values[0] if inter.values else None
            selected_id = str(getattr(selected, "id", selected))
            self.update_config({"channel_id": numeric_id(selected_id)})
            await inter.response.send_message(f"{emoji.correct} Canal de publicação definido para <#{selected_id}>.", ephemeral=True); return
        if cid == "Keys_LogChannelSelect":
            selected = inter.values[0] if inter.values else None
            selected_id = numeric_id(getattr(selected, "id", selected))
            data = self.load(); data["config"].setdefault("log_channels", {})["all"] = selected_id; self.save(data)
            await inter.response.send_message(f"{emoji.correct} Canal de logs de Keys definido para <#{selected_id}>.", ephemeral=True); return
        if cid == "Keys_LogType":
            event = str(inter.values[0]) if inter.values else "all"
            self.pending_log_types[str(inter.user.id)] = event
            return await inter.response.send_message("Agora selecione o canal que receberá esse log.", components=[disnake.ui.ActionRow(disnake.ui.ChannelSelect(custom_id="Keys_LogChannel", placeholder="Selecionar canal de logs", channel_types=[disnake.ChannelType.text], min_values=1, max_values=1))], ephemeral=True)
        if cid == "Keys_LogChannel":
            selected = inter.values[0] if inter.values else None
            selected_id = numeric_id(getattr(selected, "id", selected))
            event = self.pending_log_types.pop(str(inter.user.id), "all")
            data = self.load(); channels = data["config"].setdefault("log_channels", {}); channels[event] = selected_id; self.save(data)
            await inter.response.send_message(f"{emoji.correct} Canal de logs definido para <#{selected_id}>.", ephemeral=True); return
        if cid == "Keys_CreateRole":
            pending = self.pending_creations.pop(str(inter.user.id), None)
            if not pending:
                await inter.response.send_message(f"{emoji.wrong} Essa criação expirou. Clique em Criar Keys novamente.", ephemeral=True); return
            role = inter.values[0] if inter.values else None
            role_id = str(getattr(role, "id", role))
            keys = self.create_keys(**pending, role_id=role_id, user=inter.user)
            content = "\n".join(f"`{item['key']}` — <@&{role_id}> — expira `{item['expires_at'][:10]}`" for item in keys)
            await self._send_key_log("created", "Keys criadas", f"Foram criadas `{len(keys)}` key(s), vinculadas ao cargo <@&{role_id}>.", actor=inter.user, guild=inter.guild)
            await inter.response.send_message(f"{emoji.correct} **{len(keys)} key(s) criada(s):**\n{content}", ephemeral=True)

    @commands.Cog.listener("on_message")
    async def on_keys_dm(self, message):
        if getattr(message.author, "bot", False) or getattr(message, "guild", None) is not None:
            return
        key = str(getattr(message, "content", "") or "").strip().upper()
        if not key or "-" not in key or len(key) < 8:
            return
        result = self.redeem_key(key, message.author)
        if result == "expired":
            await self._send_key_log("expired", "Tentativa de resgate de key expirada", f"A key `{key}` foi informada por DM, mas estava expirada.", actor=message.author, guild=self._guild_for_user(message.author))
            await message.channel.send(f"🟠 {self.config().get('expired_message', DEFAULT_EXPIRED_MESSAGE)}")
        elif result:
            await self._send_key_log("redeemed", "Key resgatada por DM", f"A key `{key}` foi resgatada por mensagem direta.", actor=message.author, guild=self._guild_for_user(message.author))
            await message.channel.send(f"{emoji.correct} Key resgatada com sucesso. O cargo só pode ser aplicado quando o resgate for feito dentro do servidor; os detalhes foram registrados.")
        else:
            await message.channel.send(f"{emoji.wrong} Esta key é inválida, já foi utilizada ou foi revogada.")


def setup(bot):
    bot.add_cog(KeysPanel(bot))
