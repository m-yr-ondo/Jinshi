"""Utilities package for Logiq"""

from .logger import setup_logger, BotLogger
from .embeds import EmbedFactory, EmbedColor
from .permissions import (
    is_admin, is_moderator, has_role,
    bot_has_permissions, is_guild_owner,
    PermissionChecker
)
from .converters import TimeConverter, MessageConverter, NumberConverter
from .constants import *

__all__ = [
    'setup_logger',
    'BotLogger',
    'EmbedFactory',
    'EmbedColor',
    'is_admin',
    'is_moderator',
    'has_role',
    'bot_has_permissions',
    'is_guild_owner',
    'PermissionChecker',
    'TimeConverter',
    'MessageConverter',
    'NumberConverter'
]
