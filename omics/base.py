"""Protocols shared by optional omics implementations."""

from typing import Protocol

from bioreport.registry import Module, Registry


class OmicsPackage(Protocol):
    """A package that contributes modules to the core registry."""

    def register(self, registry: Registry) -> None:
        ...


__all__ = ["Module", "Registry", "OmicsPackage"]
