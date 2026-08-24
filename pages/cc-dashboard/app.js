// CurrentCortex 总Pages —— Vue 3 + mdui 2（Web Components）
// 通过 window.AstrBotPluginPage (bridge) 与后端通信。
// 5 个 tab 用 hash 路由：dashboard / help / settings / coyote / contact

const { createApp, ref } = Vue;

// ---------------------------------------------------------------- bridge
const bridge = window.AstrBotPluginPage;
const apiGet = (ep, params) => bridge.apiGet(ep, params);
const apiPost = (ep, body) => bridge.apiPost(ep, body);

if (bridge && bridge.ready) {
  bridge.ready().catch(() => {});
}

// ---------------------------------------------------------------- 工具函数
function fmtUptime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (d > 0) return `${d}天 ${h}小时 ${m}分`;
  if (h > 0) return `${h}小时 ${m}分 ${s}秒`;
  if (m > 0) return `${m}分 ${s}秒`;
  return `${s}秒`;
}

function fmtDate(ts) {
  if (!ts) return "-";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function toast(msg) {
  if (window.mdui && mdui.snackbar) {
    mdui.snackbar({ message: msg, placement: "top", autoCloseDelay: 3500 });
  } else {
    console.log("[CurrentCortex] " + msg);
  }
}

// ---------------------------------------------------------------- 状态
const current = ref("dashboard");
const status = ref(null);
const helpData = ref(null);
const configGroups = ref([]);
const coyote = ref(null);
const saving = ref(false);
const coyoteBusy = ref(false);
const publicIp = ref("");
const relay = ref(null);
const relayBusy = ref({ v3: false, v4: false });
const relayPublic = ref({ v3: "", v4: "" });
// 两步部署确认:第一步披露将执行的系统级操作,第二步键入版本号防误触
const relayConfirmOpen = ref({ v3: false, v4: false });
const relayConfirmText = ref({ v3: "", v4: "" });
const relayMeta = {
  v3: {
    title: "V3 中转服务器",
    desc: "旧版配对协议（端口 9999），旧版 DG-LAB APP 与新版 APP 均可扫码，适合兼容存量设备。",
  },
  v4: {
    title: "V4 中转服务器",
    desc: "新版透传协议（端口 9998），需 DG-LAB 4 APP 扫码，官方推荐协议。",
  },
};
let toastTimer = null;

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  current.value = ["dashboard", "help", "settings", "coyote", "contact"].includes(h)
    ? h
    : "dashboard";
}
window.addEventListener("hashchange", parseHash);
parseHash();

// ---------------------------------------------------------------- 加载
async function loadStatus() {
  try {
    status.value = await apiGet("cc/status");
  } catch (e) {
    toast("加载仪表板失败: " + (e && e.message ? e.message : e));
  }
}

async function loadHelp() {
  if (helpData.value) return;
  try {
    helpData.value = await apiGet("cc/help");
  } catch (e) {
    toast("加载帮助失败: " + (e && e.message ? e.message : e));
  }
}

async function loadConfig() {
  try {
    configGroups.value = (await apiGet("cc/config")).groups || [];
  } catch (e) {
    toast("加载配置失败: " + (e && e.message ? e.message : e));
  }
}

async function loadCoyote() {
  try {
    coyote.value = await apiGet("cc/coyote/info");
    if (coyote.value && coyote.value.is_public) {
      publicIp.value = (await apiGet("cc/coyote/public_ip")).ip || "";
    } else {
      publicIp.value = "";
    }
  } catch (e) {
    toast("加载郊狼状态失败: " + (e && e.message ? e.message : e));
  }
}

async function loadRelay() {
  try {
    relay.value = await apiGet("cc/coyote/relay");
    for (const v of ["v3", "v4"]) {
      const st = relay.value && relay.value[v];
      if (st && st.exposed && !relayPublic.value[v]) {
        // 已暴露时补拉公网 IP 用于展示地址
        try {
          relayPublic.value[v] = (await apiGet("cc/coyote/public_ip")).ip || "";
        } catch (e) { /* 保持空,由 relayUrl 回落 */ }
      } else if (st && !st.exposed) {
        relayPublic.value[v] = "";
      }
    }
  } catch (e) {
    toast("加载中转状态失败: " + (e && e.message ? e.message : e));
  }
}

// ---------------------------------------------------------------- 中转服务器操作
function relayUrl(v) {
  const st = relay.value && relay.value[v];
  if (!st) return "";
  const ip = relayPublic.value[v];
  return ip ? `ws://${ip}:${st.port}` : st.local_url || "";
}

function openRelayConfirm(v) {
  relayConfirmText.value[v] = "";
  relayConfirmOpen.value[v] = true;
}

function cancelRelayConfirm(v) {
  relayConfirmOpen.value[v] = false;
  relayConfirmText.value[v] = "";
}

function relayConfirmReady(v) {
  return (relayConfirmText.value[v] || "").trim().toLowerCase() === v;
}

async function relayDeploy(v) {
  // 仅当键入的版本号与目标一致时才发起部署（后端同样校验 confirm）
  if (!relayConfirmReady(v)) return;
  relayBusy.value[v] = true;
  try {
    const res = await apiPost("cc/coyote/relay/deploy", {
      version: v,
      confirm: (relayConfirmText.value[v] || "").trim(),
    });
    if (res.ok) {
      toast(res.message || "部署成功");
    } else {
      toast("部署失败: " + (res.message || "未知错误"));
    }
  } catch (e) {
    toast("部署失败: " + (e && e.message ? e.message : e));
  } finally {
    cancelRelayConfirm(v);
    await loadRelay();
    relayBusy.value[v] = false;
  }
}

async function relayUninstall(v) {
  const st = relay.value && relay.value[v];
  if (!st || !st.deployed) return;
  if (window.mdui && mdui.confirm) {
    try {
      await mdui.confirm({
        headline: `确认卸载 ${v.toUpperCase()} 中转服务器？`,
        description:
          "将停止并删除 systemd 服务、收回防火墙放行（源码目录保留，重新部署秒级完成）。\n" +
          "已通过该中转绑定的设备会断开连接，需要重新扫码。",
        confirmText: "确认卸载",
        cancelText: "取消",
      });
    } catch (e2) {
      return;
    }
  }
  relayBusy.value[v] = true;
  try {
    const res = await apiPost("cc/coyote/relay/uninstall", { version: v, confirm: true });
    toast(res.ok ? res.message || "已卸载" : "卸载失败: " + (res.message || ""));
  } catch (e) {
    toast("卸载失败: " + (e && e.message ? e.message : e));
  } finally {
    await loadRelay();
    relayBusy.value[v] = false;
  }
}

async function relayExposeToggle(v, ev) {
  const st = relay.value && relay.value[v];
  if (!st || !st.deployed) return;
  syncSwitch(ev, !!st.exposed);
  const wantOn = !st.exposed;
  relayBusy.value[v] = true;
  try {
    if (wantOn && window.mdui && mdui.confirm) {
      // 危险操作：先弹确认框（确认 resolve，取消/ESC reject）
      try {
        await mdui.confirm({
          headline: `确认放行 ${v.toUpperCase()} 中转端口？`,
          description:
            `将放行端口 ${st.port}/tcp：DG-LAB APP 可经公网地址接入该中转。\n` +
            "建议仅在使用期间开启，用完关闭。",
          confirmText: "确认放行",
          cancelText: "取消",
        });
      } catch (e2) {
        return; // 取消 → 不执行（finally 里 loadRelay 同步开关状态）
      }
    }
    const res = wantOn
      ? await apiPost("cc/coyote/relay/expose", { version: v, confirm: true })
      : await apiPost("cc/coyote/relay/unexpose", { version: v });
    if (wantOn) {
      relayPublic.value[v] = res.ip || "";
      toast(res.warning || `已放行端口 ${st.port}，公网地址 ${relayUrl(v)}`);
    } else {
      relayPublic.value[v] = "";
      toast(res.message || "已收回公网放行");
    }
  } catch (e) {
    toast("操作失败: " + (e && e.message ? e.message : e));
  } finally {
    await loadRelay();
    relayBusy.value[v] = false;
  }
}

function copyText(text, label) {
  if (!text) return;
  try {
    navigator.clipboard.writeText(text);
    toast((label || "地址") + "已复制：" + text);
  } catch (e) {
    toast("复制失败，请手动复制：" + text);
  }
}

// ---------------------------------------------------------------- 操作
function syncSwitch(ev, checked) {
  // mdui-switch 受控组件陷阱:用户点击后 DOM checked 先行翻转,若异步操作后
  // 数据值与之前相同(失败/取消),Vue 因新旧 vnode 值一致会跳过 patch,
  // 开关视觉卡在"已点击"状态。因此处理起点先把 DOM 回同步到数据值,
  // 此后视觉变化只由数据驱动。
  const el = ev && ev.target;
  if (el) el.checked = !!checked;
}

async function saveConfig() {
  const payload = {};
  for (const g of configGroups.value) {
    for (const it of g.items) {
      let v = it.value;
      if (it.type === "bool") {
        v = !!v;
      } else if ((it.type === "int" || it.type === "float") && v !== "" && v !== null && v !== undefined) {
        v = Number(v);
      } else if (v === "") {
        v = null;
      }
      payload[it.key] = v;
    }
  }
  saving.value = true;
  try {
    const res = await apiPost("cc/config", payload);
    toast(res.message || "已保存并热重载");
    setTimeout(() => {
      loadStatus();
      loadCoyote();
    }, 1200);
  } catch (e) {
    toast("保存失败: " + (e && e.message ? e.message : e));
  } finally {
    saving.value = false;
  }
}

async function webuiToggle(ev) {
  // 总开关：仅启用/关闭 WebUI，监听保持 127.0.0.1（本机），不涉及公网暴露
  syncSwitch(ev, !!(coyote.value && coyote.value.enabled));
  coyoteBusy.value = true;
  try {
    const wantOn = !(coyote.value && coyote.value.enabled);
    if (wantOn) {
      const res = await apiPost("cc/coyote/enable", {});
      coyote.value = {
        ...coyote.value,
        enabled: true,
        running: !!res.reloaded,
        host: res.host || "127.0.0.1",
        port: res.port || (coyote.value ? coyote.value.port : 9178),
        is_public: !!res.is_public,
        local_url: res.local_url || "http://localhost:9178",
      };
      toast(res.message || "已启用 WebUI");
    } else {
      await apiPost("cc/coyote/disable", {});
      coyote.value = {
        ...coyote.value,
        enabled: false,
        running: false,
        host: "127.0.0.1",
        is_public: false,
        local_url: "",
      };
      publicIp.value = "";
      toast("已关闭 WebUI");
    }
  } catch (e) {
    toast("操作失败: " + (e && e.message ? e.message : e));
  } finally {
    coyoteBusy.value = false;
  }
}

async function exposeToggle(ev) {
  // 暴露公网开关：仅当 WebUI 已启用时可见。
  // 打开 -> 监听改为 0.0.0.0（公网可访问）并探测公网 IP；
  // 关闭 -> 恢复 127.0.0.1，WebUI 总开关状态保留。
  syncSwitch(ev, !!(coyote.value && coyote.value.is_public));
  coyoteBusy.value = true;
  try {
    const wantOn = !(coyote.value && coyote.value.is_public);
    if (wantOn) {
      // 危险操作：先弹确认框。
      // 注意 mdui.confirm 的语义：点击「确认」时 resolve（无值），
      // 点击「取消」/按 ESC /点遮罩时 reject —— 不能依赖返回值判断。
      if (window.mdui && mdui.confirm) {
        try {
          await mdui.confirm({
            headline: "确认暴露公网？",
            description:
              "开启后 WebUI 将监听 0.0.0.0:9178，并自动在系统防火墙（ufw）放行该端口，公网任意地址都能访问注册、登录、设备控制等接口。\n" +
              "强烈建议先配置反向代理 + 鉴权（如 Caddy + BasicAuth、Nginx + IP 白名单）。关闭开关会自动恢复本机监听并收回防火墙放行。",
            confirmText: "确认暴露",
            cancelText: "取消",
          });
        } catch (e2) {
          return; // 用户取消或关闭弹窗 → 不执行
        }
      }
      const res = await apiPost("cc/coyote/expose", {
        port: coyote.value ? coyote.value.port : undefined,
        confirm: true,
      });
      publicIp.value = res.ip || "";
      coyote.value = {
        ...coyote.value,
        enabled: true,
        running: !!res.reloaded,
        host: res.host || "0.0.0.0",
        port: res.port,
        is_public: true,
        local_url: `http://${res.ip}:${res.port}`,
      };
      toast(res.warning || "已暴露公网，请配置反代 + 鉴权！");
    } else {
      const res = await apiPost("cc/coyote/unexpose", {});
      coyote.value = {
        ...coyote.value,
        host: "127.0.0.1",
        is_public: false,
        local_url: `http://localhost:${coyote.value ? coyote.value.port : 9178}`,
      };
      publicIp.value = "";
      toast(res.message || "已取消公网暴露");
    }
  } catch (e) {
    toast("操作失败: " + (e && e.message ? e.message : e));
  } finally {
    coyoteBusy.value = false;
  }
}

function copyGroupNo() {
  try {
    navigator.clipboard.writeText("1106353813");
    toast("群号已复制：1106353813");
  } catch (e) {
    toast("复制失败，请手动记下群号：1106353813");
  }
}

// ---------------------------------------------------------------- 设置项中文说明
// 每个配置 key 的「碳基生物能看懂」的中文名 + 人话解释。
// 后端返回的 description/hint 作为补充说明展示。
const SETTINGS_META = {
  // —— 基础 ——
  llm_tools_enable: { name: "AI 自动操作开关", hint: "开启后，AI 可以直接帮你发图、点歌、电击等（比如你说“来张图”）。关闭则只能手动用斜杠命令。" },
  // —— Pixiv ——
  default_r18: { name: "默认图片分级", hint: "0 = 全年龄，1 = 只出 R18，2 = 混合。群聊建议保持全年龄。" },
  default_num: { name: "默认图片数量", hint: "一次发几张图，范围 1~20。" },
  default_size: { name: "默认图片尺寸", hint: "original = 原图（最大），regular = 中等，small = 小图，thumb = 缩略图。" },
  image_proxy: { name: "图片加速域名", hint: "下载图片时用的代理域名，一般保持默认即可。" },
  exclude_ai: { name: "排除 AI 作品", hint: "开启后，AI 生成的图片不会出现在随机图里。" },
  request_timeout: { name: "请求超时（秒）", hint: "连不上图库时等多久算超时。网络差可以适当调大。" },
  // —— 音乐 ——
  music_file_max_bytes: { name: "音乐文件体积上限", hint: "音乐文件超过这个体积会自动转成小体积 MP3 再发。默认 26214400（25MB）。" },
  music_cooldown: { name: "点歌冷却（秒）", hint: "同一会话连续点歌要间隔的秒数，防止刷屏把服务器拖垮。" },
  music_default_source: { name: "默认音源", hint: "auto = 网易云优先、失败自动换酷狗；netease = 只用网易云；kugou = 只用酷狗。" },
  // —— LeiZ ——
  leiz_api_key: { name: "LeiZ API 密钥", hint: "图库、点歌、一言、天气等接口的密钥。留空 = 这些功能全部禁用。" },
  // —— 郊狼 ——
  dglab_server_url: { name: "郊狼服务器地址", hint: "DG-LAB 中转服务器，格式如 ws://192.168.1.100:9999。填了之后 /dglab bind 可省略地址。" },
  dglab_heartbeat_interval: { name: "心跳间隔（秒）", hint: "多久和服务器报一次到，防止连接被判定掉线。建议 30~120。" },
  dglab_auto_connect: { name: "开机自动连接", hint: "插件启动时自动连上郊狼服务器。一般建议关闭，按需连接更省资源。" },
  dglab_webui_enabled: { name: "启用网页控制台", hint: "网页版遥控面板。也可以在“郊狼控制”页用总开关开启。" },
  dglab_webui_host: { name: "网页控制台监听地址", hint: "127.0.0.1 = 只有本机能访问（安全）；0.0.0.0 = 公网可访问（危险，请用“郊狼控制”页的开关管理）。" },
  dglab_webui_port: { name: "网页控制台端口", hint: "控制台用哪个端口，默认 9178。" },
  // —— 跨群记忆 ——
  cross_group_enable: { name: "跨群共享记忆", hint: "开启后所有群共用一份聊天记忆。注意：其他群聊的内容会被提供给 AI，请确认符合隐私预期。" },
  cross_group_max_cnt: { name: "记忆条数上限", hint: "总共保留多少条记忆，建议 200~1000。越大越占内存。" },
  cross_group_inject_cnt: { name: "每次注入条数", hint: "每次回复喂给 AI 几条最近的共享记忆，建议 10~50。越大越费 token。" },
  // —— 按群开关 ——
  group_switch_enable: { name: "按群开关功能", hint: "开启后可用 /开关 命令在单个群里单独关闭/开启本插件。" },
  group_switch_admin_only: { name: "仅管理员可操作", hint: "只有群管理员能用 /开关 命令，防止群友乱关插件。" },
  // —— 分段回复 ——
  reply_seg_enable: { name: "分段回复总开关", hint: "开启后，机器人的回复会拆成多条消息分次发送，更像真人逐句说话。注意别和框架自带的分段同时开。" },
  reply_seg_only_llm: { name: "只分段 AI 回复", hint: "只拆 AI 说的话；关闭的话，/pixiv 这类命令的回复也会被拆。" },
  reply_seg_mention: { name: "首条 @ 并引用", hint: "拆开的第一条会 @ 并引用你，让分段回复有明确归属。平台不支持时会自动降级。" },
  reply_seg_mode: { name: "分段方式", hint: "llm = AI 按语义拆（最自然，但每次回复多一次 AI 调用）；punct = 按标点拆（最快零消耗）；length = 按长度拆。" },
  reply_seg_llm_provider_id: { name: "分段专用模型", hint: "专门用来拆句子的模型，建议选个便宜的快速模型。留空 = 复用当前聊天用的模型。" },
  reply_seg_llm_density: { name: "分段密度", hint: "low = 每段较长；medium = 适中；high = 每段短碎、更像刷屏。" },
  reply_seg_llm_max_segments: { name: "段数上限", hint: "最多拆成几段。0 = 按上方密度自动推算。" },
  reply_seg_llm_min_chars: { name: "最短才拆字数", hint: "回复比这个字数短就不拆，直接整段发送（省 AI 调用）。建议 20~50。" },
  reply_seg_llm_timeout: { name: "AI 拆句超时（秒）", hint: "AI 拆句超过这个秒数就放弃，改用规则拆，避免回复卡顿。建议 8~30。" },
  reply_seg_llm_max_tokens: { name: "AI 输出上限", hint: "拆句结果的 token 上限，一般保持默认即可。" },
  reply_seg_split_symbols: { name: "切分符号", hint: "在哪些标点处切开（标点保留在段尾）。默认含中英文逗号句号问号等。" },
  reply_seg_split_words: { name: "切分词", hint: "在这些词后面切开，用于语气词，如：喵 qwq owo awa。" },
  reply_seg_merge_threshold: { name: "短段合并阈值", hint: "比这短的段会并进上一段，消除碎片。0 = 不合并。" },
  reply_seg_min_length: { name: "最小段长", hint: "比这短就不切分，避免产生过短片段。建议 10~30。" },
  reply_seg_max_length: { name: "最大段长", hint: "超过这个长度才会找标点切分。建议 50~150。" },
  reply_seg_delay_range: { name: "发送间隔（秒）", hint: "每段之间的随机等待时间，格式“最小,最大”，如 0.8,2.5。模拟真人打字节奏。" },
};

function metaOf(key) {
  return SETTINGS_META[key] || {};
}

// ---------------------------------------------------------------- 导航
const NAV = [
  { key: "dashboard", label: "仪表板", icon: "dashboard--outlined" },
  { key: "help", label: "帮助中心", icon: "help--outlined" },
  { key: "settings", label: "设置", icon: "settings--outlined" },
  { key: "coyote", label: "郊狼控制", icon: "bolt--outlined" },
  { key: "contact", label: "联系我们", icon: "forum--outlined" },
];

// 加群链接（QQ 群 1106353813）
const GROUP_URL =
  "https://qun.qq.com/universal-share/share?ac=1&authKey=OmLNlwPdKBlOMNNic9zCRIlfAVn%2BqsvY0rZDEpEYLNsZ6D5UvREADl%2FeNd2nGAUH&busi_data=eyJncm91cENvZGUiOiIxMTA2MzUzODEzIiwidG9rZW4iOiJERWFBR1hSV1djMSswSHI4MEpmQzhmTFlzZTN0Q2VvbFEvZXpQbWZIaHNNSW5Dd2dHcFVKVVJmTTdzWG1OWXBVIiwidWluIjoiMTk0NTgyNjM0NiJ9&data=AFoZ21e7OHbTEKvm7w_zeEuScAfmBnqoa2V6OZFXfaajJ7cTjHQNk3JxtyRUTFE69pnNSWekOVIAA54qMXW97Q&svctype=4&tempid=h5_group_info";

const REPO_URL = "https://github.com/backrooms-yrc/astrbot_plugin_currentcortex";

// ---------------------------------------------------------------- 模板
const TEMPLATE = /* html */ `
  <div class="cc-layout">
    <!-- ===== 侧边导航 ===== -->
    <aside class="cc-side">
      <div class="cc-brand">
        <mdui-icon name="bolt" class="cc-brand-icon"></mdui-icon>
        <span class="cc-brand-name">CurrentCortex</span>
      </div>
      <mdui-list class="cc-nav-list">
        <mdui-list-item
          v-for="n in NAV"
          :key="n.key"
          :active="current === n.key"
          @click="go(n.key)"
        >
          <mdui-icon slot="icon" :name="n.icon"></mdui-icon>
          {{ n.label }}
        </mdui-list-item>
      </mdui-list>
    </aside>

    <!-- ===== 主内容 ===== -->
    <main class="cc-main">
      <!-- ===== 仪表板 ===== -->
      <section v-if="current === 'dashboard'" class="cc-section">
        <div class="cc-head">
          <h1>仪表板</h1>
          <p>CurrentCortex 插件运行情况总览</p>
        </div>

        <template v-if="status">
          <div class="cc-cards">
            <mdui-card class="cc-card">
              <mdui-icon slot="icon" name="schedule" class="cc-card-icon"></mdui-icon>
              <div class="cc-card-value">{{ fmtUptime(status.uptime_sec) }}</div>
              <div class="cc-card-label">运行时长</div>
            </mdui-card>
            <mdui-card class="cc-card">
              <mdui-icon slot="icon" name="devices" class="cc-card-icon"></mdui-icon>
              <div class="cc-card-value">{{ status.device_count }}</div>
              <div class="cc-card-label">已绑定设备</div>
            </mdui-card>
            <mdui-card class="cc-card">
              <mdui-icon slot="icon" name="link" class="cc-card-icon"></mdui-icon>
              <div class="cc-card-value">{{ status.active_connections }}</div>
              <div class="cc-card-label">活跃连接</div>
            </mdui-card>
            <mdui-card class="cc-card">
              <mdui-icon slot="icon" name="group" class="cc-card-icon"></mdui-icon>
              <div class="cc-card-value">{{ status.user_count }}</div>
              <div class="cc-card-label">注册用户</div>
            </mdui-card>
          </div>

          <mdui-card class="cc-panel">
            <h2 class="cc-panel-title">插件信息</h2>
            <div class="mdui-table">
              <table>
                <tbody>
                  <tr><td>名称</td><td>{{ status.metadata.display_name || status.metadata.name || "CurrentCortex" }}</td></tr>
                  <tr><td>版本</td><td>{{ status.metadata.version || "-" }}</td></tr>
                  <tr><td>作者</td><td>{{ status.metadata.author || "-" }}</td></tr>
                  <tr><td>启动时间</td><td>{{ fmtDate(status.started_at) }}</td></tr>
                  <tr><td>连接错误</td><td>{{ status.error_count }}</td></tr>
                </tbody>
              </table>
            </div>
          </mdui-card>

          <mdui-card class="cc-panel">
            <h2 class="cc-panel-title">功能开关</h2>
            <div class="cc-flags">
              <mdui-chip :selected="!!status.feature_flags.llm_tools_enable">LLM 工具</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.dglab_webui_enabled">郊狼 WebUI</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.cross_group_enable">跨群记忆</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.group_switch_enable">按群开关</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.reply_seg_enable">分段回复</mdui-chip>
            </div>
          </mdui-card>
        </template>
        <div v-else class="cc-loading">
          <mdui-circular-progress></mdui-circular-progress>
        </div>
      </section>

      <!-- ===== 帮助中心 ===== -->
      <section v-if="current === 'help'" class="cc-section">
        <div class="cc-head">
          <h1>帮助中心</h1>
          <p>使用文档与常见问题</p>
        </div>

        <template v-if="helpData">
          <mdui-card
            v-for="(cat, ci) in helpData.docs"
            :key="ci"
            class="cc-panel"
          >
            <h2 class="cc-panel-title">{{ cat.category }}</h2>
            <div v-for="(item, ii) in cat.items" :key="ii" class="cc-qa">
              <details>
                <summary>
                  <mdui-icon name="help--outlined" class="cc-qa-icon"></mdui-icon>
                  <span>{{ item.q }}</span>
                  <mdui-icon name="expand_more" class="cc-qa-arrow"></mdui-icon>
                </summary>
                <p class="cc-qa-a">{{ item.a }}</p>
              </details>
            </div>
          </mdui-card>
        </template>
        <div v-else class="cc-loading">
          <mdui-circular-progress></mdui-circular-progress>
        </div>
      </section>

      <!-- ===== 设置 ===== -->
      <section v-if="current === 'settings'" class="cc-section">
        <div class="cc-head">
          <h1>设置</h1>
          <p>修改插件配置，保存后自动热重载生效</p>
        </div>

        <template v-if="configGroups.length">
          <mdui-card
            v-for="(g, gi) in configGroups"
            :key="gi"
            class="cc-panel"
          >
            <h2 class="cc-panel-title">
              <mdui-icon :name="groupIcon(g.icon)" class="cc-panel-icon"></mdui-icon>
              {{ g.title }}
            </h2>

            <div v-for="(it, ii) in g.items" :key="ii" class="cc-form-row">
              <div class="cc-form-label">
                <div class="cc-form-name">{{ metaOf(it.key).name || it.key }}</div>
                <div class="cc-form-key" v-if="metaOf(it.key).name">{{ it.key }}</div>
              </div>
              <div class="cc-form-ctrl">
                <!-- 开关 -->
                <mdui-switch
                  v-if="it.type === 'bool'"
                  :checked="!!it.value"
                  @change="it.value = $event.target.checked"
                ></mdui-switch>
                <!-- 下拉选择 -->
                <mdui-select
                  v-else-if="it.options"
                  :value="it.value"
                  label=""
                  @change="it.value = $event.target.value"
                >
                  <mdui-menu-item
                    v-for="opt in it.options"
                    :key="opt"
                    :value="opt"
                  >{{ opt }}</mdui-menu-item>
                </mdui-select>
                <!-- 数字输入 -->
                <mdui-text-field
                  v-else-if="it.type === 'int' || it.type === 'float'"
                  type="number"
                  :value="it.value === null || it.value === undefined ? '' : it.value"
                  @input="it.value = $event.target.value"
                ></mdui-text-field>
                <!-- 文本输入 -->
                <mdui-text-field
                  v-else
                  :value="it.value === null || it.value === undefined ? '' : it.value"
                  @input="it.value = $event.target.value"
                ></mdui-text-field>
                <!-- 人话说明 -->
                <div class="cc-form-hint">
                  {{ metaOf(it.key).hint || it.description || it.hint }}
                </div>
              </div>
            </div>
          </mdui-card>

          <div class="cc-save-bar">
            <mdui-button
              variant="filled"
              icon="save"
              :disabled="saving"
              @click="saveConfig"
            >{{ saving ? "保存中…" : "保存并热重载" }}</mdui-button>
          </div>
        </template>
        <div v-else class="cc-loading">
          <mdui-circular-progress></mdui-circular-progress>
        </div>
      </section>

      <!-- ===== 郊狼控制 ===== -->
      <section v-if="current === 'coyote'" class="cc-section">
        <div class="cc-head">
          <h1>郊狼控制</h1>
          <p>中转服务器一键部署（v3/v4）· CCDG WebUI 总开关与公网暴露控制</p>
        </div>

        <!-- 中转服务器一键部署（v3/v4 各一张卡，独立部署/卸载） -->
        <template v-if="relay">
          <mdui-card v-for="v in ['v3', 'v4']" :key="v" class="cc-panel">
            <h2 class="cc-panel-title">
              <mdui-icon name="dns" class="cc-panel-icon"></mdui-icon>
              {{ relayMeta[v].title }}
              <span
                class="cc-relay-badge"
                :class="{ on: relay[v].deployed, run: relay[v].deployed && relay[v].running }"
              >{{ relay[v].deployed ? (relay[v].running ? "运行中" : "已停止") : "未部署" }}</span>
            </h2>
            <div class="cc-coyote-desc">{{ relayMeta[v].desc }}</div>

            <!-- 未部署：一键部署（两步确认：披露执行内容 → 键入版本号） -->
            <template v-if="!relay[v].deployed">
              <div class="cc-relay-actions">
                <mdui-button
                  variant="filled"
                  icon="rocket_launch"
                  :disabled="relayBusy[v] || !(relay.env && relay.env.git)"
                  @click="openRelayConfirm(v)"
                >一键部署</mdui-button>
                <span
                  v-if="relay.env && !relay.env.git"
                  class="cc-coyote-busy"
                >系统缺少 git，请先安装 git 后再部署</span>
              </div>

              <!-- 第一步：披露将在服务器上执行的系统级操作 -->
              <div v-if="relayConfirmOpen[v] && !relayBusy[v]" class="cc-relay-confirm">
                <div class="cc-relay-confirm-title">确认在服务器上执行以下系统级操作</div>
                <ul class="cc-relay-confirm-list">
                  <li>若缺少 Bun 运行时，执行官方安装脚本（bun.sh）安装到 /root/.bun</li>
                  <li>克隆官方仓库 dglab-websocket-server 到 /root/dglab-relay/{{ v }}</li>
                  <li>写入 .env 配置与 systemd 服务 dglab-relay-{{ v }}（开机自启、崩溃自动拉起）</li>
                  <li>不修改防火墙：端口默认仅本机可达，公网暴露需另行开启「暴露公网」开关</li>
                </ul>
                <!-- 第二步：键入版本号，防止误触 -->
                <mdui-text-field
                  class="cc-relay-confirm-input"
                  :label="'键入 ' + v + ' 确认部署'"
                  :value="relayConfirmText[v]"
                  @input="relayConfirmText[v] = $event.target.value"
                ></mdui-text-field>
                <div class="cc-relay-actions">
                  <mdui-button
                    variant="filled"
                    icon="rocket_launch"
                    :disabled="!relayConfirmReady(v)"
                    @click="relayDeploy(v)"
                  >确认部署</mdui-button>
                  <mdui-button variant="text" @click="cancelRelayConfirm(v)">取消</mdui-button>
                </div>
              </div>

              <div v-if="relayBusy[v]" class="cc-relay-actions">
                <span class="cc-coyote-busy">
                  克隆官方仓库 / 安装依赖 / 启动服务，约需 10~60 秒，请勿关闭页面…
                </span>
              </div>
              <mdui-linear-progress v-if="relayBusy[v]"></mdui-linear-progress>
            </template>

            <!-- 已部署：状态 + 暴露开关 + 地址 + 卸载 -->
            <template v-else>
              <div class="cc-relay-meta">
                <span>端口 {{ relay[v].port }}</span>
                <span v-if="relay[v].unit">服务 {{ relay[v].unit }}</span>
                <span v-if="relay[v].commit">版本 {{ relay[v].commit }}</span>
                <span v-if="!relay[v].managed" class="cc-relay-legacy">接管自手工部署</span>
              </div>

              <div class="cc-coyote-row">
                <div class="cc-coyote-info">
                  <div class="cc-coyote-state" :class="{ on: relay[v].exposed }">
                    {{ relay[v].exposed ? "已暴露" : "未暴露" }}
                  </div>
                  <div class="cc-coyote-desc">
                    {{ relay[v].exposed
                      ? "端口已放行公网，DG-LAB APP 可经公网地址接入该中转。"
                      : "仅本机（127.0.0.1）可达。开启后放行端口 " + relay[v].port + "，APP 可经公网接入。" }}
                  </div>
                </div>
              <mdui-switch
                :checked="!!relay[v].exposed"
                :disabled="relayBusy[v]"
                @change="relayExposeToggle(v, $event)"
              ></mdui-switch>
              </div>

              <div v-if="relay[v].exposed" class="cc-coyote-warn">
                <mdui-icon name="warning" class="cc-warn-icon"></mdui-icon>
                <span>端口已放行公网！任何获得地址的 DG-LAB APP 都可接入该中转，建议仅在使用期间开启、用完关闭。</span>
              </div>

              <div v-if="relay[v].local_url" class="cc-coyote-link-row">
                <span class="cc-coyote-link-label">本机地址</span>
                <mdui-button
                  variant="tonal"
                  icon="content_copy"
                  @click="copyText(relay[v].local_url, '本机地址 ')"
                >{{ relay[v].local_url }}</mdui-button>
              </div>

              <div v-if="relay[v].exposed" class="cc-coyote-link-row">
                <span class="cc-coyote-link-label">公网地址</span>
                <mdui-button
                  variant="filled"
                  icon="content_copy"
                  @click="copyText(relayUrl(v), '公网地址 ')"
                >{{ relayUrl(v) }}</mdui-button>
              </div>

              <div class="cc-relay-actions">
                <mdui-button
                  class="cc-relay-uninstall"
                  variant="outlined"
                  icon="delete"
                  :disabled="relayBusy[v]"
                  @click="relayUninstall(v)"
                >卸载</mdui-button>
                <span v-if="relayBusy[v]" class="cc-coyote-busy">操作进行中，请稍候…</span>
              </div>
            </template>
          </mdui-card>
        </template>
        <div v-else class="cc-loading">
          <mdui-circular-progress></mdui-circular-progress>
        </div>

        <template v-if="coyote">
          <mdui-card class="cc-panel">
            <h2 class="cc-panel-title">
              <mdui-icon name="power_settings_new" class="cc-panel-icon"></mdui-icon>
              WebUI 总开关
            </h2>
            <div class="cc-coyote-row">
              <div class="cc-coyote-info">
                <div class="cc-coyote-state" :class="{ on: coyote.enabled }">
                  {{ coyote.enabled ? "已启用" : "已关闭" }}
                </div>
                <div class="cc-coyote-desc">
                  {{ coyote.enabled
                      ? "WebUI 正在运行，监听 " + coyote.host + ":" + coyote.port
                          + (coyote.is_public ? "（公网可访问）" : "（仅本机可访问）")
                      : "默认关闭。开启后监听 127.0.0.1，仅本机可访问，不暴露公网。" }}
                </div>
              </div>
              <mdui-switch
                :checked="!!coyote.enabled"
                :disabled="coyoteBusy"
                @change="webuiToggle($event)"
              ></mdui-switch>
            </div>

            <div v-if="coyote.enabled && coyote.local_url" class="cc-coyote-link-row">
              <span class="cc-coyote-link-label">本机访问</span>
              <mdui-button
                variant="tonal"
                icon="open_in_new"
                @click="openUrl(coyote.local_url)"
              >{{ coyote.local_url }}</mdui-button>
            </div>
          </mdui-card>

          <!-- 暴露公网：仅 WebUI 启用后可见 -->
          <mdui-card v-if="coyote.enabled" class="cc-panel">
            <h2 class="cc-panel-title">
              <mdui-icon name="public" class="cc-panel-icon"></mdui-icon>
              暴露公网
            </h2>
            <div class="cc-coyote-row">
              <div class="cc-coyote-info">
                <div class="cc-coyote-state" :class="{ on: coyote.is_public }">
                  {{ coyote.is_public ? "已暴露" : "未暴露" }}
                </div>
                <div class="cc-coyote-desc">
                  {{ coyote.is_public
                      ? "监听 0.0.0.0:" + coyote.port + "，公网可访问。请务必配置反代 + 鉴权！"
                      : "开启后监听地址改为 0.0.0.0:" + coyote.port + "，公网任意地址均可访问（有安全风险）。" }}
                </div>
              </div>
              <mdui-switch
                :checked="!!coyote.is_public"
                :disabled="coyoteBusy"
                @change="exposeToggle($event)"
              ></mdui-switch>
            </div>

            <div v-if="coyote.is_public" class="cc-coyote-warn">
              <mdui-icon name="warning" class="cc-warn-icon"></mdui-icon>
              <span>已暴露公网！请务必在 WebUI 前配置反向代理与访问控制（如 Caddy + BasicAuth、Nginx + IP 白名单），否则任何人都可能访问注册、登录、设备接口。</span>
            </div>

            <div v-if="coyote.is_public" class="cc-coyote-link-row">
              <span class="cc-coyote-link-label">公网访问</span>
              <mdui-button
                variant="filled"
                icon="open_in_new"
                @click="openUrl(coyoteUrl())"
              >{{ coyoteUrl() }}</mdui-button>
            </div>

            <div v-if="coyoteBusy" class="cc-coyote-busy">正在热重载插件，请稍候…</div>
          </mdui-card>
        </template>
        <div v-else class="cc-loading">
          <mdui-circular-progress></mdui-circular-progress>
        </div>
      </section>

      <!-- ===== 联系我们 ===== -->
      <section v-if="current === 'contact'" class="cc-section">
        <div class="cc-head">
          <h1>联系我们</h1>
          <p>开发者信息 · 项目仓库 · 交流群</p>
        </div>

        <mdui-card class="cc-panel">
          <h2 class="cc-panel-title">
            <mdui-icon name="person" class="cc-panel-icon"></mdui-icon>
            开发者
          </h2>
          <div class="mdui-table">
            <table>
              <tbody>
                <tr><td>作者</td><td>Rcst20</td></tr>
                <tr><td>项目</td><td>CurrentCortex（astrbot_plugin_currentcortex）</td></tr>
                <tr><td>仓库</td><td>
                  <mdui-button
                    variant="text"
                    icon="code"
                    @click="openUrl(REPO_URL)"
                  >github.com/backrooms-yrc/astrbot_plugin_currentcortex</mdui-button>
                </td></tr>
              </tbody>
            </table>
          </div>
        </mdui-card>

        <mdui-card class="cc-panel">
          <h2 class="cc-panel-title">
            <mdui-icon name="groups" class="cc-panel-icon"></mdui-icon>
            交流群
          </h2>
          <div class="cc-contact-group">
            <div class="cc-contact-qq">群号：1106353813</div>
            <div class="cc-contact-actions">
              <mdui-button variant="tonal" icon="content_copy" @click="copyGroupNo">
                复制群号
              </mdui-button>
              <mdui-button
                variant="filled"
                icon="group_add"
                @click="openUrl(GROUP_URL)"
              >加入交流群</mdui-button>
            </div>
            <p class="cc-contact-tip">点击「加入交流群」直接加群；如果链接失效，请在 QQ 中搜索群号 1106353813。</p>
          </div>
        </mdui-card>
      </section>
    </main>
  </div>
`;

// ---------------------------------------------------------------- 应用
function groupIcon(icon) {
  // 后端分组 icon 名 -> Material Icons
  const map = {
    settings: "tune",
    image: "image",
    book: "menu_book",
    music: "music_note",
    key: "key",
    bolt: "bolt",
    share: "share",
    switch: "toggle_on",
    scissors: "format_align_left",
  };
  return map[icon] || "tune";
}

createApp({
  template: TEMPLATE,
  setup() {
    return {
      NAV,
      GROUP_URL,
      REPO_URL,
      current,
      status,
      helpData,
      configGroups,
      coyote,
      saving,
      coyoteBusy,
      publicIp,
      relay,
      relayBusy,
      relayMeta,
      relayConfirmOpen,
      relayConfirmText,
      relayConfirmReady,
      openRelayConfirm,
      cancelRelayConfirm,
      relayUrl,
      fmtUptime,
      fmtDate,
      metaOf,
      groupIcon,
      loadStatus,
      loadHelp,
      loadConfig,
      loadCoyote,
      loadRelay,
      saveConfig,
      webuiToggle,
      exposeToggle,
      relayDeploy,
      relayUninstall,
      relayExposeToggle,
      copyText,
      copyGroupNo,
    };
  },
  methods: {
    go(key) {
      location.hash = "#/" + key;
    },
    openUrl(url) {
      if (!url) return;
      // iframe sandbox 可能拦截新窗口，失败则降级为当前 iframe 内导航
      let win = null;
      try {
        win = window.open(url, "_blank");
      } catch (e) {
        win = null;
      }
      if (!win) {
        location.href = url;
      }
    },
    coyoteUrl() {
      if (!this.coyote || !this.coyote.is_public) return "";
      if (this.publicIp) return `http://${this.publicIp}:${this.coyote.port}`;
      return this.coyote.local_url || "";
    },
  },
  watch: {
    current(tab) {
      if (tab === "dashboard") this.loadStatus();
      if (tab === "help") this.loadHelp();
      if (tab === "settings") this.loadConfig();
      if (tab === "coyote") {
        this.loadCoyote();
        this.loadRelay();
      }
    },
  },
  created() {
    this.loadStatus();
  },
}).mount("#app");
