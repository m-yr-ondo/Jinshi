"""
Type converters and parsers for Logiq
"""

import re
from typing import Optional
from datetime import datetime, timedelta


class TimeConverter:
    """Convert time strings to seconds"""

    TIME_REGEX = re.compile(r"(\d+)\s*([smhdw])")
    TIME_UNITS = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }

    @classmethod
    def parse(cls, time_string: str) -> Optional[int]:
        """
        Parse time string to seconds

        Args:
            time_string: Time string (e.g., "1h", "30m", "2d")

        Returns:
            Total seconds or None if invalid
        """
        time_string = time_string.lower().strip()
        matches = cls.TIME_REGEX.findall(time_string)

        if not matches:
            return None

        total_seconds = 0
        for amount, unit in matches:
            total_seconds += int(amount) * cls.TIME_UNITS.get(unit, 0)

        return total_seconds if total_seconds > 0 else None

    @classmethod
    def format_seconds(cls, seconds: int) -> str:
        """
        Format seconds to readable string

        Args:
            seconds: Number of seconds

        Returns:
            Formatted string (e.g., "1h 30m")
        """
        if seconds < 60:
            return f"{seconds}s"

        parts = []
        for unit, divisor in [('w', 604800), ('d', 86400), ('h', 3600), ('m', 60)]:
            if seconds >= divisor:
                value = seconds // divisor
                parts.append(f"{value}{unit}")
                seconds %= divisor

        if seconds > 0:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    @classmethod
    def to_datetime(cls, time_string: str) -> Optional[datetime]:
        """
        Convert time string to future datetime

        Args:
            time_string: Time string

        Returns:
            Future datetime or None
        """
        seconds = cls.parse(time_string)
        if seconds:
            return datetime.utcnow() + timedelta(seconds=seconds)
        return None


class MessageConverter:
    """Convert and format messages"""

    @staticmethod
    def truncate(text: str, max_length: int = 2000, suffix: str = "...") -> str:
        """
        Truncate text to max length

        Args:
            text: Input text
            max_length: Maximum length
            suffix: Suffix to add when truncated

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix

    @staticmethod
    def escape_markdown(text: str) -> str:
        """
        Escape markdown characters

        Args:
            text: Input text

        Returns:
            Escaped text
        """
        special_chars = ['*', '_', '`', '~', '|', '>', '#']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    @staticmethod
    def format_list(items: list, numbered: bool = False) -> str:
        """
        Format list as string

        Args:
            items: List of items
            numbered: Use numbered list

        Returns:
            Formatted string
        """
        if numbered:
            return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))
        return "\n".join(f"• {item}" for item in items)


class NumberConverter:
    """Convert and format numbers"""

    @staticmethod
    def format_number(number: int) -> str:
        """
        Format number with commas

        Args:
            number: Input number

        Returns:
            Formatted string
        """
        return f"{number:,}"

    @staticmethod
    def parse_number(text: str) -> Optional[int]:
        """
        Parse number from text (handles k, m, b suffixes)

        Args:
            text: Input text

        Returns:
            Parsed number or None
        """
        text = text.lower().strip()
        multipliers = {'k': 1000, 'm': 1000000, 'b': 1000000000}

        for suffix, multiplier in multipliers.items():
            if text.endswith(suffix):
                try:
                    return int(float(text[:-1]) * multiplier)
                except ValueError:
                    return None

        try:
            return int(text)
        except ValueError:
            return None

    @staticmethod
    def format_percentage(value: float, decimals: int = 1) -> str:
        """
        Format percentage

        Args:
            value: Percentage value (0-100)
            decimals: Number of decimal places

        Returns:
            Formatted percentage string
        """
        return f"{value:.{decimals}f}%"
