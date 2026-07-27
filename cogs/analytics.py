"""
Analytics Cog for Logiq
Server analytics and statistics tracking
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Optional
import logging

from utils.embeds import EmbedFactory, EmbedColor
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class Analytics(commands.Cog):
    """Analytics and statistics cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.module_config = config.get('modules', {}).get('analytics', {})

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track message events"""
        if not self.module_config.get('enabled', True):
            return

        if message.author.bot or not message.guild:
            return

        await self.db.log_event('message', {
            'guild_id': message.guild.id,
            'user_id': message.author.id,
            'channel_id': message.channel.id
        })

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Track member joins"""
        if not self.module_config.get('enabled', True):
            return

        await self.db.log_event('member_join', {
            'guild_id': member.guild.id,
            'user_id': member.id
        })

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Track member leaves"""
        if not self.module_config.get('enabled', True):
            return

        await self.db.log_event('member_leave', {
            'guild_id': member.guild.id,
            'user_id': member.id
        })

    @app_commands.command(name="analytics", description="View server analytics")
    @app_commands.describe(days="Number of days to analyze (default: 7)")
    @is_admin()
    async def analytics(self, interaction: discord.Interaction, days: int = 7):
        """View server analytics"""
        if days < 1 or days > 365:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Range", "Days must be between 1 and 365"),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Calculate time range
        end_time = datetime.utcnow().timestamp()
        start_time = (datetime.utcnow() - timedelta(days=days)).timestamp()

        # Get analytics data
        messages = await self.db.get_analytics(
            interaction.guild.id,
            event_type='message',
            start_time=start_time,
            end_time=end_time
        )

        joins = await self.db.get_analytics(
            interaction.guild.id,
            event_type='member_join',
            start_time=start_time,
            end_time=end_time
        )

        leaves = await self.db.get_analytics(
            interaction.guild.id,
            event_type='member_leave',
            start_time=start_time,
            end_time=end_time
        )

        # Calculate stats
        total_messages = len(messages)
        total_joins = len(joins)
        total_leaves = len(leaves)
        net_growth = total_joins - total_leaves

        # Most active users
        user_message_counts = {}
        for msg in messages:
            user_id = msg.get('user_id')
            user_message_counts[user_id] = user_message_counts.get(user_id, 0) + 1

        top_users = sorted(user_message_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_users_text = "\n".join([
            f"{i + 1}. <@{user_id}>: {count} messages"
            for i, (user_id, count) in enumerate(top_users)
        ]) if top_users else "No data"

        embed = EmbedFactory.create(
            title=f"📊 Server Analytics - Last {days} Days",
            color=EmbedColor.INFO,
            fields=[
                {"name": "💬 Total Messages", "value": str(total_messages), "inline": True},
                {"name": "👋 Members Joined", "value": str(total_joins), "inline": True},
                {"name": "🚪 Members Left", "value": str(total_leaves), "inline": True},
                {"name": "📈 Net Growth", "value": str(net_growth), "inline": True},
                {"name": "📅 Period", "value": f"{days} days", "inline": True},
                {"name": "⏰ Generated", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "inline": True},
                {"name": "🏆 Most Active Users", "value": top_users_text, "inline": False}
            ]
        )

        await interaction.followup.send(embed=embed)
        logger.info(f"Analytics generated for {interaction.guild}")

    @app_commands.command(name="activity", description="View recent server activity")
    @is_admin()
    async def activity(self, interaction: discord.Interaction):
        """View recent activity"""
        # Get last 24 hours of activity
        end_time = datetime.utcnow().timestamp()
        start_time = (datetime.utcnow() - timedelta(hours=24)).timestamp()

        events = await self.db.get_analytics(
            interaction.guild.id,
            start_time=start_time,
            end_time=end_time
        )

        if not events:
            await interaction.response.send_message(
                embed=EmbedFactory.info("No Activity", "No recent activity data available"),
                ephemeral=True
            )
            return

        # Group by hour
        hourly_activity = {}
        for event in events:
            hour = datetime.fromtimestamp(event['timestamp']).strftime("%Y-%m-%d %H:00")
            hourly_activity[hour] = hourly_activity.get(hour, 0) + 1

        # Create activity chart (text-based)
        chart_text = ""
        for hour, count in sorted(hourly_activity.items())[-12:]:  # Last 12 hours
            bar = "█" * min(count // 10, 20)
            chart_text += f"{hour}: {bar} ({count})\n"

        embed = EmbedFactory.create(
            title="📈 Server Activity (Last 24 Hours)",
            description=f"```\n{chart_text}\n```",
            color=EmbedColor.INFO
        )
        embed.set_footer(text=f"Total events: {len(events)}")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(Analytics(bot, bot.db, bot.config))
