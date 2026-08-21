<div align="center">

<img src="logo.png" width="200" alt="CurrentCortex 综合插件"/>

# AstrBot CurrentCortex 综合插件

**一个多功能 AstrBot 插件** — 集内容获取、媒体解析、设备控制与跨群记忆于一体。

Pixiv 随机图片 · 每日一言 · 天气查询 · 男娘图片 · 网易云点歌 · 小红书/B站/抖音/微博解析 · DG-LAB 设备管理 · 跨群聊记忆 · LLM 工具（AI 自主调用）· 语义分段回复

[![Release](https://img.shields.io/github/v/release/backrooms-yrc/astrbot_plugin_currentcortex.svg?style=flat-square)](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/releases)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.15%20%3C5-5865F2.svg?style=flat-square)](https://github.com/AstrBot)
[![Stars](https://img.shields.io/github/stars/backrooms-yrc/astrbot_plugin_currentcortex.svg?style=flat-square&label=Stars)](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/stargazers)
[![QQ 群](https://img.shields.io/badge/QQ%E7%BE%A4-1106353813-0099FF.svg?style=flat-square&logo=tencentqq&logoColor=white)](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)

**[💬 加入交流群](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)** ·
**[🚀 快速开始](#-快速开始)** ·
**[⚙️ 配置项](#️-配置项)** ·
**[📜 更新日志](CHANGELOG.md)** ·
**[🤝 贡献指南](#-贡献指南)**

🇨🇳 [简体中文](README.md) · 🇬🇧 [English](README_EN.md) · 🇯🇵 [日本語](README_JA.md) · 🇹🇼 [繁體中文](README_ZH-TW.md)

</div>

---

> [!IMPORTANT]
> **🔒 使用本插件前，请务必加入官方 QQ 群**
>
> **所有用户请务必加入官方 QQ 群 1106353813**（[点击加入](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)）。
>
> - **更新与紧急公告**：版本更新、上游接口/协议变动、故障通知均在群内第一时间发布
> - **问题反馈**：遇到 bug 直接在群里 @维护者，跟进速度远快于 GitHub Issues
> - **使用答疑**：开发者与热心群友常驻答疑，欢迎交流使用心得
>
> 入群后请先阅读群公告。未加群的用户遇到问题时可能无法获得及时支持。

> [!NOTE]
> **📢 紧急招募：DG-LAB 远控功能急缺真机测试志愿者**
>
> DG-LAB（郊狼）**远控功能目前缺少真机测试，急需志愿者参与实测**——没有真实设备反馈，bug 只能盲修、迭代只能停滞。如果你手头有 **郊狼脉冲主机 3.0**，请务必加入官方群参与测试：
>
> - **测试内容**：设备绑定 · 远程控制指令 · CCDG WebUI 控制面板 · 中转服务器部署（V3 / V4 协议）
> - **参与方式**：加入官方 QQ 群 **1106353813**（[点击加入](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)），入群说明来意或直接 @维护者
> - **测试反馈**：问题第一时间跟进修复，贡献者记入更新日志致谢
>
> 没有设备的朋友也欢迎进群围观，或帮忙转发扩散 🙏

> [!IMPORTANT]
> **🙏 致歉信——DG-LAB 协议适配迟到的两个多月**
>
> 各位使用 DG-LAB(郊狼)功能的用户:
>
> 官方中转服务端在今年 5~7 月间迁移到了 v3 / v4 协议(6月2日 旧版 v2 服务端从官方仓库移除)。这期间使用新中转的用户一直无法正常绑定设备(报 `等待服务器分配 clientId 超时` 或 `HTTP 404`),**这是我跟进上游变更不及时的失误——没有主动关注官方仓库的动向,直到 8月13日 [#3](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues/3) 有用户反馈才发现问题,让大家等了两个多月。对此真诚地向各位道歉。**
>
> 问题已在 [v2.0.0](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/releases/tag/v2.0.0) 彻底修复:协议客户端重写为 V3 / V4 自动识别(旧 v2 中转同样兼容),无需改任何配置,升级即用;v4 中转需使用 **DG-LAB 4 APP** 扫描新版二维码,详见 [DG-LAB 章节](#7-dg-lab-设备管理--dglab-别名电击)。
>
> 为避免同类问题再次发生,我已订阅上游仓库的变更通知,并为本模块补上了 36 个协议回归测试——今后官方协议再有调整,可以第一时间跟进、不再依赖用户报障。再次感谢 issue #3 的反馈,也感谢大家的包容。
>
> —— Rcst20 · 2026年8月15日

---

> 💬 **插件官方QQ交流群**：**1106353813**，[点击跳转](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)
>
> 欢迎加入！在这里可以获取更新通知、反馈问题与建议、交流使用心得，开发者也会在群内答疑。
> 遇到 bug 或有新功能想法，也可以直接在群里 @ 维护者，或到 [Issues](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues) 提交。
>
> ⚠️ **本群是 CurrentCortex 插件的社区交流群，与 [LeiZ API](https://api.bileizhen.top) 官方无关**。本插件是基于 LeiZ API 开发的**社区（第三方）插件**，LeiZ API 的注册、Key 获取、接口计费、故障等问题请到 LeiZ API 官网及其官方渠道咨询，勿在本群反馈。

---

## 📋 目录

- [✨ 核心特性](#-核心特性)
- [🚀 快速开始](#-快速开始)
- [🎯 功能详解](#-功能详解)
  - [1. Pixiv 随机图片](#1-pixiv-随机图片--pixiv-别名图片)
  - [2. 媒体内容解析](#2-媒体内容解析--解析-别名小红书b站抖音)
  - [3. 网易云音乐](#3-网易云音乐--music-别名音乐)
  - [4. 每日一言](#4-每日一言--hitokoto-别名一言)
  - [5. 天气查询](#5-天气查询--weather-别名天气)
  - [6. 男娘图片](#6-男娘图片--femboy-别名男娘)
  - [7. DG-LAB 设备管理](#7-dg-lab-设备管理--dglab-别名电击)
- [🖥️ 总 Pages](#️-总-pages)
- [🧩 按群聊开关](#-按群聊独立开关)
- [✂️ 分段回复](#️-分段回复)
- [🤖 LLM 工具](#-llm-工具)
- [🧠 跨群聊记忆](#-跨群聊记忆)
- [⚡ 接口连通性测试](#-接口连通性测试--apitest)
- [⚙️ 配置项](#️-配置项)
- [❓ 常见问题](#-常见问题)
- [🛠️ 技术架构](#️-技术架构)
- [🤝 贡献指南](#-贡献指南)
- [📄 开源协议与致谢](#-开源协议与致谢)

---

## ✨ 核心特性

| 模块 | 能力 |
| --- | --- |
| 🎨 **Pixiv 随机图片** | 随机图 / R18 / 标签筛选 / 关键词搜索 / 指定作者 / 长宽比筛选 / 排除 AI |
| 🔍 **媒体解析** | 小红书图文视频 · B站视频信息 · 抖音无水印视频 · 微博图文视频 |
| 📚 **媒体内容解析** | 小红书 / B站 / 抖音 / 微博链接解析 |
| 🎵 **网易云点歌** | 点歌、搜索、语音条、原始文件、按 ID 获取 |
| ✨ **每日一言** | 12 种分类（动画/漫画/游戏/文学/诗词/影视…） |
| 🌤️ **天气查询** | 实时天气 + 未来 3 天预报 |
| 👗 **男娘图片** | 随机男娘主题图片（WebP） |
| 🔌 **DG-LAB** | Socket V3/V4（兼容旧 V2）设备全生命周期管理、协议自动识别、多用户/多设备隔离、CCDG WebUI 控制面板 |
| 🖥️ **总 Pages** | AstrBot WebUI 集成总面板：仪表板 · 帮助中心 · 可视化设置（保存即热重载）· 郊狼控制（中转服务器一键部署 · 公网暴露开关）· 联系我们 |
| 🧩 **按群聊开关** | 在单个群用 `/开关` 命令关闭/开启本插件全部命令（支持限时关闭自动恢复、按功能域分级），互不影响 |
| 🧠 **跨群聊记忆** | 同平台所有群共享一份持久化上下文，自动注入 LLM 请求（可按时效过滤、LLM 摘要压缩、按关键词清理） |
| ✂️ **分段回复** | 把机器人回复拆成多条消息分次发送，模拟逐条回复。支持标点/长度/LLM 语义三种分段模式 |
| 🤖 **LLM 工具** | 把图片获取/点歌/电击控制注册为 AI 可调用工具（function calling），AI 能自主响应自然语言请求 |

- **⚡ 异步高性能**：基于 `asyncio` + `aiohttp` / `websockets`，非阻塞 I/O。
- **🛡️ 健壮容错**：网络异常、API 错误、参数错误均有友好提示；点歌带指数退避重试。
- **⚙️ 灵活配置**：所有默认参数均可在 AstrBot 管理面板自定义。
- **👥 多租户隔离**：DG-LAB 每个用户/每台设备连接与操作完全隔离。

---

## 🚀 快速开始

### 1. 安装

**方式一：插件市场（推荐）** — 在 AstrBot 管理面板搜索 `astrbot_plugin_currentcortex` 安装。

**方式二：手动克隆：**

```bash
cd AstrBot/data/plugins
git clone https://github.com/backrooms-yrc/astrbot_plugin_currentcortex.git
```

### 2. 配置 API Key（必填）

> 🔐 **LeiZ API 鉴权要求**：自最新版本起，**所有接口（含免费接口）均需携带 API Key**，请求头格式为 `x-api-key: <API-Key>`。

#### 第一步：获取 API Key

前往 **LeiZ API 官网** 👉 [https://api.bileizhen.top](https://api.bileizhen.top)

在官网注册/登录后，进入「控制台 / API Keys」页面创建并复制你的 API Key（即 `x-api-key` 的值）。该 Key 为所有 LeiZ 接口（Pixiv / 一言 / 天气 / 男娘 / 网易云）统一使用，只需一个。

> 💡 具体申请位置以官网页面为准（如「控制台 → API Keys / 令牌管理」）。若官网流程有变动，以官网说明为准。

#### 第二步：填入插件配置

打开 AstrBot 管理面板 → 插件管理 → 本插件 → 配置，把上一步获取的 Key 填入 **`leiz_api_key`** 字段，保存后重启插件。

未配置时，Pixiv / 一言 / 天气 / 男娘 / 点歌 等全部 LeiZ 接口命令将不可用，调用时会给出配置引导提示。

> ⚠️ **本插件是基于 LeiZ API 的社区（第三方）插件，与 LeiZ API 官方相互独立**。API Key 的注册/获取、接口计费、额度、上游故障等问题请到 [LeiZ API 官网](https://api.bileizhen.top) 及其官方渠道咨询；本插件的交流群仅处理插件本身的使用问题。

> **旧版迁移**：v1.3.x 及更早版本的 `femboy_api_key` 已合并为统一的 `leiz_api_key`。若未填新字段但保留了旧字段，插件会自动作为统一 Key 使用并提示迁移，建议尽快改填到 `leiz_api_key`。

### 3. 安装依赖

```bash
pip install aiohttp>=3.8.0
pip install websockets>=10.0   # 仅 DG-LAB 功能需要
```

### 系统要求

- **AstrBot** >= 4.15（< 5；使用 `EventMessageType` / 处理器 `priority` / `ProviderRequest` 等较新 API）
- **Python** >= 3.10
- **aiohttp** >= 3.8.0
- **websockets** >= 10.0（DG-LAB 功能必需）
- **ffmpeg**（网易云语音条功能需要，需在系统 PATH 中）

---

## 🎯 功能详解

> 💡 在聊天中发送 **`/cc`** 或 **`/cc help`** 可查看全部命令的分类总览图片。

### 指令速查表

所有指令均支持中英文别名：

| 指令 | 别名 | 功能 |
| --- | --- | --- |
| `/pixiv` | `/图片` | Pixiv 随机图片 |
| `/解析` | — | 自动识别平台解析媒体链接 |
| `/xhs` | `/小红书` | 小红书解析 |
| `/bilibili` | `/B站` `/b站` | B站视频解析 |
| `/douyin` | `/抖音` | 抖音视频解析 |
| `/weibo` | `/微博` | 微博帖子解析 |
| `/music` | `/音乐` | 音乐点歌（网易云/酷狗） |
| `/点歌` | — | 快捷点歌（仅语音条） |
| `/音源` | — | 切换点歌音源（auto/网易云/酷狗） |
| `/hitokoto` | `/一言` | 每日一言 |
| `/weather` | `/天气` | 天气查询 |
| `/femboy` | `/男娘` | 男娘图片 |
| `/dglab` | `/电击` | DG-LAB 设备管理 |
| `/开关` | `/toggle` `/switch` | 按群聊开关本插件全部命令（支持限时、按功能域分级） |
| `/开关列表` | `/switch_list` `/开关状态列表` | 查看本平台被关闭的群与功能域（管理员） |
| `/忘记` | `/forget_memory` `/忘记记忆` | 按关键词清理跨群聊记忆（管理员） |
| `/帮助` | `/cc` `/help` `/菜单` | 插件功能总览 |
| `/apitest` | `/连通测试` `/接口测试` | 接口连通性测试 |

---

### 1. Pixiv 随机图片 (`/pixiv`，别名 `/图片`)

通过 LeiZ API 获取随机 Pixiv 图片，支持丰富的筛选与搜索。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/pixiv` | 获取一张随机图片（按默认参数） |
| `/pixiv help` | 显示帮助 |

#### 参数说明（`key:value` 格式，空格分隔，可自由组合）

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `r18:` | int | 0 | R18 模式：`0`=全年龄、`1`=仅 R18、`2`=混合 |
| `num:` | int | 1 | 获取数量（1-20） |
| `size:` | string | regular | 图片尺寸：`original`/`regular`/`small`/`thumb`/`mini` |
| `tag:` | string | — | 标签筛选；单个 tag 内用 `\|` 为 **OR**，多个 tag 参数为 **AND** |
| `keyword:` | string | — | 标题 / 作者 / 标签模糊搜索 |
| `uid:` | int | — | 指定作者 UID |
| `ratio:` | string | — | 长宽比筛选，如 `gt1.2lt1.8` |
| `excludeAI:` | bool | false | 排除 AI 生成作品 |

#### 快捷语法

| 快捷词 | 等同于 |
| --- | --- |
| `r18` | `r18:1` |
| `mixed` | `r18:2` |
| `safe` / `sfw` | `r18:0` |

#### 使用示例

```text
# 基础随机
/pixiv                          # 随机全年龄图片
/pixiv r18:1                    # 随机 R18 图片
/pixiv num:5                    # 一次获取 5 张

# 标签与关键词搜索
/pixiv tag:白丝 num:3           # 获取 3 张白丝图
/pixiv keyword:初音ミク num:5   # 搜索初音未来相关
/pixiv tag:萝莉 excludeAI:true  # 排除 AI 的萝莉标签
/pixiv uid:123456 num:3         # 指定作者作品

# 组合筛选
/pixiv r18:2 tag:白丝 keyword:初音ミク num:3 size:original

# 快捷语法
/pixiv r18                      # 等同 r18:1
/pixiv mixed                    # 等同 r18:2
```

#### 返回示例

```text
📷 [1/3]
🎨 冬日午后
👤 作者：SampleArtist
🔗 https://www.pixiv.net/artworks/12345678
🏷️ 标签：オリジナル / 女の子 / 冬 / 雪
📐 尺寸：1920×1080
[图片]
```

> 💡 **随机与搜索的路由**：未提供 `tag`/`keyword`/`uid`/`ratio`/`excludeAI` 等过滤参数时，走 GET 随机接口（每次结果不同）；提供任一过滤参数时自动切换到 POST 筛选接口。

---

### 2. 媒体内容解析 (`/解析`，别名 `/小红书` `/B站` `/抖音`)

自动识别平台并解析小红书、B站、抖音、微博的媒体链接，返回无水印图片 / 视频信息。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/解析 <链接>` | 自动识别平台并解析；**一条消息含多个链接时依次解析（最多 5 条）** |
| `/xhs <链接>`（`/小红书`） | 小红书解析 |
| `/bilibili <链接>`（`/B站` `/b站`） | B站视频解析 |
| `/douyin <链接>`（`/抖音`） | 抖音视频解析 |
| `/weibo <链接>`（`/微博`） | 微博帖子解析 |
| `/解析 help` | 显示帮助 |

#### 支持的链接格式

| 平台 | 支持格式 |
| --- | --- |
| 小红书 | `xiaohongshu.com/explore/xxx`、`xhslink.com/xxx`（短链） |
| B站 | `bilibili.com/video/BVxxx`、`b23.tv/xxx`（短链）、`avxxx` |
| 抖音 | `douyin.com/video/xxx`、`v.douyin.com/xxx`（短链） |
| 微博 | `weibo.com/数字/xxx`、`m.weibo.cn/detail/xxx`、`weibo.cn/status/xxx`、`t.cn/xxx`（短链） |

#### 使用示例

```text
/解析 https://www.xiaohongshu.com/explore/abc123
/解析 https://b23.tv/xxxx https://v.douyin.com/yyyy   # 批量：一条消息多个链接，依次解析
/xhs https://xhslink.com/xxxx
/bilibili https://www.bilibili.com/video/BV1xx411c7mD
/douyin https://v.douyin.com/xxxx
/weibo https://m.weibo.cn/detail/xxxxx
```

#### 返回信息

- **小红书**：标题、作者、点赞、简介、无水印高清原图、视频链接（如有）
- **B站**：标题、UP主、时长、播放/点赞、封面、分P信息、视频下载链接（如有）
- **抖音**：标题、作者、点赞/评论/分享、无水印视频链接
- **微博**：正文、作者、转发/评论/点赞数、配图（最多 9 张）、视频链接（如有）

> ⚠️ 请确保链接可公开访问；部分平台可能因反爬策略导致解析失败。下载链接仅供个人学习使用，请遵守平台规范。

#### 解析增强

- **失败原因分级提示**：解析失败不再甩原始异常文本，而是按原因分类提示——链接过期（短链失效）、内容已删除/私密、平台反爬拦截、网络超时、链接格式不识别等，便于判断是链接问题还是网络问题。
- **结果缓存**：相同链接在有效期内（默认 10 分钟，`media_parse_cache_ttl` 可调）直接返回上次解析结果，减少对目标平台的请求频率，降低触发反爬/封 IP 的概率；仅缓存成功结果，失败会实时重试。
- **联动跨群记忆**：跨群聊记忆开启时，解析成功会以 `media` 标签记录「谁解析了什么内容」，后续对话中机器人可以自然回溯「你刚才发的那个视频」。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `media_parse_cache_enable` | bool | true | 是否启用解析结果缓存 |
| `media_parse_cache_ttl` | int | 600 | 缓存有效期（秒）。下载/播放链接本身有时效性，不建议设置过长 |

---

### 漫画内容（原第 3 节，已移除）

> ⚠️ 因相关规定，本插件早期版本提供的漫画内容功能已于 **v2.0.4** 起整体移除，后续版本不再提供，感谢理解。

---

### 3. 音乐点歌 (`/music`，别名 `/音乐`)

通过 LeiZ API 实现点歌、搜索与播放链接获取，支持**网易云**与**酷狗**双音源，并提供 `auto` 自动路由（网易云优先，失败转酷狗）。

#### 音源切换 (`/音源`)

| 指令 | 说明 |
| --- | --- |
| `/音源` | 查看当前音源 + 可选项 |
| `/音源 auto`（自动） | **默认**。网易云优先，VIP/无版权/超时自动转酷狗 |
| `/音源 网易云` | 仅网易云 |
| `/音源 酷狗` | 仅酷狗 |

音源按**会话（群/私聊）记忆**，互不影响；重启后重置为默认（`music_default_source` 配置项，默认 auto）。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/music <歌曲名>`（`/音乐`） | 点歌（搜索并返回第一首的详细信息） |
| `/music direct <歌曲名>`（`/音乐 直接`） | 仅返回转码后的语音条 |
| `/点歌 <歌曲名>` | 快捷命令，等效 `/音乐 直接`，仅返回语音条 |
| `/music file <歌曲名>`（`/音乐 文件`） | 返回未经转码的原始音乐文件 |
| `/music id:<歌曲ID>`（`/音乐 编号:`） | 通过 ID 获取详细信息 |
| `/music search <关键词>`（`/音乐 搜索`） | 搜索歌曲列表 |
| `/music help` | 显示帮助 |

#### 使用示例

```text
/music 孤勇者              # 点歌
/music 周杰伦 晴天         # 搜索「周杰伦 晴天」
/music direct 孤勇者       # 仅返回语音条
/点歌 孤勇者               # 快捷命令
/music file 孤勇者         # 返回原始音频附件
/music id:1901371647       # 通过 ID 获取
/music search 陈奕迅       # 搜索歌曲列表
```

#### 返回信息

歌曲名称、艺术家、专辑、封面、音质（码率/格式/等级）、文件大小、播放链接。在 QQ 平台会自动将播放链接解析为**语音条**发送（依赖框架 `Record` 消息段；不支持时降级为文本链接）。

> ⚠️ 部分 VIP 歌曲可能无法获取播放链接；播放链接有时效性，请及时使用。语音条功能依赖系统 `ffmpeg`。

> 📦 **文件模式与大文件**：`/音乐 文件` 在 QQ/NapCat 下优先走 OneBot 本地上传（`upload_group_file` / `upload_private_file`），避免 `Comp.File` 经错误 `callback_api_base` 转成 HTTP 回调后被二次下载失败（日志常见「下载文件失败」）。原始音频（尤其无损 flac）体积可能很大；当文件超过 `music_file_max_bytes`（默认 25MB）时，插件会自动转码为 128kbps MP3 后再发送（需 `ffmpeg`），体积可缩小约 90%。如需发送原始无损文件，可在配置中调大该阈值（但不推荐，易发送失败）。下载侧对超时/网络错误会自动重试。

> 🚫 **防连点过载**：为避免用户短时间连点触发大量并发下载/转码拖垮服务器，点歌命令内置「进行中去重 + 冷却」（`music_cooldown`，默认 3 秒）。同一会话上一首还在处理时再次点歌会提示「请稍候」，刚点完立刻再点会提示「点得太快啦」。不同群/私聊互不影响。

---

### 4. 每日一言 (`/hitokoto`，别名 `/一言`)

获取来自社区贡献的随机一言。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/hitokoto` | 随机获取一言（全部分类） |
| `/hitokoto <分类代码>` | 指定分类 |
| `/hitokoto help` | 显示帮助 |

#### 分类选项

| 代码 | 分类 | 代码 | 分类 |
| --- | --- | --- | --- |
| a | 动画 | g | 其他 |
| b | 漫画 | h | 影视 |
| c | 游戏 | i | 诗词 |
| d | 文学 | j | 网易云 |
| e | 原创 | k | 哲学 |
| f | 来自网络 | l | 抖机灵 |

```text
/hitokoto a    # 获取动画类一言
/hitokoto i    # 获取诗词类一言
```

---

### 5. 天气查询 (`/weather`，别名 `/天气`)

实时查询城市天气及未来 3 天预报。

```text
/weather 广州市      # 查询广州天气
/weather 北京        # 查询北京天气
/weather help        # 显示帮助
```

支持中国主要城市，建议使用中文城市名（最长 50 字符）。返回当前温度/天气/体感/风力/湿度及未来 3 天预报。

---

### 6. 男娘图片 (`/femboy`，别名 `/男娘`)

随机获取男娘主题图片（WebP）。

```text
/femboy          # 随机男娘图片
/femboy help     # 显示帮助
```

> 使用前必须配置 `leiz_api_key`，详见 [快速开始](#2-配置-api-key必填)。

---

### 7. DG-LAB 设备管理 (`/dglab`，别名 `/电击`)

通过 DG-LAB Socket 协议实现对郊狼脉冲主机的完整控制。**需运行 [DG-LAB WebSocket 中转服务器](https://github.com/dungeonlab-open/dglab-websocket-server)**。

> 📡 **协议版本**：官方中转仓库已删除 v2 服务端，仅保留 **v3**（`bun run v3`，默认端口 9999）与 **v4**（`bun run v4`，默认端口 9998）。自 v2.0.0 起插件**自动识别**中转服务器协议（V3 / V4，并兼容存量旧 V2 中转），无需改配置即可直接使用；亦可通过 `dglab_protocol` 配置项手动指定（`auto` / `v3` / `v4`）。
>
> - **V3**：二维码格式与旧版一致，DG-LAB APP / DG-LAB 4 APP 均可扫码；
> - **V4**：使用新版二维码（`dungeon-lab.cn/s/?v=1&action=socket&url=...`），需 **DG-LAB 4 APP** 扫码；强度控制通过 `device.op` 任务下发（绝对强度按 APP 回传的当前值换算增量，无回传时退化为临时强度任务）。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/dglab bind [服务器地址]`（`绑定`） | 绑定新设备（生成二维码供 APP 扫描，支持多设备追加） |
| `/dglab unbind [序号]`（`解绑`） | 解绑设备（多台时需指定序号） |
| `/dglab strength [序号] <A\|B> <0-200>`（`强度`） | 设置通道强度（序号省略则操作 #1） |
| `/dglab up [序号] <A\|B> [步进]`（`增加`） | 增加强度（默认 +5） |
| `/dglab down [序号] <A\|B> [步进]`（`减少`） | 减少强度（默认 -5） |
| `/dglab shock [序号] <A\|B> [强度] [波形] [秒数]`（`开始`） | 开始电击 |
| `/dglab stop [序号] [A\|B]`（`停止`） | 停止电击（强度归零 + 清空波形） |
| `/dglab pulse [序号] <A\|B> <预设\|HEX> [秒数]`（`波形`） | 发送波形数据（默认 5 秒） |
| `/dglab clear [序号] <A\|B>`（`清空`） | 清空波形队列 |
| `/dglab feedback [序号]`（`反馈`） | 查看实时强度和反馈按钮状态 |
| `/dglab permission [on\|off]`（`权限`） | 查看/切换权限隔离（默认开启） |
| `/dglab status`（`状态`） | 查看全部设备绑定与连接状态 |
| `/dglab info`（`信息`） | 查看全部设备详细信息 |
| `/dglab help`（`帮助`） | 显示帮助 |

> 💡 **多设备**：同一用户可绑定多台设备，用序号（1/2/3…）区分，省略默认操作 #1。控制他人设备示例：`/dglab strength @用户ID 2 A 50`。

#### 波形预设

| 预设 | 效果 | 预设 | 效果 |
| --- | --- | --- | --- |
| `breathe` | 缓慢渐强渐弱 | `needle` | 高频持续尖刺 |
| `pulse` | 快速间歇脉冲 | `throb` | 低频缓慢起伏 |
| `wave` | 连续波浪起伏 | `chaos` | 强弱随机交替 |
| `tap` | 短促单次敲击 | `heartbeat` | 双拍心跳节奏 |

#### 使用流程

```text
1. 绑定设备
   /dglab bind ws://192.168.1.100:9999
2. 用 DG-LAB APP 扫描二维码完成绑定
3. 控制设备
   /dglab shock A 50 breathe 10   # A通道电击（强度50，呼吸波形，10秒）
   /dglab strength A 50           # 仅设置A通道强度
   /dglab pulse A wave 5          # 发送波浪波形5秒
   /dglab up B 10                 # B通道强度+10
   /dglab stop                    # 停止所有输出
4. 查看状态
   /dglab status
   /dglab feedback
5. 解绑（可选）
   /dglab unbind
```

#### CCDG WebUI 控制面板

启用 `dglab_webui_enabled` 后，插件会在 `dglab_webui_host`:`dglab_webui_port`（默认 `127.0.0.1:9178`）启动一个 CCDG WebUI 浏览器远程控制界面，可在网页上查看/控制设备，Material Design 3 风格。

> ⚠️ **CCDG WebUI 安全（重要）**
> - 自 v1.5.3 起，**WebUI 默认关闭**（`dglab_webui_enabled` 默认 `false`），需手动开启。
> - 默认监听地址为 `127.0.0.1`（仅本机访问）。**如需公网访问，请将 `dglab_webui_host` 显式设为 `0.0.0.0`，并务必在前面部署反向代理与访问控制**（如 Nginx + Basic Auth / IP 白名单）。
> - 也可以直接在 **总 Pages → 郊狼控制** 里用「暴露公网」开关一键切换 `127.0.0.1` / `0.0.0.0`（带二次确认与公网链接展示；打开时自动 `ufw` 放行端口，关闭/停用 WebUI 时自动收回放行）。
> - WebUI 内置独立的用户注册/登录系统，**与机器人本体/平台账号无关**：任何能访问该端口的人都能注册账号。不要在无防护的情况下直接暴露到公网。
> - 建议仅在本机使用，或仅在内网/经反代+鉴权后对外提供。

#### 高级特性

- **多用户隔离**：每个用户独立连接与绑定，互不影响，支持最多 50 个并发连接。
- **自动重连**：操作失败自动重试（最多 2 次）；连接断开尝试重建；空闲超 5 分钟自动清理。
- **安全机制**：所有参数严格校验，操作超时保护，强度限制 0-200。

> ⚠️ 仅支持**郊狼脉冲主机 3.0**；二维码在会话期间有效，超时需重新生成；建议局域网用 `ws://`，公网用 `wss://`。

---

## 🖥️ 总 Pages

> 自 **v1.9.0** 起，插件集成了 AstrBot 插件 Pages 总面板（mdui 2 Material Design 3 风格，晴空蓝 + 雪雾白）。在 AstrBot WebUI 的 **插件详情 → Pages**（或侧边栏「插件 Pages」分组）中打开。

总面板共 5 个页面：

| 页面 | 说明 |
| --- | --- |
| 📊 **仪表板** | 插件运行总览：运行时长、已绑定设备、活跃连接、注册用户、插件版本/作者/启动时间、功能开关状态 |
| 📖 **帮助中心** | 内置使用文档与常见问题（快速开始 / 郊狼 / 分段回复 / 跨群记忆 / 故障排查） |
| ⚙️ **设置** | 可视化修改全部插件配置：每个配置项都有中文名 + 人话解释，保存后**自动热重载**生效，无需手动重启 |
| ⚡ **郊狼控制** | 中转服务器一键部署（v3/v4 · 暴露公网开关）+ CCDG WebUI 总开关 + **暴露公网开关**（见下） |
| 💬 **联系我们** | 开发者信息、GitHub 仓库、QQ 交流群（一键加群） |

#### 郊狼控制：公网暴露开关

- **WebUI 总开关**：仅启用 CCDG WebUI，监听保持 `127.0.0.1`（仅本机可访问，**不算暴露公网**）。
- **暴露公网开关**（需先启用 WebUI）：打开后自动把 `dglab_webui_host` 改为 `0.0.0.0`（端口 `dglab_webui_port`，默认 `9178`），探测本机公网 IP 并展示公网跳转链接；关闭后自动改回 `127.0.0.1`。
- 打开暴露前会弹出**二次确认**，并持续显示安全警告；关闭 WebUI 总开关时也会自动把监听地址清理回 `127.0.0.1`，避免残留暴露配置。

> ⚠️ **安全提醒**：监听 `0.0.0.0` 意味着公网任意地址都能访问 WebUI 的注册 / 登录 / 设备接口。暴露公网前请务必先配置**反向代理 + 鉴权**（如 Caddy + BasicAuth、Nginx + IP 白名单、Cloudflare Zero Trust），否则任何人都有可能控制你的郊狼设备。

#### 郊狼控制：中转服务器一键部署（v3/v4）

郊狼控制页可直接在服务器上**一键部署官方 v3 / v4 中转服务器**（[dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server)，Bun 运行时），无需命令行操作：

- **自动检测**：v3（端口 9999）与 v4（端口 9998）各自独立检测部署状态；已部署的显示运行状态、systemd 服务名、源码版本，并支持一键卸载（历史手工部署的服务也能被识别接管）
- **一键部署**：自动完成 安装 Bun → 克隆官方仓库 → 写配置 → 装依赖 → 创建 systemd 常驻服务（开机自启、崩溃自动拉起）→ 协议自检，全程约 10~60 秒
- **暴露公网开关**（默认关闭）：官方服务端监听地址固定为全接口，「本机/公网」可达性由防火墙控制——开关关闭时端口不放行（仅本机 `ws://127.0.0.1:端口` 可达，页面显示本机地址）；开启时自动放行端口（ufw）并探测显示公网地址 `ws://公网IP:端口`，关闭时自动收回。放行前有二次确认
- **卸载**：停止并删除 systemd 服务、收回防火墙放行；源码目录保留，重新部署秒级完成

> ⚠️ **安全提醒**：放行中转端口后，任何获得地址的 DG-LAB APP 都可以接入该中转，建议仅在使用期间开启、用完关闭。部署/卸载依赖 systemd 与 ufw（AstrBot 需以 root 运行）。

---

## 🧩 按群聊独立开关

每个群聊可独立控制本插件是否生效，互不影响。例如某个群不需要图片/点歌等功能时，可单独关闭它，而其它群不受影响。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/开关 off`（或 `/开关 关`） | **永久关闭**本群全部插件命令（pixiv/解析/music/… 均不再响应） |
| `/开关 off <时长>` | **限时关闭**，到期自动恢复。如 `/开关 off 2h`、`/开关 off 30m`、`/开关 off 1d`、`/开关 off 2小时30分钟` |
| `/开关 off <功能域> [时长]` | **只关某一类功能**，其余功能不受影响。如 `/开关 off media 2h` 只关媒体解析 2 小时 |
| `/开关 on`（或 `/开关 开`） | **重新启用**本群插件命令（限时关闭也可提前手动恢复） |
| `/开关 on <功能域>` | 单独恢复某一类功能，如 `/开关 on media` |
| `/开关 status [功能域]`（或 `/开关 状态`） | 查看本群当前状态（限时关闭会显示预计恢复时间） |
| `/开关列表`（`/switch_list` `/开关状态列表`） | **管理员**查看当前平台所有被关闭的群（含功能域）及各自恢复时间 |
| `/开关` | 无参数 = 查看状态 + 用法提示 |

> 别名：`/toggle`、`/switch`（如 `/toggle off 2h`）。时长单位：`s`/`秒`、`m`/`分`/`分钟`、`h`/`时`/`小时`、`d`/`天`，可组合。
>
> **功能域**（可不填，不填 = 全局全部命令）：`media` 媒体解析 · `image` 图片获取 · `music` 音乐点歌 · `utility` 实用工具 · `dglab` DG-LAB 设备 · `memory` 跨群聊记忆。功能域支持中文名（如 `/开关 off 图片`）。

#### 使用示例

```text
/开关 off       # 在本群永久关闭 CurrentCortex 全部命令
/开关 off 10h   # 关闭 10 小时（例如夜间免打扰，到期自动恢复）
/开关 off media 2h   # 只关媒体解析 2 小时，点歌/图片不受影响
/开关 status media   # 查看媒体解析域的状态（⏳ 将于 1小时58分钟后 自动恢复）
/开关列表       # 管理员：查看本平台所有被关闭的群与功能域
/开关 on media  # 单独恢复媒体解析
/开关 on        # 重新启用（永久或限时关闭均可）
```

#### 工作原理与说明

- **状态持久化**：开关状态保存在 `data/currentcortex_group_switch.json`，重启后保留。默认（未配置过）为**启用**，只有主动 `/开关 off` 的群才会被关闭。
- **分级开关（scope）**：存储 key 为 `umo`（全局）或 `umo|功能域`（域级）；全局关闭优先于任何域级状态；旧版本数据（纯 umo 条目）自动视为全局禁用，无需迁移。
- **限时自动恢复**：`/开关 off [功能域] <时长>` 到期后自动恢复启用（懒惰过期判断，无需后台定时任务），重启后倒计时依然有效。
- **关闭期间提醒一次**：功能被关闭后，第一次使用对应命令会收到一句简短提示（如「本群已单独关闭媒体解析」），同一群同一功能 1 小时内不重复，避免刷屏。可用 `group_switch_hint_enable` 关闭该提醒。
- **永不死锁**：`/开关` 与 `/开关列表` 命令本身**始终可用**——即使本群已关闭，仍可发送 `/开关 on` 重新启用，不会被拦截。
- **权限**：默认仅**群管理员**（框架识别的 admin）可操作，避免任意成员随意开关。若你未被识别为管理员，可在配置中关闭 `group_switch_admin_only`。`/开关列表` 始终仅管理员可用。
- **仅作用于本插件**：该开关只拦截 CurrentCortex 的命令，不影响 AstrBot 其它插件与机器人本体功能。
- **⚠️ LLM 工具不受域级开关限制**：功能域开关只约束用户命令；AI 通过 LLM 工具自主调用图片/点歌/电击等能力时不经过命令入口，不受域级开关影响（全局关闭仍会拦截）。介意请同时关闭 `llm_tools_enable`。
- **私聊不受控**：开关仅对群聊生效。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `group_switch_enable` | bool | true | 是否启用按群聊开关功能（关闭则守卫完全不介入） |
| `group_switch_admin_only` | bool | true | 是否仅群管理员可操作 `/开关` |
| `group_switch_hint_enable` | bool | true | 功能被关闭期间，首次使用对应命令时回一句提示（同一群同一功能 1 小时一次） |

---

## ✂️ 分段回复

可选功能：把机器人的回复拆成**多条消息分次发送**，模拟「逐条回复」的节奏，让长回复更自然、更有真人感。默认关闭，需在配置面板手动开启。

#### 工作方式

开启后，插件会在回复发送前介入，按所选规则把整段文本切成若干段，逐条发送，段与段之间加随机延时（首段不延时）。

> ⚠️ **与框架自带功能的关系**：AstrBot 本身已有全局「分段回复」能力（`平台设置 → 分段回复`）。**本插件功能与之独立，请勿同时开启**，否则会重复分段。二选一即可——若你已在框架层启用，就不必再开这里的。

#### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `reply_seg_enable` | bool | false | **【总开关】** 开启分段回复 |
| `reply_seg_only_llm` | bool | true | 仅对大模型(LLM)回复分段；关闭则插件命令回复（如 `/pixiv`）也会被分段。建议保持开启 |
| `reply_seg_mention` | bool | true | 分段回复的首条消息是否 @ 并引用回复用户（让多条分段有明确归属）。部分平台不支持引用回复时自动降级 |
| `reply_seg_mode` | string | llm | 分段模式（下拉选择）：`llm`=大模型语义分段（默认·推荐，最智能）、`punct`=标点分句（最轻量）、`length`=长度切分（见下方说明） |
| `reply_seg_llm_provider_id` | string | `""` | **llm 模式专用**：用于分段的 LLM 提供商 ID。留空则复用当前会话模型；建议填廉价快速模型的 ID |
| `reply_seg_llm_density` | string | `medium` | **llm 模式专用**：分段密度，即每段目标字数。`low`=每段长(~40-70字，切少)、`medium`=适中(~20-45字)、`high`=每段短(~10-25字，切细更活泼)。会自动推算段数上限并引导模型 |
| `reply_seg_llm_max_segments` | int | `0` | **llm 模式专用**：分段数量上限。`0`=按密度档位自动推算（low=3/medium=5/high=8）；也可手动指定硬上限，超过会被合并到最后一段 |
| `reply_seg_llm_min_chars` | int | 30 | **llm 模式专用**：原文短于此字数时不调用 LLM，直接整段发送（建议 20~50） |
| `reply_seg_llm_timeout` | int | 30 | **llm 模式专用**：单次分段调用超时秒数，超时则降级规则分段。默认 30 秒，涵盖大部分模型（含推理模型） |
| `reply_seg_split_symbols` | string | `。！？!?~～…`+换行+`,，` | punct/length 模式：单字符切分符号（在这些符号处切分，符号保留在段尾）。默认含中英文逗号 |
| `reply_seg_split_words` | string | `喵 qwq owo awa ovo` | punct/length 模式：切分词（可多字符，**空格分隔**），在词的后面切分、词保留在段尾。⚠️ 建议只放多字符词：单字符词（如 `w`）会误切英文单词，左括号 `（` 会破坏配对，均默认不带 |
| `reply_seg_merge_threshold` | int | 4 | punct 模式：短段合并阈值。短于此长度的段会被合并到前一段，**纯标点段（如孤立的「。」）无条件合并**——消除逗号碎片与孤立标点。设为 `0` 关闭合并 |
| `reply_seg_min_length` | int | 15 | length 模式：最小段长，短于此不切（建议 10~30） |
| `reply_seg_max_length` | int | 80 | length 模式：最大段长，超过时在 `[最小,最大]` 范围找标点切，找不到才硬切（建议 50~150） |
| `reply_seg_delay_range` | string | `0.8,2.5` | 段间随机延时范围（秒），格式 `min,max` |

#### 三种分段模式

- **`punct`（按标点）**：在每个切分符号/词处断开。最轻量，适合大多数对话。切完后会把**过短段和纯标点段（如孤立的「。」）自动合并**到前一段，避免产生碎片（由 `reply_seg_merge_threshold` 控制，可关闭）。
- **`length`（按长度）**：当某段超过「最大段长」时，在 `[最小段长, 最大段长]` 范围内反向寻找切分点（符号或词）来切；找不到才硬切。适合控制每段不要太长。
- **`llm`（大模型语义分段）** ⭐推荐：调用大模型按**语义完整性**切分，像真人「一句一句说」——不在逗号处碎切、保持颜文字归属、列表/排比按主题归并。比规则式更智能。代价是每条回复会**多一次 LLM 调用**，增加 1~3 秒延迟与少量 token 消耗；短回复（< `reply_seg_llm_min_chars`）会自动跳过不调用。通过 `reply_seg_llm_density` 可选「低/中/高」三档分段密度，控制每段字数规模。

> 💡 **`llm` 模式建议**：在 `reply_seg_llm_provider_id` 填一个**廉价快速模型**（如 deepseek-v3）的提供商 ID，别占用主模型。provider 未配置时会复用当前会话模型；调用失败、解析异常或字数偏差过大时会**自动降级**到 punct 规则分段，不会影响正常回复。
>
> 💡 **分段密度**（`reply_seg_llm_density`）：`low`=每段较长(~40-70字，信息量大、切得少)、`medium`=适中(~20-45字)、`high`=每段短碎(~10-25字，活泼像刷屏)。档位会自动推算段数上限并写进提示词引导模型；如需精确控制段数，可用 `reply_seg_llm_max_segments` 手动指定硬上限。

> 💡 `punct` / `length` 模式下，除标点（句号、问号、逗号等）外还可配置**切分词**（`reply_seg_split_words`，空格分隔），在颜文字/语气词（如 `喵`、`qwq`、`owo`）后面断开。两种规则模式都会同时识别切分符号与切分词。

#### 说明

- 分段后的完整回复会被正确写回对话历史，不影响上下文连贯性。
- 分段仅作用于**纯文本**回复；图片、文件等不会被拆分。
- 若分段过程出现异常，会自动回退为整条发送（不影响正常使用）。

---

## 🤖 LLM 工具

可选功能：把插件的图片获取、点歌、电击控制等功能**注册为大模型可调用的工具（function calling）**，让 AI 能自主处理「来张猫娘图」「播首晴天」「电击A通道强度50」这类**自然语言请求**——无需用户输入 `/` 命令，AI 会自行判断意图并调用对应工具。默认开启，如不需要可在配置面板关闭 `llm_tools_enable`。

> ⚠️ 电击控制涉及物理设备、有安全风险，请确认安全后再开启。所有工具执行第一行都会走开关校验，关闭后工具返回提示而不执行。

#### 已注册工具一览（共 11 个）

| 类别 | 工具名 | 参数 | 说明 |
| --- | --- | --- | --- |
| 🖼️ 图片 | `get_pixiv_random` | num, r18 | 随机二次元插画 |
| 🖼️ 图片 | `search_pixiv` | keyword, num, r18 | 按关键词搜索插画 |
| 🖼️ 图片 | `get_pixiv_by_tags` | tags, num, r18 | 按标签精确筛选（多标签 AND） |
| 👗 男娘 | `get_femboy_image` | 无 | 随机男娘图片 |
| 🎵 点歌 | `play_song` | song_name | 搜索并点歌（语音条） |
| ⚡ 电击 | `dglab_shock` | channel, strength, wave, duration, device_index | 开始电击 |
| ⚡ 电击 | `dglab_strength` | channel, value, device_index | 设置绝对强度 |
| ⚡ 电击 | `dglab_strength_adjust` | channel, direction, step, device_index | 增减强度 |
| ⚡ 电击 | `dglab_pulse` | channel, wave, duration, device_index | 发送波形 |
| ⚡ 电击 | `dglab_stop` | channel, device_index | 停止输出 |
| ⚡ 电击 | `dglab_status` | 无 | 查询设备状态 |

#### 工作方式

- **零重写**：工具内部完全复用现有业务逻辑（图片走 `_process_response`、点歌走 `_search_and_get`、电击走 `_dispatch_command`），不重复造轮子。
- **媒体交付**：图片/点歌/男娘工具内部直接 `event.send` 发送媒体，并 `return` 一句说明给 AI（如「已发送2张图片」），避免 AI 再重复发文本。
- **电击安全**：电击工具把 AI 给的结构化参数拼回命令字符串，复用 `_dispatch_command`，**完整继承权限校验、跨用户隔离、设备解析**。强度值钳位到 0-200，波形预设交由现有逻辑校验。
- **自动降级**：未配置 API Key、设备未连接等情况下，工具返回友好提示而非报错。

#### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `llm_tools_enable` | bool | true | **【总开关】** 开启后注册全部工具；关闭则不生效（仅保留原有 `/` 命令） |

> 💡 开启后，AI 会根据用户消息自动判断是否调用工具。例如用户说「来张萝莉图」，AI 会调用 `get_pixiv_random`；说「我想听晴天」，AI 会调用 `play_song`；说「电我一下」，AI 会调用 `dglab_shock`（需确认电击设备已绑定连接）。

---

## 🧠 跨群聊记忆

可选功能：在同一平台实例下的所有群聊之间共享一份**持久化**记忆，作为额外上下文注入 LLM 请求，让机器人在不同群之间拥有连续语境。

- **存储**：`data/currentcortex_cross_group.json`，按平台实例（`platform_id`）分桶，重启后保留。
- **记录**：群聊中的非命令消息会被格式化为 `[昵称/HH:MM:SS]: 文本` 并滚动追加（超过上限自动裁剪旧记录）。
- **注入**：群消息触发 LLM 请求时，自动把同平台其他群的最近若干条记录以 `<system_reminder>` 注入用户消息部分；配置 `cross_group_max_age_hours` 后仅注入该时效内的记录，冷群不再翻出陈年旧话题。
- **LLM 摘要（可选）**：开启 `cross_group_summary_enable` 后，注入条数超过阈值时先调用 LLM 把原始记录压缩成一段话题摘要（「最近大家在聊 XX、YY」）再注入，省 token、更聚焦重点；失败（无模型/超时/空结果）自动降级为原始记录注入，同一份记忆 5 分钟内复用摘要不重复调用。注意：会在回复链路上增加一次 LLM 调用（最长 20 秒），建议配置廉价快速模型。
- **斜杠命令不记录**：命令消息不会进入记忆。
- **按关键词清理**：管理员发送 `/忘记 <关键词>`（别名 `/forget_memory` `/忘记记忆`）可删除本平台记忆中所有包含该关键词的记录（子串匹配、不区分大小写），用于精确清理误记录内容，无需清空整个平台记忆。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `cross_group_enable` | false | 是否启用跨群聊记忆 |
| `cross_group_max_cnt` | 500 | 每个平台保留的最大记录条数 |
| `cross_group_inject_cnt` | 30 | 每次回复注入到 LLM 的最近记录条数 |
| `cross_group_max_age_hours` | 0 | 注入 LLM 时只保留最近多少小时内的记录（`0` = 不限时效，仅按条数裁剪，即旧版行为；建议 12~48） |
| `cross_group_summary_enable` | false | 是否启用 LLM 记忆摘要（注入条数超过阈值时先压缩成话题摘要再注入） |
| `cross_group_summary_threshold` | 20 | 触发摘要的注入条数阈值（低于该值直接注入原始记录） |
| `cross_group_summary_provider_id` | （空） | 摘要专用模型 ID，留空复用当前会话模型；建议选廉价快速的非推理模型 |

> ⚠️ 开启后会向 LLM 提供其他群的聊天内容，请确认符合你的隐私预期与各群成员的知情同意。

---

## ⚡ 接口连通性测试 (`/apitest`)

一键诊断全部 LeiZ 上游接口的鉴权与连通状态，快速区分「接口异常」还是「代码问题」。

```text
/apitest          # 并行探测全部 6 个接口
/apitest help     # 显示帮助
```

5 个接口（Pixiv / 一言 / 天气 / 男娘 / 点歌）并行探测，每个用最轻量的只读请求，不消耗图片/音频下载流量。状态含义：

| 图标 | 状态 | 含义 |
| --- | --- | --- |
| 🟢 | 正常 | 接口返回成功 |
| 🟡 | HTTP 异常 | 收到非 200（如 401 鉴权失败 / 402 配额 / 5xx） |
| 🔴 | 网络/超时 | 连接失败或超过配置超时 |
| ⚫ | 跳过 | 对应客户端未初始化（通常未配置 API Key） |

---

## ⚙️ 配置项

路径：AstrBot 管理面板 → 插件管理 → 本插件 → 配置。

### Pixiv 相关

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `default_r18` | int | 0 | 默认 R18 模式（0=全年龄, 1=仅R18, 2=混合） |
| `default_num` | int | 1 | 默认每次获取的图片数量（1-20） |
| `default_size` | string | regular | 默认图片尺寸（original/regular/small/thumb/mini） |
| `image_proxy` | string | pixiv.bileizhen.top | 图片反代域名 |
| `exclude_ai` | bool | false | 默认是否排除 AI 生成作品 |

### 通用 / 鉴权

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `leiz_api_key` | string | （空） | **LeiZ API 统一密钥**（请求头 `x-api-key`），**必填**。在 [LeiZ API 官网](https://api.bileizhen.top) 注册后获取，所有 LeiZ 接口均需 |
| `request_timeout` | int | 15 | API 请求超时时间（秒），影响所有功能 |

### 网易云音乐

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `music_file_max_bytes` | int | 26214400 | `/音乐 文件` 单文件体积上限（字节，默认 25MB）。超过则自动转码为 128kbps MP3 再发送（需 ffmpeg）；设为 0 不限制（不推荐，易发送失败） |
| `music_cooldown` | int | 3 | 同一会话连续点歌的最小间隔秒数，防止用户连点触发大量并发下载/转码拖垮服务器。处理中的请求会被提示「请稍候」；设为 0 不限制（不推荐） |
| `music_default_source` | string | auto | 点歌默认音源：`auto`（网易云优先，失败转酷狗）/ `netease`（仅网易云）/ `kugou`（仅酷狗）。用户仍可用 `/音源` 按会话覆盖 |

### DG-LAB

> ⚠️ 使用 DG-LAB 功能前，必须先部署并运行 [DG-LAB WebSocket 中转服务器](https://github.com/dungeonlab-open/dglab-websocket-server)（官方现仅提供 v3 / v4 服务端，v2 已删除）。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dglab_server_url` | string | （空） | 中转服务器地址（如 `ws://192.168.1.100:9999`；V4 若配置了路径前缀需一并填写，如 `wss://host:9998/v4`） |
| `dglab_protocol` | string | auto | 中转协议版本：`auto`=自动识别（推荐）/ `v3`（默认端口 9999，兼容旧 V2 中转）/ `v4`（默认端口 9998，需 DG-LAB 4 APP 扫码） |
| `dglab_heartbeat_interval` | int | 60 | 心跳间隔（秒），建议 30-120 |
| `dglab_auto_connect` | bool | false | 插件启动时是否自动连接（一般设为 false） |
| `dglab_webui_enabled` | bool | false | 是否启用 CCDG WebUI 控制面板（**默认关闭**；需了解风险后手动开启） |
| `dglab_webui_host` | string | 127.0.0.1 | CCDG WebUI 监听地址（默认仅本机；公网需显式设为 `0.0.0.0` 并加反代+鉴权） |
| `dglab_webui_port` | int | 9178 | CCDG WebUI 监听端口 |

<details>
<summary><b>📦 DG-LAB 中转服务器部署（Bun）</b></summary>

1. 获取服务器代码：[dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server)
2. 安装 [Bun](https://bun.sh) 后启动对应版本服务端：
   ```bash
   bun run v3     # V3 服务端, 默认端口 9999 (兼容旧版 APP)
   bun run v4     # V4 服务端, 默认端口 9998 (需 DG-LAB 4 APP)
   ```
3. 端口等可通过 `.env` 修改（`PORT` / `PREFIX` 等，参考仓库 README）
4. 确保 AstrBot 与 DG-LAB APP 均可访问该服务器；`/dglab bind` 时插件会自动识别协议版本并在回执中标注

</details>

<details>
<summary><b>❓ 连接排障（对应 <a href="https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues/3">issue #3</a>）</b></summary>

- **`服务器未确认连接: 等待服务器分配 clientId 超时`**：旧版本（≤ v1.9.1）按 v2 协议在连接路径中携带自生成 clientId，被 v3 服务端误判为 APP 端而拒绝。升级到 v2.0.0+ 即可，v2.0.0 起控制端裸连根路径并使用服务端分配的 clientId。
- **`连接失败: server rejected WebSocket connection: HTTP 404`**：连接了 v4 服务端但地址带了多余路径。v4 服务端仅在根路径（或 `PREFIX` 配置的路径）接受连接，请检查 `dglab_server_url` 是否与服务端实际监听路径一致。
- **V4 绑定后控制无效**：确认使用 **DG-LAB 4 APP** 扫码（新版二维码 `dungeon-lab.cn/s/...` 旧版 APP 无法识别）；若 APP 内有多个设备插槽，插件会自动选择第一个真实连接设备的插槽。

</details>

<details>
<summary><b>🔄 从旧版 DG-LAB JSON 配置迁移</b></summary>

v1.2.0 及更早版本使用 JSON 字符串配置（已弃用）：

```json
{ "dglab": { "server_url": "ws://your-server:9999", "heartbeat_interval": 60, "auto_connect": false } }
```

新格式直接填三个独立项：`dglab_server_url`、`dglab_heartbeat_interval`、`dglab_auto_connect`。插件仍会检测旧版 `dglab` JSON 配置：若新项留空但旧配置存在，会自动读取并提示迁移。建议尽快手动迁移。

</details>

### 跨群聊记忆

见 [🧠 跨群聊记忆](#-跨群聊记忆) 章节。

### 分段回复

见 [✂️ 分段回复](#️-分段回复) 章节。

### LLM 工具

见 [🤖 LLM 工具](#-llm-工具) 章节。开关为 `llm_tools_enable`（默认开启）。

### 插件宣传（QQ 群）

插件内置官方交流群号 **1106353813**，安装后自动生效，无需任何配置。群号通过两个渠道展示：

- **`/交流群` 命令**（别名 `/群号` `/加群`）：用户主动查询时返回群号
- **命令帮助 / 错误提示**：`/pixiv help`、`/点歌 help` 等帮助文本和「API Key 未配置」错误提示末尾带上一行群号

> ⚠️ 群号**不会**注入到机器人日常回复中，避免污染对话内容。

---

## ❓ 常见问题

<details>
<summary><b>安装后插件无法加载？</b></summary>

1. Python 版本是否 >= 3.10
2. 是否已安装依赖：`pip install aiohttp>=3.8.0`（DG-LAB 还需 `websockets>=10.0`）
3. AstrBot 版本是否 >= 4.15（本插件需要较新 API，旧版会无法加载）
4. 查看 AstrBot 日志中的错误信息

</details>

<details>
<summary><b>调用命令提示「功能未启用 / 未配置 API Key」？</b></summary>

需先在 [LeiZ API 官网](https://api.bileizhen.top) 获取 API Key（见 [配置 API Key](#2-配置-api-key必填)），再填入配置面板的 `leiz_api_key` 字段，保存后重启插件。可用 `/apitest` 验证各接口连通性。Pixiv / 一言 / 天气 / 男娘 / 点歌 均依赖此 Key。

</details>

<details>
<summary><b>Pixiv 图片无法显示？</b></summary>

1. 反代域名不可用：尝试更换 `image_proxy` 配置项
2. 网络连接问题：检查服务器能否访问外网
3. API 服务异常：稍后重试

</details>

<details>
<summary><b>如何排除 AI 生成的 Pixiv 作品？</b></summary>

1. **全局排除**：配置 `exclude_ai` 为 `true`
2. **单次排除**：命令中使用 `excludeAI:true`，如 `/pixiv tag:萝莉 excludeAI:true`

</details>

<details>
<summary><b>请求超时怎么办？</b></summary>

适当增大 `request_timeout`（单位秒），检查网络状况；频繁超时多为 API 繁忙，建议稍后重试。

</details>

<details>
<summary><b>天气查询支持哪些城市？</b></summary>

支持中国主要城市，建议使用中文城市名（如「广州市」「北京」），最长 50 字符。

</details>

<details>
<summary><b>DG-LAB 功能无法使用 / 绑定失败？</b></summary>

1. 是否安装依赖：`pip install websockets>=10.0`
2. 是否配置 `dglab_server_url`，且中转服务器正在运行、可访问
3. 二维码生成后需在有效期内用 APP 扫描
4. 确认 APP 版本支持 Socket V2，且仅支持**郊狼脉冲主机 3.0**
5. 查看 AstrBot 日志中 `[DGLab]` 相关错误

</details>

<details>
<summary><b>DG-LAB 连接断开怎么办？</b></summary>

系统会自动重连（最多 2 次）；仍失败可用 `/dglab unbind` 解绑后重新 `/dglab bind`，并用 `/dglab status` 查看状态。

</details>

<details>
<summary><b>多人同时使用会冲突吗？</b></summary>

不会。每个用户拥有独立的设备绑定与连接，操作完全隔离，支持最多 50 个并发连接。

</details>

### 错误处理一览

| 错误类型 | 可能原因 | 解决方案 |
| --- | --- | --- |
| 网络错误 | 网络连接失败 | 检查网络连接 |
| 请求超时 | API 响应慢 | 增大 `request_timeout` 或稍后重试 |
| HTTP 错误 | API 服务异常（401/402/5xx 等） | 检查 API Key / 服务状态 |
| 参数错误 | 命令格式不正确 | 发送 `/xxx help` 查看帮助 |
| 无结果 | 未找到匹配内容 | 更换搜索参数 |
| 数据格式异常 | API 返回异常数据 | 稍后重试 |

---

## 🛠️ 技术架构

### 项目结构

```text
astrbot_plugin_currentcortex/
├── main.py                      # 主程序：命令注册、LLM 工具、分段回复
├── _pages_api.py                # 总 Pages 后端 API（仪表板/设置/郊狼/帮助）
├── __init__.py                  # 插件包初始化
├── clients/                     # API 客户端子包
│   ├── __init__.py
│   ├── _utils.py                # API Key 未配置提示等通用辅助
│   ├── command_parser.py        # key:value 参数与快捷语法解析器
│   ├── pixiv.py                 # Pixiv API 客户端
│   ├── hitokoto.py              # 每日一言 API 客户端
│   ├── weather.py               # 天气查询 API 客户端
│   ├── femboy.py                # 男娘图片 API 客户端
│   └── music.py                 # 网易云 / 酷狗点歌 API 客户端
├── dglab/                       # DG-LAB（郊狼）设备管理子包
│   ├── __init__.py
│   ├── docs/                    # DG-LAB 协议与集成文档
│   ├── dglab_client.py          # WebSocket 客户端（V3/V4 协议自动识别）
│   ├── dglab_connection_pool.py # 连接池与状态管理
│   ├── dglab_commands.py        # 命令解析 / 校验 / 执行
│   ├── dglab_device_store.py    # 设备绑定关系持久化
│   ├── dglab_user_store.py      # 用户存储
│   ├── dglab_permission_store.py # 权限存储
│   ├── dglab_post_store.py      # 投稿广场存储
│   ├── dglab_email_store.py     # 邮箱存储
│   ├── dglab_turnstile_store.py # Turnstile 存储
│   ├── dglab_chat_store.py      # 聊天存储
│   └── dglab_webui.py           # CCDG WebUI 控制面板
├── group/                       # 群聊子包
│   ├── __init__.py
│   ├── cross_group_memory.py    # 跨群聊记忆持久化存储
│   └── group_switch_store.py    # 按群聊开关状态持久化存储
├── media/                       # 媒体解析子包
│   ├── __init__.py
│   └── media_parser.py          # 小红书/B站/抖音/微博 媒体解析
├── pages/                       # 总 Pages 前端（mdui 2 组件库，全部本地化）
│   └── cc-dashboard/
│       ├── index.html           # Pages 入口
│       ├── app.js               # Vue 3 单页应用（5 个页面）
│       ├── app.css              # 晴空蓝 + 雪雾白主题
│       └── vendor/              # 本地依赖：Vue 3 / mdui 2 / Material Icons 字体
├── tests/                       # 测试脚本（独立运行，无需框架）
│   ├── __init__.py
│   ├── test_dglab_protocol.py   # DG-LAB V3/V4 协议端到端
│   ├── test_memory_and_switch.py # 跨群记忆与群开关
│   ├── test_music_audio.py      # 点歌音频
│   ├── test_reply_seg.py        # 语义分段回复
│   └── test_relay_pages.py      # Pages 中转
├── metadata.yaml                # 插件元数据
├── _conf_schema.json            # 配置模式定义
├── requirements.txt             # Python 依赖
├── .gitignore
├── CHANGELOG.md                 # 更新日志
├── CONTRIBUTING.md              # 贡献指南
├── LICENSE
├── logo.png
├── README.md                    # 项目文档（中文）
├── README_EN.md                 # 项目文档（英文）
├── README_JA.md                 # 项目文档（日文）
└── README_ZH-TW.md              # 项目文档（繁体中文）
```

### 核心模块

**内容获取与解析：**
- **PixivAPIClient** ([clients/pixiv.py](clients/pixiv.py))：Pixiv API 客户端，按过滤参数自动路由 GET 随机 / POST 筛选接口
- **HitokotoAPIClient** ([clients/hitokoto.py](clients/hitokoto.py)) / **WeatherAPIClient** ([clients/weather.py](clients/weather.py)) / **FemboyAPIClient** ([clients/femboy.py](clients/femboy.py))：一言 / 天气 / 男娘 API 客户端
- **NeteaseAPIClient** / **KugouAPIClient** ([clients/music.py](clients/music.py))：网易云 / 酷狗客户端，点歌带指数退避重试
- **MediaParserManager** ([media/media_parser.py](media/media_parser.py))：小红书 / B站 / 抖音 / 微博 链接解析
- **CommandParser** ([clients/command_parser.py](clients/command_parser.py))：`key:value` 参数与快捷语法解析器

**DG-LAB 设备管理：**
- **DGLabClient** ([dglab/dglab_client.py](dglab/dglab_client.py))：WebSocket 客户端，连接管理 / 消息收发 / 心跳保活 / V3·V4 协议自动识别
- **DeviceStore** ([dglab/dglab_device_store.py](dglab/dglab_device_store.py))：用户-设备绑定关系持久化（线程安全）
- **DeviceConnectionPool** ([dglab/dglab_connection_pool.py](dglab/dglab_connection_pool.py))：连接池，多用户并发 / 连接复用 / 自动重连 / 空闲清理
- **DGLabCommandHandler** ([dglab/dglab_commands.py](dglab/dglab_commands.py))：命令解析 / 校验 / 执行 / 格式化
- **DGLabWebUI** ([dglab/dglab_webui.py](dglab/dglab_webui.py))：CCDG WebUI 浏览器远程控制面板

**主插件与记忆：**
- **CurrentCortexPlugin(Star)** ([main.py](main.py))：主插件类，集成所有功能并注册命令
- **CrossGroupMemoryStore** ([group/cross_group_memory.py](group/cross_group_memory.py))：跨群聊共享记忆，JSON 持久化
- **GroupSwitchStore** ([group/group_switch_store.py](group/group_switch_store.py))：按群聊开关状态，JSON 持久化

### 设计特点

- **异步架构**：基于 `asyncio` + `aiohttp` / `websockets`，非阻塞 I/O
- **模块化设计**：DG-LAB 功能独立为多个模块，职责清晰
- **统一接口**：所有 API 客户端遵循相同设计模式
- **健壮容错**：全面的异常处理、参数校验、按需重试
- **数据持久化**：DG-LAB 绑定存于 `data/dglab_bindings.json`，跨群记忆存于 `data/currentcortex_cross_group.json`（均符合 AstrBot 规范）
- **资源管理**：连接池自动清理空闲连接，防止资源泄漏
- **多租户隔离**：每个用户独立连接，操作互不干扰

---

## 🤝 贡献指南

欢迎提交 Issue 与 PR！Bug 反馈 / 功能建议已配置 Issue 模板，PR 有自测清单模板。

开发环境搭建、项目结构、测试运行方式、提交规范与 PR 流程见 **[CONTRIBUTING.md](CONTRIBUTING.md)**。

> 💬 也可以先到 QQ 交流群 **1106353813** 讨论想法，大改动建议先对齐再动手。

---

## 📄 开源协议与致谢

本项目采用 [MIT License](LICENSE) 开源。

致谢：

- [LeiZ API](https://api.bileizhen.top) — 提供 Pixiv / 一言 / 天气 / 男娘 / 网易云 等 API 服务
- [AstrBot](https://github.com/AstrBot) — 聊天机器人框架
- [dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server) — DG-LAB WebSocket 协议与中转服务器

---

<div align="center">

**CurrentCortex** · v2.2.0 · [更新日志](CHANGELOG.md) · [问题反馈](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues) · [MIT License](LICENSE)

如果这个插件对你有帮助，欢迎点一个 ⭐ Star 支持作者！

</div>
