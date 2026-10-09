"""Load order data for Track 1."""

import csv
from pathlib import Path


# 根据代码文件定位数据，不依赖运行命令时所在的目录。
DATA_DIR = Path(__file__).resolve().parent / "track1" / "data"


def _read_csv(filename):
    """Read CSV rows, preserving strings and empty strings."""
    file_path = DATA_DIR / filename
    # 原始数据只读；清洗结果或新增数据必须保存到其他目录。
    with file_path.open(mode="r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def load_orders():
    """Return order dictionaries, preserving strings and empty strings."""
    return _read_csv("orders.csv")


def load_production():
    """Read daily production records without modifying the source file."""
    return _read_csv("production_log.csv")


def load_workshops():
    """Read workshop profiles without modifying the source file."""
    return _read_csv("workshops.csv")
