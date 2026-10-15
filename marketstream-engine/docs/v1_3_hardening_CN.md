# MarketStream Engine v1.3 — SDE 工程整改说明

## 交付定位

v1.3 基于用户提供的 v1.2 完整 ZIP 源码构建；保留金融微观结构五档盘口、交易快照对齐、特征、候选事件及可视化。目标是提高本地数据处理软件的 **完整性、质量决策正确性、数据语义和可复现性**，而不是宣称上线真实交易平台。

## 已实际完成的修改

| 来源于上一轮审查的问题 | v1.3 代码处理 | 验收重点 |
|---|---|---|
| 修改后的 Manifest 可被重发重新信任 | 新 schema-4 独立提交 Seal，缓存复用必须复核 Seal 与实际 Manifest | 篡改 Manifest 再重发会失败，CURRENT 不会变更 |
| 匹配率被舍入导致边界误判 | 保留原始计数；质量判断使用 Decimal 比较 | 任何未全匹配记录均不能通过 100% 门槛 |
| 全局质量掩盖单股票失败 | 新增 symbol/date 分组统计和可选门槛 | 特定股票/交易日可独立 fail/warn |
| 质量检查阶段过晚 | 立即在 as-of join 后执行 | fail 时不会启动特征计算 |
| 真实 CSV 绘图仍引用 synthetic dates | 独立 `figure_date` 参数，缺省选实际最新交易日 | 不必修改 synthetic dates 即可绘制真实数据日期 |
| 大金额精度与 int64 安全 | 可选 Decimal 到整数 `cum_amount_minor`、计数及 tick 索引越界拒绝 | 不截断/不四舍五入；明确 float64 仍存在 |
| pandas 内部哈希缺乏规范 | 新增版本化 `canonical-rows-v1` 字节序列化摘要 | 相同输入稳定，不同精度输入产生不同摘要 |
| Git 安全审计大小写绕过 | 对路径进行 casefold 和全路径分段审计 | `Data/`、嵌套 `SECRETS/` 拒绝 |
| 文档版本不一致 | 重写 README、架构、数据契约、可靠性、测试与 ADR | 旧版技术报告收纳至 history |

## 严格限制与未完成事项

- 没有 cryptographic signatures / external trusted immutable journal；对拥有全部目录修改权限的攻击者不提供真实性保证。
- 在 run rename 到独立提交 Seal 写入之间异常时可能留下未 Seal 的孤儿目录，需要人工审查。
- 只有 **可选的累计金额整数最小单位** 输入契约，不是完整 Decimal / 整数 tick 金融计算引擎；派生价格指标保留 float64。
- 仍然是全内存批处理，未实现分区执行、断点恢复、真正消息流和确定性事件重放。
- GitHub 远程 CI/Docker 与缺少本地工具的验证必须以真实运行结果为准；不能凭存在工作流文件就声称通过。

## 下一阶段建议（并非已实现）

优先补充完整可审计的幂等恢复与 orphan repair/GC；明确交易所时区、session、sequence ID；为价格也建立整数 tick 模型；建立 v1.2-v1.3 同环境基准对照，并对显著性能热点进行分区/列式改造。先取得真实的 CI 通过记录后再考虑高级流式系统。
