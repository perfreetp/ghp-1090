# 批处理任务清单: 端到端验证测试批-2月(对比用)

- **开始时间**: 2026-06-09 23:45:32
- **结束时间**: 2026-06-09 23:45:32
- **总耗时**: 0.07 秒
- **配置文件**: `D:\TraeProjects\1090\batch_config.test.yaml`

## 步骤执行摘要

| 步骤 | 状态 | 耗时(秒) | 输入数 | 输出数 | 说明 |
|------|------|----------|--------|--------|------|
| import | ✗ failed | 0.07 | 3 | 0 | 异常: 'gbk' codec can't encode character '\u26a0' in position 2: illegal multibyte sequence |

## import

### 输入

| 名称 | 路径 | 行数 |
|------|------|------|
| transactions.csv | `./test_data/transactions.csv` | 3030 |
| chargebacks.csv | `./test_data/chargebacks.csv` | 57 |
| blacklists.csv | `./test_data/blacklists.csv` | 65 |

> 异常: 'gbk' codec can't encode character '\u26a0' in position 2: illegal multibyte sequence

## 汇总

- **任务名**: 端到端验证测试批-2月(对比用)
- **成功步骤**: 0
- **跳过步骤**: 0
- **失败步骤**: 1
- **总步骤**: 1
- **总耗时(秒)**: 0.07
- **QG通过**: 0
- **QG警告**: 0
- **QG阻断**: 0
