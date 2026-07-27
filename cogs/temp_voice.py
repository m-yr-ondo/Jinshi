"""
Temporary Voice Channels Cog for Logiq
Create temporary voice channels that auto-delete when empty
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging

from utils.embeds import EmbedFactory, EmbedColor
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class TempVoice(commands.Cog):
    """Temporary voice channels cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.module_config = config.get('modules', {}).get('temp_voice', {})
        self.temp_channels = set()  # Track temporary channels

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        """Handle voice state updates for temp channels"""
        if not self.module_config.get('enabled', True):
            return

        guild_config = await self.db.get_guild(member.guild.id)
        if not guild_config:
            return

        # Check if user joined the creator channel
        creator_channel_id = guild_config.get('temp_voice_creator')
        if creator_channel_id and after.channel and after.channel.id == creator_channel_id:
            await self.create_temp_channel(member, after.channel)

        # Check if a temp channel is now empty
        if before.channel and before.channel.id in self.temp_channels:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Temporary channel empty")
                    self.temp_channels.discard(before.channel.id)
                    logger.info(f"Deleted empty temp channel: {before.channel.name}")
                except discord.Forbidden:
                    logger.warning(f"Cannot delete temp channel: {before.channel.name}")
                except Exception as e:
                    logger.error(f"Error deleting temp channel: {e}", exc_info=True)

    async def create_temp_channel(self, member: discord.Member, creator_channel: discord.VoiceChannel):
        """Create a temporary voice channel for a member"""
        try:
            # Get category
            category = creator_channel.category

            # Create channel name
            channel_name = f"{member.display_name}'s Channel"

            # Create the channel
            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(connect=True),
                member: discord.PermissionOverwrite(
                    connect=True,
                    manage_channels=True,
                    move_members=True,
                    mute_members=True,
                    deafen_members=True
                )
            }

            temp_channel = await creator_channel.category.create_voice_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"Temporary channel for {member}"
            )

            # Track this channel
            self.temp_channels.add(temp_channel.id)

            # Move member to new channel
            await member.move_to(temp_channel)

            logger.info(f"Created temp channel for {member}: {temp_channel.name}")

        except discord.Forbidden:
            logger.warning(f"Cannot create temp channel for {member}")
        except Exception as e:
            logger.error(f"Error creating temp channel: {e}", exc_info=True)

    @app_commands.command(name="setup-tempvoice", description="Setup temporary voice channels (Admin)")
    @app_commands.describe(
        category="Category for temporary channels",
        creator_name="Name for the creator channel (default: '➕ Create Channel')"
    )
    @is_admin()
    async def setup_tempvoice(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        creator_name: str = "➕ Create Channel"
    ):
        """Setup temporary voice channels (ADMIN ONLY)"""
        try:
            # Create the creator channel
            creator_channel = await category.create_voice_channel(
                name=creator_name,
                reason="Temporary voice channel creator"
            )

            # Save to database
            guild_config = await self.db.get_guild(interaction.guild.id)
            if not guild_config:
                guild_config = await self.db.create_guild(interaction.guild.id)

            await self.db.update_guild(interaction.guild.id, {
                'temp_voice_creator': creator_channel.id,
                'temp_voice_category': category.id
            })

            embed = EmbedFactory.success(
                "✅ Temporary Voice Setup",
                f"**Category:** {category.mention}\n"
                f"**Creator Channel:** {creator_channel.mention}\n\n"
                "Users can join the creator channel to automatically create their own temporary voice channel!"
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"Temp voice setup in {interaction.guild}")

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Permission Error", "I don't have permission to create channels"),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error setting up temp voice: {e}", exc_info=True)
            await interaction.response.send_message(
                embed=EmbedFactory.error("Error", f"Failed to setup temporary voice: {str(e)}"),
                ephemeral=True
            )

    @app_commands.command(name="voice-lock", description="Lock your temporary voice channel")
    async def voice_lock(self, interaction: discord.Interaction):
        """Lock temporary voice channel"""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not in Voice", "You must be in a voice channel"),
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel

        if channel.id not in self.temp_channels:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not a Temp Channel", "This is not a temporary voice channel"),
                ephemeral=True
            )
            return

        try:
            await channel.set_permissions(
                interaction.guild.default_role,
                connect=False
            )
            embed = EmbedFactory.success("🔒 Locked", f"Locked {channel.mention}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Permission Error", "I don't have permission to modify this channel"),
                ephemeral=True
            )

    @app_commands.command(name="voice-unlock", description="Unlock your temporary voice channel")
    async def voice_unlock(self, interaction: discord.Interaction):
        """Unlock temporary voice channel"""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not in Voice", "You must be in a voice channel"),
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel

        if channel.id not in self.temp_channels:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not a Temp Channel", "This is not a temporary voice channel"),
                ephemeral=True
            )
            return

        try:
            await channel.set_permissions(
                interaction.guild.default_role,
                connect=True
            )
            embed = EmbedFactory.success("🔓 Unlocked", f"Unlocked {channel.mention}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Permission Error", "I don't have permission to modify this channel"),
                ephemeral=True
            )

    @app_commands.command(name="voice-limit", description="Set user limit for your temporary voice channel")
    @app_commands.describe(limit="User limit (0 for no limit)")
    async def voice_limit(self, interaction: discord.Interaction, limit: int):
        """Set user limit for temporary voice channel"""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not in Voice", "You must be in a voice channel"),
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel

        if channel.id not in self.temp_channels:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not a Temp Channel", "This is not a temporary voice channel"),
                ephemeral=True
            )
            return

        if limit < 0 or limit > 99:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Limit", "Limit must be between 0 and 99"),
                ephemeral=True
            )
            return

        try:
            await channel.edit(user_limit=limit)
            limit_text = "No limit" if limit == 0 else f"{limit} users"
            embed = EmbedFactory.success("👥 Limit Set", f"User limit set to: {limit_text}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Permission Error", "I don't have permission to modify this channel"),
                ephemeral=True
            )

    @app_commands.command(name="voice-rename", description="Rename your temporary voice channel")
    @app_commands.describe(name="New channel name")
    async def voice_rename(self, interaction: discord.Interaction, name: str):
        """Rename temporary voice channel"""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not in Voice", "You must be in a voice channel"),
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel

        if channel.id not in self.temp_channels:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not a Temp Channel", "This is not a temporary voice channel"),
                ephemeral=True
            )
            return

        if len(name) > 100:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Name Too Long", "Channel name must be 100 characters or less"),
                ephemeral=True
            )
            return

        try:
            old_name = channel.name
            await channel.edit(name=name)
            embed = EmbedFactory.success("✏️ Renamed", f"Renamed channel from **{old_name}** to **{name}**")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Permission Error", "I don't have permission to modify this channel"),
                ephemeral=True
            )

    @app_commands.command(name="voice-claim", description="Claim ownership of an abandoned temporary voice channel")
    async def voice_claim(self, interaction: discord.Interaction):
        """Claim ownership of temporary voice channel"""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not in Voice", "You must be in a voice channel"),
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel

        if channel.id not in self.temp_channels:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not a Temp Channel", "This is not a temporary voice channel"),
                ephemeral=True
            )
            return

        try:
            # Give user manage permissions
            await channel.set_permissions(
                interaction.user,
                connect=True,
                manage_channels=True,
                move_members=True,
                mute_members=True,
                deafen_members=True
            )
            embed = EmbedFactory.success("👑 Claimed", f"You now own {channel.mention}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Permission Error", "I don't have permission to modify this channel"),
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(TempVoice(bot, bot.db, bot.config))
