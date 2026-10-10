"""Module registry shared by the core engine and omics packages."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Module:
    id: str
    qmd: str
    title: str
    category: str = "general"
    required_inputs: tuple[str, ...] = ()
    default_params: dict = field(default_factory=dict)
    package_root: str = ""
    parent: str | None = None
    setup_qmd: str | None = None
    optional_inputs: tuple[str, ...] = ()


class Registry:
    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}
        self._aliases: dict[str, str] = {}
        self._defaults: list[str] = []

    def register_omics(
        self,
        prefix: str,
        modules: list[Module],
        *,
        aliases: dict[str, str] | None = None,
        defaults: tuple[str, ...] = (),
    ) -> None:
        for module in modules:
            if not module.id.startswith(f"{prefix}."):
                raise ValueError(f"Module {module.id!r} is outside namespace {prefix!r}")
            if module.id in self._modules:
                raise ValueError(f"Duplicate module ID: {module.id}")
            self._modules[module.id] = module
        for alias, target in (aliases or {}).items():
            if target not in self._modules:
                raise ValueError(f"Alias {alias!r} targets unknown module {target!r}")
            self._aliases[alias] = target
        self._defaults.extend(defaults)

    def canonical(self, module_id: str) -> str:
        seen = set()
        while module_id in self._aliases:
            if module_id in seen:
                raise ValueError(f"Circular module alias: {module_id}")
            seen.add(module_id)
            module_id = self._aliases[module_id]
        return module_id

    def resolve(self, module_id: str) -> Module:
        try:
            return self._modules[module_id]
        except KeyError as exc:
            raise KeyError(f"Unknown module: {module_id}") from exc

    def validate_inputs(self, module_ids: list[str], available_inputs: set[str]) -> list[str]:
        return sorted({key for module_id in module_ids for key in self.resolve(module_id).required_inputs if key not in available_inputs})

    def qmd_path(self, module: Module) -> Path:
        if not module.package_root:
            raise ValueError(f"Module {module.id} has no package root")
        return Path(module.package_root) / module.qmd

    @property
    def modules(self) -> dict[str, Module]:
        return dict(self._modules)

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    @property
    def default_modules(self) -> tuple[str, ...]:
        return tuple(self._defaults)


_REGISTRY = Registry()


def get_registry() -> Registry:
    if not _REGISTRY.modules:
        from omics import load_all
        load_all(_REGISTRY)
    return _REGISTRY
