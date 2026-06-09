"""report 命令：输出欺诈率、样本覆盖、类别失衡和高风险特征摘要"""

import logging
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import pandas as pd
import numpy as np

from ..utils import read_file, save_file, ensure_dir

logger = logging.getLogger(__name__)


# =============== 核心计算函数 ===============

def _calc_fraud_metrics(df: pd.DataFrame, label_col: str) -> Dict:
    """计算欺诈率等核心指标"""
    n = len(df)
    if n == 0:
        return {"总样本数": 0, "_empty": True}
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
    if len(df) == 0:
        return {"_empty": True}
    coverage = {}
    for col in key_cols:
        if col in df.columns:
            rate = df[col].notna() & df[col].astype(str).str.strip().ne("")
            coverage[f"{col} 覆盖率"] = f"{rate.mean():.2%}"
            coverage[f"{col} 唯一值数"] = int(df.loc[rate, col].nunique())
    return coverage


def _calc_class_imbalance(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    """分析类别失衡"""
    if len(df) == 0 or label_col not in df.columns:
        return pd.DataFrame()

    label_map = {0: "真实", 1: "欺诈", 2: "可疑", -1: "未标记"}
    counts = df[label_col].value_counts().reset_index()
    counts.columns = ["标签编码", "样本数"]
    counts["标签名称"] = counts["标签编码"].map(label_map).fillna(counts["标签编码"].astype(str))
    counts["占比"] = counts["样本数"] / counts["样本数"].sum()
    counts["占比(格式化)"] = counts["占比"].apply(lambda x: f"{x:.2%}")
    counts["失衡权重(相对欺诈)"] = counts["样本数"] / max(
        counts.loc[counts["标签编码"] == 1, "样本数"].sum(), 1)
    return counts


def _find_high_risk_features(df: pd.DataFrame, label_col: str,
                              cat_cols: List[str], num_cols: List[str],
                              top_k: int = 10) -> Dict[str, pd.DataFrame]:
    """识别高风险特征"""
    result = {}
    if len(df) == 0 or label_col not in df.columns:
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
                if row["总数"] >= 5 and row["欺诈率"] > 0.005:
                    cat_results.append({
                        "特征": col,
                        "取值": val,
                        "样本数": int(row["总数"]),
                        "欺诈数": int(row.get(1, 0)),
                        "欺诈率": row["欺诈率"],
                        "欺诈率(格式化)": f"{row['欺诈率']:.2%}",
                        "欺诈贡献": row["欺诈贡献"],
                        "欺诈贡献(格式化)": f"{row['欺诈贡献']:.2%}",
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
                "显著性判断": "显著差异" if abs(effect_size) >= 0.5
                              else ("中等差异" if abs(effect_size) >= 0.2 else "弱差异"),
            })
        except Exception as e:
            logger.debug(f"分析 {col} 失败: {e}")

    if num_results:
        num_df = pd.DataFrame(num_results).sort_values(
            "效应量(Cohen's d)", ascending=False, key=abs).head(top_k)
        result["高风险数值特征"] = num_df

    return result


def _temporal_analysis(df: pd.DataFrame, time_col: str,
                        label_col: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """时间维度分析（月度趋势 + 日趋势 + 星期）"""
    if len(df) == 0 or time_col not in df.columns or label_col not in df.columns:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    work = df[[time_col, label_col]].copy()
    work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
    work = work.dropna(subset=[time_col])
    if len(work) == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # 月度趋势（增强：按月份）
    work["月份"] = work[time_col].dt.to_period("M").astype(str)
    monthly = work.groupby("月份").agg(
        总交易数=(label_col, "count"),
        欺诈数=(label_col, lambda x: (x == 1).sum()),
        可疑数=(label_col, lambda x: (x == 2).sum()),
        真实数=(label_col, lambda x: (x == 0).sum()),
    ).reset_index()
    monthly["欺诈率"] = (monthly["欺诈数"] / monthly["总交易数"]).round(4)
    monthly["欺诈率(格式化)"] = monthly["欺诈率"].apply(lambda x: f"{x:.2%}")
    monthly["可疑率"] = (monthly["可疑数"] / monthly["总交易数"]).round(4)
    monthly["环比欺诈量变化"] = monthly["欺诈数"].pct_change().round(4)
    monthly["环比欺诈量变化(格式化)"] = monthly["环比欺诈量变化"].apply(
        lambda x: f"{x:.1%}" if pd.notna(x) else "-")

    # 日趋势
    work["日期"] = work[time_col].dt.date
    daily = work.groupby("日期").agg(
        总交易数=(label_col, "count"),
        欺诈数=(label_col, lambda x: (x == 1).sum()),
    ).reset_index()
    daily["欺诈率"] = (daily["欺诈数"] / daily["总交易数"]).round(4)

    # 星期
    work["星期"] = work[time_col].dt.dayofweek
    weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四",
                    4: "周五", 5: "周六", 6: "周日"}
    weekday = work.groupby("星期").agg(
        总交易数=(label_col, "count"),
        欺诈数=(label_col, lambda x: (x == 1).sum()),
    ).reset_index()
    weekday["星期"] = weekday["星期"].map(weekday_map)
    weekday["欺诈率"] = (weekday["欺诈数"] / weekday["总交易数"]).round(4)
    weekday["欺诈率(格式化)"] = weekday["欺诈率"].apply(lambda x: f"{x:.2%}")

    return (monthly, daily, weekday)


def _dimension_summary(df: pd.DataFrame, label_col: str,
                        dim_cols: Dict[str, str]) -> Dict[str, pd.DataFrame]:
    """通用维度汇总

    Args:
        dim_cols: {维度中文名: 列名}  例如: {"渠道": "channel", "省份": "province"}
    """
    results = {}
    if len(df) == 0 or label_col not in df.columns:
        return results

    for dim_name, col in dim_cols.items():
        if col not in df.columns:
            continue
        try:
            grouped = df.groupby(col).agg(
                总交易数=(label_col, "count"),
                欺诈数=(label_col, lambda x: (x == 1).sum()),
                可疑数=(label_col, lambda x: (x == 2).sum()),
                真实数=(label_col, lambda x: (x == 0).sum()),
                金额合计=("txn_amount",
                          lambda s: pd.to_numeric(s, errors="coerce").sum())
                if "txn_amount" in df.columns else (label_col, "count"),
            ).reset_index()
            grouped.columns = [dim_name] + list(grouped.columns[1:])
            grouped = grouped.sort_values("欺诈数", ascending=False)
            grouped["欺诈率"] = (grouped["欺诈数"] / grouped["总交易数"]).round(4)
            grouped["欺诈率(格式化)"] = grouped["欺诈率"].apply(lambda x: f"{x:.2%}")
            grouped["交易占比"] = (grouped["总交易数"] / grouped["总交易数"].sum()).round(4)
            grouped["交易占比(格式化)"] = grouped["交易占比"].apply(lambda x: f"{x:.1%}")
            grouped["欺诈贡献占比"] = (grouped["欺诈数"] / max(grouped["欺诈数"].sum(), 1)).round(4)
            grouped["欺诈贡献占比(格式化)"] = grouped["欺诈贡献占比"].apply(lambda x: f"{x:.1%}")
            # 风险等级
            grouped["风险等级"] = pd.cut(
                grouped["欺诈率"],
                bins=[-0.001, 0.005, 0.02, 0.05, 1.01],
                labels=["低", "中", "高", "极高"]
            )
            results[dim_name] = grouped
        except Exception as e:
            logger.warning(f"维度汇总 {dim_name}({col}) 失败: {e}")
    return results


# =============== Markdown 报告生成 ===============

def _generate_business_markdown(
    df: pd.DataFrame, label_col: str, time_col: str,
    metrics: Dict, monthly: pd.DataFrame,
    dim_summaries: Dict[str, pd.DataFrame],
    hr: Dict[str, pd.DataFrame],
    output_dir: str,
    primary_label: str = "",
) -> Path:
    """生成业务同事友好的 Markdown 报告"""
    lines = []
    lines.append("# 反欺诈样本分析报告（业务视角）")
    lines.append("")
    lines.append(f"**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if primary_label:
        lines.append(f"**分析口径**: 本报告基于主集 `{primary_label}` 计算；train/valid/backtest 拆分子集仅作为 Excel 补充 sheet 展示，不参与本报告指标计算。")
    lines.append("")

    # 1. 执行摘要
    lines.append("## 📌 执行摘要")
    lines.append("")
    if metrics.get("_empty") or len(df) == 0:
        lines.append("> ⚠️ **本次分析输入为空数据集，未产出有效分析结果。**")
        lines.append("> 请检查上游 import/clean/label 步骤是否正常产出样本。")
        lines.append("")
    else:
        total = metrics.get("总样本数", len(df))
        fraud_cnt = metrics.get("欺诈交易数", 0)
        fraud_rate = fraud_cnt / max(total, 1)
        genuine_cnt = metrics.get("真实交易数", 0)

        alert_icon = "🔴" if fraud_rate >= 0.05 else ("🟠" if fraud_rate >= 0.01 else "🟢")

        lines.append(f"{alert_icon} **整体概况**")
        lines.append("")
        lines.append(f"- 样本总量：**{total:,}** 笔交易")
        lines.append(f"- 确认欺诈：**{fraud_cnt:,}** 笔，占比 **{fraud_rate:.2%}**")
        lines.append(f"- 可疑交易：**{metrics.get('可疑交易数', 0):,}** 笔，占比 **{metrics.get('可疑交易数', 0) / max(total, 1):.2%}**")
        lines.append(f"- 真实交易：**{genuine_cnt:,}** 笔")
        lines.append(f"- 欺诈 vs 真实比例：1 : **{genuine_cnt / max(fraud_cnt, 1):.1f}**（正样本约为负样本的 X 倍）")
        lines.append("")

        # 风险提示
        top_alert = []
        for dim_name, dim_df in dim_summaries.items():
            if len(dim_df) > 0:
                high = dim_df[dim_df["欺诈率"] >= 0.05]
                if len(high) > 0:
                    for _, row in high.head(3).iterrows():
                        top_alert.append(f"{row.iloc[0]}（{row['欺诈贡献占比(格式化)']} 的欺诈集中在此）")
        if top_alert:
            lines.append("**⚠️ 重点关注的高风险领域**：")
            lines.append("")
            for a in top_alert[:6]:
                lines.append(f"  - {a}")
            lines.append("")

    # 2. 月度趋势
    if monthly is not None and len(monthly) > 0:
        lines.append("## 📈 月度欺诈趋势")
        lines.append("")
        lines.append("| 月份 | 总交易数 | 欺诈数 | 欺诈率 | 可疑率 | 环比变化 |")
        lines.append("|------|----------|--------|--------|--------|----------|")
        for _, row in monthly.iterrows():
            lines.append(f"| {row['月份']} | {row['总交易数']:,} | {row['欺诈数']} | "
                         f"{row.get('欺诈率(格式化)', '-')} | "
                         f"{row.get('可疑率', pd.NA) if '可疑率' in row else '-'} | "
                         f"{row.get('环比欺诈量变化(格式化)', '-')} |")
        lines.append("")

        # 趋势判断
        if len(monthly) >= 2:
            last_row = monthly.iloc[-1]
            prev_row = monthly.iloc[-2]
            diff = last_row["欺诈数"] - prev_row["欺诈数"]
            pct = (diff / max(prev_row["欺诈数"], 1)) * 100
            direction = "📈 上升" if diff > 0 else ("📉 下降" if diff < 0 else "➖ 持平")
            lines.append(f"**趋势简评**：最近月份欺诈数 {direction} {abs(diff)} 笔（{pct:.1f}%）。")
            if pct > 30:
                lines.append("❗ **警告：环比增幅超过 30%，建议排查业务异动或欺诈攻击。**")
            elif pct < -30:
                lines.append("💡 **提示：环比降幅超过 30%，可复盘近期风控策略效果。**")
            lines.append("")

    # 3. 维度汇总
    section_icons = {"渠道": "📱", "商户类别(MCC)": "🏪", "省份": "🗺️", "城市": "🏙️", "交易类型": "💳"}
    for dim_name, dim_df in dim_summaries.items():
        if len(dim_df) == 0:
            continue
        icon = section_icons.get(dim_name, "📊")
        lines.append(f"## {icon} {dim_name}维度分析")
        lines.append("")
        show_cols = [dim_name, "总交易数", "交易占比(格式化)",
                     "欺诈数", "欺诈贡献占比(格式化)", "欺诈率(格式化)", "风险等级"]
        show_cols = [c for c in show_cols if c in dim_df.columns]
        lines.append("| " + " | ".join(show_cols) + " |")
        lines.append("|" + "|".join(["------"] * len(show_cols)) + "|")

        # 只展示 Top 10（按欺诈数）
        for _, row in dim_df.head(10).iterrows():
            vals = []
            for c in show_cols:
                v = row[c]
                if isinstance(v, (int, np.integer)):
                    vals.append(f"{v:,}")
                elif isinstance(v, (float, np.floating)):
                    vals.append(f"{v:.2f}")
                else:
                    vals.append(str(v))
            lines.append("| " + " | ".join(vals) + " |")
        lines.append("")

        # 风险提示
        high_risk = dim_df[dim_df["风险等级"].isin(["高", "极高"])]
        if len(high_risk) > 0:
            lines.append(f"**⚠️ {dim_name} - 高/极高风险项**: "
                         + ", ".join(f"`{row.iloc[0]}`({row['欺诈率(格式化)']})"
                                     for _, row in high_risk.head(5).iterrows()))
            lines.append("")

    # 4. 高风险特征
    if hr:
        lines.append("## 🔍 高风险特征摘要")
        lines.append("")
        if "高风险类别特征" in hr:
            lines.append("### 类别特征（Top 8 按欺诈数）")
            lines.append("")
            df_show = hr["高风险类别特征"].head(8)
            lines.append("| 特征 | 取值 | 样本数 | 欺诈数 | 欺诈率 | 欺诈贡献 |")
            lines.append("|------|------|--------|--------|--------|----------|")
            for _, row in df_show.iterrows():
                lines.append(f"| {row['特征']} | `{row['取值']}` | {row['样本数']:,} | "
                             f"{row['欺诈数']} | {row['欺诈率(格式化)']} | {row['欺诈贡献(格式化)']} |")
            lines.append("")

        if "高风险数值特征" in hr:
            lines.append("### 数值特征（Top 6 按效应量）")
            lines.append("")
            df_show = hr["高风险数值特征"].head(6)
            lines.append("| 特征 | 欺诈均值 | 正常均值 | 差值 | 效应量 | 显著性 |")
            lines.append("|------|----------|----------|------|--------|--------|")
            for _, row in df_show.iterrows():
                eff_size = row["效应量(Cohen's d)"]
                sig = row["显著性判断"]
                lines.append(f"| {row['特征']} | {row['欺诈均值']:,} | {row['正常均值']:,} | "
                             f"{row['差值']:+,} | {eff_size} | {sig} |")
            lines.append("")

    # 5. 建议
    lines.append("## 💡 业务建议")
    lines.append("")
    if metrics.get("_empty") or len(df) == 0:
        lines.append("1. **确认数据完整性**：请先检查 import / label 流程是否成功，是否生成了有效的带标签数据集。")
    else:
        lines.append("1. **重点监控高欺诈月份**：针对欺诈数环比上升的月份，分析是否有特定促销、节假日或新产品上线因素。")
        for dim_name, dim_df in list(dim_summaries.items())[:2]:
            if len(dim_df) > 0:
                top_item = dim_df.iloc[0]
                lines.append(
                    f"2. **{dim_name}维度**：`{top_item.iloc[0]}` 贡献了 "
                    f"{top_item['欺诈贡献占比(格式化)']} 的欺诈，建议加强准入和实时监控。"
                )
        lines.append("3. **高风险特征转化**：将识别到的高风险类别/数值特征转化为规则引擎的评分项，或作为模型训练的重要输入。")
        lines.append("4. **可疑交易人工复核**：建议将可疑样本（label=2）纳入人工审核优先队列。")
    lines.append("")

    lines.append("---")
    lines.append("*本报告由信用卡欺诈样本整理器自动生成，如有疑问请联系风控数据分析团队。*")

    md_path = Path(output_dir) / "fraud_report_business.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


# =============== 主命令 ===============

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

    label_col = "fraud_label"
    time_col = args.time_col or "txn_time"
    default_cat = ["txn_type", "channel", "merchant_id", "province", "city",
                   "mcc", "currency", "txn_result", "pos_entry_mode",
                   "card_type", "issuer_bank", "acquirer_bank"]
    default_num = ["txn_amount", "risk_score", "installment", "cashback"]
    default_dim = {"月份": "_month",  # 内部特殊值，会单独处理
                   "渠道": "channel", "商户类别(MCC)": "mcc",
                   "省份": "province", "城市": "city",
                   "交易类型": "txn_type", "收单行": "acquirer_bank"}

    cat_cols = args.cat_cols or default_cat
    num_cols = args.num_cols or default_num
    key_cols = args.key_cols or ["card_no", "txn_time", "txn_amount",
                                  "merchant_id", "txn_type", "channel"]

    # 空数据集处理
    if not input_files:
        print("[提示] 未找到任何输入数据集，生成空报告后正常退出")
        _write_empty_report(output_dir, "未找到有效的带标签数据集（.pkl）")
        return 0

    # ---- 输入文件分类：主集 vs 拆分集（口径修复） ----
    # 主集：优先 transactions_labeled.pkl（完整样本集），否则第一个含 fraud_label 的
    primary_fp: Optional[str] = None
    split_fps: List[str] = []
    split_names = {"train", "valid", "backtest", "test", "holdout"}
    for fp in input_files:
        name = Path(fp).stem.lower()
        if "transactions_labeled" in name or name == "transactions_labeled":
            primary_fp = fp
            break
    if primary_fp is None:
        for fp in input_files:
            try:
                df_hint = read_file(fp)
                if "fraud_label" in df_hint.columns and len(df_hint) > 0:
                    primary_fp = fp
                    break
            except Exception:
                continue
    if primary_fp is None:
        primary_fp = input_files[0]
    for fp in input_files:
        if fp == primary_fp:
            continue
        stem = Path(fp).stem.lower().replace("__train", "").replace("__valid", "").replace("__backtest", "")
        if any(s in stem for s in split_names):
            split_fps.append(fp)

    print("=" * 60)
    print("反欺诈样本分析报告")
    print("=" * 60)
    print(f"[口径说明] 主分析集: {Path(primary_fp).name}（用于整体指标/月度趋势/维度/特征摘要）")
    if split_fps:
        print(f"[补充说明]   拆分子集: {', '.join(Path(p).name for p in split_fps)}（仅在 Excel 作为补充 sheet 展示）")
    print("=" * 60)

    excel_path = Path(output_dir) / "fraud_report.xlsx"

    all_metrics = []
    empty_count = 0

    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            # --- 概览 Sheet ---
            pd.DataFrame([
                ["报告名称", "反欺诈样本分析报告"],
                ["生成时间", pd.Timestamp.now()],
                ["主分析集", Path(primary_fp).name],
                ["输入文件数 (主+拆分)", len(input_files)],
                ["拆分补充集数", len(split_fps)],
                ["分析维度", ", ".join(default_dim.keys())],
                ["高风险特征Top", args.top_k],
                ["口径说明", "整体指标/月度趋势/维度/业务Markdown均基于主集；train/valid/backtest仅补充sheet"],
            ]).to_excel(writer, sheet_name="00_报告说明", index=False, header=False)

            # ============ 1. 主集分析 ============
            first_monthly = pd.DataFrame()
            first_dims = {}
            first_hr = {}
            first_metrics = {}

            fname = Path(primary_fp).name
            logger.info(f"[主集] 分析: {fname}")
            try:
                df = read_file(primary_fp)
            except Exception as e:
                logger.warning(f"读取主集失败 {primary_fp}: {e}")
                df = pd.DataFrame()

            is_empty = len(df) == 0
            if is_empty:
                empty_count += 1

            print(f"\n{'─' * 50}")
            print(f"[主集分析] {fname}")
            print(f"{'─' * 50}")

            # 1) 核心指标
            metrics = _calc_fraud_metrics(df, label_col)
            metrics["_file"] = fname
            metrics["_角色"] = "主集(primary)"
            all_metrics.append(metrics)
            first_metrics = metrics

            print("\n[核心指标]")
            for k, v in metrics.items():
                if not k.startswith("_"):
                    print(f"  {k}: {v}")

            # 2) 样本覆盖
            coverage = _calc_coverage(df, key_cols)
            print("\n[关键字段覆盖率]")
            for k, v in coverage.items():
                if not k.startswith("_"):
                    print(f"  {k}: {v}")

            # 3) 类别失衡
            imbalance = _calc_class_imbalance(df, label_col)
            if len(imbalance) > 0:
                print("\n[类别分布]")
                show_cols = [c for c in ["标签编码", "标签名称", "样本数", "占比(格式化)", "失衡权重(相对欺诈)"] if c in imbalance.columns]
                print(imbalance[show_cols].to_string(index=False))
                imbalance.to_excel(writer, sheet_name="02_类别分布_主集", index=False)
            pd.DataFrame([[k, v] for k, v in metrics.items() if not k.startswith("_")],
                         columns=["指标", "值"]).to_excel(
                writer, sheet_name="01_核心指标_主集", index=False)

            # 4) 高风险特征（主集完整）
            hr = _find_high_risk_features(df, label_col, cat_cols, num_cols, args.top_k)
            first_hr = hr
            for hk, hv in hr.items():
                print(f"\n[高风险特征] {hk} Top{args.top_k}:")
                if hk == "高风险类别特征":
                    show_cols = ["特征", "取值", "样本数", "欺诈数", "欺诈率(格式化)", "欺诈贡献(格式化)"]
                else:
                    show_cols = ["特征", "欺诈均值", "正常均值", "差值", "效应量(Cohen's d)", "显著性判断"]
                show_cols = [c for c in show_cols if c in hv.columns]
                print(hv[show_cols].to_string(index=False))
                hv.to_excel(writer, sheet_name=f"05_Feature_{hk[:8]}_主集", index=False)

            # 5) 月度趋势 + 维度汇总（主集稳定输出）
            monthly, daily, weekday = _temporal_analysis(df, time_col, label_col)
            first_monthly = monthly

            dim_cols = {k: v for k, v in default_dim.items() if v != "_month"}
            dim_summaries = _dimension_summary(df, label_col, dim_cols)
            first_dims = dim_summaries

            for dim_name, dim_df in dim_summaries.items():
                if len(dim_df) > 0:
                    print(f"\n[维度汇总] {dim_name} (Top 10):")
                    show_cols = [dim_name, "总交易数", "交易占比(格式化)",
                                 "欺诈数", "欺诈率(格式化)", "风险等级"]
                    show_cols = [c for c in show_cols if c in dim_df.columns]
                    print(dim_df[show_cols].head(10).to_string(index=False))
                    safe = dim_name.replace("/", "_").replace("(", "").replace(")", "")[:12]
                    dim_df.to_excel(writer, sheet_name=f"04_Dim_{safe}_主集", index=False)

            if len(monthly) > 0:
                print(f"\n[月度趋势] (共 {len(monthly)} 个月):")
                show_cols = [c for c in ["月份", "总交易数", "欺诈数", "欺诈率(格式化)", "可疑率", "环比欺诈量变化(格式化)"] if c in monthly.columns]
                print(monthly[show_cols].to_string(index=False))
                monthly.to_excel(writer, sheet_name="03_月度趋势_主集", index=False)
            if len(daily) > 0:
                daily.to_excel(writer, sheet_name="Z9_每日趋势_主集", index=False)
            if len(weekday) > 0:
                print("\n[星期分布]:")
                print(weekday[["星期", "总交易数", "欺诈数", "欺诈率(格式化)"]].to_string(index=False))
                weekday.to_excel(writer, sheet_name="Z8_星期分布_主集", index=False)

            # 主集覆盖率 sheet
            pd.DataFrame([[k, v] for k, v in coverage.items() if not k.startswith("_")],
                         columns=["字段", "覆盖率"]).to_excel(
                writer, sheet_name="Z7_覆盖率_主集", index=False)

            # ============ 2. 拆分集分析（仅补充 Sheet，不进业务 Markdown） ============
            for split_idx, sfp in enumerate(split_fps, 1):
                sname = Path(sfp).name
                logger.info(f"[拆分集] 处理: {sname}")
                try:
                    sdf = read_file(sfp)
                except Exception as e:
                    logger.warning(f"读取拆分集失败 {sfp}: {e}")
                    continue

                s_empty = len(sdf) == 0
                if s_empty:
                    empty_count += 1
                sm = _calc_fraud_metrics(sdf, label_col)
                sm["_file"] = sname
                sm["_角色"] = "拆分集(split)"
                all_metrics.append(sm)
                srole = Path(sfp).stem
                # 核心指标 sheet
                pd.DataFrame([[k, v] for k, v in sm.items() if not k.startswith("_")],
                             columns=["指标", "值"]).to_excel(
                    writer, sheet_name=f"S{split_idx}_指标_{srole[:12]}", index=False)
                simb = _calc_class_imbalance(sdf, label_col)
                if len(simb) > 0:
                    simb.to_excel(writer, sheet_name=f"S{split_idx}_标签分布_{srole[:10]}", index=False)
                # 拆分集欺诈率对比：一行对比表追加到汇总

            # --- 拆分集欺诈率对比 Sheet ---
            if split_fps:
                rows_cmp = []
                for m in all_metrics:
                    # 统一数值键名对齐 (支持 _calc_fraud_metrics 的返回键
                    total = m.get("总样本数", 0)
                    fraud_n = m.get("欺诈交易数", 0)
                    suspect_n = m.get("可疑交易数", 0)
                    genuine_n = m.get("真实交易数", 0)
                    fr = round(fraud_n / max(total, 1) * 100, 2)
                    rows_cmp.append({
                        "数据集": m.get("_file", ""),
                        "角色": m.get("_角色", ""),
                        "总样本数": total,
                        "欺诈数": fraud_n,
                        "可疑数": suspect_n,
                        "真实数": genuine_n,
                        "欺诈率(%)": fr,
                    })
                pd.DataFrame(rows_cmp).to_excel(
                    writer, sheet_name="00_拆分集对比", index=False)

            # --- 汇总 Sheet ---
            if all_metrics:
                summary_df = pd.DataFrame(all_metrics).rename(columns={"_file": "文件", "_角色": "角色"})
                summary_df.to_excel(writer, sheet_name="01_汇总", index=False)

            # --- 空数据集说明 ---
            if empty_count > 0:
                pd.DataFrame([
                    ["空数据集数量", empty_count],
                    ["说明", "以下输入文件为空 DataFrame，未参与分析"],
                    ["空数据集文件", "\n".join(m.get("_file", "?") for m in all_metrics if m.get("_empty") or m.get("总样本数", -1) == 0)],
                ]).to_excel(writer, sheet_name="ZZ_空数据集说明", index=False, header=False)
    except Exception as e:
        logger.exception(f"写 Excel 报告失败: {e}")
        return 1

    # 生成 Markdown 业务报告（明确基于主集）
    md_path = _generate_business_markdown(
        df, label_col, time_col, first_metrics, first_monthly,
        first_dims, first_hr, output_dir,
        primary_label=Path(primary_fp).name,
    )

    # 文本报告
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
        if empty_count > 0:
            f.write(f"\n[提示] 包含 {empty_count} 个空数据集\n")

    print(f"\n{'=' * 60}")
    if empty_count == len(input_files):
        print("[提示] 所有输入数据集均为空，已生成空报告说明")
    print(f"[完成] 报告生成完成")
    print(f"  Excel报告: {excel_path}")
    print(f"  文本报告: {txt_path}")
    print(f"  业务Markdown报告: {md_path}")
    return 0


def _write_empty_report(output_dir: str, reason: str) -> None:
    """生成空报告说明文件"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    p = Path(output_dir) / "EMPTY_REPORT_NOTE.txt"
    p.write_text(
        f"空报告说明\n"
        f"==========\n"
        f"时间: {pd.Timestamp.now()}\n"
        f"原因: {reason}\n\n"
        f"可能的原因:\n"
        f"  1. 上游 import/clean/label 步骤无输入或产生空结果\n"
        f"  2. --inputs 指定的文件路径有误\n"
        f"  3. 数据目录配置错误\n"
        f"\n处理建议:\n"
        f"  - 检查 data/imported、data/cleaned、data/labeled 下是否有数据\n"
        f"  - 重新运行 pipeline 从头生成\n",
        encoding="utf-8"
    )
    # 生成空 Excel 占位
    try:
        with pd.ExcelWriter(Path(output_dir) / "fraud_report.xlsx", engine="openpyxl") as writer:
            pd.DataFrame([
                ["报告状态", "空数据集"],
                ["原因", reason],
                ["生成时间", str(pd.Timestamp.now())],
            ]).to_excel(writer, sheet_name="说明", index=False, header=False)
    except Exception:
        pass


def register_subparser(subparsers) -> None:
    """注册 report 子命令"""
    p = subparsers.add_parser("report",
                              help="输出欺诈率、样本覆盖、类别失衡和高风险特征摘要（含多维度分析和业务Markdown）")
    p.add_argument("-i", "--inputs", nargs="+", help="输入文件列表")
    p.add_argument("-d", "--data-dir", default="./data",
                   help="数据根目录 (默认: ./data)")
    p.add_argument("-o", "--output-dir", default="./data/reports",
                   help="输出目录 (默认: ./data/reports)")
    p.add_argument("--time-col", default="txn_time", help="时间列名")
    p.add_argument("--cat-cols", nargs="+", help="类别特征列名列表")
    p.add_argument("--num-cols", nargs="+", help="数值特征列名列表")
    p.add_argument("--key-cols", nargs="+", help="关键字段（用于覆盖率检查）")
    p.add_argument("--top-k", type=int, default=15, help="Top K 高风险特征")
    p.set_defaults(func=cmd_report)
