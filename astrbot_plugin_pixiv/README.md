# AstrBot Pixiv 随机图片插件

基于 [LeiZ API](https://api.bileizhen.top/doc/pixiv) 开发的 AstrBot 插件，支持通过 `/pixiv` 指令获取随机 Pixiv 图片（含 R18 内容）。

## 功能特性

- **随机图片获取**：一键获取随机 Pixiv 图片
- **R18 内容支持**：支持全年龄、仅 R18、混合三种模式
- **标签筛选**：支持按标签 AND/OR 匹配筛选
- **关键词搜索**：模糊搜索标题、作者、标签
- **多图获取**：一次获取 1-20 张图片
- **智能缓存**：TTL 缓存机制，避免重复请求，提高响应速度
- **完善错误处理**：网络异常、API 错误、参数错误等均有友好提示
- **灵活配置**：支持在 AstrBot 管理面板中自定义默认参数

## 安装方法

### 方法一：通过 AstrBot 插件市场安装

在 AstrBot 管理面板的插件市场中搜索 `astrbot_plugin_pixiv` 并安装。

### 方法二：手动安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/user/astrbot_plugin_pixiv.git
```

安装依赖：

```bash
pip install aiohttp>=3.8.0
```

## 使用方法

### 基本指令

| 指令 | 说明 |
|------|------|
| `/pixiv` | 获取一张随机全年龄图片（图片直出模式） |
| `/pixiv help` | 显示帮助信息 |
| `/pixiv clear-cache` | 清除所有请求缓存 |

### 参数说明

使用 `key:value` 格式指定参数，多个参数用空格分隔：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `r18:` | int | 0 | R18 模式：0=全年龄，1=仅R18，2=混合 |
| `tag:` | string | - | 标签筛选，多个标签用 `\|` 分隔（OR 匹配） |
| `keyword:` | string | - | 标题/作者/标签模糊搜索 |
| `num:` | int | 1 | 获取数量（1-20） |
| `size:` | string | regular | 图片尺寸：original/regular/small/thumb/mini |
| `excludeAI:` | bool | false | 是否排除 AI 生成作品 |
| `uid:` | int | - | 指定作者 UID |
| `ratio:` | string | - | 长宽比筛选，如 `gt1.2lt1.8` |

### 使用示例

```bash
# 获取随机 R18 图片
/pixiv r18:1

# 获取混合模式图片（全年龄 + R18）
/pixiv r18:2

# 按标签筛选（匹配"白丝"标签的图片）
/pixiv tag:白丝

# 多标签 OR 匹配（匹配"白丝"或"黑丝"标签）
/pixiv tag:白丝|黑丝

# 关键词搜索
/pixiv keyword:初音ミク

# 组合使用：R18 + 标签 + 关键词 + 多图
/pixiv r18:2 tag:白丝 keyword:初音ミク num:5

# 排除 AI 生成作品
/pixiv tag:萝莉 excludeAI:true num:5

# 指定作者
/pixiv uid:123456 num:3

# 长宽比筛选（横图 > 1.2 且 < 1.8）
/pixiv ratio:gt1.2lt1.8
```

### 快捷语法

除了 `key:value` 格式外，还支持快捷方式：

```bash
/pixiv r18        # 等同于 r18:1
/pixiv mixed      # 等同于 r18:2
/pixiv safe       # 等同于 r18:0
```

## 配置说明

在 AstrBot 管理面板中可配置以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `default_r18` | int | 0 | 默认 R18 模式 |
| `cache_ttl` | int | 3600 | 缓存有效期（秒） |
| `max_cache_size` | int | 100 | 最大缓存条目数 |
| `default_num` | int | 1 | 默认获取数量 |
| `image_proxy` | string | pixiv.bileizhen.top | 图片反代域名 |
| `default_size` | string | regular | 默认图片尺寸 |
| `exclude_ai` | bool | false | 默认是否排除 AI 作品 |
| `request_timeout` | int | 15 | API 请求超时时间（秒） |

## 返回结果格式

成功获取图片后，插件将返回：

1. **图片信息**：标题、作者、Pixiv 链接、标签、尺寸
2. **图片内容**：通过反代链接直接展示图片
3. **R18 警告**：如包含成人内容，会显示相应警告提示

示例输出：

```
🎨 冬日午后
👤 作者：SampleArtist
🔗 https://www.pixiv.net/artworks/12345678
🏷️ 标签：オリジナル / 女の子 / 冬 / 雪
📐 尺寸：1920×1080
[图片]
```

## 缓存机制

插件内置了智能缓存系统：

- 相同的请求参数在缓存有效期内返回缓存结果，避免重复调用 API
- 缓存命中时会显示 `📦 [缓存命中]` 提示
- 使用 `/pixiv clear-cache` 手动清除所有缓存
- 缓存有效期和最大条目数可在配置中调整

## 错误处理

插件提供了完善的错误处理机制：

| 错误类型 | 提示信息 | 处理建议 |
|----------|----------|----------|
| 网络错误 | 网络请求失败 | 检查网络连接 |
| 请求超时 | API 请求超时 | 稍后重试或增加超时时间 |
| HTTP 错误 | API 请求失败 (HTTP xxx) | 检查 API 服务状态 |
| 参数错误 | 参数错误 | 发送 `/pixiv help` 查看帮助 |
| 无结果 | 未找到符合条件的图片 | 更换参数重试 |

## 依赖项

- **AstrBot** >= 3.4.0
- **aiohttp** >= 3.8.0
- **Python** >= 3.10

## 开源协议

MIT License
