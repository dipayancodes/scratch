from __future__ import annotations

from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


ROOM_CATEGORY_ID = 1453297428181684309
REWARD_ROLE_IDS = {1453305075740053645, 1453304133506564278}


@dataclass(frozen=True, slots=True)
class ShopItem:
    key: str
    name: str
    price: int
    emoji: str
    description: str


SHOP_ITEMS: tuple[ShopItem, ...] = (
    ShopItem("focus_pass", "Focus Pass", 40, "🎟️", "A small flex item for students who keep showing up."),
    ShopItem("late_night_theme", "Late Night Theme", 55, "🌙", "Unlock a cozy profile theme for your study identity."),
    ShopItem("coffee_crate", "Coffee Crate", 65, "☕", "Stock up on virtual coffee for exam season energy."),
    ShopItem("lofi_pack", "Lo-Fi Pack", 75, "🎧", "A mood item for calm focus sessions and quiet flex."),
    ShopItem("brain_boost", "Brain Boost", 90, "🧠", "A collectible upgrade item for serious learners."),
    ShopItem("streak_shield", "Streak Shield", 110, "🛡️", "A premium collectible for consistency grinders."),
    ShopItem("note_skin", "Note Skin", 120, "📝", "A stylish note theme you can collect."),
    ShopItem("planner_skin", "Planner Skin", 125, "📅", "A premium planner cosmetic for organized students."),
    ShopItem("focus_badge", "Focus Badge", 140, "🏅", "A rare badge for students who finish what they start."),
    ShopItem("room_banner", "Room Banner", 160, "🚪", "A decorative item for your study room identity."),
    ShopItem("study_pet", "Study Pet", 180, "🐼", "A collectible companion for long study nights."),
    ShopItem("exam_luck_charm", "Exam Luck Charm", 195, "🍀", "A fun collectible for finals week."),
    ShopItem("silent_mode_pack", "Silent Mode Pack", 210, "🔕", "A premium focus collectible."),
    ShopItem("vip_study_role", "VIP Study Role", 260, "✨", "A prestige purchase for top performers."),
    ShopItem("mentor_badge", "Mentor Badge", 320, "🎓", "Show that you help others stay on track."),
    ShopItem("golden_planner", "Golden Planner", 380, "📔", "A high-tier collector item for disciplined users."),
    ShopItem("legendary_desk", "Legendary Desk", 450, "🪑", "A premium cosmetic for leaderboard regulars."),
)
SHOP_LOOKUP = {item.key: item for item in SHOP_ITEMS}


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


async def shop_item_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current_lower = current.lower().strip()
    choices = []
    for item in SHOP_ITEMS:
        haystack = f"{item.key} {item.name}".lower()
        if current_lower and current_lower not in haystack:
            continue
        label = f"{item.emoji} {item.name} - {item.price} coins"
        choices.append(app_commands.Choice(name=label[:100], value=item.key))
    return choices[:25]


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _ensure_reward_access(self, ctx: commands.Context) -> bool:
        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if member is not None and any(role.id in REWARD_ROLE_IDS for role in member.roles):
            return True
        await reply_embed(
            ctx,
            title="Permission Error",
            description="Only Staff or Administrator roles can send manual coin rewards.",
            color=WARNING,
        )
        return False

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
        await reply_embed(
            ctx,
            title="Room Commands",
            description="Use `/room create`, `/room join`, `/room leave`, `/room delete`, `/room lock`, or `/room unlock`.",
            color=INFO,
        )

    @room.command(name="create", description="Create your study room in the configured category.")
    @app_commands.describe(name="The name of the study room you want to create.")
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
        channel = await ctx.guild.create_voice_channel(name=name, category=category)
        room_id = self.bot.db.create_room(ctx.guild.id, name, channel.id, ctx.author.id)
        join_status = "Room created. Join it from the voice list."
        if ctx.author.voice and ctx.author.voice.channel:
            try:
                await ctx.author.move_to(channel)
                join_status = "Room created and you were moved in automatically."
            except discord.HTTPException:
                join_status = "Room created, but Discord did not allow an automatic move."
        await reply_embed(
            ctx,
            title="Study Room Created",
            description=join_status,
            color=SUCCESS,
            fields=[
                ("Room ID", str(room_id), True),
                ("Room", channel.mention, True),
                ("Category", category.name, True),
            ],
        )

    @room.command(name="join", description="Join one of your saved study rooms.")
    @app_commands.describe(name="Pick one of your saved study rooms.")
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
        await reply_embed(
            ctx,
            title="Room Ready",
            description=f"Your room **{channel.name}** is ready. Join it from the voice channel list.",
            color=INFO,
        )

    @room.command(name="leave", description="Leave your current voice study room.")
    async def room_leave(self, ctx: commands.Context) -> None:
        if not ctx.author.voice or not ctx.author.voice.channel:
            await reply_embed(ctx, title="Not in Voice", description="You are not currently in a voice channel.", color=WARNING)
            return
        await ctx.author.move_to(None)
        await reply_embed(ctx, title="Left Study Room", description="You disconnected from the current voice room.", color=SUCCESS)

    @room.command(name="delete", description="Delete one of your saved study rooms.")
    @app_commands.describe(name="Pick one of your saved study rooms to delete.")
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
    @app_commands.describe(name="Optional room name. Leave empty to lock the room you are currently in.")
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
    @app_commands.describe(name="Optional room name. Leave empty to unlock the room you are currently in.")
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

    @commands.hybrid_command(name="leaderboard", description="Show the study coin leaderboard.")
    async def leaderboard(self, ctx: commands.Context) -> None:
        rows = self.bot.db.coin_leaderboard(ctx.guild.id)
        if not rows:
            await reply_embed(ctx, title="Leaderboard Empty", description="No coin data exists yet.", color=INFO)
            return
        lines = []
        for index, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else str(row["user_id"])
            lines.append(f"{index}. {name} | `{row['coins']}` coins | `{row['total_focus_minutes']}` focus min")
        lines.append("")
        lines.append("Weekly leaderboard reward: top 10 students receive `100` study coins.")
        await reply_embed(ctx, title="Study Coin Leaderboard", description="\n".join(lines), color=INFO)

    @commands.hybrid_command(name="balance", description="Show your current study coin balance.")
    async def balance(self, ctx: commands.Context) -> None:
        stats = self.bot.db.get_user_stats(ctx.guild.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Study Coin Balance",
            description="Your current reward balance.",
            color=INFO,
            fields=[("Coins", f"`{stats['coins']}`", True)],
        )

    @commands.hybrid_command(name="reward", description="Reward a user with study coins.")
    @app_commands.describe(member="The user you want to reward.", coins="How many study coins to give.")
    async def reward(self, ctx: commands.Context, member: discord.Member, coins: int) -> None:
        if not await self._ensure_reward_access(ctx):
            return
        coins = max(1, min(coins, 1000))
        self.bot.db.add_coins(ctx.guild.id, member.id, coins)
        await reply_embed(ctx, title="Reward Sent", description=f"{member.mention} received `{coins}` study coins.", color=SUCCESS)

    @commands.hybrid_command(name="shop", description="Browse the reward shop or buy something fun.")
    @app_commands.describe(item="Choose an item to buy, or leave empty to browse the shop.")
    @app_commands.autocomplete(item=shop_item_autocomplete)
    async def shop(self, ctx: commands.Context, item: str = "") -> None:
        if not item:
            lines = [f"{entry.emoji} `{entry.key}` - `{entry.price}` coins | {entry.description}" for entry in SHOP_ITEMS]
            await reply_embed(
                ctx,
                title="Study Reward Shop",
                description="\n".join(lines),
                color=INFO,
                fields=[("Tip", "Use `/shop item:<name>` to buy and `/inventory` to view what you own.", False)],
            )
            return
        selected = SHOP_LOOKUP.get(item)
        if selected is None:
            await reply_embed(ctx, title="Item Not Found", description=f"`{item}` is not available in the shop.", color=ERROR)
            return
        if not self.bot.db.spend_coins(ctx.guild.id, ctx.author.id, selected.price):
            await reply_embed(
                ctx,
                title="Not Enough Coins",
                description=f"You need `{selected.price}` coins to buy `{selected.name}`.",
                color=WARNING,
            )
            return
        self.bot.db.add_inventory_item(ctx.guild.id, ctx.author.id, selected.key, f"{selected.emoji} {selected.name}")
        await reply_embed(
            ctx,
            title="Purchase Complete",
            description=f"You bought {selected.emoji} **{selected.name}** for `{selected.price}` coins.",
            color=SUCCESS,
        )

    @commands.hybrid_command(name="inventory", description="Show the items you bought from the study shop.")
    async def inventory(self, ctx: commands.Context) -> None:
        items = self.bot.db.get_inventory(ctx.guild.id, ctx.author.id)
        if not items:
            await reply_embed(ctx, title="Inventory Empty", description="Buy something from `/shop` first.", color=INFO)
            return
        lines = [f"{row['item_name']} x`{row['quantity']}`" for row in items[:20]]
        await reply_embed(ctx, title="Your Inventory", description="\n".join(lines), color=INFO)

    @commands.hybrid_command(name="analytics", description="Show your personal study analytics dashboard.")
    async def analytics(self, ctx: commands.Context) -> None:
        summary = self.bot.db.analytics_summary(ctx.guild.id, ctx.author.id)
        subjects_text = ", ".join(f"{row['subject']} ({row['hours']}h)" for row in summary["top_subjects"]) or "No weekly subject data"
        exams_text = ", ".join(f"{row['subject']} on {row['exam_date']}" for row in summary["upcoming_exams"]) or "No exams saved"
        await reply_embed(
            ctx,
            title="Personal Study Analytics",
            description="A quick snapshot of your productivity trends.",
            color=INFO,
            fields=[
                ("Total Hours", f"`{summary['total_logged_hours']}`", True),
                ("Today vs Goal", f"`{summary['today_hours']}` / `{summary['daily_goal_hours']}`", True),
                ("Streak", f"`{summary['streak']}` days", True),
                ("Focus Minutes", f"`{summary['focus_minutes']}`", True),
                ("Voice Minutes", f"`{summary['voice_minutes']}`", True),
                ("Pending Tasks", f"`{summary['pending_tasks']}`", True),
                ("Top Subjects", subjects_text, False),
                ("Upcoming Exams", exams_text, False),
            ],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Community(bot))
