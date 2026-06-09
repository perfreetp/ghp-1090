# 批处理任务清单: 端到端验证测试批

- **开始时间**: 2026-06-09 23:28:45
- **结束时间**: 2026-06-09 23:28:52
- **总耗时**: 7.39 秒
- **配置文件**: `D:\TraeProjects\1090\batch_config.test.yaml`

## 步骤执行摘要

| 步骤 | 状态 | 耗时(秒) | 输入数 | 输出数 | 说明 |
|------|------|----------|--------|--------|------|
| import | ✓ success | 0.09 | 3 | 3 | 返回码=0 |
| clean | ✓ success | 0.12 | 1 | 2 | 返回码=0 |
| label | ✓ success | 0.07 | 2 | 2 | 返回码=0 |
| profile | ✓ success | 1.48 | 1 | 9 | 返回码=0 |
| split | ✓ success | 0.10 | 1 | 7 | 返回码=0, 方式=ratio |
| mask | ✓ success | 0.13 | 3 | 4 | 处理 3 个拆分文件 |
| report | ✓ success | 1.56 | 4 | 3 | 返回码=0 |
| export | ✓ success | 3.85 | 4 | 9 | 返回码=0, 格式=['csv', 'xlsx'] |

## import

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions.csv | `./test_data/transactions.csv` | 3030 |
| chargebacks.csv | `./test_data/chargebacks.csv` | 57 |
| blacklists.csv | `./test_data/blacklists.csv` | 65 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `data\batch_output\imported\transactions_raw.pkl` | 3030 |
| chargebacks_raw.pkl | `data\batch_output\imported\chargebacks_raw.pkl` | 57 |
| blacklists_raw.pkl | `data\batch_output\imported\blacklists_raw.pkl` | 65 |

> 返回码=0

## clean

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_raw.pkl | `data\batch_output\imported\transactions_raw.pkl` | 3030 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `data\batch_output\cleaned\transactions_clean.pkl` | 3000 |
| clean_report.txt | `data\batch_output\cleaned\clean_report.txt` | - |

> 返回码=0

## label

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_clean.pkl | `data\batch_output\cleaned\transactions_clean.pkl` | 3000 |
| chargebacks_raw.pkl | `data\batch_output\imported\chargebacks_raw.pkl` | 57 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `data\batch_output\labeled\transactions_labeled.pkl` | 3000 |
| label_report.txt | `data\batch_output\labeled\label_report.txt` | - |

> 返回码=0

## profile

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `data\batch_output\labeled\transactions_labeled.pkl` | 3000 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| anomalies.csv | `data\batch_output\profiled\anomalies.csv` | 681 |
| overview.csv | `data\batch_output\profiled\overview.csv` | 6 |
| profile_report.xlsx | `data\batch_output\profiled\profile_report.xlsx` | 6 |
| stats_card_no.csv | `data\batch_output\profiled\stats_card_no.csv` | 300 |
| stats_city.csv | `data\batch_output\profiled\stats_city.csv` | 10 |
| stats_device_id.csv | `data\batch_output\profiled\stats_device_id.csv` | 374 |
| stats_mcc.csv | `data\batch_output\profiled\stats_mcc.csv` | 10 |
| stats_merchant_id.csv | `data\batch_output\profiled\stats_merchant_id.csv` | 60 |
| stats_province.csv | `data\batch_output\profiled\stats_province.csv` | 10 |

> 返回码=0

## split

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `data\batch_output\labeled\transactions_labeled.pkl` | 3000 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.csv | `data\batch_output\splits\backtest.csv` | 453 |
| backtest.pkl | `data\batch_output\splits\backtest.pkl` | 453 |
| split_report.txt | `data\batch_output\splits\split_report.txt` | - |
| train.csv | `data\batch_output\splits\train.csv` | 2098 |
| train.pkl | `data\batch_output\splits\train.pkl` | 2098 |
| valid.csv | `data\batch_output\splits\valid.csv` | 449 |
| valid.pkl | `data\batch_output\splits\valid.pkl` | 449 |

> 返回码=0, 方式=ratio

## mask

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest.pkl | `data\batch_output\splits\backtest.pkl` | 453 |
| train.pkl | `data\batch_output\splits\train.pkl` | 2098 |
| valid.pkl | `data\batch_output\splits\valid.pkl` | 449 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `data\batch_output\masked\backtest__backtest.pkl` | 453 |
| mask_summary.csv | `data\batch_output\masked\mask_summary.csv` | 1 |
| train__train.pkl | `data\batch_output\masked\train__train.pkl` | 2098 |
| valid__valid.pkl | `data\batch_output\masked\valid__valid.pkl` | 449 |

> 处理 3 个拆分文件

## report

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions_labeled.pkl | `data\batch_output\labeled\transactions_labeled.pkl` | 3000 |
| backtest.pkl | `data\batch_output\splits\backtest.pkl` | 453 |
| train.pkl | `data\batch_output\splits\train.pkl` | 2098 |
| valid.pkl | `data\batch_output\splits\valid.pkl` | 449 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| fraud_report.txt | `data\batch_output\reports\fraud_report.txt` | - |
| fraud_report.xlsx | `data\batch_output\reports\fraud_report.xlsx` | 4 |
| fraud_report_business.md | `data\batch_output\reports\fraud_report_business.md` | - |

> 返回码=0

## export

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.pkl | `data\batch_output\masked\backtest__backtest.pkl` | 453 |
| mask_summary.csv | `data\batch_output\masked\mask_summary.csv` | 1 |
| train__train.pkl | `data\batch_output\masked\train__train.pkl` | 2098 |
| valid__valid.pkl | `data\batch_output\masked\valid__valid.pkl` | 449 |

### 输出

| 名称 | 路径 | 行数 |
|------|------|------|
| backtest__backtest.csv | `data\batch_output\exported\backtest__backtest.csv` | 453 |
| backtest__backtest.xlsx | `data\batch_output\exported\backtest__backtest.xlsx` | 453 |
| export_manifest.txt | `data\batch_output\exported\export_manifest.txt` | - |
| mask_summary.csv | `data\batch_output\exported\mask_summary.csv` | 1 |
| mask_summary.xlsx | `data\batch_output\exported\mask_summary.xlsx` | 1 |
| train__train.csv | `data\batch_output\exported\train__train.csv` | 2098 |
| train__train.xlsx | `data\batch_output\exported\train__train.xlsx` | 2098 |
| valid__valid.csv | `data\batch_output\exported\valid__valid.csv` | 449 |
| valid__valid.xlsx | `data\batch_output\exported\valid__valid.xlsx` | 449 |

> 返回码=0, 格式=['csv', 'xlsx']

## 汇总

- **任务名**: 端到端验证测试批
- **成功步骤**: 8
- **跳过步骤**: 0
- **失败步骤**: 0
- **总步骤**: 8
- **总耗时(秒)**: 7.39
