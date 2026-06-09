"""split 命令：按日期或比例拆分训练集、验证集和回溯集"""

import logging
import argparse
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import numpy as np

from ..models import SplitResult
from ..utils import read_file, save_file, ensure_dir

logger = logging.getLogger(__name__)


def _split_by_ratio(df: pd.DataFrame, train_ratio: float, valid_ratio: float,
                    stratified: bool, label_col: str,
                    seed: int) -> Dict[str, pd.DataFrame]:
    """按比例拆分（支持分层抽样）"""
    np.random.seed(seed)
    n = len(df)
    indices = np.arange(n)

    if stratified and label_col in df.columns:
        labels = df[label_col].values
        unique_labels, counts = np.unique(labels, return_counts=True)
        train_idx, valid_idx, back_idx = [], [], []

        for lbl in unique_labels:
            lbl_mask = labels == lbl
            lbl_indices = indices[lbl_mask]
            np.random.shuffle(lbl_indices)

            n_lbl = len(lbl_indices)
            n_train = int(n_lbl * train_ratio)
            n_valid = int(n_lbl * valid_ratio)

            train_idx.extend(lbl_indices[:n_train])
            valid_idx.extend(lbl_indices[n_train:n_train + n_valid])
            back_idx.extend(lbl_indices[n_train + n_valid:])

        return {
            "train": df.iloc[sorted(train_idx)].reset_index(drop=True),
            "valid": df.iloc[sorted(valid_idx)].reset_index(drop=True),
            "backtest": df.iloc[sorted(back_idx)].reset_index(drop=True),
        }
    else:
        np.random.shuffle(indices)
        n_train = int(n * train_ratio)
        n_valid = int(n * valid_ratio)

        return {
            "train": df.iloc[indices[:n_train]].reset_index(drop=True),
            "valid": df.iloc[indices[n_train:n_train + n_valid]].reset_index(drop=True),
            "backtest": df.iloc[indices[n_train + n_valid:]].reset_index(drop=True),
        }


def _split_by_date(df: pd.DataFrame, time_col: str,
                   train_end: str, valid_end: str,
                   label_col: str) -> Dict[str, pd.DataFrame]:
    """按日期拆分"""
    df = df.copy()
    df["_time"] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=["_time"]).sort_values("_time")

    train_end_dt = pd.to_datetime(train_end)
    valid_end_dt = pd.to_datetime(valid_end)

    train_mask = df["_time"] <= train_end_dt
    valid_mask = (df["_time"] > train_end_dt) & (df["_time"] <= valid_end_dt)
    back_mask = df["_time"] > valid_end_dt

    result = {
        "train": df.loc[train_mask].drop(columns=["_time"]).reset_index(drop=True),
        "valid": df.loc[valid_mask].drop(columns=["_time"]).reset_index(drop=True),
        "backtest": df.loc[back_mask].drop(columns=["_time"]).reset_index(drop=True),
    }
    return result


def _calc_fraud_rate(df: pd.DataFrame, label_col: str) -> float:
    if label_col not in df.columns or len(df) == 0:
        return 0.0
    return float((df[label_col] == 1).sum() / len(df))


def cmd_split(args: argparse.Namespace) -> int:
    """执行 split 命令"""
    data_dir = args.data_dir or "./data"
    output_dir = ensure_dir(args.output_dir)

    input_file = args.input
    if not input_file:
        for sub in ["labeled", "cleaned", "imported"]:
            p = Path(data_dir) / sub
            if sub == "imported":
                p = p / "transactions_raw.pkl"
            else:
                p = p / f"transactions_{sub}.pkl"
            if p.exists():
                input_file = str(p)
                break
        if not input_file:
            logger.error("未找到输入文件")
            return 1

    logger.info(f"读取数据: {input_file}")
    df = read_file(input_file)

    label_col = "fraud_label" if "fraud_label" in df.columns else "label"
    time_col = args.time_col or "txn_time"

    result = SplitResult()

    # 拆分
    if args.method == "date":
        if not args.train_end or not args.valid_end:
            logger.error("日期拆分需要指定 --train-end 和 --valid-end")
            return 1
        if time_col not in df.columns:
            logger.error(f"时间列 {time_col} 不存在")
            return 1
        result.method = "按日期拆分"
        logger.info(f"按日期拆分: 训练≤{args.train_end}, 验证≤{args.valid_end}, 回溯>验证")
        splits = _split_by_date(df, time_col, args.train_end, args.valid_end, label_col)
    else:
        if args.ratios:
            train_ratio, valid_ratio = args.ratios[0], args.ratios[1]
        else:
            train_ratio, valid_ratio = 0.7, 0.15
        back_ratio = 1.0 - train_ratio - valid_ratio
        result.method = f"按比例拆分 ({train_ratio:.0%}/{valid_ratio:.0%}/{back_ratio:.0%})"
        stratified = args.stratified and label_col in df.columns
        if stratified:
            logger.info(f"按比例分层拆分，标签列: {label_col}")
        else:
            logger.info(f"按比例随机拆分")
        splits = _split_by_ratio(df, train_ratio, valid_ratio, stratified, label_col, args.seed)

    # 保存并统计
    for name, split_df in splits.items():
        result.splits[name] = len(split_df)
        result.fraud_rates[name] = _calc_fraud_rate(split_df, label_col)

        if name == "backtest" and args.backtest_name:
            fname = args.backtest_name
        else:
            fname = f"{name}.pkl"

        out_path = Path(output_dir) / fname
        save_file(split_df, str(out_path))

        if args.export_csv:
            csv_path = Path(output_dir) / f"{name}.csv"
            save_file(split_df, str(csv_path))

    # 防止同一卡号跨集合
    if args.prevent_card_leak and "card_no" in df.columns:
        logger.info("检查卡号泄漏...")
        train_cards = set(splits["train"]["card_no"].dropna().astype(str))
        for split_name in ["valid", "backtest"]:
            if split_name in splits and len(splits[split_name]) > 0:
                leak = splits[split_name]["card_no"].dropna().astype(str).isin(train_cards).sum()
                if leak > 0:
                    logger.warning(f"  {split_name} 中有 {leak} 条卡号与训练集重叠")
                    if args.fix_leak:
                        logger.info(f"  正在将重叠记录移至训练集...")
                        leak_mask = splits[split_name]["card_no"].dropna().astype(str).isin(train_cards)
                        leak_idx = splits[split_name].index[leak_mask]
                        leak_rows = splits[split_name].loc[leak_idx]
                        splits["train"] = pd.concat([splits["train"], leak_rows], ignore_index=True)
                        splits[split_name] = splits[split_name].drop(leak_idx).reset_index(drop=True)
                        # 重新保存
                        save_file(splits["train"], str(Path(output_dir) / "train.pkl"))
                        save_file(splits[split_name], str(Path(output_dir) / f"{split_name}.pkl"))
                        result.splits["train"] = len(splits["train"])
                        result.splits[split_name] = len(splits[split_name])

    # 保存拆分报告
    report_path = Path(output_dir) / "split_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(result.summary())
        if label_col in df.columns:
            f.write("\n\n各集合标签分布:\n")
            for name, split_df in splits.items():
                f.write(f"\n--- {name} ---\n")
                f.write(split_df[label_col].value_counts().to_string())

    print(result.summary())
    if label_col in df.columns:
        print("\n各集合标签分布:")
        for name, split_df in splits.items():
            print(f"\n--- {name} ---")
            print(split_df[label_col].value_counts().to_string())

    print(f"\n[完成] 拆分完成。数据集已保存至: {output_dir}")
    return 0


def register_subparser(subparsers) -> None:
    """注册 split 子命令"""
    p = subparsers.add_parser("split", help="按日期或比例拆分训练集、验证集和回溯集")
    p.add_argument("-i", "--input", help="输入文件")
    p.add_argument("-d", "--data-dir", default="./data",
                   help="数据根目录 (默认: ./data)")
    p.add_argument("-o", "--output-dir", default="./data/splits",
                   help="输出目录 (默认: ./data/splits)")
    p.add_argument("-m", "--method", choices=["ratio", "date"], default="ratio",
                   help="拆分方式: ratio(按比例) / date(按日期) (默认: ratio)")
    p.add_argument("--ratios", type=float, nargs=2, metavar=("TRAIN", "VALID"),
                   help="训练集和验证集比例，如 --ratios 0.7 0.15 (回溯集为剩余部分)")
    p.add_argument("--train-end", help="训练集截止日期 (YYYY-MM-DD)")
    p.add_argument("--valid-end", help="验证集截止日期 (YYYY-MM-DD)")
    p.add_argument("--time-col", default="txn_time", help="时间列名 (默认: txn_time)")
    p.add_argument("--stratified", action="store_true", default=True,
                   help="分层抽样（按标签）")
    p.add_argument("--seed", type=int, default=42, help="随机种子 (默认: 42)")
    p.add_argument("--prevent-card-leak", action="store_true", default=True,
                   help="检查卡号是否跨集合泄漏")
    p.add_argument("--fix-leak", action="store_true",
                   help="将泄漏的卡号记录移至训练集")
    p.add_argument("--backtest-name", help="回溯集输出文件名")
    p.add_argument("--export-csv", action="store_true",
                   help="同时导出 CSV 格式")
    p.set_defaults(func=cmd_split)
