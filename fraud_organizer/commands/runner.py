"""批处理任务配置解析与运行器"""

import json
import logging
import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict

import pandas as pd
import yaml

from ..utils import load_config, ensure_dir, read_file, save_file

logger = logging.getLogger(__name__)


@dataclass
class StepArtifact:
    """单步骤的输入输出清单"""
    step_name: str
    inputs: List[Dict[str, str]] = field(default_factory=list)  # [{name, path, rows}]
    outputs: List[Dict[str, str]] = field(default_factory=list)  # [{name, path, rows}]
    start_time: float = 0.0
    end_time: float = 0.0
    status: str = "pending"  # pending/running/success/skipped/failed
    message: str = ""

    @property
    def duration(self) -> float:
        return max(self.end_time - self.start_time, 0.0)


@dataclass
class BatchManifest:
    """批处理任务清单"""
    task_name: str = ""
    start_time: str = ""
    end_time: str = ""
    config_path: str = ""
    steps: List[StepArtifact] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def total_duration(self) -> float:
        return sum(s.duration for s in self.steps)

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for s in self.steps:
            rows.append({
                "步骤": s.step_name,
                "状态": s.status,
                "耗时(秒)": round(s.duration, 2),
                "输入文件数": len(s.inputs),
                "输出文件数": len(s.outputs),
                "说明": s.message,
            })
        return pd.DataFrame(rows)

    def to_markdown(self) -> str:
        lines = []
        lines.append(f"# 批处理任务清单: {self.task_name}")
        lines.append("")
        lines.append(f"- **开始时间**: {self.start_time}")
        lines.append(f"- **结束时间**: {self.end_time}")
        lines.append(f"- **总耗时**: {self.total_duration():.2f} 秒")
        lines.append(f"- **配置文件**: `{self.config_path}`")
        lines.append("")
        lines.append("## 步骤执行摘要")
        lines.append("")
        lines.append("| 步骤 | 状态 | 耗时(秒) | 输入数 | 输出数 | 说明 |")
        lines.append("|------|------|----------|--------|--------|------|")
        for s in self.steps:
            icon = {"success": "✓", "skipped": "⏭", "failed": "✗", "pending": "•", "running": "►"}
            lines.append(f"| {s.step_name} | {icon.get(s.status, '?')} {s.status} | "
                         f"{s.duration:.2f} | {len(s.inputs)} | {len(s.outputs)} | {s.message} |")
        lines.append("")

        for s in self.steps:
            lines.append(f"## {s.step_name}")
            lines.append("")
            if s.inputs:
                lines.append("### 输入")
                lines.append("")
                lines.append("| 名称 | 路径 | 行数 |")
                lines.append("|------|------|------|")
                for inp in s.inputs:
                    lines.append(f"| {inp.get('name', '-')} | `{inp.get('path', '-')}` | "
                                 f"{inp.get('rows', '-')} |")
                lines.append("")
            if s.outputs:
                lines.append("### 输出")
                lines.append("")
                lines.append("| 名称 | 路径 | 行数 |")
                lines.append("|------|------|------|")
                for out in s.outputs:
                    lines.append(f"| {out.get('name', '-')} | `{out.get('path', '-')}` | "
                                 f"{out.get('rows', '-')} |")
                lines.append("")
            if s.message:
                lines.append(f"> {s.message}")
                lines.append("")
        return "\n".join(lines)


def _count_rows(path: str) -> str:
    """统计文件行数，失败则返回 -"""
    try:
        p = Path(path)
        if not p.exists():
            return "N/A"
        if p.suffix.lower() in (".pkl", ".pickle"):
            df = pd.read_pickle(path)
            return str(len(df))
        if p.suffix.lower() == ".csv":
            return sum(1 for _ in open(path, "rb")) - 1
        if p.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path)
            return str(len(df))
        return "-"
    except Exception:
        return "-"


def cmd_run(args: argparse.Namespace) -> int:
    """执行批处理任务"""
    config_path = args.config
    if not config_path or not Path(config_path).exists():
        logger.error(f"批处理配置文件不存在: {config_path}")
        return 1

    logger.info(f"加载批处理配置: {config_path}")
    cfg = load_config(config_path)
    task_cfg = cfg.get("batch_task", cfg)

    # ---- 解析配置 ----
    task_name = task_cfg.get("task_name", f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    output_cfg = task_cfg.get("output", {}) or {}
    output_root = ensure_dir(output_cfg.get("base_dir") or
                             task_cfg.get("output_root", "./data/batch_output"))
    ensure_dir(output_root)

    # 各子目录
    dirs = {
        "imported": f"{output_root}/imported",
        "cleaned": f"{output_root}/cleaned",
        "labeled": f"{output_root}/labeled",
        "profiled": f"{output_root}/profiled",
        "splits": f"{output_root}/splits",
        "masked": f"{output_root}/masked",
        "reports": f"{output_root}/reports",
        "exported": f"{output_root}/exported",
    }
    for d in dirs.values():
        ensure_dir(d)

    # 数据路径
    data_cfg = task_cfg.get("data_paths", {})
    txn_files = data_cfg.get("transactions", []) or []
    cb_files = data_cfg.get("chargebacks", []) or []
    bl_files = data_cfg.get("blacklists", []) or []

    # 拆分配置
    split_cfg = task_cfg.get("split", {})
    split_method = split_cfg.get("method", "ratio")
    split_ratios = split_cfg.get("ratios", [0.7, 0.15])
    split_train_end = split_cfg.get("train_end")
    split_valid_end = split_cfg.get("valid_end")
    prevent_leak = split_cfg.get("prevent_card_leak", True)
    fix_leak = split_cfg.get("fix_leak", False)

    # 导出配置
    export_cfg = task_cfg.get("export", {})
    export_formats = export_cfg.get("formats", ["csv", "xlsx"])
    export_include = export_cfg.get("include_columns")
    export_exclude = export_cfg.get("exclude_columns")
    export_prefix = export_cfg.get("prefix", "")

    # 脱敏配置
    mask_cfg = task_cfg.get("mask", {})
    mask_rules = mask_cfg.get("rules", {})
    mask_salt = mask_cfg.get("salt", "")

    # 字段映射配置（给 import 用）
    import_cfg = task_cfg.get("import", {})
    field_mapping_extra = import_cfg.get("field_mapping", {})

    # 跳过步骤
    skip_steps = set(task_cfg.get("skip_steps", []) or [])

    # ---- 初始化清单 ----
    manifest = BatchManifest(
        task_name=task_name,
        start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        config_path=str(Path(config_path).resolve()),
    )

    # 延迟导入避免循环
    from . import importer, cleaner, labeler, profiler, splitter, masker, reporter, exporter

    # ---- 1. Import ----
    step = StepArtifact(step_name="import", status="running", start_time=time.time())
    for fp in txn_files:
        step.inputs.append({"name": Path(fp).name, "path": str(fp), "rows": _count_rows(fp)})
    for fp in cb_files:
        step.inputs.append({"name": Path(fp).name, "path": str(fp), "rows": _count_rows(fp)})
    for fp in bl_files:
        step.inputs.append({"name": Path(fp).name, "path": str(fp), "rows": _count_rows(fp)})

    if "import" in skip_steps or (not txn_files and not cb_files and not bl_files):
        step.status = "skipped"
        step.message = "跳过或无输入文件"
    else:
        try:
            ns = argparse.Namespace(
                transactions=txn_files if txn_files else None,
                chargebacks=cb_files if cb_files else None,
                blacklists=bl_files if bl_files else None,
                output_dir=dirs["imported"],
                force=True,
                field_mapping=field_mapping_extra,
            )
            rc = importer.cmd_import(ns)
            step.status = "success" if rc == 0 else "failed"
            for out_name in ["transactions_raw.pkl", "chargebacks_raw.pkl", "blacklists_raw.pkl"]:
                out_path = Path(dirs["imported"]) / out_name
                if out_path.exists():
                    step.outputs.append({"name": out_name, "path": str(out_path),
                                         "rows": _count_rows(str(out_path))})
            step.message = f"返回码={rc}"
        except Exception as e:
            step.status = "failed"
            step.message = f"异常: {e}"
            logger.exception("import 步骤异常")
    step.end_time = time.time()
    manifest.steps.append(step)
    if step.status == "failed":
        logger.error("import 步骤失败，任务终止")
        _finalize_manifest(manifest, dirs["reports"])
        return 2

    # ---- 2. Clean ----
    step = StepArtifact(step_name="clean", status="running", start_time=time.time())
    txn_pkl = Path(dirs["imported"]) / "transactions_raw.pkl"
    input_clean = str(txn_pkl) if txn_pkl.exists() else ""
    if input_clean:
        step.inputs.append({"name": "transactions_raw.pkl", "path": input_clean,
                            "rows": _count_rows(input_clean)})

    if "clean" in skip_steps or not input_clean:
        step.status = "skipped"
        step.message = "跳过或无输入"
    else:
        try:
            ns = argparse.Namespace(
                input=input_clean,
                data_dir=dirs["imported"],
                output_dir=dirs["cleaned"],
                dedup_cols=None, time_col=None, amount_col=None,
                currency=True, strip_strings=True,
                keep_invalid_time=False, keep_invalid_amount=False,
            )
            rc = cleaner.cmd_clean(ns)
            step.status = "success" if rc == 0 else "failed"
            for out_name in ["transactions_clean.pkl", "clean_report.txt"]:
                out_path = Path(dirs["cleaned"]) / out_name
                if out_path.exists():
                    step.outputs.append({"name": out_name, "path": str(out_path),
                                         "rows": _count_rows(str(out_path))})
            step.message = f"返回码={rc}"
        except Exception as e:
            step.status = "failed"
            step.message = f"异常: {e}"
            logger.exception("clean 步骤异常")
    step.end_time = time.time()
    manifest.steps.append(step)
    if step.status == "failed":
        logger.error("clean 步骤失败，任务终止")
        _finalize_manifest(manifest, dirs["reports"])
        return 3

    # ---- 3. Label ----
    step = StepArtifact(step_name="label", status="running", start_time=time.time())
    clean_pkl = Path(dirs["cleaned"]) / "transactions_clean.pkl"
    cb_pkl = Path(dirs["imported"]) / "chargebacks_raw.pkl"
    input_label = str(clean_pkl) if clean_pkl.exists() else ""
    if input_label:
        step.inputs.append({"name": "transactions_clean.pkl", "path": input_label,
                            "rows": _count_rows(input_label)})
    if cb_pkl.exists():
        step.inputs.append({"name": "chargebacks_raw.pkl", "path": str(cb_pkl),
                            "rows": _count_rows(str(cb_pkl))})

    if "label" in skip_steps or not input_label:
        step.status = "skipped"
        step.message = "跳过或无输入"
    else:
        try:
            ns = argparse.Namespace(
                input=input_label,
                data_dir=output_root,
                chargebacks=str(cb_pkl) if cb_pkl.exists() else None,
                output_dir=dirs["labeled"],
                high_risk_rules=["R001", "R002", "R003", "HIGH_RISK"],
                blacklist_as_fraud=False,
                default_genuine=True,
            )
            rc = labeler.cmd_label(ns)
            step.status = "success" if rc == 0 else "failed"
            for out_name in ["transactions_labeled.pkl", "label_report.txt"]:
                out_path = Path(dirs["labeled"]) / out_name
                if out_path.exists():
                    step.outputs.append({"name": out_name, "path": str(out_path),
                                         "rows": _count_rows(str(out_path))})
            step.message = f"返回码={rc}"
        except Exception as e:
            step.status = "failed"
            step.message = f"异常: {e}"
            logger.exception("label 步骤异常")
    step.end_time = time.time()
    manifest.steps.append(step)
    if step.status == "failed":
        logger.error("label 步骤失败，任务终止")
        _finalize_manifest(manifest, dirs["reports"])
        return 4

    # ---- 4. Profile ----
    step = StepArtifact(step_name="profile", status="running", start_time=time.time())
    labeled_pkl = Path(dirs["labeled"]) / "transactions_labeled.pkl"
    input_profile = str(labeled_pkl) if labeled_pkl.exists() else ""
    if input_profile:
        step.inputs.append({"name": "transactions_labeled.pkl", "path": input_profile,
                            "rows": _count_rows(input_profile)})

    if "profile" in skip_steps or not input_profile:
        step.status = "skipped"
        step.message = "跳过或无输入"
    else:
        try:
            ns = argparse.Namespace(
                input=input_profile,
                data_dir=output_root,
                output_dir=dirs["profiled"],
                entities=["card_no", "merchant_id", "device_id", "province", "city", "mcc"],
                time_col="txn_time", amount_col="txn_amount",
                window="7D", top_n=20,
                freq_threshold=20, fraud_threshold=0.05,
                interval_threshold=1.0,
            )
            rc = profiler.cmd_profile(ns)
            step.status = "success" if rc == 0 else "failed"
            for p in Path(dirs["profiled"]).glob("*"):
                step.outputs.append({"name": p.name, "path": str(p),
                                     "rows": _count_rows(str(p))})
            step.message = f"返回码={rc}"
        except Exception as e:
            step.status = "failed"
            step.message = f"异常: {e}"
            logger.exception("profile 步骤异常")
    step.end_time = time.time()
    manifest.steps.append(step)

    # ---- 5. Split ----
    step = StepArtifact(step_name="split", status="running", start_time=time.time())
    if input_profile:
        step.inputs.append({"name": "transactions_labeled.pkl", "path": input_profile,
                            "rows": _count_rows(input_profile)})

    if "split" in skip_steps or not input_profile:
        step.status = "skipped"
        step.message = "跳过或无输入"
    else:
        try:
            ns = argparse.Namespace(
                input=input_profile,
                data_dir=output_root,
                output_dir=dirs["splits"],
                method=split_method,
                ratios=split_ratios if split_ratios else None,
                train_end=split_train_end, valid_end=split_valid_end,
                time_col="txn_time",
                stratified=True, seed=42,
                prevent_card_leak=prevent_leak,
                fix_leak=fix_leak,
                backtest_name=None,
                export_csv=True,
            )
            rc = splitter.cmd_split(ns)
            step.status = "success" if rc == 0 else "failed"
            for p in Path(dirs["splits"]).glob("*"):
                step.outputs.append({"name": p.name, "path": str(p),
                                     "rows": _count_rows(str(p))})
            step.message = f"返回码={rc}, 方式={split_method}"
        except Exception as e:
            step.status = "failed"
            step.message = f"异常: {e}"
            logger.exception("split 步骤异常")
    step.end_time = time.time()
    manifest.steps.append(step)

    # ---- 6. Mask ----
    step = StepArtifact(step_name="mask", status="running", start_time=time.time())
    split_inputs = [p for p in Path(dirs["splits"]).glob("*.pkl")]
    for p in split_inputs:
        step.inputs.append({"name": p.name, "path": str(p),
                            "rows": _count_rows(str(p))})

    if "mask" in skip_steps or not split_inputs:
        step.status = "skipped"
        step.message = "跳过或无输入"
    else:
        try:
            for sp in split_inputs:
                ns = argparse.Namespace(
                    input=str(sp),
                    data_dir=output_root,
                    output_dir=dirs["masked"],
                    fields=None,
                    hash_fields=None, drop_fields=None,
                    all=False, salt=mask_salt,
                    prefix=f"{sp.stem}_",
                    keep_card_prefix=True,
                )
                rc = masker.cmd_mask(ns)
                if rc != 0:
                    logger.warning(f"脱敏 {sp.name} 返回码={rc}")
            step.status = "success"
            for p in Path(dirs["masked"]).glob("*"):
                step.outputs.append({"name": p.name, "path": str(p),
                                     "rows": _count_rows(str(p))})
            step.message = f"处理 {len(split_inputs)} 个拆分文件"
        except Exception as e:
            step.status = "failed"
            step.message = f"异常: {e}"
            logger.exception("mask 步骤异常")
    step.end_time = time.time()
    manifest.steps.append(step)

    # ---- 7. Report ----
    step = StepArtifact(step_name="report", status="running", start_time=time.time())
    report_inputs = [str(labeled_pkl)] if labeled_pkl.exists() else []
    for s in split_inputs:
        report_inputs.append(str(s))
    for p in report_inputs:
        step.inputs.append({"name": Path(p).name, "path": str(p),
                            "rows": _count_rows(str(p))})

    if "report" in skip_steps or not report_inputs:
        step.status = "skipped"
        step.message = "跳过或无输入"
    else:
        try:
            ns = argparse.Namespace(
                inputs=report_inputs,
                data_dir=output_root,
                output_dir=dirs["reports"],
                time_col="txn_time",
                cat_cols=None, num_cols=None, key_cols=None,
                top_k=15,
            )
            rc = reporter.cmd_report(ns)
            step.status = "success" if rc == 0 else "failed"
            for p in Path(dirs["reports"]).glob("*"):
                step.outputs.append({"name": p.name, "path": str(p),
                                     "rows": _count_rows(str(p))})
            step.message = f"返回码={rc}"
        except Exception as e:
            step.status = "failed"
            step.message = f"异常: {e}"
            logger.exception("report 步骤异常")
    step.end_time = time.time()
    manifest.steps.append(step)

    # ---- 8. Export ----
    step = StepArtifact(step_name="export", status="running", start_time=time.time())
    mask_files = list(Path(dirs["masked"]).glob("*"))
    for p in mask_files:
        if p.suffix in (".pkl", ".csv"):
            step.inputs.append({"name": p.name, "path": str(p),
                                "rows": _count_rows(str(p))})

    if "export" in skip_steps or not mask_files:
        step.status = "skipped"
        step.message = "跳过或无输入"
    else:
        try:
            ns = argparse.Namespace(
                input=None,
                data_dir=output_root,
                subdir="masked",
                pattern=["*.pkl", "*.csv"],
                output_dir=dirs["exported"],
                format=export_formats,
                include=export_include,
                exclude=export_exclude,
                rename=None, split_by=None,
                label_filter=None,
                date_from=None, date_to=None,
                time_col="txn_time",
                sample=None, seed=42,
                dedup=False, drop_na=False,
                drop_na_mode="threshold",
                drop_na_rows=False, drop_na_subset=None,
                drop_na_row_mode="any",
                prefix=export_prefix,
                encoding="utf-8-sig", sep=",",
                json_orient="records",
                config=None, include_raw=False,
                samplesheet=False,
                sample_format="full",
                id_col="txn_id",
            )
            rc = exporter.cmd_export(ns)
            step.status = "success" if rc == 0 else "failed"
            for p in Path(dirs["exported"]).glob("*"):
                step.outputs.append({"name": p.name, "path": str(p),
                                     "rows": _count_rows(str(p))})
            step.message = f"返回码={rc}, 格式={export_formats}"
        except Exception as e:
            step.status = "failed"
            step.message = f"异常: {e}"
            logger.exception("export 步骤异常")
    step.end_time = time.time()
    manifest.steps.append(step)

    # ---- 收尾 ----
    # 执行质量门禁（在 finalize 之前，以便把结果写入 manifest.summary）
    try:
        qg = _run_quality_gates(manifest, dirs, task_cfg)
    except Exception as e:
        logger.warning(f"Quality Gates 执行异常 (非致命): {e}")
        qg = []

    return _finalize_manifest(manifest, dirs["reports"], output_root, dirs, qg)


def _run_quality_gates(manifest: BatchManifest, dirs: Dict[str, str],
                       task_cfg: Dict) -> List[Dict[str, Any]]:
    """执行质量门禁。返回 [{rule, status, severity, detail}]"""
    results: List[Dict[str, Any]] = []

    def _add(rule: str, status: str, severity: str, detail: str):
        results.append({"规则": rule, "结果": status, "严重级别": severity, "详情": detail})

    qg_cfg = (task_cfg or {}).get("quality_gates", {}) or {}
    high_null_threshold = float((task_cfg.get("import") or {}).get("high_null_threshold", 0.3) or 0.3)
    warn_fraud_range = qg_cfg.get("fraud_rate_warn_range", [0.0005, 0.15])  # 0.05%~15%
    block_train_empty = bool(qg_cfg.get("block_on_empty_train", True))
    block_missing_required = bool(qg_cfg.get("block_on_missing_required", False))
    max_fraud_rate_volatility = float(qg_cfg.get("max_fraud_rate_volatility_pct", 50.0))  # 环比波动阈值 %

    # ---- Gate 1: 必填字段缺失 (从 import 报告读取) ----
    missing_report = Path(dirs["imported"]) / "import_field_check_report.csv"
    missing_required_files: List[str] = []
    high_null_cols: List[str] = []
    if missing_report.exists():
        try:
            rep = pd.read_csv(missing_report, encoding="utf-8-sig")
            if "严重程度" in rep.columns:
                miss_req = rep[(rep["严重程度"] == "必填缺失")]
                for _, r in miss_req.iterrows():
                    missing_required_files.append(f"{r.get('文件','?')}:{r.get('字段','?')}")
                nulls = rep[(rep["严重程度"] == "高比例空值")]
                for _, r in nulls.iterrows():
                    high_null_cols.append(f"{r.get('文件','?')}:{r.get('字段','?')}({r.get('空值率',0)})")
        except Exception as e:
            logger.warning(f"读 import 字段检查报告异常: {e}")
    if missing_required_files:
        _add("G1_必填字段缺失",
             "BLOCK" if block_missing_required else "WARN",
             "critical" if block_missing_required else "major",
             f"缺失字段数: {len(missing_required_files)}。" + "|".join(missing_required_files)[:300])
    else:
        _add("G1_必填字段缺失", "PASS", "none", "所有必填字段齐全")
    if high_null_cols:
        _add("G1b_高比例空值列", "WARN", "major",
             f"高比例空值列(>{int(high_null_threshold*100)}%)共 {len(high_null_cols)} 列: "
             + "|".join(high_null_cols)[:300])
    else:
        _add("G1b_高比例空值列", "PASS", "none", f"无空值率超过 {int(high_null_threshold*100)}% 的列")

    # ---- Gate 2: 训练集/主集为空 ----
    # labeled 集和 train split
    labeled_p = Path(dirs["labeled"]) / "transactions_labeled.pkl"
    train_p = Path(dirs["splits"]) / "train.pkl"
    labeled_count = 0
    if labeled_p.exists():
        try:
            labeled_count = len(pd.read_pickle(str(labeled_p)))
        except Exception:
            labeled_count = 0
    train_count = 0
    if train_p.exists():
        try:
            train_count = len(pd.read_pickle(str(train_p)))
        except Exception:
            train_count = 0

    if labeled_count == 0:
        _add("G2_主集(labeled)样本为空",
             "BLOCK" if block_train_empty else "WARN",
             "critical",
             "transactions_labeled.pkl 行数为 0，无法建模")
    else:
        _add("G2_主集(labeled)样本为空", "PASS", "none",
             f"主集样本数 = {labeled_count}")

    if train_count == 0 and train_p.exists():
        _add("G2b_训练集(train)为空",
             "BLOCK" if block_train_empty else "WARN",
             "major",
             "train.pkl 行数为 0，模型训练将失败")
    else:
        _add("G2b_训练集(train)为空", "PASS", "none",
             f"train 样本数 = {train_count}")

    # ---- Gate 3: 欺诈率异常波动 (对比最近一次历史跑批) ----
    if labeled_count > 0:
        # 读当前欺诈率
        try:
            df = pd.read_pickle(str(labeled_p))
            cur_fr = 0.0
            if "fraud_label" in df.columns and len(df) > 0:
                cur_fr = float((df["fraud_label"] == 1).sum() / len(df) * 100)
            # 找历史
            try:
                hist = _read_history(limit=5)
                prev_fr: Optional[float] = None
                for h in hist[1:]:
                    km = h.get("key_metrics") or {}
                    fr = km.get("fraud_rate_pct")
                    if fr is not None and km.get("txn_total", 0) > 0:
                        prev_fr = float(fr)
                        break
                if prev_fr is not None:
                    if prev_fr > 0:
                        vol = abs(cur_fr - prev_fr) / prev_fr * 100
                    else:
                        vol = float("inf") if cur_fr > 0 else 0.0
                    if vol > max_fraud_rate_volatility and cur_fr > 0:
                        _add("G3_欺诈率环比异常波动", "WARN", "major",
                             f"当前={cur_fr:.4f}%, 上次={prev_fr:.4f}%, "
                             f"环比变动={vol:.1f}%，超过阈值={max_fraud_rate_volatility}%")
                    else:
                        _add("G3_欺诈率环比异常波动", "PASS", "none",
                             f"当前={cur_fr:.4f}%, 上次={prev_fr:.4f}%, 环比={vol:.1f}%")
                else:
                    _add("G3_欺诈率环比异常波动", "SKIP", "none",
                         f"无可对比历史，当前={cur_fr:.4f}%")
            except Exception as e:
                _add("G3_欺诈率环比异常波动", "SKIP", "none", f"读历史失败: {e}")
        except Exception as e:
            _add("G3_欺诈率环比异常波动", "SKIP", "none", f"计算失败: {e}")
    else:
        _add("G3_欺诈率环比异常波动", "SKIP", "none", "主集为空，跳过")

    # ---- Gate 4: 欺诈率范围合理性 (0.05%~15% 经验范围) ----
    if labeled_count > 0 and "fraud_label" in df.columns:
        fr = float((df["fraud_label"] == 1).sum() / max(len(df), 1) * 100)
        lo, hi = float(warn_fraud_range[0]) * 100, float(warn_fraud_range[1]) * 100
        if fr < lo:
            _add("G4_欺诈率范围合理性", "WARN", "minor",
                 f"欺诈率={fr:.4f}% 低于经验下限 {lo:.2f}%，可能样本或标签异常")
        elif fr > hi:
            _add("G4_欺诈率范围合理性", "WARN", "minor",
                 f"欺诈率={fr:.4f}% 高于经验上限 {hi:.2f}%，可能样本或标签异常")
        else:
            _add("G4_欺诈率范围合理性", "PASS", "none",
                 f"欺诈率={fr:.4f}%，在合理区间 [{lo:.2f}%, {hi:.2f}%]")
    else:
        _add("G4_欺诈率范围合理性", "SKIP", "none", "主集为空或无标签列，跳过")

    # 写入结果到 manifest
    manifest.quality_gates = results  # type: ignore[attr-defined]
    # CSV
    ensure_dir(dirs["reports"])
    pd.DataFrame(results).to_csv(Path(dirs["reports"]) / "quality_gates_report.csv",
                                 index=False, encoding="utf-8-sig")
    return results


def _finalize_manifest(manifest: BatchManifest, report_dir: str,
                       output_root: str = None, dirs: Dict = None,
                       quality_gates: List[Dict[str, Any]] = None) -> int:
    """收尾：生成并保存清单文件"""
    manifest.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ensure_dir(report_dir)

    # 汇总统计
    success = sum(1 for s in manifest.steps if s.status == "success")
    skipped = sum(1 for s in manifest.steps if s.status == "skipped")
    failed = sum(1 for s in manifest.steps if s.status == "failed")
    qg_list = quality_gates or []
    qg_pass = sum(1 for q in qg_list if q.get("结果") == "PASS")
    qg_warn = sum(1 for q in qg_list if q.get("结果") == "WARN")
    qg_block = sum(1 for q in qg_list if q.get("结果") == "BLOCK")
    manifest.summary = {
        "任务名": manifest.task_name,
        "成功步骤": success,
        "跳过步骤": skipped,
        "失败步骤": failed,
        "总步骤": len(manifest.steps),
        "总耗时(秒)": round(manifest.total_duration(), 2),
        "QG通过": qg_pass,
        "QG警告": qg_warn,
        "QG阻断": qg_block,
    }

    # CSV 清单
    df = manifest.to_dataframe()
    csv_path = Path(report_dir) / "batch_manifest.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Markdown 清单
    md_path = Path(report_dir) / "batch_manifest.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(manifest.to_markdown())
        f.write("\n## 汇总\n\n")
        for k, v in manifest.summary.items():
            f.write(f"- **{k}**: {v}\n")
        # Quality Gates 追加
        qg_list = quality_gates or []
        if qg_list:
            f.write("\n## Quality Gates（质量门禁）\n\n")
            f.write("| 规则 | 结果 | 严重级别 | 详情 |\n")
            f.write("|------|------|----------|------|\n")
            for q in qg_list:
                icon = "✅" if q.get("结果") == "PASS" else (
                    "⏭" if q.get("结果") == "SKIP" else (
                        "🔴" if q.get("结果") == "BLOCK" else "🟠"))
                f.write(f"| {q.get('规则','')} | {icon} {q.get('结果','')} | {q.get('严重级别','')} | {str(q.get('详情','')).replace('|',';')[:200]} |\n")
            f.write(f"\n> 完整清单: quality_gates_report.csv\n")

    # 总览打印
    print("\n" + "=" * 70)
    print(f"[批处理完成] 任务: {manifest.task_name}")
    print("=" * 70)
    print(df.to_string(index=False))
    print("-" * 70)
    for k, v in manifest.summary.items():
        print(f"  {k}: {v}")

    # Quality Gates 打印
    qg_list = quality_gates or []
    if qg_list:
        print("-" * 70)
        print("[Quality Gates 结果]")
        qg_df = pd.DataFrame(qg_list)
        print(qg_df.to_string(index=False))

    print(f"\n清单文件:")
    print(f"  CSV:  {csv_path}")
    print(f"  MD:   {md_path}")
    if qg_list:
        print(f"  QG:   {Path(report_dir) / 'quality_gates_report.csv'}")
    if output_root:
        print(f"  数据根目录: {output_root}")
    print("=" * 70)

    # 写入任务历史台账
    try:
        _append_run_history(manifest, config_path_resolved=manifest.config_path,
                            output_root=output_root or "",
                            report_dir=report_dir, dirs=dirs or {})
    except Exception as e:
        logger.warning(f"写入任务历史台账失败 (非致命): {e}")

    if failed > 0:
        return 10 + failed
    return 0


def register_subparser(subparsers) -> None:
    """注册 run / history 子命令"""
    # --- run ---
    p = subparsers.add_parser(
        "run", aliases=["batch"],
        help="通过 YAML 配置文件执行完整批处理流程（推荐长期跑批使用）",
        description="""
示例:
  fraud-org run -c batch_config.yaml
  fraud-org batch --config my_task.yaml --verbose
""")
    p.add_argument("-c", "--config", required=True,
                   help="批处理 YAML 配置文件路径")
    p.set_defaults(func=cmd_run)

    # --- history list ---
    pl = subparsers.add_parser(
        "history", aliases=["hist", "runs", "list"],
        help="任务历史台账（回看每次跑批结果）",
        description="""
示例:
  fraud-org history list -n 20           # 最近 20 次跑批
  fraud-org history show <run_id>        # 某次跑批详情
  fraud-org history show --last          # 最近一次详情
""")
    pl.set_defaults(func=lambda a: cmd_history(a) if getattr(a, "subcmd", None) else (cmd_history_list(a) or 0))

    psub = pl.add_subparsers(dest="subcmd", help="history 子命令")

    plist = psub.add_parser("list", help="列出历史跑批记录 (默认)")
    plist.add_argument("-n", "--limit", type=int, default=20,
                       help="显示最近 N 条 (默认 20)")
    plist.add_argument("-s", "--status", choices=["all", "success", "failed", "partial"],
                       default="all", help="按状态过滤")
    plist.add_argument("--task-name", help="按任务名模糊匹配")
    plist.add_argument("--json", action="store_true", help="JSON 格式输出")
    plist.set_defaults(func=cmd_history_list)

    pshow = psub.add_parser("show", help="查看某一次跑批的详细信息")
    pshow_src = pshow.add_mutually_exclusive_group()
    pshow_src.add_argument("run_id", nargs="?", help="跑批ID（见 history list 首列）")
    pshow_src.add_argument("--last", action="store_true", help="查看最近一次跑批")
    pshow_src.add_argument("--output-dir", help="通过输出目录反查")
    pshow.add_argument("--output-json", help="将详情另存为 JSON 文件")
    pshow.set_defaults(func=cmd_history_show)


# ============================================================
# 任务历史台账 - 读写
# ============================================================

HISTORY_FILE = ".fraud_organizer_history.jsonl"


def _history_dir() -> Path:
    """历史台账存放目录：优先用户家目录，次选当前目录父级"""
    home = Path.home() / ".fraud_organizer"
    try:
        home.mkdir(parents=True, exist_ok=True)
        return home
    except Exception:
        return Path.cwd()


def _history_path() -> Path:
    return _history_dir() / HISTORY_FILE


def _load_key_metrics_from_dirs(dirs: Dict[str, str]) -> Dict[str, Any]:
    """从各步骤目录抽取关键指标（用于 history 摘要展示）"""
    metrics: Dict[str, Any] = {}
    try:
        lbl_path = Path(dirs.get("labeled", "")) / "transactions_labeled.pkl"
        if lbl_path.exists():
            df = pd.read_pickle(str(lbl_path))
            metrics["txn_total"] = int(len(df))
            if "fraud_label" in df.columns and len(df) > 0:
                vc = df["fraud_label"].value_counts(dropna=False).to_dict()
                metrics["fraud_count"] = int(vc.get(1, 0))
                metrics["suspect_count"] = int(vc.get(2, 0))
                metrics["genuine_count"] = int(vc.get(0, 0))
                total = len(df)
                metrics["fraud_rate_pct"] = round(vc.get(1, 0) / total * 100, 4) if total > 0 else 0.0
    except Exception as e:
        metrics["_metrics_error"] = str(e)
    return metrics


def _append_run_history(manifest: BatchManifest, config_path_resolved: str,
                        output_root: str, report_dir: str,
                        dirs: Dict[str, str]) -> None:
    """追加一次跑批记录到本地 JSONL 台账"""
    hp = _history_path()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + \
        str(abs(hash((manifest.task_name, manifest.start_time))) % 10000).zfill(4)

    summary = manifest.summary or {}
    key_metrics = _load_key_metrics_from_dirs(dirs)

    # 步骤简表（不展开每个文件，省空间）
    steps_slim = [
        {
            "step": s.step_name,
            "status": s.status,
            "duration_sec": round(s.duration, 3),
            "in_files": len(s.inputs),
            "out_files": len(s.outputs),
            "msg": s.message[:80] if s.message else "",
        } for s in (manifest.steps or [])
    ]

    record = {
        "run_id": run_id,
        "task_name": manifest.task_name,
        "start_time": manifest.start_time,
        "end_time": manifest.end_time,
        "duration_sec": round(manifest.total_duration(), 3),
        "status": "success" if summary.get("失败步骤", 0) == 0 else (
            "partial" if summary.get("成功步骤", 0) > 0 else "failed"),
        "config_path": config_path_resolved,
        "output_root": str(Path(output_root).resolve()) if output_root else "",
        "report_dir": str(Path(report_dir).resolve()),
        "manifest_csv": str((Path(report_dir) / "batch_manifest.csv").resolve()),
        "manifest_md": str((Path(report_dir) / "batch_manifest.md").resolve()),
        "summary": summary,
        "steps": steps_slim,
        "key_metrics": key_metrics,
    }

    line = json.dumps(record, ensure_ascii=False, default=str)
    with open(hp, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    logger.info(f"跑批记录已写入台账: {hp} (run_id={run_id})")


def _read_history(limit: int = 1000) -> List[Dict[str, Any]]:
    """读取全部历史记录（最近的在前）"""
    hp = _history_path()
    if not hp.exists():
        return []
    records: List[Dict[str, Any]] = []
    with open(hp, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                records.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    records.sort(key=lambda r: r.get("start_time", ""), reverse=True)
    if limit and len(records) > limit:
        records = records[:limit]
    return records


def cmd_history(args: argparse.Namespace) -> int:
    """history 默认行为：list"""
    return cmd_history_list(args)


def cmd_history_list(args: argparse.Namespace) -> int:
    """列出历史跑批"""
    records = _read_history()

    # 过滤
    status = getattr(args, "status", "all")
    task_name = getattr(args, "task_name", None)
    if status != "all":
        records = [r for r in records if r.get("status") == status]
    if task_name:
        records = [r for r in records if task_name.lower() in (r.get("task_name") or "").lower()]

    limit = getattr(args, "limit", 20)
    records = records[:limit]

    if getattr(args, "json", False):
        print(json.dumps(records, ensure_ascii=False, indent=2, default=str))
        return 0

    if not records:
        print("[信息] 暂无跑批历史记录。先执行 fraud-org run -c <配置.yaml> 开始第一次跑批。")
        print(f"       台账文件: {_history_path()}")
        return 0

    rows = []
    for r in records:
        km = r.get("key_metrics") or {}
        rows.append({
            "RUN_ID": r.get("run_id", ""),
            "开始时间": r.get("start_time", ""),
            "任务名": r.get("task_name", ""),
            "状态": r.get("status", ""),
            "耗时(s)": r.get("duration_sec", ""),
            "步骤": f"{(r.get('summary') or {}).get('成功步骤','?')}/{(r.get('summary') or {}).get('总步骤','?')}",
            "交易数": km.get("txn_total", "-"),
            "欺诈数": km.get("fraud_count", "-"),
            "欺诈率(%)": f"{km['fraud_rate_pct']:.2f}" if "fraud_rate_pct" in km else "-",
            "输出目录": (r.get("output_root") or "")[:40],
        })
    df = pd.DataFrame(rows)
    pd.set_option("display.max_colwidth", 40)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))
    print(f"\n台账文件: {_history_path()}")
    print(f"总数: {len(records)} (使用 fraud-org history show <RUN_ID> 查看详情)")
    return 0


def cmd_history_show(args: argparse.Namespace) -> int:
    """查看单次跑批详情"""
    records = _read_history()
    if not records:
        print("[错误] 暂无历史记录")
        return 1

    target = None
    if getattr(args, "last", False):
        target = records[0]
    elif getattr(args, "run_id", None):
        rid = args.run_id
        # 支持前缀匹配
        matches = [r for r in records if r.get("run_id", "").startswith(rid)]
        if not matches:
            # 完全匹配历史里没有，再试一次
            matches = [r for r in records if r.get("run_id") == rid]
        if matches:
            target = matches[0]
    elif getattr(args, "output_dir", None):
        od = str(Path(args.output_dir).resolve())
        for r in records:
            if (r.get("output_root") and str(Path(r["output_root"]).resolve()) == od) or \
               (r.get("report_dir") and str(Path(r["report_dir"]).resolve()) == od):
                target = r
                break

    if target is None:
        print("[错误] 未找到匹配的历史记录。用 fraud-org history list 先看 RUN_ID。")
        return 1

    # 另存 JSON
    out_json = getattr(args, "output_json", None)
    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(target, f, ensure_ascii=False, indent=2, default=str)
        print(f"[完成] 详情已保存: {out_json}")

    km = target.get("key_metrics") or {}
    summary = target.get("summary") or {}
    print("=" * 70)
    print(f"[跑批详情] RUN_ID = {target.get('run_id')}")
    print("=" * 70)
    print(f"  任务名        : {target.get('task_name')}")
    print(f"  开始时间      : {target.get('start_time')}")
    print(f"  结束时间      : {target.get('end_time')}")
    print(f"  总耗时(s)     : {target.get('duration_sec')}")
    print(f"  状态          : {target.get('status')}")
    print(f"  配置文件      : {target.get('config_path')}")
    print(f"  输出根目录    : {target.get('output_root')}")
    print(f"  报告目录      : {target.get('report_dir')}")
    print(f"  清单(CSV)     : {target.get('manifest_csv')}")
    print(f"  清单(Markdown): {target.get('manifest_md')}")
    print("-" * 70)
    print("关键指标:")
    for k in ["txn_total", "fraud_count", "suspect_count", "genuine_count"]:
        if k in km:
            print(f"  {k:<16}: {km[k]}")
    if "fraud_rate_pct" in km:
        print(f"  fraud_rate_pct  : {km['fraud_rate_pct']:.4f}%")
    print("-" * 70)
    print("步骤执行情况:")
    steps_df = pd.DataFrame(target.get("steps") or [])
    if len(steps_df) > 0:
        steps_df = steps_df.rename(columns={
            "step": "步骤", "status": "状态", "duration_sec": "耗时(s)",
            "in_files": "入文件", "out_files": "出文件", "msg": "说明"
        })
        print(steps_df.to_string(index=False))
    print("=" * 70)
    return 0
