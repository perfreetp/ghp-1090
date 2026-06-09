"""import 命令：导入交易、拒付和黑名单文件并检查缺失字段"""

import logging
import argparse
from typing import List, Optional, Dict, Tuple
from pathlib import Path

import pandas as pd
import numpy as np

from ..models import (
    REQUIRED_TXN_FIELDS, REQUIRED_CHARGEBACK_FIELDS, REQUIRED_BLACKLIST_FIELDS,
    OPTIONAL_TXN_FIELDS, FieldCheckResult
)
from ..utils import read_file, save_file, ensure_dir, load_config

logger = logging.getLogger(__name__)


def check_fields(df: pd.DataFrame, required: List[str],
                 optional: List[str], file_type: str,
                 file_path: str,
                 null_threshold_pct: float = 50.0) -> FieldCheckResult:
    """检查字段完整性，包括空值百分比分析"""
    result = FieldCheckResult(
        file_type=file_type,
        file_path=file_path,
        total_rows=len(df),
    )
    columns = set(df.columns)
    n_rows = max(len(df), 1)

    for f in required:
        if f not in columns:
            result.missing_required.append(f)

    for f in optional:
        if f not in columns:
            result.missing_optional.append(f)

    known = set(required) | set(optional)
    result.extra_fields = sorted([c for c in columns if c not in known])

    for col in df.columns:
        null_count = int(df[col].isna().sum())
        # 同时处理空字符串
        if df[col].dtype == object:
            empty_str = int(df[col].astype(str).str.strip().isin(["", "nan", "NaN", "None"]).sum())
            null_count = max(null_count, empty_str)
        if null_count > 0:
            result.null_counts[col] = null_count

    return result


def _merge_field_mappings(builtin: Dict[str, List[str]],
                          extra: Optional[Dict[str, str]]) -> Dict[str, List[str]]:
    """合并内置映射与用户配置的字段映射

    Args:
        builtin: 内置字段别名表 {标准名: [别名列表]}
        extra: 用户配置 {用户列名: 标准名} 或 {标准名: 用户列名}

    Returns:
        合并后的完整别名表
    """
    merged = {k: list(v) for k, v in builtin.items()}

    if not extra:
        return merged

    # 支持两种配置方向
    for user_col, std_name in extra.items():
        # 方向 A: 用户列名 -> 标准名 (更常见)
        if std_name in merged:
            if user_col not in merged[std_name]:
                merged[std_name].insert(0, user_col)
        else:
            # 方向 B: 如果 key 是已知标准名，把 value 作为别名追加
            if user_col in merged:
                if std_name not in merged[user_col]:
                    merged[user_col].insert(0, std_name)
            else:
                # 全新映射，当做 {标准名: [别名]}
                merged[user_col] = [std_name] + merged.get(user_col, [])

    logger.info(f"字段映射配置: 内置 {len(builtin)} 个，新增/覆盖 {len(extra)} 个，"
                f"合计 {len(merged)} 个标准字段的映射")
    return merged


def _normalize_field_names(df: pd.DataFrame,
                           mapping: Dict[str, List[str]]) -> Tuple[pd.DataFrame, Dict]:
    """标准化字段名，返回 (重命名后df, 实际映射dict)"""
    actual = {}
    lower_cols = {c.lower().strip(): c for c in df.columns}
    original_cols = list(df.columns)

    for std_name, aliases in mapping.items():
        found = False
        # 优先级 1: 精确匹配原始列（包含大小写）
        for alias in [std_name] + aliases:
            if alias in df.columns:
                actual[alias] = std_name
                found = True
                break
        if found:
            continue
        # 优先级 2: 忽略大小写匹配
        for alias in [std_name] + aliases:
            if alias.lower() in lower_cols:
                orig_col = lower_cols[alias.lower()]
                actual[orig_col] = std_name
                found = True
                break
        if found:
            continue
        # 优先级 3: 去空格后匹配
        stripped_map = {c.replace(" ", ""): c for c in df.columns}
        for alias in [std_name] + aliases:
            stripped = alias.replace(" ", "")
            if stripped in stripped_map:
                actual[stripped_map[stripped]] = std_name
                found = True
                break

    if actual:
        logger.info(f"实际命中字段映射 {len(actual)} 个: {actual}")
        df = df.rename(columns=actual)
    return df, actual


FIELD_ALIASES = {
    "txn_id": ["交易ID", "流水号", "订单号", "order_id", "trans_id"],
    "card_no": ["卡号", "银行卡号", "account_no", "card_number"],
    "txn_time": ["交易时间", "下单时间", "trans_time", "order_time"],
    "txn_amount": ["交易金额", "金额", "amount", "trans_amount"],
    "currency": ["币种", "货币", "currency_code"],
    "merchant_id": ["商户ID", "商户号", "mch_id", "merchant_code"],
    "merchant_name": ["商户名称", "mch_name", "merchant"],
    "txn_type": ["交易类型", "类型", "type", "trans_type"],
    "channel": ["渠道", "支付渠道", "pay_channel", "source"],
    "cardholder_name": ["持卡人姓名", "姓名", "持卡人", "holder_name"],
    "id_card": ["身份证号", "证件号", "身份证", "id_number", "cert_no"],
    "phone": ["手机号", "电话", "mobile", "telephone"],
    "device_id": ["设备ID", "设备号", "device", "dev_id"],
    "ip": ["IP地址", "ip_address"],
    "country": ["国家", "nation"],
    "province": ["省份", "省"],
    "city": ["城市", "市"],
    "mcc": ["商户类别码", "mcc_code"],
    "pos_entry_mode": ["刷卡方式", "entry_mode", "pos_mode"],
    "installment": ["分期", "分期数"],
    "cashback": ["返现", "返利"],
    "rule_hit": ["命中规则", "规则", "rule_ids", "rules"],
    "manual_review": ["人工审核", "人工处理"],
    "manual_result": ["人工结论", "审核结果", "review_result"],
    "risk_score": ["风险评分", "风险分", "score"],
    "auth_code": ["授权码", "auth_code"],
    "issuer_bank": ["发卡行", "issuer"],
    "acquirer_bank": ["收单行", "acquirer"],
    "terminal_id": ["终端号", "terminal"],
    "chargeback_time": ["拒付时间", "调单时间"],
    "chargeback_reason": ["拒付原因", "拒付代码", "reason_code"],
    "chargeback_amount": ["拒付金额", "争议金额"],
    "chargeback_result": ["拒付结果", "争议结果"],
    "entity_type": ["实体类型", "主体类型"],
    "entity_value": ["实体值", "主体值", "黑名单值"],
    "list_time": ["入库时间", "加入时间", "添加时间"],
    "risk_level": ["风险等级", "风险级别"],
    "source": ["来源", "数据来源"],
}


def _write_detailed_report(check_results: List[FieldCheckResult],
                           output_dir: str,
                           applied_mappings: List[Dict],
                           high_null_threshold: float = 0.3) -> None:
    """写入详细的字段检查报告
    high_null_threshold: 高于此比例空值列标记为「高比例空值」供 Quality Gates 判定
    """
    out_dir = Path(output_dir)

    # --- CSV 详细报告 ---
    report_rows = []
    for r in check_results:
        base_info = {
            "文件类型": r.file_type,
            "文件路径": r.file_path,
            "文件名称": Path(r.file_path).name,
            "总行数": r.total_rows,
        }
        # 缺失必填字段 - 每个字段一行
        for f in r.missing_required:
            row = dict(base_info)
            row["检查项"] = "缺失必填字段"
            row["字段名"] = f
            row["空值数"] = ""
            row["空值率%"] = ""
            row["严重程度"] = "必填缺失"       # Quality Gates 依赖此关键字
            report_rows.append(row)
        for f in r.missing_optional:
            row = dict(base_info)
            row["检查项"] = "缺失选填字段"
            row["字段名"] = f
            row["空值数"] = ""
            row["空值率%"] = ""
            row["严重程度"] = "信息缺失"
            report_rows.append(row)
        # 高比例空值（严格按传入 high_null_threshold 阈值）
        n = max(r.total_rows, 1)
        for col, null_cnt in r.null_counts.items():
            pct = null_cnt / n * 100
            threshold_pct = high_null_threshold * 100
            severity = ""
            item_name = ""
            if pct >= threshold_pct:
                severity = "高比例空值"     # Quality Gates 依赖此关键字
                item_name = f"高比例空值(>={int(threshold_pct)}%)"
            elif pct >= 20:
                severity = "轻微空值"
                item_name = "空值偏高(>=20%)"
            if severity:
                row = dict(base_info)
                row["检查项"] = item_name
                row["字段名"] = col
                row["空值数"] = null_cnt
                row["空值率%"] = round(pct, 2)
                row["严重程度"] = severity
                report_rows.append(row)

    if report_rows:
        pd.DataFrame(report_rows).to_csv(
            out_dir / "import_field_check_report.csv",
            index=False, encoding="utf-8-sig"
        )

    # --- 字段映射应用报告 ---
    map_rows = []
    for i, (fp, mapping) in enumerate(applied_mappings):
        for orig, std in mapping.items():
            map_rows.append({
                "序号": i + 1,
                "文件": Path(fp).name if fp else "N/A",
                "原列名": orig,
                "映射为标准字段": std,
            })
    if map_rows:
        pd.DataFrame(map_rows).to_csv(
            out_dir / "import_field_mapping_report.csv",
            index=False, encoding="utf-8-sig"
        )

    # --- Markdown 文本报告（适合发给同事看） ---
    md_lines = ["# 导入字段检查报告", ""]
    md_lines.append(f"- **生成时间**: {pd.Timestamp.now()}")
    md_lines.append(f"- **检查文件数**: {len(check_results)} 个")
    md_lines.append(f"- **总行数**: {sum(r.total_rows for r in check_results):,}")
    md_lines.append("")

    for r in check_results:
        md_lines.append(f"## {r.file_type} - {Path(r.file_path).name}")
        md_lines.append("")
        md_lines.append(f"- **路径**: `{r.file_path}`")
        md_lines.append(f"- **总行数**: {r.total_rows:,}")
        md_lines.append(f"- **字段校验状态**: {'[通过]' if r.is_valid else '[失败]'}")
        md_lines.append("")

        if r.missing_required:
            md_lines.append("### [警告] 缺失必填字段")
            md_lines.append("")
            md_lines.append("| 字段名 | 说明 |")
            md_lines.append("|--------|------|")
            for f in r.missing_required:
                hint = ""
                if f == "txn_id": hint = "交易唯一标识，用于去重、拒付关联"
                elif f == "card_no": hint = "卡号，用于持卡人维度分析"
                elif f == "txn_time": hint = "交易时间，用于时间窗口特征、时间序列拆分"
                elif f == "txn_amount": hint = "交易金额，用于金额阈值特征"
                elif f == "merchant_id": hint = "商户ID，用于商户风险画像"
                elif f == "chargeback_result": hint = "拒付结果，是欺诈标签的黄金来源"
                elif f == "entity_value": hint = "黑名单实体值"
                md_lines.append(f"| `{f}` | {hint} |")
            md_lines.append("")

        if r.missing_optional:
            md_lines.append("### ℹ 缺失选填字段（不影响流程，但建议补充）")
            md_lines.append("")
            md_lines.append("缺失字段: " + ", ".join(f"`{f}`" for f in r.missing_optional))
            md_lines.append("")

        # 高比例空值列
        n = max(r.total_rows, 1)
        high_null = [(col, cnt, cnt / n * 100)
                     for col, cnt in sorted(r.null_counts.items(), key=lambda x: -x[1])
                     if cnt / n >= 0.2]
        if high_null:
            md_lines.append("### [数据质量] 空值严重的列（≥20%）")
            md_lines.append("")
            md_lines.append("| 列名 | 空值数 | 空值率 | 建议 |")
            md_lines.append("|------|--------|--------|------|")
            for col, cnt, pct in high_null:
                sug = "**建议检查数据源，可能是关键字段未补全**" if pct >= 80 else (
                    "可考虑填充默认值或单独作为特征" if pct >= 50 else "影响较小")
                md_lines.append(f"| `{col}` | {cnt:,} | {pct:.2f}% | {sug} |")
            md_lines.append("")

    with open(out_dir / "import_field_check_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))


def cmd_import(args: argparse.Namespace) -> int:
    """执行 import 命令"""
    output_dir = ensure_dir(args.output_dir)
    check_results: List[FieldCheckResult] = []
    dataframes: Dict[str, pd.DataFrame] = {}

    txn_files = args.transactions or []
    cb_files = args.chargebacks or []
    bl_files = args.blacklists or []

    # 空输入处理
    if not txn_files and not cb_files and not bl_files:
        print("[警告] 未提供任何输入文件，生成空说明后正常退出")
        Path(output_dir, "EMPTY_IMPORT_NOTE.txt").write_text(
            "本次 import 未提供交易/拒付/黑名单文件，数据集为空。\n"
            f"时间: {pd.Timestamp.now()}\n", encoding="utf-8"
        )
        return 0

    # 加载字段映射配置
    extra_mapping = {}
    null_threshold = getattr(args, "null_threshold", 50.0)

    if getattr(args, "config", None):
        cfg = load_config(args.config)
        cfg_import = cfg.get("import", cfg) if isinstance(cfg, dict) else {}
        extra_mapping = cfg_import.get("field_mapping", {}) or {}
        null_threshold = float(cfg_import.get("null_threshold_pct", null_threshold))

    # 命令行 --field-mapping 覆盖
    if getattr(args, "field_mapping", None) and isinstance(args.field_mapping, dict):
        extra_mapping.update(args.field_mapping)

    full_mapping = _merge_field_mappings(FIELD_ALIASES, extra_mapping)

    applied_mappings = []  # [(文件路径, {原列: 标准字段})]

    # 1. 导入交易文件
    if txn_files:
        all_txns = []
        for fp in txn_files:
            logger.info(f"处理交易文件: {fp}")
            try:
                df = read_file(fp)
                df, applied = _normalize_field_names(df, full_mapping)
                applied_mappings.append((fp, applied))
                check = check_fields(df, REQUIRED_TXN_FIELDS, OPTIONAL_TXN_FIELDS,
                                     "交易文件", fp, null_threshold)
                check_results.append(check)
                if check.is_valid or args.force:
                    all_txns.append(df)
                else:
                    logger.warning(f"跳过无效文件(使用 --force 强制执行): {fp}")
            except Exception as e:
                logger.error(f"读取交易文件失败 {fp}: {e}")
                check_results.append(FieldCheckResult(
                    file_type="交易文件(读取失败)",
                    file_path=fp,
                ))
                check_results[-1].message = str(e) if hasattr(check_results[-1], "message") else None

        if all_txns:
            txn_df = pd.concat(all_txns, ignore_index=True)
            dataframes["transactions"] = txn_df
            out_path = Path(output_dir) / "transactions_raw.pkl"
            save_file(txn_df, str(out_path))
            logger.info(f"合并 {len(all_txns)} 个交易文件, 共 {len(txn_df)} 行")

    # 2. 导入拒付文件
    if cb_files:
        all_cbs = []
        for fp in cb_files:
            logger.info(f"处理拒付文件: {fp}")
            try:
                df = read_file(fp)
                df, applied = _normalize_field_names(df, full_mapping)
                applied_mappings.append((fp, applied))
                check = check_fields(df, REQUIRED_CHARGEBACK_FIELDS, [],
                                     "拒付文件", fp, null_threshold)
                check_results.append(check)
                if check.is_valid or args.force:
                    all_cbs.append(df)
            except Exception as e:
                logger.error(f"读取拒付文件失败 {fp}: {e}")

        if all_cbs:
            cb_df = pd.concat(all_cbs, ignore_index=True)
            dataframes["chargebacks"] = cb_df
            out_path = Path(output_dir) / "chargebacks_raw.pkl"
            save_file(cb_df, str(out_path))
            logger.info(f"合并 {len(all_cbs)} 个拒付文件, 共 {len(cb_df)} 行")

    # 3. 导入黑名单文件
    if bl_files:
        all_bls = []
        for fp in bl_files:
            logger.info(f"处理黑名单文件: {fp}")
            try:
                df = read_file(fp)
                df, applied = _normalize_field_names(df, full_mapping)
                applied_mappings.append((fp, applied))
                check = check_fields(df, REQUIRED_BLACKLIST_FIELDS, [],
                                     "黑名单文件", fp, null_threshold)
                check_results.append(check)
                if check.is_valid or args.force:
                    all_bls.append(df)
            except Exception as e:
                logger.error(f"读取黑名单文件失败 {fp}: {e}")

        if all_bls:
            bl_df = pd.concat(all_bls, ignore_index=True)
            dataframes["blacklists"] = bl_df
            out_path = Path(output_dir) / "blacklists_raw.pkl"
            save_file(bl_df, str(out_path))
            logger.info(f"合并 {len(all_bls)} 个黑名单文件, 共 {len(bl_df)} 行")

    # 4. 输出控制台报告
    print("\n" + "=" * 60)
    print("字段检查报告")
    print("=" * 60)
    missing_summary = []  # [(文件, 缺失必填)]
    high_null_summary = []  # [(文件, 列, 空值率)]

    for r in check_results:
        print(r.summary())
        print("-" * 40)
        if r.missing_required:
            missing_summary.append((Path(r.file_path).name, r.missing_required))
        n = max(r.total_rows, 1)
        for col, cnt in sorted(r.null_counts.items(), key=lambda x: -x[1])[:3]:
            pct = cnt / n * 100
            if pct >= null_threshold:
                high_null_summary.append((Path(r.file_path).name, col, pct, cnt))

    # 重点摘要：缺失字段汇总
    if missing_summary:
        print("\n[警告] 缺失必填字段汇总:")
        print("  文件                 缺失字段")
        print("  " + "-" * 56)
        for fname, miss in missing_summary:
            print(f"  {fname[:20]:20s} {', '.join(miss)}")

    if high_null_summary:
        print(f"\n[数据质量] 空值率 >= {null_threshold:.0f}% 的列 (Top):")
        print(f"  {'文件':20s} {'列名':20s} {'空值率':>8s}  {'空值数':>8s}")
        print("  " + "-" * 60)
        for fname, col, pct, cnt in high_null_summary:
            print(f"  {fname[:20]:20s} {col[:20]:20s} {pct:>7.1f}%  {cnt:>8,}")

    # 5. 写详细报告文件
    try:
        _write_detailed_report(check_results, output_dir, applied_mappings,
                               high_null_threshold=null_threshold / 100.0)
        logger.info("详细字段检查报告已写入 import_field_check_report.csv/.md")
    except Exception as e:
        logger.warning(f"写详细报告失败: {e}")

    all_valid = all(r.is_valid for r in check_results)
    if not all_valid:
        if args.force:
            print("\n[警告] 存在缺失字段，但使用 --force 继续执行")
        else:
            print("\n[错误] 存在必填字段缺失。使用 --force 可跳过检查继续执行。")
            print("       详细问题列表请查看: "
                  + str(Path(output_dir) / "import_field_check_report.csv"))
            return 1

    print(f"\n[完成] 导入完成。原始数据已保存至: {output_dir}")
    return 0


def register_subparser(subparsers) -> None:
    """注册 import 子命令"""
    p = subparsers.add_parser("import", help="导入交易、拒付和黑名单文件并检查字段")
    p.add_argument("-t", "--transactions", nargs="+", metavar="FILE",
                   help="交易文件路径 (CSV/Excel)")
    p.add_argument("-c", "--chargebacks", nargs="+", metavar="FILE",
                   help="拒付文件路径 (CSV/Excel)")
    p.add_argument("-b", "--blacklists", nargs="+", metavar="FILE",
                   help="黑名单文件路径 (CSV/Excel)")
    p.add_argument("-o", "--output-dir", default="./data/imported",
                   help="输出目录 (默认: ./data/imported)")
    p.add_argument("--force", action="store_true",
                   help="忽略字段缺失警告，强制导入")
    p.add_argument("--config", help="YAML 配置文件（含 field_mapping 字段映射）")
    p.add_argument("--field-mapping", nargs="*", metavar="COL=STD",
                   help="命令行字段映射，例: --field-mapping 订单号=txn_id 卡号=card_no")
    p.add_argument("--null-threshold", type=float, default=50.0,
                   help="高比例空值警告阈值(%%)，默认 50%%")
    p.set_defaults(func=cmd_import)
