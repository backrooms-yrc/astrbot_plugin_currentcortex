# AstrBot CurrentCortex All-in-One Plugin

**[简体中文](README.md)** | **[English](README_EN.md)** | **[日本語](README_JA.md)** | **[繁體中文](README_ZH-TW.md)**

> [!IMPORTANT]
> ## 🔒 Please Join the Official QQ Group Before Using This Plugin
>
> **All users are strongly encouraged to join the official QQ group 1106353813** ([click to join](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)).
>
> - **Updates & urgent announcements**: version releases, upstream API/protocol changes, and incident notices are posted in the group first
> - **Bug reports**: ping the maintainer directly in the group — responses are much faster than GitHub Issues
> - **Q&A**: the developer and helpful community members are happy to answer questions and compare notes
>
> Please read the group announcements after joining. Users who haven't joined may not be able to get timely support when something goes wrong.

> [!NOTE]
> ## 📢 Volunteers Wanted: Real-Device Testing for DG-LAB Remote Control
>
> The DG-LAB remote-control feature **still lacks testing on real hardware, and volunteers are urgently needed** — without feedback from actual devices, bugs can only be fixed blind and iteration stalls. If you own a **DG-LAB (Coyote) 3.0 pulse box**, please join the official group and help test:
>
> - **Test scope**: device binding · remote-control commands · the CCDG WebUI panel · relay server deployment (V3 / V4 protocols)
> - **How to participate**: join official QQ group **1106353813** ([click to join](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)), tell us why you're there or just ping the maintainer
> - **Feedback**: reported issues are followed up and fixed promptly, and contributors are credited in the changelog
>
> Don't have a device? You're still welcome to join and follow along, or help spread the word 🙏

> [!IMPORTANT]
> ## 🙏 An Apology — The Two-Month Delay in DG-LAB Protocol Support
>
> To everyone using the DG-LAB features:
>
> The official relay server migrated to the v3 / v4 protocols between May and July this year (the legacy v2 server was removed from the official repository on June 2). During that window, users on the new relay simply could not bind their devices (failing with `waiting for server-assigned clientId timeout` or `HTTP 404`). **That was my fault for not keeping up with upstream changes — I wasn't watching the official repository, and only found out on August 13 when a user reported it in [#3](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues/3). Everyone waited more than two months because of this, and I am sincerely sorry.**
>
> The problem was fully fixed in [v2.0.0](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/releases/tag/v2.0.0): the protocol client was rewritten to auto-detect V3 / V4 (legacy v2 relays remain supported). No configuration changes are needed — just upgrade and it works. V4 relays require the **DG-LAB 4 app** to scan the new-style QR code; see the [DG-LAB section](#7-dg-lab-device-management-dglab) for details.
>
> To keep this from happening again, I have subscribed to change notifications on the upstream repository and added 36 protocol regression tests for this module — any future official protocol change can now be followed up immediately instead of being discovered through user bug reports. Thanks again to the reporter of issue #3, and to everyone for their patience.
>
> — Rcst20 · August 15, 2026

<div align="center">

**An all-in-one AstrBot plugin** — content fetching, media parsing, device control, and cross-group memory in a single package.

Pixiv random images · Hitokoto quotes · Weather · Femboy images · NetEase Cloud Music song requests · Xiaohongshu/Bilibili/Douyin/Weibo parsing · DG-LAB device management · Cross-group memory · LLM tools (AI-initiated calls) · Segmented replies

</div>

---

> 💬 **Official plugin QQ group**: **1106353813**, [click to join](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)
>
> Everyone is welcome! The group is where update notices get posted, where you can report problems and suggest features, and where the developer answers questions.
> Found a bug or have an idea? Ping the maintainer in the group, or open an issue on [GitHub Issues](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues).
>
> ⚠️ **This group is a community group for the CurrentCortex plugin and is not affiliated with [LeiZ API](https://api.bileizhen.top)**. This plugin is a **community (third-party) plugin** built on top of LeiZ API. Questions about LeiZ API itself — registration, obtaining keys, billing, or service outages — should go to the official LeiZ API website and its official channels, not this group.

---

## 📋 Table of Contents

- [✨ Core Features](#-core-features)
- [🚀 Quick Start](#-quick-start)
- [🎯 Feature Guide](#-feature-guide)
  - [1. Pixiv Random Images](#1-pixiv-random-images-pixiv)
  - [2. Media Content Parsing](#2-media-content-parsing-xhs-bilibili-douyin)
  - [3. NetEase Cloud Music](#3-netease-cloud-music-music)
  - [4. Hitokoto](#4-hitokoto-hitokoto)
  - [5. Weather](#5-weather-weather)
  - [6. Femboy Images](#6-femboy-images-femboy)
  - [7. DG-LAB Device Management](#7-dg-lab-device-management-dglab)
- [🖥️ Master Pages](#️-master-pages)
- [🧩 Per-Group Toggle](#-per-group-toggle)
- [✂️ Segmented Replies](#️-segmented-replies)
- [🤖 LLM Tools](#-llm-tools)
- [🧠 Cross-Group Memory](#-cross-group-memory)
- [⚡ API Connectivity Test](#-api-connectivity-test-apitest)
- [⚙️ Configuration](#️-configuration)
- [❓ FAQ](#-faq)
- [🛠️ Technical Architecture](#️-technical-architecture)
- [🤝 Contributing](#-contributing)
- [📄 License & Acknowledgements](#-license--acknowledgements)

---

## ✨ Core Features

| Module | Capabilities |
| --- | --- |
| 🎨 **Pixiv Random Images** | Random picks / R18 / tag filtering / keyword search / by-author / aspect-ratio filtering / exclude AI works |
| 🔍 **Media Parsing** | Xiaohongshu posts & videos · Bilibili video info · Douyin videos without watermark · Weibo posts & videos |
| 📚 **Media Content Parsing** | Link parsing for Xiaohongshu / Bilibili / Douyin / Weibo |
| 🎵 **Song Requests** | Request, search, voice clips, raw files, fetch by ID (NetEase / Kugou) |
| ✨ **Hitokoto** | 12 categories (anime / manga / games / literature / poetry / film …) |
| 🌤️ **Weather** | Current conditions + 3-day forecast |
| 👗 **Femboy Images** | Random femboy-themed images (WebP) |
| 🔌 **DG-LAB** | Full device lifecycle management over Socket V3/V4 (legacy V2 compatible), protocol auto-detection, multi-user/multi-device isolation, CCDG WebUI control panel |
| 📖 **Wikidot Site Management** | NEW in v2.3.0: edit pages (source / write / append / tags / rename / delete) and manage the site (members / settings / forum / invitations) via Wikidot's front-end JS interface (`/wikidot`). Disabled by default |
| 🖥️ **Master Pages** | All-in-one panel integrated into the AstrBot WebUI: dashboard · help center · visual settings (hot-reload on save) · DG-LAB control (one-click relay server deployment · public-exposure toggle) · contact us |
| 🧩 **Per-Group Toggle** | Turn plugin commands on/off per group with `/toggle` (timed auto-recovery and per-category scope control supported), without affecting other groups |
| 🧠 **Cross-Group Memory** | All groups on a platform share one persistent context, automatically injected into LLM requests (with optional age filtering, LLM summarization, and keyword-based cleanup) |
| ✂️ **Segmented Replies** | Split bot replies into multiple messages sent one by one, mimicking human chatting. Three modes: punctuation / length / LLM semantic |
| 🤖 **LLM Tools** | Register image fetching / song requests / shock control as AI-callable tools (function calling), so the AI can act on natural-language requests on its own |

- **⚡ Async & fast**: built on `asyncio` + `aiohttp` / `websockets`, non-blocking I/O.
- **🛡️ Robust error handling**: friendly messages for network errors, API errors, and bad parameters; song requests retry with exponential backoff.
- **⚙️ Flexible configuration**: every default can be customized in the AstrBot admin panel.
- **👥 Multi-tenant isolation**: every DG-LAB user/device gets fully isolated connections and operations.

---

## 🚀 Quick Start

### 1. Install

**Option 1: Plugin marketplace (recommended)** — search for `astrbot_plugin_currentcortex` in the AstrBot admin panel and install.

**Option 2: Clone manually:**

```bash
cd AstrBot/data/plugins
git clone https://github.com/backrooms-yrc/astrbot_plugin_currentcortex.git
```

### 2. Configure Your API Key (Required)

> 🔐 **LeiZ API authentication**: as of the latest version, **every endpoint (including the free ones) requires an API Key**, sent via the `x-api-key: <API-Key>` request header.

#### Step 1: Get an API Key

Head to the **LeiZ API website** 👉 [https://api.bileizhen.top](https://api.bileizhen.top)

Register / log in, open the "Console / API Keys" page, create a key and copy it (this is the value for `x-api-key`). A single key covers all LeiZ endpoints (Pixiv / Hitokoto / weather / femboy / NetEase Cloud Music) — you only need one.

> 💡 The exact location depends on the website's current layout (e.g. "Console → API Keys / Token management"). If the process changes, follow the site's own instructions.

#### Step 2: Fill It into the Plugin Config

Open the AstrBot admin panel → Plugin Management → this plugin → Config, paste the key into the **`leiz_api_key`** field, save, and reload the plugin.

Without a key, all LeiZ-endpoint commands (Pixiv / Hitokoto / weather / femboy / song requests) are disabled; invoking them shows a guided message about the missing key.

> ⚠️ **This plugin is a community (third-party) plugin built on LeiZ API and is independent of LeiZ API itself**. For API key registration, billing, quotas, and upstream outages, please consult the [LeiZ API website](https://api.bileizhen.top) and its official channels; this plugin's group only handles issues with the plugin itself.

> **Migrating from older versions**: the `femboy_api_key` from v1.3.x and earlier has been merged into a unified `leiz_api_key`. If you left the new field empty but kept the old one, the plugin will automatically use it as the unified key and remind you to migrate — please move it into `leiz_api_key` soon.

### 3. Install Dependencies

```bash
pip install aiohttp>=3.8.0
pip install websockets>=10.0   # only needed for DG-LAB features
```

### System Requirements

- **AstrBot** >= 4.15 (< 5; relies on newer APIs such as `EventMessageType`, handler `priority`, and `ProviderRequest`)
- **Python** >= 3.10
- **aiohttp** >= 3.8.0
- **websockets** >= 10.0 (required for DG-LAB features)
- **ffmpeg** (needed for voice-clip song requests; must be on the system PATH)

---

## 🎯 Feature Guide

> 💡 Send **`/cc`** or **`/cc help`** in chat to get a categorized overview image of all commands.

### Command Cheat Sheet

Every command accepts both Chinese and English aliases:

| Command | Aliases | What it does |
| --- | --- | --- |
| `/pixiv` | `/图片` | Random Pixiv image |
| `/解析` | — | Auto-detect the platform and parse a media link |
| `/xhs` | `/小红书` | Xiaohongshu parsing |
| `/bilibili` | `/B站` `/b站` | Bilibili video parsing |
| `/douyin` | `/抖音` | Douyin video parsing |
| `/weibo` | `/微博` | Weibo post parsing |
| `/music` | `/音乐` | Song requests (NetEase / Kugou) |
| `/点歌` | — | Quick song request (voice clip only) |
| `/音源` | — | Switch song source (auto / NetEase / Kugou) |
| `/hitokoto` | `/一言` | Hitokoto quote |
| `/weather` | `/天气` | Weather lookup |
| `/femboy` | `/男娘` | Femboy image |
| `/dglab` | `/电击` | DG-LAB device management |
| `/开关` | `/toggle` `/switch` | Turn this plugin's commands on/off for a group (timed and per-category scope supported) |
| `/开关列表` | `/switch_list` `/开关状态列表` | List disabled groups and scopes on this platform (admin) |
| `/忘记` | `/forget_memory` `/忘记记忆` | Remove cross-group memory records by keyword (admin) |
| `/帮助` | `/cc` `/help` `/菜单` | Full plugin command overview |
| `/apitest` | `/连通测试` `/接口测试` | API connectivity test |

---

### 1. Pixiv Random Images (`/pixiv`)

Fetches random Pixiv artwork through LeiZ API, with rich filtering and search options.

#### Basic Commands

| Command | Description |
| --- | --- |
| `/pixiv` | Get one random image (default parameters) |
| `/pixiv help` | Show help |

#### Parameters (`key:value` pairs, space-separated, freely combinable)

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `r18:` | int | 0 | R18 mode: `0` = all-ages, `1` = R18 only, `2` = mixed |
| `num:` | int | 1 | How many images to fetch (1-20) |
| `size:` | string | regular | Image size: `original`/`regular`/`small`/`thumb`/`mini` |
| `tag:` | string | — | Tag filter; `\|` inside one tag means **OR**, multiple `tag:` parameters mean **AND** |
| `keyword:` | string | — | Fuzzy search over title / artist / tags |
| `uid:` | int | — | A specific artist's UID |
| `ratio:` | string | — | Aspect-ratio filter, e.g. `gt1.2lt1.8` |
| `excludeAI:` | bool | false | Exclude AI-generated works |

#### Shorthand Syntax

| Shorthand | Equivalent to |
| --- | --- |
| `r18` | `r18:1` |
| `mixed` | `r18:2` |
| `safe` / `sfw` | `r18:0` |

#### Examples

```text
# Basics
/pixiv                          # one random all-ages image
/pixiv r18:1                    # one random R18 image
/pixiv num:5                    # five images at once

# Tag & keyword search
/pixiv tag:白丝 num:3           # 3 images tagged 白丝 (white stockings)
/pixiv keyword:初音ミク num:5   # search for Hatsune Miku
/pixiv tag:萝莉 excludeAI:true  # loli tag, excluding AI works
/pixiv uid:123456 num:3         # works by a specific artist

# Combined filters
/pixiv r18:2 tag:白丝 keyword:初音ミク num:3 size:original

# Shorthand
/pixiv r18                      # same as r18:1
/pixiv mixed                    # same as r18:2
```

#### Sample Response

```text
📷 [1/3]
🎨 Winter Afternoon
👤 Artist: SampleArtist
🔗 https://www.pixiv.net/artworks/12345678
🏷️ Tags: オリジナル / 女の子 / 冬 / 雪
📐 Size: 1920×1080
[image]
```

> 💡 **Random vs. search routing**: with no filter parameters (`tag`/`keyword`/`uid`/`ratio`/`excludeAI`, …) the command hits the GET random endpoint (different results each time); as soon as any filter is present it switches to the POST filtered-search endpoint.

---

### 2. Media Content Parsing (`/xhs` `/bilibili` `/douyin`)

Auto-detects the platform behind Xiaohongshu, Bilibili, Douyin, and Weibo links and returns watermark-free images / video info.

#### Basic Commands

| Command | Description |
| --- | --- |
| `/解析 <link>` | Auto-detect the platform and parse; **a message with multiple links parses them one by one (up to 5)** |
| `/xhs <link>` (`/小红书`) | Xiaohongshu parsing |
| `/bilibili <link>` (`/B站` `/b站`) | Bilibili video parsing |
| `/douyin <link>` (`/抖音`) | Douyin video parsing |
| `/weibo <link>` (`/微博`) | Weibo post parsing |
| `/解析 help` | Show help |

#### Supported Link Formats

| Platform | Formats |
| --- | --- |
| Xiaohongshu | `xiaohongshu.com/explore/xxx`, `xhslink.com/xxx` (short link) |
| Bilibili | `bilibili.com/video/BVxxx`, `b23.tv/xxx` (short link), `avxxx` |
| Douyin | `douyin.com/video/xxx`, `v.douyin.com/xxx` (short link) |
| Weibo | `weibo.com/<uid>/xxx`, `m.weibo.cn/detail/xxx`, `weibo.cn/status/xxx`, `t.cn/xxx` (short link) |

#### Examples

```text
/解析 https://www.xiaohongshu.com/explore/abc123
/解析 https://b23.tv/xxxx https://v.douyin.com/yyyy   # batch: multiple links in one message
/xhs https://xhslink.com/xxxx
/bilibili https://www.bilibili.com/video/BV1xx411c7mD
/douyin https://v.douyin.com/xxxx
/weibo https://m.weibo.cn/detail/xxxxx
```

#### What You Get Back

- **Xiaohongshu**: title, author, likes, description, watermark-free full-resolution images, video link (if any)
- **Bilibili**: title, uploader, duration, views/likes, cover, part (P) info, video download link (if any)
- **Douyin**: title, author, likes/comments/shares, watermark-free video link
- **Weibo**: text, author, reposts/comments/likes, images (up to 9), video link (if any)

#### Parsing Enhancements

- **Graded failure hints**: parse failures no longer dump raw exception text — they are classified by cause (link expired, content deleted/private, platform anti-scraping, network timeout, unrecognized format, etc.) so you can tell link problems from network problems.
- **Result caching**: the same link returns the previous parse result within the validity window (10 minutes by default, adjustable via `media_parse_cache_ttl`), reducing request frequency to target platforms and the chance of triggering anti-scraping/IP bans; only successful results are cached — failures retry in real time.
- **Cross-group memory integration**: with cross-group memory enabled, every successful parse is recorded with the `media` tag ("who parsed what"), so later conversations can naturally refer back to "that video you just sent".

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `media_parse_cache_enable` | bool | true | Enable the parse result cache |
| `media_parse_cache_ttl` | int | 600 | Cache validity in seconds. Download/stream links themselves expire — don't set this too long |

> ⚠️ Make sure the link is publicly accessible; anti-scraping measures on some platforms may cause parsing to fail. Download links are for personal study only — please respect each platform's terms.

---

### Manga Content (formerly section 3, removed)

> ⚠️ Due to relevant regulations, the manga content feature offered by early versions of this plugin was removed entirely in **v2.0.4** and will not return in future versions. Thank you for understanding.

---

### 3. NetEase Cloud Music (`/music`)

Song requests, search, and playback links via LeiZ API, with **NetEase** and **Kugou** as dual sources plus an `auto` routing mode (NetEase first, fall back to Kugou on failure).

#### Switching Sources (`/音源`)

| Command | Description |
| --- | --- |
| `/音源` | Show the current source + available options |
| `/音源 auto` | **Default**. NetEase first; VIP / unavailable / timeout falls back to Kugou |
| `/音源 网易云` | NetEase only |
| `/音源 酷狗` | Kugou only |

The source is remembered **per conversation (group / DM)** without cross-talk; it resets to the default after a restart (`music_default_source`, default `auto`).

#### Basic Commands

| Command | Description |
| --- | --- |
| `/music <song>` (`/音乐`) | Request a song (searches and returns full details for the first hit) |
| `/music direct <song>` (`/音乐 直接`) | Return only a transcoded voice clip |
| `/点歌 <song>` | Shortcut, equivalent to `/音乐 直接` — voice clip only |
| `/music file <song>` (`/音乐 文件`) | Return the original, un-transcoded audio file |
| `/music id:<song ID>` | Fetch details by ID |
| `/music search <keyword>` | Search and list songs |
| `/music help` | Show help |

#### Examples

```text
/music 孤勇者              # request a song
/music 周杰伦 晴天         # search "周杰伦 晴天" (Jay Chou - Sunny Day)
/music direct 孤勇者       # voice clip only
/点歌 孤勇者               # shortcut
/music file 孤勇者         # original audio as attachment
/music id:1901371647       # fetch by ID
/music search 陈奕迅       # search and list songs
```

#### What You Get Back

Song name, artist, album, cover, quality (bitrate / format / level), file size, and playback link. On QQ the playback link is automatically resolved into a **voice clip** (relies on the framework's `Record` message segment; falls back to a text link when unsupported).

> ⚠️ Some VIP songs may not expose a playback link; links are time-limited, so use them promptly. The voice-clip feature requires `ffmpeg` on the system.

> 📦 **File mode & large files**: under QQ/NapCat, `/音乐 文件` prefers the OneBot local upload path (`upload_group_file` / `upload_private_file`), avoiding the `Comp.File` HTTP-callback round trip through a misconfigured `callback_api_base` that often fails with "download file failed" in the logs. Original audio (especially lossless flac) can be huge; when the file exceeds `music_file_max_bytes` (default 25MB) the plugin automatically transcodes it to a 128kbps MP3 before sending (requires `ffmpeg`), typically shrinking it by ~90%. Raise the threshold if you really need the untouched lossless file (not recommended — sends often fail). Downloads automatically retry on timeout / network errors.

> 🚫 **Anti-spam protection**: to stop rapid-fire requests from spawning masses of concurrent downloads/transcodes, song requests have built-in in-flight deduplication plus a cooldown (`music_cooldown`, default 3 seconds). Requesting again while the previous song is still processing gets a "please wait" message; requesting again immediately after one finishes gets a "that was fast!" message. Different groups / DMs don't affect each other.

---

### 4. Hitokoto (`/hitokoto`)

Fetches a random community-contributed quote.

#### Basic Commands

| Command | Description |
| --- | --- |
| `/hitokoto` | Random quote (all categories) |
| `/hitokoto <category code>` | A specific category |
| `/hitokoto help` | Show help |

#### Categories

| Code | Category | Code | Category |
| --- | --- | --- | --- |
| a | Anime | g | Other |
| b | Manga | h | Film & TV |
| c | Games | i | Poetry |
| d | Literature | j | NetEase Cloud Music |
| e | Original | k | Philosophy |
| f | From the web | l | Witticisms |

```text
/hitokoto a    # an anime quote
/hitokoto i    # a poetry quote
```

---

### 5. Weather (`/weather`)

Looks up current conditions for a city plus a 3-day forecast.

```text
/weather 广州市      # weather for Guangzhou
/weather 北京        # weather for Beijing
/weather help        # show help
```

Covers major Chinese cities; Chinese city names are recommended (up to 50 characters). Returns current temperature / condition / feels-like / wind / humidity plus a 3-day forecast.

---

### 6. Femboy Images (`/femboy`)

Returns a random femboy-themed image (WebP).

```text
/femboy          # a random femboy image
/femboy help     # show help
```

> Requires `leiz_api_key` to be configured first — see [Quick Start](#2-configure-your-api-key-required).

---

### 7. DG-LAB Device Management (`/dglab`)

Full control of DG-LAB pulse boxes over the DG-LAB Socket protocol. **Requires a running [DG-LAB WebSocket relay server](https://github.com/dungeonlab-open/dglab-websocket-server)**.

> 📡 **Protocol versions**: the official relay repository has dropped the v2 server and now ships only **v3** (`bun run v3`, default port 9999) and **v4** (`bun run v4`, default port 9998). Since v2.0.0 the plugin **auto-detects** the relay's protocol (V3 / V4, with legacy V2 relays still supported) — it just works after upgrading, no config changes needed. You can also pin it manually via the `dglab_protocol` option (`auto` / `v3` / `v4`).
>
> - **V3**: QR code format matches the old one; both the DG-LAB app and the DG-LAB 4 app can scan it;
> - **V4**: uses the new QR code format (`dungeon-lab.cn/s/?v=1&action=socket&url=...`) and requires the **DG-LAB 4 app**; strength control is dispatched via `device.op` tasks (absolute strength is converted into a delta from the value reported by the app, falling back to a temporary strength task when no value is reported).

#### Basic Commands

| Command | Description |
| --- | --- |
| `/dglab bind [server address]` | Bind a new device (generates a QR code for the app to scan; multiple devices supported) |
| `/dglab unbind [index]` | Unbind a device (index required when you have several) |
| `/dglab strength [index] <A\|B> <0-200>` | Set channel strength (defaults to device #1 when the index is omitted) |
| `/dglab up [index] <A\|B> [step]` | Increase strength (default +5) |
| `/dglab down [index] <A\|B> [step]` | Decrease strength (default -5) |
| `/dglab shock [index] <A\|B> [strength] [wave] [seconds]` | Start stimulation |
| `/dglab stop [index] [A\|B]` | Stop stimulation (zero strength + clear waves) |
| `/dglab pulse [index] <A\|B> <preset\|HEX> [seconds]` | Send wave data (default 5 seconds) |
| `/dglab clear [index] <A\|B>` | Clear the wave queue |
| `/dglab feedback [index]` | Show live strength and feedback-button state |
| `/dglab permission [on\|off]` | View / toggle permission isolation (on by default) |
| `/dglab status` | Show binding & connection state of all devices |
| `/dglab info` | Show detailed info for all devices |
| `/dglab help` | Show help |

> 💡 **Multiple devices**: one user can bind several devices, addressed by index (1/2/3…); the index defaults to #1. Controlling someone else's device looks like: `/dglab strength @userID 2 A 50`.

#### Wave Presets

| Preset | Effect | Preset | Effect |
| --- | --- | --- | --- |
| `breathe` | Slow swell and fade | `needle` | High-frequency continuous prickle |
| `pulse` | Fast intermittent pulses | `throb` | Low-frequency slow undulation |
| `wave` | Continuous rolling waves | `chaos` | Random alternation of strong and weak |
| `tap` | Short single taps | `heartbeat` | Double-beat heart rhythm |

#### Typical Workflow

```text
1. Bind a device
   /dglab bind ws://192.168.1.100:9999
2. Scan the QR code with the DG-LAB app to complete binding
3. Control the device
   /dglab shock A 50 breathe 10   # channel A (strength 50, breathe wave, 10s)
   /dglab strength A 50           # set channel A strength only
   /dglab pulse A wave 5          # send the wave preset for 5s
   /dglab up B 10                 # channel B strength +10
   /dglab stop                    # stop all output
4. Check status
   /dglab status
   /dglab feedback
5. Unbind (optional)
   /dglab unbind
```

#### CCDG WebUI Control Panel

With `dglab_webui_enabled` turned on, the plugin serves a CCDG WebUI remote-control interface at `dglab_webui_host`:`dglab_webui_port` (default `127.0.0.1:9178`) — view and control devices from a browser, in Material Design 3 style.

> ⚠️ **CCDG WebUI security (important)**
> - Since v1.5.3 the **WebUI is off by default** (`dglab_webui_enabled` defaults to `false`) and must be enabled manually.
> - It listens on `127.0.0.1` by default (local access only). **To expose it, set `dglab_webui_host` explicitly to `0.0.0.0` and put a reverse proxy with access control in front of it** (e.g. Nginx + Basic Auth / IP allowlist).
> - Alternatively, use the "Expose to public network" toggle in **Master Pages → DG-LAB Control** to flip between `127.0.0.1` / `0.0.0.0` in one click (with a confirmation dialog and public-link display; opening it automatically allows the port through ufw, closing it / disabling the WebUI revokes the rule).
> - The WebUI has its own user registration / login system, **unrelated to the bot or platform accounts**: anyone who can reach the port can register an account. Do not expose it to the public internet without protection.
> - Recommended: keep it local, or expose it only within a LAN / behind a reverse proxy with authentication.

#### Advanced Traits

- **Multi-user isolation**: every user gets independent connections and bindings, up to 50 concurrent connections.
- **Auto-reconnect**: failed operations retry automatically (up to 2 times); dropped connections are re-established; idle connections are cleaned up after 5 minutes.
- **Safety**: all parameters strictly validated, operations guarded by timeouts, strength capped at 0-200.

> ⚠️ Only the **DG-LAB (Coyote) 3.0 pulse box** is supported; QR codes are valid for the duration of a session and must be regenerated after expiry; `ws://` is recommended on LANs, `wss://` over the public internet.

---

## 🖥️ Master Pages

> Since **v1.9.0**, the plugin ships an all-in-one AstrBot Pages panel (mdui 2 Material Design 3 style, sky-blue + snow-white theme). Open it from the AstrBot WebUI under **Plugin Details → Pages** (or the "Plugin Pages" group in the sidebar).

The panel has 5 pages:

| Page | Description |
| --- | --- |
| 📊 **Dashboard** | Plugin overview: uptime, bound devices, active connections, registered users, plugin version / author / start time, feature-toggle states |
| 📖 **Help Center** | Built-in docs and FAQs (quick start / DG-LAB / segmented replies / cross-group memory / troubleshooting) |
| ⚙️ **Settings** | Edit every plugin option visually: each has a friendly name and plain-language explanation; saving **hot-reloads** the config — no restart needed |
| ⚡ **DG-LAB Control** | One-click relay server deployment (v3/v4 · public-exposure toggle) + master switch for the CCDG WebUI + **public-exposure toggle** (see below) |
| 💬 **Contact Us** | Developer info, GitHub repository, QQ group (one-click join) |

#### DG-LAB Control: Public-Exposure Toggle

- **WebUI master switch**: only enables the CCDG WebUI, which keeps listening on `127.0.0.1` (local access only — **not** considered public exposure).
- **Public-exposure toggle** (requires the WebUI enabled first): turning it on switches `dglab_webui_host` to `0.0.0.0` (port `dglab_webui_port`, default `9178`), detects the server's public IP, and shows a public link; turning it off restores `127.0.0.1`.
- Enabling exposure pops a **confirmation dialog** and keeps a persistent security warning visible; turning off the WebUI master switch also resets the listen address to `127.0.0.1`, so no exposed config lingers.

> ⚠️ **Security reminder**: listening on `0.0.0.0` means any address on the internet can reach the WebUI's registration / login / device endpoints. Put a **reverse proxy + authentication** in front of it first (e.g. Caddy + BasicAuth, Nginx + IP allowlist, Cloudflare Zero Trust) — otherwise anyone might end up controlling your DG-LAB device.

#### DG-LAB Control: One-Click Relay Server Deployment (v3/v4)

The DG-LAB control page can deploy the official v3 / v4 relay server ([dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server), Bun runtime) directly on your server — no command line needed:

- **Auto-detection**: v3 (port 9999) and v4 (port 9998) are detected and managed independently; deployments show their running state, systemd service name, and source version, and can be uninstalled in one click (manually deployed legacy services are recognized and adopted too)
- **One-click deployment**: automatically installs Bun → clones the official repo → writes the config → installs dependencies → creates a persistent systemd service (auto-start on boot, auto-restart on crash) → runs a protocol self-check; the whole thing takes roughly 10-60 seconds
- **Public-exposure toggle** (off by default): the official server always listens on all interfaces, so "local vs. public" reachability is governed by the firewall — while off, the port stays blocked (only local `ws://127.0.0.1:port` works, and the page shows the local address); turning it on allows the port through ufw, probes and displays the public address `ws://<public-IP>:port`, and turning it off revokes the rule. A confirmation dialog precedes every change
- **Uninstall**: stops and removes the systemd service and revokes the firewall rule; the source directory is kept, so re-deploying takes seconds

> ⚠️ **Security reminder**: once the relay port is open, any DG-LAB app that obtains the address can connect to your relay. Prefer enabling it only while in use. Deployment/uninstall requires systemd and ufw (AstrBot must run as root).

---

## 🧩 Per-Group Toggle

Each group can independently turn this plugin on or off without affecting others. For example, if a group doesn't want images / song requests, disable it there while every other group keeps working.

#### Basic Commands

| Command | Description |
| --- | --- |
| `/开关 off` | **Disable permanently** all plugin commands in this group (pixiv / parsing / music / … all stop responding) |
| `/开关 off <duration>` | **Timed disable** with automatic recovery, e.g. `/开关 off 2h`, `/开关 off 30m`, `/开关 off 1d`, `/开关 off 2小时30分钟` |
| `/开关 off <scope> [duration]` | **Disable one category only**, e.g. `/开关 off media 2h` turns off just media parsing for 2 hours |
| `/开关 on` | **Re-enable** the plugin's commands in this group (also ends a timed disable early) |
| `/开关 on <scope>` | Re-enable one category only, e.g. `/开关 on media` |
| `/开关 status [scope]` | Show the current state for this group (timed disables show the estimated recovery time) |
| `/开关列表` (`/switch_list` `/开关状态列表`) | **Admin**: list all disabled groups (with scopes) on this platform and their recovery times |
| `/开关` | No argument = show status + usage hint |

> Aliases: `/toggle`, `/switch` (e.g. `/toggle off 2h`). The Chinese command `/开关` also accepts `关` (off) / `开` (on) / `状态` (status) as arguments. Duration units: `s`/`秒`, `m`/`分`/`分钟`, `h`/`时`/`小时`, `d`/`天` — combinable.
>
> **Scopes** (optional; omit = global, all commands): `media` media parsing · `image` image fetching · `music` song requests · `utility` utilities · `dglab` DG-LAB devices · `memory` cross-group memory. Chinese names also work (e.g. `/开关 off 图片`).

#### Example

```text
/开关 off       # turn off all CurrentCortex commands in this group permanently
/开关 off 10h   # turn off for 10 hours (e.g. overnight do-not-disturb; auto-recovers)
/开关 off media 2h   # turn off only media parsing for 2 hours; songs/images keep working
/开关 status media   # media scope state (⏳ auto-recovers in 1h58m)
/开关列表       # admin: list all disabled groups and scopes on this platform
/开关 on media  # re-enable media parsing only
/开关 on        # re-enable (works for permanent and timed disables)
```

#### How It Works

- **Persistent state**: stored in `data/currentcortex_group_switch.json` and survives restarts. The default (never configured) is **enabled** — only groups explicitly turned off with `/开关 off` are disabled.
- **Scoped toggles**: storage keys are `umo` (global) or `umo|scope` (one category); a global disable takes precedence over any scope entry; legacy data (plain `umo` keys) is treated as global disables — no migration needed.
- **Timed auto-recovery**: `/开关 off [scope] <duration>` recovers automatically when it expires (lazy expiry check, no background timer needed); the countdown survives restarts.
- **One-shot hint while disabled**: the first use of an affected command after a disable gets a short hint (e.g. "media parsing is disabled in this group"), throttled to once per hour per group per category. Disable via `group_switch_hint_enable`.
- **Never deadlocks**: the `/开关` and `/开关列表` commands themselves **always work** — even in a disabled group, `/开关 on` re-enables it; they are never intercepted.
- **Permissions**: by default only **group admins** (as identified by the framework) may operate it, preventing random members from flipping the switch. If you aren't recognized as an admin, disable `group_switch_admin_only` in the config. `/开关列表` is always admin-only.
- **Scoped to this plugin**: the toggle only intercepts CurrentCortex commands; other AstrBot plugins and core bot features are unaffected.
- **⚠️ LLM tools are not scope-limited**: scopes constrain user commands only; abilities the AI invokes on its own via LLM tools (images/songs/DG-LAB) bypass command entry points and are unaffected by scope disables (a global disable still blocks them). If that matters, also turn off `llm_tools_enable`.
- **DMs unaffected**: the toggle applies to group chats only.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `group_switch_enable` | bool | true | Enable the per-group toggle feature (when off, the guard doesn't run at all) |
| `group_switch_admin_only` | bool | true | Only group admins may use `/开关` |
| `group_switch_hint_enable` | bool | true | Reply with a one-shot hint on first command use while disabled (once per hour per group per category) |

---

## ✂️ Segmented Replies

Optional feature: splits the bot's replies into **multiple messages sent one by one**, mimicking the rhythm of real chatting so long replies feel more natural and human. Off by default; enable it manually in the config panel.

#### How It Works

Once enabled, the plugin intercepts outgoing replies, splits the full text into segments according to the selected rules, and sends them one at a time with random delays in between (the first segment goes out immediately).

> ⚠️ **Relationship with the framework's built-in feature**: AstrBot already offers a global "segmented reply" capability (`Platform Settings → Segmented Reply`). **This plugin feature is independent of it — do not enable both**, or replies will be segmented twice. Pick one: if you've enabled it at the framework level, leave this one off.

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `reply_seg_enable` | bool | false | **【Master switch】** turn segmented replies on |
| `reply_seg_only_llm` | bool | true | Only segment LLM replies; when off, command replies (like `/pixiv`) get segmented too. Recommended: keep on |
| `reply_seg_mention` | bool | true | Whether the first segment @-mentions and reply-quotes the user (giving the segments a clear owner). Automatically degrades on platforms without reply-quotes |
| `reply_seg_mode` | string | llm | Segmentation mode (dropdown): `llm` = LLM semantic splitting (default, recommended, smartest), `punct` = split at punctuation (lightest), `length` = split by length (see below) |
| `reply_seg_llm_provider_id` | string | `""` | **llm mode only**: provider ID of the LLM used for splitting. Empty = reuse the current conversation's model; a cheap, fast model is recommended |
| `reply_seg_llm_density` | string | `medium` | **llm mode only**: segmentation density, i.e. target characters per segment. `low` = long segments (~40-70 chars, fewer cuts), `medium` = balanced (~20-45), `high` = short snappy segments (~10-25). The segment-count cap is derived automatically and fed to the model |
| `reply_seg_llm_max_segments` | int | `0` | **llm mode only**: hard cap on segment count. `0` = derive from the density level (low=3 / medium=5 / high=8); a manual cap merges any overflow into the last segment |
| `reply_seg_llm_min_chars` | int | 30 | **llm mode only**: texts shorter than this skip the LLM entirely and are sent whole (recommended 20~50) |
| `reply_seg_llm_timeout` | int | 30 | **llm mode only**: per-call timeout in seconds; on timeout it degrades to rule-based splitting. The default 30s covers most models (reasoning models included) |
| `reply_seg_split_symbols` | string | `。！？!?~～…` + newline + `,，` | punct/length modes: single-character split symbols (splits occur at these symbols, which stay at the end of the segment). Chinese and English commas are included by default |
| `reply_seg_split_words` | string | `喵 qwq owo awa ovo` | punct/length modes: split words (may be multi-character, **space-separated**); the split happens after the word, which stays at the end of the segment. ⚠️ Prefer multi-character words only: single-character words (like `w`) mangle English words, and a lone left bracket `（` breaks pairing — neither is included by default |
| `reply_seg_merge_threshold` | int | 4 | punct mode: merge threshold for short segments. Segments shorter than this are merged into the previous one, and **pure-punctuation segments (like a lone 「。」) merge unconditionally** — eliminating comma debris and stray punctuation. `0` disables merging |
| `reply_seg_min_length` | int | 15 | length mode: minimum segment length; no splitting below it (recommended 10~30) |
| `reply_seg_max_length` | int | 80 | length mode: maximum segment length; beyond it, a split point (symbol or word) is searched backwards within `[min, max]`, with a hard cut only if none is found (recommended 50~150) |
| `reply_seg_delay_range` | string | `0.8,2.5` | Random delay range between segments (seconds), format `min,max` |

#### The Three Segmentation Modes

- **`punct` (by punctuation)**: break at every split symbol / word. The lightest mode, fine for most conversations. Afterwards, **overly short and pure-punctuation segments (like a lone 「。」) are merged** into the previous segment to avoid debris (controlled by `reply_seg_merge_threshold`, can be disabled).
- **`length` (by length)**: when a segment would exceed the max length, a split point (symbol or word) is searched backwards within `[min length, max length]`; only hard-cut if none exists. Good for keeping every segment within bounds.
- **`llm` (LLM semantic splitting)** ⭐ recommended: calls an LLM to split by **semantic completeness**, the way a person speaks sentence by sentence — no dicing at commas, kaomoji stay attached, and lists / parallel structures are grouped by topic. Smarter than rule-based splitting, at the cost of **one extra LLM call** per reply (1~3s extra latency plus a few tokens); short replies (below `reply_seg_llm_min_chars`) skip the call automatically. `reply_seg_llm_density` offers low / medium / high density to control the size of each segment.

> 💡 **Tips for `llm` mode**: set `reply_seg_llm_provider_id` to a **cheap, fast model** (e.g. deepseek-v3) instead of burdening your main model. If no provider is configured, the current conversation's model is reused; on call failure, parse errors, or wild length deviations it **degrades automatically** to punct rule-based splitting — normal replies are never affected.
>
> 💡 **Density** (`reply_seg_llm_density`): `low` = longer segments (~40-70 chars, information-dense, fewer cuts), `medium` = balanced (~20-45), `high` = short bursts (~10-25, playful rapid-fire). Each level derives a segment-count cap that's written into the prompt to steer the model; for exact control, set a hard cap with `reply_seg_llm_max_segments`.

> 💡 In `punct` / `length` modes you can also configure **split words** (`reply_seg_split_words`, space-separated) in addition to punctuation, breaking after kaomoji / interjections like `喵`, `qwq`, `owo`. Both rule-based modes honor symbols and words simultaneously.

#### Notes

- The full, unsegmented reply is still written back into conversation history, so context stays coherent.
- Segmentation applies to **plain-text** replies only; images, files, etc. are never split.
- If anything goes wrong during segmentation, the reply falls back to being sent as one message (normal usage is unaffected).

---

## 🤖 LLM Tools

Optional feature: registers the plugin's image fetching, song requests, shock control, and more **as tools the LLM can call (function calling)**, so the AI can handle **natural-language requests** like "send me a catgirl pic", "play Sunny Day", or "set channel A strength to 50" on its own — no `/` commands needed; the AI judges the intent and invokes the matching tool. On by default; turn it off with `llm_tools_enable` in the config panel if you don't want it.

> ⚠️ Shock control involves a physical device and carries real risk — make sure it's safe before enabling. Every tool checks the master switch on its first line; when off, tools return an explanation instead of executing.

#### Registered Tools (11 in total)

| Category | Tool | Parameters | Description |
| --- | --- | --- | --- |
| 🖼️ Images | `get_pixiv_random` | num, r18 | Random anime illustrations |
| 🖼️ Images | `search_pixiv` | keyword, num, r18 | Search illustrations by keyword |
| 🖼️ Images | `get_pixiv_by_tags` | tags, num, r18 | Filter precisely by tags (multi-tag AND) |
| 👗 Femboy | `get_femboy_image` | none | Random femboy image |
| 🎵 Songs | `play_song` | song_name | Search and request a song (voice clip) |
| ⚡ Shock | `dglab_shock` | channel, strength, wave, duration, device_index | Start stimulation |
| ⚡ Shock | `dglab_strength` | channel, value, device_index | Set absolute strength |
| ⚡ Shock | `dglab_strength_adjust` | channel, direction, step, device_index | Raise / lower strength |
| ⚡ Shock | `dglab_pulse` | channel, wave, duration, device_index | Send a wave |
| ⚡ Shock | `dglab_stop` | channel, device_index | Stop output |
| ⚡ Shock | `dglab_status` | none | Query device status |

#### How It Works

- **Zero rewrites**: tools reuse the existing business logic wholesale (images via `_process_response`, songs via `_search_and_get`, shock via `_dispatch_command`) — no duplicated code.
- **Media delivery**: image / song / femboy tools send media directly with `event.send` and `return` a one-line note to the AI (like "2 images sent"), preventing the AI from repeating it as text.
- **Shock safety**: shock tools reassemble the AI's structured parameters into a command string and go through `_dispatch_command`, **fully inheriting permission checks, cross-user isolation, and device resolution**. Strength is clamped to 0-200; wave presets are validated by the existing logic.
- **Graceful degradation**: with no API key configured or no device connected, tools return a friendly note instead of raising an error.

#### Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `llm_tools_enable` | bool | true | **【Master switch】** on = all tools registered; off = none take effect (only the original `/` commands remain) |

> 💡 Once enabled, the AI decides on its own when to call a tool. For "send me a loli pic" it calls `get_pixiv_random`; for "I want to hear Sunny Day" it calls `play_song`; for "shock me" it calls `dglab_shock` (requires a shock device to be bound and connected).

---

## 🧠 Cross-Group Memory

Optional feature: shares one **persistent** memory across all groups on the same platform instance and injects it into LLM requests as extra context, giving the bot a continuous thread between different groups.

- **Storage**: `data/currentcortex_cross_group.json`, bucketed per platform instance (`platform_id`), preserved across restarts.
- **Recording**: non-command group messages are formatted as `[nickname/HH:MM:SS]: text` and appended in a rolling fashion (old records are trimmed past the cap).
- **Injection**: when a group message triggers an LLM request, the most recent records from the other groups on the same platform are injected into the user-message part as a `<system_reminder>`; with `cross_group_max_age_hours` set, only records within that window are injected, so cold groups no longer dig up stale topics.
- **LLM summarization (optional)**: with `cross_group_summary_enable` on, once the record count exceeds the threshold the raw records are first compressed by an LLM into a short topical digest ("recently people have been talking about X, Y") before injection — fewer tokens, more focused. Failures (no provider / timeout / empty result) fall back to raw-record injection; the same memory reuses its digest for 5 minutes. Note: this adds one LLM call (up to 20 s) on the reply path — configure a cheap, fast model.
- **Slash commands never recorded**: command messages don't enter memory.
- **Keyword cleanup**: admins can send `/忘记 <keyword>` (aliases `/forget_memory` `/忘记记忆`) to delete every record containing that keyword from this platform's memory (substring match, case-insensitive) — precise cleanup of mis-recorded content without wiping the whole platform's memory.

| Option | Default | Description |
| --- | --- | --- |
| `cross_group_enable` | false | Enable cross-group memory |
| `cross_group_max_cnt` | 500 | Maximum records kept per platform |
| `cross_group_inject_cnt` | 30 | Recent records injected per reply |
| `cross_group_max_age_hours` | 0 | Only inject records from the last N hours (`0` = no age limit, trim by count only, i.e. the old behavior; 12~48 recommended) |
| `cross_group_summary_enable` | false | Enable LLM summarization (compress records into a topical digest when above the threshold) |
| `cross_group_summary_threshold` | 20 | Injection count threshold that triggers summarization (below it, raw records are injected directly) |
| `cross_group_summary_provider_id` | (empty) | Dedicated model for summaries; empty = reuse the current session model. A cheap, fast non-reasoning model is recommended |

> ⚠️ Enabling this feeds the chat content of other groups to the LLM — make sure that matches your privacy expectations and that the members of each group are aware and consenting.

---

## ⚡ API Connectivity Test (`/apitest`)

Diagnoses the auth & connectivity of every LeiZ upstream endpoint in one shot, so you can tell "the API is down" from "something's wrong locally".

```text
/apitest          # probe all 6 endpoints in parallel
/apitest help     # show help
```

5 endpoints (Pixiv / Hitokoto / weather / femboy / songs) are probed in parallel, each with the lightest possible read-only request — no image/audio download traffic is consumed. Status meanings:

| Icon | Status | Meaning |
| --- | --- | --- |
| 🟢 | OK | Endpoint returned success |
| 🟡 | HTTP error | Non-200 response (e.g. 401 auth failure / 402 quota / 5xx) |
| 🔴 | Network / timeout | Connection failed or exceeded the configured timeout |
| ⚫ | Skipped | The corresponding client isn't initialized (usually no API key configured) |

---

## ⚙️ Configuration

Path: AstrBot admin panel → Plugin Management → this plugin → Config.

### Pixiv

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `default_r18` | int | 0 | Default R18 mode (0 = all-ages, 1 = R18 only, 2 = mixed) |
| `default_num` | int | 1 | Default number of images per fetch (1-20) |
| `default_size` | string | regular | Default image size (original/regular/small/thumb/mini) |
| `image_proxy` | string | pixiv.bileizhen.top | Image reverse-proxy domain |
| `exclude_ai` | bool | false | Exclude AI-generated works by default |

### General / Auth

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `leiz_api_key` | string | (empty) | **Unified LeiZ API key** (`x-api-key` header), **required**. Obtain it after registering on the [LeiZ API website](https://api.bileizhen.top); needed by every LeiZ endpoint |
| `request_timeout` | int | 15 | API request timeout (seconds); affects all features |

### Music

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `music_file_max_bytes` | int | 26214400 | Size cap per file for `/音乐 文件` (bytes, default 25MB). Larger files are transcoded to 128kbps MP3 before sending (requires ffmpeg); `0` = no limit (not recommended — sends often fail) |
| `music_cooldown` | int | 3 | Minimum interval between song requests in the same conversation, to stop rapid-fire requests from spawning masses of concurrent downloads/transcodes. In-flight requests get a "please wait"; `0` = no limit (not recommended) |
| `music_default_source` | string | auto | Default song source: `auto` (NetEase first, fall back to Kugou) / `netease` (NetEase only) / `kugou` (Kugou only). Users can still override per conversation with `/音源` |

### DG-LAB

> ⚠️ Before using DG-LAB features you must deploy and run a [DG-LAB WebSocket relay server](https://github.com/dungeonlab-open/dglab-websocket-server) (the official repo now ships only v3 / v4 servers; v2 is gone).

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `dglab_server_url` | string | (empty) | Relay server address (e.g. `ws://192.168.1.100:9999`; for V4 include any path prefix, e.g. `wss://host:9998/v4`) |
| `dglab_protocol` | string | auto | Relay protocol version: `auto` = auto-detect (recommended) / `v3` (default port 9999, legacy V2 relays compatible) / `v4` (default port 9998, requires the DG-LAB 4 app to scan) |
| `dglab_heartbeat_interval` | int | 60 | Heartbeat interval (seconds); 30-120 recommended |
| `dglab_auto_connect` | bool | false | Auto-connect on plugin startup (usually keep false) |
| `dglab_webui_enabled` | bool | false | Enable the CCDG WebUI panel (**off by default**; enable manually once you understand the risks) |
| `dglab_webui_host` | string | 127.0.0.1 | CCDG WebUI listen address (local-only by default; public exposure requires explicitly setting `0.0.0.0` plus a reverse proxy + auth) |
| `dglab_webui_port` | int | 9178 | CCDG WebUI listen port |

<details>
<summary><b>📦 Deploying the DG-LAB relay server (Bun)</b></summary>

1. Get the server code: [dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server)
2. Install [Bun](https://bun.sh), then start the server for your protocol version:
   ```bash
   bun run v3     # V3 server, default port 9999 (works with the legacy app)
   bun run v4     # V4 server, default port 9998 (requires the DG-LAB 4 app)
   ```
3. Ports etc. can be changed via `.env` (`PORT` / `PREFIX`, … — see the repo's README)
4. Make sure both AstrBot and the DG-LAB app can reach the server; on `/dglab bind` the plugin auto-detects the protocol version and labels it in the response

</details>

<details>
<summary><b>❓ Connection troubleshooting (re: <a href="https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues/3">issue #3</a>)</b></summary>

- **`server never confirmed connection: waiting for server-assigned clientId timeout`**: older versions (≤ v1.9.1) put a self-generated clientId in the connection path per the v2 protocol, which v3 servers misread as the app side and reject. Upgrade to v2.0.0+ — since v2.0.0 the controller connects to the bare root path and uses the server-assigned clientId.
- **`connection failed: server rejected WebSocket connection: HTTP 404`**: you're hitting a v4 server with an extra path in the address. The v4 server only accepts connections on the root path (or the path configured via `PREFIX`); check that `dglab_server_url` matches the path the server actually listens on.
- **V4 binding works but control does nothing**: make sure you scanned with the **DG-LAB 4 app** (the legacy app can't read the new `dungeon-lab.cn/s/...` QR codes); if the app shows multiple device slots, the plugin automatically picks the first slot with a real device connection.

</details>

<details>
<summary><b>🔄 Migrating from the legacy DG-LAB JSON config</b></summary>

v1.2.0 and earlier used a JSON string config (deprecated):

```json
{ "dglab": { "server_url": "ws://your-server:9999", "heartbeat_interval": 60, "auto_connect": false } }
```

The new format uses three standalone options: `dglab_server_url`, `dglab_heartbeat_interval`, `dglab_auto_connect`. The plugin still detects the legacy `dglab` JSON: if the new options are empty but the old config exists, it's read automatically with a migration notice. Please migrate manually soon.

</details>

### Cross-Group Memory

See the [🧠 Cross-Group Memory](#-cross-group-memory) section.

### Segmented Replies

See the [✂️ Segmented Replies](#️-segmented-replies) section.

### LLM Tools

See the [🤖 LLM Tools](#-llm-tools) section. The switch is `llm_tools_enable` (on by default).

### Plugin Promotion (QQ Group)

The plugin ships with the official group number **1106353813** built in — active right after installation, zero configuration. The number surfaces in two places:

- **The `/交流群` command** (aliases `/群号` `/加群`): returns the group number on request
- **Command help / error messages**: help texts like `/pixiv help`, `/点歌 help` and "API key not configured" errors end with a one-line group number

> ⚠️ The group number is **never** injected into the bot's everyday replies, keeping conversations clean.

---

## ❓ FAQ

<details>
<summary><b>The plugin won't load after installation?</b></summary>

1. Is Python >= 3.10?
2. Are dependencies installed: `pip install aiohttp>=3.8.0` (DG-LAB also needs `websockets>=10.0`)?
3. Is AstrBot >= 4.15? (This plugin needs newer APIs; older versions can't load it.)
4. Check the error details in the AstrBot logs.

</details>

<details>
<summary><b>Commands say "feature not enabled / API key not configured"?</b></summary>

Get an API Key from the [LeiZ API website](https://api.bileizhen.top) first (see [Configure Your API Key](#2-configure-your-api-key-required)), paste it into the `leiz_api_key` field in the config panel, save, and reload the plugin. `/apitest` verifies each endpoint's connectivity. Pixiv / Hitokoto / weather / femboy / songs all depend on this key.

</details>

<details>
<summary><b>Pixiv images won't display?</b></summary>

1. Broken reverse proxy: try changing the `image_proxy` option
2. Network issues: check whether the server can reach the internet
3. API outage: try again later

</details>

<details>
<summary><b>How do I exclude AI-generated Pixiv works?</b></summary>

1. **Globally**: set `exclude_ai` to `true`
2. **One-off**: add `excludeAI:true` to a command, e.g. `/pixiv tag:萝莉 excludeAI:true`

</details>

<details>
<summary><b>Requests keep timing out?</b></summary>

Raise `request_timeout` (seconds) a bit and check your network; frequent timeouts usually mean the API is busy — retry later.

</details>

<details>
<summary><b>Which cities does the weather lookup support?</b></summary>

Major Chinese cities; Chinese city names are recommended (e.g. 「广州市」, 「北京」), up to 50 characters.

</details>

<details>
<summary><b>DG-LAB features don't work / binding fails?</b></summary>

1. Is the dependency installed: `pip install websockets>=10.0`?
2. Is `dglab_server_url` configured, and is the relay server running and reachable?
3. QR codes must be scanned by the app before they expire
4. Confirm the app version supports Socket V2, and that the device is a **DG-LAB 3.0 pulse box** (the only supported hardware)
5. Check `[DGLab]` errors in the AstrBot logs

</details>

<details>
<summary><b>The DG-LAB connection dropped — what now?</b></summary>

Reconnection is automatic (up to 2 attempts); if it still fails, `/dglab unbind` then `/dglab bind` again, and check `/dglab status`.

</details>

<details>
<summary><b>Do simultaneous users interfere with each other?</b></summary>

No. Every user has independent device bindings and connections, fully isolated, with up to 50 concurrent connections.

</details>

### Error Handling Overview

| Error | Likely cause | Fix |
| --- | --- | --- |
| Network error | Connection failure | Check your network |
| Request timeout | Slow API | Raise `request_timeout` or retry later |
| HTTP error | API problem (401/402/5xx …) | Check your API key / service status |
| Bad parameters | Wrong command format | Send `/xxx help` |
| No results | Nothing matched | Change your search parameters |
| Malformed data | API returned junk | Retry later |

---

## 🛠️ Technical Architecture

### Project Structure

```text
astrbot_plugin_currentcortex/
├── main.py                      # Main program: all command registration & API clients
├── _pages_api.py                # Master Pages backend API (dashboard/settings/DG-LAB/help)
├── pages/                       # Master Pages frontend (mdui 2 component library, fully local)
│   └── cc-dashboard/
│       ├── index.html           # Pages entry
│       ├── app.js               # Vue 3 single-page app (5 pages)
│       ├── app.css              # Sky-blue + snow-white theme
│       └── vendor/              # Local dependencies: Vue 3 / mdui 2 / Material Icons fonts
├── cross_group_memory.py        # Cross-group memory persistence
├── group_switch_store.py        # Per-group toggle state persistence
├── media_parser.py              # Xiaohongshu / Bilibili / Douyin media parsing
├── media_cmds.py                # Media command helpers
├── dglab_client.py              # DG-LAB WebSocket client wrapper
├── dglab_device_store.py        # DG-LAB device binding persistence
├── dglab_connection_pool.py     # DG-LAB connection pool & state management
├── dglab_commands.py            # DG-LAB command handlers
├── dglab_webui.py               # CCDG WebUI control panel
├── dglab_user_store.py          # DG-LAB user storage
├── dglab_permission_store.py    # DG-LAB permission storage
├── dglab_post_store.py          # DG-LAB community-post storage
├── dglab_email_store.py         # DG-LAB email storage
├── dglab_turnstile_store.py     # DG-LAB Turnstile storage
├── dglab_chat_store.py          # DG-LAB chat storage
├── metadata.yaml                # Plugin metadata
├── CHANGELOG.md                 # Changelog
├── CONTRIBUTING.md              # Contributing guide
├── _conf_schema.json            # Config schema definition
├── requirements.txt             # Python dependencies
├── README.md                    # Project documentation (Chinese)
├── README_EN.md                 # Project documentation (English)
├── README_JA.md                 # Project documentation (Japanese)
└── README_ZH-TW.md              # Project documentation (Traditional Chinese)
```

### Core Modules

**Content fetching & parsing:**
- **PixivAPIClient** ([main.py](main.py)): Pixiv API client; routes between the GET random and POST filtered-search endpoints based on filters
- **HitokotoAPIClient** / **WeatherAPIClient** / **FemboyAPIClient**: quote / weather / femboy API clients
- **NeteaseAPIClient**: NetEase Cloud Music client with exponential-backoff retries
- **KugouAPIClient**: Kugou client (search / playback links)
- **MediaParserManager** ([media_parser.py](media_parser.py)): Xiaohongshu / Bilibili / Douyin link parsing
- **CommandParser** ([main.py](main.py)): parser for `key:value` parameters and shorthand syntax

**DG-LAB device management:**
- **DGLabClient** ([dglab_client.py](dglab_client.py)): WebSocket client — connection management, message I/O, keep-alive heartbeats
- **DeviceStore** ([dglab_device_store.py](dglab_device_store.py)): persistent user-device bindings (thread-safe)
- **DeviceConnectionPool** ([dglab_connection_pool.py](dglab_connection_pool.py)): connection pool — multi-user concurrency, connection reuse, auto-reconnect, idle cleanup
- **DGLabCommandHandler** ([dglab_commands.py](dglab_commands.py)): command parsing / validation / execution / formatting
- **DGLabWebUI** ([dglab_webui.py](dglab_webui.py)): CCDG WebUI browser control panel

**Main plugin & memory:**
- **CurrentCortexPlugin(Star)** ([main.py](main.py)): main plugin class; wires everything together and registers commands
- **CrossGroupMemoryStore** ([cross_group_memory.py](cross_group_memory.py)): cross-group shared memory, JSON-persisted
- **GroupSwitchStore** ([group_switch_store.py](group_switch_store.py)): per-group toggle state, JSON-persisted

### Design Highlights

- **Async architecture**: `asyncio` + `aiohttp` / `websockets`, non-blocking I/O
- **Modular design**: DG-LAB features split into focused modules with clear responsibilities
- **Uniform interfaces**: all API clients follow the same design pattern
- **Robust fault tolerance**: thorough exception handling, parameter validation, and retries where they matter
- **Persistent data**: DG-LAB bindings in `data/dglab_bindings.json`, cross-group memory in `data/currentcortex_cross_group.json` (both per AstrBot conventions)
- **Resource management**: the connection pool reaps idle connections to prevent leaks
- **Multi-tenant isolation**: independent connections per user, no cross-interference

---

## 🤝 Contributing

Issues and PRs are welcome! Bug reports and feature suggestions have Issue templates, and PRs have a self-test checklist template.

For dev environment setup, project structure, running tests, commit conventions, and the PR workflow, see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

> 💬 You can also drop by QQ group **1106353813** to discuss ideas first — for big changes, aligning early is recommended before writing code.

---

## 📄 License & Acknowledgements

This project is open-sourced under the [MIT License](LICENSE).

Acknowledgements:

- [LeiZ API](https://api.bileizhen.top) — the Pixiv / Hitokoto / weather / femboy / NetEase Cloud Music API services
- [AstrBot](https://github.com/AstrBot) — the chatbot framework
- [dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server) — the DG-LAB WebSocket protocol & relay server

---

**Version**: v2.0.11 (per-version changes in [CHANGELOG.md](CHANGELOG.md))  
**Repository**: [GitHub](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex)



