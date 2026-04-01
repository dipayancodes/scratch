from __future__ import annotations

from collections.abc import Sequence

import discord
from discord.ext import commands


SUCCESS = discord.Color.green()
ERROR = discord.Color.red()
INFO = discord.Color.blue()
WARNING = discord.Color.gold()


def make_embed(
    *,
    user: discord.abc.User,
    title: str,
    description: str = "",
    color: discord.Color = INFO,
    fields: Sequence[tuple[str, str, bool]] | None = None,
    footer: str = "Stay focused 📚",
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description[:4096], color=color)
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    for name, value, inline in fields or ():
        embed.add_field(name=name[:256], value=value[:1024] or "\u200b", inline=inline)
    embed.set_footer(text=footer[:2048])
    return embed


async def reply_embed(
    ctx: commands.Context,
    *,
    title: str,
    description: str = "",
    color: discord.Color = INFO,
    fields: Sequence[tuple[str, str, bool]] | None = None,
    footer: str = "Stay focused 📚",
) -> discord.Message:
    embed = make_embed(
        user=ctx.author,
        title=title,
        description=description,
        color=color,
        fields=fields,
        footer=footer,
    )
    return await ctx.reply(embed=embed, mention_author=False)


async def reply_to_message(
    message: discord.Message | discord.PartialMessage,
    *,
    user: discord.abc.User,
    title: str,
    description: str = "",
    color: discord.Color = INFO,
    fields: Sequence[tuple[str, str, bool]] | None = None,
    footer: str = "Stay focused 📚",
) -> discord.Message:
    embed = make_embed(
        user=user,
        title=title,
        description=description,
        color=color,
        fields=fields,
        footer=footer,
    )
    return await message.reply(embed=embed, mention_author=False)
