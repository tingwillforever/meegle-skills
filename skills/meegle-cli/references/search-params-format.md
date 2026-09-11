# search_params 格式规范

> **Source**: https://project.feishu.cn/b/helpcenter/1p8d7djs/1l8il0l6（飞书项目「搜索参数格式及常用示例」官方文档，2026-05 抓取）
>
> 本文覆盖 `workitem search-by-params` 的 `--search-group` 入参构造规范。
> 字段写入（`workitem create` / `workitem update`）的 `field_value` shape 见 [field-value-format.md](field-value-format.md)。

`workitem search-by-params` 支持 backend projection。需要限制后端返回字段时，默认使用 CLI 产品化 projection alias `--select id,name,...`；live `inspect.parameters[]` 可能显示底层 API-native 参数 `fields`，但普通 skill 路径不要改用 `--fields`。`--fields` 仅作为兼容/排障输入，不要与 `--select` 同时使用。只想裁剪本地展示时，用 `--output-select`。

---

## 常用复合检索速查 (Quick Patterns)

大多数复杂筛选可直接套用以下 3 种标准模式：

### 1. 查我负责/与我相关的工作项
```bash
meegle workitem search-by-params \
  --project-key <project_key> \
  --work-item-type-key <type_key> \
  --search-group '{"conjunction":"AND","search_params":[{"param_key":"people","operator":"HAS ANY OF","value":["<meegle_user_key>"]}],"search_groups":[]}' \
  --select id,name,work_item_status,created_at \
  --page-size 10 --format json
```

### 2. 查关联到特定工作项（按被关联 ID）
> 注意：关联字段过滤的 value 必须是**数字 ID 数组**（如 `[20336086]`），不能传字符串。
```bash
meegle workitem search-by-params \
  --project-key <project_key> \
  --work-item-type-key <subject_type_key> \
  --search-group '{"conjunction":"AND","search_params":[{"param_key":"<related_field_key>","operator":"HAS ANY OF","value":[<target_work_item_id>]}],"search_groups":[]}' \
  --select id,name,work_item_status,created_at \
  --page-size 10 --format json
```

### 3. 按时间范围与状态组合过滤
> 注意：创建/更新时间过滤的 value 是毫秒时间戳（int64）。
```bash
meegle workitem search-by-params \
  --project-key <project_key> \
  --work-item-type-key <type_key> \
  --search-group '{"conjunction":"AND","search_params":[{"param_key":"created_at","operator":">=","value":1779436496000},{"param_key":"work_item_status","operator":"!=","value":["Finished"]}],"search_groups":[]}' \
  --select id,name,work_item_status,created_at \
  --page-size 10 --format json
```

---

## 顶层结构：SearchGroup

```json
{
  "conjunction": "AND",        // "AND" 或 "OR"，对应筛选器的「且/或」
  "search_params": [...],      // SearchParam 数组，每条是一个筛选条件
  "search_groups": [...]       // 嵌套 SearchGroup，用于复杂逻辑组合
}
```

## 单条筛选：SearchParam

| 字段 | 类型 | 说明 |
|------|------|------|
| `param_key` | string | 字段 key（普通字段用 `field_key`，特殊字段用固定 key，见下表） |
| `operator` | string | 操作符，不同字段类型支持的操作符不同，见下表 |
| `value` | interface{} | 筛选值，格式随 `param_key` 类型变化 |
| `pre_operator` | string | 前置操作符，仅复合字段场景使用 |
| `value_search_groups` | SearchGroup | 仅 `compound_field` 且 operator 为 `MEET`/`NOT MEET` 时使用；其内部 `search_params` 不支持 `pre_operator` |

> 说明：筛选参数不支持字段类型为公式计算的字段。

---

## 固定参数（特殊 param_key）

这些 key 不是 `field_key`，是系统内置的固定参数名。

| 参数名 | param_key | 支持的 operator | value 类型 | value 说明 |
|--------|-----------|----------------|------------|------------|
| 进行中节点 | `current_nodes` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `CONTAINS` `NOT CONTAINS` | `list<string>` | 节点**名称**列表（不是 state_key） |
| 流程节点 | `all_states` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `CONTAINS` `NOT CONTAINS` | `list<string>` | 节点名称列表 |
| 流程节点时间 | `feature_state_time` | `<` `>` `<=` `>=` `IS NULL` `IS NOT NULL` | object | 见下方示例 |
| 全部人员 | `people` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` `CONTAINS` `NOT CONTAINS` | `list<string>` | user_key 列表 |
| 创建时间 | `created_at` | `=` `!=` `<` `>` `<=` `>=` | int64 | 毫秒时间戳，**单值**；区间需传两条 |
| 指定节点负责人 | `node_owners` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` `CONTAINS` `NOT CONTAINS` | `list<object>` | 见下方示例 |
| 工作项 ID | `work_item_id` | `=` `!=` `<` `>` `<=` `>=` `HAS ANY OF` `HAS NONE OF` | `list<int64>` | 工作项 ID 列表 |
| 工作项状态 | `work_item_status` | `=` `!=` `HAS ANY OF` `HAS NONE OF` | `list<string>` | state_key 列表，见下方说明 |
| 模板 ID | `template_id` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` | `list<int64>` | 模板 ID 列表 |
| 业务线 | `business` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` | `list<string>` | 业务线 ID 列表 |
| 角色人员 | `role_owners` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` `CONTAINS` `NOT CONTAINS` | object | 见下方示例 |

### ⚠️ work_item_status 特殊规则

- value 是状态的 `state_key`，**不是** display name；内置状态是可读字符串（如 `"started"`、`"Finished"`），自定义状态是 opaque ID
- state_key 来源：查询路径默认从 `workitem meta-fields` 中 `work_item_status` 字段的 `options[].value` 获取；不要为了 search/filter 回到 `meta-create-fields`
- **不能同时查询「已终止」和「未终止」的工作项**
- 筛选已终止：`=` 或 `HAS ANY OF` 时传 `closed`（节点流）/ `systemEnded`（状态流）
- 排除已终止：`!=` 或 `HAS NONE OF` 时**无需**传 `closed`/`systemEnded`，系统默认排除

### ⚠️ created_at / 时间区间

时间字段每条只接受**单个毫秒整数**，区间需拆成两条：

```json
{"param_key": "created_at", "operator": ">", "value": 1771603200000},
{"param_key": "created_at", "operator": "<", "value": 1779379199000}
```

Python 换算：`int(datetime(..., tzinfo=tz).timestamp() * 1000)`

### feature_state_time 示例

```json
{
  "param_key": "feature_state_time",
  "operator": ">",
  "value": {
    "state_name": "Android开发估分",
    "state_timestamp": 1702310399000,
    "state_condition": 1
  }
}
```

`state_condition`：`0` = 节点开始，`1` = 节点结束。

### node_owners 示例

```json
{
  "param_key": "node_owners",
  "operator": "HAS ANY OF",
  "value": [
    {"state_name": "开发", "owners": ["7457914056381416309"]}
  ]
}
```

多组节点之间是 AND 关系；需要 OR 时用 `search_groups` 拆分。

### role_owners 示例

```json
{
  "param_key": "role_owners",
  "operator": "HAS ANY OF",
  "value": [
    {"role": "role_id", "owners": ["7457914056381416309"]}
  ]
}
```

---

## 自定义字段参数

普通自定义字段的 `param_key` 就是 `field_key`（如 `field_f3badf`）。

| field_type_key | 支持的 operator | value 类型 | 说明 |
|----------------|----------------|------------|------|
| `text` | `~` `!~` `=` `!=` `IS NULL` `IS NOT NULL` | string | 前后模糊匹配 |
| `number` | `=` `!=` `<` `>` `<=` `>=` `IS NULL` `IS NOT NULL` | float64 | — |
| `link` | `~` `!~` `=` `!=` `IS NULL` `IS NOT NULL` | string | — |
| `bool` | `=` `!=` `IS NULL` `IS NOT NULL` | bool | 空值用 `IS NULL` |
| `signal` | `=` `!=` `HAS ANY OF` `HAS NONE OF` | `list<string>` | `"undefined"` 暂无信息 / `"null"` 进行中 / `"false"` 未通过 / `"true"` 已通过 |
| `select` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` | `list<string>` | 选项 value（不是 label），查询路径默认从 `meta-fields` 的 `options[].value` 取 |
| `radio` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` | `list<string>` | 同 select |
| `multi-select` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` `CONTAINS` `NOT CONTAINS` | `list<string>` | — |
| `tree-select` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` | `list<string>` | — |
| `tree-multi-select` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` | `list<string>` | — |
| `user` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` | `list<string>` | user_key 列表 |
| `multi-user` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` `CONTAINS` `NOT CONTAINS` | `list<string>` | user_key 列表 |
| `multi-text` | `~` `!~` `IS NULL` `IS NOT NULL` | string | 无格式匹配 |
| `workitem_related_select` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` | `list<int64>` | 关联工作项 ID 列表（**数字数组**，不是字符串，也不是单个标量） |
| `workitem_related_multi_select` | `=` `!=` `HAS ANY OF` `HAS NONE OF` `IS NULL` `IS NOT NULL` `CONTAINS` `NOT CONTAINS` | `list<int64>` | 同上 |
| `date` | `<` `>` `<=` `>=` `IS NULL` `IS NOT NULL` | int64 | 毫秒时间戳，区间拆两条 |
| `precise_date` | `<` `>` `<=` `>=` `IS NULL` `IS NOT NULL` | int64 | 同上 |
| `compound_field` | `IS NULL` `IS NOT NULL` `MEET` `NOT MEET` | — | `MEET`/`NOT MEET` 需配合 `value_search_groups` |
| 复合字段-子字段 | 支持本表格的自定义类型（除 `compound_field`）对应的操作符 | 对应子字段类型的值类型 | 直接填写在 `SearchParam` 中时支持 `pre_operator`；填在 `value_search_groups` 中时不支持 `pre_operator` |
| `telephone` | `~` `!~` `=` `!=` `IS NULL` `IS NOT NULL` | string | — |
| `email` | `~` `!~` `=` `!=` `IS NULL` `IS NOT NULL` | string | — |

> 兼容提示：本在线文档使用 `multi-select` / `multi-user` / `workitem_related_select` 等拼写；若 live CLI 元数据返回 `multi_select` / `multi_user` / `work_item_related_select` 等下划线拼写，按同一字段类型家族处理，优先以 live `field_type_key` 为准。

### ⚠️ 关联字段（workitem_related_select）ID 查找 SOP

关联字段的 value 是被关联工作项的**数字 ID**，不能直接知道，需要先查：

```bash
# Step 1：查字段 key 和类型
meegle workitem meta-fields \
  --project-key PROJ \
  --work-item-type-key TYPE_KEY \
  --output-select field_key,field_name,field_type_key \
  --format json
# 从返回 JSON 的 data[] 中筛选 field_type_key 属于 workitem_related_select / work_item_related_select 的字段。

# Step 2：查被关联工作项的 ID
# - 基础名称匹配、内置维度过滤：用 search-filter
# - 字段级/复杂条件查询，或当前授权/接口契约不适合 search-filter：用 search-by-params
meegle workitem search-filter \
  --project-key PROJ \
  --work-item-type-keys '["TARGET_TYPE_KEY"]' \
  --work-item-name "目标名称" \
  --format json
# 从返回 JSON 的 data[] 中读取 id 和 name。

# search-by-params 示例
meegle workitem search-by-params \
  --project-key PROJ \
  --work-item-type-key TARGET_TYPE_KEY \
  --search-group '{"conjunction":"AND","search_params":[{"param_key":"people","operator":"HAS ANY OF","value":["USER_KEY"]}],"search_groups":[]}' \
  --format json
# 从返回 JSON 的 data[] 中读取 id 和 name。

# Step 3：构造过滤条件（value 是数字数组）
# {"param_key": "field_key", "operator": "HAS ANY OF", "value": [19582870]}
#                                                                 ↑ 数字，不加引号
```

关联字段默认使用 `operator: "HAS ANY OF"` + `value: [ID]`。不要写成 `"operator":"=","value":19582870`；即使 operator 是 `=`，该字段族的 value shape 仍是 `list<int64>`，标量会触发 `param type must be []int64`。

---

## 操作符枚举值

官方源码定义（完整）：

```
// operator 枚举
"~"          // 匹配（模糊包含）
"!~"         // 不匹配（模糊不包含）
"="          // 等于
"!="         // 不等于
"<"          // 小于
">"          // 大于
"<="         // 小于等于
">="         // 大于等于
"HAS ANY OF" // 存在选项属于（多值 OR）
"HAS NONE OF"// 全部选项均不属于
"IS NULL"    // 为空
"IS NOT NULL"// 不为空
"CONTAINS"   // 包含（多值 AND）
"NOT CONTAINS"// 不包含
"MEET"       // 满足（复合字段子条件）
"NOT MEET"   // 不满足（复合字段子条件）

// pre_operator 枚举（仅复合字段）
"EVERY"      // 每一组
"ANY"        // 存在一组
```

> ⚠️ `IS NULL` / `IS NOT NULL` 时不校验 value（流程节点时间、节点负责人、角色人员除外）。

---

## 常用查询示例

### 1. 指定状态 + 创建时间区间

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "created_at",       "operator": ">",  "value": 1654064482000},
    {"param_key": "created_at",       "operator": "<",  "value": 1654063482000},
    {"param_key": "work_item_status", "operator": "=",  "value": ["start"]}
  ]
}
```

### 2. 包含指定人员

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "people", "operator": "HAS ANY OF", "value": ["USER_KEY"]}
  ]
}
```

### 3. 通过工作项 ID 查询

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "work_item_id", "operator": "HAS ANY OF", "value": [12345, 45678]}
  ]
}
```

### 4. 查询关联缺陷（通过 _field_linked_story）

路径参数的工作项类型需指定缺陷类型。

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "_field_linked_story", "operator": "=", "value": [12345]}
  ]
}
```

### 5. 一段时间内更新的工作项

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "updated_at", "operator": ">", "value": 1654064482000},
    {"param_key": "updated_at", "operator": "<", "value": 1657064482000}
  ]
}
```

### 6. 角色 A 且角色 B 均存在指定人员

```json
{
  "conjunction": "AND",
  "search_params": [
    {
      "param_key": "role_owners",
      "operator": "HAS ANY OF",
      "value": [
        {"role": "A", "owners": ["USER_KEY_A"]},
        {"role": "B", "owners": ["USER_KEY_B"]}
      ]
    }
  ]
}
```

### 7. 「开始」节点且「进行中」节点均存在指定负责人

```json
{
  "conjunction": "AND",
  "search_params": [
    {
      "param_key": "node_owners",
      "operator": "HAS ANY OF",
      "value": [
        {"state_name": "开始",   "owners": ["USER_KEY"]},
        {"state_name": "进行中", "owners": ["USER_KEY"]}
      ]
    }
  ]
}
```

### 8. 使用指定模板的工作项

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "template_id", "operator": "HAS ANY OF", "value": [123, 456]}
  ]
}
```

### 9. 排除结束状态（终止状态默认不返回，无需传 closed）

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "work_item_status", "operator": "!=", "value": ["end"]}
  ]
}
```

### 10. 复杂 OR + AND 嵌套：优先级非 P2，或（业务线=X 且 PM=指定人）

```json
{
  "conjunction": "OR",
  "search_params": [
    {"param_key": "priority", "operator": "HAS NONE OF", "value": ["2"]}
  ],
  "search_groups": [
    {
      "conjunction": "AND",
      "search_params": [
        {"param_key": "business",    "operator": "=",          "value": ["BUSINESS_ID"]},
        {"param_key": "role_owners", "operator": "=",          "value": [{"role": "pm", "owners": ["USER_KEY"]}]}
      ]
    }
  ]
}
```

### 11. 提出时间区间 OR 更新时间区间

```json
{
  "conjunction": "OR",
  "search_groups": [
    {
      "conjunction": "AND",
      "search_params": [
        {"param_key": "start_time", "operator": ">=", "value": 1696089600000},
        {"param_key": "start_time", "operator": "<=", "value": 1698767999000}
      ]
    },
    {
      "conjunction": "AND",
      "search_params": [
        {"param_key": "updated_at", "operator": ">=", "value": 1696089600000},
        {"param_key": "updated_at", "operator": "<=", "value": 1698767999000}
      ]
    }
  ]
}
```

### 12. 多层筛选组：优先级非 P2，且嵌套开始时间 OR 更新时间条件

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "priority", "operator": "HAS NONE OF", "value": ["2"]}
  ],
  "search_groups": [
    {
      "conjunction": "OR",
      "search_params": [
        {"param_key": "start_time", "operator": ">=", "value": 1696089600000},
        {"param_key": "start_time", "operator": "<=", "value": 1698767999000}
      ]
    },
    {
      "conjunction": "AND",
      "search_params": [
        {"param_key": "updated_at", "operator": ">=", "value": 1696089600000},
        {"param_key": "updated_at", "operator": "<=", "value": 1698767999000}
      ]
    }
  ]
}
```

### 13. 筛选流程节点时间区间

```json
{
  "conjunction": "AND",
  "search_params": [
    {
      "param_key": "feature_state_time",
      "operator": ">=",
      "value": {"state_name": "Android开发估分", "state_timestamp": 1701792000000, "state_condition": 0}
    },
    {
      "param_key": "feature_state_time",
      "operator": "<=",
      "value": {"state_name": "Android开发估分", "state_timestamp": 1702310399000, "state_condition": 1}
    }
  ]
}
```

### 14. 按创建者搜索（自定义字段 field_key）

先通过「获取空间字段」API 拿到创建者字段的 `field_key`，再：

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "owner", "operator": "HAS ANY OF", "value": ["USER_KEY"]}
  ]
}
```

### 15. 按工作项状态筛选

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "work_item_status", "operator": "HAS ANY OF", "value": ["started"]}
  ]
}
```

### 16. 复合字段为空

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "field_xxxxxx", "operator": "IS NULL"}
  ]
}
```

### 17. 复合字段：每一组文本子字段都等于 1

```json
{
  "conjunction": "AND",
  "search_params": [
    {
      "param_key": "field_xxxxxx",
      "operator": "MEET",
      "pre_operator": "EVERY",
      "value_search_groups": {
        "conjunction": "AND",
        "search_params": [
          {"param_key": "field_xxxxxx", "operator": "=", "value": "1"}
        ]
      }
    }
  ]
}
```

或直接在子字段上加 `pre_operator`：

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "field_4396f8", "operator": "=", "pre_operator": "EVERY", "value": "1"}
  ]
}
```

### 18. 复合字段：存在一组文本子字段等于 1

```json
{
  "conjunction": "AND",
  "search_params": [
    {
      "param_key": "field_ba8f2e",
      "operator": "MEET",
      "pre_operator": "ANY",
      "value_search_groups": {
        "conjunction": "AND",
        "search_params": [
          {"param_key": "field_4396f8", "operator": "=", "value": "1"}
        ]
      }
    }
  ]
}
```

或：

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "field_4396f8", "operator": "=", "pre_operator": "ANY", "value": "1"}
  ]
}
```

---

## 本项目常用示例

### 近 3 个月创建 + 业务线 + 排除已完成 + 关联字段过滤

```json
{
  "conjunction": "AND",
  "search_params": [
    {"param_key": "business",         "operator": "HAS ANY OF",  "value": ["BUSINESS_LINE_ID"]},
    {"param_key": "created_at",       "operator": ">",           "value": 1771603200000},
    {"param_key": "created_at",       "operator": "<",           "value": 1779379199000},
    {"param_key": "work_item_status", "operator": "HAS NONE OF", "value": ["Finished"]},
    {"param_key": "CUSTOM_FIELD_KEY", "operator": "HAS ANY OF",  "value": [RELATED_WORKITEM_ID]}
  ],
  "search_groups": []
}
```
