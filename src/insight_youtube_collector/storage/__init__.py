"""Storage adapters for YouTube collector output."""

from .json_storage import JsonStorage
from .warehouse_storage import WarehouseStorage

__all__ = ["JsonStorage", "WarehouseStorage"]
