"""profile 命令：统计卡号、商户、设备、地区的异常频次"""

import logging
import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd
import numpy as np

from ..utils import read_file, save_file, ensure_dir

logger = logging.getLogger(__name__)


def _calc_entity_stats(df: pd.DataFrame, entity_col: str, time_col: str,
                       amount_col: str, label_col: str,
                       window: str = "7D") -> pd.DataFrame:
    """计算实体维度的频次统计"""
    if entity_col not in df.columns:
        return pd.DataFrame()

    stats = df.groupby(entity_col).agg(
        总交易次数=(entity_col, "count"),
        总金额=(amount_col, "sum") if amount_col in df.columns else (entity_col, "count"),
        欺诈次数=(label_col, lambda x: (x == 1).sum()),
        可疑次数=(label_col, lambda x: (x == 2).sum()),
        唯一商户=("merchant_id", "nunique") if "merchant_id" in df.columns else (entity_col, "nunique"),
        唯一地区=("province", "nunique") if "province" in df.columns else (entity_col, "nunique"),
        唯一设备=("device_id", "nunique") if "device_id" in df.columns else (entity_col, "nunique"),
    ).reset_index()

    stats["欺诈率"] = np.where(stats["总交易次数"] > 0,
                               stats["欺诈次数"] / stats["总交易次数"], 0)
    stats["风险等级"] = pd.cut(
        stats["欺诈率"],
        bins=[-0.01, 0.01, 0.05, 0.2, 1.01],
        labels=["低", "中", "高", "极高"]
    )
    stats = stats.sort_values("欺诈次数", ascending=False)
    return stats


def _calc_time_stats(df: pd.DataFrame, entity_col: str, time_col: str,
                     amount_col: str) -> pd.DataFrame:
    """计算实体的时间间隔特征"""
    if entity_col not in df.columns or time_col not in df.columns:
        return pd.DataFrame()

    work = df[[entity_col, time_col, amount_col]].copy()
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
    work = work.dropna(subset=[time_col]).sort_values([entity_col, time_col])

    work["prev_time"] = work.groupby(entity_col)[time_col].shift(1)
    work["time_diff_hours"] = (work[time_col] - work["prev_time"]).dt.total_seconds() / 3600

    if amount_col in work.columns:
        work[amount_col] = pd.to_numeric(work[amount_col], errors="coerce")
        work["prev_amount"] = work.groupby(entity_col)[amount_col].shift(1)
        work["amount_ratio"] = np.where(
            work["prev_amount"] > 0,
            work[amount_col] / work["prev_amount"],
            np.nan
        )

    interval_stats = work.groupby(entity_col).agg(
        平均间隔小时=("time_diff_hours", "mean"),
        最小间隔分钟=("time_diff_hours", lambda x: (x * 60).min()),
        最大交易间隔=("time_diff_hours", "max"),
        间隔变异系数=("time_diff_hours",
                    lambda x: x.std() / x.mean() if x.mean() > 0 else 0),
    ).reset_index()

    if "amount_ratio" in work.columns:
        amount_stats = work.groupby(entity_col).agg(
            金额波动率=("amount_ratio",
                       lambda x: x.dropna().std() / x.dropna().mean()
                       if x.dropna().mean() > 0 else 0),
        ).reset_index()
        interval_stats = interval_stats.merge(amount_stats, on=entity_col, how="left")

    return interval_stats


def _find_anomalies(df: pd.DataFrame, entity_col: str,
                    stats: pd.DataFrame,
                    freq_threshold: int = 10,
                    fraud_threshold: float = 0.1,
                    interval_threshold: float = 1.0) -> pd.DataFrame:
    """识别异常实体"""
    if len(stats) == 0:
        return pd.DataFrame()

    anomalies = []
    if entity_col not in df.columns:
        return pd.DataFrame()

    card_counts = df[entity_col].value_counts()

    for _, row in stats.iterrows():
        entity = row[entity_col]
        reasons = []
        if row.get("欺诈率", 0) >= fraud_threshold and row.get("欺诈次数", 0) >= 1:
            reasons.append(f"欺诈率{row['欺诈率']:.1%}≥{fraud_threshold:.0%}")
        if row.get("总交易次数", 0) >= freq_threshold:
            reasons.append(f"交易频次{row['总交易次数']}≥{freq_threshold}")
        if "平均间隔小时" in row and not pd.isna(row["平均间隔小时"]) and row["平均间隔小时"] < interval_threshold:
            reasons.append(f"平均间隔{row['平均间隔小时']:.1f}h<{interval_threshold}h")
        if "唯一地区" in row and row["唯一地区"] >= 5:
            reasons.append(f"跨地区数{row['唯一地区']}≥5")
        if "唯一设备" in row and row["唯一设备"] >= 5:
            reasons.append(f"跨设备数{row['唯一设备']}≥5")

        if reasons:
            anomalies.append({
                "实体类型": entity_col,
                "实体值": entity,
                "总交易次数": row.get("总交易次数", card_counts.get(entity, 0)),
                "欺诈次数": row.get("欺诈次数", 0),
                "欺诈率": row.get("欺诈率", 0),
                "异常原因": "; ".join(reasons),
            })

    return pd.DataFrame(anomalies)


def cmd_profile(args: argparse.Namespace) -> int:
    """执行 profile 命令"""
    data_dir = args.data_dir or "./data"
    output_dir = ensure_dir(args.output_dir)

    input_file = args.input
    if not input_file:
        p = Path(data_dir) / "labeled" / "transactions_labeled.pkl"
        if not p.exists():
            p = Path(data_dir) / "cleaned" / "transactions_clean.pkl"
        if p.exists():
            input_file = str(p)
        else:
            logger.error("未找到输入文件")
            return 1

    logger.info(f"读取数据: {input_file}")
    df = read_file(input_file)

    time_col = args.time_col or "txn_time"
    amount_col = args.amount_col or "txn_amount"
    label_col = "fraud_label" if "fraud_label" in df.columns else None

    # 为未标记数据打临时标签
    if label_col is None:
        df["fraud_label"] = -1
        label_col = "fraud_label"

    entities = args.entities or ["card_no", "merchant_id", "device_id", "province"]
    all_stats = {}
    all_anomalies = []

    for entity in entities:
        logger.info(f"分析维度: {entity}")
        stats = _calc_entity_stats(df, entity, time_col, amount_col, label_col,
                                   window=args.window)
        if len(stats) > 0:
            all_stats[entity] = stats.head(args.top_n)
            interval_stats = _calc_time_stats(df, entity, time_col, amount_col)
            if len(interval_stats) > 0:
                stats = stats.merge(interval_stats, on=entity, how="left")

            anomalies = _find_anomalies(
                df, entity, stats,
                freq_threshold=args.freq_threshold,
                fraud_threshold=args.fraud_threshold,
                interval_threshold=args.interval_threshold,
            )
            all_anomalies.append(anomalies)

            # 保存每个维度的统计
            stats_path = Path(output_dir) / f"stats_{entity}.csv"
            stats.to_csv(stats_path, index=False, encoding="utf-8-sig")

    # 汇总异常
    anomaly_df = pd.concat(all_anomalies, ignore_index=True) if all_anomalies else pd.DataFrame()

    # 总体概览
    overview = {
        "总样本数": len(df),
        "唯一卡数": df["card_no"].nunique() if "card_no" in df.columns else 0,
        "唯一商户数": df["merchant_id"].nunique() if "merchant_id" in df.columns else 0,
        "唯一设备数": df["device_id"].nunique() if "device_id" in df.columns else 0,
        "唯一地区数": df["province"].nunique() if "province" in df.columns else 0,
        "欺诈样本数": int((df[label_col] == 1).sum()) if label_col else 0,
    }
    if label_col:
        overview["整体欺诈率"] = f"{overview['欺诈样本数'] / max(len(df),1):.2%}"

    # 输出报告
    print("=" * 60)
    print("数据画像 - 总体概览")
    print("=" * 60)
    for k, v in overview.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("Top 维度统计")
    print("=" * 60)
    for name, stats_df in all_stats.items():
        print(f"\n--- [{name}] Top{args.top_n} ---")
        cols_show = [c for c in [name, "总交易次数", "欺诈次数", "欺诈率", "风险等级"]
                     if c in stats_df.columns]
        print(stats_df[cols_show].to_string(index=False))

    if len(anomaly_df) > 0:
        print("\n" + "=" * 60)
        print(f"[警告] 检测到 {len(anomaly_df)} 个异常实体")
        print("=" * 60)
        print(anomaly_df.head(20).to_string(index=False))

    # 保存 Excel 报告
    excel_path = Path(output_dir) / "profile_report.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        pd.DataFrame([overview]).T.to_excel(writer, sheet_name="概览", header=False)
        for name, stats_df in all_stats.items():
            sheet = name[:31]
            stats_df.to_excel(writer, sheet_name=sheet, index=False)
        if len(anomaly_df) > 0:
            anomaly_df.to_excel(writer, sheet_name="异常实体", index=False)

    # 保存 CSV 版本
    overview_path = Path(output_dir) / "overview.csv"
    pd.DataFrame([overview]).T.to_csv(overview_path, header=False, encoding="utf-8-sig")

    if len(anomaly_df) > 0:
        anomaly_path = Path(output_dir) / "anomalies.csv"
        anomaly_df.to_csv(anomaly_path, index=False, encoding="utf-8-sig")

    print(f"\n[完成] 画像完成。报告已保存至: {output_dir}")
    return 0


def register_subparser(subparsers) -> None:
    """注册 profile 子命令"""
    p = subparsers.add_parser("profile", help="统计卡号、商户、设备、地区的异常频次")
    p.add_argument("-i", "--input", help="输入文件")
    p.add_argument("-d", "--data-dir", default="./data",
                   help="数据根目录 (默认: ./data)")
    p.add_argument("-o", "--output-dir", default="./data/profiled",
                   help="输出目录 (默认: ./data/profiled)")
    p.add_argument("--entities", nargs="+",
                   default=["card_no", "merchant_id", "device_id", "province", "city", "mcc"],
                   help="分析维度列名")
    p.add_argument("--time-col", default="txn_time", help="时间列名")
    p.add_argument("--amount-col", default="txn_amount", help="金额列名")
    p.add_argument("--window", default="7D", help="统计窗口 (如 7D, 30D)")
    p.add_argument("--top-n", type=int, default=20, help="每维度显示Top N")
    p.add_argument("--freq-threshold", type=int, default=20,
                   help="高频交易阈值 (次)")
    p.add_argument("--fraud-threshold", type=float, default=0.05,
                   help="异常欺诈率阈值")
    p.add_argument("--interval-threshold", type=float, default=1.0,
                   help="短交易间隔阈值 (小时)")
    p.set_defaults(func=cmd_profile)
