# 历史重放评分实验

- Generated at: 2026-03-24T01:07:08
- Codes: AAPL,NVDA,AMZN,TSLA
- Date range: 2026-03-19 -> 2026-03-23
- Replay samples: 11
- Sentiment score mode: adanos
- Forecast score mode: static 50.0

## 分数分桶

| Bucket | Count | T+1 Avg% | T+3 Avg% | T+5 Avg% | T+5 Win Rate |
|---|---:|---:|---:|---:|---:|
| 40-60 | 11 | -0.4434 | None | None | None |

## 操作建议分组

| Advice | Count | T+1 Avg% | T+3 Avg% | T+5 Avg% | T+5 Win Rate |
|---|---:|---:|---:|---:|---:|
| watch/hold | 11 | -0.4434 | None | None | None |

## 说明

- 这版实验优先复用本地 `stock_daily` 和 `fundamental_snapshot`。
- forecast 分当前使用中性占位，不参与方向性放大。
- 目标先验证结构化评分在小样本下是否具备排序能力。
