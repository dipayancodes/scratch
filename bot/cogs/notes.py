from __future__ import annotations

from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, reply_embed


class Notes(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="notes", description="Save and review study notes.", invoke_without_command=True)
    async def notes(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Notes Commands", description="Use `/notes add`, `/notes list`, `/notes view`, or `/notes delete`.", color=INFO)

    @notes.command(name="add", description="Save a new note.")
    async def notes_add(self, ctx: commands.Context, title: str, *, content: str) -> None:
        note_id = self.bot.db.save_note(ctx.guild.id, ctx.author.id, title, content)
        self.bot.db.add_xp(ctx.guild.id, ctx.author.id, 8)
        self.bot.db.sync_achievements(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Note Saved", description="Your note has been stored.", color=SUCCESS, fields=[("Note ID", str(note_id), True), ("Title", title, True)])

    @notes.command(name="list", description="List your saved notes with note IDs.")
    async def notes_list(self, ctx: commands.Context) -> None:
        notes = self.bot.db.list_notes(ctx.guild.id, ctx.author.id)
        if not notes:
            await reply_embed(ctx, title="No Notes Saved", description="Add one with `/notes add`.", color=INFO)
            return
        lines = [f"`{row['id']}` {row['title']}" for row in notes[:20]]
        await reply_embed(ctx, title="Your Notes", description="\n".join(lines), color=INFO)

    @notes.command(name="view", description="View one of your saved notes by ID or title.")
    async def notes_view(self, ctx: commands.Context, *, note: str) -> None:
        note_doc = None
        if note.isdigit():
            note_doc = self.bot.db.get_note_by_id(ctx.guild.id, ctx.author.id, int(note))
        else:
            for row in self.bot.db.list_notes(ctx.guild.id, ctx.author.id):
                if row["title"].strip().lower() == note.strip().lower():
                    note_doc = row
                    break
        if not note_doc:
            await reply_embed(ctx, title="Note Not Found", description=f"No note exists for `{note}`.", color=ERROR)
            return
        await reply_embed(
            ctx,
            title=f"Note: {note_doc['title']}",
            description=note_doc["content"][:3500],
            color=INFO,
            fields=[("Note ID", str(note_doc['id']), True)],
        )

    @notes.command(name="delete", description="Delete one of your saved notes by ID or title.")
    async def notes_delete(self, ctx: commands.Context, *, note: str) -> None:
        if note.isdigit():
            deleted = self.bot.db.delete_note_by_id(ctx.guild.id, ctx.author.id, int(note))
            label = note
        else:
            deleted = False
            label = note
            for row in self.bot.db.list_notes(ctx.guild.id, ctx.author.id):
                if row["title"].strip().lower() == note.strip().lower():
                    deleted = self.bot.db.delete_note_by_id(ctx.guild.id, ctx.author.id, row["id"])
                    label = str(row["id"])
                    break
        if not deleted:
            await reply_embed(ctx, title="Note Not Found", description=f"No note exists for `{note}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Note Deleted", description=f"Removed note `{label}`.", color=SUCCESS)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Notes(bot))
