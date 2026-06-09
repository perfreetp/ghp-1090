"""数据模型和常量定义"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class TransactionType(Enum):
    """交易类型"""
    CONSUMTION = "消费"
    WITHDRAW = "取现"
    TRANSFER = "转账"
    REFUND = "退款"
    PREAUTH = "预授权"
    OTHER = "其他"


class FraudLabel(Enum):
    """欺诈标签"""
    GENUINE = 0  # 真实交易
    FRAUD = 1    # 欺诈交易
    SUSPICIOUS = 2  # 可疑交易
    UNKNOWN = -1  # 未知


class DatasetType(Enum):
    """数据集类型"""
    TRAIN = "train"
    VALID = "valid"
    BACKTEST = "backtest"


REQUIRED_TXN_FIELDS = [
    "txn_id", "card_no", "txn_time", "txn_amount", "currency",
    "merchant_id", "merchant_name", "txn_type", "channel"
]

REQUIRED_CHARGEBACK_FIELDS = [
    "txn_id", "chargeback_time", "chargeback_reason",
    "chargeback_amount", "chargeback_result"
]

REQUIRED_BLACKLIST_FIELDS = [
    "entity_type", "entity_value", "list_time",
    "risk_level", "source"
]

OPTIONAL_TXN_FIELDS = [
    "cardholder_name", "id_card", "phone", "device_id", "ip",
    "country", "province", "city", "mcc", "pos_entry_mode",
    "installment", "cashback", "rule_hit", "manual_review",
    "manual_result", "risk_score", "auth_code", "issuer_bank",
    "acquirer_bank", "terminal_id"
]

MASK_FIELDS = ["cardholder_name", "id_card", "phone", "card_no", "email", "address"]

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y%m%d%H%M%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y%m%d",
    "%Y-%m-%d",
    "%Y/%m/%d",
]


@dataclass
class FieldCheckResult:
    """字段检查结果"""
    file_type: str
    file_path: str
    missing_required: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)
    extra_fields: List[str] = field(default_factory=list)
    total_rows: int = 0
    null_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return len(self.missing_required) == 0

    def summary(self) -> str:
        lines = [f"[{self.file_type}] {self.file_path}"]
        lines.append(f"  总行数: {self.total_rows}")
        if self.missing_required:
            lines.append(f"  [警告] 缺失必填字段: {', '.join(self.missing_required)}")
        if self.missing_optional:
            lines.append(f"  [信息] 缺失选填字段: {', '.join(self.missing_optional)}")
        if self.extra_fields:
            lines.append(f"  [信息] 额外字段: {', '.join(self.extra_fields)}")
        if self.null_counts:
            top_null = dict(sorted(self.null_counts.items(), key=lambda x: -x[1])[:5])
            lines.append(f"  空值Top5: {top_null}")
        lines.append(f"  状态: {'[通过]' if self.is_valid else '[失败]'}")
        return "\n".join(lines)


@dataclass
class CleanResult:
    """数据清洗结果"""
    initial_rows: int = 0
    final_rows: int = 0
    duplicates_removed: int = 0
    invalid_time_removed: int = 0
    invalid_amount_removed: int = 0
    amount_normalized: int = 0
    time_normalized: int = 0

    def summary(self) -> str:
        lines = ["=== 数据清洗摘要 ==="]
        lines.append(f"初始行数: {self.initial_rows}")
        lines.append(f"最终行数: {self.final_rows}")
        lines.append(f"去除重复: {self.duplicates_removed}")
        lines.append(f"移除无效时间: {self.invalid_time_removed}")
        lines.append(f"移除无效金额: {self.invalid_amount_removed}")
        lines.append(f"标准化金额格式: {self.amount_normalized}")
        lines.append(f"标准化时间格式: {self.time_normalized}")
        return "\n".join(lines)


@dataclass
class LabelResult:
    """标签生成结果"""
    total: int = 0
    genuine: int = 0
    fraud: int = 0
    suspicious: int = 0
    unknown: int = 0
    from_chargeback: int = 0
    from_manual: int = 0
    from_rule: int = 0

    def summary(self) -> str:
        lines = ["=== 标签生成摘要 ==="]
        lines.append(f"总样本数: {self.total}")
        lines.append(f"真实交易(0): {self.genuine} ({self.genuine/self.total*100:.2f}%)")
        lines.append(f"欺诈交易(1): {self.fraud} ({self.fraud/self.total*100:.2f}%)")
        lines.append(f"可疑交易(2): {self.suspicious} ({self.suspicious/self.total*100:.2f}%)")
        lines.append(f"未标记(-1): {self.unknown} ({self.unknown/self.total*100:.2f}%)")
        lines.append("--- 标签来源 ---")
        lines.append(f"拒付来源: {self.from_chargeback}")
        lines.append(f"人工审核来源: {self.from_manual}")
        lines.append(f"规则命中来源: {self.from_rule}")
        if self.fraud > 0:
            ratio = self.genuine / max(self.fraud, 1)
            lines.append(f"类别失衡比(正/负): {ratio:.2f}:1")
        return "\n".join(lines)


@dataclass
class SplitResult:
    """数据集拆分结果"""
    splits: Dict[str, int] = field(default_factory=dict)
    fraud_rates: Dict[str, float] = field(default_factory=dict)
    method: str = ""

    def summary(self) -> str:
        lines = [f"=== 数据集拆分({self.method}) ==="]
        total = sum(self.splits.values())
        for name, count in self.splits.items():
            pct = count / total * 100 if total else 0
            fr = self.fraud_rates.get(name, 0) * 100
            lines.append(f"  {name}: {count} ({pct:.2f}%) | 欺诈率: {fr:.2f}%")
        return "\n".join(lines)
