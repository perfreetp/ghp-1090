"""clean 命令：去重、统一金额和时间格式"""

import logging
import argparse
from pathlib import Path

import pandas as pd
import numpy as np

from ..models import CleanResult
from ..utils import read_file, save_file, ensure_dir, parse_datetime, normalize_amount

logger = logging.getLogger(__name__)


def cmd_clean(args: argparse.Namespace) -> int:
    """执行 clean 命令"""
    input_file = args.input
    output_dir = ensure_dir(args.output_dir)

    if not input_file:
        p = Path(args.data_dir or "./data/imported") / "transactions_raw.pkl"
        if p.exists():
            input_file = str(p)
        else:
            logger.error(f"未找到输入文件，且默认位置 {p} 不存在")
            return 1

    logger.info(f"读取数据: {input_file}")
    df = read_file(input_file)

    result = CleanResult(initial_rows=len(df))
    initial_len = len(df)

    # 1. 去重
    dedup_cols = args.dedup_cols
    if not dedup_cols:
        if "txn_id" in df.columns:
            dedup_cols = ["txn_id"]
        else:
            dedup_cols = [c for c in ["card_no", "txn_time", "txn_amount",
                                      "merchant_id"] if c in df.columns]

    if dedup_cols:
        before = len(df)
        df = df.drop_duplicates(subset=dedup_cols, keep="first").reset_index(drop=True)
        result.duplicates_removed = before - len(df)
        logger.info(f"去重依据: {dedup_cols}, 移除 {result.duplicates_removed} 条")

    # 2. 标准化时间格式
    time_col = args.time_col or "txn_time"
    if time_col in df.columns:
        logger.info(f"标准化时间列: {time_col}")
        parsed, failed = parse_datetime(df[time_col])
        result.time_normalized = parsed.notna().sum()
        if failed > 0 and not args.keep_invalid_time:
            result.invalid_time_removed = failed
            df = df[parsed.notna()].reset_index(drop=True)
            parsed = parsed[parsed.notna()].reset_index(drop=True)
            logger.warning(f"移除 {failed} 条时间无效的记录")
        df[time_col] = parsed
        if df[time_col].notna().any():
            df[time_col] = df[time_col].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 3. 标准化金额格式
    amount_col = args.amount_col or "txn_amount"
    if amount_col in df.columns:
        logger.info(f"标准化金额列: {amount_col}")
        norm, count = normalize_amount(df[amount_col])
        result.amount_normalized = count
        invalid = norm.isna().sum()
        if invalid > 0 and not args.keep_invalid_amount:
            result.invalid_amount_removed = invalid
            df = df[norm.notna()].reset_index(drop=True)
            norm = norm[norm.notna()].reset_index(drop=True)
            logger.warning(f"移除 {invalid} 条金额无效的记录")
        df[amount_col] = norm

    # 4. 去空格
    if args.strip_strings:
        obj_cols = df.select_dtypes(include="object").columns
        for col in obj_cols:
            df[col] = df[col].astype(str).str.strip().replace({"nan": np.nan, "": np.nan})

    # 5. 币种统一
    if "currency" in df.columns and args.currency:
        df["currency"] = df["currency"].str.upper()
        df.loc[df["currency"].isin(["CNY", "RMB", "¥", "￥"]), "currency"] = "CNY"
        df.loc[df["currency"].isin(["USD", "$"]), "currency"] = "USD"

    # 6. 交易类型统一
    if "txn_type" in df.columns:
        type_map = {
            "消费": "消费", "PURCHASE": "消费", "SALE": "消费", "01": "消费",
            "取现": "取现", "WITHDRAW": "取现", "CASH": "取现", "02": "取现",
            "转账": "转账", "TRANSFER": "转账", "03": "转账",
            "退款": "退款", "REFUND": "退款", "04": "退款",
            "预授权": "预授权", "PREAUTH": "预授权", "05": "预授权",
        }
        df["txn_type"] = df["txn_type"].map(
            lambda x: type_map.get(str(x).strip().upper(), type_map.get(str(x).strip(), x))
            if pd.notna(x) else x
        )

    result.final_rows = len(df)

    # 保存结果
    out_path = Path(output_dir) / "transactions_clean.pkl"
    save_file(df, str(out_path))

    # 保存清洗报告
    report_path = Path(output_dir) / "clean_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(result.summary())

    print(result.summary())
    print(f"\n[完成] 清洗完成。输出: {out_path}")
    return 0


def register_subparser(subparsers) -> None:
    """注册 clean 子命令"""
    p = subparsers.add_parser("clean", help="去重、统一金额和时间格式")
    p.add_argument("-i", "--input", help="输入文件 (默认从 data/imported 读取)")
    p.add_argument("-d", "--data-dir", default="./data/imported",
                   help="数据目录 (默认: ./data/imported)")
    p.add_argument("-o", "--output-dir", default="./data/cleaned",
                   help="输出目录 (默认: ./data/cleaned)")
    p.add_argument("--dedup-cols", nargs="+",
                   help="去重依据列名 (默认: txn_id 或 卡号+时间+金额+商户)")
    p.add_argument("--time-col", help="时间列名 (默认: txn_time)")
    p.add_argument("--amount-col", help="金额列名 (默认: txn_amount)")
    p.add_argument("--currency", action="store_true", default=True,
                   help="统一币种编码")
    p.add_argument("--strip-strings", action="store_true", default=True,
                   help="去除字符串两端空格")
    p.add_argument("--keep-invalid-time", action="store_true",
                   help="保留时间无效的记录")
    p.add_argument("--keep-invalid-amount", action="store_true",
                   help="保留金额无效的记录")
    p.set_defaults(func=cmd_clean)
