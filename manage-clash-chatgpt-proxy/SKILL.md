---
name: manage-clash-chatgpt-proxy
description: 在 Clash Verge Rev 或 Mihomo 中为 ChatGPT/OpenAI 流量建立、维护并验证独立代理组，使 GPT 流量与其他流量分开路由。当 Codex 需要创建或检查 ChatGPT 专用策略组、筛选专用节点、添加或移除节点名称排除条件、将 OpenAI 域名路由到独立代理组、持久化并重新加载配置、根据 Clash 日志诊断 GPT 路由故障，或确认独立代理组已经生效时使用。
---

# 为 ChatGPT 配置独立代理组

为 ChatGPT/OpenAI 流量建立并维护独立代理组，使 GPT 流量不与其他流量共用默认代理策略。安全管理相关路由，不得泄露订阅地址、代理凭据或控制器密钥。将配置增强文件视为持久化来源，将生成的 Mihomo 配置视为当前运行时输入。

## 修改前先检查

1. 定位正在运行的 Clash 或 Mihomo 应用及其数据目录。在 macOS 上优先检查以下常见位置：

   ```text
   ~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev
   ~/.config/clash
   ~/.config/mihomo
   ```

2. 优先使用 `rg`、`lsof` 以及限定范围的 `sed` 或 `awk` 执行只读检查。检查以下内容：

   - 从 `profiles.yaml` 确认当前配置 UID，以及关联的 `groups`、`rules`、`merge` 或 `script` 增强文件。
   - 从 `clash-verge.yaml` 或应用生成的配置确认实际生效的策略组与规则。
   - 从最新 Mihomo 日志确认真实路由记录和错误。
   - 从本地控制器端点确认实时代理组状态。

3. 不得打印完整代理定义或大段 YAML，避免暴露密码、UUID、订阅令牌或地址。只输出节点名称、组类型、当前节点、路由规则、测试设置、数量，以及用户明确要求的脱敏服务器信息。

4. 分开报告配置状态与实时状态。尽可能通过控制器 API 确认当前节点；控制器不可用时，再结合持久化的 `selected.now` 和近期日志记录进行判断，例如：

   ```text
   using ChatGPT自动[节点名称]
   ```

## 区分配置层次

在 Clash Verge Rev 中区分以下层次：

- `profiles.yaml`：选择当前远程配置，并引用对应的增强文件。
- `profiles/<groups-uid>.yaml`：持久保存自定义策略组定义。修改此文件以保留策略组变更。
- `profiles/<rules-uid>.yaml`：持久保存自定义 ChatGPT/OpenAI 路由规则。
- `clash-verge.yaml`：保存 Mihomo 当前加载的生成配置。应用未自动重新生成配置时，更新并重新加载此文件以立即生效。
- Mihomo 控制器：读取并验证实际内存中的策略组状态。

不要只修改 `clash-verge.yaml` 来实现持久化；订阅刷新或配置切换可能覆盖它。用户要求立即生效时，也不要只修改增强文件；当前 Mihomo 进程可能仍在使用旧的生成配置。

## 建立 ChatGPT 独立代理组

优先复用现有的 ChatGPT 专用策略组；不存在时创建独立的自动测速组。除非用户要求修改，否则保留现有专用组的名称和设置。不要让 ChatGPT/OpenAI 规则回退到日常流量使用的默认策略组。典型配置如下：

```yaml
- name: ChatGPT自动
  type: url-test
  include-all-proxies: true
  exclude-filter: '香港|台湾|澳门|剩余|套餐|流量'
  url: 'https://www.gstatic.com/generate_204'
  interval: 300
  tolerance: 100
  lazy: true
```

创建或检查独立代理组时：

1. 确认 ChatGPT/OpenAI 域名规则全部指向该专用组。
2. 使用 `url-test` 自动选择可用节点，并确保组内至少保留一个候选节点。
3. 将 `exclude-filter` 解释为针对代理名称匹配的正则表达式。明确说明：匹配的节点只会从此策略组排除，在其他策略组中仍然可用。
4. 将策略组定义写入增强文件，使订阅刷新后仍能恢复。

添加排除条件时：

1. 读取现有表达式。
2. 添加用户要求的备选项，不得删除原有条件。
3. 必要时在修改前统计并列出匹配的节点。
4. 修改所引用的策略组增强文件，保证变更持久化。
5. 仅在应用未自动重新生成配置时更新生成配置，使修改立即生效。
6. 重新加载 Mihomo，并确认实时策略组的候选列表中不再出现被排除的名称。

除非用户明确要求，否则不要把自动 `url-test` 组改成手动 `select` 组。请求与节点测试行为无关时，保留健康检查地址和时间设置。

## 配置路由规则

将 ChatGPT/OpenAI 规则集中放在自定义规则列表靠前的位置，并全部指向独立代理组，使其优先于范围更广的兜底规则。保留现有规则，只在确有需要时添加域名。现有配置中常见的规则包括：

```yaml
- DOMAIN-SUFFIX,chatgpt.com,ChatGPT自动
- DOMAIN-SUFFIX,openai.com,ChatGPT自动
- DOMAIN-SUFFIX,oaistatic.com,ChatGPT自动
- DOMAIN-SUFFIX,oaiusercontent.com,ChatGPT自动
- DOMAIN-SUFFIX,oaistatsig.com,ChatGPT自动
```

扩展域名集合前，先检查用户当前的流量和日志。不得擅自将无关 AI 服务或全部流量重定向到 ChatGPT 策略组。

## 安全应用修改

1. 保留无关的用户修改，只做最小文本变更。避免使用会重新排列整个订阅配置的 YAML 序列化工具。
2. 目标位于可写沙箱之外时：
   - 将目标复制到可写位置中名称唯一的临时文件。
   - 使用 `apply_patch` 修改暂存副本。
   - 展示不含凭据的局部差异。
   - 将暂存文件复制回原位置前请求授权。
3. 覆盖重要的持久化源文件前，在没有其他恢复方式时先创建备份。
4. 不得在工作区交付物、回复、日志、命令输出或 skill 资源中写入密钥。
5. 验证成功后移除临时暂存副本。

## 重新加载并验证

从生效配置中读取 `external-controller-unix`、`external-controller` 和 `secret`，但不得打印 `secret`。存在本地 Unix 控制器时优先使用它。

使用控制器执行以下操作：

- 请求 `GET /proxies/<URL-encoded-group-name>`，检查 `type`、`now`、`all` 和候选节点数量。
- 使用生成配置路径请求 `PUT /configs?force=true`，热加载即时修改。

只在授权请求头中传递控制器密钥。不得将密钥硬编码到 skill 或显示在终端输出中。沙箱阻止访问本地套接字时，请求范围明确的执行授权，不要绕过控制器。

重新加载后验证以下全部项目：

- 持久化增强文件包含所需修改。
- 生成的生效配置包含相同修改。
- 实时策略组中不存在匹配新增排除条件的候选节点。
- 策略组仍有可用候选节点，且当前节点不为空。
- 近期 ChatGPT/OpenAI 日志使用预期策略组，并且没有重复连接失败。

重新加载或重新测速时，`url-test` 组可能自动切换节点。报告新的当前节点和候选数量变化，不要把自动切换误判为失败。

控制器不可用时，说明持久化修改已经完成，但仍需重新应用配置或重启应用才能立即生效。重启会短暂中断代理连接，因此执行前先征得用户同意。

## 报告结果

只总结以下内容：

- 修改了哪个策略组或哪些规则。
- 持久化配置、生成配置和实时状态是否一致。
- 修改前后的候选节点数量。
- 当前节点名称。
- 相关的超时或路由警告，但不得包含凭据或订阅详情。
