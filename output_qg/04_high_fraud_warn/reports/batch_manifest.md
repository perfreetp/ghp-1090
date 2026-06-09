# 批处理任务清单: QG_scenario4_high_fraud_warn

- **开始时间**: 2026-06-10 00:07:09
- **结束时间**: 2026-06-10 00:07:15
- **总耗时**: 6.36 秒
- **配置文件**: `D:\TraeProjects\1090\batch_config.qg4_high_fraud.yaml`

## 步骤执行摘要

| 步骤 | 状态 | 耗时(秒) | 输入数 | 输出数 | 说明 |
|------|------|----------|--------|--------|------|
| import | ✓ success | 0.09 | 3 | 3 | 返回码=0 |
| clean | ✓ success | 0.12 | 1 | 2 | 返回码=0 |
| label | ✓ success | 0.06 | 2 | 2 | 返回码=0 |
| profile | ✓ success | 1.56 | 1 | 9 | 返回码=0 |
| split | ✓ success | 0.10 | 1 | 7 | 返回码=0, 方式=ratio |
| mask | ✓ success | 0.11 | 3 | 4 | 处理 3 个拆分文件 |
| report | ✓ success | 0.52 | 4 | 3 | 返回码=0 |
| export | ✓ success | 3.80 | 4 | 9 | 返回码=0, 格式=['csv', 'xlsx'] |

## import

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| txn_normal.csv | `test_data/qg_testdata/txn_normal.csv` | 3030 |
| chargebacks_high.csv | `test_data/qg_testdata/chargebacks_high.csv` | 750 |
| blacklists.csv | `test_data/qg_testdata/blacklists.csv` | 65 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `output_qg\04_high_fraud_warn\imported\transactions_raw.pkl` | 3030 |
| chargebacks_raw.pkl | `output_qg\04_high_fraud_warn\imported\chargebacks_raw.pkl` | 750 |
| blacklists_raw.pkl | `output_qg\04_high_fraud_warn\imported\blacklists_raw.pkl` | 65 |

> 返回码=0

## clean

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `output_qg\04_high_fraud_warn\imported\transactions_raw.pkl` | 3030 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `output_qg\04_high_fraud_warn\cleaned\transactions_clean.pkl` | 3000 |
| clean_report.txt | `output_qg\04_high_fraud_warn\cleaned\clean_report.txt` | - |

> 返回码=0

## label

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `output_qg\04_high_fraud_warn\cleaned\transactions_clean.pkl` | 3000 |
| chargebacks_raw.pkl | `output_qg\04_high_fraud_warn\imported\chargebacks_raw.pkl` | 750 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\04_high_fraud_warn\labeled\transactions_labeled.pkl` | 3000 |
| label_report.txt | `output_qg\04_high_fraud_warn\labeled\label_report.txt` | - |

> 返回码=0

## profile

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\04_high_fraud_warn\labeled\transactions_labeled.pkl` | 3000 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| anomalies.csv | `output_qg\04_high_fraud_warn\profiled\anomalies.csv` | 679 |
| overview.csv | `output_qg\04_high_fraud_warn\profiled\overview.csv` | 6 |
| profile_report.xlsx | `output_qg\04_high_fraud_warn\profiled\profile_report.xlsx` | 6 |
| stats_card_no.csv | `output_qg\04_high_fraud_warn\profiled\stats_card_no.csv` | 300 |
| stats_city.csv | `output_qg\04_high_fraud_warn\profiled\stats_city.csv` | 10 |
| stats_device_id.csv | `output_qg\04_high_fraud_warn\profiled\stats_device_id.csv` | 374 |
| stats_mcc.csv | `output_qg\04_high_fraud_warn\profiled\stats_mcc.csv` | 10 |
| stats_merchant_id.csv | `output_qg\04_high_fraud_warn\profiled\stats_merchant_id.csv` | 60 |
| stats_province.csv | `output_qg\04_high_fraud_warn\profiled\stats_province.csv` | 10 |

> 返回码=0

## split

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\04_high_fraud_warn\labeled\transactions_labeled.pkl` | 3000 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.csv | `output_qg\04_high_fraud_warn\splits\backtest.csv` | 303 |
| backtest.pkl | `output_qg\04_high_fraud_warn\splits\backtest.pkl` | 303 |
| split_report.txt | `output_qg\04_high_fraud_warn\splits\split_report.txt` | - |
| train.csv | `output_qg\04_high_fraud_warn\splits\train.csv` | 2099 |
| train.pkl | `output_qg\04_high_fraud_warn\splits\train.pkl` | 2099 |
| valid.csv | `output_qg\04_high_fraud_warn\splits\valid.csv` | 598 |
| valid.pkl | `output_qg\04_high_fraud_warn\splits\valid.pkl` | 598 |

> 返回码=0, 方式=ratio

## mask

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.pkl | `output_qg\04_high_fraud_warn\splits\backtest.pkl` | 303 |
| train.pkl | `output_qg\04_high_fraud_warn\splits\train.pkl` | 2099 |
| valid.pkl | `output_qg\04_high_fraud_warn\splits\valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `output_qg\04_high_fraud_warn\masked\backtest__backtest.pkl` | 303 |
| mask_summary.csv | `output_qg\04_high_fraud_warn\masked\mask_summary.csv` | 1 |
| train__train.pkl | `output_qg\04_high_fraud_warn\masked\train__train.pkl` | 2099 |
| valid__valid.pkl | `output_qg\04_high_fraud_warn\masked\valid__valid.pkl` | 598 |

> 处理 3 个拆分文件

## report

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\04_high_fraud_warn\labeled\transactions_labeled.pkl` | 3000 |
| backtest.pkl | `output_qg\04_high_fraud_warn\splits\backtest.pkl` | 303 |
| train.pkl | `output_qg\04_high_fraud_warn\splits\train.pkl` | 2099 |
| valid.pkl | `output_qg\04_high_fraud_warn\splits\valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| fraud_report.txt | `output_qg\04_high_fraud_warn\reports\fraud_report.txt` | - |
| fraud_report.xlsx | `output_qg\04_high_fraud_warn\reports\fraud_report.xlsx` | 7 |
| fraud_report_business.md | `output_qg\04_high_fraud_warn\reports\fraud_report_business.md` | - |

> 返回码=0

## export

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `output_qg\04_high_fraud_warn\masked\backtest__backtest.pkl` | 303 |
| mask_summary.csv | `output_qg\04_high_fraud_warn\masked\mask_summary.csv` | 1 |
| train__train.pkl | `output_qg\04_high_fraud_warn\masked\train__train.pkl` | 2099 |
| valid__valid.pkl | `output_qg\04_high_fraud_warn\masked\valid__valid.pkl` | 598 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.csv | `output_qg\04_high_fraud_warn\exported\backtest__backtest.csv` | 303 |
| backtest__backtest.xlsx | `output_qg\04_high_fraud_warn\exported\backtest__backtest.xlsx` | 303 |
| export_manifest.txt | `output_qg\04_high_fraud_warn\exported\export_manifest.txt` | - |
| mask_summary.csv | `output_qg\04_high_fraud_warn\exported\mask_summary.csv` | 1 |
| mask_summary.xlsx | `output_qg\04_high_fraud_warn\exported\mask_summary.xlsx` | 1 |
| train__train.csv | `output_qg\04_high_fraud_warn\exported\train__train.csv` | 2099 |
| train__train.xlsx | `output_qg\04_high_fraud_warn\exported\train__train.xlsx` | 2099 |
| valid__valid.csv | `output_qg\04_high_fraud_warn\exported\valid__valid.csv` | 598 |
| valid__valid.xlsx | `output_qg\04_high_fraud_warn\exported\valid__valid.xlsx` | 598 |

> 返回码=0, 格式=['csv', 'xlsx']

## 汇总

- **任务名**: QG_scenario4_high_fraud_warn
- **整体状态**: success
- **成功步骤**: 8
- **跳过步骤**: 0
- **失败步骤**: 0
- **总步骤**: 8
- **总耗时(秒)**: 6.36
- **QG通过**: 4
- **QG警告**: 2
- **QG阻断**: 0

## Quality Gates（质量门禁）

| 规则 | 结果 | 严重级别 | 详情 |
|------|------|----------|------|
| G1_必填字段缺失 | 🟠 WARN | major | 缺失字段数: 4。chargebacks_high.csv.chargeback_time ; chargebacks_high.csv.chargeback_reason ; chargebacks_high.csv.chargeback_amount ; chargebacks_high.csv.chargeback_result |
| G1b_高比例空值列 | 🟠 WARN | major | 高比例空值列(>30%)共 4 列: txn_normal.csv.installment(71.09%) ; txn_normal.csv.cashback(69.47%) ; txn_normal.csv.rule_hit(96.57%) ; txn_normal.csv.manual_result(96.96%) |
| G2_主集(labeled)样本为空 | ✅ PASS | none | 主集样本数 = 3000 |
| G2b_训练集(train)为空 | ✅ PASS | none | train 样本数 = 2099 |
| G3_欺诈率环比异常波动 | ✅ PASS | none | 当前=1.3000%, 上次=1.6000%, 环比=18.8% |
| G4_欺诈率范围合理性 | ✅ PASS | none | 欺诈率=1.3000%，在合理区间 [0.05%, 15.00%] |

> 完整清单: quality_gates_report.csv
