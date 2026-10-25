from __future__ import annotations

import disnake
from disnake.ext import commands

from functions.emoji import emoji
from functions.system_logs import send_system_log
from .manager import (
    DEFAULT_CONFIG,
    TweetModal,
    CommentModal,
    TwitterButtonModal,
    TwitterPanelModal,
    _channel_id,
    _emoji,
    _id,
    _now,
    add_pending,
    add_post,
    admin_components,
    channel_select,
    config,
    comments_components,
    ensure_data,
    pop_pending,
    public_components,
    role_select,
    tweet_card,
    tweet_file,
    update_config,
)


class TwitterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ensure_data()

    def display_twitter_panel(self, inter):
        return admin_components(self.bot)

    def _channel(self, inter, key):
        channel_id = _channel_id(config().get(key))
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None and getattr(inter, "guild", None):
                channel = inter.guild.get_channel(int(channel_id))
            if channel:
                return channel
        return None

    def _is_staff(self, member) -> bool:
        cfg = config()
        role_id = _id(cfg.get("staff_role_id"))
        if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
            return True
        if not role_id:
            return False
        return any(str(getattr(role, "id", "")) == role_id for role in getattr(member, "roles", []))

    async def _log(self, inter, title, description):
        try:
            cfg = config()
            channel = self._channel(inter, "logs_channel_id")
            if channel:
                await channel.send(components=tweet_card(self.bot, {"text": f"**{title}**\n{description}", "author_id": getattr(inter.user, "id", "")}), flags=disnake.MessageFlags(is_components_v2=True))
            await send_system_log(self.bot, getattr(inter, "guild", None), title=title, system="Twitter", description=description, actor=getattr(inter, "user", None), config=cfg)
        except Exception:
            pass

    async def _send(self, inter, content=None, **kwargs):
        if inter.response.is_done():
            return await inter.followup.send(content, **kwargs)
        return await inter.response.send_message(content, **kwargs)

    async def _edit_admin(self, inter):
        if inter.response.is_done():
            await inter.edit_original_message(components=admin_components(self.bot), flags=disnake.MessageFlags(is_components_v2=True))
        else:
            await inter.response.edit_message(components=admin_components(self.bot), flags=disnake.MessageFlags(is_components_v2=True))

    async def submit_tweet(self, inter, text: str, image_url: str = ""):
        cfg = config()
        if not cfg.get("enabled"):
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} O sistema Twitter está desativado.", ephemeral=True)
        if not text:
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} O texto do tweet não pode ficar vazio.", ephemeral=True)
        tweet = {
            "author_id": str(inter.user.id),
            "author_name": str(getattr(inter.user, "global_name", None) or getattr(inter.user, "name", "Membro")),
            "author_handle": f"@{getattr(inter.user, 'name', 'membro')}",
            "avatar_url": str(getattr(getattr(inter.user, "display_avatar", None), "url", "") or ""),
            "text": text[:1800],
            "image_url": image_url[:500],
            "created_at": _now(),
            "likes": [],
            "comments": [],
        }
        if cfg.get("approval_enabled"):
            approval_channel = self._channel(inter, "approval_channel_id")
            if approval_channel is None:
                return await self._send(inter, f"{_emoji('wrong', 'wrong')} O canal de aprovação ainda não foi configurado.", ephemeral=True)
            tweet = add_pending(tweet)
            await approval_channel.send(components=tweet_card(self.bot, tweet, moderation=True), file=tweet_file(tweet), flags=disnake.MessageFlags(is_components_v2=True))
            await self._log(inter, "Tweet aguardando aprovação", f"{inter.user.mention} enviou um tweet para aprovação.")
            return await self._send(inter, f"{_emoji('correct', 'correct')} Tweet enviado para aprovação da equipe.", ephemeral=True)
        await self._publish_tweet(inter, tweet)

    async def _publish_tweet(self, inter, tweet):
        channel = self._channel(inter, "posts_channel_id")
        if channel is None:
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} O canal de posts ainda não foi configurado.", ephemeral=True)
        tweet = add_post(tweet)
        await channel.send(components=tweet_card(self.bot, tweet), file=tweet_file(tweet), flags=disnake.MessageFlags(is_components_v2=True))
        await self._log(inter, "Tweet publicado", f"{getattr(inter.user, 'mention', 'Membro')} publicou um tweet em {channel.mention}.")
        await self._send(inter, f"{_emoji('correct', 'correct')} Tweet publicado em {channel.mention}.", ephemeral=True)

    async def _approve(self, inter, tweet_id: str):
        if not self._is_staff(inter.user):
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Apenas o cargo Staff pode aprovar tweets.", ephemeral=True)
        tweet = pop_pending(tweet_id)
        if not tweet:
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Tweet pendente não encontrado.", ephemeral=True)
        await self._publish_tweet(inter, tweet)
        try:
            await inter.message.edit(components=tweet_card(self.bot, tweet), file=tweet_file(tweet), flags=disnake.MessageFlags(is_components_v2=True))
        except Exception:
            pass

    async def _reject(self, inter, tweet_id: str):
        if not self._is_staff(inter.user):
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Apenas o cargo Staff pode rejeitar tweets.", ephemeral=True)
        tweet = pop_pending(tweet_id)
        if not tweet:
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Tweet pendente não encontrado.", ephemeral=True)
        await self._log(inter, "Tweet rejeitado", f"Tweet `{tweet_id}` rejeitado por {inter.user.mention}.")
        try:
            await inter.message.edit(components=[disnake.ui.Container(disnake.ui.TextDisplay(f"{_emoji('wrong', 'wrong')} Tweet rejeitado pela equipe."))], flags=disnake.MessageFlags(is_components_v2=True))
        except Exception:
            pass
        await self._send(inter, f"{_emoji('correct', 'correct')} Tweet rejeitado.", ephemeral=True)

    async def add_comment(self, inter, tweet_id: str, comment: str, source_message=None):
        data = ensure_data()
        for tweet in data["config"].get("posts", []):
            if str(tweet.get("id")) == str(tweet_id):
                tweet.setdefault("comments", []).append({"author_id": str(inter.user.id), "text": comment[:500], "created_at": _now()})
                from functions.database import database as db
                db.salvar("database/twitter_system.json", data)
                if source_message is not None:
                    try:
                        await source_message.edit(components=tweet_card(self.bot, tweet), file=tweet_file(tweet), flags=disnake.MessageFlags(is_components_v2=True))
                    except Exception:
                        pass
                await self._send(inter, f"{_emoji('correct', 'correct')} Comentário enviado.", ephemeral=True)
                return
        await self._send(inter, f"{_emoji('wrong', 'wrong')} Tweet não encontrado.", ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def on_button(self, inter: disnake.MessageInteraction):
        cid = str(getattr(inter.component, "custom_id", "") or "")
        if not cid.startswith("Twitter_"):
            return
        if cid == "Twitter_Toggle":
            update_config({"enabled": not bool(config().get("enabled"))})
            return await self._edit_admin(inter)
        if cid == "Twitter_Approval":
            update_config({"approval_enabled": not bool(config().get("approval_enabled"))})
            return await self._edit_admin(inter)
        if cid == "Twitter_EditPanel":
            return await inter.response.send_modal(TwitterPanelModal(self))
        if cid == "Twitter_EditButton":
            return await inter.response.send_modal(TwitterButtonModal(self))
        if cid == "Twitter_Thumbnail":
            update_config({"thumbnail_enabled": not bool(config().get("thumbnail_enabled"))})
            return await self._edit_admin(inter)
        if cid in {"Twitter_SendChannel", "Twitter_ApprovalChannel", "Twitter_PostsChannel", "Twitter_LogsChannel"}:
            key_map = {"Twitter_SendChannel": ("send_channel_id", "Selecionar canal de envio"), "Twitter_ApprovalChannel": ("approval_channel_id", "Selecionar canal de aprovação"), "Twitter_PostsChannel": ("posts_channel_id", "Selecionar canal de posts"), "Twitter_LogsChannel": ("logs_channel_id", "Selecionar canal de logs")}
            key, placeholder = key_map[cid]
            update_config({"_selecting": key})
            return await inter.response.send_message(components=channel_select(f"Twitter_SelectChannel:{key}", placeholder, [disnake.ChannelType.text]), ephemeral=True)
        if cid == "Twitter_StaffRole":
            return await inter.response.send_message(components=role_select(), ephemeral=True)
        if cid == "Twitter_PublishPanel":
            channel = self._channel(inter, "posts_channel_id") or self._channel(inter, "send_channel_id")
            if not channel:
                return await self._send(inter, f"{_emoji('wrong', 'wrong')} Configure primeiro o canal de posts.", ephemeral=True)
            await channel.send(components=public_components(self.bot), flags=disnake.MessageFlags(is_components_v2=True))
            await self._log(inter, "Painel Twitter publicado", f"Painel publicado em {channel.mention}.")
            return await self._send(inter, f"{_emoji('correct', 'correct')} Painel Twitter enviado em {channel.mention}.", ephemeral=True)
        if cid == "Twitter_Refresh":
            return await self._edit_admin(inter)
        if cid == "Twitter_Submit":
            return await inter.response.send_modal(TweetModal(self))
        if cid.startswith("Twitter_Approve:"):
            return await self._approve(inter, cid.split(":", 1)[1])
        if cid.startswith("Twitter_Reject:"):
            return await self._reject(inter, cid.split(":", 1)[1])
        if cid.startswith("Twitter_Like:"):
            tweet_id = cid.split(":", 1)[1]
            data = ensure_data()
            for tweet in data["config"].get("posts", []):
                if str(tweet.get("id")) == tweet_id:
                    likes = tweet.setdefault("likes", [])
                    user_id = str(inter.user.id)
                    if user_id in likes:
                        likes.remove(user_id)
                    else:
                        likes.append(user_id)
                    from functions.database import database as db
                    db.salvar("database/twitter_system.json", data)
                    return await inter.response.edit_message(components=tweet_card(self.bot, tweet), file=tweet_file(tweet), flags=disnake.MessageFlags(is_components_v2=True))
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Tweet não encontrado.", ephemeral=True)
        if cid.startswith("Twitter_Repost:"):
            tweet_id = cid.split(":", 1)[1]
            data = ensure_data()
            for tweet in data["config"].get("posts", []):
                if str(tweet.get("id")) == tweet_id:
                    channel = self._channel(inter, "posts_channel_id")
                    if channel is None:
                        return await self._send(inter, f"{_emoji('wrong', 'wrong')} O canal de posts não está configurado.", ephemeral=True)
                    repost = dict(tweet)
                    repost["author_id"] = str(inter.user.id)
                    repost["author_name"] = str(getattr(inter.user, "global_name", None) or getattr(inter.user, "name", "Membro"))
                    repost["author_handle"] = f"@{getattr(inter.user, 'name', 'membro')}"
                    repost["avatar_url"] = str(getattr(getattr(inter.user, "display_avatar", None), "url", "") or "")
                    repost["likes"] = []
                    repost["comments"] = []
                    repost = add_post(repost)
                    await channel.send(components=tweet_card(self.bot, repost), file=tweet_file(repost), flags=disnake.MessageFlags(is_components_v2=True))
                    return await self._send(inter, f"{_emoji('correct', 'correct')} Tweet repostado em {channel.mention}.", ephemeral=True)
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Tweet não encontrado.", ephemeral=True)
        if cid.startswith("Twitter_Comment:"):
            return await inter.response.send_modal(CommentModal(self, cid.split(":", 1)[1], getattr(inter, "message", None)))
        if cid.startswith("Twitter_Comments:"):
            tweet_id = cid.split(":", 1)[1]
            data = ensure_data()
            for tweet in data["config"].get("posts", []):
                if str(tweet.get("id")) == tweet_id:
                    return await self._send(
                        inter,
                        components=comments_components(self.bot, tweet, self._is_staff(inter.user)),
                        flags=disnake.MessageFlags(is_components_v2=True),
                        ephemeral=True,
                    )
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Tweet não encontrado.", ephemeral=True)
        if cid.startswith("Twitter_DeleteComment:"):
            parts = cid.split(":")
            if len(parts) != 3 or not self._is_staff(inter.user):
                return await self._send(inter, f"{_emoji('wrong', 'wrong')} Apenas ADM/Staff pode excluir comentários.", ephemeral=True)
            tweet_id, index_text = parts[1], parts[2]
            try:
                comment_index = int(index_text)
            except ValueError:
                return await self._send(inter, f"{_emoji('wrong', 'wrong')} Comentário inválido.", ephemeral=True)
            data = ensure_data()
            for tweet in data["config"].get("posts", []):
                if str(tweet.get("id")) == tweet_id:
                    comments = tweet.get("comments") if isinstance(tweet.get("comments"), list) else []
                    if comment_index < 0 or comment_index >= len(comments):
                        return await self._send(inter, f"{_emoji('wrong', 'wrong')} Comentário não encontrado.", ephemeral=True)
                    removed = comments.pop(comment_index)
                    from functions.database import database as db
                    db.salvar("database/twitter_system.json", data)
                    await self._log(inter, "Comentário excluído", f"Comentário de `{removed.get('author_id', 'Membro')}` excluído no tweet `{tweet_id}`.")
                    try:
                        await inter.response.edit_message(components=comments_components(self.bot, tweet, True), flags=disnake.MessageFlags(is_components_v2=True))
                    except Exception:
                        await self._send(inter, f"{_emoji('correct', 'correct')} Comentário excluído.", ephemeral=True)
                    return
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Tweet não encontrado.", ephemeral=True)
        if cid.startswith("Twitter_Delete:"):
            tweet_id = cid.split(":", 1)[1]
            data = ensure_data()
            for tweet in list(data["config"].get("posts", [])):
                if str(tweet.get("id")) == tweet_id:
                    is_author = str(tweet.get("author_id")) == str(inter.user.id)
                    if not is_author and not self._is_staff(inter.user):
                        return await self._send(inter, f"{_emoji('wrong', 'wrong')} Apenas o autor ou Staff pode apagar.", ephemeral=True)
                    data["config"]["posts"].remove(tweet)
                    from functions.database import database as db
                    db.salvar("database/twitter_system.json", data)
                    try:
                        await inter.message.delete()
                    except Exception:
                        pass
                    return await self._send(inter, f"{_emoji('correct', 'correct')} Tweet apagado.", ephemeral=True)
            return await self._send(inter, f"{_emoji('wrong', 'wrong')} Tweet não encontrado.", ephemeral=True)

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction):
        cid = str(getattr(inter.component, "custom_id", "") or "")
        if cid.startswith("Twitter_SelectChannel:"):
            key = cid.split(":", 1)[1]
            selected = inter.values[0] if inter.values else None
            update_config({key: str(getattr(selected, "id", selected))})
            return await self._send(inter, f"{_emoji('correct', 'correct')} Canal configurado.", ephemeral=True)
        if cid == "Twitter_StaffRoleSelect":
            selected = inter.values[0] if inter.values else None
            update_config({"staff_role_id": str(getattr(selected, "id", selected))})
            return await self._send(inter, f"{_emoji('correct', 'correct')} Cargo Staff configurado.", ephemeral=True)

    @commands.Cog.listener("on_message")
    async def on_send_channel_message(self, message: disnake.Message):
        if getattr(message.author, "bot", False) or not getattr(message, "guild", None):
            return
        cfg = config()
        if not cfg.get("enabled") or not _id(cfg.get("send_channel_id")) or str(message.channel.id) != _id(cfg.get("send_channel_id")):
            return
        text = str(message.content or "").strip()
        attachments = list(getattr(message, "attachments", []) or [])
        if not text and not attachments:
            return
        image_url = ""
        if attachments:
            image_url = str(getattr(attachments[0], "url", "") or "")
        tweet = {"author_id": str(message.author.id), "author_name": str(getattr(message.author, "display_name", message.author.name)), "avatar_url": str(getattr(getattr(message.author, "display_avatar", None), "url", "") or ""), "text": text[:1800], "image_url": image_url[:500], "created_at": _now(), "likes": [], "comments": []}
        if cfg.get("approval_enabled"):
            approval = self._channel(message, "approval_channel_id")
            if approval:
                tweet = add_pending(tweet)
                await approval.send(components=tweet_card(self.bot, tweet, moderation=True), file=tweet_file(tweet), flags=disnake.MessageFlags(is_components_v2=True))
        else:
            posts = self._channel(message, "posts_channel_id")
            if posts:
                tweet = add_post(tweet)
                await posts.send(components=tweet_card(self.bot, tweet), file=tweet_file(tweet), flags=disnake.MessageFlags(is_components_v2=True))
        try:
            await message.delete()
        except Exception:
            pass


def setup(bot: commands.Bot):
    bot.add_cog(TwitterCog(bot))
