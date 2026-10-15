# 小样本回测实验

这个目录放的是独立实验，不影响主服务。

当前实验目标：

- 用 `backend_analysis/data/stock_analysis.db` 里的
  - `analysis_history`
  - `stock_daily`
- 做一个最小可运行的小样本分层回测
- 先验证一个问题：
  - 高分组未来收益是否整体好于低分组

## 当前实验方法

脚本会：

1. 读取历史分析记录
2. 用 `sentiment_score` 作为当前交易决策分
3. 找到分析日之后的交易日收盘价
4. 计算：
   - `T+1`
   - `T+3`
   - `T+5`
5. 按分数分桶：
   - `0-20`
   - `20-40`
   - `40-60`
   - `60-80`
   - `80-100`
6. 输出：
   - 每桶样本数
   - 平均收益
   - 中位数收益
   - 上涨概率
7. 同时按 `operation_advice` 做一版分组统计

## 适用范围

这是小样本实验，不是正式策略验证。

适合现在这种情况：

- 数据量还不大
- 先看分数有没有排序能力
- 不急着做正式资金曲线

## 运行方式

在项目根目录执行：

```bash
python3 回测/run_small_sample_backtest.py
```

如果想自定义数据库路径：

```bash
python3 回测/run_small_sample_backtest.py --db /absolute/path/to/stock_analysis.db
```

## 输出文件

默认会生成：

- `回测/output/record_level_returns.csv`
- `回测/output/score_bucket_summary.csv`
- `回测/output/advice_summary.csv`
- `回测/output/summary.md`

## 注意

- 样本很少时，结果只能做方向性参考
- 如果某个桶样本数太少，不要过度解读
- 这版默认使用“分析日之后第一个可用交易日收盘价”为起点
