"""
Unit tests for utility functions
"""

import pytest
from utils.converters import TimeConverter, NumberConverter, MessageConverter
from utils.constants import calculate_level_xp


def test_time_parser():
    """Test time string parsing"""
    assert TimeConverter.parse("1h") == 3600
    assert TimeConverter.parse("30m") == 1800
    assert TimeConverter.parse("1d") == 86400
    assert TimeConverter.parse("1h30m") == 5400
    assert TimeConverter.parse("invalid") is None


def test_time_formatter():
    """Test time formatting"""
    assert TimeConverter.format_seconds(3600) == "1h"
    assert TimeConverter.format_seconds(90) == "1m 30s"
    assert TimeConverter.format_seconds(86400) == "1d"


def test_number_parser():
    """Test number parsing with suffixes"""
    assert NumberConverter.parse_number("1k") == 1000
    assert NumberConverter.parse_number("2.5m") == 2500000
    assert NumberConverter.parse_number("1b") == 1000000000
    assert NumberConverter.parse_number("500") == 500
    assert NumberConverter.parse_number("invalid") is None


def test_number_formatter():
    """Test number formatting"""
    assert NumberConverter.format_number(1000) == "1,000"
    assert NumberConverter.format_number(1000000) == "1,000,000"


def test_message_truncate():
    """Test message truncation"""
    long_text = "a" * 3000
    truncated = MessageConverter.truncate(long_text, max_length=100)
    assert len(truncated) <= 100
    assert truncated.endswith("...")


def test_level_xp_calculation():
    """Test XP calculation for levels"""
    assert calculate_level_xp(1) > 0
    assert calculate_level_xp(10) > calculate_level_xp(5)
    assert calculate_level_xp(0) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
