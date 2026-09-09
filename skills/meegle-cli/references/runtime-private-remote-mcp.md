# Private Runtime: Installed CLI + Remote MCP

## 目录

- [Required runtime model](#required-runtime-model)
- [On-demand diagnostics](#on-demand-diagnostics)
- [Installation model](#installation-model)
- [安装包更新与提醒](#安装包更新与提醒)
- [Bootstrap](#bootstrap)

This repository's private deployment runtime is now:

- installed `meegle` CLI
- remote MCP Server
- SSO-backed session created by browser login or terminal QR login

It is not a local `stdio` / bundled `meegle-mcp` workflow.

## Required runtime model

- `meegle` installed from the published package
- built-in remote MCP endpoint, or an active profile override with `mcp_server_url`
- successful `meegle auth login`

## On-demand diagnostics

不要把 `meegle doctor --format json` 当成每次业务命令的固定前置。默认直接走业务命令；只有在以下情况再跑 `doctor`：

- 用户主动要求诊断
- 登录 / 认证 / 配置异常
- 业务命令报错但错误信息不足以定位根因
- `inspect --format json` 显示 `runtime_source != "live"`，或怀疑命令面漂移

```bash
meegle doctor --format json
```

重点看：

- `overall_status`
- `checks[].name == "runtime_source"`
- `checks[].name == "descriptor_drift"`
- `checks[].name == "live_descriptor"`

理想状态：

- `overall_status: ok`
- `runtime_source.status: ok`
- `runtime_source.details.runtime_source: "live"`
- `descriptor_drift.status: ok`

如果 `doctor` 显示：

- `runtime_source == "snapshot"`：当前 public runtime 仅适合只读诊断；不要继续执行业务命令
- `descriptor_drift != ok`：视为 CLI 与远端 public descriptor 漂移，先修复环境/发布链路
- `live_descriptor != ok`：先修复 runtime/auth/config，再继续业务命令

## Installation model

Typical private installation:

```bash
npm install -g @tingwillforever/meegle-cli
```

## 安装包更新与提醒

`meegle update` 只支持 npm 安装路径，会执行：

```bash
npm update -g @tingwillforever/meegle-cli
```

直接运行的裸 Go 二进制不会自我替换。npm launcher 在普通命令启动时会按 24 小时
节流规则后台检查 npm latest；新版本提醒只写 `stderr`，状态保存在
`~/.meegle/update-state.json`，检查失败静默且不应阻塞业务命令。若脚本或 Agent
需要稳定的 JSON/NDJSON `stdout`，可设置 `MEEGLE_CLI_NO_UPDATE_NOTIFIER=1` 关闭
自动检查和提醒；该变量不影响显式 `meegle update`。

如果当前 `meegle` 是手工安装的裸 Go 二进制，并且普通 npm 安装因同名 bin 文件报
`EEXIST`，只需执行一次：

```bash
npm install -g --force @tingwillforever/meegle-cli
```

迁移后再使用 `meegle update`；不要把裸 Go 二进制和 npm launcher 混装在同一个 bin 路径。

## Bootstrap

Default local acceptance:

```bash
meegle auth login
meegle auth status
```

For an SSH host or terminal server without a browser:

```bash
meegle auth login --qr
meegle auth status --format json
meegle auth whoami --format json
```

`--qr` renders the i讯飞 QR payload in the terminal and never launches a client browser.
Do not substitute `--device-code`: that flag remains standard OAuth Device Authorization
Grant and is unsupported by the private remote MCP endpoint.

Expected login outcomes:

- `Login successful`: remote MCP session is ready for business commands
- `No project membership found`: SSO passed, but the account is not a role-owner on any project-management work item in the configured space

In the `no project membership` case, ask an administrator to add the account to the relevant project-management work item's role members, then retry `meegle auth login`.

Temporary endpoint override:

```bash
meegle auth login --mcp-server-url https://mcp.example.com/mcp
```
