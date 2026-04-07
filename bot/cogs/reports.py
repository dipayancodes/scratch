from __future__ import annotations

import asyncio
from datetime import timedelta

import discord
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, WARNING, make_embed, reply_embed


ADMIN_ROLE_ID = 1453304133506564278
STAFF_ROLE_ID = 1453305075740053645
REPORT_CHANNEL_ID = 1453301328859103342
REPORT_CATEGORY_NAME = "Reports"
REPORT_SPAM_LIMIT = 3
REPORT_TIMEOUT = timedelta(days=7)
REPORT_THANK_YOU_REWARD = 75


class ReportPanelView(discord.ui.View):
    def __init__(self, cog: "Reports") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Open Report", style=discord.ButtonStyle.danger, custom_id="reports:open")
    async def open_report(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.open_report(interaction)


class ReportPendingCaseView(discord.ui.View):
    def __init__(self, cog: "Reports") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, custom_id="reports:claim")
    async def claim_report(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.claim_report(interaction)


class ReportClaimedCaseView(discord.ui.View):
    def __init__(self, cog: "Reports") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, custom_id="reports:close")
    async def close_report(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.close_report(interaction)

    @discord.ui.button(label="Thank You", style=discord.ButtonStyle.success, custom_id="reports:thanks")
    async def thank_reporter(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.thank_reporter(interaction)


class Reports(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._creation_locks: dict[tuple[int, int], asyncio.Lock] = {}

    async def cog_load(self) -> None:
        self.bot.add_view(ReportPanelView(self))
        self.bot.add_view(ReportPendingCaseView(self))
        self.bot.add_view(ReportClaimedCaseView(self))

    async def _db_call(self, func, *args, default=None, operation: str = "database operation", **kwargs):
        helper = getattr(self.bot, "_db_call", None)
        if callable(helper):
            return await helper(func, *args, default=default, operation=operation, **kwargs)
        return func(*args, **kwargs)

    @staticmethod
    def _is_admin(member: discord.Member) -> bool:
        return member.guild_permissions.administrator or any(role.id == ADMIN_ROLE_ID for role in member.roles)

    @staticmethod
    def _is_staff(member: discord.Member) -> bool:
        return member.guild_permissions.administrator or any(role.id in {ADMIN_ROLE_ID, STAFF_ROLE_ID} for role in member.roles)

    @staticmethod
    def _report_channel_name(user: discord.abc.User) -> str:
        display = user.display_name.replace("\n", " ").strip() or user.name
        return f"report • {display}"[:100]

    def _creation_lock(self, guild_id: int, user_id: int) -> asyncio.Lock:
        key = (guild_id, user_id)
        lock = self._creation_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._creation_locks[key] = lock
        return lock

    @staticmethod
    def _panel_embed(user: discord.abc.User) -> discord.Embed:
        return make_embed(
            user=user,
            title="Report a User",
            description="Use this only for serious reports. Press the button below and I will DM you to collect the full issue and evidence before opening a private staff case.",
            color=WARNING,
            fields=[
                ("Examples", "Illegal content, harassment, threats, severe rule breaks, or urgent staff/admin attention.", False),
                ("How It Works", "Press the button, reply in DM with details and screenshots/videos, then staff/admin review the private case.", False),
            ],
        )

    def _target_panel_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel = guild.get_channel(REPORT_CHANNEL_ID)
        return channel if isinstance(channel, discord.TextChannel) else None

    def _report_overwrites(self, guild: discord.Guild) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
        }
        if guild.me is not None:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                attach_files=True,
                embed_links=True,
            )
        for role in guild.roles:
            if role.id in {ADMIN_ROLE_ID, STAFF_ROLE_ID} or role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                    manage_channels=True,
                )
        return overwrites

    async def _timeout_report_spammer(self, member: discord.Member) -> bool:
        try:
            await member.timeout(discord.utils.utcnow() + REPORT_TIMEOUT, reason="Report system abuse")
            return True
        except discord.HTTPException:
            return False

    async def _ensure_report_category(self, guild: discord.Guild, panel_channel: discord.TextChannel | None) -> discord.CategoryChannel | None:
        state = await self._db_call(
            self.bot.db.get_report_panel_state,
            guild.id,
            default=None,
            operation="get_report_panel_state",
        )
        category = guild.get_channel(state.get("category_id", 0)) if state else None
        if not isinstance(category, discord.CategoryChannel):
            for candidate in guild.categories:
                if candidate.name == REPORT_CATEGORY_NAME:
                    category = candidate
                    break
        if not isinstance(category, discord.CategoryChannel):
            try:
                category = await guild.create_category(REPORT_CATEGORY_NAME, position=0, reason="Report system setup")
            except discord.HTTPException:
                return None
        try:
            await category.edit(position=0, reason="Keep report category at the top")
        except discord.HTTPException:
            pass
        if panel_channel is not None and panel_channel.category_id != category.id:
            try:
                await panel_channel.edit(category=category, position=0, sync_permissions=False, reason="Report system setup")
            except discord.HTTPException:
                pass
        await self._db_call(
            self.bot.db.set_report_panel_state,
            guild.id,
            channel_id=panel_channel.id if panel_channel is not None else REPORT_CHANNEL_ID,
            category_id=category.id,
            default=None,
            operation="set_report_panel_category",
        )
        return category

    async def _find_existing_panel_message(self, channel: discord.TextChannel) -> discord.Message | None:
        async for message in channel.history(limit=25):
            if message.author.id != self.bot.user.id:
                continue
            for row in message.components:
                for component in row.children:
                    if getattr(component, "custom_id", None) == "reports:open":
                        return message
        return None

    async def ensure_report_panel(self, guild: discord.Guild) -> tuple[discord.TextChannel | None, bool]:
        panel_channel = self._target_panel_channel(guild)
        if panel_channel is None:
            return None, False
        category = await self._ensure_report_category(guild, panel_channel)
        state = await self._db_call(
            self.bot.db.get_report_panel_state,
            guild.id,
            default=None,
            operation="get_report_panel_state",
        )
        if state and state.get("message_id"):
            try:
                await panel_channel.fetch_message(int(state["message_id"]))
                return panel_channel, False
            except discord.NotFound:
                pass
            except discord.HTTPException:
                return panel_channel, False
        existing_message = await self._find_existing_panel_message(panel_channel)
        if existing_message is not None:
            await self._db_call(
                self.bot.db.set_report_panel_state,
                guild.id,
                channel_id=panel_channel.id,
                message_id=existing_message.id,
                category_id=category.id if category is not None else None,
                default=None,
                operation="set_report_panel_existing",
            )
            return panel_channel, False
        message = await panel_channel.send(embed=self._panel_embed(guild.me or self.bot.user), view=ReportPanelView(self))
        await self._db_call(
            self.bot.db.set_report_panel_state,
            guild.id,
            channel_id=panel_channel.id,
            message_id=message.id,
            category_id=category.id if category is not None else None,
            default=None,
            operation="set_report_panel_created",
        )
        return panel_channel, True

    @commands.command(name="reportpanel", hidden=True)
    async def reportpanel(self, ctx: commands.Context) -> None:
        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if member is None or not self._is_staff(member):
            await reply_embed(
                ctx,
                title="Permission Error",
                description="Only Staff or Admin can post the report panel.",
                color=WARNING,
            )
            return
        target, created = await self.ensure_report_panel(ctx.guild)
        if target is None:
            await reply_embed(
                ctx,
                title="Report Channel Missing",
                description=f"I could not find the configured report channel with ID `{REPORT_CHANNEL_ID}`.",
                color=ERROR,
            )
            return
        await reply_embed(
            ctx,
            title="Report Panel Ready",
            description=(
                f"The report panel is live in {target.mention}."
                if created
                else f"The report panel already exists in {target.mention}. No duplicate was posted."
            ),
            color=SUCCESS if created else INFO,
        )

    async def open_report(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This report button only works inside the server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        lock = self._creation_lock(interaction.guild.id, interaction.user.id)
        async with lock:
            existing = await self._db_call(
                self.bot.db.get_active_report_for_user,
                interaction.guild.id,
                interaction.user.id,
                default=None,
                operation="get_active_report_for_user",
            )
            if existing is not None:
                attempts = await self._db_call(
                    self.bot.db.add_report_attempt,
                    interaction.guild.id,
                    interaction.user.id,
                    default=0,
                    operation="add_report_attempt",
                )
                muted = attempts >= REPORT_SPAM_LIMIT and await self._timeout_report_spammer(interaction.user)
                embed = make_embed(
                    user=interaction.user,
                    title="Report Already Open",
                    description=(
                        "You already have an active report. Continue in DM or wait for Staff/Admin to close the current case."
                        if not muted
                        else "You spammed the report button while a case was already open, so you were muted for 1 week."
                    ),
                    color=WARNING if not muted else ERROR,
                    fields=[("Attempts", f"`{attempts}` in the last 10 minutes", True)],
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            prompt = make_embed(
                user=interaction.user,
                title="Report Intake Started",
                description="Reply here with the issue details and attach any screenshots, photos, or videos. Everything you send in this DM will be forwarded to a private staff report case.",
                color=INFO,
            )
            try:
                await interaction.user.send(embed=prompt)
            except discord.HTTPException:
                await interaction.followup.send(
                    embed=make_embed(
                        user=interaction.user,
                        title="DM Required",
                        description="I could not DM you. Turn on DMs for this server and press the report button again.",
                        color=ERROR,
                    ),
                    ephemeral=True,
                )
                return
            report = await self._db_call(
                self.bot.db.create_report,
                interaction.guild.id,
                interaction.user.id,
                REPORT_CHANNEL_ID,
                default=None,
                operation="create_report",
            )
            if report is None:
                await interaction.followup.send(
                    embed=make_embed(
                        user=interaction.user,
                        title="Report Intake Failed",
                        description="I could not start the private report intake right now. Try again in a moment.",
                        color=ERROR,
                    ),
                    ephemeral=True,
                )
                return
            await interaction.followup.send(
                embed=make_embed(
                    user=interaction.user,
                    title="Check Your DMs",
                    description="Your report intake is open. Send the full issue and any evidence in DM now. The private case channel will be created only after you send the evidence.",
                    color=SUCCESS,
                ),
                ephemeral=True,
            )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self.bot.user is None:
            return
        for guild in self.bot.guilds:
            try:
                await self.ensure_report_panel(guild)
            except discord.HTTPException:
                continue

    async def claim_report(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This button only works inside the server.", ephemeral=True)
            return
        if not self._is_staff(interaction.user):
            await interaction.response.send_message("Only Staff or Admin can claim reports.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        report = await self._db_call(
            self.bot.db.get_active_report_by_channel,
            interaction.guild.id,
            interaction.channel_id,
            default=None,
            operation="get_active_report_by_channel",
        )
        if report is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send(
                embed=make_embed(
                    user=interaction.user,
                    title="Report Missing",
                    description="I could not find an active report for this channel.",
                    color=ERROR,
                ),
                ephemeral=True,
            )
            return
        if report.get("claimed_by") and report["claimed_by"] != interaction.user.id:
            await interaction.followup.send(
                embed=make_embed(
                    user=interaction.user,
                    title="Already Claimed",
                    description="Another staff member already claimed this report.",
                    color=WARNING,
                ),
                ephemeral=True,
            )
            return
        reporter = interaction.guild.get_member(report["user_id"])
        if reporter is None:
            await interaction.followup.send(
                embed=make_embed(
                    user=interaction.user,
                    title="Reporter Missing",
                    description="The reporting user is no longer available in this server.",
                    color=ERROR,
                ),
                ephemeral=True,
            )
            return
        await interaction.channel.set_permissions(
            reporter,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        )
        await self._db_call(
            self.bot.db.claim_report,
            report["id"],
            interaction.user.id,
            default=None,
            operation="claim_report",
        )
        if interaction.message is not None:
            try:
                await interaction.message.edit(view=ReportClaimedCaseView(self))
            except discord.HTTPException:
                pass
        await interaction.channel.send(
            content=reporter.mention,
            embed=make_embed(
                user=interaction.user,
                title="Report Claimed",
                description=f"{interaction.user.mention} claimed this report. The reporter can now join the discussion here.",
                color=SUCCESS,
            ),
            allowed_mentions=discord.AllowedMentions(users=True),
        )
        await interaction.followup.send(
            embed=make_embed(
                user=interaction.user,
                title="Report Claimed",
                description="The reporter now has access to this case channel.",
                color=SUCCESS,
            ),
            ephemeral=True,
        )

    async def close_report(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This button only works inside the server.", ephemeral=True)
            return
        if not self._is_staff(interaction.user):
            await interaction.response.send_message("Only Staff or Admin can close reports.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        report = await self._db_call(
            self.bot.db.get_active_report_by_channel,
            interaction.guild.id,
            interaction.channel_id,
            default=None,
            operation="get_active_report_by_channel",
        )
        if report is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send(
                embed=make_embed(
                    user=interaction.user,
                    title="Report Missing",
                    description="I could not find an active report for this channel.",
                    color=ERROR,
                ),
                ephemeral=True,
            )
            return
        reporter = interaction.guild.get_member(report["user_id"])
        if reporter is not None:
            try:
                await reporter.send(
                    embed=make_embed(
                        user=reporter,
                        title="Report Closed",
                        description="Your report has been concluded and the case channel is being deleted.",
                        color=INFO,
                    )
                )
            except discord.HTTPException:
                pass
        await self._db_call(
            self.bot.db.close_report,
            report["id"],
            default=None,
            operation="close_report",
        )
        channel = interaction.channel
        await interaction.followup.send(
            embed=make_embed(
                user=interaction.user,
                title="Closing Report",
                description="The case is closed and the channel will now be deleted.",
                color=INFO,
            ),
            ephemeral=True,
        )
        try:
            await channel.delete(reason=f"Report closed by {interaction.user}")
        except discord.HTTPException:
            pass

    async def thank_reporter(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This button only works inside the server.", ephemeral=True)
            return
        if not self._is_staff(interaction.user):
            await interaction.response.send_message("Only Staff or Admin can thank reporters.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        report = await self._db_call(
            self.bot.db.get_active_report_by_channel,
            interaction.guild.id,
            interaction.channel_id,
            default=None,
            operation="get_active_report_by_channel",
        )
        if report is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send(
                embed=make_embed(
                    user=interaction.user,
                    title="Report Missing",
                    description="I could not find an active report for this channel.",
                    color=ERROR,
                ),
                ephemeral=True,
            )
            return
        if report.get("thanked_at"):
            await interaction.followup.send(
                embed=make_embed(
                    user=interaction.user,
                    title="Already Rewarded",
                    description="This report was already thanked and rewarded.",
                    color=WARNING,
                ),
                ephemeral=True,
            )
            return
        reporter = interaction.guild.get_member(report["user_id"])
        user = reporter
        if user is None:
            user = self.bot.get_user(report["user_id"])
            if user is None:
                try:
                    user = await self.bot.fetch_user(report["user_id"])
                except discord.HTTPException:
                    user = None
        updated = await self._db_call(
            self.bot.db.mark_report_thanked,
            report["id"],
            interaction.user.id,
            default=None,
            operation="mark_report_thanked",
        )
        if updated is None:
            await interaction.followup.send(
                embed=make_embed(
                    user=interaction.user,
                    title="Already Rewarded",
                    description="This report was already thanked and rewarded.",
                    color=WARNING,
                ),
                ephemeral=True,
            )
            return
        await self._db_call(
            self.bot.db.add_coins,
            interaction.guild.id,
            report["user_id"],
            REPORT_THANK_YOU_REWARD,
            default=None,
            operation="reward_reporter_coins",
        )
        if user is not None:
            try:
                await user.send(
                    embed=make_embed(
                        user=user,
                        title="Thank You for Reporting",
                        description=(
                            "Your report helped the staff team review a serious issue. "
                            f"You received `{REPORT_THANK_YOU_REWARD}` reward points for doing the right thing."
                        ),
                        color=SUCCESS,
                    )
                )
            except discord.HTTPException:
                pass
        await self._db_call(
            self.bot.db.close_report,
            report["id"],
            default=None,
            operation="close_report_after_thanks",
        )
        await interaction.followup.send(
            embed=make_embed(
                user=interaction.user,
                title="Thank You Sent",
                description="The reporter was DM'd, rewarded, and this case will now be closed.",
                color=SUCCESS,
            ),
            ephemeral=True,
        )
        try:
            await interaction.channel.delete(reason=f"Report thanked and closed by {interaction.user}")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is not None:
            return
        report = await self._db_call(
            self.bot.db.get_active_report_for_dm_user,
            message.author.id,
            default=None,
            operation="get_active_report_for_dm_user",
        )
        if report is None:
            return
        if not message.content.strip() and not message.attachments:
            try:
                await message.reply(
                    embed=make_embed(
                        user=message.author,
                        title="More Detail Needed",
                        description="Send the issue details or attach screenshots, photos, or videos so I can forward them to Staff/Admin.",
                        color=WARNING,
                    ),
                    mention_author=False,
                )
            except discord.HTTPException:
                pass
            return
        guild = self.bot.get_guild(report["guild_id"])
        if guild is None:
            return
        channel = guild.get_channel(report.get("channel_id", 0)) if report.get("channel_id") else None
        if not isinstance(channel, discord.TextChannel):
            panel_channel = self._target_panel_channel(guild)
            category = await self._ensure_report_category(guild, panel_channel)
            try:
                channel = await guild.create_text_channel(
                    name=self._report_channel_name(message.author),
                    category=category,
                    overwrites=self._report_overwrites(guild),
                    reason=f"Report case for {message.author}",
                )
            except discord.HTTPException:
                try:
                    await message.reply(
                        embed=make_embed(
                            user=message.author,
                            title="Report Channel Failed",
                            description="I received your evidence, but I could not create the private case channel right now. Try again shortly.",
                            color=ERROR,
                        ),
                        mention_author=False,
                    )
                except discord.HTTPException:
                    pass
                return
            await self._db_call(
                self.bot.db.attach_report_channel,
                report["id"],
                channel.id,
                default=None,
                operation="attach_report_channel",
            )
            await channel.send(
                content=f"<@&{STAFF_ROLE_ID}> <@&{ADMIN_ROLE_ID}>",
                embed=make_embed(
                    user=message.author,
                    title="New Report Case",
                    description="Evidence has been received. Staff or admin can claim this case now.",
                    color=WARNING,
                    fields=[
                        ("Report ID", str(report["id"]), True),
                        ("Reporter", f"{message.author.mention} (`{message.author.id}`)", False),
                        ("Status", "`submitted`", True),
                    ],
                ),
                view=ReportPendingCaseView(self),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        attachment_block = "\n".join(attachment.url for attachment in message.attachments)
        details = message.content.strip() or "Attachment-only evidence submitted."
        fields = [("Reporter", f"{message.author.mention} (`{message.author.id}`)", False)]
        if attachment_block:
            fields.append(("Attachments", attachment_block[:1024], False))
        await channel.send(
            content=attachment_block or None,
            embed=make_embed(
                user=message.author,
                title="Report Evidence Received",
                description=details,
                color=INFO,
                fields=fields,
            ),
            allowed_mentions=discord.AllowedMentions(users=True),
        )
        await self._db_call(
            self.bot.db.mark_report_submitted,
            report["id"],
            default=None,
            operation="mark_report_submitted",
        )
        try:
            await message.reply(
                embed=make_embed(
                    user=message.author,
                    title="Evidence Forwarded",
                    description="Your report details were sent to the private Staff/Admin case channel.",
                    color=SUCCESS,
                ),
                mention_author=False,
            )
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if isinstance(channel, discord.TextChannel):
            await self._db_call(
                self.bot.db.close_report_by_channel,
                channel.guild.id,
                channel.id,
                default=None,
                operation="close_report_by_channel",
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reports(bot))
