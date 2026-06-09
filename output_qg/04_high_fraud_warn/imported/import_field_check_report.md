# 导入字段检查报告

- **生成时间**: 2026-06-10 00:07:09.546230
- **检查文件数**: 3 个
- **总行数**: 3,845

## 交易文件 - txn_normal.csv

- **路径**: `test_data/qg_testdata/txn_normal.csv`
- **总行数**: 3,030
- **字段校验状态**: [通过]

### [数据质量] 空值严重的列（≥20%）

| 列名 | 空值数 | 空值率 | 建议 |
|------|--------|--------|------|
| `manual_result` | 2,938 | 96.96% | **建议检查数据源，可能是关键字段未补全** |
| `rule_hit` | 2,926 | 96.57% | **建议检查数据源，可能是关键字段未补全** |
| `installment` | 2,154 | 71.09% | 可考虑填充默认值或单独作为特征 |
| `cashback` | 2,105 | 69.47% | 可考虑填充默认值或单独作为特征 |

## 拒付文件 - chargebacks_high.csv

- **路径**: `test_data/qg_testdata/chargebacks_high.csv`
- **总行数**: 750
- **字段校验状态**: [失败]

### [警告] 缺失必填字段

| 字段名 | 说明 |
|--------|------|
| `chargeback_time` |  |
| `chargeback_reason` |  |
| `chargeback_amount` |  |
| `chargeback_result` | 拒付结果，是欺诈标签的黄金来源 |

## 黑名单文件 - blacklists.csv

- **路径**: `test_data/qg_testdata/blacklists.csv`
- **总行数**: 65
- **字段校验状态**: [通过]
