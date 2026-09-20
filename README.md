# Meegle Skills

这个仓库是公开可安装的 Meegle skill mirror，统一发布三套 skill：

- `meegle-cli`：给本机安装了 `meegle` CLI 的用户使用，覆盖日常工作项、视图与工作流操作
- `meegle-mcp`：给业务方 Agent 平台或 MCP-native 宿主使用
- `meegle-rdhs-diagnosis`：给业务线负责人与产研管理层使用，提供产研过程健康度（RDHS）实时体检与提分治理建议

它只负责对外分发，不是新的事实源。

## 安装 `meegle-cli`

先安装 CLI：

```bash
npm install -g @tingwillforever/meegle-cli
```

然后安装 CLI skill：

```bash
npx -y skills add https://github.com/tingwillforever/meegle-skills --skill meegle-cli -g -y
```

适用场景：

- 用户在本机通过 `meegle` CLI 访问私有化部署
- Agent 需要学习如何选择正确的 CLI 命令、SOP 和安全停点

首次实际使用前，先完成登录：

```bash
meegle auth login
```

## 安装 `meegle-rdhs-diagnosis`（产研过程健康度体检）

面向一线产研团队、业务线接口人及管理层，随时掌握各产品及全业务线最新产研过程健康状况：

```bash
npx -y skills add https://github.com/tingwillforever/meegle-skills --skill meegle-rdhs-diagnosis -g -y
```

适用场景：

- 业务负责人查询单品或业务线实时产研健康分（如“诊断讯飞智作”、“查看开放平台RDHS情况”）
- 了解短板扣分原因（如“为什么我这个产品分这么低”）
- 自动生成按角色分工的极简提分抓手行动卡片（如“怎么冲刺到70分达标”）

## 安装 `meegle-mcp`

如果你的宿主是业务方 Agent 平台，或能直接连接远端 `meegle-mcp` Server 的 MCP-native 客户端，安装 MCP skill：

```bash
npx -y skills add https://github.com/tingwillforever/meegle-skills --skill meegle-mcp -g -y
```

适用场景：

- 普通用户 -> 业务方 Agent 平台 -> 远端 `meegle-mcp`
- 宿主直接给 Agent 暴露 `preset.public` 与 canonical MCP skill

## Source Of Truth

公开 mirror 的 canonical source 仍分属两个 owning repository：

- `tingwillforever/meegle-cli` 中的 `skills/meegle-cli/`
- `tingwillforever/meegle-mcp` 中的 `skills/meegle-mcp/`

这个仓库只发布经过 review 的公开安装内容，不单独定义 CLI 或 MCP 语义。
