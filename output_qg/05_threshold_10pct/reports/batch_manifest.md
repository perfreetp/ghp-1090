# 批处理任务清单: QG_scenario5_threshold_10pct_consistency

- **开始时间**: 2026-06-10 00:16:44
- **结束时间**: 2026-06-10 00:16:50
- **总耗时**: 6.34 秒
- **配置文件**: `D:\TraeProjects\1090\batch_config.qg5_threshold.yaml`

## 步骤执行摘要

| 步骤 | 状态 | 耗时(秒) | 输入数 | 输出数 | 说明 |
|------|------|----------|--------|--------|------|
| import | ✓ success | 0.08 | 3 | 3 | 返回码=0 |
| clean | ✓ success | 0.12 | 1 | 2 | 返回码=0 |
| label | ✓ success | 0.07 | 2 | 2 | 返回码=0 |
| profile | ✓ success | 1.55 | 1 | 9 | 返回码=0 |
| split | ✓ success | 0.10 | 1 | 7 | 返回码=0, 方式=ratio |
| mask | ✓ success | 0.10 | 3 | 4 | 处理 3 个拆分文件 |
| report | ✓ success | 0.51 | 4 | 3 | 返回码=0 |
| export | ✓ success | 3.81 | 4 | 9 | 返回码=0, 格式=['csv', 'xlsx'] |

## import

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| txn_normal.csv | `test_data/qg_testdata/txn_normal.csv` | 3030 |
| chargebacks.csv | `test_data/qg_testdata/chargebacks.csv` | 57 |
| blacklists.csv | `test_data/qg_testdata/blacklists.csv` | 65 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `output_qg\05_threshold_10pct\imported\transactions_raw.pkl` | 3030 |
| chargebacks_raw.pkl | `output_qg\05_threshold_10pct\imported\chargebacks_raw.pkl` | 57 |
| blacklists_raw.pkl | `output_qg\05_threshold_10pct\imported\blacklists_raw.pkl` | 65 |

> 返回码=0

## clean

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `output_qg\05_threshold_10pct\imported\transactions_raw.pkl` | 3030 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `output_qg\05_threshold_10pct\cleaned\transactions_clean.pkl` | 3000 |
| clean_report.txt | `output_qg\05_threshold_10pct\cleaned\clean_report.txt` | - |

> 返回码=0

## label

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `output_qg\05_threshold_10pct\cleaned\transactions_clean.pkl` | 3000 |
| chargebacks_raw.pkl | `output_qg\05_threshold_10pct\imported\chargebacks_raw.pkl` | 57 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\05_threshold_10pct\labeled\transactions_labeled.pkl` | 3000 |
| label_report.txt | `output_qg\05_threshold_10pct\labeled\label_report.txt` | - |

> 返回码=0

## profile

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\05_threshold_10pct\labeled\transactions_labeled.pkl` | 3000 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| anomalies.csv | `output_qg\05_threshold_10pct\profiled\anomalies.csv` | 681 |
| overview.csv | `output_qg\05_threshold_10pct\profiled\overview.csv` | 6 |
| profile_report.xlsx | `output_qg\05_threshold_10pct\profiled\profile_report.xlsx` | 6 |
| stats_card_no.csv | `output_qg\05_threshold_10pct\profiled\stats_card_no.csv` | 300 |
| stats_city.csv | `output_qg\05_threshold_10pct\profiled\stats_city.csv` | 10 |
| stats_device_id.csv | `output_qg\05_threshold_10pct\profiled\stats_device_id.csv` | 374 |
| stats_mcc.csv | `output_qg\05_threshold_10pct\profiled\stats_mcc.csv` | 10 |
| stats_merchant_id.csv | `output_qg\05_threshold_10pct\profiled\stats_merchant_id.csv` | 60 |
| stats_province.csv | `output_qg\05_threshold_10pct\profiled\stats_province.csv` | 10 |

> 返回码=0

## split

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\05_threshold_10pct\labeled\transactions_labeled.pkl` | 3000 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.csv | `output_qg\05_threshold_10pct\splits\backtest.csv` | 304 |
| backtest.pkl | `output_qg\05_threshold_10pct\splits\backtest.pkl` | 304 |
| split_report.txt | `output_qg\05_threshold_10pct\splits\split_report.txt` | - |
| train.csv | `output_qg\05_threshold_10pct\splits\train.csv` | 2098 |
| train.pkl | `output_qg\05_threshold_10pct\splits\train.pkl` | 2098 |
| valid.csv | `output_qg\05_threshold_10pct\splits\valid.csv` | 598 |
| valid.pkl | `output_qg\05_threshold_10pct\splits\valid.pkl` | 598 |

> 返回码=0, 方式=ratio

## mask

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.pkl | `output_qg\05_threshold_10pct\splits\backtest.pkl` | 304 |
| train.pkl | `output_qg\05_threshold_10pct\splits\train.pkl` | 2098 |
| valid.pkl | `output_qg\05_threshold_10pct\splits\valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `output_qg\05_threshold_10pct\masked\backtest__backtest.pkl` | 304 |
| mask_summary.csv | `output_qg\05_threshold_10pct\masked\mask_summary.csv` | 1 |
| train__train.pkl | `output_qg\05_threshold_10pct\masked\train__train.pkl` | 2098 |
| valid__valid.pkl | `output_qg\05_threshold_10pct\masked\valid__valid.pkl` | 598 |

> 处理 3 个拆分文件

## report

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\05_threshold_10pct\labeled\transactions_labeled.pkl` | 3000 |
| backtest.pkl | `output_qg\05_threshold_10pct\splits\backtest.pkl` | 304 |
| train.pkl | `output_qg\05_threshold_10pct\splits\train.pkl` | 2098 |
| valid.pkl | `output_qg\05_threshold_10pct\splits\valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| fraud_report.txt | `output_qg\05_threshold_10pct\reports\fraud_report.txt` | - |
| fraud_report.xlsx | `output_qg\05_threshold_10pct\reports\fraud_report.xlsx` | 7 |
| fraud_report_business.md | `output_qg\05_threshold_10pct\reports\fraud_report_business.md` | - |

> 返回码=0

## export

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `output_qg\05_threshold_10pct\masked\backtest__backtest.pkl` | 304 |
| mask_summary.csv | `output_qg\05_threshold_10pct\masked\mask_summary.csv` | 1 |
| train__train.pkl | `output_qg\05_threshold_10pct\masked\train__train.pkl` | 2098 |
| valid__valid.pkl | `output_qg\05_threshold_10pct\masked\valid__valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.csv | `output_qg\05_threshold_10pct\exported\backtest__backtest.csv` | 304 |
| backtest__backtest.xlsx | `output_qg\05_threshold_10pct\exported\backtest__backtest.xlsx` | 304 |
| export_manifest.txt | `output_qg\05_threshold_10pct\exported\export_manifest.txt` | - |
| mask_summary.csv | `output_qg\05_threshold_10pct\exported\mask_summary.csv` | 1 |
| mask_summary.xlsx | `output_qg\05_threshold_10pct\exported\mask_summary.xlsx` | 1 |
| train__train.csv | `output_qg\05_threshold_10pct\exported\train__train.csv` | 2098 |
| train__train.xlsx | `output_qg\05_threshold_10pct\exported\train__train.xlsx` | 2098 |
| valid__valid.csv | `output_qg\05_threshold_10pct\exported\valid__valid.csv` | 598 |
| valid__valid.xlsx | `output_qg\05_threshold_10pct\exported\valid__valid.xlsx` | 598 |

> 返回码=0, 格式=['csv', 'xlsx']

## 汇总

- **任务名**: QG_scenario5_threshold_10pct_consistency
- **整体状态**: success
- **成功步骤**: 8
- **跳过步骤**: 0
- **失败步骤**: 0
- **总步骤**: 8
- **总耗时(秒)**: 6.34
- **QG通过**: 5
- **QG警告**: 1
- **QG阻断**: 0

## Quality Gates（质量门禁）

| 规则 | 结果 | 严重级别 | 详情 |
|------|------|----------|------|
| G1_必填字段缺失 | ✅ PASS | none | 所有必填字段齐全 |
| G1b_高比例空值列 | 🟠 WARN | major | 高比例空值列(>10%)共 4 列: txn_normal.csv.installment(71.09%) ; txn_normal.csv.cashback(69.47%) ; txn_normal.csv.rule_hit(96.57%) ; txn_normal.csv.manual_result(96.96%) |
| G2_主集(labeled)样本为空 | ✅ PASS | none | 主集样本数 = 3000 |
| G2b_训练集(train)为空 | ✅ PASS | none | train 样本数 = 2098 |
| G3_欺诈率环比异常波动 | ✅ PASS | none | 当前=1.6000%, 上次=1.6000%, 环比=0.0% |
| G4_欺诈率范围合理性 | ✅ PASS | none | 欺诈率=1.6000%，在合理区间 [0.05%, 15.00%] |

> 完整清单: quality_gates_report.csv
