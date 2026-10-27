from __future__ import annotations

import importlib
import logging

from devpulse.config import get_settings
from devpulse.source_connectors.base import SourceConnector

log = logging.getLogger(__name__)
_REGISTRY: dict[str, type[SourceConnector]] = {}
_loaded = False


def register(type_name: str):
    def deco(cls: type[SourceConnector]) -> type[SourceConnector]:
        cls.type_name = type_name
        _REGISTRY[type_name] = cls
        return cls

    return deco


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    for mod in ("rss", "json_api", "github_releases", "webpage", "email_inbox"):
        importlib.import_module(f"devpulse.source_connectors.{mod}")
    for mod in filter(None, (m.strip() for m in get_settings().plugin_modules.split(","))):
        try:
            importlib.import_module(mod)
            log.info("Plugin de conectores carregado: %s", mod)
        except Exception:
            log.exception("Falha ao carregar plugin %s", mod)


def get_connector(type_name: str) -> SourceConnector:
    _load()
    if type_name not in _REGISTRY:
        raise KeyError(f"Tipo de conector desconhecido: {type_name}")
    return _REGISTRY[type_name]()


def available() -> dict[str, type[SourceConnector]]:
    _load()
    return dict(_REGISTRY)
