"""
Activity Tracker Cog for Logiq
Tracks daily game-playing and Spotify-listening time via presence updates,
and posts a per-member summary card at 10pm local (Africa/Nairobi) time.
"""

import random
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging

from utils.embeds import EmbedFactory, EmbedColor
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Africa/Nairobi")
CHECKPOINT_MINUTES = 5  # how often ongoing sessions are saved, bounding restart data-loss to this window

NO_ACTIVITY_LINES = [
    "{name} was not feeling well today.",
    "{name} touched grass today. Respect.",
    "{name} went completely dark today.",
    "{name} was suspiciously offline all day.",
]


def _classify(activity: discord.BaseActivity):
    """Return (type, name) for activities we care about, or None to ignore it"""
    if isinstance(activity, discord.Spotify):
        return ("spotify", "Spotify")
    if isinstance(activity, discord.Activity) and activity.type == discord.ActivityType.playing:
        return ("game", activity.name)
    return None


class ActivityTracker(commands.Cog):
    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.module_config = config.get("modules", {}).get("activity_tracker", {})
        # in-memory: {(guild_id, user_id, type, name): start_time}
        self.sessions = {}
        self.last_report_date = None
        self.daily_report.start()
        self.checkpoint_sessions.start()

    def cog_unload(self):
        self.daily_report.cancel()
        self.checkpoint_sessions.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        # Seed sessions already in progress at startup, so a restart mid-session
        # doesn't lose the time played before the bot came back up.
        now = datetime.now(TZ)
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot:
                    continue
                for activity in member.activities:
                    classified = _classify(activity)
                    if classified:
                        key = (guild.id, member.id, *classified)
                        self.sessions.setdefault(key, now)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if after.bot or not self.module_config.get("enabled", True):
            return

        before_keys = {_classify(a) for a in before.activities if _classify(a)}
        after_keys = {_classify(a) for a in after.activities if _classify(a)}

        now = datetime.now(TZ)

        # Started
        for classified in after_keys - before_keys:
            key = (after.guild.id, after.id, *classified)
            self.sessions.setdefault(key, now)

        # Ended - flush elapsed time
        for classified in before_keys - after_keys:
            key = (after.guild.id, after.id, *classified)
            start = self.sessions.pop(key, None)
            if start:
                elapsed = (now - start).total_seconds()
                await self.db.add_activity_seconds(
                    after.guild.id, after.id, now.strftime("%Y-%m-%d"),
                    classified[0], classified[1], elapsed
                )

    async def _flush_all_sessions(self, now: datetime):
        """Save elapsed time for every ongoing session so far, then reset their clocks.
        Used both by the periodic checkpoint and before building a report, so a
        restart or a report never loses more than CHECKPOINT_MINUTES of progress."""
        for key, start in list(self.sessions.items()):
            g_id, u_id, a_type, a_name = key
            elapsed = (now - start).total_seconds()
            await self.db.add_activity_seconds(
                g_id, u_id, now.strftime("%Y-%m-%d"), a_type, a_name, elapsed
            )
            self.sessions[key] = now

    @tasks.loop(minutes=CHECKPOINT_MINUTES)
    async def checkpoint_sessions(self):
        await self._flush_all_sessions(datetime.now(TZ))

    @checkpoint_sessions.before_loop
    async def before_checkpoint(self):
        await self.bot.wait_until_ready()

    async def _send_report(self, guild: discord.Guild, channel: discord.TextChannel, date_str: str):
        activity_by_user = await self.db.get_daily_activity(guild.id, date_str)

        for member in guild.members:
            if member.bot:
                continue
            entries = activity_by_user.get(member.id)
            if not entries:
                embed = EmbedFactory.create(
                    title=member.display_name,
                    description=random.choice(NO_ACTIVITY_LINES).format(name=member.display_name),
                    color=EmbedColor.INFO,
                    thumbnail=member.display_avatar.url
                )
            else:
                lines = []
                spotify_seconds = 0
                for entry in entries:
                    if entry["type"] == "spotify":
                        spotify_seconds += entry["seconds"]
                    else:
                        lines.append(f"**{entry['name']}** - {entry['seconds'] / 3600:.1f}h")
                if spotify_seconds:
                    lines.append(f"**Spotify** - {spotify_seconds / 3600:.1f}h")

                embed = EmbedFactory.create(
                    title=member.display_name,
                    description="\n".join(lines),
                    color=EmbedColor.PRIMARY,
                    thumbnail=member.display_avatar.url,
                    footer="Today's activity"
                )
            await channel.send(embed=embed)

    @tasks.loop(minutes=1)
    async def daily_report(self):
        now = datetime.now(TZ)
        if now.hour != 22 or now.minute != 0:
            return
        today = now.strftime("%Y-%m-%d")
        if self.last_report_date == today:
            return
        self.last_report_date = today

        channel_id = self.module_config.get("channel_id")
        if not channel_id:
            return

        await self._flush_all_sessions(now)

        for guild in self.bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                await self._send_report(guild, channel, today)

    @daily_report.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="testactivityreport", description="Send today's activity report right now (Admin)")
    @is_admin()
    async def test_activity_report(self, interaction: discord.Interaction):
        channel_id = self.module_config.get("channel_id")
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        if not channel:
            await interaction.response.send_message(
                embed=EmbedFactory.error("No Report Channel", "activity_tracker.channel_id isn't set or the channel wasn't found."),
                ephemeral=True
            )
            return

        await interaction.response.send_message("Sending test report now...", ephemeral=True)
        now = datetime.now(TZ)
        await self._flush_all_sessions(now)
        await self._send_report(interaction.guild, channel, now.strftime("%Y-%m-%d"))


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityTracker(bot, bot.db, bot.config))