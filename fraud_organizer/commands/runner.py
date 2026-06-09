"""批处理任务配置解析与运行器"""

import logging
import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

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
    output_root = ensure_dir(task_cfg.get("output_root", "./data/batch_output"))
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
    return _finalize_manifest(manifest, dirs["reports"], output_root, dirs)


def _finalize_manifest(manifest: BatchManifest, report_dir: str,
                       output_root: str = None, dirs: Dict = None) -> int:
    """收尾：生成并保存清单文件"""
    manifest.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ensure_dir(report_dir)

    # 汇总统计
    success = sum(1 for s in manifest.steps if s.status == "success")
    skipped = sum(1 for s in manifest.steps if s.status == "skipped")
    failed = sum(1 for s in manifest.steps if s.status == "failed")
    manifest.summary = {
        "任务名": manifest.task_name,
        "成功步骤": success,
        "跳过步骤": skipped,
        "失败步骤": failed,
        "总步骤": len(manifest.steps),
        "总耗时(秒)": round(manifest.total_duration(), 2),
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

    # 总览打印
    print("\n" + "=" * 70)
    print(f"[批处理完成] 任务: {manifest.task_name}")
    print("=" * 70)
    print(df.to_string(index=False))
    print("-" * 70)
    for k, v in manifest.summary.items():
        print(f"  {k}: {v}")
    print(f"\n清单文件:")
    print(f"  CSV:  {csv_path}")
    print(f"  MD:   {md_path}")
    if output_root:
        print(f"  数据根目录: {output_root}")
    print("=" * 70)

    if failed > 0:
        return 10 + failed
    return 0


def register_subparser(subparsers) -> None:
    """注册 run 子命令"""
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
