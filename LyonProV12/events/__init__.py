from disnake.ext import commands


EVENT_EXTENSIONS = (
    "events.interaction_monitor",
    "events.on_member_ban",
    "events.on_member_join",
    "events.on_member_remove",
    "events.on_member_update_roles",
    "events.on_member_update_permissions",
    "events.on_member_update_timeout",
    "events.on_guild_channel_create",
    "events.on_guild_channel_delete",
    "events.on_guild_channel_update",
    "events.on_guild_role_create",
    "events.on_guild_role_delete",
    "events.on_message_delete",
    "events.on_message_edit",
    "events.on_voice_state_update",
    "events.on_command",
    "events.on_ready",
)


def setup(bot: commands.Bot):
    for extension in EVENT_EXTENSIONS:
        bot.load_extension(extension)

    # websocket_ready foi integrado no on_ready para evitar multiplas conexoes.
    # bot.load_extension("events.websocket_ready")
    # bot.load_extension("events.boost_websocket_ready")
