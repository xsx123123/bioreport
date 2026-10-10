"""Built-in omics modules."""

import importlib
import pkgutil


def load_all(registry) -> None:
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        register = getattr(module, "register", None)
        if register:
            register(registry)
