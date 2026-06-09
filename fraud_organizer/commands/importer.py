"""import 命令：导入交易、拒付和黑名单文件并检查缺失字段"""

import logging
import argparse
from typing import List, Optional, Dict, Tuple
from pathlib import Path

import pandas as pd

from ..models import (
    REQUIRED_TXN_FIELDS, REQUIRED_CHARGEBACK_FIELDS, REQUIRED_BLACKLIST_FIELDS,
    OPTIONAL_TXN_FIELDS, FieldCheckResult
)
from ..utils import read_file, save_file, ensure_dir

logger = logging.getLogger(__name__)


def check_fields(df: pd.DataFrame, required: List[str],
                 optional: List[str], file_type: str,
                 file_path: str) -> FieldCheckResult:
    """检查字段完整性"""
    result = FieldCheckResult(
        file_type=file_type,
        file_path=file_path,
        total_rows=len(df),
    )
    columns = set(df.columns)

    for f in required:
        if f not in columns:
            result.missing_required.append(f)

    for f in optional:
        if f not in columns:
            result.missing_optional.append(f)

    known = set(required) | set(optional)
    result.extra_fields = sorted([c for c in columns if c not in known])

    for col in df.columns:
        null_count = df[col].isna().sum()
        if null_count > 0:
            result.null_counts[col] = int(null_count)

    return result


def _normalize_field_names(df: pd.DataFrame,
                           mapping: Dict[str, str]) -> pd.DataFrame:
    """标准化字段名"""
    existing_map = {}
    lower_cols = {c.lower().strip(): c for c in df.columns}

    for std_name, aliases in mapping.items():
        for alias in [std_name] + aliases:
            if alias in df.columns:
                existing_map[alias] = std_name
                break
            if alias.lower() in lower_cols:
                existing_map[lower_cols[alias.lower()]] = std_name
                break

    if existing_map:
        logger.info(f"字段映射: {existing_map}")
        df = df.rename(columns=existing_map)
    return df


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


def cmd_import(args: argparse.Namespace) -> int:
    """执行 import 命令"""
    output_dir = ensure_dir(args.output_dir)
    check_results: List[FieldCheckResult] = []
    dataframes: Dict[str, pd.DataFrame] = {}

    txn_files = args.transactions or []
    cb_files = args.chargebacks or []
    bl_files = args.blacklists or []

    # 1. 导入交易文件
    if txn_files:
        all_txns = []
        for fp in txn_files:
            logger.info(f"处理交易文件: {fp}")
            try:
                df = read_file(fp)
                df = _normalize_field_names(df, FIELD_ALIASES)
                check = check_fields(df, REQUIRED_TXN_FIELDS, OPTIONAL_TXN_FIELDS,
                                     "交易文件", fp)
                check_results.append(check)
                if check.is_valid or args.force:
                    all_txns.append(df)
                else:
                    logger.warning(f"跳过无效文件(使用 --force 强制执行): {fp}")
            except Exception as e:
                logger.error(f"读取交易文件失败 {fp}: {e}")

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
                df = _normalize_field_names(df, FIELD_ALIASES)
                check = check_fields(df, REQUIRED_CHARGEBACK_FIELDS, [],
                                     "拒付文件", fp)
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
                df = _normalize_field_names(df, FIELD_ALIASES)
                check = check_fields(df, REQUIRED_BLACKLIST_FIELDS, [],
                                     "黑名单文件", fp)
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

    # 4. 输出检查报告
    print("\n" + "=" * 60)
    print("字段检查报告")
    print("=" * 60)
    for r in check_results:
        print(r.summary())
        print("-" * 40)

    all_valid = all(r.is_valid for r in check_results)
    if not all_valid:
        if args.force:
            print("\n[警告] 存在缺失字段，但使用 --force 继续执行")
        else:
            print("\n[错误] 存在必填字段缺失。使用 --force 可跳过检查继续执行。")
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
    p.set_defaults(func=cmd_import)
