# AstrBot CurrentCortex 综合插件

基于 [LeiZ API](https://api.bileizhen.top) 开发的多功能 AstrBot 插件，提供 **Pixiv 随机图片获取**、**每日一言**、**天气查询**、**男娘图片获取**、**网易云音乐点歌**、**JMComic 漫画获取** 及 **DG-LAB 设备管理** 等功能。

## 📋 项目概述

本插件是一个集成了多种实用功能的 AstrBot 插件，专为提升聊天机器人交互体验而设计。通过简洁的命令接口，用户可以轻松获取各类内容和服务，并支持对 DG-LAB 设备进行完整的生命周期管理。

### ✨ 核心特性

- **🎨 Pixiv 随机图片**：获取随机 Pixiv 图片，支持 R18 内容、标签筛选、关键词搜索、指定作者等
- **✨ 每日一言**：获取随机一言（支持动画、漫画、游戏、文学等 12 种分类）
- **🌤️ 天气查询**：实时查询城市天气信息及未来 3 天天气预报
- **👗 男娘图片**：随机获取男娘主题图片（需配置 API 密钥）
- **📚 JMComic 漫画**：搜索漫画、查看详情、获取章节图片、随机推荐
- **🎵 网易云音乐**：点歌、搜索歌曲、获取播放链接和歌曲详情
- **🔌 DG-LAB 设备管理**：完整的 DG-LAB Socket V2 设备控制，包括绑定/解绑、强度调节、电击启停、波形发送、实时反馈等
- **⚡ 异步高性能**：基于 aiohttp 的异步请求，响应迅速
- **🛡️ 完善错误处理**：网络异常、API 错误、参数错误等均有友好提示
- **⚙️ 灵活配置**：支持在 AstrBot 管理面板中自定义默认参数
- **👥 多用户隔离**：DG-LAB 模块支持多用户并发使用，操作完全隔离

### 📝 指令别名速查

所有指令均支持中文别名，用户输入中文命令也能触发对应功能：

| 英文指令 | 中文别名 | 功能 |
| --- | --- | --- |
| `/pixiv` | `/图片` | Pixiv 随机图片 |
| `/hitokoto` | `/一言` | 每日一言 |
| `/weather` | `/天气` | 天气查询 |
| `/femboy` | `/男娘` | 男娘图片 |
| `/jm` | `/漫画` | JMComic 漫画 |
| `/jmcommend` | `/漫画推荐` | 漫画随机推荐 |
| `/music` | `/音乐` | 网易云音乐 |
| `/dglab` | `/电击` | DG-LAB 设备管理 |

**子命令中文别名：**

| 命令 | 英文子命令 | 中文子命令 |
| --- | --- | --- |
| `/jm` (漫画) | `search` / `detail` / `chapter` | `搜索` / `详情` / `章节` |
| `/music` (音乐) | `search` / `id:` | `搜索` / `编号:` |
| `/dglab` (电击) | `bind` / `unbind` / `strength` / `up` / `down` / `shock` / `stop` / `clear` / `pulse` / `feedback` / `status` / `info` / `permission` | `绑定` / `解绑` / `强度` / `增加` / `减少` / `电击` / `停止` / `清空` / `波形` / `反馈` / `状态` / `信息` / `权限` |

## 📦 安装方法

### 方法一：通过 AstrBot 插件市场安装（推荐）

在 AstrBot 管理面板的插件市场中搜索 `astrbot_plugin_currentcortex` 并安装。

### 方法二：手动安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/backrooms-yrc/astrbot_plugin_currentcortex.git
```

#### 安装依赖

```bash
pip install aiohttp>=3.8.0 websockets>=10.0
```

> ⚠️ **DG-LAB 功能需要 `websockets` 库**，请确保已安装。

### 系统要求

- **AstrBot** >= 3.4.0
- **Python** >= 3.10
- **aiohttp** >= 3.8.0
- **websockets** >= 10.0（DG-LAB 功能必需）

## 🎯 功能介绍

### 1️⃣ Pixiv 随机图片 (`/pixiv`，别名：`/图片`)

通过 LeiZ API 获取随机 Pixiv 图片，支持丰富的筛选和搜索功能。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/pixiv`（或 `/图片`） | 获取一张随机全年龄图片 |
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

### 2️⃣ 每日一言 (`/hitokoto`，别名：`/一言`)

获取来自社区贡献的随机一言，支持多分类选择。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/hitokoto`（或 `/一言`） | 获取一条随机一言（默认全部分类） |
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

### 3️⃣ 天气查询 (`/weather`，别名：`/天气`)

实时查询指定城市的天气信息及未来 3 天天气预报。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/weather <城市名>`（或 `/天气 <城市名>`） | 查询指定城市的天气 |
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

### 4️⃣ 男娘图片 (`/femboy`，别名：`/男娘`)

通过 LeiZ Femboy API 随机获取男娘主题图片。

> ⚠️ **使用前必须配置 API 密钥**，详见下方配置说明。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/femboy`（或 `/男娘`） | 获取一张随机男娘图片（WebP 格式） |
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

### 5️⃣ JMComic 漫画 (`/jm`，别名：`/漫画` & `/jmcommend`，别名：`/漫画推荐`)

通过 LeiZ JMComic API 搜索和获取漫画内容，支持搜索、详情查看、章节图片获取及随机推荐。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/jm search <关键词>`（或 `/漫画 搜索 <关键词>`） | 搜索漫画 |
| `/jm search <关键词> page:<页码>` | 搜索漫画（指定页码） |
| `/jm detail <漫画ID>`（或 `/漫画 详情 <漫画ID>`） | 获取漫画详情（标题、作者、简介、章节列表） |
| `/jm chapter <章节ID>`（或 `/漫画 章节 <章节ID>`） | 获取章节图片（以合并转发消息发送） |
| `/jmcommend`（或 `/漫画推荐`） | 随机推荐一部漫画 |
| `/jm help` | 显示帮助信息 |

#### 使用示例

```
# 搜索漫画
/jm search 原神              # 搜索「原神」相关漫画
/jm search 萝莉 page:2       # 搜索第2页结果

# 查看详情
/jm detail 413828            # 获取漫画ID为413828的详情

# 获取章节图片
/jm chapter 413828           # 获取章节图片（合并转发发送）

# 随机推荐
/jmcommend                   # 随机推荐一部漫画
```

#### 搜索结果示例

```
📚 搜索「原神」结果（第1页）：

  1. 【1438976】被达达利亚用常识改变催眠...
     作者: 秋月リア | 分类: 同人
  2. 【1435210】原神同人作品集
     作者: SampleAuthor | 分类: 同人

💡 使用 /jm detail <漫画ID> 查看详情
```

#### 随机推荐示例

```
📚 随机漫画推荐

📕 标题：示例漫画标题
👤 作者：示例作者
📂 分类：同人
🆔 ID：123456

💡 使用 /jm detail 123456 查看详情
💡 使用 /jm chapter 123456 查看图片
```

#### QQ 合并转发支持

在 QQ 平台使用 `/jm chapter` 获取章节图片时，插件会以**合并转发消息**（聊天记录）的形式批量发送图片，避免逐条发送大量图片导致风控或刷屏。

#### 注意事项

- 内容来源于第三方 API，请遵守相关法律法规
- API 响应可能较慢（尤其是详情和章节接口），请耐心等待
- 章节图片默认展示前 10 张，以合并转发形式发送
- 无需额外配置，开箱即用

---

### 6️⃣ 网易云音乐 (`/music`，别名：`/音乐`)

通过 LeiZ Netease API 实现点歌、搜索歌曲和获取播放链接功能。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/music <歌曲名>`（或 `/音乐 <歌曲名>`） | 点歌（搜索并返回第一首歌的详细信息） |
| `/music id:<歌曲ID>`（或 `/音乐 编号:<歌曲ID>`） | 通过歌曲 ID 获取详细信息 |
| `/music search <关键词>`（或 `/音乐 搜索 <关键词>`） | 搜索歌曲列表 |
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

### 7️⃣ DG-LAB 设备管理 (`/dglab`，别名：`/电击`)

通过 DG-LAB Socket V2 协议实现对郊狼脉冲主机的完整控制，支持设备绑定、强度调节、输出控制等功能。

> ⚠️ **此功能需要运行 DG-LAB 中转服务器**（详见下方配置说明）。

#### 基本指令

| 指令 | 说明 |
| --- | --- |
| `/dglab bind [服务器地址]`（或 `/电击 绑定`） | 绑定设备（生成二维码供 APP 扫描） |
| `/dglab unbind`（或 `/电击 解绑`） | 解绑当前设备 |
| `/dglab strength <A\|B> <0-200>`（或 `/电击 强度`） | 设置通道强度值 |
| `/dglab up <A\|B> [步进]`（或 `/电击 增加`） | 增加强度（默认+5） |
| `/dglab down <A\|B> [步进]`（或 `/电击 减少`） | 减少强度（默认-5） |
| `/dglab shock <A\|B> [强度] [波形] [秒数]`（或 `/电击 开始`） | 开始电击（设置强度并发送波形） |
| `/dglab stop [A\|B]`（或 `/电击 停止`） | 停止电击（强度归零+清空波形，不指定则停止全部） |
| `/dglab pulse <A\|B> <预设名\|HEX> [秒数]`（或 `/电击 波形`） | 发送波形数据（默认5秒） |
| `/dglab clear <A\|B>`（或 `/电击 清空`） | 清空波形队列 |
| `/dglab feedback`（或 `/电击 反馈`） | 查看设备实时强度和反馈按钮状态 |
| `/dglab permission [on\|off]`（或 `/电击 权限`） | 查看/切换权限隔离（默认开启） |
| `/dglab status`（或 `/电击 状态`） | 查看绑定状态和连接状态 |
| `/dglab info`（或 `/电击 信息`） | 查看详细设备信息 |
| `/dglab help`（或 `/电击 帮助`） | 显示帮助信息 |

#### 使用流程

```
1. 绑定设备
   /dglab bind ws://192.168.1.100:9999
   
2. 使用 DG-LAB APP 扫描二维码完成绑定

3. 控制设备
   /dglab shock A 50 breathe 10  # A通道开始电击（强度50，呼吸波形，10秒）
   /dglab strength A 50     # 仅设置A通道强度为50
   /dglab pulse A wave 5    # 仅发送波浪波形到A通道（5秒）
   /dglab up B 10           # B通道强度增加10
   /dglab stop              # 停止所有输出
   /dglab stop A            # 仅停止A通道

4. 查看状态
   /dglab status            # 查看连接状态
   /dglab feedback          # 查看实时强度和反馈

5. 解绑设备（可选）
   /dglab unbind            # 解绑当前设备
```

#### 参数说明

**强度控制参数：**

| 参数 | 类型 | 范围 | 说明 |
| --- | --- | --- | --- |
| `通道` | string | A 或 B | A/B 双通道独立控制 |
| `强度值` | int | 0-200 | 目标强度值（0=关闭，200=最大） |
| `步进值` | int | 1-200 | 每次调整的幅度（默认5） |

**电击控制参数（`/dglab shock`）：**

| 参数 | 类型 | 范围 | 说明 |
| --- | --- | --- | --- |
| `通道` | string | A 或 B | 必填，指定输出通道 |
| `强度` | int | 0-200 | 可选，默认20 |
| `波形` | string | 预设名 | 可选，默认pulse。可选: breathe, pulse, wave, tap, storm |
| `秒数` | int | 1-30 | 可选，持续时间，默认5秒 |

**波形控制参数（`/dglab pulse`）：**

| 参数 | 类型 | 范围 | 说明 |
| --- | --- | --- | --- |
| `通道` | string | A 或 B | 必填，指定输出通道 |
| `预设名/HEX` | string | 见下方 | 必填，波形预设名或16位HEX数据 |
| `秒数` | int | 1-30 | 可选，持续时间，默认5秒 |

**可用波形预设：**

| 预设名 | 效果 |
| --- | --- |
| `breathe` | 缓慢渐强渐弱 |
| `pulse` | 快速间歇脉冲 |
| `wave` | 连续波浪起伏 |
| `tap` | 短促有力的单次敲击 |
| `storm` | 高频持续输出 |

**绑定参数：**

| 参数 | 类型 | 说明 | 示例 |
| --- | --- | --- | --- |
| `服务器地址` | string | DG-LAB 中转服务器地址 | `ws://192.168.1.100:9999` |

> 💡 **提示**：如果配置了默认服务器地址，`/dglab bind` 可省略地址参数。

#### 返回结果示例

**绑定成功：**
```
🔗 DG-LAB 设备绑定

👤 用户: TestUser
🖥️  服务器: ws://192.168.1.100:9999
🆔 客户端ID: a1b2c3d4...
📱 请使用 DG-LAB APP 扫描下方二维码完成绑定

📲 二维码内容:
`https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://192.168.1.100:9999/a1b2c3d4...`

⏳ 等待APP扫码绑定中...
💡 绑定成功后将自动通知您
```

**查看状态：**
```
📊 DG-LAB 设备状态

🔗 绑定状态: ✅ 已绑定
🖥️  服务器: ws://192.168.1.100:9999
🆔 客户端ID: a1b2c3d4e5f6...
🕐 绑定时间: 2025-01-15 10:30:00
🔄 最后活跃: 2025-01-15 14:25:30
📡 连接状态: 🟢 bound
⏱️  连接时长: 14340 秒 (239 分钟)
😴 空闲时长: 120 秒

📈 系统活跃连接数: 3
```

#### 高级特性

**多用户隔离：**
- 每个用户拥有独立的设备连接和绑定关系
- 用户间操作完全隔离，互不影响
- 支持最多 50 个并发连接

**自动重连与容错：**
- 操作失败时自动重试（最多 2 次）
- 连接断开时尝试重新建立
- 空闲超过 5 分钟的连接自动清理（释放资源）

**安全机制：**
- 所有输入参数严格校验（范围、格式、类型）
- 操作超时保护（防止长时间阻塞）
- 强度值限制在安全范围内 (0-200)

#### 注意事项

- ⚠️ **强度值范围**：必须在 0-200 之间，请根据个人耐受度调整
- ⚠️ **APP 要求**：仅支持 **郊狼脉冲主机 3.0**
- ⚠️ **网络要求**：确保服务器可访问，建议使用局域网或公网服务器
- ⚠️ **二维码有效期**：绑定二维码在会话期间有效，超时需重新生成
- ⚠️ **权限隔离**：您的设备仅您可控制，其他用户无法访问

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

### DG-LAB 配置

> ⚠️ **使用 DG-LAB 功能前，必须先部署并运行 [DG-LAB Socket V2 中转服务器](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE)**。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dglab_server_url` | string | （空） | DG-LAB 中转服务器地址（如 `ws://192.168.1.100:9999`） |
| `dglab_heartbeat_interval` | int | 60 | 心跳间隔（秒），建议 30-120 |
| `dglab_auto_connect` | bool | false | 是否在插件启动时自动连接（一般设为 false） |

#### 配置示例

在 AstrBot 管理面板的插件配置中直接填写：

| 配置项 | 填写示例 |
| --- | --- |
| `dglab_server_url` | `ws://192.168.1.100:9999` |
| `dglab_heartbeat_interval` | `60` |
| `dglab_auto_connect` | `false` |

#### 配置迁移指南

从旧版本（v1.2.0 及更早）的 JSON 格式配置迁移到新独立配置项：

**旧格式（已弃用）：**
```json
{
  "dglab": {
    "server_url": "ws://your-server:9999",
    "heartbeat_interval": 60,
    "auto_connect": false
  }
}
```

**新格式：**
直接在配置面板中填写以下三个独立项：
- `dglab_server_url` → 填入旧 `server_url` 的值
- `dglab_heartbeat_interval` → 填入旧 `heartbeat_interval` 的值（默认 60）
- `dglab_auto_connect` → 填入旧 `auto_connect` 的值（默认 false）

**兼容性说明：**
插件仍会检测旧版 `dglab` JSON 配置。如果新的独立配置项留空但旧配置存在，插件会自动读取旧配置并给出迁移提示。建议尽快手动迁移以获得更好的配置体验。

#### 部署中转服务器

1. **获取服务器代码**：访问 [DG-LAB-OPENSOURCE](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE)
2. **安装依赖并启动**：
   ```bash
   cd socket/v2/backend
   npm install
   npm start
   ```
3. **默认端口**：`9999`（可通过 `.env` 文件修改）
4. **网络要求**：确保服务器可被 AstrBot 和 DG-LAB APP 访问

> 💡 **提示**：局域网部署使用 `ws://`，公网部署建议使用 `wss://`（更安全）。

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

### Q: DG-LAB 功能无法使用？

请检查：
1. **是否安装依赖**：`pip install websockets>=10.0`
2. **是否配置服务器地址**：在插件配置中填写 `dglab_server_url`
3. **中转服务器是否运行**：确保 DG-LAB Socket V2 服务器已启动并可访问
4. **网络连通性**：AstrBot 服务器能否连接到中转服务器
5. **查看日志**：检查 AstrBot 日志中的 `[DGLab]` 相关错误信息

### Q: DG-LAB 绑定失败？

可能原因：
1. **APP 未扫码**：二维码生成后需在有效期内用 APP 扫描
2. **服务器地址错误**：确认地址格式正确（如 `ws://host:port`）
3. **网络不通**：检查防火墙和网络配置
4. **APP 版本过低**：确保使用支持 Socket V2 的 APP 版本

### Q: 多人同时使用会冲突吗？

不会。每个用户拥有独立的设备绑定和连接，操作完全隔离。系统支持最多 50 个并发连接。

### Q: DG-LAB 连接断开怎么办？

1. 系统会自动尝试重连（最多 2 次）
2. 如果仍失败，使用 `/dglab unbind` 解绑后重新 `/dglab bind`
3. 检查中转服务器是否正常运行
4. 使用 `/dglab status` 查看当前连接状态

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
astrbot_plugin_currentcortex/
├── main.py                      # 主程序文件（包含所有功能实现及插件入口）
├── dglab_client.py              # DG-LAB Socket V2 WebSocket 客户端封装
├── dglab_device_store.py        # DG-LAB 设备绑定关系持久化存储
├── dglab_connection_pool.py     # DG-LAB 连接池与状态管理
├── dglab_commands.py            # DG-LAB 命令处理器（参数解析、校验、执行）
├── test_dglab_integration.py    # DG-LAB 模块集成测试脚本
├── metadata.yaml                # 插件元数据
├── _conf_schema.json            # 配置模式定义
├── requirements.txt             # Python 依赖
├── README.md                    # 项目文档
└── .gitignore                   # Git 忽略规则
```

## 🛠️ 技术架构

### 核心模块

**Pixiv 相关：**
- **PixivAPIClient**：Pixiv API 客户端，支持 GET/POST 请求，处理重定向和 JSON 响应
- **HitokotoAPIClient**：一言 API 客户端，支持分类筛选
- **WeatherAPIClient**：天气 API 客户端，解析当前天气和未来预报
- **FemboyAPIClient**：男娘图片 API 客户端，需 x-api-key 认证
- **NeteaseAPIClient**：网易云音乐 API 客户端，支持歌曲获取和搜索
- **JMComicAPIClient**：JMComic 漫画 API 客户端，支持搜索、详情、章节图片获取
- **CommandParser**：命令解析器，支持 `key:value` 格式参数和快捷语法

**DG-LAB 设备管理：**
- **DGLabClient** ([dglab_client.py](dglab_client.py))：WebSocket 客户端封装，实现连接管理、消息收发、心跳保活
- **DeviceStore** ([dglab_device_store.py](dglab_device_store.py))：用户-设备绑定关系持久化存储（JSON 文件），线程安全
- **DeviceConnectionPool** ([dglab_connection_pool.py](dglab_connection_pool.py))：连接池管理器，支持多用户并发、连接复用、自动重连、空闲清理、超时保护
- **DGLabCommandHandler** ([dglab_commands.py](dglab_commands.py))：命令处理器，负责参数解析、合法性校验、操作执行、结果格式化

**主插件：**
- **CurrentCortexPlugin(Star)** ([main.py](main.py))：主插件类，集成所有功能并注册命令

### 设计特点

- **异步架构**：基于 asyncio 和 aiohttp/websockets，非阻塞 I/O
- **模块化设计**：DG-LAB 功能独立为 4 个模块，职责清晰，便于维护
- **统一接口**：所有 API 客户端遵循相同的设计模式
- **完善日志**：详细的调试和错误日志，便于排查问题
- **健壮性**：全面的异常处理和参数校验
- **数据持久化**：DG-LAB 绑定数据存储在 `data/dglab_bindings.json`（符合 AstrBot 规范）
- **资源管理**：连接池自动清理空闲连接，防止资源泄漏
- **多租户隔离**：每个用户独立连接，操作互不干扰

## 📄 开源协议

MIT License

## 🙏 致谢

- [LeiZ API](https://api.bileizhen.top) — 提供 Pixiv、一言、天气、男娘图片、网易云音乐等 API 服务
- [AstrBot](https://github.com/AstrBot) — 聊天机器人框架
- [DG-LAB-OPENSOURCE](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE) — DG-LAB Socket V2 协议与中转服务器

---

**版本**：v1.3.0  
**更新日期**：2026-05-17  
**新增功能**：JMComic 漫画获取（搜索、详情、章节图片、随机推荐）  
**仓库**：[GitHub](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex)
