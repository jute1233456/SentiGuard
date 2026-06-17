"""Data source registry."""
from .base import BaseDataSource, merge_sources
from .gdelt_client import GDELTClient
from .thucnews_loader import THUCNewsLoader

__all__ = ["BaseDataSource", "GDELTClient", "THUCNewsLoader", "merge_sources"]
