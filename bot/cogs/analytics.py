from __future__ import annotations

import discord
from discord.ext import commands
import logging

from bot.cog_helpers import progress_bar
from bot.dashboard_card import render_dashboard_card
from bot.ui import INFO, reply_embed


log = logging.getLogger(__name__)


class Analytics(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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
                ("Study Hours", f"`{summary['study_hours']}`", True),
                ("Today vs Goal", f"`{summary['today_hours']}` / `{summary['daily_goal_hours']}`", True),
                ("Streak", f"`{summary['streak']}` days", True),
                ("Focus Minutes", f"`{summary['focus_minutes']}`", True),
                ("Voice Minutes", f"`{summary['voice_minutes']}`", True),
                ("Level", f"`{summary['level']}`", True),
                ("Top Subjects", subjects_text, False),
                ("Upcoming Exams", exams_text, False),
            ],
        )

    @commands.hybrid_command(name="dashboard", description="Show a combined study dashboard with tasks, goals, and streaks.")
    async def dashboard(self, ctx: commands.Context) -> None:
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        data = self.bot.db.get_dashboard_data(ctx.guild.id, ctx.author.id)
        summary = data["summary"]
        try:
            image_bytes = await render_dashboard_card(
                member=ctx.author,
                summary=summary,
                tasks=data["tasks"],
                plans=data["plans"],
                exams=data["exams"],
                inventory=data.get("inventory", []),
            )
            file = discord.File(image_bytes, filename="study-dashboard.png")
            embed = discord.Embed(
                title="Study Dashboard",
                description="Your visual study profile is ready.",
                color=INFO,
            )
            embed.set_image(url="attachment://study-dashboard.png")
            await ctx.send(
                content=ctx.author.mention,
                embed=embed,
                file=file,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            return
        except Exception as exc:
            log.exception("Dashboard image generation failed for guild=%s user=%s", ctx.guild.id if ctx.guild else "unknown", ctx.author.id if ctx.author else "unknown")
            tasks = "\n".join(f"`{row['id']}` {row['content']}" for row in data["tasks"]) or "No pending tasks"
            exams = "\n".join(f"`{row['id']}` {row['subject']} - {row['exam_date']}" for row in data["exams"]) or "No exams saved"
            plans = "\n".join(f"{row['day'].title()} - {row['target_date']}" for row in data["plans"]) or "No saved plans"
            inventory = "\n".join(f"{row['item_name']} x`{row['quantity']}`" for row in data.get("inventory", [])) or "No shop items bought yet"
            goal_bar = progress_bar(summary["today_hours"], summary["daily_goal_hours"])
            await reply_embed(
                ctx,
                title="Study Dashboard",
                description="Dashboard image failed, so I sent the text fallback instead.",
                color=INFO,
                fields=[
                    ("Streak", f"`{summary['streak']}` days", True),
                    ("Coins", f"`{summary['coins']}`", True),
                    ("Level", f"`{summary['level']}`", True),
                    ("Goal", f"`{goal_bar}`", False),
                    ("Tasks", tasks, False),
                    ("Plans", plans, False),
                    ("Exams", exams, False),
                    ("Loadout", inventory, False),
                    ("Error", f"`{exc.__class__.__name__}`", True),
                ],
            )

    @commands.hybrid_group(name="vc", description="Review voice study tracking.", invoke_without_command=True)
    async def vc(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Voice Tracking", description="Use `/vc stats` to see your voice study tracking.", color=INFO)

    @vc.command(name="stats", description="Show your automatic study voice stats.")
    async def vc_stats(self, ctx: commands.Context) -> None:
        stats = self.bot.db.get_voice_stats(ctx.guild.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Voice Study Stats",
            description="Automatic tracking for your study voice sessions.",
            color=INFO,
            fields=[
                ("Total Voice Minutes", f"`{stats['total_voice_minutes']}`", True),
                ("Current Session", f"`{stats['current_session_minutes']}` min", True),
                ("Focus Minutes", f"`{stats['total_focus_minutes']}`", True),
            ],
        )

    @commands.hybrid_command(name="graph", description="Show your study trend graph for the last 7 days.")
    async def graph(self, ctx: commands.Context) -> None:
        points = self.bot.db.get_daily_graph(ctx.guild.id, ctx.author.id, days=7)
        max_hours = max((row["hours"] for row in points), default=1.0)
        lines = []
        for row in points:
            bar = progress_bar(row["hours"], max_hours or 1, length=12)
            lines.append(f"{row['day'][5:]} | `{bar}` | `{row['hours']}h`")
        await reply_embed(ctx, title="Study Trend Graph", description="\n".join(lines) or "No study graph data yet.", color=INFO)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Analytics(bot))
