# Skills

这是一个个人 Codex skills 仓库，用于保存可复用的操作流程、领域知识和安全约束。每个 skill 都放在独立目录中，并通过 `SKILL.md` 描述适用场景和执行步骤。

## Skill 列表

| Skill | 说明 |
| --- | --- |
| [`manage-clash-chatgpt-proxy`](./manage-clash-chatgpt-proxy/) | 为 ChatGPT/OpenAI 流量建立并维护独立代理组。 |

## manage-clash-chatgpt-proxy

用于在 Clash Verge Rev 或 Mihomo 中为 ChatGPT/OpenAI 流量建立独立代理组，让 GPT 流量与日常流量分开路由，同时避免泄露订阅地址、代理凭据和控制器密钥。

主要能力：

- 为 ChatGPT/OpenAI 流量创建或维护单独的自动代理组，与其他流量使用的代理策略分离。
- 将 ChatGPT/OpenAI 相关域名统一路由到该独立代理组。
- 筛选、测速并排除不适合 GPT 的节点。
- 将独立代理组和路由规则持久化，避免订阅更新后丢失。
- 重新加载配置，并通过控制器与日志确认 GPT 流量确实经过独立代理组。
- 在操作过程中保护订阅令牌、代理密码与控制器密钥。

调用示例：

```text
使用 $manage-clash-chatgpt-proxy 为 ChatGPT/OpenAI 流量建立独立自动代理组，并确认路由已经生效。
```

```text
使用 $manage-clash-chatgpt-proxy 把香港节点排除出 ChatGPT 自动测速组，并确认配置已经生效。
```

## 目录结构

```text
skills/
├── README.md
└── manage-clash-chatgpt-proxy/
    ├── SKILL.md
    └── agents/
        └── openai.yaml
```

后续新增 skill 时，请在上方列表中补充名称和简要说明。
