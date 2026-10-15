"""Explicit domain-specific failures at pipeline boundaries."""


class MarketStreamError(Exception):
    """Base exception for expected market data pipeline failures."""


class SchemaValidationError(MarketStreamError, ValueError):
    """Input schema or market data invariant violation."""


class AlignmentError(MarketStreamError, ValueError):
    """Time alignment cannot be completed unambiguously."""


class StorageError(MarketStreamError, OSError):
    """Data product writing failed."""
