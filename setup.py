from setuptools import setup, find_packages

setup(
    name="fraud-sample-organizer",
    version="1.0.0",
    description="信用卡欺诈样本整理器 - 银行反欺诈分析工具",
    author="Fraud Analytics Team",
    packages=find_packages(),
    install_requires=[
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "pyyaml>=6.0",
        "openpyxl>=3.1.0",
        "tqdm>=4.65.0",
        "chardet>=5.0.0",
    ],
    entry_points={
        "console_scripts": [
            "fraud-org=fraud_organizer.cli:main",
        ],
    },
    python_requires=">=3.9",
)
