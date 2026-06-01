"""MCP clients (REST adapters) package."""

from .courtlistener import CourtListenerClient
from .eurlex import EURLexClient
from .eurovoc import EuroVocClient

__all__ = ["CourtListenerClient", "EURLexClient", "EuroVocClient"]
