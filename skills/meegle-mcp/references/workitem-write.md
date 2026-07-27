# Workitem Write

本文件定义 direct MCP 下的工作项写路径。

## 通用规则

1. 先读取，再写入。
2. 先回显目标范围，再执行。
3. 复杂字段写入或状态流转后必须 readback / 回读。
4. destructive / conditional 操作必须等待用户明确确认。
5. 创建和更新的详细 SOP 分别见 [sop-create-workitem.md](sop-create-workitem.md) 与 [sop-update-workitem.md](sop-update-workitem.md)；本文件只保留公共写路径边界。

## 创建

默认顺序：

1. `meegle.space.types` 确认 `work_item_type_key`
2. `meegle.workitem.meta` 读取字段与 options
   - 用户指定实例角色时，另调用一次 `meegle.config.flowRole.list`
3. `meegle.workitem.createPreflight` 读取有效必填
4. `meegle.workitem.create`
5. 用 `meegle.workitem.get` 做结果核验

规则：

- 当前 session 只有一个 `projectKeys` 时，该值就是默认 `project_key`。创建前应直接回显并使用它，不要把“空间确认”再次抛给用户。
- 只有 session 暴露多个 `projectKeys`、用户明确指定了其他空间、或当前写接口明确要求不同 key 形态时，才补做空间确认或解析。
- `createPreflight` 是有效必填事实源
- 字段 option value 必须来自元数据，不要猜 label
- `createPreflight` 不是字段白名单；用户明确要求的可选字段仍要保留到 create payload
- 处理人、报告人、项目经理等实例角色按 [role-assignment.md](role-assignment.md) 写 `role_owners`
- 批量创建必须串行执行，并逐个 readback

## 更新

默认顺序：

1. `meegle.workitem.get`
2. 普通字段用 `meegle.workitem.meta`；实例角色用 `meegle.config.flowRole.list`
3. `meegle.workitem.update`
4. 必要时 `meegle.workitem.get` readback

需要 readback 的高风险字段：

- 关联字段
- 人员字段
- 多选枚举
- 复合字段
- 排期类对象字段
- 富文本字段

如果当前 session 只有一个 `projectKeys`，更新默认直接落在该空间；执行前确认的是对象范围和变更风险，不是再次确认空间本身。

更新默认是覆盖语义。用户说“追加 / 再加 / 补充”时，必须先读取旧值、合并、去重，再整体写回；不要把追加误做覆盖。

实例角色规则见 [role-assignment.md](role-assignment.md)；其他不可写字段和字段 shape 见 [field-value-format.md](field-value-format.md)。

## 中止 / 恢复 / 冻结

使用：

- `meegle.workitem.abort`
- `meegle.workitem.restore`
- `meegle.workitem.freeze`
- `meegle.workitem.unfreeze`

这些都属于有业务影响的操作，执行前要再次确认对象范围。

若当前 session 只有一个 `projectKeys`，该空间默认沿用；不要把空间本身再次当成待确认问题。

执行后必须读取目标工作项或相关状态，确认生命周期状态已经变化。
