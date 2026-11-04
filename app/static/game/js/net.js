// Сеть: авторизация Telegram, REST и WebSocket с переподключением.

export const tg = window.Telegram?.WebApp;

// Вне Telegram (браузер при разработке) — dev-вход; сервер примет его только при DEV_AUTH_BYPASS=true
function devInitData() {
  let id;
  try {
    id = localStorage.getItem("kq-dev-id");
    if (!id) { id = String(100000 + Math.floor(Math.random() * 900000)); localStorage.setItem("kq-dev-id", id); }
  } catch { id = String(100000 + Math.floor(Math.random() * 900000)); }
  const qsId = new URLSearchParams(location.search).get("dev");  // ?dev=2 — второй игрок в соседней вкладке
  if (qsId) id = qsId;
  return `dev:${id}:voin${id.slice(-3)}`;  // только ASCII: значение уходит в HTTP-заголовок
}

export const initData = tg?.initData || devInitData();

export async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: { "X-Init-Data": initData, ...(opts.headers || {}) } });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export class GameSocket {
  constructor(onMessage, onStatus) {
    this.onMessage = onMessage;
    this.onStatus = onStatus;
    this.ws = null;
    this.matchId = null;
    this.topic = null;
    this.mapId = null;
    this.closedByServer = false;
    this.retries = 0;
  }

  connect() {
    this.closedByServer = false;
    const q = new URLSearchParams({ init_data: initData });
    if (this.matchId) q.set("match_id", this.matchId);
    else {
      if (this.topic) q.set("topic", this.topic);
      if (this.mapId) q.set("map", this.mapId);
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws?${q}`);
    this.ws = ws;
    ws.onopen = () => { this.retries = 0; this.onStatus("open"); };
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.state?.match_id) this.matchId = m.state.match_id;
      if (m.type === "end") this.closedByServer = true;
      this.onMessage(m);
    };
    ws.onclose = (e) => {
      if (this.ws !== ws) return;
      // 1000 — матч закончен; 4401 — не прошла авторизация; остальное — обрыв сети, пробуем вернуться
      if (this.closedByServer || e.code === 1000 || e.code === 4000) return this.onStatus("closed");
      if (e.code === 4401) return this.onStatus("auth", e.reason);
      this.onStatus("reconnecting");
      const delay = Math.min(8000, 800 * 2 ** this.retries++);
      setTimeout(() => this.ws === ws && this.connect(), delay);
    };
  }

  send(obj) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  close() {
    const ws = this.ws;
    this.ws = null;
    this.matchId = null;
    ws?.close(1000);
  }
}
