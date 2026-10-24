// CurrentCortex 总Pages —— Vue 3 + mdui 2（Web Components）
// 通过 window.AstrBotPluginPage (bridge) 与后端通信。
// 6 个 tab 用 hash 路由：dashboard / quake / help / settings / coyote / contact

const { createApp, ref, reactive } = Vue;

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
// 地震预警：状态 / 立即检查 / 模拟表单
const quake = ref(null);
const quakeBusy = ref(false);
const quakePolling = ref(false);
const quakeForm = reactive({
  magnitude: 5.0,
  place: "",
  city: "",
  depth: 10,
  latitude: "",
  longitude: "",
  countdown: 15,
  extreme: false,
  extremeConfirm: "",
});
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
  current.value = ["dashboard", "quake", "help", "settings", "coyote", "contact"].includes(h)
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

async function loadQuake() {
  try {
    quake.value = await apiGet("cc/quake/status");
    // 首次打开时用最近事件预填震中，方便快速演练；用户改过的值不覆盖
    const last = quake.value && quake.value.last_event;
    if (!quakeForm.place) {
      quakeForm.place = (last && last.place) || "模拟市模拟区";
    }
    if (quakeForm.latitude === "" && last && last.latitude !== undefined && last.latitude !== null) {
      quakeForm.latitude = last.latitude;
      quakeForm.longitude = last.longitude;
    }
  } catch (e) {
    toast("加载地震预警状态失败: " + (e && e.message ? e.message : e));
  }
}

function quakeSources() {
  const obj = quake.value && quake.value.sources;
  return obj ? Object.entries(obj).map(([key, val]) => ({ key, ...val })) : [];
}

async function pollQuake() {
  quakePolling.value = true;
  try {
    const res = await apiPost("cc/quake/poll", {});
    if (res && res.ok) {
      toast(`检查完成：上游 ${res.candidates || 0} 条，时效内 ${res.fresh || 0} 条，播报 ${res.alerts || 0} 条`);
    } else {
      toast((res && res.reason) || "检查完成，但没有可播报事件");
    }
    await loadQuake();
  } catch (e) {
    toast("立即检查失败: " + (e && e.message ? e.message : e));
  } finally {
    quakePolling.value = false;
  }
}

function setExtreme(checked) {
  quakeForm.extreme = !!checked;
  quakeForm.extremeConfirm = "";
}

async function simulateQuake() {
  const magnitude = Number(quakeForm.magnitude);
  const depth = Number(quakeForm.depth);
  const countdown = Number(quakeForm.countdown || 0);
  const place = String(quakeForm.place || "").trim();
  const city = String(quakeForm.city || "").trim();
  const hasLat = String(quakeForm.latitude).trim() !== "";
  const hasLon = String(quakeForm.longitude).trim() !== "";
  const extreme = !!quakeForm.extreme;
  if (!place && !city) {
    toast("请填写模拟震中名称或震中城市");
    return;
  }
  if (extreme && String(quakeForm.extremeConfirm || "").trim() !== "极限演练") {
    toast("极限演练需输入确认词「极限演练」");
    return;
  }
  if (extreme && !city && !(hasLat && hasLon)) {
    toast("极限演练需填写震中城市或经纬度");
    return;
  }
  if (!(magnitude >= 0 && magnitude <= 10)) {
    toast("震级必须在 0~10 之间");
    return;
  }
  if (!(depth >= 0 && depth <= 700)) {
    toast("震源深度必须在 0~700 km 之间");
    return;
  }
  if (hasLat !== hasLon) {
    toast("纬度和经度必须同时填写或同时留空");
    return;
  }
  if (countdown < 0 || countdown > 60) {
    toast("倒计时必须在 0~60 秒之间（0 = 按距离自动计算）");
    return;
  }
  if (window.mdui && mdui.confirm) {
    try {
      await mdui.confirm({
        headline: extreme ? "发起极限演练？" : "发起模拟地震预警？",
        description: extreme
          ? "极限演练不会发送「仅为模拟」的提示，所有群消息与真实地震预警完全一致。\n" +
            "可能引起群成员恐慌；请确认已明确告知白名单群成员这是演练。"
          : "将向全部白名单群聊发送地震预警演练消息，并先提醒「仅为模拟」。\n" +
            "请勿在真实地震发生时使用，避免与真实预警混淆。",
        confirmText: extreme ? "发起极限演练" : "发起模拟",
        cancelText: "取消",
      });
    } catch (e2) {
      return;
    }
  }
  quakeBusy.value = true;
  try {
    const res = await apiPost("cc/quake/simulate", {
      magnitude,
      place,
      city,
      depth,
      latitude: hasLat ? Number(quakeForm.latitude) : null,
      longitude: hasLon ? Number(quakeForm.longitude) : null,
      countdown,
      extreme,
      extreme_confirm: extreme ? "极限演练" : "",
    });
    toast(res.message || (extreme ? "极限演练已发起" : "模拟预警已发起"));
    if (extreme) {
      quakeForm.extreme = false;
      quakeForm.extremeConfirm = "";
    }
    setTimeout(loadQuake, 1200);
  } catch (e) {
    toast("发送失败: " + (e && e.message ? e.message : e));
  } finally {
    quakeBusy.value = false;
  }
}

async function removeQuakeGroup(group) {
  if (!group || !group.umo) return;
  const label = group.group_id || group.umo;
  if (window.mdui && mdui.confirm) {
    try {
      await mdui.confirm({
        headline: "移除白名单群聊？",
        description: `群 ${label} 将不再接收地震预警，直到群主/管理员重新发送 /地震 开启。`,
        confirmText: "移除",
        cancelText: "取消",
      });
    } catch (e) {
      return;
    }
  }
  try {
    const res = await apiPost("cc/quake/whitelist/remove", { umo: group.umo });
    toast(res.message || "已移除");
    await loadQuake();
  } catch (e) {
    toast("移除失败: " + (e && e.message ? e.message : e));
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
  // —— 校验码 ——
  verify_code: { name: "校验码（必填）", hint: "加入官方 QQ 群 1106353813 获取校验码填在这里——完全免费，捐赠自愿、权益无差别。留空或填错 = 插件全部功能锁定，机器人只会回复入群提示。" },
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
  ncm_api_base: { name: "自建网易云SVIP音源地址", hint: "自建的 api-enhanced 服务地址，默认本机反代域名。这个音源能拿到无损/Hi-Res/超清母带等最高音质，不依赖 LeiZ 密钥。" },
  ncm_cookie_path: { name: "SVIP Cookie 文件路径", hint: "自建音源的登录 cookie 文件路径，服务器每日自动刷新、插件自动跟随，不用重启。留空 = 匿名访问（只有免费音质）。" },
  music_default_source: { name: "默认音源", hint: "auto = 三个音源同时探测、自动选音质最好的；ncm = 只用自建网易云SVIP；netease/kugou = 只用网易云/酷狗（需要 LeiZ 密钥，没填会自动改走自建源）。" },
  music_cooldown: { name: "点歌冷却（秒）", hint: "同一会话连续点歌要间隔的秒数，防止刷屏把服务器拖垮。" },
  music_download_progress_mode: { name: "下载进度播报", hint: "简略（默认）= 下载前后各提示一条；详细 = 每完成 10% 播报一条；关闭 = 全程静默。秒下的小文件任何档位都不播报。" },
  // —— LeiZ ——
  leiz_api_key: { name: "LeiZ API 密钥", hint: "图库、一言、天气、网易云/酷狗等 LeiZ 接口的密钥，非必填。留空 = 这些功能触发时提示填写，点歌自动改走自建网易云SVIP音源，其他功能不受影响。" },
  // —— 媒体解析 ——
  media_auto_parse_enable: { name: "链接自动解析", hint: "群里有人发 小红书/B站/抖音/微博 的链接时，不用发命令、机器人自动解析并回复。" },
  media_auto_parse_dedup_min: { name: "自动解析去重（分钟）", hint: "同一条链接在同一个群里，多少分钟内只自动解析一次，防止反复转发刷屏。0 = 每次都解析。" },
  media_video_send_enable: { name: "视频直接发出来", hint: "解析到视频时直接把视频发到聊天里，不用自己点链接。发不出去时自动改为发链接。" },
  media_video_max_mb: { name: "视频大小上限（MB）", hint: "超过这个大小的视频就不发、只给链接，免得大文件卡住机器人。" },
  media_video_quality: { name: "B站视频清晰度", hint: "下拉选择：480P / 720P / 1080P / 4K / 自动最高。4K 文件很大，长视频可能发不动、自动改为只发链接。需要配置 LeiZ API 密钥。" },
  media_parse_cache_enable: { name: "解析结果缓存", hint: "同一条链接短时间内再发，直接用上次的结果，不去重复请求、不容易触发平台反爬。" },
  media_parse_cache_ttl: { name: "缓存有效期（秒）", hint: "解析结果缓存多久过期。默认 600（10 分钟）。" },
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
  // —— 地震预警 ——
  earthquake_enable: { name: "地震预警总开关", hint: "开启且至少一个群在白名单中时才会轮询预警源。关闭后不请求任何上游；白名单由群主/管理员用 /地震 开启 添加。" },
  earthquake_poll_interval: { name: "轮询间隔（秒）", hint: "多久检查一次预警源。越短越及时，但请求越频繁；默认 30，追求及时性可调 10~15 秒。" },
  earthquake_min_magnitude: { name: "最低播报震级", hint: "低于此震级不播报。默认 4.0；调低会收到更多小震。" },
  earthquake_max_age_sec: { name: "事件最大时效（秒）", hint: "只播报在此时间窗口内发震/发布的事件，避免启动时补发旧闻。默认 300 秒。" },
  earthquake_max_distance_km: { name: "最大震中距（km）", hint: "白名单群接收位置超过此距离不播报；0 = 不过滤。" },
  earthquake_default_lat: { name: "默认接收纬度", hint: "群未单独设置位置时使用；需和默认经度同时填写，(0,0) 视为未设置。" },
  earthquake_default_lon: { name: "默认接收经度", hint: "与默认接收纬度配合使用。" },
  earthquake_default_place: { name: "默认接收地点名", hint: "仅用于播报展示，如「北京」；群内可用 /地震 位置 覆盖。" },
  earthquake_countdown_max_ticks: { name: "倒计时条数上限", hint: "最多逐条发送多少条倒计时。剩余时间更长时先只发基本信息，抵达前最后 N 秒开始倒计时。" },
  earthquake_countdown_max_wait_sec: { name: "倒计时最长等待（秒）", hint: "估算到达时间超过此值时只发基本信息，不启动长倒计时任务，避免远距离事件的任务长时间挂起。" },
  earthquake_countdown_interval: { name: "倒计时发送间隔（秒）", hint: "默认 1.0（每秒一条），最小 1 秒；设为 2 时数字按 2 秒步长递减（如 10s、8s、6s…），降低刷屏频率。" },
  earthquake_s_wave_km_s: { name: "S 波速度（km/s）", hint: "用于按接收位置估算到达时间，默认 3.5；不同地质区域有差异，仅供参考。" },
  earthquake_broadcast_interval: { name: "多群发送间隔（秒）", hint: "向多个白名单群逐条发送时的间隔，降低平台频控风险。默认 0.6。" },
  earthquake_http_timeout: { name: "预警源超时（秒）", hint: "单个上游请求超时；源之间并行，单源失败不影响其他源。" },
  earthquake_sim_cooldown: { name: "模拟预警冷却（秒）", hint: "Pages 模拟预警的冷却时间，防止连续点击向白名单群刷屏。默认 30。" },
  earthquake_extreme_cooldown: { name: "极限演练冷却（秒）", hint: "极限演练不显示模拟提示、消息与真实预警一致，误触风险更高；默认 300 秒，建议不要调低。" },
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
  { key: "quake", label: "地震预警", icon: "warning--outlined" },
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
              <mdui-chip :selected="!!status.feature_flags.verify_ok">校验码已通过</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.llm_tools_enable">LLM 工具</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.dglab_webui_enabled">郊狼 WebUI</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.cross_group_enable">跨群记忆</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.group_switch_enable">按群开关</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.earthquake_enable">地震预警</mdui-chip>
              <mdui-chip :selected="!!status.feature_flags.reply_seg_enable">分段回复</mdui-chip>
            </div>
          </mdui-card>
        </template>
        <div v-else class="cc-loading">
          <mdui-circular-progress></mdui-circular-progress>
        </div>
      </section>

      <!-- ===== 地震预警 ===== -->
      <section v-if="current === 'quake'" class="cc-section">
        <div class="cc-head">
          <h1>地震预警</h1>
          <p>多预警源聚合 · 群聊白名单 · 到达倒计时 · 模拟演练</p>
        </div>

        <template v-if="quake">
          <div class="cc-cards">
            <mdui-card class="cc-card">
              <mdui-icon slot="icon" name="groups" class="cc-card-icon"></mdui-icon>
              <div class="cc-card-value">{{ quake.active_groups || 0 }}</div>
              <div class="cc-card-label">白名单群聊</div>
            </mdui-card>
            <mdui-card class="cc-card">
              <mdui-icon slot="icon" name="sensors" class="cc-card-icon"></mdui-icon>
              <div class="cc-card-value">{{ quake.running ? "运行中" : (quake.enabled ? "待机" : "已关闭") }}</div>
              <div class="cc-card-label">轮询状态</div>
            </mdui-card>
            <mdui-card class="cc-card">
              <mdui-icon slot="icon" name="cloud_sync" class="cc-card-icon"></mdui-icon>
              <div class="cc-card-value">{{ quakeSources().filter(s => s.ok).length }}/{{ quakeSources().length }}</div>
              <div class="cc-card-label">预警源正常</div>
            </mdui-card>
            <mdui-card class="cc-card">
              <mdui-icon slot="icon" name="campaign" class="cc-card-icon"></mdui-icon>
              <div class="cc-card-value">{{ (quake.stats && quake.stats.alerts) || 0 }}</div>
              <div class="cc-card-label">累计预警</div>
            </mdui-card>
          </div>

          <mdui-card class="cc-panel">
            <h2 class="cc-panel-title">
              <mdui-icon name="warning" class="cc-panel-icon"></mdui-icon>
              运行状态
            </h2>
            <div class="cc-quake-meta">
              <span>轮询间隔：{{ quake.poll_interval }} 秒</span>
              <span>最低震级：M{{ quake.min_magnitude }}</span>
              <span>倒计时上限：最后 {{ quake.countdown_max_ticks }} 条</span>
              <span>白名单：{{ quake.groups.length }} 个（启用 {{ quake.active_groups }}）</span>
            </div>
            <div class="cc-quake-actions">
              <mdui-button variant="outlined" icon="refresh" :disabled="quakePolling" @click="pollQuake">
                {{ quakePolling ? "检查中…" : "立即检查预警源" }}
              </mdui-button>
              <span v-if="quake.last_skip" class="cc-coyote-busy">{{ quake.last_skip }}</span>
              <span v-else-if="quake.last_poll_error" class="cc-coyote-busy">{{ quake.last_poll_error }}</span>
            </div>
            <div v-if="quake.last_event" class="cc-quake-last">
              最近预警：M{{ quake.last_event.magnitude }} {{ quake.last_event.place }}
              （{{ quake.last_event.origin_time }}，{{ quake.last_event.source_label }}）
            </div>
            <div v-if="quake.last_simulation" class="cc-quake-last">
              最近{{ quake.last_simulation.extreme ? "极限演练" : "模拟" }}：M{{ quake.last_simulation.magnitude }} {{ quake.last_simulation.place }}
              （{{ quake.last_simulation.origin_time }}，{{ quake.last_simulation.groups }} 群）
            </div>
          </mdui-card>

          <mdui-card class="cc-panel">
            <h2 class="cc-panel-title">
              <mdui-icon name="campaign" class="cc-panel-icon"></mdui-icon>
              模拟预警
            </h2>
            <div class="cc-quake-warn">
              ⚠️ 模拟预警会向全部白名单群聊发送消息，并先提醒「仅为模拟，不是真实地震」。
              请勿在真实地震发生时使用，避免混淆。
            </div>
            <div class="cc-quake-mode">
              <mdui-switch
                :checked="!!quakeForm.extreme"
                @change="setExtreme($event.target.checked)"
              ></mdui-switch>
              <div>
                <div class="cc-quake-mode-title">极限演练模式</div>
                <div class="cc-quake-mode-hint">
                  开启后不发送「仅为模拟」提示，所有广播（含来源、倒计时、到达指引）与真实地震预警完全相同。
                  极限演练按真实 S 波距离估算倒计时，不使用上方秒数；可能引起群成员恐慌，仅限已明确告知群成员的演练。
                </div>
              </div>
            </div>
            <div v-if="quakeForm.extreme" class="cc-quake-warn cc-quake-extreme-warn">
              ⚠️ 极限演练消息无法与真实预警区分。请输入确认词「极限演练」后才能发送。
              <mdui-text-field
                label="输入「极限演练」确认"
                :value="quakeForm.extremeConfirm"
                @input="quakeForm.extremeConfirm = $event.target.value"
              ></mdui-text-field>
            </div>
            <div class="cc-quake-form">
              <mdui-text-field label="震级" type="number" step="0.1" min="0" max="10"
                :value="quakeForm.magnitude"
                @input="quakeForm.magnitude = $event.target.value"></mdui-text-field>
              <mdui-text-field label="震中名称" :value="quakeForm.place"
                @input="quakeForm.place = $event.target.value"></mdui-text-field>
              <mdui-text-field label="震中城市（可选，填了可代替经纬度）" :value="quakeForm.city"
                @input="quakeForm.city = $event.target.value"></mdui-text-field>
              <mdui-text-field label="震源深度（km）" type="number" step="1" min="0" max="700"
                :value="quakeForm.depth"
                @input="quakeForm.depth = $event.target.value"></mdui-text-field>
              <mdui-text-field label="倒计时秒数（0=按距离）" type="number" step="1" min="0" max="60"
                :disabled="quakeForm.extreme"
                :value="quakeForm.countdown"
                @input="quakeForm.countdown = $event.target.value"></mdui-text-field>
              <mdui-text-field label="震中纬度（可留空）" type="number" step="0.0001"
                :value="quakeForm.latitude"
                @input="quakeForm.latitude = $event.target.value"></mdui-text-field>
              <mdui-text-field label="震中经度（可留空）" type="number" step="0.0001"
                :value="quakeForm.longitude"
                @input="quakeForm.longitude = $event.target.value"></mdui-text-field>
            </div>
            <div class="cc-quake-actions">
              <mdui-button variant="filled" icon="campaign"
                :disabled="quakeBusy || !quake.active_groups || !quake.enabled || (quakeForm.extreme && quakeForm.extremeConfirm !== '极限演练')"
                @click="simulateQuake">{{ quakeBusy ? "发送中…" : (quakeForm.extreme ? "发起极限演练" : "发起模拟预警") }}</mdui-button>
              <span v-if="!quake.enabled" class="cc-coyote-busy">
                地震预警总开关已关闭，请先在「设置」中开启 earthquake_enable。
              </span>
              <span v-else-if="!quake.active_groups" class="cc-coyote-busy">
                暂无启用的白名单群聊。请群主/管理员在目标群发送 /地震 开启 &lt;纬度&gt; &lt;经度&gt; [地点]
              </span>
              <span v-else class="cc-coyote-busy">
                将向 {{ quake.active_groups }} 个群发送；{{ quakeForm.extreme ? "极限演练与真实预警完全一致" : "倒计时按各群最近接收城市估算（填 0 时），群内关闭倒计时则只发基本信息与到达指引" }}。
              </span>
            </div>
          </mdui-card>

          <mdui-card class="cc-panel">
            <h2 class="cc-panel-title">
              <mdui-icon name="group" class="cc-panel-icon"></mdui-icon>
              群聊白名单
            </h2>
            <div v-if="quake.groups.length" class="mdui-table cc-quake-table">
              <table>
                <thead>
                  <tr>
                    <th>群号</th><th>平台</th><th>接收城市</th><th>倒计时</th><th>状态</th><th>启用人 / 时间</th><th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="g in quake.groups" :key="g.umo">
                    <td>{{ g.group_id || "-" }}</td>
                    <td>{{ g.platform_id || "-" }}</td>
                    <td>
                      <template v-if="g.locations && g.locations.length">
                        <div v-for="(loc, li) in g.locations" :key="li">
                          {{ loc.place || "未命名" }}
                          <small>（{{ Number(loc.latitude).toFixed(4) }}, {{ Number(loc.longitude).toFixed(4) }}）</small>
                        </div>
                      </template>
                      <span v-else>{{ g.place || "未设置" }}</span>
                    </td>
                    <td>{{ g.countdown_enabled === false ? "⛔ 关" : "✅ 开" }}</td>
                    <td>{{ g.enabled ? "✅ 启用" : "⛔ 停用" }}</td>
                    <td>{{ g.enabled_by || "-" }}<br><small>{{ g.enabled_at || "-" }}</small></td>
                    <td>
                      <mdui-button variant="text" icon="delete" @click="removeQuakeGroup(g)">移除</mdui-button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="cc-quake-empty">
              尚无群聊启用。请让群主/管理员在目标群发送：<br>
              <code>/地震 开启 北京</code><br>
              一个群可用 <code>/地震 添加城市 上海</code> 添加多个接收城市。
            </div>
          </mdui-card>

          <mdui-card class="cc-panel">
            <h2 class="cc-panel-title">
              <mdui-icon name="dns" class="cc-panel-icon"></mdui-icon>
              预警源状态
            </h2>
            <div v-if="quakeSources().length" class="mdui-table cc-quake-table">
              <table>
                <thead><tr><th>预警源</th><th>状态</th><th>返回条数</th><th>最近错误</th></tr></thead>
                <tbody>
                  <tr v-for="s in quakeSources()" :key="s.key">
                    <td>{{ s.label }}</td>
                    <td>{{ s.last_ts ? (s.ok ? "✅ 正常" : "⚠️ 异常") : "⏳ 尚未检查" }}</td>
                    <td>{{ s.count || 0 }}</td>
                    <td class="cc-quake-error">{{ s.error || "-" }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="cc-quake-empty">预警服务未启动（全局开关关闭或服务未初始化）。</div>
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
    verified: "verified",
    settings: "tune",
    image: "image",
    book: "menu_book",
    music: "music_note",
    key: "key",
    bolt: "bolt",
    share: "share",
    switch: "toggle_on",
    scissors: "format_align_left",
    warning: "warning",
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
      quake,
      quakeForm,
      quakeBusy,
      quakePolling,
      quakeSources,
      loadQuake,
      pollQuake,
      simulateQuake,
      removeQuakeGroup,
      setExtreme,
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
      if (tab === "quake") this.loadQuake();
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
    if (current.value === "quake") this.loadQuake();
  },
}).mount("#app");
