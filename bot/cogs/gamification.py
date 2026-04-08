from __future__ import annotations

from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


REWARD_ROLE_IDS = {1453305075740053645, 1453304133506564278}


@dataclass(frozen=True, slots=True)
class ShopItem:
    key: str
    name: str
    price: int
    emoji: str
    description: str


SHOP_ITEMS: tuple[ShopItem, ...] = (
    ShopItem("focus_pass", "Focus Pass", 250, "🎟️", "A small flex item for students who keep showing up."),
    ShopItem("late_night_theme", "Late Night Theme", 340, "🌙", "Unlock a cozy profile theme for your study identity."),
    ShopItem("coffee_crate", "Coffee Crate", 430, "☕", "Stock up on virtual coffee for exam season energy."),
    ShopItem("lofi_pack", "Lo-Fi Pack", 520, "🎧", "A mood item for calm focus sessions and quiet flex."),
    ShopItem("brain_boost", "Brain Boost", 650, "🧠", "A collectible upgrade item for serious learners."),
    ShopItem("streak_shield", "Streak Shield", 850, "🛡️", "Adds one streak protection charge when bought."),
    ShopItem("note_skin", "Note Skin", 980, "📝", "A stylish note theme you can collect."),
    ShopItem("planner_skin", "Planner Skin", 1120, "📅", "A premium planner cosmetic for organized students."),
    ShopItem("focus_badge", "Focus Badge", 1350, "🏅", "A rare badge for students who finish what they start."),
    ShopItem("room_banner", "Room Banner", 1600, "🚪", "A decorative item for your study room identity."),
    ShopItem("study_pet", "Study Pet", 1900, "🐼", "A collectible companion for long study nights."),
    ShopItem("exam_luck_charm", "Exam Luck Charm", 2250, "🍀", "A fun collectible for finals week."),
    ShopItem("silent_mode_pack", "Silent Mode Pack", 2600, "🔕", "A premium focus collectible."),
    ShopItem("vip_study_role", "VIP Study Role", 3200, "✨", "A prestige purchase for top performers."),
    ShopItem("mentor_badge", "Mentor Badge", 3900, "🎓", "Show that you help others stay on track."),
    ShopItem("golden_planner", "Golden Planner", 4700, "📔", "A high-tier collector item for disciplined users."),
    ShopItem("legendary_desk", "Legendary Desk", 5600, "🪑", "A premium cosmetic for leaderboard regulars."),
)
SHOP_LOOKUP = {item.key: item for item in SHOP_ITEMS}


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


class Gamification(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _ensure_reward_access(self, ctx: commands.Context) -> bool:
        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if member is not None and any(role.id in REWARD_ROLE_IDS for role in member.roles):
            return True
        await reply_embed(ctx, title="Permission Error", description="Only Staff or Administrator roles can send manual coin rewards.", color=WARNING)
        return False

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
            lines.append(f"{index}. {name} | `{row['coins']}` coins | `Lv {row.get('level', 1)}`")
        lines.append("")
        lines.append("Weekly leaderboard reward: top 10 students receive `100` study coins.")
        await reply_embed(ctx, title="Study Coin Leaderboard", description="\n".join(lines), color=INFO)

    @commands.hybrid_command(name="balance", description="Show your current study coin balance.")
    async def balance(self, ctx: commands.Context) -> None:
        stats = self.bot.db.get_user_stats(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Study Coin Balance", description="Your current reward balance.", color=INFO, fields=[("Coins", f"`{stats['coins']}`", True)])

    @commands.hybrid_command(name="reward", description="Reward a user with study coins.")
    @app_commands.describe(member="The user you want to reward.", coins="How many study coins to give.")
    async def reward(self, ctx: commands.Context, member: discord.Member, coins: int) -> None:
        if not await self._ensure_reward_access(ctx):
            return
        coins = max(1, min(coins, 1000))
        self.bot.db.add_coins(ctx.guild.id, member.id, coins)
        self.bot.db.add_xp(ctx.guild.id, member.id, max(1, coins // 5))
        await reply_embed(ctx, title="Reward Sent", description=f"{member.mention} received `{coins}` study coins.", color=SUCCESS)

    @commands.hybrid_command(name="shop", description="Browse the reward shop or buy something fun.")
    @app_commands.describe(item="Choose an item to buy, or leave empty to browse the shop.")
    @app_commands.autocomplete(item=shop_item_autocomplete)
    async def shop(self, ctx: commands.Context, item: str = "") -> None:
        if not item:
            lines = [f"{entry.emoji} `{entry.key}` - `{entry.price}` coins | {entry.description}" for entry in SHOP_ITEMS]
            await reply_embed(ctx, title="Study Reward Shop", description="\n".join(lines), color=INFO)
            return
        selected = SHOP_LOOKUP.get(item)
        if selected is None:
            await reply_embed(ctx, title="Item Not Found", description=f"`{item}` is not available in the shop.", color=ERROR)
            return
        if not self.bot.db.spend_coins(ctx.guild.id, ctx.author.id, selected.price):
            await reply_embed(ctx, title="Not Enough Coins", description=f"You need `{selected.price}` coins to buy `{selected.name}`.", color=WARNING)
            return
        self.bot.db.add_inventory_item(ctx.guild.id, ctx.author.id, selected.key, f"{selected.emoji} {selected.name}")
        if selected.key == "streak_shield":
            self.bot.db.grant_streak_protect(ctx.guild.id, ctx.author.id, 1)
        self.bot.db.add_xp(ctx.guild.id, ctx.author.id, max(5, selected.price // 10))
        await reply_embed(ctx, title="Purchase Complete", description=f"You bought {selected.emoji} **{selected.name}** for `{selected.price}` coins.", color=SUCCESS)

    @commands.hybrid_command(name="inventory", description="Show the items you bought from the study shop.")
    async def inventory(self, ctx: commands.Context) -> None:
        items = self.bot.db.get_inventory(ctx.guild.id, ctx.author.id)
        if not items:
            await reply_embed(ctx, title="Inventory Empty", description="Buy something from `/shop` first.", color=INFO)
            return
        lines = [f"{row['item_name']} x`{row['quantity']}`" for row in items[:20]]
        await reply_embed(ctx, title="Your Inventory", description="\n".join(lines), color=INFO)

    @commands.hybrid_command(name="achievements", description="Show your unlocked study achievements.")
    async def achievements(self, ctx: commands.Context) -> None:
        self.bot.db.sync_achievements(ctx.guild.id, ctx.author.id)
        achievements = self.bot.db.list_achievements(ctx.guild.id, ctx.author.id)
        if not achievements:
            await reply_embed(ctx, title="No Achievements Yet", description="Use the bot more consistently to unlock achievements.", color=INFO)
            return
        lines = [f"🏅 **{row['name']}** - {row['description']}" for row in achievements[:15]]
        await reply_embed(ctx, title="Achievements", description="\n".join(lines), color=INFO)

    @commands.hybrid_command(name="xp", description="Show your current XP progress.")
    async def xp(self, ctx: commands.Context) -> None:
        stats = self.bot.db.get_user_stats(ctx.guild.id, ctx.author.id)
        current_xp = int(stats.get("xp", 0))
        level = int(stats.get("level", 1))
        next_level_at = level * 100
        await reply_embed(
            ctx,
            title="XP Progress",
            description="Your current progression.",
            color=INFO,
            fields=[("XP", f"`{current_xp}`", True), ("Level", f"`{level}`", True), ("Next Level At", f"`{next_level_at}`", True)],
        )

    @commands.hybrid_command(name="level", description="Show your current study level.")
    async def level(self, ctx: commands.Context) -> None:
        stats = self.bot.db.get_user_stats(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Study Level", description="Your current study level.", color=INFO, fields=[("Level", f"`{stats.get('level', 1)}`", True), ("Coins", f"`{stats.get('coins', 0)}`", True)])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Gamification(bot))
