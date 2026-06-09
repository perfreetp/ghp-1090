"""通用工具函数"""

import os
import re
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import pandas as pd
import numpy as np
import yaml

from .models import DATE_FORMATS

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def detect_encoding(file_path: str) -> str:
    """检测文件编码"""
    try:
        import chardet
        with open(file_path, "rb") as f:
            raw = f.read(100000)
        result = chardet.detect(raw)
        enc = result.get("encoding", "utf-8")
        if enc and enc.lower() in ("gb2312", "gbk", "gb18030"):
            return "gb18030"
        return enc or "utf-8"
    except Exception:
        return "utf-8"


def read_file(file_path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """读取 CSV/Excel 文件"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    suffix = path.suffix.lower()
    if suffix in (".csv", ".txt"):
        enc = detect_encoding(str(path))
        logger.info(f"读取 {path.name} (编码: {enc})")
        for sep in [",", "\t", "|", ";"]:
            try:
                df = pd.read_csv(str(path), sep=sep, dtype=str, encoding=enc,
                                 low_memory=False, nrows=5)
                if len(df.columns) > 2:
                    return pd.read_csv(str(path), sep=sep, dtype=str,
                                       encoding=enc, low_memory=False)
            except Exception:
                continue
        return pd.read_csv(str(path), dtype=str, encoding=enc, low_memory=False)
    elif suffix in (".xlsx", ".xls"):
        logger.info(f"读取 {path.name} (sheet: {sheet_name or '默认'})")
        return pd.read_excel(str(path), sheet_name=sheet_name or 0, dtype=str)
    elif suffix in (".pkl", ".pickle"):
        logger.info(f"读取 {path.name} (pickle格式)")
        return pd.read_pickle(str(path))
    elif suffix == ".parquet":
        logger.info(f"读取 {path.name} (parquet格式)")
        return pd.read_parquet(str(path))
    else:
        raise ValueError(f"不支持的文件格式: {suffix}")


def save_file(df: pd.DataFrame, file_path: str, **kwargs) -> None:
    """保存 DataFrame 到文件"""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if suffix in (".csv", ".txt"):
        sep = kwargs.get("sep", ",")
        encoding = kwargs.get("encoding", "utf-8-sig")
        df.to_csv(str(path), sep=sep, index=False, encoding=encoding)
    elif suffix in (".xlsx", ".xls"):
        with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=kwargs.get("sheet_name", "Sheet1"))
    elif suffix == ".parquet":
        df.to_parquet(str(path), index=False)
    elif suffix == ".pkl":
        df.to_pickle(str(path))
    else:
        raise ValueError(f"不支持的输出格式: {suffix}")

    logger.info(f"已保存 {len(df)} 行到 {path}")


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """加载 YAML 配置文件"""
    if not config_path:
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_datetime(series: pd.Series) -> Tuple[pd.Series, int]:
    """解析时间字符串，返回 (标准化后的Series, 失败数)"""
    result = pd.Series([pd.NaT] * len(series), index=series.index)
    success_count = 0

    for fmt in DATE_FORMATS:
        mask = result.isna() & series.notna()
        if mask.sum() == 0:
            break
        parsed = pd.to_datetime(series[mask], format=fmt, errors="coerce")
        valid = parsed.notna()
        result.loc[mask[valid].index] = parsed[valid]
        success_count += valid.sum()

    failed = (result.isna() & series.notna()).sum()
    return result, failed


def normalize_amount(series: pd.Series) -> Tuple[pd.Series, int]:
    """标准化金额字符串，返回 (标准化后的Series, 处理数)"""
    processed = series.astype(str).copy()
    count = 0

    pattern = r"[¥￥$,\s]"
    cleaned = processed.str.replace(pattern, "", regex=True)

    negative_mask = cleaned.str.contains(r"^\(.*\)$|^-", na=False)
    cleaned = cleaned.str.replace(r"[()]", "", regex=True)
    cleaned = pd.to_numeric(cleaned, errors="coerce")
    cleaned[negative_mask] = -cleaned[negative_mask]

    count = (cleaned.notna() & (processed.str.contains(pattern, na=True) | negative_mask)).sum()

    return cleaned, count


def mask_card_no(value: str, keep_start: int = 6, keep_end: int = 4) -> str:
    """脱敏卡号"""
    if pd.isna(value) or not isinstance(value, str):
        return value
    s = value.strip().replace(" ", "")
    if len(s) <= keep_start + keep_end:
        return "*" * len(s)
    return s[:keep_start] + "*" * (len(s) - keep_start - keep_end) + s[-keep_end:]


def mask_name(value: str) -> str:
    """脱敏姓名"""
    if pd.isna(value) or not isinstance(value, str):
        return value
    s = value.strip()
    if len(s) <= 1:
        return "*"
    if len(s) == 2:
        return s[0] + "*"
    return s[0] + "*" * (len(s) - 2) + s[-1]


def mask_id_card(value: str) -> str:
    """脱敏证件号"""
    if pd.isna(value) or not isinstance(value, str):
        return value
    s = value.strip()
    if len(s) <= 8:
        return s[:2] + "*" * max(0, len(s) - 2)
    return s[:4] + "*" * (len(s) - 8) + s[-4:]


def mask_phone(value: str) -> str:
    """脱敏手机号"""
    if pd.isna(value) or not isinstance(value, str):
        return value
    s = value.strip()
    if len(s) <= 7:
        return s[:2] + "*" * max(0, len(s) - 2)
    return s[:3] + "*" * (len(s) - 7) + s[-4:]


def mask_email(value: str) -> str:
    """脱敏邮箱"""
    if pd.isna(value) or not isinstance(value, str):
        return value
    if "@" not in value:
        return mask_id_card(value)
    user, domain = value.split("@", 1)
    if len(user) <= 2:
        masked_user = "*" * len(user)
    else:
        masked_user = user[:2] + "*" * (len(user) - 2)
    return f"{masked_user}@{domain}"


def mask_address(value: str) -> str:
    """脱敏地址"""
    if pd.isna(value) or not isinstance(value, str):
        return value
    s = value.strip()
    if len(s) <= 6:
        return s[:2] + "*" * max(0, len(s) - 2)
    return s[:4] + "*" * (len(s) - 6) + s[-2:]


def get_mask_function(field_name: str):
    """根据字段名获取脱敏函数"""
    name = field_name.lower()
    if "card" in name and ("no" in name or "num" in name):
        return mask_card_no
    if "name" in name:
        return mask_name
    if "id" in name and ("card" in name or "cert" in name):
        return mask_id_card
    if "phone" in name or "mobile" in name or "tel" in name:
        return mask_phone
    if "email" in name or "mail" in name:
        return mask_email
    if "address" in name or "addr" in name:
        return mask_address
    return mask_id_card


def ensure_dir(path: str) -> str:
    """确保目录存在"""
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    """生成安全的文件名"""
    return re.sub(r"[\\/:*?\"<>|]", "_", name)


def hash_str(value: str, salt: str = "") -> str:
    """哈希字符串"""
    if pd.isna(value):
        return value
    return hashlib.sha256((str(value) + salt).encode("utf-8")).hexdigest()[:16]
