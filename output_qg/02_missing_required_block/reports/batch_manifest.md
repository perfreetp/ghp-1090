# 批处理任务清单: QG_scenario2_missing_required_block

- **开始时间**: 2026-06-10 00:05:48
- **结束时间**: 2026-06-10 00:05:53
- **总耗时**: 5.01 秒
- **配置文件**: `D:\TraeProjects\1090\batch_config.qg2_missing.yaml`

## 步骤执行摘要

| 步骤 | 状态 | 耗时(秒) | 输入数 | 输出数 | 说明 |
|------|------|----------|--------|--------|------|
| import | ✓ success | 0.08 | 3 | 3 | 返回码=0 |
| clean | ✓ success | 0.10 | 1 | 2 | 返回码=0 |
| label | ✓ success | 0.07 | 2 | 2 | 返回码=0 |
| profile | ✓ success | 0.74 | 1 | 9 | 返回码=0 |
| split | ✓ success | 0.10 | 1 | 7 | 返回码=0, 方式=ratio |
| mask | ✓ success | 0.11 | 3 | 4 | 处理 3 个拆分文件 |
| report | ✗ failed | 0.19 | 4 | 4 | 返回码=1 |
| export | ✓ success | 3.62 | 4 | 9 | 返回码=0, 格式=['csv', 'xlsx'] |

## import

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| txn_missing_required.csv | `test_data/qg_testdata/txn_missing_required.csv` | 3030 |
| chargebacks.csv | `test_data/qg_testdata/chargebacks.csv` | 57 |
| blacklists.csv | `test_data/qg_testdata/blacklists.csv` | 65 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `output_qg\02_missing_required_block\imported\transactions_raw.pkl` | 3030 |
| chargebacks_raw.pkl | `output_qg\02_missing_required_block\imported\chargebacks_raw.pkl` | 57 |
| blacklists_raw.pkl | `output_qg\02_missing_required_block\imported\blacklists_raw.pkl` | 65 |

> 返回码=0

## clean

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `output_qg\02_missing_required_block\imported\transactions_raw.pkl` | 3030 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `output_qg\02_missing_required_block\cleaned\transactions_clean.pkl` | 3000 |
| clean_report.txt | `output_qg\02_missing_required_block\cleaned\clean_report.txt` | - |

> 返回码=0

## label

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `output_qg\02_missing_required_block\cleaned\transactions_clean.pkl` | 3000 |
| chargebacks_raw.pkl | `output_qg\02_missing_required_block\imported\chargebacks_raw.pkl` | 57 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\02_missing_required_block\labeled\transactions_labeled.pkl` | 3000 |
| label_report.txt | `output_qg\02_missing_required_block\labeled\label_report.txt` | - |

> 返回码=0

## profile

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\02_missing_required_block\labeled\transactions_labeled.pkl` | 3000 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| anomalies.csv | `output_qg\02_missing_required_block\profiled\anomalies.csv` | 681 |
| overview.csv | `output_qg\02_missing_required_block\profiled\overview.csv` | 6 |
| profile_report.xlsx | `output_qg\02_missing_required_block\profiled\profile_report.xlsx` | 6 |
| stats_card_no.csv | `output_qg\02_missing_required_block\profiled\stats_card_no.csv` | 300 |
| stats_city.csv | `output_qg\02_missing_required_block\profiled\stats_city.csv` | 10 |
| stats_device_id.csv | `output_qg\02_missing_required_block\profiled\stats_device_id.csv` | 374 |
| stats_mcc.csv | `output_qg\02_missing_required_block\profiled\stats_mcc.csv` | 10 |
| stats_merchant_id.csv | `output_qg\02_missing_required_block\profiled\stats_merchant_id.csv` | 60 |
| stats_province.csv | `output_qg\02_missing_required_block\profiled\stats_province.csv` | 10 |

> 返回码=0

## split

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\02_missing_required_block\labeled\transactions_labeled.pkl` | 3000 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.csv | `output_qg\02_missing_required_block\splits\backtest.csv` | 304 |
| backtest.pkl | `output_qg\02_missing_required_block\splits\backtest.pkl` | 304 |
| split_report.txt | `output_qg\02_missing_required_block\splits\split_report.txt` | - |
| train.csv | `output_qg\02_missing_required_block\splits\train.csv` | 2098 |
| train.pkl | `output_qg\02_missing_required_block\splits\train.pkl` | 2098 |
| valid.csv | `output_qg\02_missing_required_block\splits\valid.csv` | 598 |
| valid.pkl | `output_qg\02_missing_required_block\splits\valid.pkl` | 598 |

> 返回码=0, 方式=ratio

## mask

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.pkl | `output_qg\02_missing_required_block\splits\backtest.pkl` | 304 |
| train.pkl | `output_qg\02_missing_required_block\splits\train.pkl` | 2098 |
| valid.pkl | `output_qg\02_missing_required_block\splits\valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `output_qg\02_missing_required_block\masked\backtest__backtest.pkl` | 304 |
| mask_summary.csv | `output_qg\02_missing_required_block\masked\mask_summary.csv` | 1 |
| train__train.pkl | `output_qg\02_missing_required_block\masked\train__train.pkl` | 2098 |
| valid__valid.pkl | `output_qg\02_missing_required_block\masked\valid__valid.pkl` | 598 |

> 处理 3 个拆分文件

## report

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\02_missing_required_block\labeled\transactions_labeled.pkl` | 3000 |
| backtest.pkl | `output_qg\02_missing_required_block\splits\backtest.pkl` | 304 |
| train.pkl | `output_qg\02_missing_required_block\splits\train.pkl` | 2098 |
| valid.pkl | `output_qg\02_missing_required_block\splits\valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| batch_manifest.csv | `output_qg\02_missing_required_block\reports\batch_manifest.csv` | 8 |
| batch_manifest.md | `output_qg\02_missing_required_block\reports\batch_manifest.md` | - |
| fraud_report.xlsx | `output_qg\02_missing_required_block\reports\fraud_report.xlsx` | 7 |
| quality_gates_report.csv | `output_qg\02_missing_required_block\reports\quality_gates_report.csv` | 6 |

> 返回码=1

## export

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `output_qg\02_missing_required_block\masked\backtest__backtest.pkl` | 304 |
| mask_summary.csv | `output_qg\02_missing_required_block\masked\mask_summary.csv` | 1 |
| train__train.pkl | `output_qg\02_missing_required_block\masked\train__train.pkl` | 2098 |
| valid__valid.pkl | `output_qg\02_missing_required_block\masked\valid__valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.csv | `output_qg\02_missing_required_block\exported\backtest__backtest.csv` | 304 |
| backtest__backtest.xlsx | `output_qg\02_missing_required_block\exported\backtest__backtest.xlsx` | 304 |
| export_manifest.txt | `output_qg\02_missing_required_block\exported\export_manifest.txt` | - |
| mask_summary.csv | `output_qg\02_missing_required_block\exported\mask_summary.csv` | 1 |
| mask_summary.xlsx | `output_qg\02_missing_required_block\exported\mask_summary.xlsx` | 1 |
| train__train.csv | `output_qg\02_missing_required_block\exported\train__train.csv` | 2098 |
| train__train.xlsx | `output_qg\02_missing_required_block\exported\train__train.xlsx` | 2098 |
| valid__valid.csv | `output_qg\02_missing_required_block\exported\valid__valid.csv` | 598 |
| valid__valid.xlsx | `output_qg\02_missing_required_block\exported\valid__valid.xlsx` | 598 |

> 返回码=0, 格式=['csv', 'xlsx']

## 汇总

- **任务名**: QG_scenario2_missing_required_block
- **整体状态**: blocked
- **成功步骤**: 7
- **跳过步骤**: 0
- **失败步骤**: 1
- **总步骤**: 8
- **总耗时(秒)**: 5.01
- **QG通过**: 4
- **QG警告**: 1
- **QG阻断**: 1

## Quality Gates（质量门禁）

| 规则 | 结果 | 严重级别 | 详情 |
|------|------|----------|------|
| G1_必填字段缺失 | 🔴 BLOCK | critical | 缺失字段数: 1。txn_missing_required.csv.txn_time |
| G1b_高比例空值列 | 🟠 WARN | major | 高比例空值列(>30%)共 4 列: txn_missing_required.csv.installment(71.09%) ; txn_missing_required.csv.cashback(69.47%) ; txn_missing_required.csv.rule_hit(96.57%) ; txn_missing_required.csv.manual_result(96.96%) |
| G2_主集(labeled)样本为空 | ✅ PASS | none | 主集样本数 = 3000 |
| G2b_训练集(train)为空 | ✅ PASS | none | train 样本数 = 2098 |
| G3_欺诈率环比异常波动 | ✅ PASS | none | 当前=1.6000%, 上次=1.6000%, 环比=0.0% |
| G4_欺诈率范围合理性 | ✅ PASS | none | 欺诈率=1.6000%，在合理区间 [0.05%, 15.00%] |

> 完整清单: quality_gates_report.csv
