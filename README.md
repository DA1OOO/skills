# Skills

这是一个个人 Codex skills 仓库，用于保存可复用的操作流程、领域知识和安全约束。每个 skill 都放在独立目录中，并通过 `SKILL.md` 描述适用场景和执行步骤。

## Skill 列表

| Skill | 说明 |
| --- | --- |
| [`manage-clash-chatgpt-proxy`](./manage-clash-chatgpt-proxy/) | 为 ChatGPT/OpenAI 流量建立并维护独立代理组。 |
| [`guard-git-push-secrets`](./guard-git-push-secrets/) | 在每次 Git push 前扫描待推送提交中的敏感文件与凭据。 |

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

## guard-git-push-secrets

用于给 Git 仓库安装本地 `pre-push` hook，在每次普通 `git push` 前扫描本次要推送的全部提交。检查由本地规则执行，不调用大模型或外部服务；Skill 负责让 Codex 安装、更新、测试或卸载 hook。

主要能力：

- 检测 `.env`、Git 凭据文件、SSH 私钥、云服务凭据路径和私钥存储文件。
- 检测 GitHub、GitLab、AWS、Slack、Stripe、Google 与 SendGrid 等常见密钥格式。
- 检测密码、Token、API Key 等高熵赋值，同时忽略常见示例占位值。
- 扫描每个待推送提交中的 Git Blob；秘密即使在后续提交中被删除，也会被发现。
- 使用 `.git-sensitive-scan-allowlist` 为已确认的测试样本配置精确路径白名单。
- 保留并串联仓库已有的 `pre-push` hook，卸载时恢复原 hook。
- 发现风险或扫描失败时阻断 push，且不在输出中打印秘密原文。

让 Codex 安装到指定仓库：

```text
使用 $guard-git-push-secrets 给 /path/to/repository 安装 push 前敏感信息检查。
```

也可以直接运行安装器：

```bash
python3 ./guard-git-push-secrets/scripts/install.py --repo /path/to/repository
```

安装后照常运行 `git push` 即可自动检查。Git 的 `git push --no-verify` 会绕过所有 `pre-push` hook；该本地检查不能替代服务端秘密扫描或已经泄露凭据的轮换。

对于确认是虚假凭据的测试文件，在目标仓库根目录创建 `.git-sensitive-scan-allowlist`：

```text
# 每行一个仓库相对路径 glob
tests/fixtures/**
examples/demo.env
```

手动扫描指定提交范围：

```bash
python3 ./guard-git-push-secrets/scripts/scan_push.py \
  --repo /path/to/repository \
  --range origin/main..HEAD
```

卸载并恢复之前的 hook：

```bash
python3 ./guard-git-push-secrets/scripts/install.py \
  --repo /path/to/repository \
  --uninstall
```

## 目录结构

```text
skills/
├── .git-sensitive-scan-allowlist
├── README.md
├── guard-git-push-secrets/
│   ├── SKILL.md
│   ├── agents/
│   │   └── openai.yaml
│   └── scripts/
│       ├── install.py
│       ├── scan_push.py
│       └── self_test.py
└── manage-clash-chatgpt-proxy/
    ├── SKILL.md
    └── agents/
        └── openai.yaml
```

后续新增 skill 时，请在上方列表中补充名称和简要说明。
