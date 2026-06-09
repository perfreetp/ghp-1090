# 批处理任务清单: QG_scenario3_empty_train_block

- **开始时间**: 2026-06-10 00:06:28
- **结束时间**: 2026-06-10 00:06:29
- **总耗时**: 1.07 秒
- **配置文件**: `D:\TraeProjects\1090\batch_config.qg3_empty_train.yaml`

## 步骤执行摘要

| 步骤 | 状态 | 耗时(秒) | 输入数 | 输出数 | 说明 |
|------|------|----------|--------|--------|------|
| import | ✓ success | 0.04 | 3 | 3 | 返回码=0 |
| clean | ✓ success | 0.04 | 1 | 2 | 返回码=0 |
| label | ✓ success | 0.03 | 2 | 2 | 返回码=0 |
| profile | ✓ success | 0.47 | 1 | 8 | 返回码=0 |
| split | ✓ success | 0.03 | 1 | 7 | 返回码=0, 方式=date |
| mask | ✓ success | 0.04 | 3 | 4 | 处理 3 个拆分文件 |
| report | ✓ success | 0.33 | 4 | 3 | 返回码=0 |
| export | ✓ success | 0.10 | 4 | 10 | 返回码=0, 格式=['csv', 'xlsx'] |

## import

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| txn_train_empty.csv | `test_data/qg_testdata/txn_train_empty.csv` | 5 |
| chargebacks.csv | `test_data/qg_testdata/chargebacks.csv` | 57 |
| blacklists.csv | `test_data/qg_testdata/blacklists.csv` | 65 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `output_qg\03_empty_train_block\imported\transactions_raw.pkl` | 5 |
| chargebacks_raw.pkl | `output_qg\03_empty_train_block\imported\chargebacks_raw.pkl` | 57 |
| blacklists_raw.pkl | `output_qg\03_empty_train_block\imported\blacklists_raw.pkl` | 65 |

> 返回码=0

## clean

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `output_qg\03_empty_train_block\imported\transactions_raw.pkl` | 5 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `output_qg\03_empty_train_block\cleaned\transactions_clean.pkl` | 5 |
| clean_report.txt | `output_qg\03_empty_train_block\cleaned\clean_report.txt` | - |

> 返回码=0

## label

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `output_qg\03_empty_train_block\cleaned\transactions_clean.pkl` | 5 |
| chargebacks_raw.pkl | `output_qg\03_empty_train_block\imported\chargebacks_raw.pkl` | 57 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\03_empty_train_block\labeled\transactions_labeled.pkl` | 5 |
| label_report.txt | `output_qg\03_empty_train_block\labeled\label_report.txt` | - |

> 返回码=0

## profile

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\03_empty_train_block\labeled\transactions_labeled.pkl` | 5 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| overview.csv | `output_qg\03_empty_train_block\profiled\overview.csv` | 6 |
| profile_report.xlsx | `output_qg\03_empty_train_block\profiled\profile_report.xlsx` | 6 |
| stats_card_no.csv | `output_qg\03_empty_train_block\profiled\stats_card_no.csv` | 5 |
| stats_city.csv | `output_qg\03_empty_train_block\profiled\stats_city.csv` | 4 |
| stats_device_id.csv | `output_qg\03_empty_train_block\profiled\stats_device_id.csv` | 5 |
| stats_mcc.csv | `output_qg\03_empty_train_block\profiled\stats_mcc.csv` | 4 |
| stats_merchant_id.csv | `output_qg\03_empty_train_block\profiled\stats_merchant_id.csv` | 5 |
| stats_province.csv | `output_qg\03_empty_train_block\profiled\stats_province.csv` | 3 |

> 返回码=0

## split

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\03_empty_train_block\labeled\transactions_labeled.pkl` | 5 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.csv | `output_qg\03_empty_train_block\splits\backtest.csv` | 5 |
| backtest.pkl | `output_qg\03_empty_train_block\splits\backtest.pkl` | 5 |
| split_report.txt | `output_qg\03_empty_train_block\splits\split_report.txt` | - |
| train.csv | `output_qg\03_empty_train_block\splits\train.csv` | 0 |
| train.pkl | `output_qg\03_empty_train_block\splits\train.pkl` | 0 |
| valid.csv | `output_qg\03_empty_train_block\splits\valid.csv` | 0 |
| valid.pkl | `output_qg\03_empty_train_block\splits\valid.pkl` | 0 |

> 返回码=0, 方式=date

## mask

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.pkl | `output_qg\03_empty_train_block\splits\backtest.pkl` | 5 |
| train.pkl | `output_qg\03_empty_train_block\splits\train.pkl` | 0 |
| valid.pkl | `output_qg\03_empty_train_block\splits\valid.pkl` | 0 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `output_qg\03_empty_train_block\masked\backtest__backtest.pkl` | 5 |
| mask_summary.csv | `output_qg\03_empty_train_block\masked\mask_summary.csv` | 1 |
| train__train.pkl | `output_qg\03_empty_train_block\masked\train__train.pkl` | 0 |
| valid__valid.pkl | `output_qg\03_empty_train_block\masked\valid__valid.pkl` | 0 |

> 处理 3 个拆分文件

## report

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `output_qg\03_empty_train_block\labeled\transactions_labeled.pkl` | 5 |
| backtest.pkl | `output_qg\03_empty_train_block\splits\backtest.pkl` | 5 |
| train.pkl | `output_qg\03_empty_train_block\splits\train.pkl` | 0 |
| valid.pkl | `output_qg\03_empty_train_block\splits\valid.pkl` | 0 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| fraud_report.txt | `output_qg\03_empty_train_block\reports\fraud_report.txt` | - |
| fraud_report.xlsx | `output_qg\03_empty_train_block\reports\fraud_report.xlsx` | 7 |
| fraud_report_business.md | `output_qg\03_empty_train_block\reports\fraud_report_business.md` | - |

> 返回码=0

## export

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `output_qg\03_empty_train_block\masked\backtest__backtest.pkl` | 5 |
| mask_summary.csv | `output_qg\03_empty_train_block\masked\mask_summary.csv` | 1 |
| train__train.pkl | `output_qg\03_empty_train_block\masked\train__train.pkl` | 0 |
| valid__valid.pkl | `output_qg\03_empty_train_block\masked\valid__valid.pkl` | 0 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.csv | `output_qg\03_empty_train_block\exported\backtest__backtest.csv` | 5 |
| backtest__backtest.xlsx | `output_qg\03_empty_train_block\exported\backtest__backtest.xlsx` | 5 |
| EMPTY_EXPORT_NOTE.txt | `output_qg\03_empty_train_block\exported\EMPTY_EXPORT_NOTE.txt` | - |
| export_manifest.txt | `output_qg\03_empty_train_block\exported\export_manifest.txt` | - |
| mask_summary.csv | `output_qg\03_empty_train_block\exported\mask_summary.csv` | 1 |
| mask_summary.xlsx | `output_qg\03_empty_train_block\exported\mask_summary.xlsx` | 1 |
| train__train.csv | `output_qg\03_empty_train_block\exported\train__train.csv` | 0 |
| train__train.xlsx | `output_qg\03_empty_train_block\exported\train__train.xlsx` | 0 |
| valid__valid.csv | `output_qg\03_empty_train_block\exported\valid__valid.csv` | 0 |
| valid__valid.xlsx | `output_qg\03_empty_train_block\exported\valid__valid.xlsx` | 0 |

> 返回码=0, 格式=['csv', 'xlsx']

## 汇总

- **任务名**: QG_scenario3_empty_train_block
- **整体状态**: blocked
- **成功步骤**: 8
- **跳过步骤**: 0
- **失败步骤**: 0
- **总步骤**: 8
- **总耗时(秒)**: 1.07
- **QG通过**: 3
- **QG警告**: 2
- **QG阻断**: 1

## Quality Gates（质量门禁）

| 规则 | 结果 | 严重级别 | 详情 |
|------|------|----------|------|
| G1_必填字段缺失 | ✅ PASS | none | 所有必填字段齐全 |
| G1b_高比例空值列 | 🟠 WARN | major | 高比例空值列(>30%)共 4 列: txn_train_empty.csv.installment(60.0%) ; txn_train_empty.csv.cashback(60.0%) ; txn_train_empty.csv.rule_hit(100.0%) ; txn_train_empty.csv.manual_result(100.0%) |
| G2_主集(labeled)样本为空 | ✅ PASS | none | 主集样本数 = 5 |
| G2b_训练集(train)为空 | 🔴 BLOCK | major | train.pkl 行数为 0，模型训练将失败 |
| G3_欺诈率环比异常波动 | ✅ PASS | none | 当前=0.0000%, 上次=1.6000%, 环比=100.0% |
| G4_欺诈率范围合理性 | 🟠 WARN | minor | 欺诈率=0.0000% 低于经验下限 0.05%，可能样本或标签异常 |

> 完整清单: quality_gates_report.csv
