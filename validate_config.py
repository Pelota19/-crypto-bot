#!/usr/bin/env python3
"""
Configuration validator for the crypto bot.
Checks that all required environment variables and settings are properly configured.
"""
import os
from src.config import (
    MODE,
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    STARTING_BALANCE_USDT,
    POSITION_SIZE_PERCENT,
    DAILY_PROFIT_TARGET_USD,
    MAX_DAILY_LOSS_USD,
)


def validate_config():
    """Validate configuration and return list of issues."""
    issues = []
    warnings = []

    # Check mode
    if MODE not in ["paper", "live"]:
        issues.append(f"MODE must be 'paper' or 'live', got: {MODE}")

    # Check Binance API credentials (only warn if empty in paper mode, error in live mode)
    if not BINANCE_API_KEY:
        msg = "BINANCE_API_KEY is not set"
        if MODE == "live":
            issues.append(msg)
        else:
            warnings.append(msg + " (OK for paper trading)")

    if not BINANCE_API_SECRET:
        msg = "BINANCE_API_SECRET is not set"
        if MODE == "live":
            issues.append(msg)
        else:
            warnings.append(msg + " (OK for paper trading)")

    # Check Telegram configuration (optional)
    if not TELEGRAM_TOKEN:
        warnings.append("TELEGRAM_TOKEN is not set (notifications disabled)")
    if not TELEGRAM_CHAT_ID:
        warnings.append("TELEGRAM_CHAT_ID is not set (notifications disabled)")

    # Check financial settings
    if STARTING_BALANCE_USDT <= 0:
        issues.append(
            f"STARTING_BALANCE_USDT must be positive, got: {STARTING_BALANCE_USDT}"
        )

    if POSITION_SIZE_PERCENT <= 0 or POSITION_SIZE_PERCENT > 1:
        issues.append(
            f"POSITION_SIZE_PERCENT must be between 0 and 1, got: {POSITION_SIZE_PERCENT}"
        )

    if DAILY_PROFIT_TARGET_USD <= 0:
        issues.append(
            f"DAILY_PROFIT_TARGET_USD must be positive, got: {DAILY_PROFIT_TARGET_USD}"
        )

    if MAX_DAILY_LOSS_USD <= 0:
        issues.append(f"MAX_DAILY_LOSS_USD must be positive, got: {MAX_DAILY_LOSS_USD}")

    # Check if .env file exists
    if not os.path.exists(".env"):
        warnings.append(".env file not found (using defaults)")

    return issues, warnings


def print_validation_report():
    """Print validation report to console."""
    issues, warnings = validate_config()

    print("🔧 Configuration Validation Report")
    print("=" * 40)

    if issues:
        print("❌ Critical Issues:")
        for issue in issues:
            print(f"  • {issue}")
        print()

    if warnings:
        print("⚠️  Warnings:")
        for warning in warnings:
            print(f"  • {warning}")
        print()

    if not issues and not warnings:
        print("✅ Configuration is valid!")
    elif not issues:
        print("✅ Configuration is valid (with warnings)")
    else:
        print("❌ Configuration has critical issues that must be fixed")

    return len(issues) == 0


if __name__ == "__main__":
    valid = print_validation_report()
    exit(0 if valid else 1)
