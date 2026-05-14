# AstrBot Pixiv 综合插件

基于 [LeiZ API](https://api.bileizhen.top) 开发的多功能 AstrBot 插件，提供 **Pixiv 随机图片获取**、**每日一言**、**天气查询**、**男娘图片获取** 及 **网易云音乐点歌** 等功能。

## 📋 项目概述

本插件是一个集成了多种实用功能的 AstrBot 插件，专为提升聊天机器人交互体验而设计。通过简洁的命令接口，用户可以轻松获取各类内容和服务。

### ✨ 核心特性

- **🎨 Pixiv 随机图片**：获取随机 Pixiv 图片，支持 R18 内容、标签筛选、关键词搜索、指定作者等
- **✨ 每日一言**：获取随机一言（支持动画、漫画、游戏、文学等 12 种分类）
- **🌤️ 天气查询**：实时查询城市天气信息及未来 3 天天气预报
- **👗 男娘图片**：随机获取男娘主题图片（需配置 API 密钥）
- **🎵 网易云音乐**：点歌、搜索歌曲、获取播放链接和歌曲详情
- **⚡ 异步高性能**：基于 aiohttp 的异步请求，响应迅速
- **🛡️ 完善错误处理**：网络异常、API 错误、参数错误等均有友好提示
- **⚙️ 灵活配置**：支持在 AstrBot 管理面板中自定义默认参数

## 📦 安装方法

### 方法一：通过 AstrBot 插件市场安装（推荐）

在 AstrBot 管理面板的插件市场中搜索 `astrbot_plugin_pixiv` 并安装。

### 方法二：手动安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/backrooms-yrc/astrbot_plugin_pixiv.git
```

#### 安装依赖

```bash
pip install aiohttp>=3.8.0
```

### 系统要求

- **AstrBot** >= 3.4.0
- **Python** >= 3.10
- **aiohttp** >= 3.8.0

## 🎯 功能介绍

### 1️⃣ Pixiv 随机图片 (`/pixiv`)

通过 LeiZ API 获取随机 Pixiv 图片，支持丰富的筛选和搜索功能。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/pixiv` | 获取一张随机全年龄图片 |
| `/pixiv help` | 显示帮助信息 |

#### 参数说明

使用 `key:value` 格式指定参数，多个参数用空格分隔：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `r18:` | int | 0 | R18 模式：0=全年龄，1=仅R18，2=混合 |
| `tag:` | string | - | 标签筛选，多个标签用 `\|` 分隔（OR 匹配），多个 tag 参数为 AND 匹配 |
| `keyword:` | string | - | 标题/作者/标签模糊搜索 |
| `num:` | int | 1 | 获取数量（1-20） |
| `size:` | string | regular | 图片尺寸：original/regular/small/thumb/mini |
| `excludeAI:` | bool | false | 是否排除 AI 生成作品 |
| `uid:` | int | - | 指定作者 UID |
| `ratio:` | string | - | 长宽比筛选，如 `gt1.2lt1.8` |

#### 快捷语法

| 快捷词 | 等同于 |
| --- | --- |
| `r18` | `r18:1` |
| `mixed` | `r18:2` |
| `safe` / `sfw` | `r18:0` |

#### 使用示例

```
# 基础用法
/pixiv                          # 随机全年龄图片
/pixiv r18:1                    # 随机 R18 图片
/pixiv help                     # 显示帮助

# 高级搜索
/pixiv r18:1 tag:白丝 num:3     # 获取3张白丝R18图
/pixiv keyword:初音ミク num:5   # 搜索初音未来相关图片
/pixiv tag:萝莉 excludeAI:true  # 排除AI的萝莉标签图片
/pixiv uid:123456 num:3         # 获取指定作者的作品

# 组合筛选
/pixiv r18:2 tag:白丝 keyword:初音ミク num:3 size:original

# 快捷语法
/pixiv r18                      # 等同于 r18:1
/pixiv mixed                    # 等同于 r18:2
/pixiv safe                     # 等同于 r18:0
```

#### 返回结果示例

```
📷 [1/3]
🎨 冬日午后
👤 作者：SampleArtist
🔗 https://www.pixiv.net/artworks/12345678
🏷️ 标签：オリジナル / 女の子 / 冬 / 雪
📐 尺寸：1920×1080
[图片]
```

---

### 2️⃣ 每日一言 (`/hitokoto`)

获取来自社区贡献的随机一言，支持多分类选择。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/hitokoto` | 获取一条随机一言（默认全部分类） |
| `/hitokoto <分类代码>` | 获取指定分类的一言 |
| `/hitokoto help` | 显示帮助信息 |

#### 分类选项

| 代码 | 分类 | 代码 | 分类 |
| --- | --- | --- | --- |
| a | 动画 | g | 其他 |
| b | 漫画 | h | 影视 |
| c | 游戏 | i | 诗词 |
| d | 文学 | j | 网易云 |
| e | 原创 | k | 哲学 |
| f | 来自网络 | l | 抖机灵 |

#### 使用示例

```
/hitokoto                  # 随机获取一言
/hitokoto a               # 获取动画类一言
/hitokoto d               # 获取文学类一言
/hitokoto i               # 获取诗词类一言
/hitokoto help            # 显示帮助
```

#### 返回结果示例

```
✨ 每日一言

「生活就像一盒巧克力，你永远不知道下一颗是什么味道」

—— 阿甘正传
📂 分类：影视
```

---

### 3️⃣ 天气查询 (`/weather`)

实时查询指定城市的天气信息及未来 3 天天气预报。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/weather <城市名>` | 查询指定城市的天气 |
| `/weather help` | 显示帮助信息 |

#### 使用示例

```
/weather 广州市           # 查询广州市天气
/weather 北京             # 查询北京市天气
/weather 上海             # 查询上海市天气
/weather help             # 显示帮助
```

#### 返回结果示例

```
🌤️ 广州市 天气预报
📍 广东

☀️ 当前天气
🌡️ 温度：28
☁️ 天气：多云
🤒 体感温度：30
💨 风力：东南风 3级
💧 湿度：75%

📅 未来天气预报

📆 第1天：2025-01-15（周三）
   ☁️ 天气：晴
   🌡️ 温度：18~28
   💨 风力：东南风 3级
   💧 湿度：70%

📆 第2天：2025-01-16（周四）
   ☁️ 天气：多云
   🌡️ 温度：19~29
   💨 风力：南风 2级
   💧 湿度：68%
```

---

### 4️⃣ 男娘图片 (`/femboy`)

通过 LeiZ Femboy API 随机获取男娘主题图片。

> ⚠️ **使用前必须配置 API 密钥**，详见下方配置说明。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/femboy` | 获取一张随机男娘图片（WebP 格式） |
| `/femboy help` | 显示帮助信息 |

#### 配置要求

使用此功能前，需要在插件配置面板中填写 `femboy_api_key`（x-api-key）。未配置时调用命令会提示错误。

#### 使用示例

```
/femboy                  # 获取随机男娘图片
/femboy help             # 显示帮助
```

#### 返回结果示例

```
👗 随机男娘图片
📸 来源：网络收集
📝 备注：示例备注
[图片]
```

---

### 5️⃣ 网易云音乐 (`/music`)

通过 LeiZ Netease API 实现点歌、搜索歌曲和获取播放链接功能。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/music <歌曲名>` | 点歌（搜索并返回第一首歌的详细信息） |
| `/music id:<歌曲ID>` | 通过歌曲 ID 获取详细信息 |
| `/music search <关键词>` | 搜索歌曲列表 |
| `/music help` | 显示帮助信息 |

#### 使用示例

```
# 点歌（搜索并获取第一首歌的信息）
/music 孤勇者              # 搜索并获取「孤勇者」
/music 周杰伦 晴天         # 搜索「周杰伦 晴天」

# 通过 ID 获取
/music id:1901371647       # 获取指定 ID 的歌曲信息

# 搜索歌曲列表
/music search 陈奕迅       # 搜索陈奕迅相关歌曲列表
/music help                # 显示帮助
```

#### 返回信息

- 歌曲名称、艺术家、专辑
- 专辑封面图片
- 音质信息（码率、格式、音质等级）
- 文件大小
- 播放链接

#### 返回结果示例

```
🎵 孤勇者
👤 艺术家：陈奕迅
💿 专辑：孤勇者
🎧 音质：无损 / FLAC / 907kbps
📦 大小：27.7MB
🔗 播放链接：http://m701.music.126.net/...
[专辑封面图片]
```

#### 搜索结果示例

```
🔍 搜索「陈奕迅」结果：

  1. 孤勇者 - 陈奕迅
     ID: 1901371647
  2. 富士山下 - 陈奕迅
     ID: 5264842
  3. 十年 - 陈奕迅
     ID: 185809

💡 使用 /music id:<歌曲ID> 获取详细信息和播放链接
```

#### QQ 语音条支持

在 QQ 平台使用时，插件会自动将播放链接解析为**语音条**发送，用户可以直接在聊天中播放歌曲，无需手动打开链接。

> 💡 语音条功能依赖 AstrBot 框架的 `Record` 消息段支持。如果当前环境不支持，插件会自动降级为仅发送文本链接，不影响其他功能。

#### 注意事项

- 部分 VIP 歌曲可能无法获取播放链接
- 播放链接有时效性，请及时使用
- 数据来源于网易云音乐，仅供个人试听
- 无需额外配置，开箱即用
- 在 QQ 中会自动发送语音条，其他平台发送播放链接

---

## ⚙️ 配置说明

在 AstrBot 管理面板中可配置以下参数：

**路径**：AstrBot 管理面板 → 插件管理 → astrbot\_plugin\_pixiv → 配置

### Pixiv 相关配置

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `default_r18` | int | 0 | 默认 R18 模式（0=全年龄, 1=仅R18, 2=混合） |
| `default_num` | int | 1 | 默认每次获取的图片数量（1-20） |
| `image_proxy` | string | pixiv.bileizhen.top | 图片反代域名 |
| `default_size` | string | regular | 默认图片尺寸（original/regular/small/thumb/mini） |
| `exclude_ai` | bool | false | 默认是否排除 AI 生成作品 |

### 通用配置

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `request_timeout` | int | 15 | API 请求超时时间（秒），影响所有功能 |
| `femboy_api_key` | string | （空） | 男娘图片 API 密钥（x-api-key），**必填**才能使用 `/femboy` |

## ❓ 常见问题

### Q: 安装后插件无法加载？

请检查：
1. Python 版本是否 >= 3.10
2. 是否已安装依赖：`pip install aiohttp>=3.8.0`
3. AstrBot 版本是否 >= 3.4.0
4. 查看 AstrBot 日志中的错误信息

### Q: Pixiv 图片无法显示？

可能原因：
1. **反代域名不可用**：尝试更换 `image_proxy` 配置项
2. **网络连接问题**：检查服务器是否能访问外网
3. **API 服务异常**：稍后重试

### Q: `/femboy` 提示功能未启用？

需要在插件配置面板中填写 `femboy_api_key` 字段（您的 x-api-key），保存配置后重启插件即可。

### Q: 如何排除 AI 生成的 Pixiv 作品？

两种方式：
1. **全局排除**：在配置中设置 `exclude_ai` 为 `true`
2. **单次排除**：在命令中使用 `excludeAI:true`，如 `/pixiv tag:萝莉 excludeAI:true`

### Q: 请求超时怎么办？

1. 在配置中增加 `request_timeout` 的值（单位：秒）
2. 检查网络连接状况
3. 如果频繁超时，可能是 API 服务繁忙，建议稍后重试

### Q: 天气查询支持哪些城市？

支持中国主要城市，建议使用中文城市名称（如"广州市"、"北京"）。城市名称最长 50 个字符。

## 🔧 错误处理

插件对各类异常均有友好提示：

| 错误类型 | 可能原因 | 解决方案 |
| --- | --- | --- |
| 网络错误 | 网络连接失败 | 检查网络连接 |
| 请求超时 | API 响应慢 | 增加 timeout 配置或稍后重试 |
| HTTP 错误 | API 服务异常 | 检查 API 服务状态 |
| 参数错误 | 命令格式不正确 | 发送 `/xxx help` 查看帮助 |
| 无结果 | 未找到匹配内容 | 更换搜索参数 |
| 数据格式异常 | API 返回异常数据 | 稍后重试 |

## 📊 项目结构

```
astrbot_plugin_pixiv/
├── main.py              # 主程序文件（包含所有功能实现）
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置模式定义
├── requirements.txt     # Python 依赖
├── README.md            # 项目文档
└── .gitignore           # Git 忽略规则
```

## 🛠️ 技术架构

### 核心模块

- **PixivAPIClient**：Pixiv API 客户端，支持 GET/POST 请求，处理重定向和 JSON 响应
- **HitokotoAPIClient**：一言 API 客户端，支持分类筛选
- **WeatherAPIClient**：天气 API 客户端，解析当前天气和未来预报
- **FemboyAPIClient**：男娘图片 API 客户端，需 x-api-key 认证
- **NeteaseAPIClient**：网易云音乐 API 客户端，支持歌曲获取和搜索
- **CommandParser**：命令解析器，支持 `key:value` 格式参数和快捷语法
- **PixivPlugin(Star)**：主插件类，集成所有功能并注册命令

### 设计特点

- **异步架构**：基于 asyncio 和 aiohttp，非阻塞 I/O
- **单文件设计**：所有功能集中在 `main.py`，部署简单
- **统一接口**：所有 API 客户端遵循相同的设计模式
- **完善日志**：详细的调试和错误日志，便于排查问题
- **健壮性**：全面的异常处理和参数校验

## 📄 开源协议

MIT License

## 🙏 致谢

- [LeiZ API](https://api.bileizhen.top) — 提供 Pixiv、一言、天气、男娘图片、网易云音乐等 API 服务
- [AstrBot](https://github.com/AstrBot) — 聊天机器人框架

---

**版本**：v1.2.0
**仓库**：[GitHub](https://github.com/backrooms-yrc/astrbot_plugin_pixiv)
