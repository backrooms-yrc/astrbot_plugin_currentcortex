# 贡献指南

感谢你关注 CurrentCortex！无论是提 Issue、修 Bug 还是加新功能，都欢迎参与。

💬 **QQ 交流群：1106353813** —— 部署问题、玩法讨论、开发意向都可以先进群聊，大改动建议先开 Issue 或群里对齐再动手，避免白干。

---

## 开发环境准备

1. **前置要求**：Python 3.10+、AstrBot `>=4.15,<5`（见 `metadata.yaml`）
2. **部署 AstrBot**：参照 [AstrBot 官方文档](https://astrbot.app)，UV / Docker / 源码均可
3. **放入插件目录**：把本仓库克隆 / 软链接到 AstrBot 的插件目录，目录名保持 `astrbot_plugin_currentcortex`：

   ```bash
   cd AstrBot/data/plugins
   git clone https://github.com/<你的用户名>/astrbot_plugin_currentcortex.git
   ```

4. **安装依赖**（AstrBot 通常会自动安装，手动补装也可以）：

   ```bash
   pip install -r requirements.txt
   ```

5. 在 AstrBot WebUI 的插件管理页**重载插件**即可让改动生效；`main.py` 之外的模块改动重载同样会生效，个别情况重启 AstrBot 更彻底。

> ⚠️ 本插件多数功能依赖 [LeiZ API](https://api.bileizhen.top)（统一 `x-api-key` 鉴权），没有 Key 时相关命令会提示未配置，不影响其他模块调试。

## 项目结构速览

| 模块 | 职责 |
| --- | --- |
| `main.py` | 插件主入口：命令注册、LLM 工具、分段回复 |
| `clients/` | API 客户端子包：Pixiv / 一言 / 天气 / 男娘 / 点歌 / 命令解析 |
| `dglab/` | DG-LAB（郊狼）子包：协议客户端（V3/V4 自动识别）、连接池、命令、WebUI、各类存储 |
| `media/` | 媒体解析子包：小红书 / B站 / 抖音 / 微博 链接解析 |
| `group/` | 群聊子包：跨群聊记忆、按群聊开关 |
| `_pages_api.py` / `pages/` | AstrBot WebUI 集成的 Pages 总面板 |
| `tests/` | 独立测试脚本（无需测试框架，新增需登记 `.gitignore` 白名单） |
| `_conf_schema.json` | 配置面板模式定义（新增配置项必须同步这里） |
| `metadata.yaml` | 插件元数据（版本号在此修改） |

## 测试

仓库采用可直接运行的独立测试脚本，无需测试框架：

```bash
python3 tests/test_dglab_protocol.py    # DG-LAB V3/V4 协议端到端（mock 服务端）
python3 tests/test_reply_seg.py         # 语义分段回复
python3 tests/test_music_audio.py       # 点歌音频
```

**注意**：`.gitignore` 默认忽略 `tests/test_*.py`（防止误提交带内网信息的临时脚本），采用白名单机制收录正式测试。**新增测试文件时，记得在 `.gitignore` 追加一行 `!tests/test_xxx.py`**，否则不会被纳入版本管理。

改到哪个模块，就把对应测试（以及受影响的其他测试）跑一遍再提交。

## 提交规范

沿用现有历史的格式：`类型(范围): 中文简要描述`，例如：

```
fix(dglab): 适配官方中转 V3/V4 协议并自动识别
feat(reply-seg): 分段数量上限 slider 从 10 扩到 99
docs: 更新贡献指南
chore: 版本号升至 v2.0.0
```

常用类型：`feat` / `fix` / `docs` / `chore` / `refactor` / `style` / `test` / `security`。范围（scope）可省略，建议写明受影响的模块。

## 提交 PR 流程

1. Fork 本仓库并创建特性分支（如 `fix/dglab-v4-timeout`）
2. 完成改动并自测（见上文「测试」一节与 PR 模板中的自测清单）
3. 提交 PR 到 `main` 分支，按模板填写改动说明
4. 涉及命令用法 / 配置项变更的，同步更新 `README.md` 与 `_conf_schema.json`
5. **有用户可见变更时，在 [CHANGELOG.md](CHANGELOG.md) 的 `[Unreleased]` 小节下追加条目**（格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，按 新增/变更/修复/移除 分类）
6. 若修复了某个 Issue，请在 PR 描述中写 `Fixes #编号`，合并后会自动关闭对应 Issue

### 代码风格约定

- 遵循现有文件的组织方式与中文注释习惯，**不做与本次目的无关的大范围重构**
- 新配置项必须同时补充 `_conf_schema.json` 的类型、默认值与人话描述
- 对外报错信息保持中文并附带可操作的建议（参考 `DGLabCommandError` 的写法）
- 涉及网络请求的逻辑注意超时与异常兜底，日志用 AstrBot 的 `logger`

## 提交 Issue

- **Bug 反馈** / **功能建议**请使用对应模板（仓库已配置 Issue Templates），重点是把**复现步骤**和**环境信息**写全
- 敏感信息（API Key、内网地址、QQ 号等）发帖前请自行打码
- DG-LAB 相关问题请附上 AstrBot 控制台的完整相关日志，以及中转服务器的协议版本（v2 / v3 / v4）

再次感谢你的贡献！🎉
