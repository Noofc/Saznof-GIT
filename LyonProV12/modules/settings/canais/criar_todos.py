import re

import disnake
from disnake.ext import commands

from functions import auto_setup
from functions.database import database as db
from functions.emoji import emoji
from functions.guild_channels import is_main_guild, load_guild_channels, save_guild_channels
from functions.message import message, embed_message
from functions.system_logs import send_system_log
from .listar import CANAIS_OPCOES
from .cog import ConfigurarCanais


class MensagensCanais:
    @staticmethod
    def canal_criado_components(ch: disnake.TextChannel, auto: bool) -> disnake.ui.Container:
        origem = "Criar Todos os Canais Automaticamente" if auto else "Criar Canal"
        return disnake.ui.Container(
            disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# {origem} > Canal Criado"),
            disnake.ui.Separator(),
            disnake.ui.TextDisplay(f"**Informacoes do canal:**\nID: `{ch.id}`\nNome: `{ch.name}`\nMencao: {ch.mention}"),
        )

    @staticmethod
    def canais_criados_components(criados: list[disnake.TextChannel]) -> list[disnake.ui.Container]:
        canais = ", ".join(f"{c.mention} (`{c.id}`)" for c in criados)
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(
                    "**Informacoes dos canais criados:**\n"
                    f"`{len(criados)}` canais criados com sucesso."
                ),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(canais[:3900]),
            )
        ]

    @staticmethod
    def canal_criado_embed(ch: disnake.TextChannel, auto: bool):
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")
        embed = disnake.Embed(
            title="Canal Criado",
            description=f"**Informacoes do canal:**\nID: `{ch.id}`\nNome: `{ch.name}`\nMencao: {ch.mention}",
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)
        return embed, []

    @staticmethod
    def canais_criados_embed(criados: list[disnake.TextChannel]):
        colors = db.get_document("custom_colors") or {}
        primary_color_hex = colors.get("primary")
        embed = disnake.Embed(
            title="Canais Criados",
            description=f"`{len(criados)}` canais criados com sucesso.",
        )
        if primary_color_hex:
            embed.color = int(primary_color_hex.replace("#", ""), 16)
        embed.add_field(
            name="Canais:",
            value=", ".join(f"{c.mention} (`{c.id}`)" for c in criados)[:1024],
        )
        return embed, []


class CriarTodosCanais(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _normalize_channel_name(self, value: str) -> str:
        raw = str(value or "").strip().lower()
        raw = raw.replace("/", "-").replace("\\", "-")
        raw = re.sub(r"[^\w-]+", "-", raw, flags=re.UNICODE)
        raw = re.sub(r"[-_]+", "-", raw).strip("-")
        return raw

    def _channel_from_id(self, guild: disnake.Guild, raw_id) -> disnake.TextChannel | None:
        try:
            channel = guild.get_channel(int(raw_id))
        except (TypeError, ValueError):
            return None
        return channel if isinstance(channel, disnake.TextChannel) else None

    def _find_existing_channels(self, guild: disnake.Guild, raw_id, name: str) -> list[disnake.TextChannel]:
        channels = []
        seen = set()

        def add(channel):
            if isinstance(channel, disnake.TextChannel) and channel.id not in seen:
                seen.add(channel.id)
                channels.append(channel)

        add(self._channel_from_id(guild, raw_id))
        clean_name = str(name or "").strip().lower()
        if clean_name:
            for channel in guild.text_channels:
                if str(channel.name or "").strip().lower() == clean_name:
                    add(channel)
        return channels

    async def _delete_existing_channels(self, channels: list[disnake.TextChannel], reason: str) -> list[str]:
        deleted = []
        seen = set()
        for channel in channels:
            if not isinstance(channel, disnake.TextChannel) or channel.id in seen:
                continue
            seen.add(channel.id)
            name = channel.name
            try:
                await channel.delete(reason=f"{reason} - recriando canal automatico")
                deleted.append(name)
            except Exception as exc:
                print(f"[Canais] Falha ao apagar canal antigo {channel.id} ({name}): {exc}")
        return deleted

    def _managed_log_names(self, setup_cfg: dict) -> set[str]:
        names = set()
        custom_names = setup_cfg.get("channel_names") if isinstance(setup_cfg, dict) else {}
        custom_names = custom_names if isinstance(custom_names, dict) else {}

        for key, label, _emoji_icon in CANAIS_OPCOES:
            if not auto_setup.is_logs_key(key):
                continue
            variants = [
                auto_setup.channel_name(key, label, setup_cfg),
                auto_setup.slugify(label),
                auto_setup.slugify(key.replace("canal_de_", "").replace("_", " ")),
            ]
            custom = str(custom_names.get(key) or "").strip()
            if custom:
                variants.append(auto_setup.slugify(custom))
            for variant in variants:
                normalized = self._normalize_channel_name(variant)
                if normalized:
                    names.add(normalized)
        return names

    def _is_log_channel_name(self, channel_name: str, managed_names: set[str]) -> bool:
        normalized = self._normalize_channel_name(channel_name)
        if not normalized:
            return False
        if normalized in managed_names:
            return True
        parts = {part for part in normalized.split("-") if part}
        return "logs" in parts or "log" in parts or normalized.startswith("logs-") or normalized.endswith("-logs")

    def _collect_log_channels_to_delete(
        self,
        guild: disnake.Guild,
        defs: dict,
        setup_cfg: dict,
        log_categories: list[disnake.CategoryChannel],
    ) -> list[disnake.TextChannel]:
        channels = []
        seen = set()
        managed_names = self._managed_log_names(setup_cfg)
        log_category_ids = {category.id for category in log_categories if isinstance(category, disnake.CategoryChannel)}

        def add(channel):
            if isinstance(channel, disnake.TextChannel) and channel.id not in seen:
                seen.add(channel.id)
                channels.append(channel)

        for key, label, _emoji_icon in CANAIS_OPCOES:
            if not auto_setup.is_logs_key(key):
                continue
            add(self._channel_from_id(guild, defs.get(key)))
            expected_name = auto_setup.channel_name(key, label, setup_cfg)
            for channel in guild.text_channels:
                if self._normalize_channel_name(channel.name) == self._normalize_channel_name(expected_name):
                    add(channel)

        for channel in guild.text_channels:
            in_logs_category = bool(channel.category_id in log_category_ids)
            if in_logs_category:
                add(channel)
                continue
            if self._is_log_channel_name(channel.name, managed_names):
                add(channel)

        return channels

    def _collect_regular_channels_to_delete(
        self,
        guild: disnake.Guild,
        defs: dict,
        setup_cfg: dict,
    ) -> list[disnake.TextChannel]:
        channels = []
        seen = set()

        def add(channel):
            if isinstance(channel, disnake.TextChannel) and channel.id not in seen:
                seen.add(channel.id)
                channels.append(channel)

        for key, label, _emoji_icon in CANAIS_OPCOES:
            if auto_setup.is_logs_key(key):
                continue
            add(self._channel_from_id(guild, defs.get(key)))
            expected_name = auto_setup.channel_name(key, label, setup_cfg)
            expected_norm = self._normalize_channel_name(expected_name)
            for channel in guild.text_channels:
                if self._normalize_channel_name(channel.name) == expected_norm:
                    add(channel)
        return channels

    def _collect_categories_by_names(self, guild: disnake.Guild, names: set[str], *, include_log_like: bool = False) -> list[disnake.CategoryChannel]:
        categories = []
        seen = set()
        normalized_names = {self._normalize_channel_name(name) for name in names if str(name or "").strip()}

        for category in guild.categories:
            normalized = self._normalize_channel_name(category.name)
            parts = {part for part in normalized.split("-") if part}
            matched = normalized in normalized_names
            if include_log_like and ("logs" in parts or "log" in parts or normalized.startswith("logs-") or normalized.endswith("-logs")):
                matched = True
            if matched and category.id not in seen:
                seen.add(category.id)
                categories.append(category)
        return categories

    def _collect_log_categories(self, guild: disnake.Guild, setup_cfg: dict) -> list[disnake.CategoryChannel]:
        separator = str(setup_cfg.get("separator") or auto_setup.DEFAULT_SEPARATOR)
        names = {
            setup_cfg.get("logs_category"),
            "Logs",
            "logs",
            f"{separator} Logs",
            f"{auto_setup.DEFAULT_SEPARATOR} Logs",
            "╺╸ Logs",
        }
        return self._collect_categories_by_names(guild, names, include_log_like=True)

    def _collect_public_categories(self, guild: disnake.Guild, setup_cfg: dict) -> list[disnake.CategoryChannel]:
        separator = str(setup_cfg.get("separator") or auto_setup.DEFAULT_SEPARATOR)
        names = {
            setup_cfg.get("community_category"),
            "Comunidade",
            "comunidade",
            f"{separator} Comunidade",
            f"{auto_setup.DEFAULT_SEPARATOR} Comunidade",
            "╺╸ Comunidade",
        }
        return self._collect_categories_by_names(guild, names)

    async def _delete_empty_categories(self, guild: disnake.Guild, categories: list[disnake.CategoryChannel], reason: str) -> list[str]:
        deleted = []
        seen = set()
        for category in categories:
            if not isinstance(category, disnake.CategoryChannel) or category.id in seen:
                continue
            seen.add(category.id)
            has_channels = any(getattr(channel, "category_id", None) == category.id for channel in guild.channels)
            if has_channels:
                continue
            try:
                name = category.name
                await category.delete(reason=f"{reason} - removendo categoria automatica antiga")
                deleted.append(name)
            except Exception as exc:
                print(f"[Canais] Falha ao apagar categoria antiga {category.id} ({category.name}): {exc}")
        return deleted

    async def _get_or_create_category(self, guild: disnake.Guild, name: str, reason: str):
        clean_name = str(name or "").strip()[:100] or "╺╸ Sistema"
        category = next((c for c in guild.categories if (c.name or "").strip().lower() == clean_name.lower()), None)
        if category:
            return category
        try:
            return await guild.create_category(clean_name, reason=reason)
        except Exception:
            return None

    def _sync_document_channel(self, doc_key: str, field: str, channel_key: str, defs: dict, synced: list[str]) -> None:
        channel_id = defs.get(channel_key)
        if not channel_id:
            return
        data = db.get_document(doc_key) or {}
        if not isinstance(data, dict):
            data = {}
        value = int(channel_id) if str(channel_id).isdigit() else channel_id
        if str(data.get(field) or "") == str(value):
            return
        data[field] = value
        db.save_document(doc_key, data)
        synced.append(doc_key)

    def _sync_json_channel(self, path: str, field: str, channel_key: str, defs: dict, synced: list[str]) -> None:
        channel_id = defs.get(channel_key)
        if not channel_id:
            return
        data = db.obter(path)
        if not isinstance(data, dict):
            data = {}
        if str(data.get(field) or "") == str(channel_id):
            return
        data[field] = str(channel_id)
        db.salvar(path, data)
        synced.append(path)

    def _first_channel_id(self, defs: dict, *channel_keys: str):
        for channel_key in channel_keys:
            channel_id = defs.get(channel_key)
            if channel_id:
                return channel_id
        return None

    def _normal_channel_id(self, channel_id):
        return int(channel_id) if str(channel_id).isdigit() else channel_id

    def _sync_nested_document_channel(self, doc_key: str, section_key: str, field: str, channel_id, synced: list[str]) -> None:
        if not channel_id:
            return
        data = db.get_document(doc_key) or {}
        if not isinstance(data, dict):
            data = {}
        section = data.get(section_key)
        if not isinstance(section, dict):
            section = {}
            data[section_key] = section
        value = self._normal_channel_id(channel_id)
        if str(section.get(field) or "") == str(value):
            return
        section[field] = value
        db.save_document(doc_key, {}, data)
        synced.append(f"{doc_key}.{section_key}")

    def _sync_advanced_security_channel(self, guild_id: int, channel_id, synced: list[str]) -> None:
        if not channel_id:
            return
        data = db.get_document("protection_advanced_security") or {}
        if not isinstance(data, dict):
            data = {}
        guilds = data.get("guilds")
        if not isinstance(guilds, dict):
            guilds = {}
            data["guilds"] = guilds
        cfg = guilds.get(str(guild_id))
        if not isinstance(cfg, dict):
            cfg = {}
            guilds[str(guild_id)] = cfg
        value = self._normal_channel_id(channel_id)
        if str(cfg.get("log_channel_id") or "") == str(value):
            return
        cfg["log_channel_id"] = value
        db.save_document("protection_advanced_security", data)
        synced.append("protection_advanced_security")

    def _sync_protection_log_channels(self, guild_id: int, defs: dict, synced: list[str]) -> None:
        protection_default = self._first_channel_id(
            defs,
            "canal_de_logs_de_protecao",
            "canal_de_logs_de_antifraude",
            "canal_de_logs_do_sistema",
        )
        protection_updates = [
            ("protection_privatizacoes_apps", "privatizacao_apps_avancado", protection_default),
            (
                "protection_privatizacoes_cargos",
                "privatizacao_cargos_avancado",
                self._first_channel_id(defs, "canal_de_logs_de_cargos_editados", "canal_de_logs_de_protecao", "canal_de_logs_do_sistema"),
            ),
            ("protection_privatizacoes_mencoes", "privatizacao_mencoes_avancado", protection_default),
            (
                "protection_privatizacoes_perms",
                "privatizacao_permissoes_avancado",
                self._first_channel_id(defs, "canal_de_logs_de_permissoes_removidas", "canal_de_logs_de_protecao", "canal_de_logs_do_sistema"),
            ),
            (
                "protection_privatizacoes_persistencia",
                "persistencia_canais_avancado",
                self._first_channel_id(defs, "canal_de_logs_de_canais_excluidos", "canal_de_logs_de_protecao", "canal_de_logs_do_sistema"),
            ),
            ("protection_privatizacoes_urls", "privatizacao_urls_avancado", protection_default),
            (
                "protection_protecaogeral_banimentos",
                "banimentos_avancado",
                self._first_channel_id(defs, "canal_de_logs_de_banimentos", "canal_de_logs_de_protecao", "canal_de_logs_do_sistema"),
            ),
            (
                "protection_protecaogeral_canais",
                "canais_avancado",
                self._first_channel_id(defs, "canal_de_logs_de_canais_editados", "canal_de_logs_de_protecao", "canal_de_logs_do_sistema"),
            ),
            (
                "protection_protecaogeral_cargos",
                "cargos_avancado",
                self._first_channel_id(defs, "canal_de_logs_de_cargos_editados", "canal_de_logs_de_protecao", "canal_de_logs_do_sistema"),
            ),
            ("protection_protecaogeral_comandosext", "comandosext_avancado", protection_default),
            (
                "protection_protecaogeral_expulsoes",
                "expulsoes_avancado",
                self._first_channel_id(defs, "canal_de_logs_de_expulsoes", "canal_de_logs_de_protecao", "canal_de_logs_do_sistema"),
            ),
            ("protection_protecaogeral_webhooks", "webhooks_avancado", protection_default),
        ]

        for doc_key, section_key, channel_id in protection_updates:
            self._sync_nested_document_channel(doc_key, section_key, "canal_logs", channel_id, synced)

        self._sync_advanced_security_channel(guild_id, protection_default, synced)

    def _sync_system_log_channels(self, guild_id: int, defs: dict) -> list[str]:
        synced = []
        if not is_main_guild(guild_id):
            self._sync_document_channel(f"middleman_{guild_id}", "logs_channel_id", "canal_de_logs_de_middleman", defs, synced)
            self._sync_advanced_security_channel(
                guild_id,
                self._first_channel_id(defs, "canal_de_logs_de_protecao", "canal_de_logs_de_antifraude", "canal_de_logs_do_sistema"),
                synced,
            )
            return synced

        doc_updates = [
            ("robux_config", "log_channel_id", "canal_de_logs_de_robux"),
            ("stock_config", "logs_channel_id", "canal_de_logs_de_restock"),
            ("antifraud_config", "log_channel_id", "canal_de_logs_de_antifraude"),
            ("scam_detector_config", "log_channel_id", "canal_de_logs_de_antifraude"),
            (f"middleman_{guild_id}", "logs_channel_id", "canal_de_logs_de_middleman"),
        ]
        for doc_key, field, channel_key in doc_updates:
            self._sync_document_channel(doc_key, field, channel_key, defs, synced)

        self._sync_json_channel("database/fivem_system.json", "log_channel_id", "canal_de_logs_de_fivem", defs, synced)
        self._sync_json_channel("database/bateponto_system.json", "log_channel_id", "canal_de_logs_de_bate_ponto", defs, synced)
        self._sync_protection_log_channels(guild_id, defs, synced)
        return synced

    @commands.Cog.listener("on_button_click")
    async def criar_todos_canais(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id != "Configuracoes_CriarTodosCanais":
            return

        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter, send=False)

        setup_cfg = auto_setup.get_config()
        guild = inter.guild
        if not guild:
            return
        defs = load_guild_channels(guild)

        reason = f"Auto-criacao pelo painel de configuracoes - {inter.author.name} ({inter.author.id})"
        old_log_categories = self._collect_log_categories(guild, setup_cfg)
        old_public_categories = self._collect_public_categories(guild, setup_cfg)

        private_logs = bool(setup_cfg.get("private_logs", True))
        send_created_message = bool(setup_cfg.get("send_created_message", True))
        criados = []
        apagados = []
        categorias_apagadas = []

        channels_to_delete = []
        channels_to_delete.extend(self._collect_log_channels_to_delete(guild, defs, setup_cfg, old_log_categories))
        channels_to_delete.extend(self._collect_regular_channels_to_delete(guild, defs, setup_cfg))
        if channels_to_delete:
            apagados.extend(await self._delete_existing_channels(channels_to_delete, reason))

        categorias_apagadas.extend(await self._delete_empty_categories(guild, old_log_categories + old_public_categories, reason))

        cat_logs = await self._get_or_create_category(guild, setup_cfg.get("logs_category"), reason)
        cat_public = await self._get_or_create_category(guild, setup_cfg.get("community_category"), reason)

        for key, label, _emoji_icon in CANAIS_OPCOES:
            name = auto_setup.channel_name(key, label, setup_cfg)
            is_log_channel = auto_setup.is_logs_key(key)
            category = cat_logs if is_log_channel and cat_logs else cat_public
            overwrites = None
            if is_log_channel and private_logs:
                overwrites = {guild.default_role: disnake.PermissionOverwrite(view_channel=False)}

            try:
                ch = await guild.create_text_channel(
                    name,
                    overwrites=overwrites,
                    category=category,
                    reason=reason,
                )
            except Exception as exc:
                print(f"[Canais] Falha ao criar {key}: {exc}")
                continue

            defs[key] = str(ch.id)
            criados.append(ch)

            if send_created_message:
                try:
                    if mode == "embed":
                        embed, components = MensagensCanais.canal_criado_embed(ch, auto=True)
                        await ch.send(embed=embed, components=components)
                    else:
                        await ch.send(
                            components=MensagensCanais.canal_criado_components(ch, auto=True),
                            flags=disnake.MessageFlags(is_components_v2=True),
                        )
                except Exception:
                    pass

        save_guild_channels(guild, defs)
        synced = self._sync_system_log_channels(guild.id, defs)

        if criados:
            await send_system_log(
                self.bot,
                guild,
                title="Canais automaticos criados",
                system="Configuracoes",
                description=(
                    f"Foram criados `{len(criados)}` canais automaticamente.\n"
                    f"Canais antigos apagados: `{len(apagados)}`\n"
                    f"Categorias antigas apagadas: `{len(categorias_apagadas)}`\n"
                    f"Configs de logs atualizadas: `{len(synced)}`\n"
                    + "\n".join(f"- {c.mention} (`{c.name}`)" for c in criados[:20])
                ),
                actor=inter.user,
            )

        if mode == "embed":
            embed, components = ConfigurarCanais.canais_embed(inter)
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            await inter.edit_original_message(components=ConfigurarCanais.canais_components(inter))

        if criados:
            if mode == "embed":
                embed, components = MensagensCanais.canais_criados_embed(criados)
                await inter.followup.send(embed=embed, components=components, ephemeral=True)
            else:
                await inter.followup.send(
                    components=MensagensCanais.canais_criados_components(criados),
                    flags=disnake.MessageFlags(is_components_v2=True),
                    ephemeral=True,
                )
