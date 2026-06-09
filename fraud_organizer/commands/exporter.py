"""export 命令：按指定格式生成可交付文件"""

import logging
import argparse
from pathlib import Path
from typing import List, Optional

import pandas as pd
import numpy as np

from ..utils import read_file, save_file, ensure_dir, load_config

logger = logging.getLogger(__name__)


FORMAT_EXT = {
    "csv": ".csv",
    "xlsx": ".xlsx",
    "excel": ".xlsx",
    "parquet": ".parquet",
    "pickle": ".pkl",
    "pkl": ".pkl",
    "json": ".json",
    "tsv": ".tsv",
}


def _select_columns(df: pd.DataFrame, include: Optional[List[str]],
                    exclude: Optional[List[str]]) -> pd.DataFrame:
    """选择列"""
    cols = list(df.columns)
    if include:
        cols = [c for c in include if c in df.columns]
        missing = [c for c in include if c not in df.columns]
        if missing:
            logger.warning(f"  跳过不存在的列: {missing}")
    if exclude:
        cols = [c for c in cols if c not in exclude]
    return df[cols]


def _apply_value_mapping(df: pd.DataFrame,
                         mappings: dict) -> pd.DataFrame:
    """应用值映射"""
    for col, col_map in mappings.items():
        if col in df.columns and isinstance(col_map, dict):
            logger.info(f"  值映射: {col} -> {len(col_map)} 条规则")
            df[col] = df[col].map(lambda x: col_map.get(x, x) if pd.notna(x) else x)
    return df


def _rename_columns(df: pd.DataFrame, rename_map: dict) -> pd.DataFrame:
    """重命名列"""
    if not rename_map:
        return df
    actual = {k: v for k, v in rename_map.items() if k in df.columns}
    if actual:
        logger.info(f"  重命名列: {actual}")
        df = df.rename(columns=actual)
    return df


def _split_sheets(df: pd.DataFrame, split_by: Optional[str]) -> dict:
    """按列拆分为多sheet"""
    if not split_by or split_by not in df.columns:
        return {"Sheet1": df}
    sheets = {}
    for val, group in df.groupby(split_by, dropna=False):
        sheet_name = str(val).replace("/", "_").replace("\\", "_")[:31] or "EMPTY"
        sheets[sheet_name] = group.reset_index(drop=True)
    return sheets


def cmd_export(args: argparse.Namespace) -> int:
    """执行 export 命令"""
    data_dir = args.data_dir or "./data"
    output_dir = ensure_dir(args.output_dir)

    # 收集输入文件
    input_pairs = []  # (path, out_stem)

    if args.input:
        input_pairs.append((args.input, Path(args.input).stem))
    else:
        # 查找输入目录下的文件
        input_subdir = args.subdir or "masked"
        search_dir = Path(data_dir) / input_subdir
        if not search_dir.is_dir():
            search_dir = Path(data_dir)
        patterns = args.pattern or ["*.pkl", "*.csv"]
        for pat in patterns:
            for p in sorted(search_dir.glob(pat)):
                if "raw" in p.stem.lower() and not args.include_raw:
                    continue
                input_pairs.append((str(p), p.stem))

    if not input_pairs:
        logger.error("未找到可导出的文件")
        return 1

    # 加载配置
    config = load_config(args.config)
    include_cols = args.include or config.get("include_columns")
    exclude_cols = args.exclude or config.get("exclude_columns")
    rename_map = args.rename or config.get("rename_columns", {})
    value_maps = config.get("value_mappings", {})
    drop_na_cols = args.drop_na or config.get("drop_na_columns")
    drop_duplicates = args.dedup or config.get("drop_duplicates", False)

    formats = args.format or ["csv"]
    if isinstance(formats, str):
        formats = [formats]

    if args.samplesheet:
        # 生成样本提交格式
        return _export_samplesheet(args, input_pairs, output_dir)

    total_exported = 0

    for fp, stem in input_pairs:
        logger.info(f"处理文件: {fp}")
        df = read_file(fp)

        # 1. 去重
        if drop_duplicates:
            before = len(df)
            df = df.drop_duplicates()
            if before != len(df):
                logger.info(f"  去重: {before - len(df)} 行移除")

        # 2. 列筛选
        df = _select_columns(df, include_cols, exclude_cols)

        # 3. 重命名
        df = _rename_columns(df, rename_map)

        # 4. 值映射
        if value_maps:
            df = _apply_value_mapping(df, value_maps)

        # 5. 删除空值列
        if drop_na_cols:
            if args.drop_na_mode == "all":
                df = df.dropna(axis=1, how="all")
            else:
                threshold = len(df) * 0.5
                df = df.dropna(axis=1, thresh=int(threshold))
            logger.info(f"  删除空值列后剩余 {len(df.columns)} 列")

        # 6. 删除空行
        if args.drop_na_rows:
            subset = args.drop_na_subset or None
            before = len(df)
            df = df.dropna(subset=subset, how=args.drop_na_row_mode)
            if before != len(df):
                logger.info(f"  删除空行: {before - len(df)} 行移除")

        # 7. 按标签过滤
        if args.label_filter is not None:
            label_col = "fraud_label"
            if label_col in df.columns:
                before = len(df)
                df = df[df[label_col].astype(float).astype(int).isin(args.label_filter)]
                logger.info(f"  标签过滤 {args.label_filter}: {before} -> {len(df)}")

        # 8. 按日期过滤
        if (args.date_from or args.date_to) and (args.time_col or "txn_time") in df.columns:
            time_col = args.time_col or "txn_time"
            dt = pd.to_datetime(df[time_col], errors="coerce")
            mask = pd.Series(True, index=df.index)
            if args.date_from:
                mask &= dt >= pd.to_datetime(args.date_from)
            if args.date_to:
                mask &= dt <= pd.to_datetime(args.date_to + " 23:59:59")
            before = len(df)
            df = df[mask]
            logger.info(f"  日期过滤: {before} -> {len(df)}")

        # 9. 采样
        if args.sample and args.sample < len(df):
            df = df.sample(n=args.sample, random_state=args.seed)
            logger.info(f"  采样: {len(df)} 行")

        if len(df) == 0:
            logger.warning(f"  过滤/输入为空，生成占位文件")
            # 生成占位 CSV / Excel，确保下游调度无需分支判断
            for fmt in formats:
                ext = FORMAT_EXT.get(fmt.lower().strip(), ".csv")
                out_stem = args.prefix + stem if args.prefix else stem
                if fmt.lower() in ("xlsx", "excel"):
                    out_path = Path(output_dir) / f"{out_stem}{ext}"
                    with pd.ExcelWriter(str(out_path), engine="openpyxl") as writer:
                        df.to_excel(writer, index=False, sheet_name="数据(空占位)")
                        pd.DataFrame([
                            ["状态", "空数据集占位"],
                            ["原因", f"{stem} 过滤后为空"],
                            ["生成时间", str(pd.Timestamp.now())],
                        ]).to_excel(writer, sheet_name="说明", index=False, header=False)
                    logger.info(f"  占位 Excel: {out_path.name} (空数据集)")
                elif fmt.lower() in ("csv", "tsv"):
                    out_path = Path(output_dir) / f"{out_stem}{ext}"
                    df.to_csv(str(out_path), index=False,
                              encoding=args.encoding or "utf-8-sig",
                              sep="\t" if fmt.lower() == "tsv" else (args.sep or ","))
                    logger.info(f"  占位 {fmt.upper()}: {out_path.name} (0 行, 列骨架保留)")
                elif fmt.lower() in ("json", "jsonl"):
                    out_path = Path(output_dir) / f"{out_stem}{ext}"
                    df.to_json(str(out_path), orient="records", force_ascii=False)
                    logger.info(f"  占位 {fmt.upper()}: {out_path.name}")
                else:
                    # pickle/parquet 等仍然写空 DataFrame
                    out_path = Path(output_dir) / f"{out_stem}{ext}"
                    save_file(df, str(out_path))
                    logger.info(f"  占位 {fmt.upper()}: {out_path.name}")
                total_exported += 1
            _write_empty_export_note(output_dir, stem, "过滤或输入为空")
            continue

        # 10. 按格式导出
        for fmt in formats:
            ext = FORMAT_EXT.get(fmt.lower().strip(), ".csv")
            out_stem = args.prefix + stem if args.prefix else stem

            if fmt.lower() in ("xlsx", "excel"):
                out_path = Path(output_dir) / f"{out_stem}{ext}"
                sheets = _split_sheets(df, args.split_by)
                with pd.ExcelWriter(str(out_path), engine="openpyxl") as writer:
                    for sheet_name, sheet_df in sheets.items():
                        sheet_df.to_excel(writer, index=False, sheet_name=sheet_name)
                logger.info(f"  导出 Excel({len(sheets)} sheet): {out_path.name}")

            elif fmt.lower() == "csv":
                out_path = Path(output_dir) / f"{out_stem}{ext}"
                df.to_csv(str(out_path), index=False,
                          encoding=args.encoding or "utf-8-sig",
                          sep=args.sep or ",")
                logger.info(f"  导出 CSV: {out_path.name} ({len(df)} 行, {len(df.columns)} 列)")

            elif fmt.lower() == "tsv":
                out_path = Path(output_dir) / f"{out_stem}{ext}"
                df.to_csv(str(out_path), index=False,
                          encoding=args.encoding or "utf-8-sig", sep="\t")
                logger.info(f"  导出 TSV: {out_path.name}")

            elif fmt.lower() == "parquet":
                out_path = Path(output_dir) / f"{out_stem}{ext}"
                df.to_parquet(str(out_path), index=False)
                logger.info(f"  导出 Parquet: {out_path.name}")

            elif fmt.lower() in ("pickle", "pkl"):
                out_path = Path(output_dir) / f"{out_stem}{ext}"
                df.to_pickle(str(out_path))
                logger.info(f"  导出 Pickle: {out_path.name}")

            elif fmt.lower() == "json":
                out_path = Path(output_dir) / f"{out_stem}{ext}"
                orient = args.json_orient or "records"
                df.to_json(str(out_path), orient=orient,
                           force_ascii=False, indent=2)
                logger.info(f"  导出 JSON: {out_path.name}")

            else:
                logger.warning(f"  不支持的格式: {fmt}")
                continue

            total_exported += 1

    # 导出清单
    manifest = Path(output_dir) / "export_manifest.txt"
    with open(manifest, "w", encoding="utf-8") as f:
        f.write(f"导出时间: {pd.Timestamp.now()}\n")
        f.write(f"输出格式: {formats}\n")
        f.write(f"文件数量: {total_exported}\n")
        if include_cols:
            f.write(f"包含列: {include_cols}\n")
        if exclude_cols:
            f.write(f"排除列: {exclude_cols}\n")
        f.write("\n文件清单:\n")
        for p in sorted(Path(output_dir).iterdir()):
            if p.is_file() and p.name != manifest.name:
                size_kb = p.stat().st_size / 1024
                f.write(f"  {p.name:50s} {size_kb:>8.1f} KB\n")

    print(f"\n{'=' * 60}")
    print(f"[完成] 导出完成")
    print(f"  输出目录: {output_dir}")
    print(f"  格式: {', '.join(formats)}")
    print(f"  导出文件数: {total_exported}")
    print(f"  清单文件: {manifest}")
    return 0


def _export_samplesheet(args, input_pairs, output_dir) -> int:
    """生成竞赛/交付样本提交格式"""
    logger.info("生成样本提交格式...")

    fp = input_pairs[0][0]
    df = read_file(fp)

    id_col = args.id_col or "txn_id"
    label_col = "fraud_label"
    if id_col not in df.columns:
        logger.error(f"ID列 {id_col} 不存在")
        return 1

    result = pd.DataFrame({
        id_col: df[id_col],
        "fraud_label": df[label_col] if label_col in df.columns else -1,
        "probability": df["risk_score"].astype(float) / 100
        if "risk_score" in df.columns else 0.0,
    })

    if args.sample_format == "kaggle":
        result.columns = [id_col, "is_fraud"]
        out_path = Path(output_dir) / "sample_submission_kaggle.csv"
    elif args.sample_format == "simple":
        result = result[[id_col, "fraud_label"]]
        out_path = Path(output_dir) / "sample_submission.csv"
    else:
        out_path = Path(output_dir) / "sample_submission_full.csv"

    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[完成] 样本提交格式已生成: {out_path}")
    print(result.head().to_string(index=False))
    return 0


def register_subparser(subparsers) -> None:
    """注册 export 子命令"""
    p = subparsers.add_parser("export", help="按指定格式生成可交付文件")
    p.add_argument("-i", "--input", help="单个输入文件（不指定则批量导出）")
    p.add_argument("-d", "--data-dir", default="./data",
                   help="数据根目录 (默认: ./data)")
    p.add_argument("-s", "--subdir", default="masked",
                   help="搜索的子目录名 (默认: masked)")
    p.add_argument("-p", "--pattern", nargs="+",
                   help="文件匹配模式 (默认: *.pkl *.csv)")
    p.add_argument("-o", "--output-dir", default="./data/exported",
                   help="输出目录 (默认: ./data/exported)")
    p.add_argument("-f", "--format", nargs="+", default=["csv"],
                   choices=["csv", "xlsx", "excel", "parquet", "pickle", "pkl", "json", "tsv"],
                   help="输出格式，可多选 (默认: csv)")
    p.add_argument("--include", nargs="+", metavar="COL", help="只导出指定列")
    p.add_argument("--exclude", nargs="+", metavar="COL", help="排除指定列")
    p.add_argument("--rename", nargs="*", metavar="OLD=NEW",
                   help="重命名列，格式: 旧列名=新列名")
    p.add_argument("--split-by", metavar="COL",
                   help="Excel 导出时按此列拆分为多个 Sheet")
    p.add_argument("--label-filter", type=int, nargs="+",
                   help="按标签过滤: 0=真实 1=欺诈 2=可疑")
    p.add_argument("--date-from", metavar="YYYY-MM-DD", help="起始日期过滤")
    p.add_argument("--date-to", metavar="YYYY-MM-DD", help="截止日期过滤")
    p.add_argument("--time-col", default="txn_time", help="日期过滤用的时间列")
    p.add_argument("--sample", type=int, help="随机采样行数")
    p.add_argument("--seed", type=int, default=42, help="随机种子")
    p.add_argument("--dedup", action="store_true", help="导出前去重")
    p.add_argument("--drop-na", action="store_true", help="删除空值列")
    p.add_argument("--drop-na-mode", choices=["all", "threshold"], default="threshold",
                   help="删除空值列方式")
    p.add_argument("--drop-na-rows", action="store_true", help="删除含空值的行")
    p.add_argument("--drop-na-subset", nargs="+", help="删行只检查这些列")
    p.add_argument("--drop-na-row-mode", choices=["any", "all"], default="any",
                   help="删行条件")
    p.add_argument("--prefix", default="", help="输出文件名前缀")
    p.add_argument("--encoding", default="utf-8-sig", help="CSV/TSV 编码")
    p.add_argument("--sep", default=",", help="CSV 分隔符")
    p.add_argument("--json-orient", default="records",
                   choices=["records", "columns", "index", "values", "table"],
                   help="JSON 导出方向")
    p.add_argument("--config", help="YAML 配置文件（含列名/值映射）")
    p.add_argument("--include-raw", action="store_true",
                   help="包含 raw 原始文件")
    p.add_argument("--samplesheet", action="store_true",
                   help="生成样本提交格式")
    p.add_argument("--sample-format", choices=["full", "kaggle", "simple"],
                   default="full", help="样本提交格式类型")
    p.add_argument("--id-col", default="txn_id", help="样本提交格式的ID列")
    p.set_defaults(func=cmd_export)


def _write_empty_export_note(output_dir: str, stem: str, reason: str) -> None:
    """在导出目录写空数据说明（追加，避免多次覆盖）"""
    ensure_dir(output_dir)
    note_path = Path(output_dir) / "EMPTY_EXPORT_NOTE.txt"
    ts = pd.Timestamp.now()
    line = f"[{ts}] 文件={stem} 原因={reason}\n"
    try:
        if not note_path.exists():
            header = (
                "空导出说明\n"
                "==========\n"
                "说明: 本目录下文件名包含「空占位」或0行的 CSV/Excel/JSON 等，"
                "是输入数据为空或过滤后无匹配记录时自动生成的。\n"
                "      目的是让下游调度系统无需分支判断即可正常处理，避免因文件缺失导致失败。\n\n"
                "处理建议:\n"
                "  - 检查上游 import/label/split 步骤是否产出有效样本\n"
                "  - 检查 exporter --label-filter / --date-from / --date-to / --sample 等过滤参数是否过于严格\n\n"
                "具体明细（每个空输出一行）:\n"
            )
            with open(note_path, "w", encoding="utf-8") as f:
                f.write(header)
        with open(note_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
