# 导入字段检查报告

- **生成时间**: 2026-06-09 23:29:20.967898
- **检查文件数**: 3 个
- **总行数**: 122

## 交易文件 - empty_transactions.csv

- **路径**: `test_data/empty_transactions.csv`
- **总行数**: 0
- **字段校验状态**: [通过]

### ℹ 缺失选填字段（不影响流程，但建议补充）

缺失字段: `id_card`, `ip`, `country`, `installment`, `cashback`, `manual_review`, `auth_code`, `issuer_bank`, `terminal_id`

## 拒付文件 - chargebacks.csv

- **路径**: `test_data/chargebacks.csv`
- **总行数**: 57
- **字段校验状态**: [通过]

## 黑名单文件 - blacklists.csv

- **路径**: `test_data/blacklists.csv`
- **总行数**: 65
- **字段校验状态**: [通过]
