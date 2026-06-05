"""Base scraper — all source-specific scrapers inherit from this."""
from abc import ABC, abstractmethod


class BaseScraper(ABC):
    """Handles deduplication, AI extraction, logging, error handling.
    Subclasses only implement fetch_listings()."""

    source_name: str = ""

    @abstractmethod
    async def fetch_listings(self) -> list[dict]:
        """Fetch raw listing data from the source. Return list of dicts."""
        ...
