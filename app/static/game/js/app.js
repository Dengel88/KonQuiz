// Клиент KonQuiz. Сервер решает всё; клиент только рисует последний снимок состояния и шлёт намерения.

import { api, GameSocket, tg } from "./net.js";
import { MapView, colorHex, thumbnail } from "./map.js";

const $ = (id) => document.getElementById(id);
const HINTS = {
  "50_50": { title: "50/50", cost: 15, icon: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 3v18" stroke="currentColor" stroke-width="2"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/></svg>' },
  freeze: { title: "+10 с", cost: 20, icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v20M3.3 7l17.4 10M3.3 17 20.7 7"/><path d="m9 4 3 2 3-2M9 20l3-2 3 2"/></svg>' },
  radar: { title: "Зал", cost: 30, icon: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="12" width="4" height="9" rx="1"/><rect x="10" y="5" width="4" height="16" rx="1"/><rect x="17" y="9" width="4" height="12" rx="1"/></svg>' },
};
const ICON = (d) => `<svg class="ico-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const RATES = [
  [1, ICON('<path d="M7 11v9H4v-9zM7 11l4-7a2 2 0 0 1 3 2l-1 4h5a2 2 0 0 1 2 2.3l-1.2 6A2 2 0 0 1 16.8 20H7"/>'), "Нравится"],
  [0, ICON('<path d="M5 12h14"/>'), "Средне"],
  [-1, ICON('<path d="M7 13V4H4v9zM7 13l4 7a2 2 0 0 0 3-2l-1-4h5a2 2 0 0 0 2-2.3l-1.2-6A2 2 0 0 0 16.8 4H7"/>'), "Не нравится"],
];
const BOT_MARK = `<svg class="bot-mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-label="бот"><circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/></svg>`;

const ui = {
  me: null,          // мой tg_id
  profile: null,     // /api/me
  S: null,           // последний снимок MatchState
  skew: 0,           // server_time - локальное время
  map: null,         // MapView текущей карты
  mapData: {},       // кэш /api/map по id
  src: null,         // выбранный источник атаки
  typed: "",         // набранное число
  chosen: null,      // выбранный вариант (до ответа сервера)
  removed: [],       // 50/50
  radar: null,       // распределение «зала»
  shownResult: null, // последний показанный last_result (для хаптики)
  phaseForLocal: -1, // локальные штуки сбрасываются при смене фазы
  rated: new Map(),  // question_id -> оценка, чтобы не спрашивать дважды
  hud: null,         // { key, cards: Map<pid, {root, odo, count, mark}> }
  topic: load("kq-topic", "general"),
  mapChoice: load("kq-map", null),
  topics: [],
  maps: [],
};

function load(key, dflt) {
  try { return localStorage.getItem(key) || dflt; } catch { return dflt; }
}
function save(key, value) {
  try { localStorage.setItem(key, value); } catch {}
}

const socket = new GameSocket(onMessage, onSocketStatus);

// ---------------------------------------------------------------- утилиты

function show(screen) {
  for (const s of document.querySelectorAll(".screen")) s.hidden = s.id !== `scr-${screen}`;
  document.body.dataset.screen = screen;
  syncBgVideo();
}

// Фон крутим только там, где он виден — в бою не тратим батарею. Если WebView
// не дал автозапуск без жеста, пробуем снова на первом касании.
function syncBgVideo() {
  const bg = $("bg-video");
  if (!bg) return;
  const screen = document.body.dataset.screen;
  if (screen === "lobby" || screen === "search") bg.play().catch(() => {});
  else bg.pause();
}
addEventListener("pointerdown", syncBgVideo, { once: true, capture: true });
document.addEventListener("visibilitychange", () => !document.hidden && syncBgVideo());

let toastTimer;
function toast(text, ms = 2600) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), ms);
}

const haptic = {
  tap: () => tg?.HapticFeedback?.impactOccurred("light"),
  hit: () => tg?.HapticFeedback?.impactOccurred("heavy"),
  ok: () => tg?.HapticFeedback?.notificationOccurred("success"),
  bad: () => tg?.HapticFeedback?.notificationOccurred("error"),
  warn: () => tg?.HapticFeedback?.notificationOccurred("warning"),
};

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (n) => (typeof n === "number" ? n.toLocaleString("ru-RU") : String(n));
const colorName = (pid) => ui.S?.players[pid]?.color || "red";
const colorOf = (pid) => (ui.S?.players[pid] ? colorHex(colorName(pid)) : "#8a7050");
const nameOf = (pid) => {
  const p = ui.S?.players[pid];
  if (!p) return "—";
  return +pid === ui.me ? "Вы" : p.username || `Игрок ${pid}`;
};
const shield = (pid, text = "") => `<span class="shield" style="--c:${colorOf(pid)}">${esc(text)}</span>`;
// держава игрока — по региону его столицы («Московское княжество»); до выбора столицы пусто
const realmOf = (pid, s = ui.S) => {
  const tid = s?.capitals[pid] ?? ui.capHist?.[pid];  // разрушенный замок — держава всё равно остаётся в итогах
  return tid != null ? ui.map?.byId.get(tid)?.realm || "" : "";
};
const ownedBy = (pid) => Object.entries(ui.S.territories).filter(([, o]) => o === +pid).map(([t]) => +t);

// Счёт ведёт сервер: замок 1000, земля 200, захват +400, оборона +100, руины замка — ±1000
const liveScore = (pid) => Math.max(0, ui.S.players[pid]?.score ?? 0);

function send(obj) {
  haptic.tap();
  socket.send({ ...obj, phase: ui.S?.phase });
}

async function mapData(id) {
  if (!ui.mapData[id]) ui.mapData[id] = await api(`/api/map?map_id=${encodeURIComponent(id)}`);
  return ui.mapData[id];
}

// ---------------------------------------------------------------- лобби

async function loadProfile() {
  try {
    ui.profile = await api("/api/me");
  } catch (e) {
    $("lobby-name").textContent = "Не удалось войти";
    toast(String(e.message).includes("401") ? "Откройте игру из Telegram" : "Сервер недоступен");
    return;
  }
  const p = ui.profile;
  ui.me = p.id;
  $("lobby-name").textContent = p.username || `Воин ${p.id}`;
  $("lobby-gold").textContent = fmt(p.gold);
  $("lobby-xp").textContent = fmt(p.xp);
  $("lobby-hints").innerHTML = Object.entries(HINTS).map(([k, h]) =>
    `<span class="hint-chip"><span class="hint-ico">${h.icon}</span>${h.title}<b>× ${p.hints[k]}</b></span>`
  ).join("");
  renderTopics();
  renderMaps();
  if (p.active_match_id) {  // вернулись в незаконченный матч
    socket.matchId = p.active_match_id;
    startMatch();
  }
}

async function renderTopics() {
  if (!ui.topics.length) {
    try { ui.topics = await api("/api/topics"); } catch { return; }
  }
  $("lobby-topics").innerHTML = ui.topics.map((t) =>
    `<button class="topic" role="radio" aria-checked="${t.id === ui.topic}" data-topic="${t.id}">${esc(t.title)}</button>`
  ).join("");
}

async function renderMaps() {
  if (!ui.maps.length) {
    try { ui.maps = await api("/api/maps"); } catch { return; }
  }
  if (!ui.maps.some((m) => m.id === ui.mapChoice)) ui.mapChoice = ui.maps[0]?.id;
  const box = $("lobby-maps");
  if (box.children.length !== ui.maps.length) {
    box.replaceChildren(...ui.maps.map((m) => {
      const b = document.createElement("button");
      b.className = "map-card";
      b.setAttribute("role", "radio");
      b.dataset.map = m.id;
      b.innerHTML = `<span class="map-thumb-box"></span><span class="map-title">${esc(m.title)}</span>`;
      mapData(m.id).then((d) => b.querySelector(".map-thumb-box").appendChild(thumbnail(d))).catch(() => {});
      return b;
    }));
  }
  for (const b of box.children) b.setAttribute("aria-checked", String(b.dataset.map === ui.mapChoice));
}

async function showFact(card) {
  const text = card.querySelector("[data-fact-text]");
  try {
    const r = await api(`/api/fact?topic=${encodeURIComponent(ui.topic)}`);
    text.textContent = r.fact || "Фактов по этой теме пока нет.";
  } catch {
    text.textContent = "Не удалось загрузить факт.";
  }
}

function startMatch() {
  ui.S = null;
  ui.hud = null;
  socket.topic = ui.topic;
  socket.mapId = ui.mapChoice;
  show("search");
  renderSearch();
  showFact($("search-fact"));
  socket.connect();
}

// ---------------------------------------------------------------- сообщения сервера

function onSocketStatus(status, reason) {
  if (status === "reconnecting") toast("Связь потеряна, переподключаемся…", 1800);
  if (status === "open" && ui.S) toast("Снова в строю", 1200);
  if (status === "auth") { toast(`Ошибка входа: ${reason}`); show("lobby"); }
}

function onMessage(m) {
  switch (m.type) {
    case "welcome":
      ui.me = m.you;
      setState(m.state);
      break;
    case "state":
      setState(m.state);
      break;
    case "error":
      haptic.warn();
      toast(m.message);
      ui.chosen = null;
      render();
      break;
    case "hint":
      if (m.remove) ui.removed = m.remove;
      if (m.distribution) ui.radar = m.distribution;
      if (ui.profile) {
        if (m.paid_with === "gold") ui.profile.gold -= HINTS[m.hint].cost;
        else ui.profile.hints[m.hint] -= 1;
      }
      toast(m.paid_with === "gold" ? `Подсказка за ${HINTS[m.hint].cost} золота` : "Подсказка из запаса");
      render();
      break;
    case "end":
      showEnd(m.final);
      break;
  }
}

async function ensureMap(id) {
  if (ui.map?.id === id) return;
  const data = await mapData(id);
  if (ui.map?.id !== id) ui.map = new MapView($("map"), data, onMapTap);
}

function setState(s) {
  const prev = ui.S;
  ui.S = s;
  ui.skew = s.server_time - Date.now() / 1000;
  if (ui.capMatch !== s.match_id) { ui.capMatch = s.match_id; ui.capHist = {}; }
  Object.assign(ui.capHist, s.capitals);
  if (s.phase !== ui.phaseForLocal) {
    ui.phaseForLocal = s.phase;
    ui.src = null;
    ui.typed = "";
    ui.chosen = null;
    ui.removed = [];
    ui.radar = null;
  }
  if (s.state_name === "MATCHMAKING") {
    show("search");
    renderSearch();
    return;
  }
  if (s.state_name === "END_GAME") return;  // итоги придут событием end
  show("match");
  // хаптика на итог вопроса — один раз на новый результат
  if (s.state_name === "REVEAL" && s.last_result && JSON.stringify(s.last_result) !== ui.shownResult) {
    ui.shownResult = JSON.stringify(s.last_result);
    const r = s.last_result;
    const iWon = r.winner === ui.me || (r.battle && ((r.outcome === "captured" && r.battle.attacker === ui.me) || (r.outcome === "defended" && r.battle.defender === ui.me)));
    const iLost = r.battle && ((r.outcome === "captured" && r.battle.defender === ui.me) || (r.outcome === "defended" && r.battle.attacker === ui.me));
    if (iWon) haptic.ok(); else if (iLost) haptic.bad();
  }
  if (prev && JSON.stringify(prev.territories) !== JSON.stringify(s.territories)) haptic.hit();
  // новая столица — объявляем основание державы
  if (prev && ui.map?.id === s.map_id) {
    for (const pid of Object.keys(s.capitals)) {
      if (prev.capitals[pid] == null && realmOf(pid, s)) {
        if (!playRealm(pid, s)) {
          toast(`${nameOf(pid)} — ${+pid === ui.me ? "ваша держава" : "основана держава"}: ${realmOf(pid, s)}`, 3200);
        }
      }
    }
  }
  // сервер пошёл дальше (вопрос) — ролик не должен его закрывать
  if (s.state_name !== "REALM_REVEAL") closeRealm();
  if (ui.map?.id === s.map_id) render();
  else ensureMap(s.map_id).then(render).catch(() => toast("Не удалось загрузить карту"));
}

// ---------------------------------------------------------------- ролик державы

// Ролики сняты только для карты России: realm_NN.mp4, NN = territory_id столицы.
const REALM_VIDEO_MAPS = new Set(["russia"]);

function playRealm(pid, s) {
  const tid = s.capitals[pid];
  if (!REALM_VIDEO_MAPS.has(s.map_id) || tid == null) return false;
  const nn = String(tid).padStart(2, "0");
  const v = $("realm-video");
  v.poster = `media/realms/realm_${nn}.jpg`;
  v.src = `media/realms/realm_${nn}.mp4`;
  $("realm-kicker").textContent = +pid === ui.me ? "Ваша держава" : "Основана держава";
  $("realm-name").textContent = realmOf(pid, s);
  $("realm-who").textContent = nameOf(pid);
  $("realm-reveal").hidden = false;
  // со звуком, если WebView разрешит; иначе хотя бы картинка
  v.muted = false;
  v.play().catch(() => { v.muted = true; v.play().catch(() => {}); });
  return true;
}

function closeRealm() {
  const box = $("realm-reveal");
  if (box.hidden) return;
  box.hidden = true;
  const v = $("realm-video");
  v.pause();
  v.removeAttribute("src");
  v.load();
}

$("realm-video").addEventListener("ended", closeRealm);
$("realm-skip").onclick = closeRealm;

// ---------------------------------------------------------------- поиск

function renderSearch() {
  const players = ui.S ? Object.values(ui.S.players) : [];
  const slots = [0, 1, 2].map((i) => {
    const p = players[i];
    return p
      ? `<div class="slot">${shield(p.tg_id)}${esc(p.tg_id === ui.me ? "Вы" : p.username)}</div>`
      : `<div class="slot empty"><span class="shield"></span>…</div>`;
  });
  $("search-slots").innerHTML = slots.join("");
  $("search-text").textContent = players.length < 3 ? "Ищем соперников…" : "Армии собраны!";
}

// ---------------------------------------------------------------- матч

function phaseTitle(s) {
  switch (s.state_name) {
    case "EXPANSION": return "Раздел земель";
    case "EXPANSION_PICK": {
      const more = (s.pick_queue || []).filter((p) => p === s.picker_tg_id).length;
      const tail = more ? " (ещё одну после)" : "";
      return s.picker_tg_id === ui.me ? `Выберите землю${tail}` : `${nameOf(s.picker_tg_id)} занимает землю${tail}`;
    }
    case "BATTLE_WAIT": return s.current_turn_tg_id === ui.me ? "Ваш ход: нападайте!" : `${nameOf(s.current_turn_tg_id)} выбирает цель`;
    case "BATTLE_QUESTION": {
      const b = s.battle;
      const castle = b && s.capitals[b.defender] === b.target;
      return castle ? `Штурм замка: башен ${s.towers[b.defender]}` : "Битва!";
    }
    case "BATTLE_TIEBREAKER": return "Решающий вопрос";
    case "FINAL_TIEBREAKER": return "Очков поровну — финальный вопрос";
    case "REVEAL": return "Итоги";
    case "REALM_REVEAL": return "Основана держава";
    default: return s.state_name;
  }
}

function render() {
  const s = ui.S;
  if (!s || $("scr-match").hidden || !ui.map) return;
  $("m-phase").textContent = phaseTitle(s);
  renderTracker(s);
  renderHud(s);
  renderBanner(s);
  const options = mapOptions(s);
  ui.map.render(s, { options, src: ui.src, colorName, nameOf });
  renderSheet(s);
  fitMap(s, options);
}

// Камера: мой выбор — наезд на допустимые земли; бой — на двух участников; иначе вся карта
function fitMap(s, options) {
  let ids = null;
  if (options.size) ids = [...options];
  else if (s.battle) ids = [s.battle.source, s.battle.target];
  else if (s.state_name === "REVEAL" && s.last_result?.battle) ids = [s.last_result.battle.source, s.last_result.battle.target];
  const svg = $("map"), sheet = $("m-sheet");
  const top = svg.getBoundingClientRect().top - $("scr-match").getBoundingClientRect().top;
  const visH = sheet.hidden ? undefined : sheet.offsetTop - top - 6;
  ui.map.fit(ids, visH, sheet.hidden ? 0 : 40);
}

// Трекер раундов: этап + 5 ячеек, в каждой — полоски очерёдности ходов цветами игроков
function renderTracker(s) {
  const capitalsLeft = Object.keys(s.capitals).length < Object.keys(s.players).length;
  const stage = s.round ? (s.round >= s.rounds_total ? "Финал" : "Битва") : capitalsLeft ? "Замки" : "Завоевание";
  const order = s.turn_order.length ? s.turn_order : Object.keys(s.players).map(Number);
  const cells = Array.from({ length: s.rounds_total || 4 }, (_, i) => {
    const r = i + 1;
    const state = !s.round || r > s.round ? "future" : r < s.round ? "past" : "now";
    const bars = order.map((pid, k) => {
      const done = state === "past" || (state === "now" && k < s.turn_index);
      const cur = state === "now" && k === s.turn_index;
      return `<i class="${done ? "done" : ""} ${cur ? "cur" : ""}" style="--c:${colorOf(pid)}"></i>`;
    }).join("");
    return `<span class="cell ${state}">${bars}</span>`;
  }).join("");
  $("m-tracker").innerHTML = `<span class="stage-name">${stage}</span><span class="cells">${cells}</span>`;
}

// HUD-карточки: строим один раз на матч, дальше только обновляем — иначе одометр не прокрутится
function renderHud(s) {
  const pids = Object.keys(s.players).map(Number).sort((a, b) => (a === ui.me ? -1 : b === ui.me ? 1 : 0));
  const key = pids.join(",");
  if (ui.hud?.key !== key) {
    const box = $("m-hud");
    box.replaceChildren();
    const cards = new Map();
    for (const pid of pids) {
      const p = s.players[pid];
      const root = document.createElement("div");
      root.className = `pcard ${pid === ui.me ? "me" : ""}`;
      root.style.setProperty("--c", colorOf(pid));
      root.innerHTML = `<div class="pcard-tab"><span class="pcard-name">${esc(pid === ui.me ? "Вы" : p.username)}</span><span class="pcard-mark"></span></div>
        <div class="pcard-realm"></div>
        <div class="pcard-body"><span class="pcard-count"></span><span class="odo"></span></div>`;
      box.appendChild(root);
      cards.set(pid, {
        root, odo: root.querySelector(".odo"), count: root.querySelector(".pcard-count"),
        mark: root.querySelector(".pcard-mark"), realm: root.querySelector(".pcard-realm"),
      });
    }
    ui.hud = { key, cards };
  }
  const active = s.current_turn_tg_id ?? s.picker_tg_id;
  for (const [pid, c] of ui.hud.cards) {
    const p = s.players[pid];
    c.root.classList.toggle("turn", pid === active);
    c.root.classList.toggle("dead", p.eliminated);
    c.realm.textContent = realmOf(pid) || "без столицы";
    c.realm.classList.toggle("none", !realmOf(pid));
    c.mark.innerHTML = s.answers[pid] ? "✓" : !p.connected ? "⌁" : p.is_bot ? BOT_MARK : "";
    c.count.innerHTML = `${ownedBy(pid).length}<small>зем.</small>${s.capitals[pid] != null ? `<b class="cap-dot" title="Замок: башен ${s.towers?.[pid] ?? 0}"></b><small class="towers">${"♜".repeat(s.towers?.[pid] ?? 0)}</small>` : ""}`;
    odometer(c.odo, liveScore(pid));
  }
}

function odometer(node, value) {
  const digits = String(value).padStart(4, " ");  // без «0600»: пустые ячейки скрыты
  node.setAttribute("aria-label", `${value} очков`);
  if (node.children.length !== digits.length) {
    node.innerHTML = [...digits].map(() =>
      `<span class="odo-col" aria-hidden="true"><span class="odo-strip">${[..."0123456789"].map((d) => `<i>${d}</i>`).join("")}</span></span>`
    ).join("");
  }
  [...digits].forEach((d, i) => {
    const col = node.children[i];
    col.classList.toggle("blank", d === " ");
    if (d !== " ") col.firstChild.style.transform = `translateY(${-d * 10}%)`;
  });
}

function renderBanner(s) {
  const b = $("m-banner");
  let text = "";
  if (s.state_name === "BATTLE_WAIT" && s.current_turn_tg_id === ui.me) {
    const r = s.round, last = s.rounds_total;
    text = r >= last ? "Последний раунд: бейте любую землю!" : r <= 1 ? "Атакуйте соседнюю землю (замки — со 2-го раунда)" : "Атакуйте соседнюю землю или замок";
  } else if (s.state_name === "EXPANSION_PICK" && s.picker_tg_id === ui.me) {
    text = "Нажмите на подсвеченную землю";
  }
  b.hidden = !text;
  b.textContent = text;
}

function mapOptions(s) {
  if (s.picker_tg_id === ui.me) return new Set(s.pick_options);
  if (s.state_name === "BATTLE_WAIT" && s.current_turn_tg_id === ui.me) {
    return new Set(s.attack_targets || []);  // цели считает сервер по правилам раунда
  }
  return new Set();
}

function onMapTap(hitId, snap) {
  const s = ui.S;
  if (!s) return;
  if (s.picker_tg_id === ui.me) {
    const tid = snap(new Set(s.pick_options));
    if (tid != null) send({ action: "pick", territory: tid });
    return;
  }
  if (s.state_name !== "BATTLE_WAIT" || s.current_turn_tg_id !== ui.me) return;
  // как в оригинале — один тап по цели; откуда ударить, решает сервер
  const tgt = snap(mapOptions(s));
  if (tgt != null) send({ action: "attack", target_territory: tgt });
}

// ---------------------------------------------------------------- листок вопроса / итогов

function renderDuel(s, battle) {
  const duel = $("q-duel");
  duel.hidden = !battle;
  if (!battle) return;
  const isCap = s.capitals[battle.defender] === battle.target;
  const towers = isCap ? s.towers?.[battle.defender] ?? 0 : 0;
  duel.innerHTML = `<span class="duel-side atk" style="--c:${colorOf(battle.attacker)}">${esc(nameOf(battle.attacker))}</span>
    <span class="duel-chev" aria-hidden="true"></span>
    <span class="duel-side def" style="--c:${colorOf(battle.defender)}">${esc(nameOf(battle.defender))}${isCap ? `<b class="duel-cap" title="Замок"></b><span class="duel-towers" title="Башен осталось">${"♜".repeat(towers)}</span>` : ""}</span>`;
}

function renderSheet(s) {
  const sheet = $("m-sheet");
  const cq = s.current_question;
  const r = s.last_result;
  const isReveal = s.state_name === "REVEAL" && r && r.text;
  sheet.hidden = !cq && !isReveal;
  $("m-hud").classList.toggle("under-sheet", !sheet.hidden);
  if (sheet.hidden) return;
  if (isReveal) return renderReveal(r);
  $("q-rate").hidden = true;

  renderDuel(s, s.battle);
  const mine = s.question_participants.includes(ui.me);
  const answered = !!s.answers[ui.me] || ui.chosen !== null;
  $("q-tag").textContent =
    s.state_name === "BATTLE_TIEBREAKER" ? "Оба правы — кто ближе?" :
    s.battle ? (cq.q_type === "EXACT" ? "Кто ближе — тот и победил" : "") :
    cq.q_type === "EXACT" ? "Кто ближе — тот и победил" : "Выберите ответ";
  $("q-text").textContent = cq.text;

  const isChoice = cq.q_type === "CHOICE";
  $("q-options").hidden = !isChoice;
  $("q-exact").hidden = isChoice || !mine;
  if (isChoice) {
    $("q-options").innerHTML = cq.options.map((o, i) => {
      const gone = ui.removed.includes(i);
      const pct = ui.radar ? `<span class="opt-pct">${ui.radar[i]}%</span>` : "";
      return `<button class="opt-btn ${ui.chosen === i ? "chosen" : ""} ${gone ? "gone" : ""}" data-i="${i}"
        ${!mine || answered || gone ? "disabled" : ""}><span>${esc(o)}</span>${pct}</button>`;
    }).join("");
  } else if (mine) {
    $("q-display").textContent = ui.typed ? fmt(+ui.typed) : "0";
    renderKeypad(answered);
  }

  const waitingFor = s.question_participants.filter((p) => !s.answers[p]).length;
  $("q-status").textContent = !mine ? (s.battle ? "Вы наблюдаете за битвой" : "В этом вопросе вы не участвуете") :
    answered ? (waitingFor ? "Ответ принят. Ждём остальных…" : "Все ответили") : "";

  const me = s.players[ui.me];
  $("q-hints").hidden = !mine || answered;
  if (mine && !answered) {
    $("q-hints").innerHTML = Object.entries(HINTS).map(([k, h]) => {
      const onlyChoice = k !== "freeze" && !isChoice;
      const used = me?.used_hints.includes(k);
      const stock = ui.profile?.hints[k] ?? 0;
      const label = used ? "использована" : stock > 0 ? `запас ${stock}` : `${h.cost} зол.`;
      return `<button class="hint-btn" data-hint="${k}" title="${h.title}" ${used || onlyChoice ? "disabled" : ""}>
        ${h.icon}<small>${onlyChoice ? "—" : label}</small></button>`;
    }).join("");
  }
}

function renderKeypad(disabled) {
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "✓"];
  $("q-keypad").innerHTML = keys.map((k) =>
    `<button class="key ${k === "✓" ? "ok" : ""}" data-k="${k}" ${disabled || (k === "✓" && !ui.typed) ? "disabled" : ""}>${k}</button>`
  ).join("");
}

function renderReveal(r) {
  $("q-exact").hidden = true;
  $("q-hints").hidden = true;
  renderDuel(ui.S, r.battle);
  $("q-tag").textContent = "Правильный ответ";
  $("q-text").textContent = r.text;

  const entries = Object.entries(r.answers);
  let html = "";
  if (r.q_type === "CHOICE") {
    // ответы остаются на своих местах: верный — зелёный, чужие выборы — точками цвета игроков
    $("q-options").hidden = false;
    $("q-options").innerHTML = r.options.map((o, i) => {
      const who = entries.filter(([, v]) => v === i).map(([pid]) => `<i style="--c:${colorOf(pid)}"></i>`).join("");
      const mineWrong = r.answers[ui.me] === i && i !== r.correct;
      return `<button class="opt-btn ${i === r.correct ? "right" : "off"} ${mineWrong ? "wrong" : ""}" disabled>
        <span>${esc(o)}</span><span class="opt-who">${who}</span>${mineWrong ? '<b class="nope" aria-label="Неверно"></b>' : ""}</button>`;
    }).join("");
  } else {
    $("q-options").hidden = true;
    const fa = (n) => (r.is_year ? String(n) : fmt(n));
    html += `<div class="reveal-correct">${fa(r.correct)}</div><div class="reveal-list">`;
    const order = r.ranking || entries.map(([p]) => +p);
    html += order.map((pid) => {
      const v = r.answers[pid];
      const diff = Math.abs(v - r.correct);
      return `<div class="reveal-row ${pid === r.winner ? "win" : ""}">${shield(pid)}${esc(nameOf(pid))}
        <span class="val">${fa(v)} <small class="muted">(${diff === 0 ? "точно!" : "±" + fmt(diff)})</small></span></div>`;
    }).join("");
    html += "</div>";
  }
  if (!entries.length) html += '<div class="reveal-row">Никто не ответил</div>';

  let outcome = "";
  if (r.outcome === "tiebreaker") outcome = "Оба правы — решающий вопрос!";
  else if (r.outcome === "captured") outcome = `${nameOf(r.battle.attacker)} ${r.battle.attacker === ui.me ? "захватили" : "захватывает"} землю: +${fmt(r.points)}`;
  else if (r.outcome === "tower_down") outcome = `Башня пала! Осталось ${r.towers_left} — штурм продолжается`;
  else if (r.outcome === "castle_destroyed") outcome = `Замок разрушен! ${nameOf(r.battle.attacker)} ${r.battle.attacker === ui.me ? "забираете" : "забирает"} всё: +${fmt(r.points)}`;
  else if (r.outcome === "defended") outcome = `${nameOf(r.battle.defender)} ${r.battle.defender === ui.me ? "отстояли" : "отстоял"} землю${r.bonus ? ` (+${r.bonus} за оборону)` : ""}`;
  else if (r.kind === "final_tiebreaker" && r.winner != null) outcome = `${nameOf(r.winner)} ${r.winner === ui.me ? "побеждаете" : "побеждает"} в финальном вопросе!`;
  else if (r.picks) outcome = Object.entries(r.picks).map(([pid, n]) => `${nameOf(pid)} ${+pid === ui.me ? "берёте" : "берёт"} ${n === 1 ? "1 землю" : `${n} земли`}`).join(", ");
  else if (r.winner != null) outcome = `${nameOf(r.winner)} ${r.winner === ui.me ? "занимаете" : "занимает"} землю`;
  if (outcome) html += `<div class="reveal-outcome">${esc(outcome)}</div>`;
  if (r.fact) html += `<div class="reveal-fact">${esc(r.fact)}</div>`;
  $("q-status").innerHTML = html;
  renderRate(r.question_id);
}

function renderRate(qid) {
  const box = $("q-rate");
  box.hidden = qid == null;
  if (qid == null) return;
  const mine = ui.rated.get(qid);
  box.innerHTML = `<span class="rate-title">${mine === undefined ? "Оцените вопрос" : "Спасибо за оценку!"}</span>` +
    RATES.map(([v, icon, title]) =>
      `<button class="rate-btn ${mine === v ? "on" : ""}" data-v="${v}" data-q="${qid}"><span>${icon}</span>${title}</button>`
    ).join("");
}

// ---------------------------------------------------------------- таймер

function tick() {
  const s = ui.S;
  const fill = $("m-fuse");
  if (s?.timer_ends_at) {
    const now = Date.now() / 1000 + ui.skew;
    const left = Math.max(0, s.timer_ends_at - now);
    const total = ui.timerTotal?.phase === s.phase && ui.timerTotal.ends === s.timer_ends_at
      ? ui.timerTotal.total
      : (ui.timerTotal = { phase: s.phase, ends: s.timer_ends_at, total: Math.max(left, 0.1) }).total;
    fill.style.width = `${Math.min(100, (left / total) * 100)}%`;
    fill.classList.toggle("low", left < 3 && left > 0);
    if (s.state_name === "MATCHMAKING") $("search-timer").textContent = left > 0 ? `Боты вступят в бой через ${Math.ceil(left)} с` : "";
  } else {
    fill.style.width = "0";
  }
  requestAnimationFrame(tick);
}

// ---------------------------------------------------------------- итоги

function showEnd(final) {
  const s = ui.S;
  show("end");
  const results = final?.results || [];
  const mine = results.find((r) => r.tg_id === ui.me);
  $("end-title").textContent = mine?.place === 1 ? "Победа!" : "Конец войны";
  if (mine?.place === 1) haptic.ok();
  $("end-list").innerHTML = results.map((r) => {
    const p = s?.players[r.tg_id];
    return `<div class="card place ${r.tg_id === ui.me ? "me" : ""}" style="--c:${colorOf(r.tg_id)}">
      <span class="num">${r.place}</span>${shield(r.tg_id, r.territories)}
      <div class="place-name">${esc(r.tg_id === ui.me ? "Вы" : p?.username || r.tg_id)}${r.is_bot ? " " + BOT_MARK : ""}
        ${realmOf(r.tg_id) ? `<small>${esc(realmOf(r.tg_id))}</small>` : ""}</div>
      <div class="score"><b>${fmt(r.score)}</b><small>${r.territories} зем.${s?.capitals[r.tg_id] != null ? " + замок" : s?.players[r.tg_id]?.eliminated ? " · замок пал" : ""}</small></div></div>`;
  }).join("");
  $("end-rewards").innerHTML = mine
    ? `<span><i class="ico ico-gold"></i>+${mine.gold}</span><span><i class="ico ico-xp"></i>+${mine.xp}</span>`
    : "";
  socket.matchId = null;
}

// ---------------------------------------------------------------- пыль в луче света

function startDust() {
  const cv = $("dust");
  const ctx = cv.getContext("2d");
  if (!ctx || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const motes = [];
  let w = 0, h = 0, dpr = 1;
  const resize = () => {
    dpr = Math.min(2, devicePixelRatio || 1);
    w = cv.width = innerWidth * dpr;
    h = cv.height = innerHeight * dpr;
  };
  const spawn = (anywhere) => ({
    x: w * (0.2 + Math.random() * 0.6),
    y: anywhere ? Math.random() * h : h + 10,
    r: (0.6 + Math.random() * 1.8) * dpr,
    vy: -(0.08 + Math.random() * 0.25) * dpr,
    vx: (Math.random() - 0.5) * 0.12 * dpr,
    ph: Math.random() * Math.PI * 2,
  });
  resize();
  addEventListener("resize", resize);
  for (let i = 0; i < 38; i++) motes.push(spawn(true));
  const frame = (t) => {
    if (!document.hidden) {
      ctx.clearRect(0, 0, w, h);
      for (const m of motes) {
        m.x += m.vx + Math.sin(t / 2400 + m.ph) * 0.1 * dpr;
        m.y += m.vy;
        if (m.y < -10) Object.assign(m, spawn(false));
        // ярче в центре «луча»
        const beam = 1 - Math.min(1, Math.abs(m.x / w - 0.5) * 2.2);
        const a = (0.15 + 0.5 * beam) * (0.6 + 0.4 * Math.sin(t / 700 + m.ph));
        ctx.fillStyle = `rgba(255, 206, 120, ${a.toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- события UI

$("lobby-topics").addEventListener("click", (e) => {
  const b = e.target.closest(".topic");
  if (!b) return;
  ui.topic = b.dataset.topic;
  save("kq-topic", ui.topic);
  haptic.tap();
  renderTopics();
  showFact($("lobby-fact"));
});
$("lobby-maps").addEventListener("click", (e) => {
  const b = e.target.closest(".map-card");
  if (!b) return;
  ui.mapChoice = b.dataset.map;
  save("kq-map", ui.mapChoice);
  haptic.tap();
  renderMaps();
});
for (const btn of document.querySelectorAll("[data-fact-more]")) {
  btn.addEventListener("click", () => { haptic.tap(); showFact(btn.closest(".fact-card")); });
}
$("btn-play").onclick = () => { haptic.tap(); startMatch(); };
$("btn-again").onclick = () => { haptic.tap(); loadProfile(); startMatch(); };
$("btn-home").onclick = () => { show("lobby"); loadProfile(); };

$("q-options").addEventListener("click", (e) => {
  const b = e.target.closest(".opt-btn");
  if (!b || b.disabled) return;
  ui.chosen = +b.dataset.i;
  send({ action: "answer", value: ui.chosen });
  render();
});
$("q-keypad").addEventListener("click", (e) => {
  const b = e.target.closest(".key");
  if (!b || b.disabled) return;
  const k = b.dataset.k;
  if (k === "⌫") ui.typed = ui.typed.slice(0, -1);
  else if (k === "✓") { ui.chosen = +ui.typed; send({ action: "answer", value: +ui.typed }); }
  else if (ui.typed.length < 9) ui.typed = (ui.typed + k).replace(/^0+(?=\d)/, "");
  haptic.tap();
  render();
});
$("q-hints").addEventListener("click", (e) => {
  const b = e.target.closest(".hint-btn");
  if (b && !b.disabled) send({ use_hint: b.dataset.hint });
});
$("q-rate").addEventListener("click", async (e) => {
  const b = e.target.closest(".rate-btn");
  if (!b) return;
  const qid = +b.dataset.q, v = +b.dataset.v;
  haptic.tap();
  ui.rated.set(qid, v);
  renderRate(qid);
  try {
    await api(`/api/questions/${qid}/rate`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value: v }),
    });
  } catch {
    ui.rated.delete(qid);
    renderRate(qid);
    toast("Не удалось сохранить оценку");
  }
});

// ---------------------------------------------------------------- старт

// Telegram: safe-area (шапка «Закрыть/⋯» в fullscreen, полоска жестов) и стабильная высота webview
function syncTgInsets() {
  const st = document.documentElement.style;
  const sa = tg?.safeAreaInset || {}, ca = tg?.contentSafeAreaInset || {};
  st.setProperty("--tg-safe-top", `${sa.top || 0}px`);
  st.setProperty("--tg-safe-bottom", `${sa.bottom || 0}px`);
  st.setProperty("--tg-content-top", `${ca.top || 0}px`);
  if (tg?.viewportStableHeight) st.setProperty("--tg-vh", `${tg.viewportStableHeight}px`);
}
for (const ev of ["safeAreaChanged", "contentSafeAreaChanged", "viewportChanged"]) tg?.onEvent?.(ev, syncTgInsets);
syncTgInsets();

tg?.ready();
tg?.expand();
tg?.setHeaderColor?.("#120b06");
tg?.setBackgroundColor?.("#120b06");
tg?.disableVerticalSwipes?.();
show("lobby");
loadProfile();
startDust();
requestAnimationFrame(tick);
addEventListener("resize", () => ui.S && !$("scr-match").hidden && render());
