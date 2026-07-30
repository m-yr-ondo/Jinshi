"""

XP and leveling system with rank cards
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
from typing import Optional
import logging
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from utils.embeds import EmbedFactory, EmbedColor
from utils.constants import calculate_level_xp
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class ResetLevelsConfirmView(discord.ui.View):
    """Confirmation view shown before wiping every level in a guild"""

    def __init__(self, db: DatabaseManager, guild_id: int, author_id: int):
        super().__init__(timeout=30)
        self.db = db
        self.guild_id = guild_id
        self.author_id = author_id
        self.responded = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only the admin who ran the command can confirm/cancel it
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.responded = True
        count = await self.db.reset_guild_levels(self.guild_id)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=EmbedFactory.success(
                "Levels Reset",
                f"Reset XP and level to 0 for **{count}** member(s) in this server."
            ),
            view=self
        )
        logger.info(f"{interaction.user} reset all levels in guild {self.guild_id} ({count} affected)")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.responded = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=EmbedFactory.warning("Cancelled", "No levels were changed."),
            view=self
        )

    async def on_timeout(self) -> None:
        if not self.responded:
            for child in self.children:
                child.disabled = True
            # message may be gone/edited already; best effort only
            try:
                await self.message.edit(
                    embed=EmbedFactory.warning("Cancelled", "Confirmation timed out. No levels were changed."),
                    view=self
                )
            except (discord.NotFound, discord.HTTPException, AttributeError):
                pass


class Leveling(commands.Cog):
    """Leveling system cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.module_config = config.get('modules', {}).get('leveling', {})
        self.xp_cooldown = {}
        self.voice_xp_tick.start()

    def cog_unload(self):
        self.voice_xp_tick.cancel()

    async def _award_xp(self, user_id: int, guild_id: int, amount: int, announce_channel: Optional[discord.TextChannel] = None):
        """Shared XP-award + level-up logic, used by both message and voice XP"""
        user_data = await self.db.get_user(user_id, guild_id)
        if not user_data:
            user_data = await self.db.create_user(user_id, guild_id)

        new_xp = user_data.get('xp', 0) + amount
        current_level = user_data.get('level', 0)

        new_level = current_level
        while new_xp >= calculate_level_xp(new_level + 1):
            new_level += 1

        if new_level > current_level:
            await self.db.update_user(user_id, guild_id, {'xp': new_xp, 'level': new_level})
            logger.info(f"User {user_id} leveled up to {new_level} in guild {guild_id}")
            if announce_channel:
                member = announce_channel.guild.get_member(user_id)
                if member:
                    await announce_channel.send(embed=EmbedFactory.level_up(member, new_level, new_xp))
        else:
            await self.db.update_user(user_id, guild_id, {'xp': new_xp})

    @tasks.loop(minutes=1)
    async def voice_xp_tick(self):
        """Award voice XP once per minute to anyone in a voice channel with at least
        one other human present - prevents farming XP by idling alone in an empty VC."""
        if not self.module_config.get('enabled', True):
            return
        rate = self.module_config.get('voice_xp_rate', 5)

        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                if channel == guild.afk_channel:
                    continue
                humans = [m for m in channel.members if not m.bot]
                if len(humans) < 2:
                    continue
                for member in humans:
                    await self._award_xp(member.id, guild.id, rate, announce_channel=guild.system_channel)

    @voice_xp_tick.before_loop
    async def before_voice_xp_tick(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Award XP for messages"""
        if not self.module_config.get('enabled', True):
            return

        if message.author.bot or not message.guild:
            return

        # Check cooldown
        user_key = f"{message.guild.id}_{message.author.id}"
        current_time = datetime.utcnow().timestamp()

        if user_key in self.xp_cooldown:
            if current_time - self.xp_cooldown[user_key] < self.module_config.get('xp_cooldown', 60):
                return

        self.xp_cooldown[user_key] = current_time
        xp_gain = self.module_config.get('xp_per_message', 10)
        await self._award_xp(message.author.id, message.guild.id, xp_gain, announce_channel=message.channel)

    # NOTE: /rank and /leaderboard commands have been moved to games.py as PUBLIC commands

    @app_commands.command(name="setlevel", description="Set user's level (Admin)")
    @app_commands.describe(
        user="User to modify",
        level="New level"
    )
    @is_admin()
    async def set_level(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        level: int
    ):
        """Set user level"""
        if level < 0:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Level", "Level must be 0 or greater"),
                ephemeral=True
            )
            return

        xp = calculate_level_xp(level)

        await self.db.update_user(user.id, interaction.guild.id, {
            'level': level,
            'xp': xp
        })

        embed = EmbedFactory.success(
            "Level Set",
            f"Set {user.mention}'s level to **{level}**"
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"{interaction.user} set {user}'s level to {level}")

    @app_commands.command(name="resetlevels", description="Reset all levels (Admin)")
    @is_admin()
    async def reset_levels(self, interaction: discord.Interaction):
        """Reset all levels in guild (requires confirmation - destructive)"""
        view = ResetLevelsConfirmView(self.db, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            embed=EmbedFactory.warning(
                "Reset All Levels?",
                "This will set **every** member's XP and level back to 0 in this server. "
                "This cannot be undone.\n\nConfirm within 30 seconds to proceed."
            ),
            view=view,
            ephemeral=True
        )
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(Leveling(bot, bot.db, bot.config))