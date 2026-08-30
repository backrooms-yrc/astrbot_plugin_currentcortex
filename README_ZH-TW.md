# AstrBot CurrentCortex 綜合插件

**[简体中文](README.md)** | **[English](README_EN.md)** | **[日本語](README_JA.md)** | **[繁體中文](README_ZH-TW.md)**

> [!IMPORTANT]
> ## 🔒 使用本插件前，請務必加入官方 QQ 群
>
> **所有使用者請務必加入官方 QQ 群 1106353813**（[點擊加入](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)）。
>
> - **更新與緊急公告**：版本更新、上游 API／協定變動、故障通知都會在群內第一時間發布
> - **問題回饋**：遇到 bug 直接在群裡 @ 維護者，跟進速度遠快於 GitHub Issues
> - **使用答疑**：開發者與熱心群友常駐答疑，歡迎交流使用心得
>
> 入群後請先閱讀群公告。未加群的使用者遇到問題時，可能無法獲得及時支援。

> [!NOTE]
> ## 📢 緊急招募：DG-LAB 遠控功能急缺實機測試志工
>
> DG-LAB（郊狼）**遠控功能目前缺乏實機測試，急需志工參與實測**——沒有真實裝置的回饋，bug 只能盲修、迭代只能停滯。如果你手上有**郊狼脈衝主機 3.0**，請務必加入官方群參與測試：
>
> - **測試內容**：裝置綁定 · 遠端控制指令 · CCDG WebUI 控制面板 · 中繼伺服器部署（V3 / V4 協定）
> - **參與方式**：加入官方 QQ 群 **1106353813**（[點擊加入](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)，入群說明來意或直接 @ 維護者
> - **測試回饋**：問題第一時間跟進修復，貢獻者記入更新日誌致謝
>
> 沒有裝置的朋友也歡迎進群圍觀，或幫忙轉發擴散 🙏

> [!IMPORTANT]
> ## 🙏 致歉信——DG-LAB 協定支援遲到的兩個多月
>
> 各位使用 DG-LAB（郊狼）功能的使用者：
>
> 官方中繼伺服器在今年 5~7 月間遷移到了 v3 / v4 協定（6月2日，舊版 v2 伺服器自官方儲存庫移除）。這段期間使用新中繼的使用者一直無法正常綁定裝置（回報 `等待伺服器分配 clientId 逾時` 或 `HTTP 404`）。**這是我跟進上游變更不及時的失誤——沒有主動關注官方儲存庫的動向，直到 8月13日 [#3](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues/3) 有使用者回饋才發現問題，讓大家等了兩個多月。對此真誠地向各位致歉。**
>
> 問題已在 [v2.0.0](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/releases/tag/v2.0.0) 徹底修復：協定用戶端重寫為 V3 / V4 自動偵測（舊 v2 中繼同樣相容），無需修改任何設定，升級即可使用；v4 中繼需使用 **DG-LAB 4 APP** 掃描新版 QR Code，詳見 [DG-LAB 章節](#7-dg-lab-裝置管理-dglab別名-电击)。
>
> 為避免同類問題再次發生，我已訂閱上游儲存庫的變更通知，並為本模組補上了 36 個協定回歸測試——今後官方協定再有調整，可以第一時間跟進、不再依賴使用者回報障礙。再次感謝 issue #3 的回饋，也感謝大家的包容。
>
> —— Rcst20 · 2026年8月15日

<div align="center">

**多功能 AstrBot 插件** — 集內容取得、媒體解析、裝置控制與跨群記憶於一身。

Pixiv 隨機圖片 · 每日一言 · 天氣查詢 · 男娘圖片 · 網易雲點歌 · 小紅書／B站／抖音／微博解析 · DG-LAB 裝置管理 · 跨群聊記憶 · LLM 工具（AI 自主呼叫）· 語意分段回覆

</div>

---

> 💬 **插件官方 QQ 交流群**：**1106353813**，[點擊前往](https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info)
>
> 歡迎加入！在這裡可以獲取更新通知、回饋問題與建議、交流使用心得，開發者也會在群內答疑。
> 遇到 bug 或有新功能想法，也可以直接在群裡 @ 維護者，或到 [Issues](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues) 提交。
>
> ⚠️ **本群是 CurrentCortex 插件的社群交流群，與 [LeiZ API](https://api.bileizhen.top) 官方無關**。本插件是基於 LeiZ API 開發的**社群（第三方）插件**。LeiZ API 的註冊、Key 取得、API 計費、故障等問題請到 LeiZ API 官網及其官方管道諮詢，勿在本群回饋。

---

## 📋 目錄

- [✨ 核心特性](#-核心特性)
- [🚀 快速開始](#-快速開始)
- [🎯 功能詳解](#-功能詳解)
  - [1. Pixiv 隨機圖片](#1-pixiv-隨機圖片-pixiv別名-图片)
  - [2. 媒體內容解析](#2-媒體內容解析-解析別名-小红书-b站-抖音)
  - [3. 網易雲音樂](#3-音樂點歌-music別名-音乐)
  - [4. 每日一言](#4-每日一言-hitokoto別名-一言)
  - [5. 天氣查詢](#5-天氣查詢-weather別名-天气)
  - [6. 男娘圖片](#6-男娘圖片-femboy別名-男娘)
  - [7. DG-LAB 裝置管理](#7-dg-lab-裝置管理-dglab別名-电击)
- [🖥️ 總覽 Pages](#️-總覽-pages)
- [🧩 按群聊獨立開關](#-按群聊獨立開關)
- [✂️ 分段回覆](#️-分段回覆)
- [🤖 LLM 工具](#-llm-工具)
- [🧠 跨群聊記憶](#-跨群聊記憶)
- [⚡ API 連通性測試](#-api-連通性測試-apitest)
- [⚙️ 設定項](#️-設定項)
- [❓ 常見問題](#-常見問題)
- [🛠️ 技術架構](#️-技術架構)
- [🤝 貢獻指南](#-貢獻指南)
- [📄 開源授權與致謝](#-開源授權與致謝)

---

## ✨ 核心特性

| 模組 | 能力 |
| --- | --- |
| 🎨 **Pixiv 隨機圖片** | 隨機圖 / R18 / 標籤篩選 / 關鍵字搜尋 / 指定作者 / 長寬比篩選 / 排除 AI |
| 🔍 **媒體解析** | 小紅書圖文影片 · B站影片資訊 · 抖音無浮水印影片 · 微博圖文影片 |
| 📚 **媒體內容解析** | 小紅書 / B站 / 抖音 / 微博連結解析 |
| 🎵 **網易雲點歌** | 點歌、搜尋、語音訊息、原始檔案、依 ID 取得 |
| ✨ **每日一言** | 12 種分類（動畫／漫畫／遊戲／文學／詩詞／影視…） |
| 🌤️ **天氣查詢** | 即時天氣＋未來 3 天預報 |
| 👗 **男娘圖片** | 隨機男娘主題圖片（WebP） |
| 🔌 **DG-LAB** | Socket V3/V4（相容舊 V2）裝置全生命週期管理、協定自動偵測、多使用者／多裝置隔離、CCDG WebUI 控制面板 |
| 📖 **Wikidot 站點管理** | v2.3.0 新增：呼叫 Wikidot 前端 JS 介面編輯頁面（源碼／寫入／追加／標籤／重新命名／刪除）與管理站點（成員／設定／論壇／邀請）（`/wikidot`）。預設關閉 |
| 🖥️ **總覽 Pages** | AstrBot WebUI 整合總覽面板：儀表板 · 說明中心 · 視覺化設定（儲存即熱重載）· 郊狼控制（中繼伺服器一鍵部署 · 對外開放開關）· 聯絡我們 |
| 🧩 **按群聊開關** | 在單一群組用 `/开关` 指令關閉／開啟本插件指令（支援限時關閉自動恢復、按功能域分級），互不影響 |
| 🧠 **跨群聊記憶** | 同平台所有群共享一份持久化上下文，自動注入 LLM 請求（可依時效過濾、LLM 摘要壓縮、依關鍵字清理） |
| ✂️ **分段回覆** | 把機器人回覆拆成多則訊息分次傳送，模擬逐條回覆。支援標點／長度／LLM 語意三種分段模式 |
| 🤖 **LLM 工具** | 把圖片取得／點歌／電擊控制註冊為 AI 可呼叫的工具（function calling），AI 能自主回應自然語言請求 |

- **⚡ 非同步高效能**：基於 `asyncio` + `aiohttp` / `websockets`，非阻塞 I/O。
- **🛡️ 健全容錯**：網路異常、API 錯誤、參數錯誤均有友善提示；點歌附指數退避重試。
- **⚙️ 彈性設定**：所有預設參數均可在 AstrBot 管理後台自訂。
- **👥 多租戶隔離**：DG-LAB 每位使用者／每台裝置的連線與操作完全隔離。

---

## 🚀 快速開始

### 1. 安裝

**方式一：插件市集（建議）** — 在 AstrBot 管理後台搜尋 `astrbot_plugin_currentcortex` 安裝。

**方式二：手動複製儲存庫：**

```bash
cd AstrBot/data/plugins
git clone https://github.com/backrooms-yrc/astrbot_plugin_currentcortex.git
```

### 2. 設定 API Key (必填)

> 🔐 **LeiZ API 驗證要求**：自最新版本起，**所有 API（含免費 API）均需攜帶 API Key**，請求頭格式為 `x-api-key: <API-Key>`。

#### 第一步：取得 API Key

前往 **LeiZ API 官網** 👉 [https://api.bileizhen.top](https://api.bileizhen.top)

在官網註冊／登入後，進入「控制台 / API Keys」頁面建立並複製你的 API Key（即 `x-api-key` 的值）。該 Key 適用於所有 LeiZ API（Pixiv / 一言 / 天氣 / 男娘 / 網易雲），只需一組。

> 💡 實際申請位置以官網頁面為準（如「控制台 → API Keys / 權杖管理」）。若官網流程有變動，以官網說明為準。

#### 第二步：填入插件設定

開啟 AstrBot 管理後台 → 插件管理 → 本插件 → 設定，把上一步取得的 Key 填入 **`leiz_api_key`** 欄位，儲存後重新啟動插件。

未設定時，Pixiv / 一言 / 天氣 / 男娘 / 點歌等全部 LeiZ API 指令將無法使用，呼叫時會給予設定引導提示。

> ⚠️ **本插件是基於 LeiZ API 的社群（第三方）插件，與 LeiZ API 官方相互獨立**。API Key 的註冊／取得、API 計費、額度、上游故障等問題請到 [LeiZ API 官網](https://api.bileizhen.top) 及其官方管道諮詢；本插件的交流群僅處理插件本身的使用問題。

> **舊版移轉**：v1.3.x 及更早版本的 `femboy_api_key` 已合併為統一的 `leiz_api_key`。若未填新欄位但保留了舊欄位，插件會自動將其作為統一 Key 使用並提示移轉，建議盡快改填到 `leiz_api_key`。

### 3. 安裝相依套件

```bash
pip install aiohttp>=3.8.0
pip install websockets>=10.0   # 僅 DG-LAB 功能需要
```

### 系統需求

- **AstrBot** >= 4.15（< 5；使用 `EventMessageType` / 處理器 `priority` / `ProviderRequest` 等較新的 API）
- **Python** >= 3.10
- **aiohttp** >= 3.8.0
- **websockets** >= 10.0（DG-LAB 功能必備）
- **ffmpeg**（網易雲語音功能需要，須在系統 PATH 中）

---

## 🎯 功能詳解

> 💡 在聊天中傳送 **`/cc`** 或 **`/cc help`** 可查看全部指令的分類總覽圖片。

### 指令速查表

所有指令均支援中英文別名（**別名為簡體中文，請照原文輸入**）：

| 指令 | 別名 | 功能 |
| --- | --- | --- |
| `/pixiv` | `/图片` | Pixiv 隨機圖片 |
| `/解析` | — | 自動辨識平台並解析媒體連結 |
| `/xhs` | `/小红书` | 小紅書解析 |
| `/bilibili` | `/B站` `/b站` | B站影片解析 |
| `/douyin` | `/抖音` | 抖音影片解析 |
| `/weibo` | `/微博` | 微博貼文解析 |
| `/music` | `/音乐` | 音樂點歌（網易雲／酷狗） |
| `/点歌` | — | 快捷點歌（僅語音訊息） |
| `/音源` | — | 切換點歌音源（auto／網易雲／酷狗） |
| `/hitokoto` | `/一言` | 每日一言 |
| `/weather` | `/天气` | 天氣查詢 |
| `/femboy` | `/男娘` | 男娘圖片 |
| `/dglab` | `/电击` | DG-LAB 裝置管理 |
| `/开关` | `/toggle` `/switch` | 按群聊開關本插件指令（支援限時、按功能域分級） |
| `/开关列表` | `/switch_list` `/开关状态列表` | 查看本平台被關閉的群與功能域（管理員） |
| `/忘记` | `/forget_memory` `/忘记记忆` | 依關鍵字清理跨群聊記憶（管理員） |
| `/帮助` | `/cc` `/help` `/菜单` | 插件功能總覽 |
| `/apitest` | `/连通测试` `/接口测试` | API 連通性測試 |

---

### 1. Pixiv 隨機圖片 (`/pixiv`，別名 `/图片`)

透過 LeiZ API 取得隨機 Pixiv 圖片，支援豐富的篩選與搜尋。

#### 基本指令

| 指令 | 說明 |
| --- | --- |
| `/pixiv` | 取得一張隨機圖片（按預設參數） |
| `/pixiv help` | 顯示說明 |

#### 參數說明（`key:value` 格式，空格分隔，可自由組合）

| 參數 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `r18:` | int | 0 | R18 模式：`0`=全年齡、`1`=僅 R18、`2`=混合 |
| `num:` | int | 1 | 取得數量（1-20） |
| `size:` | string | regular | 圖片尺寸：`original`/`regular`/`small`/`thumb`/`mini` |
| `tag:` | string | — | 標籤篩選；單一 tag 內用 `\|` 為 **OR**，多個 tag 參數為 **AND** |
| `keyword:` | string | — | 標題／作者／標籤模糊搜尋 |
| `uid:` | int | — | 指定作者 UID |
| `ratio:` | string | — | 長寬比篩選，如 `gt1.2lt1.8` |
| `excludeAI:` | bool | false | 排除 AI 生成作品 |

#### 快捷語法

| 快捷詞 | 等同於 |
| --- | --- |
| `r18` | `r18:1` |
| `mixed` | `r18:2` |
| `safe` / `sfw` | `r18:0` |

#### 使用範例

```text
# 基礎隨機
/pixiv                          # 隨機全年齡圖片
/pixiv r18:1                    # 隨機 R18 圖片
/pixiv num:5                    # 一次取得 5 張

# 標籤與關鍵字搜尋
/pixiv tag:白丝 num:3           # 取得 3 張白丝圖
/pixiv keyword:初音ミク num:5   # 搜尋初音未來相關
/pixiv tag:萝莉 excludeAI:true  # 排除 AI 的萝莉標籤
/pixiv uid:123456 num:3         # 指定作者作品

# 組合篩選
/pixiv r18:2 tag:白丝 keyword:初音ミク num:3 size:original

# 快捷語法
/pixiv r18                      # 等同 r18:1
/pixiv mixed                    # 等同 r18:2
```

#### 回傳範例

```text
📷 [1/3]
🎨 冬日午後
👤 作者：SampleArtist
🔗 https://www.pixiv.net/artworks/12345678
🏷️ 標籤：オリジナル / 女の子 / 冬 / 雪
📐 尺寸：1920×1080
[圖片]
```

> 💡 **隨機與搜尋的路由**：未提供 `tag`/`keyword`/`uid`/`ratio`/`excludeAI` 等過濾參數時，走 GET 隨機 API（每次結果不同）；提供任一過濾參數時自動切換到 POST 篩選 API。

---

### 2. 媒體內容解析 (`/解析`，別名 `/小红书` `/B站` `/抖音`)

自動辨識平台並解析小紅書、B站、抖音、微博的媒體連結，回傳無浮水印圖片／影片資訊。

#### 基本指令

| 指令 | 說明 |
| --- | --- |
| `/解析 <連結>` | 自動辨識平台並解析；**一則訊息含多個連結時依次解析（最多 5 條）** |
| `/xhs <連結>`（`/小红书`） | 小紅書解析 |
| `/bilibili <連結>`（`/B站` `/b站`） | B站影片解析 |
| `/douyin <連結>`（`/抖音`） | 抖音影片解析 |
| `/weibo <連結>`（`/微博`） | 微博貼文解析 |
| `/解析 help` | 顯示說明 |

#### 支援的連結格式

| 平台 | 支援格式 |
| --- | --- |
| 小紅書 | `xiaohongshu.com/explore/xxx`、`xhslink.com/xxx`（短連結） |
| B站 | `bilibili.com/video/BVxxx`、`b23.tv/xxx`（短連結）、`avxxx` |
| 抖音 | `douyin.com/video/xxx`、`v.douyin.com/xxx`（短連結） |
| 微博 | `weibo.com/數字/xxx`、`m.weibo.cn/detail/xxx`、`weibo.cn/status/xxx`、`t.cn/xxx`（短連結） |

#### 使用範例

```text
/解析 https://www.xiaohongshu.com/explore/abc123
/解析 https://b23.tv/xxxx https://v.douyin.com/yyyy   # 批次：一則訊息多個連結，依次解析
/xhs https://xhslink.com/xxxx
/bilibili https://www.bilibili.com/video/BV1xx411c7mD
/douyin https://v.douyin.com/xxxx
/weibo https://m.weibo.cn/detail/xxxxx
```

#### 回傳資訊

- **小紅書**：標題、作者、按讚數、簡介、無浮水印高解析度原圖、影片連結（如有）
- **B站**：標題、UP主、影片長度、播放／按讚、封面、分P資訊、影片下載連結（如有）
- **抖音**：標題、作者、按讚／留言／分享、無浮水印影片連結
- **微博**：正文、作者、轉發／留言／按讚數、配圖（最多 9 張）、影片連結（如有）

#### 解析增強

- **失敗原因分級提示**：解析失敗不再甩原始例外文字，而是依原因分類提示——連結過期（短鏈失效）、內容已刪除／私密、平台反爬攔截、網路逾時、連結格式無法辨識等，便於判斷是連結問題還是網路問題。
- **結果快取**：相同連結在有效期內（預設 10 分鐘，`media_parse_cache_ttl` 可調）直接回傳上次解析結果，降低對目標平台的請求頻率與觸發反爬／封 IP 的機率；僅快取成功結果，失敗會即時重試。
- **聯動跨群聊記憶**：跨群聊記憶開啟時，解析成功會以 `media` 標籤記錄「誰解析了什麼內容」，後續對話中機器人可以自然回溯「你剛才發的那個影片」。

| 設定項 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `media_parse_cache_enable` | bool | true | 是否啟用解析結果快取 |
| `media_parse_cache_ttl` | int | 600 | 快取有效期（秒）。下載／播放連結本身有時效性，不建議設定過長 |

> ⚠️ 請確保連結可公開存取；部分平台可能因反爬蟲策略導致解析失敗。下載連結僅供個人學習使用，請遵守平台規範。

---

### 漫畫內容（原第 3 節，已移除）

> ⚠️ 因相關規範，本插件早期版本提供的漫畫內容功能已於 **v2.0.4** 起整體移除，後續版本不再提供，感謝理解。

---

### 3. 音樂點歌 (`/music`，別名 `/音乐`)

透過 LeiZ API 實現點歌、搜尋與播放連結取得，支援**網易雲**與**酷狗**雙音源，並提供 `auto` 自動路由（網易雲優先，失敗轉酷狗）。

#### 音源切換 (`/音源`)

| 指令 | 說明 |
| --- | --- |
| `/音源` | 查看目前音源＋可選項 |
| `/音源 auto`（自動） | **預設**。網易雲優先，VIP／無版權／逾時自動轉酷狗 |
| `/音源 网易云` | 僅網易雲 |
| `/音源 酷狗` | 僅酷狗 |

音源按**會話（群組／私訊）記憶**，互不影響；重新啟動後重設為預設（`music_default_source` 設定項，預設 auto）。

#### 基本指令

| 指令 | 說明 |
| --- | --- |
| `/music <歌曲名>`（`/音乐`） | 點歌（搜尋並回傳第一首的詳細資訊） |
| `/music direct <歌曲名>`（`/音乐 直接`） | 僅回傳轉碼後的語音訊息 |
| `/点歌 <歌曲名>` | 快捷指令，等同 `/音乐 直接`，僅回傳語音訊息 |
| `/music file <歌曲名>`（`/音乐 文件`） | 回傳未經轉碼的原始音樂檔案 |
| `/music id:<歌曲ID>` | 透過 ID 取得詳細資訊 |
| `/music search <關鍵字>` | 搜尋歌曲清單 |
| `/music help` | 顯示說明 |

#### 使用範例

```text
/music 孤勇者              # 點歌
/music 周杰伦 晴天         # 搜尋「周杰伦 晴天」
/music direct 孤勇者       # 僅回傳語音訊息
/点歌 孤勇者               # 快捷指令
/music file 孤勇者         # 回傳原始音檔附件
/music id:1901371647       # 透過 ID 取得
/music search 陈奕迅       # 搜尋歌曲清單
```

#### 回傳資訊

歌曲名稱、演出者、專輯、封面、音質（位元率／格式／等級）、檔案大小、播放連結。在 QQ 平台會自動將播放連結解析為**語音訊息**傳送（依賴框架 `Record` 訊息段；不支援時降級為文字連結）。

> ⚠️ 部分 VIP 歌曲可能無法取得播放連結；播放連結有時效性，請及時使用。語音功能依賴系統 `ffmpeg`。

> 📦 **檔案模式與大檔案**：`/音乐 文件` 在 QQ／NapCat 下優先走 OneBot 本地上傳（`upload_group_file` / `upload_private_file`），避免 `Comp.File` 經錯誤的 `callback_api_base` 轉成 HTTP 回呼後被二次下載失敗（日誌常見「下載檔案失敗」）。原始音檔（尤其無損 flac）體積可能很大；當檔案超過 `music_file_max_bytes`（預設 25MB）時，插件會自動轉碼為 128kbps MP3 後再傳送（需 `ffmpeg`），體積可縮小約 90%。如需傳送原始無損檔案，可在設定中調高該門檻（但不建議，容易傳送失敗）。下載側對逾時／網路錯誤會自動重試。

> 🚫 **防連點過載**：為避免使用者短時間連點觸發大量並行下載／轉碼拖垮伺服器，點歌指令內建「處理中去重＋冷卻」（`music_cooldown`，預設 3 秒）。同一會話上一首還在處理時再次點歌會提示「請稍候」，剛點完立刻再點會提示「點得太快啦」。不同群組／私訊互不影響。

---

### 4. 每日一言 (`/hitokoto`，別名 `/一言`)

取得來自社群貢獻的隨機一言。

#### 基本指令

| 指令 | 說明 |
| --- | --- |
| `/hitokoto` | 隨機取得一言（全部分類） |
| `/hitokoto <分類代碼>` | 指定分類 |
| `/hitokoto help` | 顯示說明 |

#### 分類選項

| 代碼 | 分類 | 代碼 | 分類 |
| --- | --- | --- | --- |
| a | 動畫 | g | 其他 |
| b | 漫畫 | h | 影視 |
| c | 遊戲 | i | 詩詞 |
| d | 文學 | j | 網易雲 |
| e | 原創 | k | 哲學 |
| f | 來自網路 | l | 抖機靈 |

```text
/hitokoto a    # 取得動畫類一言
/hitokoto i    # 取得詩詞類一言
```

---

### 5. 天氣查詢 (`/weather`，別名 `/天气`)

即時查詢城市天氣及未來 3 天預報。

```text
/weather 广州市      # 查詢廣州天氣
/weather 北京        # 查詢北京天氣
/weather help        # 顯示說明
```

支援中國主要城市，建議使用簡體城市名（最長 50 字元）。回傳目前溫度／天氣／體感／風力／濕度及未來 3 天預報。

---

### 6. 男娘圖片 (`/femboy`，別名 `/男娘`)

隨機取得男娘主題圖片（WebP）。

```text
/femboy          # 隨機男娘圖片
/femboy help     # 顯示說明
```

> 使用前必須設定 `leiz_api_key`，詳見[快速開始](#2-設定-api-key-必填)。

---

### 7. DG-LAB 裝置管理 (`/dglab`，別名 `/电击`)

透過 DG-LAB Socket 協定實現對郊狼脈衝主機的完整控制。**需執行 [DG-LAB WebSocket 中繼伺服器](https://github.com/dungeonlab-open/dglab-websocket-server)**。

> 📡 **協定版本**：官方中繼儲存庫已刪除 v2 伺服器，僅保留 **v3**（`bun run v3`，預設連接埠 9999）與 **v4**（`bun run v4`，預設連接埠 9998）。自 v2.0.0 起插件**自動偵測**中繼伺服器協定（V3 / V4，並相容既有舊 V2 中繼），無需改設定即可直接使用；亦可透過 `dglab_protocol` 設定項手動指定（`auto` / `v3` / `v4`）。
>
> - **V3**：QR Code 格式與舊版一致，DG-LAB APP / DG-LAB 4 APP 均可掃描；
> - **V4**：使用新版 QR Code（`dungeon-lab.cn/s/?v=1&action=socket&url=...`），需 **DG-LAB 4 APP** 掃描；強度控制透過 `device.op` 任務下發（絕對強度按 APP 回傳的目前值換算增量，無回傳時退化為臨時強度任務）。

#### 基本指令

| 指令 | 說明 |
| --- | --- |
| `/dglab bind [伺服器位址]`（`绑定`） | 綁定新裝置（產生 QR Code 供 APP 掃描，支援多裝置追加） |
| `/dglab unbind [序號]`（`解绑`） | 解除裝置綁定（多台時需指定序號） |
| `/dglab strength [序號] <A\|B> <0-200>`（`强度`） | 設定通道強度（序號省略則操作 #1） |
| `/dglab up [序號] <A\|B> [步進]`（`增加`） | 增加強度（預設 +5） |
| `/dglab down [序號] <A\|B> [步進]`（`减少`） | 減少強度（預設 -5） |
| `/dglab shock [序號] <A\|B> [強度] [波形] [秒數]`（`开始`） | 開始電擊 |
| `/dglab stop [序號] [A\|B]`（`停止`） | 停止電擊（強度歸零＋清空波形） |
| `/dglab pulse [序號] <A\|B> <預設\|HEX> [秒數]`（`波形`） | 傳送波形資料（預設 5 秒） |
| `/dglab clear [序號] <A\|B>`（`清空`） | 清空波形佇列 |
| `/dglab feedback [序號]`（`反馈`） | 查看即時強度與回饋按鈕狀態 |
| `/dglab permission [on\|off]`（`权限`） | 查看／切換權限隔離（預設開啟） |
| `/dglab status`（`状态`） | 查看全部裝置綁定與連線狀態 |
| `/dglab info`（`信息`） | 查看全部裝置詳細資訊 |
| `/dglab help`（`帮助`） | 顯示說明 |

> 💡 **多裝置**：同一使用者可綁定多台裝置，用序號（1/2/3…）區分，省略預設操作 #1。控制他人裝置範例：`/dglab strength @使用者ID 2 A 50`。

#### 波形預設

| 預設 | 效果 | 預設 | 效果 |
| --- | --- | --- | --- |
| `breathe` | 緩慢漸強漸弱 | `needle` | 高頻連續尖刺 |
| `pulse` | 快速間歇脈衝 | `throb` | 低頻緩慢起伏 |
| `wave` | 連續波浪起伏 | `chaos` | 強弱隨機交替 |
| `tap` | 短促單次敲擊 | `heartbeat` | 雙拍心跳節奏 |

#### 使用流程

```text
1. 綁定裝置
   /dglab bind ws://192.168.1.100:9999
2. 用 DG-LAB APP 掃描 QR Code 完成綁定
3. 控制裝置
   /dglab shock A 50 breathe 10   # A通道電擊（強度50，呼吸波形，10秒）
   /dglab strength A 50           # 僅設定A通道強度
   /dglab pulse A wave 5          # 傳送波浪波形5秒
   /dglab up B 10                 # B通道強度+10
   /dglab stop                    # 停止所有輸出
4. 查看狀態
   /dglab status
   /dglab feedback
5. 解除綁定（可選）
   /dglab unbind
```

#### CCDG WebUI 控制面板

啟用 `dglab_webui_enabled` 後，插件會在 `dglab_webui_host`:`dglab_webui_port`（預設 `127.0.0.1:9178`）啟動一個 CCDG WebUI 瀏覽器遠端控制介面，可在網頁上查看／控制裝置，Material Design 3 風格。

> ⚠️ **CCDG WebUI 安全（重要）**
> - 自 v1.5.3 起，**WebUI 預設關閉**（`dglab_webui_enabled` 預設 `false`），需手動開啟。
> - 預設監聽位址為 `127.0.0.1`（僅本機存取）。**如需對外存取，請將 `dglab_webui_host` 明確設為 `0.0.0.0`，並務必在前方部署反向代理與存取控制**（如 Nginx + Basic Auth / IP 白名單）。
> - 也可以直接在**總覽 Pages → 郊狼控制**裡用「對外開放」開關一鍵切換 `127.0.0.1` / `0.0.0.0`（附二次確認與對外連結展示；開啟時自動以 ufw 開放連接埠，關閉／停用 WebUI 時自動收回）。
> - WebUI 內建獨立的使用者註冊／登入系統，**與機器人本體／平台帳號無關**：任何能存取該連接埠的人都能註冊帳號。不要在無防護的情況下直接暴露到對外網路。
> - 建議僅在本機使用，或僅在內網／經反向代理＋驗證後對外提供。

#### 進階特性

- **多使用者隔離**：每位使用者獨立連線與綁定，互不影響，支援最多 50 個並行連線。
- **自動重連**：操作失敗自動重試（最多 2 次）；連線中斷嘗試重建；閒置超過 5 分鐘自動清理。
- **安全機制**：所有參數嚴格驗證，操作逾時保護，強度限制 0-200。

> ⚠️ 僅支援**郊狼脈衝主機 3.0**；QR Code 在會話期間有效，逾時需重新產生；建議區域網路用 `ws://`，對外網路用 `wss://`。

---

## 🖥️ 總覽 Pages

> 自 **v1.9.0** 起，插件整合了 AstrBot 插件 Pages 總覽面板（mdui 2 Material Design 3 風格，晴空藍＋雪霧白）。在 AstrBot WebUI 的**插件詳細資訊 → Pages**（或側邊欄「插件 Pages」分組）中開啟。

總覽面板共 5 個頁面：

| 頁面 | 說明 |
| --- | --- |
| 📊 **儀表板** | 插件執行總覽：執行時長、已綁定裝置、活躍連線、註冊使用者、插件版本／作者／啟動時間、功能開關狀態 |
| 📖 **說明中心** | 內建使用文件與常見問題（快速開始／郊狼／分段回覆／跨群記憶／故障排除） |
| ⚙️ **設定** | 視覺化修改全部插件設定：每個設定項都有中文名＋白話解釋，儲存後**自動熱重載**生效，無需手動重新啟動 |
| ⚡ **郊狼控制** | 中繼伺服器一鍵部署（v3/v4 · 對外開放開關）＋ CCDG WebUI 總開關＋**對外開放開關**（見下） |
| 💬 **聯絡我們** | 開發者資訊、GitHub 儲存庫、QQ 交流群（一鍵加群） |

#### 郊狼控制：對外開放開關

- **WebUI 總開關**：僅啟用 CCDG WebUI，監聽保持 `127.0.0.1`（僅本機可存取，**不算對外開放**）。
- **對外開放開關**（需先啟用 WebUI）：開啟後自動把 `dglab_webui_host` 改為 `0.0.0.0`（連接埠 `dglab_webui_port`，預設 `9178`），偵測本機對外 IP 並顯示對外連結；關閉後自動改回 `127.0.0.1`。
- 開啟前會彈出**二次確認**，並持續顯示安全警告；關閉 WebUI 總開關時也會自動把監聽位址清理回 `127.0.0.1`，避免殘留對外設定。

> ⚠️ **安全提醒**：監聽 `0.0.0.0` 意味著對外網路任意位址都能存取 WebUI 的註冊／登入／裝置 API。對外開放前請務必先設定**反向代理＋驗證**（如 Caddy + BasicAuth、Nginx + IP 白名單、Cloudflare Zero Trust），否則任何人都可能控制你的郊狼裝置。

#### 郊狼控制：中繼伺服器一鍵部署（v3/v4）

郊狼控制頁可直接在伺服器上**一鍵部署官方 v3 / v4 中繼伺服器**（[dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server)，Bun 執行環境），無需命令列操作：

- **自動偵測**：v3（連接埠 9999）與 v4（連接埠 9998）各自獨立偵測部署狀態；已部署的顯示執行狀態、systemd 服務名稱、原始碼版本，並支援一鍵解除安裝（歷史手動部署的服務也能被識別接管）
- **一鍵部署**：自動完成 安裝 Bun → 複製官方儲存庫 → 寫入設定 → 安裝相依套件 → 建立 systemd 常駐服務（開機自動啟動、崩潰自動重啟）→ 協定自我檢查，全程約 10~60 秒
- **對外開放開關**（預設關閉）：官方伺服器監聽位址固定為全部介面，「本機／對外」可達性由防火牆控制——開關關閉時連接埠不開放（僅本機 `ws://127.0.0.1:連接埠` 可達，頁面顯示本機位址）；開啟時自動開放連接埠（ufw）並偵測顯示對外位址 `ws://對外IP:連接埠`，關閉時自動收回。開放前有二次確認
- **解除安裝**：停止並刪除 systemd 服務、收回防火牆開放；原始碼目錄保留，重新部署秒級完成

> ⚠️ **安全提醒**：開放中繼連接埠後，任何取得位址的 DG-LAB APP 都可以接入該中繼，建議僅在使用期間開啟、用完關閉。部署／解除安裝依賴 systemd 與 ufw（AstrBot 需以 root 執行）。

---

## 🧩 按群聊獨立開關

每個群聊可獨立控制本插件是否生效，互不影響。例如某個群不需要圖片／點歌等功能時，可單獨關閉它，而其他群不受影響。

#### 基本指令

| 指令 | 說明 |
| --- | --- |
| `/开关 off`（或 `/开关 关`） | **永久關閉**本群全部插件指令（pixiv／解析／music／… 均不再回應） |
| `/开关 off <時長>` | **限時關閉**，到期自動恢復。如 `/开关 off 2h`、`/开关 off 30m`、`/开关 off 1d`、`/开关 off 2小时30分钟` |
| `/开关 off <功能域> [時長]` | **只關某一類功能**，其餘功能不受影響。如 `/开关 off media 2h` 只關媒體解析 2 小時 |
| `/开关 on`（或 `/开关 开`） | **重新啟用**本群插件指令（限時關閉也可提前手動恢復） |
| `/开关 on <功能域>` | 單獨恢復某一類功能，如 `/开关 on media` |
| `/开关 status [功能域]`（或 `/开关 状态`） | 查看本群目前狀態（限時關閉會顯示預計恢復時間） |
| `/开关列表`（`/switch_list` `/开关状态列表`） | **管理員**查看目前平台所有被關閉的群（含功能域）及各自恢復時間 |
| `/开关` | 無參數＝查看狀態＋用法提示 |

> 別名：`/toggle`、`/switch`（如 `/toggle off 2h`）。時長單位：`s`/`秒`、`m`/`分`/`分钟`、`h`/`时`/`小时`、`d`/`天`，可組合。
>
> **功能域**（可不填，不填＝全域全部指令）：`media` 媒體解析 · `image` 圖片獲取 · `music` 音樂點歌 · `utility` 實用工具 · `dglab` DG-LAB 裝置 · `memory` 跨群聊記憶。功能域支援中文名（如 `/开关 off 图片`）。

#### 使用範例

```text
/开关 off       # 在本群永久關閉 CurrentCortex 全部指令
/开关 off 10h   # 關閉 10 小時（例如夜間免打擾，到期自動恢復）
/开关 off media 2h   # 只關媒體解析 2 小時，點歌／圖片不受影響
/开关 status media   # 查看媒體解析域的狀態（⏳ 將於 1小時58分鐘後 自動恢復）
/开关列表       # 管理員：查看本平台所有被關閉的群與功能域
/开关 on media  # 單獨恢復媒體解析
/开关 on        # 重新啟用（永久或限時關閉均可）
```

#### 工作原理與說明

- **狀態持久化**：開關狀態保存在 `data/currentcortex_group_switch.json`，重新啟動後保留。預設（未設定過）為**啟用**，只有主動 `/开关 off` 的群才會被關閉。
- **分級開關（scope）**：儲存 key 為 `umo`（全域）或 `umo|功能域`（域級）；全域關閉優先於任何域級狀態；舊版本資料（純 `umo` 條目）自動視為全域禁用，無需遷移。
- **限時自動恢復**：`/开关 off [功能域] <時長>` 到期後自動恢復啟用（惰性過期判斷，無需背景定時任務），重新啟動後倒數依然有效。
- **關閉期間提醒一次**：功能被關閉後，第一次使用對應指令會收到一句簡短提示（如「本群已單獨關閉媒體解析」），同一群同一功能 1 小時內不重複，避免刷屏。可用 `group_switch_hint_enable` 關閉該提醒。
- **永不死鎖**：`/开关` 與 `/开关列表` 指令本身**始終可用**——即使本群已關閉，仍可傳送 `/开关 on` 重新啟用，不會被攔截。
- **權限**：預設僅**群組管理員**（框架識別的 admin）可操作。若你未被識別為管理員，可在設定中關閉 `group_switch_admin_only`。`/开关列表` 始終僅管理員可用。
- **僅作用於本插件**：該開關只攔截 CurrentCortex 的指令，不影響 AstrBot 其他插件與機器人本體功能。
- **⚠️ LLM 工具不受域級開關限制**：功能域開關只約束使用者指令；AI 透過 LLM 工具自主呼叫圖片／點歌／電擊等能力時不經過指令入口，不受域級開關影響（全域關閉仍會攔截）。介意請同時關閉 `llm_tools_enable`。
- **私訊不受控**：開關僅對群聊生效。

| 設定項 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `group_switch_enable` | bool | true | 是否啟用按群聊開關功能（關閉則守衛完全不介入） |
| `group_switch_admin_only` | bool | true | 是否僅群組管理員可操作 `/开关` |
| `group_switch_hint_enable` | bool | true | 功能被關閉期間，首次使用對應指令時回一句提示（同一群同一功能 1 小時一次） |

---

## ✂️ 分段回覆

選用功能：把機器人的回覆拆成**多則訊息分次傳送**，模擬「逐條回覆」的節奏，讓長回覆更自然、更有真人感。預設關閉，需在設定面板手動開啟。

#### 工作方式

開啟後，插件會在回覆傳送前介入，按所選規則把整段文字切成若干段，逐條傳送，段與段之間加隨機延遲（首段不延遲）。

> ⚠️ **與框架內建功能的關係**：AstrBot 本身已有全域「分段回覆」能力（`平台設定 → 分段回覆`）。**本插件功能與之獨立，請勿同時開啟**，否則會重複分段。二選一即可——若你已在框架層啟用，就不必再開這裡的。

#### 設定項

| 設定項 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `reply_seg_enable` | bool | false | **【總開關】** 開啟分段回覆 |
| `reply_seg_only_llm` | bool | true | 僅對大模型（LLM）回覆分段；關閉則插件指令回覆（如 `/pixiv`）也會被分段。建議保持開啟 |
| `reply_seg_mention` | bool | true | 分段回覆的首則訊息是否 @ 並引用回覆使用者（讓多段有明確歸屬）。部分平台不支援引用回覆時自動降級 |
| `reply_seg_mode` | string | llm | 分段模式（下拉選擇）：`llm`=大模型語意分段（預設·建議，最智慧）、`punct`=標點分句（最輕量）、`length`=長度切分（見下方說明） |
| `reply_seg_llm_provider_id` | string | `""` | **llm 模式專用**：用於分段的 LLM 供應商 ID。留空則複用目前會話模型；建議填便宜快速的模型 ID |
| `reply_seg_llm_density` | string | `medium` | **llm 模式專用**：分段密度，即每段目標字數。`low`=每段長（~40-70字，切少）、`medium`=適中（~20-45字）、`high`=每段短（~10-25字，切細更活潑）。會自動推算段數上限並引導模型 |
| `reply_seg_llm_max_segments` | int | `0` | **llm 模式專用**：分段數量上限。`0`=按密度檔位自動推算（low=3／medium=5／high=8）；也可手動指定硬上限，超過會被合併到最後一段 |
| `reply_seg_llm_min_chars` | int | 30 | **llm 模式專用**：原文短於此字數時不呼叫 LLM，直接整段傳送（建議 20~50） |
| `reply_seg_llm_timeout` | int | 30 | **llm 模式專用**：單次分段呼叫逾時秒數，逾時則降級規則分段。預設 30 秒，涵蓋大部分模型（含推理模型） |
| `reply_seg_split_symbols` | string | `。！？!?~～…`＋換行＋`,，` | punct／length 模式：單字元切分符號（在這些符號處切分，符號保留在段尾）。預設含中英文逗號 |
| `reply_seg_split_words` | string | `喵 qwq owo awa ovo` | punct／length 模式：切分詞（可多字元，**空格分隔**），在詞的後面切分、詞保留在段尾。⚠️ 建議只放多字元詞：單字元詞（如 `w`）會誤切英文單字，左括號 `（` 會破壞配對，均預設不包含 |
| `reply_seg_merge_threshold` | int | 4 | punct 模式：短段合併門檻。短於此長度的段會被合併到前一段，**純標點段（如孤立的「。」）無條件合併**——消除逗號碎片與孤立標點。設為 `0` 關閉合併 |
| `reply_seg_min_length` | int | 15 | length 模式：最小段長，短於此不切（建議 10~30） |
| `reply_seg_max_length` | int | 80 | length 模式：最大段長，超過時在 `[最小,最大]` 範圍找標點切，找不到才硬切（建議 50~150） |
| `reply_seg_delay_range` | string | `0.8,2.5` | 段間隨機延遲範圍（秒），格式 `min,max` |

#### 三種分段模式

- **`punct`（按標點）**：在每個切分符號／詞處斷開。最輕量，適合大多數對話。切完後會把**過短段與純標點段（如孤立的「。」）自動合併**到前一段，避免產生碎片（由 `reply_seg_merge_threshold` 控制，可關閉）。
- **`length`（按長度）**：當某段超過「最大段長」時，在 `[最小段長, 最大段長]` 範圍內反向尋找切分點（符號或詞）來切；找不到才硬切。適合控制每段不要太長。
- **`llm`（大模型語意分段）** ⭐建議：呼叫大模型按**語意完整性**切分，像真人「一句一句說」——不在逗號處碎切、顏文字歸屬保持完整、清單／排比按主題歸併。比規則式更智慧。代價是每條回覆會**多一次 LLM 呼叫**，增加 1~3 秒延遲與少量 token 消耗；短回覆（< `reply_seg_llm_min_chars`）會自動跳過不呼叫。透過 `reply_seg_llm_density` 可選「低／中／高」三檔分段密度，控制每段字數規模。

> 💡 **`llm` 模式建議**：在 `reply_seg_llm_provider_id` 填一個**便宜快速的模型**（如 deepseek-v3）的供應商 ID，別佔用主模型。供應商未設定時會複用目前會話模型；呼叫失敗、解析異常或字數偏差過大時會**自動降級**到 punct 規則分段，不影響正常回覆。
>
> 💡 **分段密度**（`reply_seg_llm_density`）：`low`=每段較長（~40-70字，資訊量大、切得少）、`medium`=適中（~20-45字）、`high`=每段短碎（~10-25字，活潑像洗版）。檔位會自動推算段數上限並寫進提示詞引導模型；如需精確控制段數，可用 `reply_seg_llm_max_segments` 手動指定硬上限。

> 💡 `punct` / `length` 模式下，除標點（句號、問號、逗號等）外還可設定**切分詞**（`reply_seg_split_words`，空格分隔），在顏文字／語氣詞（如 `喵`、`qwq`、`owo`）後面斷開。兩種規則模式都會同時識別切分符號與切分詞。

#### 說明

- 分段後的完整回覆會被正確寫回對話歷史，不影響上下文連貫性。
- 分段僅作用於**純文字**回覆；圖片、檔案等不會被拆分。
- 若分段過程出現異常，會自動回退為整條傳送（不影響正常使用）。

---

## 🤖 LLM 工具

選用功能：把插件的圖片取得、點歌、電擊控制等功能**註冊為大模型可呼叫的工具（function calling）**，讓 AI 能自主處理「來張貓娘圖」「播首晴天」「電擊A通道強度50」這類**自然語言請求**——無需使用者輸入 `/` 指令，AI 會自行判斷意圖並呼叫對應工具。預設開啟，如不需要可在設定面板關閉 `llm_tools_enable`。

> ⚠️ 電擊控制涉及實體裝置、有安全風險，請確認安全後再開啟。所有工具執行第一行都會走開關檢查，關閉後工具回傳提示而不執行。

#### 已註冊工具一覽（共 11 個）

| 類別 | 工具名 | 參數 | 說明 |
| --- | --- | --- | --- |
| 🖼️ 圖片 | `get_pixiv_random` | num, r18 | 隨機二次元插畫 |
| 🖼️ 圖片 | `search_pixiv` | keyword, num, r18 | 按關鍵字搜尋插畫 |
| 🖼️ 圖片 | `get_pixiv_by_tags` | tags, num, r18 | 按標籤精確篩選（多標籤 AND） |
| 👗 男娘 | `get_femboy_image` | 無 | 隨機男娘圖片 |
| 🎵 點歌 | `play_song` | song_name | 搜尋並點歌（語音訊息） |
| ⚡ 電擊 | `dglab_shock` | channel, strength, wave, duration, device_index | 開始電擊 |
| ⚡ 電擊 | `dglab_strength` | channel, value, device_index | 設定絕對強度 |
| ⚡ 電擊 | `dglab_strength_adjust` | channel, direction, step, device_index | 增減強度 |
| ⚡ 電擊 | `dglab_pulse` | channel, wave, duration, device_index | 傳送波形 |
| ⚡ 電擊 | `dglab_stop` | channel, device_index | 停止輸出 |
| ⚡ 電擊 | `dglab_status` | 無 | 查詢裝置狀態 |

#### 工作方式

- **零重寫**：工具內部完全複用現有業務邏輯（圖片走 `_process_response`、點歌走 `_search_and_get`、電擊走 `_dispatch_command`），不重複造輪子。
- **媒體交付**：圖片／點歌／男娘工具內部直接 `event.send` 傳送媒體，並 `return` 一句說明給 AI（如「已傳送2張圖片」），避免 AI 再重複發文字。
- **電擊安全**：電擊工具把 AI 給的結構化參數拼回指令字串，複用 `_dispatch_command`，**完整繼承權限檢查、跨使用者隔離、裝置解析**。強度值鉗位到 0-200，波形預設交由現有邏輯驗證。
- **自動降級**：未設定 API Key、裝置未連線等情況下，工具回傳友善提示而非報錯。

#### 設定項

| 設定項 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `llm_tools_enable` | bool | true | **【總開關】** 開啟後註冊全部工具；關閉則不生效（僅保留原有 `/` 指令） |

> 💡 開啟後，AI 會根據使用者訊息自動判斷是否呼叫工具。例如使用者說「來張蘿莉圖」，AI 會呼叫 `get_pixiv_random`；說「我想聽晴天」，AI 會呼叫 `play_song`；說「電我一下」，AI 會呼叫 `dglab_shock`（需確認電擊裝置已綁定連線）。

---

## 🧠 跨群聊記憶

選用功能：在同一平台實例下的所有群聊之間共享一份**持久化**記憶，作為額外上下文注入 LLM 請求，讓機器人在不同群之間擁有連續語境。

- **儲存**：`data/currentcortex_cross_group.json`，按平台實例（`platform_id`）分桶，重新啟動後保留。
- **記錄**：群聊中的非指令訊息會被格式化為 `[暱稱/HH:MM:SS]: 文字` 並滾動追加（超過上限自動修剪舊記錄）。
- **注入**：群組訊息觸發 LLM 請求時，自動把同平台其他群的最近若干筆記錄以 `<system_reminder>` 注入使用者訊息部分；設定 `cross_group_max_age_hours` 後僅注入該時效內的記錄，冷群不再翻出陳年舊話題。
- **LLM 摘要（可選）**：開啟 `cross_group_summary_enable` 後，注入筆數超過閾值時先呼叫 LLM 把原始記錄壓縮成一段話題摘要（「最近大家在聊 XX、YY」）再注入，省 token、更聚焦重點；失敗（無模型／逾時／空結果）自動降級為原始記錄注入，同一份記憶 5 分鐘內重用摘要不重複呼叫。注意：會在回覆鏈路上增加一次 LLM 呼叫（最長 20 秒），建議配置廉價快速模型。
- **斜線指令不記錄**：指令訊息不會進入記憶。
- **依關鍵字清理**：管理員傳送 `/忘记 <關鍵字>`（別名 `/forget_memory` `/忘记记忆`）可刪除本平台記憶中所有包含該關鍵字的記錄（子字串匹配、不區分大小寫），用於精確清理誤記錄內容，無需清空整個平台記憶。

| 設定項 | 預設值 | 說明 |
| --- | --- | --- |
| `cross_group_enable` | false | 是否啟用跨群聊記憶 |
| `cross_group_max_cnt` | 500 | 每個平台保留的最大記錄筆數 |
| `cross_group_inject_cnt` | 30 | 每次回覆注入到 LLM 的最近記錄筆數 |
| `cross_group_max_age_hours` | 0 | 注入 LLM 時只保留最近多少小時內的記錄（`0` = 不限時效，僅按筆數修剪，即舊版行為；建議 12~48） |
| `cross_group_summary_enable` | false | 是否啟用 LLM 記憶摘要（注入筆數超過閾值時先壓縮成話題摘要） |
| `cross_group_summary_threshold` | 20 | 觸發摘要的注入筆數閾值（低於該值直接注入原始記錄） |
| `cross_group_summary_provider_id` | （空） | 摘要專用模型 ID，留空重用目前會話模型；建議選廉價快速的非推理模型 |

> ⚠️ 開啟後會向 LLM 提供其他群的聊天內容，請確認符合你的隱私預期與各群成員的知情同意。

---

## ⚡ API 連通性測試 (`/apitest`)

一鍵診斷全部 LeiZ 上游 API 的驗證與連線狀態，快速區分「API 異常」還是「程式問題」。

```text
/apitest          # 並行探測全部 6 個 API
/apitest help     # 顯示說明
```

5 個 API（Pixiv / 一言 / 天氣 / 男娘 / 點歌）並行探測，每個用最輕量的唯讀請求，不消耗圖片／音訊下載流量。狀態含義：

| 圖示 | 狀態 | 含義 |
| --- | --- | --- |
| 🟢 | 正常 | API 回傳成功 |
| 🟡 | HTTP 異常 | 收到非 200（如 401 驗證失敗 / 402 額度 / 5xx） |
| 🔴 | 網路／逾時 | 連線失敗或超過設定逾時 |
| ⚫ | 略過 | 對應用戶端未初始化（通常未設定 API Key） |

---

## ⚙️ 設定項

路徑：AstrBot 管理後台 → 插件管理 → 本插件 → 設定。

### Pixiv 相關

| 設定項 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `default_r18` | int | 0 | 預設 R18 模式（0=全年齡, 1=僅R18, 2=混合） |
| `default_num` | int | 1 | 預設每次取得的圖片數量（1-20） |
| `default_size` | string | regular | 預設圖片尺寸（original/regular/small/thumb/mini） |
| `image_proxy` | string | pixiv.bileizhen.top | 圖片反向代理網域 |
| `exclude_ai` | bool | false | 預設是否排除 AI 生成作品 |

### 通用／驗證

| 設定項 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `leiz_api_key` | string | （空） | **LeiZ API 統一金鑰**（請求頭 `x-api-key`），**必填**。在 [LeiZ API 官網](https://api.bileizhen.top) 註冊後取得，所有 LeiZ API 均需 |
| `request_timeout` | int | 15 | API 請求逾時時間（秒），影響所有功能 |

### 網易雲音樂

| 設定項 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `music_file_max_bytes` | int | 26214400 | `/音乐 文件` 單檔體積上限（位元組，預設 25MB）。超過則自動轉碼為 128kbps MP3 再傳送（需 ffmpeg）；設為 0 不限制（不建議，容易傳送失敗） |
| `music_cooldown` | int | 3 | 同一會話連續點歌的最小間隔秒數，防止使用者連點觸發大量並行下載／轉碼拖垮伺服器。處理中的請求會被提示「請稍候」；設為 0 不限制（不建議） |
| `music_default_source` | string | auto | 點歌預設音源：`auto`（網易雲優先，失敗轉酷狗）/ `netease`（僅網易雲）/ `kugou`（僅酷狗）。使用者仍可用 `/音源` 按會話覆寫 |

### DG-LAB

> ⚠️ 使用 DG-LAB 功能前，必須先部署並執行 [DG-LAB WebSocket 中繼伺服器](https://github.com/dungeonlab-open/dglab-websocket-server)（官方現僅提供 v3 / v4 伺服器，v2 已刪除）。

| 設定項 | 類型 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `dglab_server_url` | string | （空） | 中繼伺服器位址（如 `ws://192.168.1.100:9999`；V4 若配置了路徑前綴需一併填寫，如 `wss://host:9998/v4`） |
| `dglab_protocol` | string | auto | 中繼協定版本：`auto`=自動偵測（建議）/ `v3`（預設連接埠 9999，相容舊 V2 中繼）/ `v4`（預設連接埠 9998，需 DG-LAB 4 APP 掃描） |
| `dglab_heartbeat_interval` | int | 60 | 心跳間隔（秒），建議 30-120 |
| `dglab_auto_connect` | bool | false | 插件啟動時是否自動連線（一般設 false） |
| `dglab_webui_enabled` | bool | false | 是否啟用 CCDG WebUI 控制面板（**預設關閉**；需了解風險後手動開啟） |
| `dglab_webui_host` | string | 127.0.0.1 | CCDG WebUI 監聽位址（預設僅本機；對外需明確設為 `0.0.0.0` 並加反向代理＋驗證） |
| `dglab_webui_port` | int | 9178 | CCDG WebUI 監聽連接埠 |

<details>
<summary><b>📦 DG-LAB 中繼伺服器部署（Bun）</b></summary>

1. 取得伺服器程式碼：[dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server)
2. 安裝 [Bun](https://bun.sh) 後啟動對應版本伺服器：
   ```bash
   bun run v3     # V3 伺服器, 預設連接埠 9999（相容舊版 APP）
   bun run v4     # V4 伺服器, 預設連接埠 9998（需 DG-LAB 4 APP）
   ```
3. 連接埠等可透過 `.env` 修改（`PORT` / `PREFIX` 等，參考儲存庫 README）
4. 確保 AstrBot 與 DG-LAB APP 均可存取該伺服器；`/dglab bind` 時插件會自動辨識協定版本並在回覆中標注

</details>

<details>
<summary><b>❓ 連線疑難排解（對應 <a href="https://github.com/backrooms-yrc/astrbot_plugin_currentcortex/issues/3">issue #3</a>）</b></summary>

- **`伺服器未確認連線: 等待伺服器分配 clientId 逾時`**：舊版本（≤ v1.9.1）按 v2 協定在連線路徑中攜帶自生成的 clientId，被 v3 伺服器誤判為 APP 端而拒絕。升級到 v2.0.0+ 即可，v2.0.0 起控制端裸連根路徑並使用伺服器分配的 clientId。
- **`連線失敗: server rejected WebSocket connection: HTTP 404`**：連線了 v4 伺服器但位址帶了多餘路徑。v4 伺服器僅在根路徑（或 `PREFIX` 設定的路徑）接受連線，請檢查 `dglab_server_url` 是否與伺服器實際監聽路徑一致。
- **V4 綁定後控制無效**：確認使用 **DG-LAB 4 APP** 掃描（新版 QR Code `dungeon-lab.cn/s/...` 舊版 APP 無法識別）；若 APP 內有多個裝置插槽，插件會自動選擇第一個真實連線裝置的插槽。

</details>

<details>
<summary><b>🔄 從舊版 DG-LAB JSON 設定移轉</b></summary>

v1.2.0 及更早版本使用 JSON 字串設定（已棄用）：

```json
{ "dglab": { "server_url": "ws://your-server:9999", "heartbeat_interval": 60, "auto_connect": false } }
```

新格式直接填三個獨立項：`dglab_server_url`、`dglab_heartbeat_interval`、`dglab_auto_connect`。插件仍會偵測舊版 `dglab` JSON 設定：若新項留空但舊設定存在，會自動讀取並提示移轉。建議盡快手動移轉。

</details>

### 跨群聊記憶

見 [🧠 跨群聊記憶](#-跨群聊記憶) 章節。

### 分段回覆

見 [✂️ 分段回覆](#️-分段回覆) 章節。

### LLM 工具

見 [🤖 LLM 工具](#-llm-工具) 章節。開關為 `llm_tools_enable`（預設開啟）。

### 插件宣傳（QQ 群）

插件內建官方交流群號 **1106353813**，安裝後自動生效，無需任何設定。群號透過兩個管道展示：

- **`/交流群` 指令**（別名 `/群号` `/加群`）：使用者主動查詢時回傳群號
- **指令說明／錯誤提示**：`/pixiv help`、`/点歌 help` 等說明文字和「API Key 未設定」錯誤提示末尾附上一行群號

> ⚠️ 群號**不會**注入到機器人日常回覆中，避免污染對話內容。

---

## ❓ 常見問題

<details>
<summary><b>安裝後插件無法載入？</b></summary>

1. Python 版本是否 >= 3.10
2. 是否已安裝相依套件：`pip install aiohttp>=3.8.0`（DG-LAB 還需 `websockets>=10.0`）
3. AstrBot 版本是否 >= 4.15（本插件需要較新的 API，舊版無法載入）
4. 查看 AstrBot 日誌中的錯誤訊息

</details>

<details>
<summary><b>呼叫指令提示「功能未啟用 / 未設定 API Key」？</b></summary>

需先在 [LeiZ API 官網](https://api.bileizhen.top) 取得 API Key（見[設定 API Key](#2-設定-api-key-必填)），再填入設定面板的 `leiz_api_key` 欄位，儲存後重新啟動插件。可用 `/apitest` 驗證各 API 連通性。Pixiv / 一言 / 天氣 / 男娘 / 點歌 均依賴此 Key。

</details>

<details>
<summary><b>Pixiv 圖片無法顯示？</b></summary>

1. 反向代理網域不可用：嘗試更換 `image_proxy` 設定項
2. 網路連線問題：檢查伺服器能否存取外網
3. API 服務異常：稍後重試

</details>

<details>
<summary><b>如何排除 AI 生成的 Pixiv 作品？</b></summary>

1. **全域排除**：設定 `exclude_ai` 為 `true`
2. **單次排除**：指令中使用 `excludeAI:true`，如 `/pixiv tag:萝莉 excludeAI:true`

</details>

<details>
<summary><b>請求逾時怎麼辦？</b></summary>

適當增大 `request_timeout`（單位秒），檢查網路狀況；頻繁逾時多為 API 繁忙，建議稍後重試。

</details>

<details>
<summary><b>天氣查詢支援哪些城市？</b></summary>

支援中國主要城市，建議使用簡體城市名（如「广州市」「北京」，因上游 API 以簡體比對），最長 50 字元。

</details>

<details>
<summary><b>DG-LAB 功能無法使用 / 綁定失敗？</b></summary>

1. 是否安裝相依套件：`pip install websockets>=10.0`
2. 是否設定 `dglab_server_url`，且中繼伺服器正在執行、可存取
3. QR Code 產生後需在有效期內用 APP 掃描
4. 確認 APP 版本支援 Socket V2，且僅支援**郊狼脈衝主機 3.0**
5. 查看 AstrBot 日誌中 `[DGLab]` 相關錯誤

</details>

<details>
<summary><b>DG-LAB 連線中斷怎麼辦？</b></summary>

系統會自動重連（最多 2 次）；仍失敗可用 `/dglab unbind` 解除綁定後重新 `/dglab bind`，並用 `/dglab status` 查看狀態。

</details>

<details>
<summary><b>多人同時使用會衝突嗎？</b></summary>

不會。每位使用者擁有獨立的裝置綁定與連線，操作完全隔離，支援最多 50 個並行連線。

</details>

### 錯誤處理一覽

| 錯誤類型 | 可能原因 | 解決方案 |
| --- | --- | --- |
| 網路錯誤 | 網路連線失敗 | 檢查網路連線 |
| 請求逾時 | API 回應慢 | 增大 `request_timeout` 或稍後重試 |
| HTTP 錯誤 | API 服務異常（401/402/5xx 等） | 檢查 API Key / 服務狀態 |
| 參數錯誤 | 指令格式不正確 | 傳送 `/xxx help` 查看說明 |
| 無結果 | 未找到匹配內容 | 更換搜尋參數 |
| 資料格式異常 | API 回傳異常資料 | 稍後重試 |

---

## 🛠️ 技術架構

### 專案結構

```text
astrbot_plugin_currentcortex/
├── main.py                      # 主程式：所有指令註冊與 API 用戶端
├── _pages_api.py                # 總覽 Pages 後端 API（儀表板/設定/郊狼/說明）
├── pages/                       # 總覽 Pages 前端（mdui 2 元件庫，全部本地化）
│   └── cc-dashboard/
│       ├── index.html           # Pages 入口
│       ├── app.js               # Vue 3 單頁應用（5 個頁面）
│       ├── app.css              # 晴空藍＋雪霧白主題
│       └── vendor/              # 本地相依：Vue 3 / mdui 2 / Material Icons 字型
├── cross_group_memory.py        # 跨群聊記憶持久化儲存
├── group_switch_store.py        # 按群聊開關狀態持久化儲存
├── media_parser.py              # 小紅書/B站/抖音 媒體解析
├── media_cmds.py                # 媒體指令輔助
├── dglab_client.py              # DG-LAB WebSocket 用戶端封裝
├── dglab_device_store.py        # DG-LAB 裝置綁定關係持久化
├── dglab_connection_pool.py     # DG-LAB 連線池與狀態管理
├── dglab_commands.py            # DG-LAB 指令處理器
├── dglab_webui.py               # CCDG WebUI 控制面板
├── dglab_user_store.py          # DG-LAB 使用者儲存
├── dglab_permission_store.py    # DG-LAB 權限儲存
├── dglab_post_store.py          # DG-LAB 投稿廣場儲存
├── dglab_email_store.py         # DG-LAB 電子郵件儲存
├── dglab_turnstile_store.py     # DG-LAB Turnstile 儲存
├── dglab_chat_store.py          # DG-LAB 聊天儲存
├── metadata.yaml                # 插件中繼資料
├── CHANGELOG.md                 # 更新日誌
├── CONTRIBUTING.md              # 貢獻指南
├── _conf_schema.json            # 設定結構定義
├── requirements.txt             # Python 相依套件
├── README.md                    # 專案文件（簡體中文）
├── README_EN.md                 # 專案文件（英文）
├── README_JA.md                 # 專案文件（日文）
└── README_ZH-TW.md              # 專案文件（繁體中文）
```

### 核心模組

**內容取得與解析：**
- **PixivAPIClient** ([main.py](main.py))：Pixiv API 用戶端，按過濾參數自動路由 GET 隨機 / POST 篩選 API
- **HitokotoAPIClient** / **WeatherAPIClient** / **FemboyAPIClient**：一言 / 天氣 / 男娘 API 用戶端
- **NeteaseAPIClient**：網易雲用戶端，點歌附指數退避重試
- **KugouAPIClient**：酷狗音樂用戶端（搜尋 / 播放連結）
- **MediaParserManager** ([media_parser.py](media_parser.py))：小紅書 / B站 / 抖音 連結解析
- **CommandParser** ([main.py](main.py))：`key:value` 參數與快捷語法解析器

**DG-LAB 裝置管理：**
- **DGLabClient** ([dglab_client.py](dglab_client.py))：WebSocket 用戶端，連線管理 / 訊息收發 / 心跳保活
- **DeviceStore** ([dglab_device_store.py](dglab_device_store.py))：使用者-裝置綁定關係持久化（執行緒安全）
- **DeviceConnectionPool** ([dglab_connection_pool.py](dglab_connection_pool.py))：連線池，多使用者並行 / 連線複用 / 自動重連 / 閒置清理
- **DGLabCommandHandler** ([dglab_commands.py](dglab_commands.py))：指令解析 / 驗證 / 執行 / 格式化
- **DGLabWebUI** ([dglab_webui.py](dglab_webui.py))：CCDG WebUI 瀏覽器遠端控制面板

**主插件與記憶：**
- **CurrentCortexPlugin(Star)** ([main.py](main.py))：主插件類別，整合所有功能並註冊指令
- **CrossGroupMemoryStore** ([cross_group_memory.py](cross_group_memory.py))：跨群聊共享記憶，JSON 持久化
- **GroupSwitchStore** ([group_switch_store.py](group_switch_store.py))：按群聊開關狀態，JSON 持久化

### 設計特點

- **非同步架構**：基於 `asyncio` + `aiohttp` / `websockets`，非阻塞 I/O
- **模組化設計**：DG-LAB 功能獨立為多個模組，職責清晰
- **統一介面**：所有 API 用戶端遵循相同設計模式
- **健全容錯**：全面的例外處理、參數驗證、按需重試
- **資料持久化**：DG-LAB 綁定存於 `data/dglab_bindings.json`，跨群記憶存於 `data/currentcortex_cross_group.json`（均符合 AstrBot 規範）
- **資源管理**：連線池自動清理閒置連線，防止資源洩漏
- **多租戶隔離**：每位使用者獨立連線，操作互不干擾

---

## 🤝 貢獻指南

歡迎提交 Issue 與 PR！Bug 回報 / 功能建議已設定 Issue 範本，PR 有自測清單範本。

開發環境搭建、專案結構、測試執行方式、提交規範與 PR 流程見 **[CONTRIBUTING.md](CONTRIBUTING.md)**。

> 💬 也可以先到 QQ 交流群 **1106353813** 討論想法，大改動建議先對齊再動手。

---

## 📄 開源授權與致謝

本專案採用 [MIT License](LICENSE) 開源。

致謝：

- [LeiZ API](https://api.bileizhen.top) — 提供 Pixiv / 一言 / 天氣 / 男娘 / 網易雲 等 API 服務
- [AstrBot](https://github.com/AstrBot) — 聊天機器人框架
- [dglab-websocket-server](https://github.com/dungeonlab-open/dglab-websocket-server) — DG-LAB WebSocket 協定與中繼伺服器

---

**版本**：v2.0.11（各版本變更詳見 [CHANGELOG.md](CHANGELOG.md)）  
**儲存庫**：[GitHub](https://github.com/backrooms-yrc/astrbot_plugin_currentcortex)



