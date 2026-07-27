"""
Embed utilities for Logiq
Creates consistent, themed embeds
"""

import discord
from typing import Optional, List, Dict, Any
from datetime import datetime


class EmbedColor:
    """Color palette for embeds"""
    PRIMARY = 0x5865F2  # Discord Blurple
    SUCCESS = 0x57F287  # Green
    WARNING = 0xFEE75C  # Yellow
    ERROR = 0xED4245    # Red
    INFO = 0x5865F2     # Blue
    PREMIUM = 0xF47FFF  # Pink
    LEVELING = 0xFEE75C  # Gold
    ECONOMY = 0x57F287   # Green
    AI = 0x00D9FF        # Cyan


class EmbedFactory:
    """Factory for creating themed embeds"""

    @staticmethod
    def create(
        title: Optional[str] = None,
        description: Optional[str] = None,
        color: int = EmbedColor.PRIMARY,
        footer: Optional[str] = None,
        thumbnail: Optional[str] = None,
        image: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        timestamp: bool = True
    ) -> discord.Embed:
        """
        Create a custom embed

        Args:
            title: Embed title
            description: Embed description
            color: Embed color (hex)
            footer: Footer text
            thumbnail: Thumbnail URL
            image: Image URL
            fields: List of field dictionaries
            timestamp: Whether to add timestamp

        Returns:
            Configured Discord embed
        """
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.utcnow() if timestamp else None
        )

        if footer:
            embed.set_footer(text=footer)

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        if image:
            embed.set_image(url=image)

        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get("name", ""),
                    value=field.get("value", ""),
                    inline=field.get("inline", True)
                )

        return embed

    @staticmethod
    def success(title: str, description: str) -> discord.Embed:
        """Create success embed"""
        return EmbedFactory.create(
            title=f"✅ {title}",
            description=description,
            color=EmbedColor.SUCCESS
        )

    @staticmethod
    def error(title: str, description: str) -> discord.Embed:
        """Create error embed"""
        return EmbedFactory.create(
            title=f"❌ {title}",
            description=description,
            color=EmbedColor.ERROR
        )

    @staticmethod
    def warning(title: str, description: str) -> discord.Embed:
        """Create warning embed"""
        return EmbedFactory.create(
            title=f"⚠️ {title}",
            description=description,
            color=EmbedColor.WARNING
        )

    @staticmethod
    def info(title: str, description: str) -> discord.Embed:
        """Create info embed"""
        return EmbedFactory.create(
            title=f"ℹ️ {title}",
            description=description,
            color=EmbedColor.INFO
        )

    @staticmethod
    def ai_response(message: str, model: str = "AI") -> discord.Embed:
        """Create AI response embed"""
        return EmbedFactory.create(
            title="🤖 AI Response",
            description=message,
            color=EmbedColor.AI,
            footer=f"Powered by {model}"
        )

    @staticmethod
    def level_up(user: discord.Member, new_level: int, xp: int) -> discord.Embed:
        """Create level up embed"""
        return EmbedFactory.create(
            title="🎉 Level Up!",
            description=f"{user.mention} just reached **Level {new_level}**!",
            color=EmbedColor.LEVELING,
            thumbnail=user.display_avatar.url,
            fields=[
                {"name": "Level", "value": str(new_level), "inline": True},
                {"name": "Total XP", "value": str(xp), "inline": True}
            ]
        )

    @staticmethod
    def rank_card(user: discord.Member, level: int, xp: int, rank: int, next_level_xp: int) -> discord.Embed:
        """Create rank card embed"""
        progress = (xp % next_level_xp) / next_level_xp * 100
        progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))

        return EmbedFactory.create(
            title=f"📊 Rank Card - {user.display_name}",
            color=EmbedColor.LEVELING,
            thumbnail=user.display_avatar.url,
            fields=[
                {"name": "Rank", "value": f"#{rank}", "inline": True},
                {"name": "Level", "value": str(level), "inline": True},
                {"name": "XP", "value": f"{xp % next_level_xp}/{next_level_xp}", "inline": True},
                {"name": "Progress", "value": f"{progress_bar} {progress:.1f}%", "inline": False}
            ]
        )

    @staticmethod
    def economy_balance(user: discord.Member, balance: int, currency_symbol: str = "💎") -> discord.Embed:
        """Create balance embed"""
        return EmbedFactory.create(
            title=f"{currency_symbol} Balance",
            description=f"{user.mention}'s balance",
            color=EmbedColor.ECONOMY,
            thumbnail=user.display_avatar.url,
            fields=[
                {"name": "Amount", "value": f"{currency_symbol} {balance:,}", "inline": False}
            ]
        )

    @staticmethod
    def moderation_action(
        action: str,
        user: discord.Member,
        moderator: discord.Member,
        reason: str
    ) -> discord.Embed:
        """Create moderation action embed"""
        return EmbedFactory.create(
            title=f"🔨 {action}",
            description=f"{user.mention} has been {action.lower()}",
            color=EmbedColor.WARNING,
            fields=[
                {"name": "User", "value": f"{user.mention} ({user.id})", "inline": True},
                {"name": "Moderator", "value": moderator.mention, "inline": True},
                {"name": "Reason", "value": reason, "inline": False}
            ]
        )

    @staticmethod
    def verification_prompt() -> discord.Embed:
        """Create verification prompt embed"""
        return EmbedFactory.create(
            title="🔐 Verification Required",
            description="Click the button below to verify and gain access to the server.",
            color=EmbedColor.PRIMARY,
            footer="Complete verification to unlock all channels"
        )

    @staticmethod
    def ticket_created(ticket_id: str, category: str) -> discord.Embed:
        """Create ticket created embed"""
        return EmbedFactory.create(
            title="🎫 Ticket Created",
            description="Your support ticket has been created!",
            color=EmbedColor.SUCCESS,
            fields=[
                {"name": "Ticket ID", "value": ticket_id, "inline": True},
                {"name": "Category", "value": category, "inline": True}
            ]
        )

    @staticmethod
    def leaderboard(
        title: str,
        entries: List[Dict[str, Any]],
        field_name: str = "Rank",
        color: int = EmbedColor.LEVELING
    ) -> discord.Embed:
        """Create leaderboard embed"""
        description = ""
        for i, entry in enumerate(entries[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            description += f"{medal} <@{entry['user_id']}> - **{entry.get(field_name, 0):,}**\n"

        return EmbedFactory.create(
            title=f"🏆 {title}",
            description=description or "No entries yet",
            color=color
        )
