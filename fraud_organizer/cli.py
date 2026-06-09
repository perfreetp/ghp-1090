"""命令行主入口"""

import sys
import argparse
import logging

from . import __version__
from .utils import setup_logging
from .commands import (
    importer, cleaner, labeler, profiler,
    splitter, masker, reporter, exporter, runner,
)

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """创建参数解析器"""
    parser = argparse.ArgumentParser(
        prog="fraud-org",
        description="信用卡欺诈样本整理器 - 银行反欺诈分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
命令示例:
  # 方式一: 批处理配置（推荐长期跑批、日常调度使用）
  fraud-org run -c batch_config.yaml
  fraud-org batch --config monthly_task.yaml --verbose

  # 方式二: 一键完整流水线
  fraud-org pipeline -t txns*.csv -c chargebacks.xlsx -b blacklist.csv

  # 方式三: 单步执行（调试、局部重跑用）
  fraud-org import -t txns_2024*.csv -c chargebacks.xlsx -b blacklist.csv
  fraud-org clean
  fraud-org label
  fraud-org profile --top-n 30
  fraud-org split -m ratio --ratios 0.7 0.15
  fraud-org mask --all
  fraud-org report
  fraud-org export -f csv xlsx
        """,
    )

    parser.add_argument("-v", "--verbose", action="store_true",
                        help="开启调试日志")
    parser.add_argument("--version", action="version",
                        version=f"fraud-org v{__version__}")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    importer.register_subparser(subparsers)
    cleaner.register_subparser(subparsers)
    labeler.register_subparser(subparsers)
    profiler.register_subparser(subparsers)
    splitter.register_subparser(subparsers)
    masker.register_subparser(subparsers)
    reporter.register_subparser(subparsers)
    exporter.register_subparser(subparsers)
    runner.register_subparser(subparsers)

    # 流水线命令
    pipeline = subparsers.add_parser("pipeline", aliases=["all"],
                                     help="一键执行完整流水线 (import->clean->label->profile->split->mask->report->export)")
    pipeline.add_argument("-t", "--transactions", nargs="+", metavar="FILE",
                          help="交易文件路径")
    pipeline.add_argument("-c", "--chargebacks", nargs="+", metavar="FILE",
                          help="拒付文件路径")
    pipeline.add_argument("-b", "--blacklists", nargs="+", metavar="FILE",
                          help="黑名单文件路径")
    pipeline.add_argument("-d", "--data-dir", default="./data",
                          help="数据根目录")
    pipeline.add_argument("--skip", nargs="+", default=[],
                          choices=["import", "clean", "label", "profile",
                                   "split", "mask", "report", "export"],
                          help="跳过指定步骤")
    pipeline.add_argument("--formats", nargs="+", default=["csv", "xlsx"],
                          help="导出格式 (默认: csv xlsx)")
    pipeline.set_defaults(func=cmd_pipeline)

    return parser


def cmd_pipeline(args: argparse.Namespace) -> int:
    """执行完整流水线"""
    from .utils import ensure_dir
    import argparse as _ap

    data_dir = args.data_dir
    ensure_dir(data_dir)

    steps = [
        ("import", ["import"]),
        ("clean", ["clean"]),
        ("label", ["label"]),
        ("profile", ["profile"]),
        ("split", ["split"]),
        ("mask", ["mask", "--all"]),
        ("report", ["report"]),
        ("export", ["export", "-f"] + list(args.formats or ["csv", "xlsx"])),
    ]

    parser = create_parser()

    for step_name, step_args in steps:
        if step_name in args.skip:
            print(f"\n[-] 跳过步骤: {step_name}")
            continue

        print(f"\n{'=' * 60}")
        print(f">> 执行步骤: {step_name}")
        print(f"{'=' * 60}")

        full_args = step_args[:]
        if step_name == "import":
            if args.transactions:
                full_args += ["-t"] + args.transactions
            if args.chargebacks:
                full_args += ["-c"] + args.chargebacks
            if args.blacklists:
                full_args += ["-b"] + args.blacklists
            full_args += ["-o", f"{data_dir}/imported", "--force"]
        elif step_name == "clean":
            full_args += [
                "-i", f"{data_dir}/imported/transactions_raw.pkl",
                "-d", f"{data_dir}/imported",
                "-o", f"{data_dir}/cleaned",
            ]
        elif step_name == "label":
            full_args += [
                "-i", f"{data_dir}/cleaned/transactions_clean.pkl",
                "-d", data_dir,
                "-o", f"{data_dir}/labeled",
            ]
        elif step_name == "profile":
            full_args += [
                "-i", f"{data_dir}/labeled/transactions_labeled.pkl",
                "-d", data_dir,
                "-o", f"{data_dir}/profiled",
            ]
        elif step_name == "split":
            full_args += [
                "-i", f"{data_dir}/labeled/transactions_labeled.pkl",
                "-d", data_dir,
                "-o", f"{data_dir}/splits",
                "--export-csv",
            ]
        elif step_name == "mask":
            full_args += [
                "-i", f"{data_dir}/splits/train.pkl",
                "-d", data_dir,
                "-o", f"{data_dir}/masked",
                "--prefix", "train_",
            ]
            # 额外处理 valid 和 backtest
        elif step_name == "report":
            full_args += [
                "-d", data_dir,
                "-o", f"{data_dir}/reports",
            ]
        elif step_name == "export":
            full_args += [
                "-s", "masked",
                "-d", data_dir,
                "-o", f"{data_dir}/exported",
                "-f"] + list(args.formats or ["csv", "xlsx"])

        try:
            parsed = parser.parse_args(full_args)
            setup_logging(args.verbose)
            rc = parsed.func(parsed)
            if rc != 0:
                print(f"[错误] 步骤 {step_name} 执行失败 (返回码: {rc})")
                if step_name in ("import", "clean", "label"):
                    return rc
                print(f"[警告] 非核心步骤失败，继续执行后续步骤")
        except Exception as e:
            print(f"[错误] 步骤 {step_name} 异常: {e}")
            if step_name in ("import", "clean", "label"):
                return 1

    print(f"\n{'=' * 60}")
    print("[完成] 流水线执行完毕！")
    print(f"{'=' * 60}")
    print(f"[数据目录] {data_dir}")
    for sub in ["imported", "cleaned", "labeled", "profiled",
                "splits", "masked", "reports", "exported"]:
        from pathlib import Path
        p = Path(data_dir) / sub
        if p.exists():
            n_files = len(list(p.iterdir()))
            print(f"  [{sub}] {n_files} 个文件")
    return 0


def main(argv=None) -> int:
    """程序主入口"""
    parser = create_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    setup_logging(args.verbose)

    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\n[警告] 用户中断")
        return 130
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
