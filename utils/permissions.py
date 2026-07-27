"""
Permission checks and utilities for Logiq
"""

import discord
from discord import app_commands
from typing import Optional, Callable
from functools import wraps


def is_admin():
    """Check if user has administrator permission"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


def is_moderator():
    """Check if user has moderation permissions"""
    async def predicate(interaction: discord.Interaction) -> bool:
        perms = interaction.user.guild_permissions
        return any([
            perms.administrator,
            perms.kick_members,
            perms.ban_members,
            perms.manage_messages
        ])
    return app_commands.check(predicate)


def has_role(role_id: int):
    """Check if user has specific role"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return any(role.id == role_id for role in interaction.user.roles)
    return app_commands.check(predicate)


def bot_has_permissions(**perms):
    """Check if bot has required permissions"""
    async def predicate(interaction: discord.Interaction) -> bool:
        bot_perms = interaction.guild.me.guild_permissions
        return all(getattr(bot_perms, perm, False) for perm in perms)
    return app_commands.check(predicate)


def is_guild_owner():
    """Check if user is guild owner"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == interaction.guild.owner_id
    return app_commands.check(predicate)


class PermissionChecker:
    """Utility class for permission checking"""

    @staticmethod
    def check_hierarchy(
        executor: discord.Member,
        target: discord.Member
    ) -> bool:
        """
        Check if executor is higher in role hierarchy than target

        Args:
            executor: Member executing action
            target: Member being targeted

        Returns:
            True if executor can act on target
        """
        if executor.guild.owner_id == executor.id:
            return True
        if target.guild.owner_id == target.id:
            return False
        return executor.top_role > target.top_role

    @staticmethod
    def can_moderate(
        moderator: discord.Member,
        target: discord.Member
    ) -> tuple[bool, Optional[str]]:
        """
        Check if moderator can moderate target

        Args:
            moderator: Moderator member
            target: Target member

        Returns:
            Tuple of (can_moderate, error_message)
        """
        if moderator.id == target.id:
            return False, "You cannot moderate yourself"

        if target.guild.owner_id == target.id:
            return False, "You cannot moderate the server owner"

        if not PermissionChecker.check_hierarchy(moderator, target):
            return False, "You cannot moderate someone with a higher or equal role"

        return True, None

    @staticmethod
    def has_permission(
        member: discord.Member,
        permission: str
    ) -> bool:
        """
        Check if member has specific permission

        Args:
            member: Member to check
            permission: Permission name

        Returns:
            True if member has permission
        """
        return getattr(member.guild_permissions, permission, False)

    @staticmethod
    def get_missing_permissions(
        member: discord.Member,
        required_permissions: list[str]
    ) -> list[str]:
        """
        Get list of missing permissions

        Args:
            member: Member to check
            required_permissions: List of required permission names

        Returns:
            List of missing permissions
        """
        missing = []
        for perm in required_permissions:
            if not getattr(member.guild_permissions, perm, False):
                missing.append(perm)
        return missing
