"""
Datetime Utilities Module

Utilities for converting between local datetime formats and ISO 8601
format expected by Canvas API.
"""

import logging
from datetime import datetime
from typing import Optional, Union
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python < 3.9 fallback
    from backports.zoneinfo import ZoneInfo

logger = logging.getLogger("canvas_author.datetime_utils")

# Default timezone for course (Eastern Time)
DEFAULT_TIMEZONE = "America/New_York"


def convert_to_iso8601(
    dt_string: Optional[str],
    timezone: str = DEFAULT_TIMEZONE,
    use_utc: bool = False
) -> Optional[str]:
    """
    Convert a datetime string to ISO 8601 format for Canvas API.

    Canvas API expects datetime strings in ISO 8601 format with timezone
    information. This function converts strings like "2026-01-16 23:59:00"
    to ISO 8601 format like "2026-01-17T04:59:00Z" (UTC) or
    "2026-01-16T23:59:00-05:00" (local timezone).

    Args:
        dt_string: Datetime string in format "YYYY-MM-DD HH:MM:SS" or ISO 8601
        timezone: IANA timezone name (default: "America/New_York")
        use_utc: If True, convert to UTC with 'Z' suffix (default: True)

    Returns:
        ISO 8601 formatted datetime string, or None if input is None

    Examples:
        >>> convert_to_iso8601("2026-01-16 23:59:00")
        "2026-01-17T04:59:00Z"

        >>> convert_to_iso8601("2026-01-16 23:59:00", use_utc=False)
        "2026-01-16T23:59:00-05:00"

        >>> convert_to_iso8601("2026-01-16T23:59:00-05:00")
        "2026-01-17T04:59:00Z"
    """
    if not dt_string:
        return None

    # If already in ISO 8601 format (has T and timezone), return as-is
    if 'T' in dt_string and ('+' in dt_string or dt_string.endswith('Z') or '-' in dt_string[-6:]):
        logger.debug(f"Datetime already in ISO 8601 format: {dt_string}")
        # If we want UTC and it's not already UTC, convert it
        if use_utc and not dt_string.endswith('Z'):
            try:
                dt = datetime.fromisoformat(dt_string)
                utc_dt = dt.astimezone(ZoneInfo('UTC'))
                iso_string = utc_dt.isoformat().replace('+00:00', 'Z')
                logger.debug(f"Converted to UTC: {iso_string}")
                return iso_string
            except Exception as e:
                logger.warning(f"Failed to convert to UTC: {e}")
                return dt_string
        return dt_string

    try:
        # Parse the naive datetime string
        naive_dt = datetime.strptime(dt_string.strip(), '%Y-%m-%d %H:%M:%S')

        # Add timezone information
        tz = ZoneInfo(timezone)
        aware_dt = naive_dt.replace(tzinfo=tz)

        if use_utc:
            # Convert to UTC
            utc_dt = aware_dt.astimezone(ZoneInfo('UTC'))
            iso_string = utc_dt.isoformat().replace('+00:00', 'Z')
        else:
            # Keep in local timezone
            iso_string = aware_dt.isoformat()

        logger.debug(f"Converted '{dt_string}' to ISO 8601: {iso_string}")
        return iso_string

    except ValueError as e:
        logger.warning(f"Failed to parse datetime '{dt_string}': {e}. Returning as-is.")
        # Return as-is if we can't parse it - let Canvas API handle the error
        return dt_string


def convert_to_datetime(
    dt_string: Optional[str],
    timezone: str = DEFAULT_TIMEZONE
) -> Optional[datetime]:
    """
    Convert a datetime string to a timezone-aware datetime object.

    Canvas API can accept datetime objects instead of ISO 8601 strings.
    This function converts strings like "2026-01-16 23:59:00" to
    timezone-aware datetime objects.

    Args:
        dt_string: Datetime string in format "YYYY-MM-DD HH:MM:SS" or ISO 8601
        timezone: IANA timezone name (default: "America/New_York")

    Returns:
        Timezone-aware datetime object, or None if input is None

    Examples:
        >>> dt = convert_to_datetime("2026-01-16 23:59:00")
        >>> dt.tzinfo
        ZoneInfo(key='America/New_York')
    """
    if not dt_string:
        return None

    # If already a datetime object, return it
    if isinstance(dt_string, datetime):
        return dt_string

    # If ISO 8601 format, parse it
    if 'T' in dt_string:
        try:
            if dt_string.endswith('Z'):
                dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(dt_string)
            logger.debug(f"Parsed ISO 8601 datetime: {dt}")
            return dt
        except ValueError as e:
            logger.warning(f"Failed to parse ISO 8601 datetime '{dt_string}': {e}")

    # Try parsing as simple format
    try:
        naive_dt = datetime.strptime(dt_string.strip(), '%Y-%m-%d %H:%M:%S')
        tz = ZoneInfo(timezone)
        aware_dt = naive_dt.replace(tzinfo=tz)
        logger.debug(f"Converted '{dt_string}' to datetime: {aware_dt}")
        return aware_dt
    except ValueError as e:
        logger.warning(f"Failed to parse datetime '{dt_string}': {e}")
        return None


def convert_from_iso8601(
    iso_string: Optional[str],
    timezone: str = DEFAULT_TIMEZONE
) -> Optional[str]:
    """
    Convert ISO 8601 datetime string to simple local format.

    Converts from Canvas API format like "2026-01-16T23:59:00-05:00"
    to simple format like "2026-01-16 23:59:00" in the specified timezone.

    Args:
        iso_string: ISO 8601 formatted datetime string
        timezone: IANA timezone name for conversion (default: "America/New_York")

    Returns:
        Simple datetime string "YYYY-MM-DD HH:MM:SS", or None if input is None

    Examples:
        >>> convert_from_iso8601("2026-01-16T23:59:00-05:00")
        "2026-01-16 23:59:00"
    """
    if not iso_string or iso_string == "None":
        return None

    try:
        # Parse ISO 8601 string
        # Handle both 'Z' suffix and timezone offsets
        if iso_string.endswith('Z'):
            dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(iso_string)

        # Convert to target timezone
        tz = ZoneInfo(timezone)
        local_dt = dt.astimezone(tz)

        # Format as simple string
        simple_string = local_dt.strftime('%Y-%m-%d %H:%M:%S')

        logger.debug(f"Converted ISO 8601 '{iso_string}' to local: {simple_string}")
        return simple_string

    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse ISO 8601 datetime '{iso_string}': {e}")
        return iso_string
