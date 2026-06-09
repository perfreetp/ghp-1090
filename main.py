#!/usr/bin/env python3
"""命令行入口包装脚本 (用于开发模式)

使用:
  python -m fraud_organizer.cli --help
  或
  python main.py --help
"""

from fraud_organizer.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
