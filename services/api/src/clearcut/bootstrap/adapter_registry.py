"""Explicit adapter registry for typed external provider ports."""
from typing import Any


class AdapterRegistry:
    def __init__(self) -> None:
        self._storage_adapter: Any | None = None
        self._identity_adapter: Any | None = None
        self._search_adapter: Any | None = None
        self._ai_adapter: Any | None = None
        self._frozen: bool = False

    def register_storage(self, adapter: Any) -> None:
        if self._frozen:
            raise RuntimeError("Cannot register storage adapter: registry is frozen")
        self._storage_adapter = adapter

    def register_identity(self, adapter: Any) -> None:
        if self._frozen:
            raise RuntimeError("Cannot register identity adapter: registry is frozen")
        self._identity_adapter = adapter

    def register_search(self, adapter: Any) -> None:
        if self._frozen:
            raise RuntimeError("Cannot register search adapter: registry is frozen")
        self._search_adapter = adapter

    def register_ai(self, adapter: Any) -> None:
        if self._frozen:
            raise RuntimeError("Cannot register AI adapter: registry is frozen")
        self._ai_adapter = adapter

    def freeze(self) -> None:
        self._frozen = True

    def is_frozen(self) -> bool:
        return self._frozen
