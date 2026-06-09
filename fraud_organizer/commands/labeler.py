"""label 命令：按拒付结果、人工结论和规则命中生成标签"""

import logging
import argparse
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from ..models import LabelResult, FraudLabel
from ..utils import read_file, save_file, ensure_dir

logger = logging.getLogger(__name__)


def _parse_chargeback_result(value) -> Optional[int]:
    """解析拒付结果 -> 标签"""
    if pd.isna(value):
        return None
    s = str(value).strip()
    fraud_markers = [
        "欺诈", "确认欺诈", "商户败诉", "持卡人胜诉", "拒付成立",
        "chargeback", "fraud", "guilty", "lost", "true", "1", "是",
    ]
    genuine_markers = [
        "真实交易", "商户胜诉", "持卡人败诉", "拒付不成立", "正常",
        "genuine", "won", "false", "0", "否",
    ]
    s_lower = s.lower()
    for m in fraud_markers:
        if m.lower() in s_lower:
            return FraudLabel.FRAUD.value
    for m in genuine_markers:
        if m.lower() in s_lower:
            return FraudLabel.GENUINE.value
    return None


def _parse_manual_result(value) -> Optional[int]:
    """解析人工结论 -> 标签"""
    if pd.isna(value):
        return None
    s = str(value).strip()
    fraud_markers = [
        "欺诈", "确认欺诈", "虚假交易", "盗刷", "盗用", "风控通过-欺诈",
        "fraud", "确认是欺诈", "可疑欺诈",
    ]
    genuine_markers = [
        "真实", "正常交易", "本人交易", "持卡人确认", "放行",
        "genuine", "legitimate", "真实交易",
    ]
    suspicious_markers = [
        "可疑", "待确认", "高风险", "无法核实", "suspicious",
    ]
    s_lower = s.lower()
    for m in fraud_markers:
        if m.lower() in s_lower:
            return FraudLabel.FRAUD.value
    for m in suspicious_markers:
        if m.lower() in s_lower:
            return FraudLabel.SUSPICIOUS.value
    for m in genuine_markers:
        if m.lower() in s_lower:
            return FraudLabel.GENUINE.value
    return None


def _check_blacklist(df: pd.DataFrame, bl_df: Optional[pd.DataFrame],
                     entity_col: str, value_col: str) -> pd.Series:
    """检查是否在黑名单中"""
    if bl_df is None or entity_col not in bl_df.columns:
        return pd.Series([False] * len(df), index=df.index)
    bl_sub = bl_df[bl_df["entity_type"].astype(str).str.lower() == entity_col.lower()]
    if len(bl_sub) == 0 or value_col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    bl_values = set(bl_sub["entity_value"].astype(str))
    return df[value_col].astype(str).isin(bl_values)


def _parse_rule_hit(value, high_risk_rules: set) -> Optional[int]:
    """解析规则命中"""
    if pd.isna(value) or not str(value).strip():
        return None
    rules = str(value).split(",") if "," in str(value) else str(value).split("|")
    rules = [r.strip() for r in rules]
    high_hit = any(r in high_risk_rules for r in rules)
    any_hit = len(rules) > 0
    if high_hit:
        return FraudLabel.SUSPICIOUS.value
    if any_hit:
        return None
    return None


def cmd_label(args: argparse.Namespace) -> int:
    """执行 label 命令"""
    data_dir = args.data_dir or "./data"
    output_dir = ensure_dir(args.output_dir)

    txn_file = args.input
    if not txn_file:
        p = Path(data_dir) / "cleaned" / "transactions_clean.pkl"
        if p.exists():
            txn_file = str(p)
        else:
            p2 = Path(data_dir) / "imported" / "transactions_raw.pkl"
            if p2.exists():
                txn_file = str(p2)
            else:
                print("[提示] 未找到交易文件，生成空标签说明后正常退出")
                _write_empty_label(output_dir, "未找到交易输入文件 "
                                   "(cleaned/transactions_clean.pkl 或 "
                                   "imported/transactions_raw.pkl)")
                return 0

    logger.info(f"读取交易数据: {txn_file}")
    df = read_file(txn_file)

    # ---- 空数据集处理 ----
    if len(df) == 0:
        print("[提示] 交易数据集为空，生成空标签结果后正常退出")
        _write_empty_label(output_dir,
                           f"输入交易数据集 ({Path(txn_file).name}) 行数为 0")
        # 写一个空的带标签 DataFrame 方便下游步骤衔接
        empty_df = df.copy()
        empty_df["fraud_label"] = []
        empty_df["label_source"] = []
        save_file(empty_df, str(Path(output_dir) / "transactions_labeled.pkl"))
        return 0

    # 读取拒付数据
    cb_df = None
    if args.chargebacks:
        cb_df = read_file(args.chargebacks)
    else:
        cb_path = Path(data_dir) / "imported" / "chargebacks_raw.pkl"
        if cb_path.exists():
            cb_df = read_file(str(cb_path))

    # 读取黑名单
    bl_df = None
    bl_path = Path(data_dir) / "imported" / "blacklists_raw.pkl"
    if bl_path.exists():
        bl_df = read_file(str(bl_path))

    result = LabelResult(total=len(df))

    # 标签来源记录
    label_from_cb = pd.Series([None] * len(df), index=df.index, dtype="Int64")
    label_from_manual = pd.Series([None] * len(df), index=df.index, dtype="Int64")
    label_from_rule = pd.Series([None] * len(df), index=df.index, dtype="Int64")
    label_from_bl = pd.Series([False] * len(df), index=df.index)

    # 1. 拒付标签
    if cb_df is not None and "txn_id" in cb_df.columns and "chargeback_result" in cb_df.columns:
        logger.info("应用拒付标签...")
        cb_map = {}
        for _, row in cb_df.iterrows():
            lbl = _parse_chargeback_result(row.get("chargeback_result"))
            if lbl is not None:
                cb_map[str(row["txn_id"])] = lbl
        if "txn_id" in df.columns:
            mask = df["txn_id"].astype(str).isin(cb_map)
            label_from_cb[mask] = df.loc[mask, "txn_id"].astype(str).map(cb_map).astype("Int64")
            result.from_chargeback = label_from_cb.notna().sum()
            logger.info(f"  从拒付获取标签: {result.from_chargeback}")

    # 2. 人工审核标签
    if "manual_result" in df.columns:
        logger.info("应用人工审核标签...")
        mask = df["manual_result"].notna()
        label_from_manual[mask] = df.loc[mask, "manual_result"].apply(
            _parse_manual_result).astype("Int64")
        result.from_manual = label_from_manual.notna().sum()
        logger.info(f"  从人工审核获取标签: {result.from_manual}")

    # 3. 黑名单标签
    if bl_df is not None:
        logger.info("检查黑名单命中...")
        bl_card = _check_blacklist(df, bl_df, "card", "card_no")
        bl_phone = _check_blacklist(df, bl_df, "phone", "phone")
        bl_id = _check_blacklist(df, bl_df, "id_card", "id_card")
        bl_merchant = _check_blacklist(df, bl_df, "merchant", "merchant_id")
        label_from_bl = bl_card | bl_phone | bl_id | bl_merchant
        result.from_rule += int(label_from_bl.sum())
        logger.info(f"  黑名单命中: {label_from_bl.sum()}")

    # 4. 规则命中标签
    if "rule_hit" in df.columns:
        logger.info("应用规则命中标签...")
        high_risk = set(args.high_risk_rules or [])
        mask = df["rule_hit"].notna() & df["rule_hit"].astype(str).str.strip().ne("")
        label_from_rule[mask] = df.loc[mask, "rule_hit"].apply(
            lambda x: _parse_rule_hit(x, high_risk)).astype("Int64")
        # 规则命中 + 黑名单合并
        bl_fraud = FraudLabel.SUSPICIOUS.value if not args.blacklist_as_fraud else FraudLabel.FRAUD.value
        mask_bl = label_from_bl & label_from_rule.isna()
        label_from_rule[mask_bl] = bl_fraud
        result.from_rule = max(result.from_rule, int(label_from_rule.notna().sum()))

    # 5. 综合标签（优先级：拒付 > 人工 > 规则/黑名单）
    logger.info("合并标签 (优先级: 拒付 > 人工 > 规则)...")
    final_labels = pd.Series([FraudLabel.UNKNOWN.value] * len(df),
                             index=df.index, dtype="Int64")

    # 先应用规则
    mask = label_from_rule.notna() & final_labels.eq(FraudLabel.UNKNOWN.value)
    final_labels[mask] = label_from_rule[mask]

    # 再应用人工（覆盖规则）
    mask = label_from_manual.notna()
    final_labels[mask] = label_from_manual[mask]

    # 最后应用拒付（最高优先级）
    mask = label_from_cb.notna()
    final_labels[mask] = label_from_cb[mask]

    # 默认：未命中任何规则的为真实
    if args.default_genuine:
        mask = final_labels.eq(FraudLabel.UNKNOWN.value)
        final_labels[mask] = FraudLabel.GENUINE.value

    # 黑名单命中但无其他标签的，升级为可疑
    if not args.default_genuine:
        mask = label_from_bl & final_labels.eq(FraudLabel.UNKNOWN.value)
        final_labels[mask] = FraudLabel.SUSPICIOUS.value

    df["fraud_label"] = final_labels.astype(int)
    df["label_source"] = "unknown"
    df.loc[label_from_cb.notna(), "label_source"] = "chargeback"
    df.loc[label_from_manual.notna() & label_from_cb.isna(), "label_source"] = "manual"
    rule_mask = label_from_rule.notna() & label_from_cb.isna() & label_from_manual.isna()
    df.loc[rule_mask, "label_source"] = "rule"
    df.loc[label_from_bl & (df["label_source"] == "unknown"), "label_source"] = "blacklist"

    result.genuine = int((df["fraud_label"] == FraudLabel.GENUINE.value).sum())
    result.fraud = int((df["fraud_label"] == FraudLabel.FRAUD.value).sum())
    result.suspicious = int((df["fraud_label"] == FraudLabel.SUSPICIOUS.value).sum())
    result.unknown = int((df["fraud_label"] == FraudLabel.UNKNOWN.value).sum())

    # 保存
    out_path = Path(output_dir) / "transactions_labeled.pkl"
    save_file(df, str(out_path))

    report_path = Path(output_dir) / "label_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(result.summary())
        f.write("\n\n标签来源分布:\n")
        f.write(df["label_source"].value_counts().to_string())

    print(result.summary())
    print("\n标签来源分布:")
    print(df["label_source"].value_counts().to_string())
    print(f"\n[完成] 标签生成完成。输出: {out_path}")
    return 0


def _write_empty_label(output_dir: str, reason: str) -> None:
    """生成空标签说明文件"""
    from pathlib import Path as _Path
    _Path(output_dir).mkdir(parents=True, exist_ok=True)
    p = _Path(output_dir) / "EMPTY_LABEL_NOTE.txt"
    p.write_text(
        f"空标签说明\n"
        f"==========\n"
        f"时间: {pd.Timestamp.now()}\n"
        f"原因: {reason}\n\n"
        f"对下游的影响:\n"
        f"  - 输出 transactions_labeled.pkl 为空 DataFrame\n"
        f"  - profile/split/report/export 可正常运行，将识别为空数据集并给出提示\n"
        f"\n处理建议:\n"
        f"  - 检查上游 import 是否成功读取了交易文件\n"
        f"  - 检查 clean 是否因字段校验失败而未产出数据\n"
        f"  - 检查输入文件本身是否为空\n",
        encoding="utf-8"
    )
    # 生成空报告
    report_path = _Path(output_dir) / "label_report.txt"
    report_path.write_text(
        "=== 标签生成摘要 ===\n"
        f"总样本数: 0 (空数据集)\n"
        f"原因: {reason}\n",
        encoding="utf-8"
    )


def register_subparser(subparsers) -> None:
    """注册 label 子命令"""
    p = subparsers.add_parser("label", help="按拒付结果、人工结论和规则命中生成标签")
    p.add_argument("-i", "--input", help="输入交易文件")
    p.add_argument("-d", "--data-dir", default="./data",
                   help="数据根目录 (默认: ./data)")
    p.add_argument("-c", "--chargebacks", help="拒付文件路径 (默认自动查找)")
    p.add_argument("-o", "--output-dir", default="./data/labeled",
                   help="输出目录 (默认: ./data/labeled)")
    p.add_argument("--high-risk-rules", nargs="+", default=["R001", "R002", "R003", "HIGH_RISK"],
                   help="高风险规则ID列表，命中则标记为可疑")
    p.add_argument("--blacklist-as-fraud", action="store_true",
                   help="黑名单命中直接标记为欺诈(否则为可疑)")
    p.add_argument("--default-genuine", action="store_true", default=True,
                   help="未命中任何标记的视为真实交易")
    p.set_defaults(func=cmd_label)
