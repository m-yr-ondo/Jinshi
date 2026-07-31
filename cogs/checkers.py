"""Public checkers statistics and leaderboard commands."""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from database.db_manager import DatabaseManager
from utils.embeds import EmbedFactory, EmbedColor


class Checkers(commands.Cog):
    """Jinshi Checkers standings."""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.module_config = config.get("modules", {}).get("checkers", {})

    @app_commands.command(
        name="checkersleaderboard",
        description="View this server's checkers standings"
    )
    @app_commands.guild_only()
    async def checkers_leaderboard(self, interaction: discord.Interaction):
        standings = await self.db.get_checkers_leaderboard(interaction.guild.id, limit=10)
        if not standings:
            await interaction.response.send_message(
                embed=EmbedFactory.info(
                    "No Checkers Games Yet",
                    "Complete a Jinshi Checkers match to claim the first spot."
                )
            )
            return

        lines = []
        for rank, entry in enumerate(standings, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"`{rank}.`")
            lines.append(
                f"{medal} <@{entry['user_id']}> — **{entry.get('points', 0)} pts**\n"
                f"　{entry.get('wins', 0)}W · {entry.get('draws', 0)}D · "
                f"{entry.get('losses', 0)}L · Best streak: {entry.get('best_win_streak', 0)}"
            )

        embed = EmbedFactory.create(
            title="♛ Checkers Leaderboard",
            description="\n".join(lines),
            color=EmbedColor.ECONOMY,
            footer="Scoring: win 3 · draw 1 · loss 0"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="checkersstats",
        description="View checkers statistics for yourself or another member"
    )
    @app_commands.describe(user="Member to inspect (defaults to you)")
    @app_commands.guild_only()
    async def checkers_stats(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None
    ):
        target = user or interaction.user
        stats = await self.db.get_checkers_stats(interaction.guild.id, target.id)
        if not stats:
            await interaction.response.send_message(
                embed=EmbedFactory.info(
                    "No Checkers Record",
                    f"{target.mention} hasn't completed a match yet."
                )
            )
            return

        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        draws = stats.get("draws", 0)
        games = wins + losses + draws
        win_rate = (wins / games * 100) if games else 0
        embed = EmbedFactory.create(
            title=f"♛ Checkers Stats — {target.display_name}",
            color=EmbedColor.ECONOMY,
            thumbnail=target.display_avatar.url,
            fields=[
                {"name": "Points", "value": f"**{stats.get('points', 0)}**", "inline": True},
                {"name": "Record", "value": f"**{wins}W · {draws}D · {losses}L**", "inline": True},
                {"name": "Win rate", "value": f"**{win_rate:.1f}%**", "inline": True},
                {
                    "name": "Win streak",
                    "value": (
                        f"Current: **{stats.get('current_win_streak', 0)}**\n"
                        f"Best: **{stats.get('best_win_streak', 0)}**"
                    ),
                    "inline": True
                },
                {
                    "name": "Losing streak",
                    "value": (
                        f"Current: **{stats.get('current_loss_streak', 0)}**\n"
                        f"Worst: **{stats.get('worst_loss_streak', 0)}**"
                    ),
                    "inline": True
                },
                {"name": "Games played", "value": f"**{games}**", "inline": True}
            ],
            footer="Win 3 points · Draw 1 point · Loss 0 points"
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Checkers(bot, bot.db, bot.config))
