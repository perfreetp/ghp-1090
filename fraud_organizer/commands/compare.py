"""跨批次对比分析：给两个历史产出，输出环比分析 Excel + 业务 Markdown"""

import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field

import pandas as pd

from ..utils import ensure_dir, read_file, save_file
from . import runner as _runner_mod

logger = logging.getLogger(__name__)


DIMENSIONS = [
    ("月度", "_month"),
    ("渠道", "channel"),
    ("商户类别(MCC)", "mcc"),
    ("省份", "province"),
    ("城市", "city"),
    ("交易类型", "txn_type"),
    ("收单行", "acquirer_bank"),
]


def _df_to_markdown(df: pd.DataFrame) -> str:
    """DataFrame 转 Markdown 表格（无需 tabulate 依赖）"""
    if len(df) == 0:
        return "> (无数据)"
    cols = list(df.columns)
    lines: List[str] = []
    lines.append("| " + " | ".join(str(c) for c in cols) + " |")
    lines.append("|" + "|".join(["------"] * len(cols)) + "|")
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


@dataclass
class CompareResult:
    """对比结果"""
    base_tag: str = ""
    comp_tag: str = ""
    overall: Dict[str, Any] = field(default_factory=dict)
    dimension_diffs: Dict[str, pd.DataFrame] = field(default_factory=dict)
    output_files: Dict[str, str] = field(default_factory=dict)


def _resolve_labeled_dir(src: str) -> Optional[str]:
    """解析对比来源：RUN_ID / 输出根目录 / labeled 目录 / pkl 文件
    返回：labeled 目录路径
    """
    src = str(src)
    # 1) 直接是 pkl 文件
    p = Path(src)
    if p.is_file() and p.suffix in (".pkl", ".pickle", ".csv", ".xlsx"):
        return str(p.parent)
    # 2) 已经是 labeled 目录
    if p.is_dir():
        lp = p / "transactions_labeled.pkl"
        if lp.exists():
            return str(p)
        # 3) 可能是输出根目录
        sub = p / "labeled" / "transactions_labeled.pkl"
        if sub.exists():
            return str(p / "labeled")
    # 4) 可能是 RUN_ID，查历史
    try:
        hist = _runner_mod._read_history(limit=500)
        for r in hist:
            rid = r.get("run_id", "")
            if rid == src or rid.startswith(src):
                oroot = r.get("output_root", "")
                if oroot:
                    sub = Path(oroot) / "labeled" / "transactions_labeled.pkl"
                    if sub.exists():
                        return str(sub.parent)
    except Exception:
        pass
    return None


def _load_df(src_dir: str) -> Tuple[pd.DataFrame, str]:
    """加载数据集，返回 (df, 标签)"""
    p = Path(src_dir) / "transactions_labeled.pkl"
    if not p.exists():
        # fallback: 目录下第一个 pkl
        alts = list(Path(src_dir).glob("*.pkl"))
        p = alts[0] if alts else None
    if p is None or not p.exists():
        return pd.DataFrame(), str(Path(src_dir).name)
    df = read_file(str(p))
    tag = Path(src_dir).parent.name or p.parent.parent.name or src_dir
    return df, tag


def _overall(df: pd.DataFrame, tag: str) -> Dict[str, Any]:
    total = len(df)
    fraud = suspect = genuine = 0
    fraud_rate = 0.0
    if "fraud_label" in df.columns and total > 0:
        vc = df["fraud_label"].value_counts(dropna=False).to_dict()
        fraud = int(vc.get(1, 0))
        suspect = int(vc.get(2, 0))
        genuine = int(vc.get(0, 0))
        fraud_rate = fraud / total * 100 if total > 0 else 0.0
    return {
        "标签": tag,
        "总交易数": total,
        "欺诈数": fraud,
        "可疑数": suspect,
        "真实数": genuine,
        "欺诈率(%)": round(fraud_rate, 4),
    }


def _add_month(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0 or "txn_time" not in df.columns:
        df = df.copy()
        df["_month"] = pd.Series([], dtype=str)
        return df
    df = df.copy()
    t = pd.to_datetime(df["txn_time"], errors="coerce")
    df["_month"] = t.dt.strftime("%Y-%m")
    return df


def _dim_summary(df: pd.DataFrame, dim_col: str,
                 label_col: str = "fraud_label") -> pd.DataFrame:
    """单维度汇总（与 reporter 一致口径）"""
    if len(df) == 0 or dim_col not in df.columns:
        return pd.DataFrame(columns=[dim_col, "总交易数", "欺诈数", "欺诈率(%)"])
    g = df.groupby(dim_col, dropna=False)
    total = g.size().rename("总交易数")
    fraud = g[label_col].apply(lambda s: int((s == 1).sum())).rename("欺诈数")
    out = pd.concat([total, fraud], axis=1).reset_index()
    out["欺诈率(%)"] = (out["欺诈数"] / out["总交易数"] * 100).round(4)
    out = out.sort_values("欺诈数", ascending=False)
    return out


def _dim_diff(base: pd.DataFrame, comp: pd.DataFrame, dim_col: str,
              base_tag: str, comp_tag: str) -> pd.DataFrame:
    """两个批次同一维度做 diff：返回差量表"""
    def _rename(df, tag):
        cols = {
            "总交易数": f"{tag}_总交易数",
            "欺诈数": f"{tag}_欺诈数",
            "欺诈率(%)": f"{tag}_欺诈率(%)",
        }
        return df.rename(columns=cols)

    b = _rename(_dim_summary(base, dim_col), base_tag)
    c = _rename(_dim_summary(comp, dim_col), comp_tag)
    key_col = dim_col
    merged = b.merge(c, on=key_col, how="outer").fillna(0)

    bt, ct = base_tag, comp_tag
    merged[f"总交易数_差量"] = merged[f"{ct}_总交易数"] - merged[f"{bt}_总交易数"]
    merged[f"欺诈数_差量"] = merged[f"{ct}_欺诈数"] - merged[f"{bt}_欺诈数"]
    merged[f"欺诈率_差量(pct)"] = (merged[f"{ct}_欺诈率(%)"]
                                   - merged[f"{bt}_欺诈率(%)"]).round(4)

    def _pct_change(new, old):
        try:
            if old == 0 and new == 0:
                return 0.0
            if old == 0:
                return float("inf") if new > 0 else 0.0
            return round((new - old) / abs(old) * 100, 2)
        except Exception:
            return 0.0

    merged[f"欺诈数_环比(%)"] = merged.apply(
        lambda r: _pct_change(r[f"{ct}_欺诈数"], r[f"{bt}_欺诈数"]), axis=1)

    merged = merged.sort_values(f"欺诈数_差量", ascending=False)
    return merged


def _build_overall_diff(base_row: Dict, comp_row: Dict,
                        base_tag: str, comp_tag: str) -> pd.DataFrame:
    def _chg(new, old):
        if old == 0 and new == 0:
            return 0.0
        if old == 0:
            return float("inf") if new > 0 else 0.0
        return round((new - old) / abs(old) * 100, 2)

    rows = []
    for k in ["总交易数", "欺诈数", "可疑数", "真实数"]:
        bv = base_row.get(k, 0) or 0
        cv = comp_row.get(k, 0) or 0
        rows.append({
            "指标": k,
            f"{base_tag}": bv,
            f"{comp_tag}": cv,
            "差量": cv - bv,
            "环比(%)": _chg(cv, bv),
        })
    bfr = base_row.get("欺诈率(%)", 0.0) or 0.0
    cfr = comp_row.get("欺诈率(%)", 0.0) or 0.0
    rows.append({
        "指标": "欺诈率(%)",
        f"{base_tag}": bfr,
        f"{comp_tag}": cfr,
        "差量(pct)": round(cfr - bfr, 4),
        "环比(%)": _chg(cfr, bfr),
    })
    return pd.DataFrame(rows)


def _write_excel(result: CompareResult, output_dir: str) -> str:
    ensure_dir(output_dir)
    out_path = Path(output_dir) / "batch_compare.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        pd.DataFrame([result.overall["base"], result.overall["comp"]]).to_excel(
            w, sheet_name="0_整体概览", index=False)
        result.overall["diff_df"].to_excel(w, sheet_name="1_整体差量", index=False)
        for dim_name, df in result.dimension_diffs.items():
            safe = dim_name.replace("/", "_").replace("(", "").replace(")", "")[:25]
            df.to_excel(w, sheet_name=f"{safe}_差量", index=False)
    return str(out_path)


def _write_markdown(result: CompareResult, output_dir: str) -> str:
    bt, ct = result.base_tag, result.comp_tag
    lines: List[str] = []
    lines.append("# 跨批次对比分析报告（业务视角）")
    lines.append("")
    lines.append(f"- **基准批次 (A)**: `{bt}`")
    lines.append(f"- **对比批次 (B)**: `{ct}`")
    lines.append(f"- **生成时间**: {pd.Timestamp.now()}")
    lines.append("")

    # ---- 整体概览 ----
    lines.append("## 1. 整体概览")
    lines.append("")
    ov = result.overall
    base_row, comp_row = ov["base"], ov["comp"]
    diff_df = ov["diff_df"]
    b_fr = base_row.get("欺诈率(%)", 0.0) or 0.0
    c_fr = comp_row.get("欺诈率(%)", 0.0) or 0.0
    fr_diff = round(c_fr - b_fr, 4)

    level_emoji = "🟢" if abs(fr_diff) < 0.1 else ("🟠" if abs(fr_diff) < 0.5 else "🔴")
    direction = "上升" if fr_diff > 0 else ("下降" if fr_diff < 0 else "持平")
    lines.append(f"{level_emoji} **欺诈率变化: {b_fr:.2f}% → {c_fr:.2f}% ({direction} {abs(fr_diff):.4f} pct)**")
    lines.append("")
    lines.append(_df_to_markdown(diff_df))
    lines.append("")

    # ---- 维度差量 ----
    lines.append("## 2. 各维度差量（Top 变化项）")
    lines.append("")
    for dim_name, df in result.dimension_diffs.items():
        if len(df) == 0:
            continue
        lines.append(f"### {dim_name}")
        lines.append("")
        # 正增 Top 5 + 负增 Top 3
        pos = df[df["欺诈数_差量"] > 0].head(5)
        neg = df[df["欺诈数_差量"] < 0].head(3)
        if len(pos) == 0 and len(neg) == 0:
            lines.append("> 该维度欺诈数无变化")
            lines.append("")
            continue
        key_col = df.columns[0]
        cols_show = [key_col, f"{bt}_欺诈数", f"{ct}_欺诈数",
                     "欺诈数_差量", "欺诈数_环比(%)",
                     f"{bt}_欺诈率(%)", f"{ct}_欺诈率(%)", "欺诈率_差量(pct)"]
        cols_ok = [c for c in cols_show if c in df.columns]
        if len(pos) > 0:
            lines.append("**欺诈数上升 Top：**")
            lines.append("")
            lines.append(_df_to_markdown(pos[cols_ok]))
            lines.append("")
        if len(neg) > 0:
            lines.append("**欺诈数下降 Top：**")
            lines.append("")
            lines.append(_df_to_markdown(neg[cols_ok]))
            lines.append("")

    # ---- 建议 ----
    lines.append("## 3. 业务建议")
    lines.append("")
    tips: List[str] = []
    if fr_diff > 0.3:
        tips.append(f"1. **欺诈率攀升预警**：{bt} → {ct} 欺诈率上升 {fr_diff:.4f} pct，建议排查近期是否有新的攻击模式。")
    elif fr_diff < -0.3:
        tips.append(f"1. **策略效果复盘**：欺诈率下降 {abs(fr_diff):.4f} pct，建议对比策略调整前后差异，固化有效规则。")
    else:
        tips.append("1. **整体稳定**：欺诈率变动在 ±0.3 pct 以内，维持现有监控即可。")
    # 各维度最大异动
    for dim_name, df in result.dimension_diffs.items():
        if len(df) == 0:
            continue
        key_col = df.columns[0]
        top_up = df[df["欺诈数_差量"] > 0].nlargest(1, "欺诈数_差量")
        if len(top_up) > 0:
            r = top_up.iloc[0]
            if r["欺诈数_差量"] >= 3:
                tips.append(f"- **{dim_name}异动**: `{r[key_col]}` 欺诈数 +{int(r['欺诈数_差量'])}，建议重点监控。")
    if len(tips) == 1:
        tips.append("2. 各维度欺诈分布较稳定，建议按常规节奏复核。")
    lines.extend(tips)
    lines.append("")
    lines.append("---")
    lines.append("*本报告由信用卡欺诈样本整理器自动生成。*")

    out_path = Path(output_dir) / "batch_compare_business.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return str(out_path)


def cmd_compare(args: argparse.Namespace) -> int:
    """执行跨批次对比"""
    base_src = args.base
    comp_src = args.comp
    output_dir = ensure_dir(args.output_dir)

    base_dir = _resolve_labeled_dir(base_src)
    comp_dir = _resolve_labeled_dir(comp_src)

    if not base_dir:
        print(f"[错误] 无法解析基准批次: {base_src}")
        print("       支持：RUN_ID / 输出根目录 / labeled目录 / transactions_labeled.pkl 路径")
        return 1
    if not comp_dir:
        print(f"[错误] 无法解析对比批次: {comp_src}")
        return 1

    print(f"基准批次 -> {base_dir}")
    print(f"对比批次 -> {comp_dir}")

    base_df, base_tag = _load_df(base_dir)
    comp_df, comp_tag = _load_df(comp_dir)
    # 若同名，加后缀区分
    if base_tag == comp_tag:
        base_tag = f"A_{base_tag}"
        comp_tag = f"B_{comp_tag}"

    # 加月份
    base_df_m = _add_month(base_df)
    comp_df_m = _add_month(comp_df)

    overall_base = _overall(base_df_m, base_tag)
    overall_comp = _overall(comp_df_m, comp_tag)
    overall_diff = _build_overall_diff(overall_base, overall_comp, base_tag, comp_tag)

    result = CompareResult(
        base_tag=base_tag, comp_tag=comp_tag,
        overall={
            "base": overall_base,
            "comp": overall_comp,
            "diff_df": overall_diff,
        }
    )

    # 维度差量
    for dim_name, dim_col in DIMENSIONS:
        if dim_col == "_month":
            df_diff = _dim_diff(base_df_m, comp_df_m, dim_col, base_tag, comp_tag)
        else:
            df_diff = _dim_diff(base_df, comp_df, dim_col, base_tag, comp_tag)
        if len(df_diff) > 0:
            result.dimension_diffs[dim_name] = df_diff

    # 输出
    xlsx = _write_excel(result, output_dir)
    md = _write_markdown(result, output_dir)
    result.output_files = {"excel": xlsx, "markdown": md}

    print("\n" + "=" * 70)
    print(f"[跨批次对比完成] {base_tag} <-> {comp_tag}")
    print("=" * 70)
    print(overall_diff.to_string(index=False))
    print("-" * 70)
    for dim_name, df in result.dimension_diffs.items():
        print(f"\n[{dim_name} 变化 Top 3]")
        key_col = df.columns[0]
        cols_show = [key_col, "欺诈数_差量", "欺诈率_差量(pct)"]
        cols_ok = [c for c in cols_show if c in df.columns]
        print(df.nlargest(3, "欺诈数_差量")[cols_ok].to_string(index=False))
    print("-" * 70)
    print(f"Excel对比报告 : {xlsx}")
    print(f"业务Markdown   : {md}")
    print("=" * 70)
    return 0


def register_subparser(subparsers) -> None:
    """注册 compare / diff 子命令"""
    p = subparsers.add_parser(
        "compare", aliases=["diff", "cmp"],
        help="跨批次环比对比（欺诈率/月度/渠道/MCC/地区等维度）",
        description="""
示例:
  fraud-org diff --base ./output/A --comp ./output/B
  fraud-org compare --base 20241001_xxxx --comp 20241101_yyyy -o ./compare_result
  fraud-org cmp --base ./old/labeled --comp ./new/labeled
""")
    p.add_argument("-b", "--base", required=True,
                   help="基准批次（支持 RUN_ID / 输出根目录 / labeled目录 / pkl文件）")
    p.add_argument("-c", "--comp", required=True,
                   help="对比批次（同基准批次）")
    p.add_argument("-o", "--output-dir", default="./data/compare",
                   help="对比报告输出目录")
    p.set_defaults(func=cmd_compare)
