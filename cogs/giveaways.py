"""
Giveaways Cog for Logiq
Complete giveaway system with reactions and winners
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Optional
import logging
import random
import asyncio

from utils.embeds import EmbedFactory, EmbedColor
from utils.permissions import is_admin
from utils.converters import TimeConverter
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class GiveawayView(discord.ui.View):
    """View for giveaway participation"""

    def __init__(self, giveaway_id: str, cog: 'Giveaways'):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.cog = cog

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.success, custom_id="giveaway_enter")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle giveaway entry"""
        # Get giveaway from database
        giveaway = await self.cog.db.db.giveaways.find_one({"_id": self.giveaway_id})
        
        if not giveaway:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Error", "Giveaway not found"),
                ephemeral=True
            )
            return

        # Check if already ended
        if giveaway.get('ended', False):
            await interaction.response.send_message(
                embed=EmbedFactory.error("Giveaway Ended", "This giveaway has already ended"),
                ephemeral=True
            )
            return

        # Check if user already entered
        participants = giveaway.get('participants', [])
        if interaction.user.id in participants:
            await interaction.response.send_message(
                embed=EmbedFactory.warning("Already Entered", "You have already entered this giveaway!"),
                ephemeral=True
            )
            return

        # Add user to participants
        await self.cog.db.db.giveaways.update_one(
            {"_id": self.giveaway_id},
            {"$push": {"participants": interaction.user.id}}
        )

        await interaction.response.send_message(
            embed=EmbedFactory.success("Entered!", f"You have been entered into the giveaway for **{giveaway['prize']}**!"),
            ephemeral=True
        )
        logger.info(f"{interaction.user} entered giveaway {self.giveaway_id}")


class Giveaways(commands.Cog):
    """Giveaway system cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.module_config = config.get('modules', {}).get('giveaways', {})
        # Start giveaway checker
        self.giveaway_task = self.bot.loop.create_task(self.check_giveaways())

    def cog_unload(self):
        """Cleanup on cog unload"""
        self.giveaway_task.cancel()

    async def check_giveaways(self):
        """Background task to check for ended giveaways"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                current_time = datetime.utcnow().timestamp()
                
                # Find giveaways that should end
                cursor = self.db.db.giveaways.find({
                    "end_time": {"$lte": current_time},
                    "ended": False
                })
                
                giveaways = await cursor.to_list(length=100)
                
                for giveaway in giveaways:
                    await self.end_giveaway(giveaway)
                
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error in giveaway checker: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def end_giveaway(self, giveaway: dict):
        """End a giveaway and pick winners"""
        try:
            guild = self.bot.get_guild(giveaway['guild_id'])
            if not guild:
                return

            channel = guild.get_channel(giveaway['channel_id'])
            if not channel:
                return

            participants = giveaway.get('participants', [])
            winners_count = giveaway.get('winners', 1)
            
            # Pick winners
            if len(participants) == 0:
                # No participants
                embed = EmbedFactory.warning(
                    "🎉 Giveaway Ended",
                    f"**Prize:** {giveaway['prize']}\n\n"
                    "No one entered the giveaway! 😢"
                )
                await channel.send(embed=embed)
            elif len(participants) < winners_count:
                # Not enough participants
                winners = participants
                winner_mentions = " ".join([f"<@{uid}>" for uid in winners])
                
                embed = EmbedFactory.success(
                    "🎉 Giveaway Ended",
                    f"**Prize:** {giveaway['prize']}\n\n"
                    f"**Winners:** {winner_mentions}\n\n"
                    "Not enough participants, so everyone wins!"
                )
                await channel.send(embed=embed)
            else:
                # Pick random winners
                winners = random.sample(participants, winners_count)
                winner_mentions = " ".join([f"<@{uid}>" for uid in winners])
                
                embed = EmbedFactory.success(
                    "🎉 Giveaway Ended",
                    f"**Prize:** {giveaway['prize']}\n\n"
                    f"**{'Winner' if winners_count == 1 else 'Winners'}:** {winner_mentions}\n\n"
                    "Congratulations! 🎊"
                )
                await channel.send(winner_mentions, embed=embed)

            # Mark as ended
            await self.db.db.giveaways.update_one(
                {"_id": giveaway['_id']},
                {"$set": {"ended": True, "winners_list": winners if participants else []}}
            )

            logger.info(f"Ended giveaway {giveaway['_id']} in {guild}")

        except Exception as e:
            logger.error(f"Error ending giveaway: {e}", exc_info=True)

    @app_commands.command(name="giveaway", description="Start a giveaway (Admin)")
    @app_commands.describe(
        prize="What are you giving away?",
        duration="How long should the giveaway last? (e.g., 1h, 30m, 1d)",
        winners="Number of winners (default: 1)"
    )
    @is_admin()
    async def start_giveaway(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str,
        winners: int = 1
    ):
        """Start a giveaway (ADMIN ONLY)"""
        if winners < 1 or winners > 20:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Winners", "Winners must be between 1 and 20"),
                ephemeral=True
            )
            return

        seconds = TimeConverter.parse(duration)
        if not seconds or seconds < 60:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Duration", "Duration must be at least 1 minute (e.g., 1h, 30m, 1d)"),
                ephemeral=True
            )
            return

        if seconds > 2592000:  # Max 30 days
            await interaction.response.send_message(
                embed=EmbedFactory.error("Duration Too Long", "Maximum giveaway duration is 30 days"),
                ephemeral=True
            )
            return

        end_time = datetime.utcnow().timestamp() + seconds
        end_timestamp = int(end_time)

        # Create giveaway in database
        giveaway_data = {
            "guild_id": interaction.guild.id,
            "channel_id": interaction.channel.id,
            "host_id": interaction.user.id,
            "prize": prize,
            "winners": winners,
            "end_time": end_time,
            "ended": False,
            "participants": []
        }

        result = await self.db.db.giveaways.insert_one(giveaway_data)
        giveaway_id = str(result.inserted_id)

        # Create giveaway embed
        embed = EmbedFactory.create(
            title="🎉 GIVEAWAY 🎉",
            description=f"**Prize:** {prize}\n\n"
                       f"**Winners:** {winners}\n"
                       f"**Hosted by:** {interaction.user.mention}\n"
                       f"**Ends:** <t:{end_timestamp}:R> (<t:{end_timestamp}:F>)\n\n"
                       "Click the button below to enter!",
            color=EmbedColor.SUCCESS
        )
        embed.set_footer(text=f"Ends at")
        embed.timestamp = datetime.utcfromtimestamp(end_time)

        view = GiveawayView(giveaway_id, self)
        
        await interaction.response.send_message("🎉 Giveaway started!", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)

        logger.info(f"{interaction.user} started giveaway in {interaction.guild}")

    @app_commands.command(name="gend", description="End a giveaway early (Admin)")
    @app_commands.describe(message_id="Message ID of the giveaway")
    @is_admin()
    async def end_giveaway_early(self, interaction: discord.Interaction, message_id: str):
        """End a giveaway early (ADMIN ONLY)"""
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid ID", "Please provide a valid message ID"),
                ephemeral=True
            )
            return

        # Find giveaway by channel and approximate time
        giveaway = await self.db.db.giveaways.find_one({
            "guild_id": interaction.guild.id,
            "channel_id": interaction.channel.id,
            "ended": False
        })

        if not giveaway:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not Found", "No active giveaway found in this channel"),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=EmbedFactory.success("Ending Giveaway", "Ending the giveaway now..."),
            ephemeral=True
        )

        await self.end_giveaway(giveaway)

    @app_commands.command(name="greroll", description="Reroll giveaway winners (Admin)")
    @app_commands.describe(message_id="Message ID of the giveaway")
    @is_admin()
    async def reroll_giveaway(self, interaction: discord.Interaction, message_id: str):
        """Reroll giveaway winners (ADMIN ONLY)"""
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid ID", "Please provide a valid message ID"),
                ephemeral=True
            )
            return

        # Find ended giveaway
        giveaway = await self.db.db.giveaways.find_one({
            "guild_id": interaction.guild.id,
            "ended": True
        })

        if not giveaway:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not Found", "No ended giveaway found"),
                ephemeral=True
            )
            return

        participants = giveaway.get('participants', [])
        winners_count = giveaway.get('winners', 1)

        if len(participants) == 0:
            await interaction.response.send_message(
                embed=EmbedFactory.error("No Participants", "This giveaway had no participants"),
                ephemeral=True
            )
            return

        # Pick new winners
        new_winners = random.sample(participants, min(winners_count, len(participants)))
        winner_mentions = " ".join([f"<@{uid}>" for uid in new_winners])

        embed = EmbedFactory.success(
            "🎉 Giveaway Rerolled",
            f"**Prize:** {giveaway['prize']}\n\n"
            f"**New {'Winner' if winners_count == 1 else 'Winners'}:** {winner_mentions}\n\n"
            "Congratulations! 🎊"
        )

        await interaction.response.send_message(winner_mentions, embed=embed)
        logger.info(f"{interaction.user} rerolled giveaway in {interaction.guild}")


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(Giveaways(bot, bot.db, bot.config))
