# CLI Guide

## 目录

- [命令形态](#命令形态)
- [命令发现](#命令发现)
- [历史别名与 `tool_name`](#历史别名与-tool_name)
- [Flag 语义层](#flag-语义层)

## 命令形态

```bash
meegle <resource> <method> [flags] --format json
```

包维护命令例外：`meegle update` 是 npm-only 的本地升级入口，不访问 Meegle MCP；
`meegle version`、`meegle --version`、`meegle help` 和 `meegle completion` 也不
触发后台版本检查。自动更新提醒只写 `stderr`，需要纯结构化 `stdout` 时可设置
`MEEGLE_CLI_NO_UPDATE_NOTIFIER=1`。

默认优先使用 `--format json`，除非用户明确需要 table 或 ndjson。

## 命令发现

统一按以下条件发现，不将诊断变成固定业务前置：

- **inspect**：参数/能力/projection 不确定、新复杂 shape、命令报错需诊断或 schema 过期/漂移时读取 live descriptor。已验证 public CLI contract 覆盖且当前上下文未变的普通读路径，不为展示固定追加 inspect；不从示例推导未知能力。
- **只读 dry-run**：普通已知条件直接查询，不因分页/projection 固定预览；新复杂嵌套条件、时间边界、shape 不确定或明确排障时先预览 normalized request。
- **写入/conditional/destructive**：仍按对应 SOP 保留命令面、risk/capability、用户授权、写前预览及写后核验；上述普通读豁免不适用于写。destructive 必须用户明确要求并带 `--confirm`；conditional warning 不等于已授权。
- **证据范围**：仅同任务、同 profile/账号/空间/类型且未漂移的适用证据可复用；变化时重新确认相应权威证据，不缓存权限。空间与元数据发现见 [workitem.md](workitem.md#发现与复用)。
- **doctor**：用户要求诊断、auth/config 异常、业务错误无法定位或 runtime/descriptor 漂移才调用，见 [runtime-private-remote-mcp.md](runtime-private-remote-mcp.md#on-demand-diagnostics)。

需要发现时，以 live CLI 为准：

```bash
meegle inspect
meegle inspect workitem.create --format json
meegle inspect comment.add --format json
```

当历史示例与 inspect 不一致时，优先相信 inspect 输出。

把 `inspect --format json` 看成 manifest-backed public command descriptor，而不是原始 tool schema。构造命令时，优先读取：

- `parameters[].flag`：CLI 直接可用的 flag 名
- `parameters[].name`：后端 canonical 参数名
- `parameters[].type` / `required` / `envelope` / `items`
- `runtime_source` / `snapshot_stale`
- `deprecation.replacement`

能力尚未确认或发生漂移时，使用 `--select` 前读取 `inspect --format json` 的 projection metadata（普通已验证读路径复用适用 contract）：

- `projection.backend_select_supported`
- `projection.backend_request_path`
- `projection.local_projection_flag`
- `projection.local_path_hint`（如 `view items` 的 `data.<field>`）
- `decision_guidance.projection_mode`
- `decision_guidance.wrapper_path_hint`
- `decision_guidance.dry_run_recommended`

执行前额外判断：

- `runtime_source == "live"`：允许正常执行
- `runtime_source == "snapshot"`：只允许 `inspect` / `doctor` 等只读诊断；不要继续执行业务命令
- `deprecation.replacement` 存在：优先改用 replacement

## 历史别名与 `tool_name`

- `inspect --format json` 返回的 `tool_name` 用于说明底层绑定，不等于 public CLI 命令名。
- 组装和执行命令时，只认 `inspect.name` / `parameters[].flag` 暴露的 public command surface，不要把内部 `tool_name`、旧 skill、旧 OpenSpec 里的历史别名直接拿来执行。
- 常见混淆例子：当前 public command 是 `workitem meta-types` / `workitem meta-fields`，而历史材料里可能出现 `space types` / `workitem meta`，底层 `tool_name` 还可能分别显示为 `meegle_space_types` / `meegle_config_field_list`。遇到这种情况，优先相信 live `inspect`。

## Flag 语义层

全局 flag 不是同一类能力。先判断语义层，再判断能否影响后端请求。

| 语义层 | 代表 flag | 是否进入后端业务请求 | 使用原则 |
|---|---|---:|---|
| Request input | 命令自身 flags、`--params/-P`、`--set`、支持 backend projection 的 `--select` | 是 | 用于过滤、分页、写入、字段 projection 等请求语义 |
| Execution control | `--dry-run`、`--refresh` | 否 | 控制 CLI 执行流程、认证刷新或请求预览 |
| Output display | `--format`、`--envelope`、`--verbose`、`--output-select` | 否 | 控制本地输出形状或诊断信息，不替代后端过滤 |
| Compat / lower-level | `--fields` 等 API-native 参数 | 是 | 仅在命令特定兼容场景使用，不作为默认产品化 UX |

### 命令专属 flag 消歧

不要把一个命令的合法 flag 泛化到另一个命令。按已验证 contract 选 flag；未覆盖或漂移时用 `inspect <resource>.<method> --format json` 的 `parameters[].flag` 校验，触发条件见 [命令发现](#命令发现)。已知高混淆点如下：

| 场景 | 正确命令 / flag | 禁止串用 | 原因 |
|---|---|---|---|
| 按名称搜索工作项 | `workitem search-filter --work-item-name "名称"` | `workitem search-filter --name`、`workitem search-filter --keyword` | `--name` 是 `workitem create` 的标题输入，`--keyword` 不是 search-filter 参数 |
| `search-filter` 类型范围 | `--work-item-type-keys '["TYPE_KEY"]'` | `--work-item-type-key TYPE_KEY` | `search-filter` 接收复数数组 |
| `search-by-params` 类型范围 | `--work-item-type-key TYPE_KEY` | `--work-item-type-keys '[...]'` | `search-by-params` 接收单个类型 |
| `workitem get` 读取 ID | `--work-item-ids '[123]'` | `--work-item-id 123`、`--work-item-ids '["123"]'` | `get` 是批量读取接口，接收 number 数组 |
| `workitem update` 写入 ID | `--work-item-id 123` | `--work-item-ids '[123]'` | `update` 是单对象写入 |
| 固定 / 条件视图列表 | `view list --work-item-type-key TYPE_KEY --page-size N` | `--work-item-type-keys` | `view list` 按单类型列视图 |
| 读取固定视图 items | `view items --project-key PROJ --view-id VIEW_ID` | `--page-size`、`--select` | `view items` 当前 live 请求参数只有 `project-key` / `view-id`；展示裁剪用 `--output-select data.xxx` |
| 后端字段 projection | `workitem get/search-by-params --select id,name,...` | 在 `search-filter` / `view items` 上用 `--select` | 只有 `projection.backend_select_supported == true` 的命令支持 |
| `search-by-params` 默认展示字段 | `--select id,name,work_item_status,current_status_operator,created_at` | `--fields '["id",...]'` | 普通展示走产品化 `--select`，不要因 live 底层参数名是 `fields` 回退到 `--fields`；`current_status_operator` 仍按 `fields[]` 业务字段读取 |
| 本地展示裁剪 | `--output-select ...`，object-wrapper 用 `data.xxx` | 把 `--output-select` 当过滤条件 | `--output-select` 不进入后端请求 |
| 查询 / 展示字段元数据 | `workitem meta-fields` | `meta-create-fields` | `meta-fields` 是查询、过滤、状态/枚举 label 映射来源 |
| 创建 / 写入字段 shape | `workitem meta-create-fields` | `meta-fields` | `meta-create-fields` 承载创建页必填、模板和写入 shape |
| 类型入参取值 | `meta-types` 返回的 UUID `type_key` | `api_name`、URL path、中文名直接当 `--work-item-type-key(s)` | CLI 业务命令需要 UUID type key |

如果发现自己想用上表“禁止串用”列里的 flag，不要先 probe；先改回正确 flag。只有表中没有覆盖、且参数 shape 确实不确定时，才用 `inspect` 诊断。

### Array flag value shape

`inspect.parameters[].type == "array"` 的 flag 示例必须写成 JSON array string，不要裸传单值，也不要用重复 flag 代替数组。常见格式：

```bash
--work-item-type-keys '["TYPE_KEY"]'
--work-item-ids '[12345]'
--user-keys '["USER_KEY"]'
--recordIDs '["RECORD_ID_1","RECORD_ID_2"]'
--trigger '[{"iBuildAppId":"APP_ID","chartFullName":"REPO/CHART.tgz"}]'
```

数组元素类型以 `inspect.parameters[].items.type` 为准。`workitem get` 的 `work_item_ids` 是 `number[]`，必须传 `--work-item-ids '[12345]'`；不要传 `--work-item-ids '["12345"]'`。

相反，单值 flag 不要写成数组，例如 `--work-item-type-key TYPE_KEY`、`--work-item-id 12345`。

### Structured request input

`--params/-P` 与 `--set` 用于补充 request input：

```bash
meegle workitem search-filter \
  --project-key PROJ \
  --work-item-type-keys '["TYPE_KEY"]' \
  --params '{"page_size":50}' \
  --set 'created_at.start=1771603200000' \
  --set 'created_at.end=1779379199000' \
  --dry-run \
  --format json
```

优先级稳定为：

```text
--params/-P < --set < 具体命令 flag
```

新复杂嵌套对象、时间边界、shape 不确定、明确排障或写操作时，先加 `--dry-run` 检查 `.params`；普通已验证分页/projection 不固定预览，见 [命令发现](#命令发现)。

verified command 的 dry-run 如果发现明显未知顶层参数，现在会直接 fail fast，而不是继续输出看似正常的 payload。遇到这种情况时：

1. 先修正 flag 名或 `--params` 顶层 key
2. 若 CLI 给出高置信度 `did-you-mean`，优先按该建议改写
3. 用 `meegle inspect <resource>.<method> --format json` 对照当前 public flag 集
4. 如怀疑本地 schema 过期，再加 `--refresh`

### Backend projection 与本地输出裁剪

`--select` 与 `--output-select` 不是同义词：

| 目标 | 使用 | 效果 |
|---|---|---|
| 减少后端返回字段 | `--select id,name,work_item_status` | 进入后端请求；当前首批支持 `workitem get`、`workitem search-by-params` |
| 只减少本地展示字段 | `--output-select id,name,work_item_status` | 后端仍返回原始结果，CLI 在响应后裁剪展示 |

判断 `--select` 能力不能猜：按 [命令发现](#命令发现) 使用已验证 contract 或必要时读取 `projection.backend_select_supported`。

示例：排障时预览支持 backend projection 的命令（不是普通读固定前置）。

```bash
meegle workitem search-by-params \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --search-group '{"conjunction":"AND","search_params":[],"search_groups":[]}' \
  --select id,name,work_item_status,created_at \
  --dry-run \
  --format json
```

dry-run 中应看到 `params.data.fields`：

```json
{
  "data": {
    "fields": ["id", "name", "work_item_status", "created_at"]
  }
}
```

示例：只做本地展示裁剪。

```bash
meegle workitem search-filter \
  --project-key PROJ \
  --work-item-type-keys '["TYPE_KEY"]' \
  --page-size 20 \
  --output-select id,name,work_item_status,created_at \
  --format json
```

如果该列表响应还需要进一步缩小分页元字段，只保留需要的 `pagination` 子字段：

```bash
meegle workitem search-filter \
  --project-key PROJ \
  --work-item-type-keys '["TYPE_KEY"]' \
  --page-size 20 \
  --output-select data.id,data.name,data.work_item_status,data.created_at,pagination.total,pagination.page_num,pagination.page_size \
  --format json
```

如果在非 projection-capable 命令上使用 `--select`：

- CLI 会直接返回错误，不再做本地裁剪 fallback。
- 错误 remediation 会同时指向 `meegle inspect <resource>.<method> --format json` 和与该命令返回形状匹配的 `--output-select` 改写方式。
- 目标是本地展示裁剪：改用 `--output-select`。
- 目标是减少后端字段：改用 `workitem get` / `workitem search-by-params` 等支持 backend projection 的命令，或移除 projection 诉求。

说明：当前 backend projection 在 `workitem get` / `workitem search-by-params` 上主要会收敛 `fields[]` 业务字段集合；工作项稳定顶层 allowlist 仍可能按接口契约返回。`--select` 是返回字段声明，不是 JSON 顶层路径声明；例如 `current_status_operator` 可以放进 `--select`，但读取时仍从 `fields[]` 找同名 `field_key` / `field_alias`。

`--output-select` 的路径需要匹配真实响应形状：

- 列表响应或 `{data:[...]}` wrapper：通常可以直接写 `id,name,work_item_status`，CLI 会自动投影到数组元素，并默认保留同级 `pagination`。只有想显式约束分页元字段时，才改写成 `data.<field>` 与 `pagination.xxx`。
- object-wrapper 响应：需要显式写 wrapper 路径，例如 `view items` 用 `--output-select data.name,data.view_id,data.work_item_id_list`。
- 对已知 object-wrapper 命令，如果误写成 bare key，CLI 会返回 wrapper-aware remediation，并提示你用 `inspect` 确认 `data.xxx` 路径。

### `--fields` 兼容边界

`--fields` 是 API-native compatibility input，不是默认 projection UX。`workitem search-by-params` 的 live `inspect.parameters[]` 可能显示底层参数 `fields`，但当 `projection.backend_select_supported == true` 时，Skill 默认使用 CLI 产品化 alias `--select`；CLI 会把它映射到后端 `data.fields`。

- 命令支持 backend projection 时，优先使用 `--select`。
- 只有当用户明确需要底层 API-native `fields` 参数，或排障需要直连底层参数时，才使用 `--fields`。
- 不要在同一命令中同时传 `--select` 与 `--fields`；CLI 会返回确定性冲突错误。

### 输出展示 flag

`--format`、`--envelope`、`--verbose`、`--output-select` 都属于本地输出展示层：

- `--format json`：默认稳定机器可读输出。
- `--format ndjson`：适合流式或逐行处理。
- `--format table`：适合人类浏览。
- `--envelope`：输出 `{data, meta, error}` wrapper；用于需要响应 envelope 的脚本或排障。
- `--verbose`：增加 table 细节或错误诊断；不要把它当成 JSON data shape contract。
- `--output-select`：响应返回后裁剪展示字段；不改变后端请求。

`--dry-run` 验证请求构造，不验证这些输出展示 flag 的最终渲染效果。
