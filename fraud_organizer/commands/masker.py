"""mask 命令：对姓名、证件、手机号做脱敏"""

import logging
import argparse
from pathlib import Path
from typing import List, Dict

import pandas as pd

from ..utils import (
    read_file, save_file, ensure_dir, get_mask_function,
    mask_card_no, mask_name, mask_id_card, mask_phone,
    mask_email, mask_address, hash_str
)
from ..models import MASK_FIELDS

logger = logging.getLogger(__name__)


DEFAULT_MASK_RULES = {
    "card_no": "mask",
    "cardholder_name": "mask",
    "name": "mask",
    "id_card": "mask",
    "cert_no": "mask",
    "phone": "mask",
    "mobile": "mask",
    "email": "mask",
    "address": "mask",
    "device_id": "hash",
    "ip": "hash",
    "cardholder_id": "mask",
}


def _apply_mask(df: pd.DataFrame, col: str, method: str,
                salt: str = "") -> pd.Series:
    """对单列应用脱敏"""
    if method == "none":
        return df[col]

    if method == "drop":
        return pd.Series(["[REDACTED]"] * len(df), index=df.index, name=col)

    if method == "hash":
        return df[col].apply(lambda x: hash_str(x, salt) if pd.notna(x) else x)

    # method == "mask"
    func = get_mask_function(col)
    logger.debug(f"  {col}: 使用脱敏函数 {func.__name__}")
    return df[col].apply(lambda x: func(x) if pd.notna(x) else x)


def cmd_mask(args: argparse.Namespace) -> int:
    """执行 mask 命令"""
    data_dir = args.data_dir or "./data"
    output_dir = ensure_dir(args.output_dir)

    input_file = args.input
    if not input_file:
        # 查找所有需要脱敏的文件
        candidates = []
        for sub in ["splits", "labeled", "cleaned", "imported"]:
            subdir = Path(data_dir) / sub
            if subdir.is_dir():
                for p in subdir.glob("*.pkl"):
                    candidates.append(str(p))
                for p in subdir.glob("*.csv"):
                    candidates.append(str(p))
        if not candidates:
            logger.error("未找到输入文件")
            return 1
        if args.all:
            input_files = candidates
        else:
            input_files = [candidates[0]]
    else:
        input_files = [input_file]

    # 构建脱敏规则
    rules = {}
    if args.fields:
        for item in args.fields:
            if "=" in item:
                col, method = item.split("=", 1)
                rules[col.strip()] = method.strip().lower()
            else:
                rules[item.strip()] = "mask"
    else:
        rules = DEFAULT_MASK_RULES.copy()

    if args.hash_fields:
        for col in args.hash_fields:
            rules[col] = "hash"
    if args.drop_fields:
        for col in args.drop_fields:
            rules[col] = "drop"

    if args.keep_card_prefix and "card_no" in rules:
        rules["card_no"] = "mask"

    salt = args.salt or ""
    summary_rows = []

    for fp in input_files:
        logger.info(f"处理文件: {fp}")
        df = read_file(fp)
        original_cols = set(df.columns)

        applied_rules = {col: method for col, method in rules.items()
                         if col in original_cols}

        if not applied_rules:
            logger.warning(f"  没有可匹配的列，跳过")
            continue

        logger.info(f"  应用脱敏规则到 {len(applied_rules)} 列: {list(applied_rules.keys())}")

        masked_count = 0
        for col, method in applied_rules.items():
            before = df[col].copy()
            df[col] = _apply_mask(df, col, method, salt)
            changed = (before.astype(str) != df[col].astype(str)).sum()
            masked_count += changed
            logger.debug(f"    {col} ({method}): {changed} 行被处理")

        # 输出文件
        src_path = Path(fp)
        if args.prefix:
            out_name = f"{args.prefix}_{src_path.stem}{src_path.suffix}"
        else:
            out_name = f"masked_{src_path.stem}{src_path.suffix}"
        out_path = Path(output_dir) / out_name
        save_file(df, str(out_path))

        summary_rows.append({
            "文件": src_path.name,
            "总行数": len(df),
            "处理列数": len(applied_rules),
            "修改行数": masked_count,
            "输出": out_name,
        })

    if not summary_rows:
        logger.error("没有文件被处理")
        return 1

    # 生成摘要
    summary_df = pd.DataFrame(summary_rows)
    summary_path = Path(output_dir) / "mask_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    print("=" * 60)
    print("脱敏处理摘要")
    print("=" * 60)
    print(summary_df.to_string(index=False))
    print(f"\n脱敏规则:")
    for col, method in rules.items():
        if method != "none":
            print(f"  {col}: {method}")
    print(f"\n[完成] 脱敏完成。输出目录: {output_dir}")
    return 0


def register_subparser(subparsers) -> None:
    """注册 mask 子命令"""
    p = subparsers.add_parser("mask", help="对姓名、证件、手机号做脱敏")
    p.add_argument("-i", "--input", help="输入文件（不指定则处理 data 下所有 pkl/csv）")
    p.add_argument("-d", "--data-dir", default="./data",
                   help="数据根目录 (默认: ./data)")
    p.add_argument("-o", "--output-dir", default="./data/masked",
                   help="输出目录 (默认: ./data/masked)")
    p.add_argument("-f", "--fields", nargs="+", metavar="COL[=METHOD]",
                   help="脱敏列及方法 (METHOD: mask/hash/drop/none)。"
                        "例: -f card_no=mask phone=hash email=drop")
    p.add_argument("--hash-fields", nargs="+", metavar="COL",
                   help="指定列为哈希脱敏")
    p.add_argument("--drop-fields", nargs="+", metavar="COL",
                   help="指定列为置空脱敏")
    p.add_argument("--all", action="store_true",
                   help="处理 data 目录下所有文件")
    p.add_argument("--salt", default="", help="哈希盐值")
    p.add_argument("--prefix", default="", help="输出文件名前缀")
    p.add_argument("--keep-card-prefix", action="store_true", default=True,
                   help="卡号保留前6后4位")
    p.set_defaults(func=cmd_mask)
