# 金融业务

先读 [应用规则](../AGENTS.md)。

## 模块职责

| 模块 | 职责 |
| --- | --- |
| `contracts.py` | 行情输入与正式结论契约，限制可请求的数据范围 |
| `market.py` | 获取、验证并归档固定行情，返回来源、单位和缺口 |
| `validation.py` | 从归档数据重算正式产物，验证引用及结论条件 |

## 业务约束

- 当前支持 A 股 daily / 1d / none；一次最多三只证券、一年区间，不隐式扩展权限或复权口径。
- 价格保留十进制文本；成交量为手、成交额为千元；缺失值不补零。
- 时间边界按 Asia/Shanghai 解释，排除截止点当天日线；同轮查询复用固定快照。
- 当前历史日线标记 historical_reconstruction，不宣称点时数据或无前视偏差。
- 正式 signal / backtest 从归档快照重算 close_return；检查执行输入、引用归属、日期、单位、币种及口径。
- backtest 仅表示带基准的区间收益比较，不宣称包含费用、滑点或完整策略回测。
- observation 需要正反查证、截止点前可确定时间的支持证据、条件和 validated signal。
- 区分无结果、部分数据与失败；允许 insufficient_evidence 和 no_opportunity，不编造机会。
- 修改这些边界时同步 `tests/unit/` 中对应回归用例和 README 金融边界说明。
