# 视图辅助命令

## Private CLI 差异

| upstream | private installed CLI |
|---|---|
| `view list` | `view list` |
| `view items` | `view items` |
| `view create-fixed` / `view update-fixed` | 当前不作为默认 skill 路径 |
| `view list-multi-project-workitems` | 当前 public CLI 不暴露，按需另行评审 |

视图 URL 路由先看 [url-kinds.md](url-kinds.md)。不要从 URL path 推断视图类型；必须先用 `view list` 读取 `view_type`。

URL decode 返回的 `work_item_type` 是 `api_name`，不是 `view list` 可用的 `work_item_type_key`。执行任何 `view list` 前，必须先用同空间的 `workitem meta-types` 把 `api_name` 映射为 UUID `type_key`；不要把 `story_new`、`bug_new`、`issue` 等 api_name 作为 `--work-item-type-key` 试探。

关键分流：

- `view_type=0` 或 `view_type=2`：可继续用 `view items` 读取视图包装信息和 `work_item_id_list`
- `view_type=1`：这是条件视图；先用 `inspect` / verified command surface 确认当前 public CLI 是否暴露条件视图 item reader。未确认前不要从 URL、视图名或历史经验猜实例集合；若当前命令面未暴露读取能力，停止读取路径并说明限制。

---

## view list

列出空间和工作项类型下的视图配置，返回 `view_id`、名称和 `view_type`。

```bash
meegle view list \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --page-num 1 \
  --page-size 50 \
  --format json
```

`view_type` 只用于选择后续路径，不要仅凭 URL 中的 `storyView` / `multiProjectView` 判断。
如果结果较多，优先显式传 `--page-num`、`--page-size`，避免默认返回过大结果集。

固定视图 URL 的最小只读序列：

1. `url decode`
2. `workitem meta-types` 映射 `api_name -> type_key`
3. `view list` 用真实 UUID `type_key` 确认目标 `view_id` 和 `view_type`
4. `view items` 读取 `data.name`、`data.view_id`、`data.work_item_id_list`
5. 如用户要标题或详情，对 `work_item_id_list` 执行一次 `workitem get`

不要在第 3 步之前用 URL 中的 api_name 试跑 `view list`。第 5 步是该业务目标的最终工作项查询：执行前先决定是否需要 `--output-select id,name`；一旦 `workitem get` 成功返回足以回答的数据，不要为了裁剪字段或生成表格再重跑同一批 ID。

## view items

读取固定视图或系统列表视图下的工作项。通常用于 `view_type=0` 或 `view_type=2`。

```bash
meegle view items \
  --project-key PROJ \
  --view-id VIEW_ID \
  --format json
```

`view items` 当前 live 参数只有 `--project-key` 和 `--view-id`。不要传 `--page-size`；它会报 `unknown flag: --page-size`。`view items` 当前不声明 backend projection。传 `--select` 会直接报错。只想减少本地展示字段时，用 `--output-select`，并按 object-wrapper 路径书写：

```bash
meegle view items \
  --project-key PROJ \
  --view-id VIEW_ID \
  --output-select data.name,data.view_id,data.work_item_id_list \
  --format json
```

注意：`view items` 返回的是 object-wrapper，不是直接数组，因此不要写成 `--output-select name,view_id`。
如果误写成 bare key，CLI 会直接返回 remediation，提示你改成 `data.xxx` 并指向 `meegle inspect view.items --format json`。

如果用户要“读取视图里的工作项”而不是只要 ID 列表，`view items` 只负责返回视图包装信息和 `work_item_id_list`。拿到 ID 后，继续用同一个 `work_item_type_key` 批量读取标题或详情。`workitem get` 一次最多传 50 个工作项 ID；超过 50 个时先取前 50 个做结果核验，或按 50 个一批分批查询。

```bash
meegle workitem get \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --work-item-ids '[12345,67890]' \
  --output-select id,name \
  --format json
```

不要把 `view items` 的 `data.name` 当成工作项标题；它是视图名称。

如果只是确认 URL 指向的视图类型，`view list` 可以用较小输出定位目标视图，避免展开大量视图配置：

```bash
meegle view list \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --page-num 1 \
  --page-size 100 \
  --output-select data.view_id,data.name,data.view_type \
  --format json
```

在当前页命中目标 `view_id` 后立即进入 `view items`；未命中时再按页翻查，不要用大段 shell 管道展开全量输出。

如果目标 `view_id` 不在首页，按页查询是允许的，但要保持有界：顺序查页，不要并发扫 1-10 页；命中目标页后立即停止。普通确认视图类型时不需要继续读取 items 或展开所有视图。

仅当 wrapper/projection 能力不确定或发生漂移时，按 [cli-guide.md](cli-guide.md#命令发现) 执行；普通已验证固定视图读路径不固定追加 inspect：

```bash
meegle inspect view.items --format json
```

确认：

- `projection.backend_select_supported == false`
- `projection.local_projection_flag == "--output-select"`
- `projection.local_path_hint == "data.<field>"`
- `decision_guidance.wrapper_path_hint == "data.<field>"`

条件视图读取是 capability-gated 路径。如果后续 public CLI 暴露 `view panoramic-items` 或等价 item reader，应单独评审命令契约后再纳入默认路径。

对于 `view_type=1`，不要把 `view items` 当作自愈 fallback。`view items` 只适用于固定视图或系统列表视图；条件视图只能在 public CLI contract 已验证时继续，否则 fail-fast。

## 条件与删除类视图操作

删除固定视图或条件视图、创建条件视图、更新条件视图都属于条件操作，不作为默认 skill 路径。只有用户明确要求管理视图配置时，才查看 `verified-command-surface.md` 与 `meegle inspect` 确认当前公开命令和参数。

条件视图创建 / 更新的 `search_group` 结构见下方。不要在普通读取工作流里主动引导用户使用这些写操作。

---

## search_group 结构

```json
{
  "conjunction": "AND",
  "search_params": [
    {
      "param_key": "字段key或固定参数key",
      "value": ["值1", "值2"],
      "operator": "HAS ANY OF"
    }
  ]
}
```

操作符枚举见 [search-params-format.md](search-params-format.md)。

### 常用固定参数

| 参数名 | param_key | 支持操作符 | value 格式 | 说明 |
|---|---|---|---|---|
| 进行中节点 | `current_nodes` | `=`、`!=`、`HAS ANY OF`、`HAS NONE OF`、`CONTAINS`、`NOT CONTAINS` | **节点名称**列表 | 从"获取流程模板配置详情"接口获取，**不是 state_key** |
| 流程节点（含历史） | `all_states` | 同上 | **节点名称**列表 | |
| 业务线 | `business` | `=`、`!=`、`HAS ANY OF`、`HAS NONE OF`、`IS NULL`、`IS NOT NULL` | 业务线 ID 列表 | 从 `meegle space business-lines` 获取 |
| 工作项状态 | `work_item_status` | `=`、`!=`、`HAS ANY OF`、`HAS NONE OF` | `state_key` 列表 | 来自 `meegle workitem meta-fields` 的 `options[].value` |
| 模板 | `template` | `=`、`!=`、`HAS ANY OF`、`HAS NONE OF`、`IS NULL`、`IS NOT NULL` | 模板 ID 列表 | |
| 更新时间 | `updated_at` | `=`、`!=`、`<`、`>`、`<=`、`>=` | UTC 格式字符串 | 如 `2024-09-01T00:00:00+07:00` |

### 普通字段

`param_key` 为字段的 `field_key`，`value` 格式与字段类型对应（user 类型传 user_key 列表，select 类型传 option value 列表等）。

### 示例：测试业务线 + 我负责 + 已完成状态

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "business", "value": ["678f4f4907926543018acd93"], "operator": "="},
    {"param_key": "owner", "value": ["7457914056381416309"], "operator": "HAS ANY OF"},
    {"param_key": "work_item_status", "value": ["-a2LFTw3o"], "operator": "HAS ANY OF"}
  ]
}
```

### 示例：筛选处于"需求完成"节点的工作项

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "current_nodes", "value": ["需求完成"], "operator": "HAS ANY OF"}
  ]
}
```
