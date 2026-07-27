"""
Constants and configuration values for Logiq
"""

from typing import Dict, Any

# Bot Information
BOT_NAME = "Logiq"
BOT_VERSION = "1.0.0"
BOT_DESCRIPTION = "AI-enhanced Discord bot for community management"
BOT_GITHUB = "https://github.com/yourusername/Logiq"

# Emoji Constants
EMOJIS = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "loading": "⏳",
    "verified": "✓",
    "ai": "🤖",
    "level_up": "🎉",
    "coin": "💎",
    "trophy": "🏆",
    "ticket": "🎫",
    "lock": "🔒",
    "unlock": "🔓",
    "ban": "🔨",
    "mute": "🔇",
    "kick": "👢"
}

# Leveling Constants
LEVELING = {
    "xp_per_message": 10,
    "xp_cooldown": 60,  # seconds
    "base_xp": 100,
    "xp_multiplier": 1.5
}

def calculate_level_xp(level: int) -> int:
    """Calculate XP required for level"""
    return int(LEVELING["base_xp"] * (level ** LEVELING["xp_multiplier"]))

# Economy Constants
ECONOMY = {
    "starting_balance": 1000,
    "daily_reward": 100,
    "daily_cooldown": 86400,  # 24 hours
    "currency_name": "ProgrammiCoin",
    "currency_symbol": "💎",
    "max_bet": 10000,
    "min_bet": 10
}

# Moderation Constants
MODERATION = {
    "max_warnings": 3,
    "auto_ban_warnings": 5,
    "mute_role_name": "Muted",
    "max_mentions": 5,
    "max_emojis": 10,
    "spam_threshold": 5,  # messages
    "spam_interval": 5    # seconds
}

# Time Limits
TIME_LIMITS = {
    "mute_max": 2419200,      # 28 days
    "timeout_max": 2419200,   # 28 days
    "reminder_max": 31536000  # 1 year
}

# Pagination
PAGINATION = {
    "items_per_page": 10,
    "leaderboard_size": 10,
    "timeout": 60  # seconds
}

# AI Settings
AI_SETTINGS = {
    "max_tokens": 500,
    "temperature": 0.7,
    "max_history": 10,
    "toxicity_threshold": 0.7,
    "spam_threshold": 0.8
}

# Music Settings
MUSIC = {
    "max_queue_size": 100,
    "default_volume": 50,
    "max_song_length": 600,  # 10 minutes
    "search_results": 5
}

# Ticket Settings
TICKETS = {
    "max_open_tickets": 3,
    "categories": [
        "General Support",
        "Technical Issue",
        "Report User",
        "Suggestion",
        "Other"
    ]
}

# Game Settings
GAMES = {
    "trivia_time": 30,        # seconds
    "trivia_categories": ["general", "programming", "science", "history"],
    "blackjack_starting_chips": 100,
    "roulette_payouts": {
        "number": 35,
        "color": 1,
        "odd_even": 1,
        "high_low": 1
    }
}

# Rate Limits
RATE_LIMITS: Dict[str, Dict[str, Any]] = {
    "commands": {
        "rate": 5,
        "per": 60  # 5 commands per minute
    },
    "messages": {
        "rate": 10,
        "per": 10  # 10 messages per 10 seconds
    }
}

# Embed Limits
EMBED_LIMITS = {
    "title": 256,
    "description": 4096,
    "fields": 25,
    "field_name": 256,
    "field_value": 1024,
    "footer": 2048,
    "author": 256
}

# File Paths
PATHS = {
    "logs": "logs",
    "data": "data",
    "temp": "temp",
    "assets": "assets"
}

# API Endpoints
API_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1"
}

# Status Messages
STATUS_MESSAGES = [
    "Managing your community",
    "Powered by AI",
    "Type /help",
    "Serving {guild_count} servers",
    "Moderating {member_count} members"
]
