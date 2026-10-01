"""Failures shared by source listing implementations and their API adapter."""


class SourceSearchError(Exception):
    """A requested listing could not be fetched or validated."""


class SourceSearchUnavailable(SourceSearchError):
    """The selected source is disabled or has no search implementation."""
