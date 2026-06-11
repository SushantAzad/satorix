"""
Transform registry — maps transform_type strings to BaseTransform subclass instances.
Auto-populated at module import by each transform submodule.
"""

from __future__ import annotations

import logging
from typing import Optional

from layer2_pipeline.transforms.base import BaseTransform

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, BaseTransform] = {}


def register(transform: BaseTransform) -> None:
    name = transform.transform_type
    if not name:
        raise ValueError(f"{type(transform).__name__} has no transform_type set")
    if name in _REGISTRY:
        logger.warning("Re-registering transform type %r", name)
    _REGISTRY[name] = transform
    logger.debug("Registered transform: %s", name)


def get(transform_type: str) -> Optional[BaseTransform]:
    t = _REGISTRY.get(transform_type)
    if t is None:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        logger.error("Unknown transform type %r — available: %s", transform_type, available)
    return t


def all_types() -> list[str]:
    return sorted(_REGISTRY.keys())


def _auto_register() -> None:
    """Import all transform modules so they self-register."""
    import importlib

    modules = [
        "layer2_pipeline.transforms.cleaning.string_transforms",
        "layer2_pipeline.transforms.cleaning.number_transforms",
        "layer2_pipeline.transforms.cleaning.date_transforms",
        "layer2_pipeline.transforms.cleaning.address_transforms",
        "layer2_pipeline.transforms.cleaning.identifier_transforms",
        "layer2_pipeline.transforms.structural.column_ops",
        "layer2_pipeline.transforms.structural.row_ops",
        "layer2_pipeline.transforms.structural.table_ops",
        "layer2_pipeline.transforms.enrichment.reference_lookup",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
        except ImportError as exc:
            logger.debug("Could not load transform module %s: %s", mod, exc)


_auto_register()
