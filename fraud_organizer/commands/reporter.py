"""report 命令：输出欺诈率、样本覆盖、类别失衡和高风险特征摘要"""

import logging
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import numpy as np

from ..utils import read_file, save_file, ensure_dir

logger = logging.getLogger(__name__)


def _calc_fraud_metrics(df: pd.DataFrame, label_col: str) -> Dict:
    """计算欺诈率等核心指标"""
    n = len(df)
    if label_col not in df.columns:
        return {"总样本数": n}

    genuine = int((df[label_col] == 0).sum())
    fraud = int((df[label_col] == 1).sum())
    suspicious = int((df[label_col] == 2).sum())
    unknown = int((df[label_col] == -1).sum())

    metrics = {
        "总样本数": n,
        "真实交易数": genuine,
        "欺诈交易数": fraud,
        "可疑交易数": suspicious,
        "未标记数": unknown,
        "整体欺诈率(含未标记)": f"{fraud / max(n,1):.4%}",
        "欺诈率(已标记样本)": f"{fraud / max(genuine + fraud + suspicious,1):.4%}",
        "正负样本比": f"{genuine / max(fraud, 1):.2f} : 1",
        "有效标记率": f"{(genuine + fraud + suspicious) / max(n,1):.2%}",
    }
    return metrics


def _calc_coverage(df: pd.DataFrame, key_cols: List[str]) -> Dict:
    """计算关键字段覆盖率"""
    coverage = {}
    for col in key_cols:
        if col in df.columns:
            rate = df[col].notna() & df[col].astype(str).str.strip().ne("")
            coverage[f"{col} 覆盖率"] = f"{rate.mean():.2%}"
            coverage[f"{col} 唯一值数"] = int(df.loc[rate, col].nunique())
    return coverage


def _calc_class_imbalance(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    """分析类别失衡"""
    if label_col not in df.columns:
        return pd.DataFrame()

    label_map = {0: "真实", 1: "欺诈", 2: "可疑", -1: "未标记"}
    counts = df[label_col].value_counts().reset_index()
    counts.columns = ["标签编码", "样本数"]
    counts["标签名称"] = counts["标签编码"].map(label_map).fillna(counts["标签编码"].astype(str))
    counts["占比"] = counts["样本数"] / counts["样本数"].sum()
    counts["占比"] = counts["占比"].apply(lambda x: f"{x:.2%}")
    counts["失衡权重(相对欺诈)"] = counts["样本数"] / max(
        counts.loc[counts["标签编码"] == 1, "样本数"].sum(), 1)
    return counts


def _find_high_risk_features(df: pd.DataFrame, label_col: str,
                              cat_cols: List[str], num_cols: List[str],
                              top_k: int = 10) -> Dict[str, pd.DataFrame]:
    """识别高风险特征"""
    result = {}
    if label_col not in df.columns:
        return result

    fraud_mask = df[label_col] == 1

    # 类别特征
    cat_results = []
    for col in cat_cols:
        if col not in df.columns:
            continue
        try:
            cross = pd.crosstab(df[col], df[label_col])
            if 1 not in cross.columns:
                continue
            cross["总数"] = cross.sum(axis=1)
            cross["欺诈率"] = cross.get(1, 0) / cross["总数"]
            cross["欺诈贡献"] = cross.get(1, 0) / max(cross.get(1, 0).sum(), 1)

            for val, row in cross.iterrows():
                if row["总数"] >= 5 and row["欺诈率"] > 0.01:
                    cat_results.append({
                        "特征": col,
                        "取值": val,
                        "样本数": int(row["总数"]),
                        "欺诈数": int(row.get(1, 0)),
                        "欺诈率": f"{row['欺诈率']:.2%}",
                        "欺诈贡献": f"{row['欺诈贡献']:.2%}",
                    })
        except Exception as e:
            logger.debug(f"分析 {col} 失败: {e}")

    if cat_results:
        cat_df = pd.DataFrame(cat_results).sort_values(
            "欺诈数", ascending=False).head(top_k)
        result["高风险类别特征"] = cat_df

    # 数值特征
    num_results = []
    for col in num_cols:
        if col not in df.columns:
            continue
        try:
            vals = pd.to_numeric(df[col], errors="coerce")
            fraud_vals = vals[fraud_mask].dropna()
            normal_vals = vals[~fraud_mask & (df[label_col] == 0)].dropna()

            if len(fraud_vals) < 5 or len(normal_vals) < 5:
                continue

            mean_diff = fraud_vals.mean() - normal_vals.mean()
            std_val = vals.std() or 1
            effect_size = mean_diff / std_val

            num_results.append({
                "特征": col,
                "欺诈均值": round(fraud_vals.mean(), 4),
                "正常均值": round(normal_vals.mean(), 4),
                "差值": round(mean_diff, 4),
                "效应量(Cohen's d)": round(effect_size, 4),
                "欺诈中位数": round(fraud_vals.median(), 4),
                "正常中位数": round(normal_vals.median(), 4),
            })
        except Exception as e:
            logger.debug(f"分析 {col} 失败: {e}")

    if num_results:
        num_df = pd.DataFrame(num_results).sort_values(
            "效应量(Cohen's d)", ascending=False, key=abs).head(top_k)
        result["高风险数值特征"] = num_df

    return result


def _temporal_analysis(df: pd.DataFrame, time_col: str,
                        label_col: str) -> pd.DataFrame:
    """时间维度分析"""
    if time_col not in df.columns or label_col not in df.columns:
        return pd.DataFrame()

    work = df[[time_col, label_col]].copy()
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
    work = work.dropna(subset=[time_col])

    work["日期"] = work[time_col].dt.date
    daily = work.groupby("日期").agg(
        总交易数=(label_col, "count"),
        欺诈数=(label_col, lambda x: (x == 1).sum()),
    ).reset_index()
    daily["欺诈率"] = (daily["欺诈数"] / daily["总交易数"]).round(4)

    # 按星期
    work["星期"] = work[time_col].dt.dayofweek
    weekday = work.groupby("星期").agg(
        总交易数=(label_col, "count"),
        欺诈数=(label_col, lambda x: (x == 1).sum()),
    ).reset_index()
    weekday_name = {0: "周一", 1: "周二", 2: "周三", 3: "周四",
                    4: "周五", 5: "周六", 6: "周日"}
    weekday["星期"] = weekday["星期"].map(weekday_name)
    weekday["欺诈率"] = (weekday["欺诈数"] / weekday["总交易数"]).round(4)

    return daily, weekday


def cmd_report(args: argparse.Namespace) -> int:
    """执行 report 命令"""
    data_dir = args.data_dir or "./data"
    output_dir = ensure_dir(args.output_dir)

    input_files = args.inputs or []
    if not input_files:
        for sub in ["labeled", "splits", "cleaned"]:
            subdir = Path(data_dir) / sub
            if subdir.is_dir():
                for p in sorted(subdir.glob("*.pkl")):
                    input_files.append(str(p))
                break
    if not input_files:
        logger.error("未找到输入文件")
        return 1

    label_col = "fraud_label"
    time_col = args.time_col or "txn_time"
    default_cat = ["txn_type", "channel", "merchant_id", "province", "city",
                   "mcc", "currency", "txn_result", "pos_entry_mode",
                   "card_type", "issuer_bank", "acquirer_bank"]
    default_num = ["txn_amount", "risk_score", "installment", "cashback"]

    cat_cols = args.cat_cols or default_cat
    num_cols = args.num_cols or default_num
    key_cols = args.key_cols or ["card_no", "txn_time", "txn_amount",
                                  "merchant_id", "txn_type", "channel"]

    print("=" * 60)
    print("反欺诈样本分析报告")
    print("=" * 60)

    excel_path = Path(output_dir) / "fraud_report.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        all_metrics = []

        for fp in input_files:
            fname = Path(fp).name
            logger.info(f"分析文件: {fname}")
            df = read_file(fp)

            print(f"\n{'─' * 50}")
            print(f"[文件分析] {fname}")
            print(f"{'─' * 50}")

            # 1. 欺诈率
            metrics = _calc_fraud_metrics(df, label_col)
            metrics["_file"] = fname
            all_metrics.append(metrics)
            print("\n[核心指标]")
            for k, v in metrics.items():
                if not k.startswith("_"):
                    print(f"  {k}: {v}")

            # 2. 样本覆盖
            coverage = _calc_coverage(df, key_cols)
            print("\n[关键字段覆盖率]")
            for k, v in coverage.items():
                print(f"  {k}: {v}")

            # 3. 类别失衡
            imbalance = _calc_class_imbalance(df, label_col)
            if len(imbalance) > 0:
                print("\n[类别分布]")
                print(imbalance.to_string(index=False))
                sheet_key = f"类别分布_{fname.split('.')[0][:20]}"
                imbalance.to_excel(writer, sheet_name=sheet_key, index=False)

            # 4. 高风险特征
            hr = _find_high_risk_features(df, label_col, cat_cols, num_cols, args.top_k)
            for hk, hv in hr.items():
                print(f"\n[高风险特征] {hk} Top{args.top_k}:")
                print(hv.to_string(index=False))
                sheet_key = f"{hk}_{fname.split('.')[0][:15]}"
                hv.to_excel(writer, sheet_name=sheet_key[:31], index=False)

            # 5. 时间分析
            try:
                daily, weekday = _temporal_analysis(df, time_col, label_col)
                if len(daily) > 0:
                    print(f"\n[时间分析] (共 {len(daily)} 天):")
                    print(f"  日均交易: {daily['总交易数'].mean():.1f}")
                    print(f"  日均欺诈: {daily['欺诈数'].mean():.1f}")
                    if len(weekday) > 0:
                        print("  星期分布:")
                        print(weekday.to_string(index=False))
                    sheet_key = f"每日趋势_{fname.split('.')[0][:18]}"
                    daily.to_excel(writer, sheet_name=sheet_key[:31], index=False)
            except Exception as e:
                logger.debug(f"时间分析失败: {e}")

            # 6. 保存单文件指标到Excel
            metrics_df = pd.DataFrame(
                [[k, v] for k, v in metrics.items() if not k.startswith("_")],
                columns=["指标", "值"]
            )
            sheet_key = f"指标_{fname.split('.')[0][:22]}"
            metrics_df.to_excel(writer, sheet_name=sheet_key[:31], index=False)

        # 汇总
        if all_metrics:
            summary_df = pd.DataFrame(all_metrics).rename(columns={"_file": "文件"})
            summary_df.to_excel(writer, sheet_name="00_汇总", index=False)

    # 生成文本报告
    txt_path = Path(output_dir) / "fraud_report.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("反欺诈样本分析报告\n")
        f.write(f"生成时间: {pd.Timestamp.now()}\n")
        f.write("=" * 60 + "\n\n")
        f.write("一、核心指标汇总\n")
        f.write("-" * 50 + "\n")
        for m in all_metrics:
            f.write(f"\n文件: {m.get('_file', 'N/A')}\n")
            for k, v in m.items():
                if not k.startswith("_"):
                    f.write(f"  {k}: {v}\n")

    print(f"\n{'=' * 60}")
    print(f"[完成] 报告生成完成")
    print(f"  Excel报告: {excel_path}")
    print(f"  文本报告: {txt_path}")
    return 0


def register_subparser(subparsers) -> None:
    """注册 report 子命令"""
    p = subparsers.add_parser("report",
                              help="输出欺诈率、样本覆盖、类别失衡和高风险特征摘要")
    p.add_argument("-i", "--inputs", nargs="+", help="输入文件列表")
    p.add_argument("-d", "--data-dir", default="./data",
                   help="数据根目录 (默认: ./data)")
    p.add_argument("-o", "--output-dir", default="./data/reports",
                   help="输出目录 (默认: ./data/reports)")
    p.add_argument("--time-col", default="txn_time", help="时间列名")
    p.add_argument("--cat-cols", nargs="+", help="类别特征列名列表")
    p.add_argument("--num-cols", nargs="+", help="数值特征列名列表")
    p.add_argument("--key-cols", nargs="+", help="关键字段（用于覆盖率检查）")
    p.add_argument("--top-k", type=int, default=10, help="Top K 高风险特征")
    p.set_defaults(func=cmd_report)
