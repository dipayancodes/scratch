from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


ROOM_CATEGORY_ID = 1453297428181684309


async def room_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    db = getattr(interaction.client, "db", None)
    if db is None:
        return []
    current_lower = current.lower().strip()
    rooms = db.list_rooms_for_user(interaction.guild_id or 0, interaction.user.id)
    choices = []
    for room in rooms:
        name = room["name"]
        if current_lower and current_lower not in name.lower():
            continue
        choices.append(app_commands.Choice(name=name[:100], value=name))
    return choices[:25]


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    def _display_room_name(owner: discord.abc.User, base_name: str) -> str:
        clean_owner = owner.display_name.strip() or owner.name
        clean_base = base_name.strip()
        full_name = f"{clean_owner} • {clean_base}"
        return full_name[:100]

    def _room_from_current_channel(self, ctx: commands.Context) -> dict | None:
        if not ctx.author.voice or not ctx.author.voice.channel:
            return None
        current_channel_id = ctx.author.voice.channel.id
        for room in self.bot.db.list_rooms_for_user(ctx.guild.id, ctx.author.id):
            if room["channel_id"] == current_channel_id:
                return room
        return None

    async def _get_room_channel(self, ctx: commands.Context, name: str) -> tuple[dict | None, discord.VoiceChannel | None]:
        room = self.bot.db.get_room_by_name(ctx.guild.id, ctx.author.id, name)
        if room is None:
            return None, None
        channel = ctx.guild.get_channel(room["channel_id"])
        return room, channel if isinstance(channel, discord.VoiceChannel) else None

    @commands.hybrid_group(name="room", description="Create and manage private study voice rooms.", invoke_without_command=True)
    async def room(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Room Commands", description="Use `/room create`, `/room join`, `/room leave`, `/room delete`, `/room lock`, or `/room unlock`.", color=INFO)

    @room.command(name="create", description="Create your study room in the configured category.")
    async def room_create(self, ctx: commands.Context, *, name: str) -> None:
        category = ctx.guild.get_channel(ROOM_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await reply_embed(ctx, title="Room Category Missing", description="The configured study room category could not be found.", color=ERROR)
            return
        existing_room, existing_channel = await self._get_room_channel(ctx, name)
        if existing_room and existing_channel:
            await reply_embed(ctx, title="Room Already Exists", description=f"You already have an active room named `{name}`.", color=WARNING)
            return
        if existing_room and existing_channel is None:
            self.bot.db.deactivate_room(existing_room["channel_id"])
        channel = await ctx.guild.create_voice_channel(name=self._display_room_name(ctx.author, name), category=category)
        room_id = self.bot.db.create_room(ctx.guild.id, name, channel.id, ctx.author.id)
        join_status = "Room created. Join it from the voice list."
        if ctx.author.voice and ctx.author.voice.channel:
            try:
                await ctx.author.move_to(channel)
                join_status = "Room created and you were moved in automatically."
            except discord.HTTPException:
                join_status = "Room created, but Discord did not allow an automatic move."
        await reply_embed(ctx, title="Study Room Created", description=join_status, color=SUCCESS, fields=[("Room ID", str(room_id), True), ("Room", channel.mention, True), ("Category", category.name, True)])

    @room.command(name="join", description="Join one of your saved study rooms.")
    @app_commands.autocomplete(name=room_name_autocomplete)
    async def room_join(self, ctx: commands.Context, name: str) -> None:
        room, channel = await self._get_room_channel(ctx, name)
        if room is None:
            await reply_embed(ctx, title="Room Not Found", description=f"No active saved room exists for `{name}`.", color=ERROR)
            return
        if channel is None:
            self.bot.db.deactivate_room(room["channel_id"])
            await reply_embed(ctx, title="Room Missing", description="That saved room channel no longer exists.", color=ERROR)
            return
        if ctx.author.voice:
            try:
                await ctx.author.move_to(channel)
                await reply_embed(ctx, title="Joined Study Room", description=f"You were moved to **{channel.name}**.", color=SUCCESS)
                return
            except discord.HTTPException:
                pass
        await reply_embed(ctx, title="Room Ready", description=f"Your room **{channel.name}** is ready. Join it from the voice channel list.", color=INFO)

    @room.command(name="leave", description="Leave your current voice study room.")
    async def room_leave(self, ctx: commands.Context) -> None:
        if not ctx.author.voice or not ctx.author.voice.channel:
            await reply_embed(ctx, title="Not in Voice", description="You are not currently in a voice channel.", color=WARNING)
            return
        await ctx.author.move_to(None)
        await reply_embed(ctx, title="Left Study Room", description="You disconnected from the current voice room.", color=SUCCESS)

    @room.command(name="delete", description="Delete one of your saved study rooms.")
    @app_commands.autocomplete(name=room_name_autocomplete)
    async def room_delete(self, ctx: commands.Context, name: str) -> None:
        room, channel = await self._get_room_channel(ctx, name)
        deleted = self.bot.db.delete_room(ctx.guild.id, ctx.author.id, name)
        if deleted is None:
            await reply_embed(ctx, title="Room Not Found", description=f"No saved room exists for `{name}`.", color=ERROR)
            return
        if channel is not None:
            try:
                await channel.delete(reason=f"Deleted by {ctx.author}")
            except discord.HTTPException:
                pass
        await reply_embed(ctx, title="Study Room Deleted", description=f"Removed your room `{name}`.", color=SUCCESS)

    @room.command(name="lock", description="Lock one of your study rooms.")
    @app_commands.autocomplete(name=room_name_autocomplete)
    async def room_lock(self, ctx: commands.Context, name: str = "") -> None:
        room = self._room_from_current_channel(ctx) if not name else self.bot.db.get_room_by_name(ctx.guild.id, ctx.author.id, name)
        if room is None:
            await reply_embed(ctx, title="Room Not Found", description="Pick one of your rooms or join your room first.", color=ERROR)
            return
        channel = ctx.guild.get_channel(room["channel_id"])
        if not isinstance(channel, discord.VoiceChannel):
            self.bot.db.deactivate_room(room["channel_id"])
            await reply_embed(ctx, title="Room Missing", description="That saved room no longer exists.", color=ERROR)
            return
        await channel.set_permissions(ctx.guild.default_role, connect=False)
        self.bot.db.set_room_lock(ctx.guild.id, ctx.author.id, room["name"], True)
        await reply_embed(ctx, title="Room Locked", description=f"`{room['name']}` is now locked.", color=SUCCESS)

    @room.command(name="unlock", description="Unlock one of your study rooms.")
    @app_commands.autocomplete(name=room_name_autocomplete)
    async def room_unlock(self, ctx: commands.Context, name: str = "") -> None:
        room = self._room_from_current_channel(ctx) if not name else self.bot.db.get_room_by_name(ctx.guild.id, ctx.author.id, name)
        if room is None:
            await reply_embed(ctx, title="Room Not Found", description="Pick one of your rooms or join your room first.", color=ERROR)
            return
        channel = ctx.guild.get_channel(room["channel_id"])
        if not isinstance(channel, discord.VoiceChannel):
            self.bot.db.deactivate_room(room["channel_id"])
            await reply_embed(ctx, title="Room Missing", description="That saved room no longer exists.", color=ERROR)
            return
        await channel.set_permissions(ctx.guild.default_role, connect=None)
        self.bot.db.set_room_lock(ctx.guild.id, ctx.author.id, room["name"], False)
        await reply_embed(ctx, title="Room Unlocked", description=f"`{room['name']}` is open again.", color=SUCCESS)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Community(bot))
