"""
Activity Tracker Cog for Logiq
Tracks daily game-playing and Spotify-listening time via presence updates,
and posts a per-member summary card at 10pm local (Africa/Nairobi) time.
"""

import random
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
import logging

from utils.embeds import EmbedFactory, EmbedColor
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Africa/Nairobi")

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

    def cog_unload(self):
        self.daily_report.cancel()

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

        for guild in self.bot.guilds:
            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            # Flush any sessions still running so today's totals include them
            for (g_id, u_id, a_type, a_name), start in list(self.sessions.items()):
                if g_id != guild.id:
                    continue
                elapsed = (now - start).total_seconds()
                await self.db.add_activity_seconds(guild.id, u_id, today, a_type, a_name, elapsed)
                self.sessions[(g_id, u_id, a_type, a_name)] = now  # keep tracking, reset the clock

            activity_by_user = await self.db.get_daily_activity(guild.id, today)

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

    @daily_report.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityTracker(bot, bot.db, bot.config))