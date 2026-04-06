from __future__ import annotations

from discord import app_commands
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, reply_embed


class Task(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="task", description="Manage your study tasks.", invoke_without_command=True)
    async def task(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Task Commands", description="Use `/task add`, `/task list`, `/task done`, `/task delete`, or `/task clear`.", color=INFO)

    @task.command(name="add", description="Add a new study task.")
    @app_commands.describe(task="The task you want to add.")
    async def task_add(self, ctx: commands.Context, *, task: str) -> None:
        task_id = self.bot.db.add_task(ctx.guild.id, ctx.author.id, task)
        self.bot.db.add_xp(ctx.guild.id, ctx.author.id, 5)
        self.bot.db.sync_achievements(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Task Added", description="Your study task has been saved.", color=SUCCESS, fields=[("Task ID", str(task_id), True), ("Task", task, False)])

    @task.command(name="list", description="Show all your pending study tasks.")
    async def task_list(self, ctx: commands.Context) -> None:
        tasks = self.bot.db.list_tasks(ctx.guild.id, ctx.author.id)
        if not tasks:
            await reply_embed(ctx, title="No Pending Tasks", description="You have no pending tasks right now.", color=INFO)
            return
        value = "\n".join(f"`{row['id']}` {row['content']}" for row in tasks[:20])
        await reply_embed(ctx, title="Pending Tasks", description=value, color=INFO)

    @task.command(name="done", description="Mark one of your tasks as completed.")
    @app_commands.describe(task_id="The task ID you want to mark as done.")
    async def task_done(self, ctx: commands.Context, task_id: int) -> None:
        if not self.bot.db.complete_task(ctx.guild.id, ctx.author.id, task_id):
            await reply_embed(ctx, title="Task Not Found", description=f"No pending task exists with ID `{task_id}`.", color=ERROR)
            return
        xp = self.bot.db.add_xp(ctx.guild.id, ctx.author.id, 15)
        self.bot.db.add_coins(ctx.guild.id, ctx.author.id, 10)
        self.bot.db.sync_achievements(ctx.guild.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Task Completed",
            description=f"Task `{task_id}` marked complete.",
            color=SUCCESS,
            fields=[("Reward", "`10 study coins`", True), ("Level", f"`{xp['level']}`", True)],
        )

    @task.command(name="delete", description="Delete one of your saved tasks.")
    @app_commands.describe(task_id="The task ID you want to delete.")
    async def task_delete(self, ctx: commands.Context, task_id: int) -> None:
        if not self.bot.db.delete_task(ctx.guild.id, ctx.author.id, task_id):
            await reply_embed(ctx, title="Task Not Found", description=f"No task exists with ID `{task_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Task Deleted", description=f"Task `{task_id}` has been removed.", color=SUCCESS)

    @task.command(name="clear", description="Clear all tasks or just one task by ID.")
    @app_commands.describe(task_id="Optional task ID. Leave empty to clear all your tasks.")
    async def task_clear(self, ctx: commands.Context, task_id: int | None = None) -> None:
        if task_id is not None:
            if not self.bot.db.delete_task(ctx.guild.id, ctx.author.id, task_id):
                await reply_embed(ctx, title="Task Not Found", description=f"No task exists with ID `{task_id}`.", color=ERROR)
                return
            await reply_embed(ctx, title="Task Cleared", description=f"Removed task `{task_id}`.", color=SUCCESS)
            return
        count = self.bot.db.clear_tasks(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Tasks Cleared", description=f"Removed `{count}` tasks from your list.", color=SUCCESS)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Task(bot))
