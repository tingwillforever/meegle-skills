# Instance Role Assignment

用于 direct MCP 下把“处理人、报告人、项目经理、研发项目经理、研发代表、测试代表”等实例角色赋给人员。实例角色字段是 `role_owners`；workflow node owner、`role_assignee` 与派生字段 `current_status_operator` 是不同概念。

## 角色发现

在 `project_key + work_item_type_key` 确定后最多调用一次 `meegle.config.flowRole.list`。canonical 返回为 `data[]`：

```json
{"id":"role_xxx","name":"处理人"}
```

按用户说出的角色显示名与 `name` 精确匹配。只接受唯一结果，并使用 `id` 写入。创建场景或明确角色名更新中，无匹配、多匹配或缺少 `id` 时展示候选并停止；已有实例的泛化“处理人”是唯一例外，先按下方规则与一次 workflow 结果交叉，交叉后仍不唯一才停止。不要硬编码租户 role id，不要读取样本工作项反推角色。

## 写入

创建或更新都使用原生字段结构：

```json
{
  "field_key": "role_owners",
  "field_value": [
    {"role":"role_xxx","owners":["user_key"]}
  ]
}
```

- 创建实例没有当前节点，workflow 调用预算为 0。
- 更新明确角色名时 workflow 调用预算为 0。
- 更新已有实例的泛化“处理人”时仍先精确匹配 `name == "处理人"`；仅失败时可调用一次 `meegle.workflow.query`，用当前生效单元引用的 role id 与同一次角色元数据交叉唯一匹配。
- 仍不唯一时停止，不降级为 `owner`。
- `current_status_operator` 不可直接写；它为空不代表 `role_owners` 没有持久化。

更新是覆盖语义。需要只替换一个角色并保留其他角色时，先用一次 `meegle.workitem.get` 读取旧 `role_owners`，替换目标 role 后整体写回。写后再次 `meegle.workitem.get` 核验 `role_owners`。
