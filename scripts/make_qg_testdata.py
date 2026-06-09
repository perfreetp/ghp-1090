"""生成 Quality Gates 三种场景测试数据"""
import pandas as pd
from pathlib import Path

OUT = Path("test_data/qg_testdata")
OUT.mkdir(parents=True, exist_ok=True)

# ---------- 场景 1 & 2: 正常规模样本（用于 G3 欺诈率波动对比）----------
# 复用已有 transactions.csv，但另外造：
# (A) 缺必填字段版：删掉 txn_time, amt 两列
# (B) 极端欺诈率版（G4 验证用）：欺诈率 25%

np_seed = None
import numpy as np
np.random.seed(42)

# 读取原表做母本
orig = pd.read_csv("test_data/transactions.csv")

# ---- A. 缺必填字段（删 txn_time, amt） ----
missing_required = orig.drop(columns=["txn_time", "amt"], errors="ignore")
missing_required.to_csv(OUT / "txn_missing_required.csv", index=False, encoding="utf-8-sig")
print(f"[A] 缺必填字段  -> {len(missing_required)} 行, 列={list(missing_required.columns)}")

# ---- B. 正常数据集，但欺诈率飙高（G3/G4） ----
high_fraud = orig.copy()
high_fraud["txn_time"] = pd.date_range("2024-07-01", periods=len(high_fraud), freq="h").astype(str)
# 强制高欺诈标签（需要 label 阶段生成，但我们在 label 之前造了样本；为了简单，这里改 chargebacks 让更多交易命中）
high_fraud.to_csv(OUT / "txn_normal.csv", index=False, encoding="utf-8-sig")

# ---- C. 极端欺诈率 25%（直接在 txn_id 层面造假，label 阶段会用 chargeback 匹配，我们造 chargebacks.csv 让 25% 的 txn_id 都拒付）----
chargebacks_orig = pd.read_csv("test_data/chargebacks.csv")
# 取 750 个 txn_id 随机强行标欺诈
high_cb_ids = high_fraud["txn_id"].sample(n=750, random_state=42).tolist()
high_chargebacks = pd.DataFrame({
    "txn_id": high_cb_ids,
    "cb_time": pd.date_range("2024-07-15", periods=len(high_cb_ids), freq="min").astype(str),
    "cb_reason": "CNP欺诈",
    "cb_amount": 100.0,
})
high_chargebacks.to_csv(OUT / "chargebacks_high.csv", index=False, encoding="utf-8-sig")
print(f"[B] 高欺诈chargebacks -> {len(high_chargebacks)} 条")

# ---- D. 空训练集（只有 5 条交易，日期都在 train_end 之后）----
small_dates = pd.date_range("2024-12-29", periods=5, freq="h")
# 配置里 split 会指定 train_end=2024-11-30, valid_end=2024-12-15
# 所有交易日期 12/29 之后，所以 train(<=11/30)=0 行
small = orig.head(5).copy()
small["txn_id"] = [f"T{i:06d}" for i in range(99001, 99006)]
small["txn_time"] = small_dates.astype(str)
small.to_csv(OUT / "txn_train_empty.csv", index=False, encoding="utf-8-sig")
print(f"[C] 小样本(会导致train空)  -> {len(small)} 行, 日期范围: {small['txn_time'].min()} ~ {small['txn_time'].max()}")

# ---- E. 正常用 chargebacks/blacklists 拷贝 ----
import shutil
shutil.copy("test_data/chargebacks.csv", OUT / "chargebacks.csv")
shutil.copy("test_data/blacklists.csv", OUT / "blacklists.csv")
print("✔ 测试数据准备完成:", list(OUT.glob("*")))
