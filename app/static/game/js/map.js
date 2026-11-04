// Карта «золотой слиток во тьме»: SVG-регионы из /api/map?map_id=….
// Статичные слои (свечение, тень, слиток, фаска, границы) строятся один раз; при каждом снимке
// меняются только заливки и «живые» слои (подсветка, столицы, мечи, стрелки).

const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

// Глянцевые цвета игроков: блик → основной → тень
export const PALETTE = {
  red: ["#ff8a6a", "#d8342a", "#7e120b"],
  blue: ["#8fcbff", "#2f7fd8", "#113a7c"],
  green: ["#9be986", "#3fae3a", "#155d18"],
  yellow: ["#fff08f", "#f2c230", "#8e6204"],
  purple: ["#dcb0ff", "#9b4fd1", "#4d1c73"],
};
export const colorHex = (name) => PALETTE[name]?.[1] || "#8a7050";

// Золотая башня столицы (как в референсе — золото, а цвет владельца даёт табличка с ником)
function castle(u, towers = 3) {
  const g = el("g", { class: "cap-icon", transform: `scale(${u})` });
  g.appendChild(el("ellipse", { cx: 0, cy: 11, rx: 15, ry: 4, fill: "rgba(40,20,0,.45)" }));
  g.appendChild(el("path", {
    d: "M-12 11v-15h-3v-8h5v4h4v-4h4v4h4v-4h5v8h-3v15z",
    fill: "url(#kq-goldbar)", stroke: "#5a3510", "stroke-width": 1.4, "stroke-linejoin": "round",
  }));
  g.appendChild(el("path", { d: "M-4 11v-6a4 4 0 0 1 8 0v6z", fill: "#4a2a0a" }));
  g.appendChild(el("path", { d: "M0 -12v-12l9 3.5-9 3.5", fill: "#fff1c4", stroke: "#5a3510", "stroke-width": 1.2 }));
  // башни замка: целые — золотые, павшие — тёмные (как «жизни» в оригинале)
  for (let i = 0; i < 3; i++) {
    const alive = i < towers;
    g.appendChild(el("rect", {
      class: `tower ${alive ? "" : "down"}`, x: -10 + i * 7.5, y: 15, width: 5, height: 6, rx: 1,
      fill: alive ? "#ffd56a" : "#3a2410", stroke: "#2a1606", "stroke-width": 1,
    }));
  }
  return g;
}

// Скрещённые мечи на спорной земле
function swords(u) {
  const g = el("g", { class: "swords", transform: `scale(${u})` });
  const blade = (rot) => {
    const b = el("g", { transform: `rotate(${rot})` });
    b.appendChild(el("path", { d: "M-2 -20h4v24h-4z", fill: "#e9eef2", stroke: "#2a1a0a", "stroke-width": 1.2 }));
    b.appendChild(el("path", { d: "M-2 -20l2 -4 2 4z", fill: "#e9eef2", stroke: "#2a1a0a", "stroke-width": 1.2 }));
    b.appendChild(el("path", { d: "M-8 4h16v3h-16z", fill: "#d9a24a", stroke: "#2a1a0a", "stroke-width": 1.2 }));
    b.appendChild(el("path", { d: "M-1.8 7h3.6v8h-3.6z", fill: "#6b3f1a", stroke: "#2a1a0a", "stroke-width": 1 }));
    return b;
  };
  g.append(blade(-40), blade(40));
  return g;
}

// Объёмная стрелка, падающая на землю. Остриё в (0,0); две грани — светлая и тёмная.
function dropArrow(u, color) {
  const [hi, mid, lo] = PALETTE[color] || PALETTE.red;
  const g = el("g", { class: "drop", style: `--u:${u}` });
  g.appendChild(el("ellipse", { class: "drop-shadow", cx: 0, cy: 1, rx: 11 * u, ry: 3.5 * u, fill: "rgba(30,12,0,.55)" }));
  const a = el("g", { class: "drop-body", transform: `scale(${u})` });
  a.appendChild(el("path", { d: "M0 0L-14 -17h8v-24h6z", fill: hi, stroke: lo, "stroke-width": 1.3, "stroke-linejoin": "round" }));
  a.appendChild(el("path", { d: "M0 0L14 -17h-8v-24h-6z", fill: mid, stroke: lo, "stroke-width": 1.3, "stroke-linejoin": "round" }));
  g.appendChild(a);
  return g;
}

export class MapView {
  /**
   * @param svg   элемент <svg>
   * @param data  ответ /api/map
   * @param onTap (hitId|null, snap(options)=>id|null) — клиент сам решает, что значит тап
   */
  constructor(svg, data, onTap) {
    this.svg = svg;
    this.id = data.id;
    this.data = data;
    this.byId = new Map(data.territories.map((t) => [t.territory_id, t]));
    const [x, y, w, h] = data.view_box;
    this.u = w / 380;  // «экранный пиксель» при типичной ширине телефона — масштаб значков и шрифтов
    const u = this.u;
    const pad = 14 * u;
    svg.replaceChildren();
    this.full = { x: x - pad, y: y - pad, w: w + 2 * pad, h: h + 2 * pad };
    this.vb = [this.full.x, this.full.y, this.full.w, this.full.h];
    this.fitKey = null;
    svg.setAttribute("viewBox", this.vb.join(" "));
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    const defs = el("defs");
    defs.innerHTML = `
      <radialGradient id="kq-ingot" cx="45%" cy="35%" r="80%">
        <stop offset="0" stop-color="#fff5d6"/><stop offset=".5" stop-color="#f4d690"/><stop offset="1" stop-color="#d49a3e"/>
      </radialGradient>
      <linearGradient id="kq-goldbar" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#fff0b8"/><stop offset=".45" stop-color="#f0b949"/><stop offset="1" stop-color="#a86a12"/>
      </linearGradient>
      <linearGradient id="kq-sheen" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#fff" stop-opacity=".32"/><stop offset=".45" stop-color="#fff" stop-opacity="0"/>
      </linearGradient>
      <filter id="kq-blur-l" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="${7 * u}"/></filter>
      <filter id="kq-blur-s" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="${2.2 * u}"/></filter>
      ${Object.entries(PALETTE).map(([name, [hi, mid, lo]]) => `
        <linearGradient id="kq-g-${name}" x1="0" y1="0" x2=".35" y2="1">
          <stop offset="0" stop-color="${hi}"/><stop offset=".45" stop-color="${mid}"/><stop offset="1" stop-color="${lo}"/>
        </linearGradient>`).join("")}`;
    const clip = el("clipPath", { id: "kq-land" });
    for (const t of data.territories) clip.appendChild(el("path", { d: t.path }));
    defs.appendChild(clip);
    svg.appendChild(defs);

    // силуэт суши: из генератора (Россия) или просто все регионы (остров)
    const landPaths = data.outline ? [data.outline] : data.territories.map((t) => t.path);
    const land = (attrs) => {
      const g = el("g", attrs);
      for (const d of landPaths) g.appendChild(el("path", { d }));
      return g;
    };
    svg.appendChild(land({ class: "land-glow", fill: "none", stroke: "#ffb13b", "stroke-width": 16 * u, filter: "url(#kq-blur-l)" }));
    svg.appendChild(land({ fill: "#000", opacity: .6, transform: `translate(0 ${7 * u})`, filter: "url(#kq-blur-l)" }));
    svg.appendChild(land({ fill: "#6b420f", transform: `translate(0 ${2.5 * u})` }));  // торец слитка
    svg.appendChild(land({ fill: "url(#kq-ingot)" }));

    this.paths = new Map();
    const fills = el("g");
    for (const t of data.territories) {
      const p = el("path", { d: t.path, class: "terr", "data-t": t.territory_id });
      fills.appendChild(p);
      this.paths.set(t.territory_id, p);
    }
    svg.appendChild(fills);

    // фаска: тёмная размытая кромка внутри каждого региона + общий блик сверху
    const bevel = el("g", { "clip-path": "url(#kq-land)", class: "bevel" });
    for (const t of data.territories) {
      bevel.appendChild(el("path", { d: t.path, fill: "none", stroke: "#4a2806", "stroke-width": 7 * u, opacity: .5, filter: "url(#kq-blur-s)" }));
    }
    svg.appendChild(bevel);
    const sheen = el("g", { "clip-path": "url(#kq-land)", class: "sheen" });
    sheen.appendChild(el("rect", { x: x - pad, y: y - pad, width: w + 2 * pad, height: h + 2 * pad, fill: "url(#kq-sheen)" }));
    svg.appendChild(sheen);

    this.dimLayer = el("g", { class: "dim-layer" });
    const borders = el("g", { class: "borders" });
    for (const t of data.territories) borders.appendChild(el("path", { d: t.path }));
    svg.append(this.dimLayer, borders);
    svg.appendChild(land({ class: "rim", fill: "none" }));

    this.hlLayer = el("g", { class: "hl-layer" });
    this.labels = el("g", { class: "labels" });
    this.fx = el("g");  // стрелка атаки, мечи
    this.caps = el("g");
    this.drops = el("g");
    svg.append(this.hlLayer, this.labels, this.fx, this.caps, this.drops);

    this.labelNodes = new Map();
    for (const t of data.territories) {
      const g = el("g", { transform: `translate(${t.cx} ${t.cy})` });
      const val = el("text", { class: "terr-val", y: 1 * u, "font-size": 11 * u });
      val.textContent = t.base_points;
      const name = el("text", { class: "terr-name", y: 11 * u, "font-size": 7.5 * u });
      name.textContent = t.name;
      g.append(val, name);
      this.labels.appendChild(g);
      this.labelNodes.set(t.territory_id, { val, name });
    }

    this.prevOwners = null;
    svg.onclick = (e) => {
      const hit = e.target.closest?.("[data-t]");
      const hitId = hit ? +hit.dataset.t : null;
      onTap(hitId, (options) => this.snap(e, hitId, options));
    };
  }

  // Мелкие регионы на телефоне трудно попасть пальцем: берём ближайший допустимый к точке тапа
  snap(evt, hitId, options) {
    if (!options.size) return null;
    if (options.has(hitId)) return hitId;
    const m = this.svg.getScreenCTM();
    if (!m) return null;
    const p = new DOMPoint(evt.clientX, evt.clientY).matrixTransform(m.inverse());
    let best = null, bestD = Infinity;
    for (const id of options) {
      const t = this.byId.get(id);
      const d = Math.hypot(t.cx - p.x, t.cy - p.y);
      if (d < bestD) { bestD = d; best = id; }
    }
    return bestD <= 46 * this.u ? best : null;
  }

  /**
   * @param s     публичный MatchState
   * @param opts  { options: Set<id>, src: id|null, colorName(pid) -> "red"|…, nameOf(pid) }
   */
  render(s, { options = new Set(), src = null, colorName, nameOf }) {
    const u = this.u;
    const owners = s.territories;
    // цена земли живая: 200 → 400 после захвата, замок/руины — 1000
    for (const [tid, n] of this.labelNodes) {
      const v = s.values?.[tid];
      if (v != null && n.val.textContent !== String(v)) n.val.textContent = v;
    }
    for (const [tid, p] of this.paths) {
      const owner = owners[tid];
      p.style.fill = owner != null ? `url(#kq-g-${colorName(owner)})` : "";
      p.classList.toggle("owned", owner != null);
      if (this.prevOwners && this.prevOwners[tid] !== owner && owner != null) {
        p.classList.remove("flood");
        void p.getBBox();  // перезапуск анимации
        p.classList.add("flood");
        this.drop(tid, colorName(owner));
      }
      const lbl = this.labelNodes.get(tid);
      lbl.val.style.display = owner == null ? "" : "none";
      lbl.name.classList.toggle("on-color", owner != null);
    }
    this.prevOwners = { ...owners };

    // затемнение недоступного и подсветка доступного
    this.dimLayer.replaceChildren();
    this.hlLayer.replaceChildren();
    const fight = s.battle ? [s.battle.source, s.battle.target] : [];
    for (const [tid, t] of this.byId) {
      if (options.size && !options.has(tid) && src !== tid) this.dimLayer.appendChild(el("path", { d: t.path }));
      if (options.has(tid)) this.hlLayer.appendChild(el("path", { d: t.path, class: "hl-opt" }));
      if (src === tid) this.hlLayer.appendChild(el("path", { d: t.path, class: "hl-src" }));
      if (fight.includes(tid)) this.hlLayer.appendChild(el("path", { d: t.path, class: "hl-fight" }));
    }

    this.fx.replaceChildren();
    if (s.battle) {
      this.fx.appendChild(this.attackArrow(s.battle.source, s.battle.target, colorName(s.battle.attacker)));
      const t = this.byId.get(s.battle.target);
      const sw = el("g", { transform: `translate(${t.cx} ${t.cy - 2 * u})` });
      sw.appendChild(swords(u));
      this.fx.appendChild(sw);
    }

    this.caps.replaceChildren();
    for (const [pid, tid] of Object.entries(s.capitals)) {
      const t = this.byId.get(tid);
      const g = el("g", { transform: `translate(${t.cx} ${t.cy})` });
      g.appendChild(castle(u, s.towers?.[pid] ?? 3));
      const nick = String(nameOf(pid)).slice(0, 14);
      const wpx = (nick.length * 5.2 + 10) * u;
      const plate = el("g", { transform: `translate(0 ${-30 * u})` });
      plate.appendChild(el("rect", {
        x: -wpx / 2, y: -7 * u, width: wpx, height: 13 * u, rx: 6.5 * u,
        fill: `url(#kq-g-${colorName(pid)})`, stroke: "#2a1606", "stroke-width": 1 * u,
      }));
      const tx = el("text", { class: "cap-nick", y: 2.6 * u, "font-size": 8.5 * u });
      tx.textContent = nick;
      plate.appendChild(tx);
      g.appendChild(plate);
      this.caps.appendChild(g);
    }
  }

  /**
   * «Камера»: плавно вписать регионы ids (или всю карту) в верхнюю полосу высотой visH px —
   * ниже может лежать листок вопроса. На телефоне это заодно делает мелкие регионы крупнее.
   */
  fit(ids, visH) {
    const { width: W, height: H } = this.svg.getBoundingClientRect();
    if (!W || !H) return;
    visH = Math.max(100, Math.min(H, visH ?? H));
    const key = `${(ids || []).join(",")}|${Math.round(W)}x${Math.round(H)}|${Math.round(visH)}`;
    if (key === this.fitKey) return;
    this.fitKey = key;

    let R = this.full;
    if (ids?.length) {
      const boxes = ids.map((id) => this.paths.get(id).getBBox());
      const x0 = Math.min(...boxes.map((b) => b.x)), y0 = Math.min(...boxes.map((b) => b.y));
      const x1 = Math.max(...boxes.map((b) => b.x + b.width)), y1 = Math.max(...boxes.map((b) => b.y + b.height));
      const m = 26 * this.u;  // поле вокруг — чтобы влезли значки и таблички с никами
      R = { x: x0 - m, y: y0 - m * 1.6, w: x1 - x0 + 2 * m, h: y1 - y0 + m * 2.6 };
    }
    const kFull = Math.min(W / this.full.w, visH / this.full.h);
    const k = Math.min(W / R.w, visH / R.h, kFull * 2.6);  // px на единицу карты; не больше ×2.6
    const cx = R.x + R.w / 2, cy = R.y + R.h / 2;
    this.animateViewBox([cx - W / k / 2, cy - visH / k / 2, W / k, H / k]);
  }

  animateViewBox(to) {
    const from = [...this.vb];
    const t0 = performance.now(), dur = 550;
    cancelAnimationFrame(this.vbAnim);
    if (document.hidden || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      this.vb = to;  // в фоне rAF не тикает — ставим сразу
      return this.svg.setAttribute("viewBox", to.join(" "));
    }
    const step = (now) => {
      const t = Math.min(1, (now - t0) / dur);
      const e = t < .5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
      this.vb = from.map((v, i) => v + (to[i] - v) * e);
      this.svg.setAttribute("viewBox", this.vb.join(" "));
      if (t < 1) this.vbAnim = requestAnimationFrame(step);
    };
    this.vbAnim = requestAnimationFrame(step);
  }

  drop(tid, color) {
    const t = this.byId.get(tid);
    const g = el("g", { transform: `translate(${t.cx} ${t.cy - 4 * this.u})` });
    g.appendChild(dropArrow(this.u, color));
    this.drops.appendChild(g);
    setTimeout(() => g.remove(), 2600);
  }

  attackArrow(fromId, toId, color) {
    const u = this.u;
    const a = this.byId.get(fromId), b = this.byId.get(toId);
    const dx = b.cx - a.cx, dy = b.cy - a.cy;
    const cx = (a.cx + b.cx) / 2 - dy * 0.3, cy = (a.cy + b.cy) / 2 + dx * 0.3;  // изгиб дугой
    const ex = b.cx - dx * 0.2, ey = b.cy - dy * 0.2;  // не доводим до мечей
    const [hi, mid, lo] = PALETTE[color] || PALETTE.red;
    const g = el("g", { class: "atk" });
    const d = `M${a.cx} ${a.cy} Q${cx} ${cy} ${ex} ${ey}`;
    g.appendChild(el("path", { d, fill: "none", stroke: lo, "stroke-width": 9 * u, "stroke-linecap": "round", opacity: .7 }));
    g.appendChild(el("path", { d, class: "atk-line", fill: "none", stroke: mid, "stroke-width": 5 * u, "stroke-linecap": "round", "stroke-dasharray": `${10 * u} ${7 * u}` }));
    // наконечник по касательной в конце кривой
    const tx = ex - cx, ty = ey - cy, len = Math.hypot(tx, ty) || 1;
    const nx = tx / len, ny = ty / len, s = 12 * u;
    const pts = [
      [ex + nx * s, ey + ny * s],
      [ex - ny * s * 0.8, ey + nx * s * 0.8],
      [ex + ny * s * 0.8, ey - nx * s * 0.8],
    ].map((p) => p.join(",")).join(" ");
    g.appendChild(el("polygon", { points: pts, fill: hi, stroke: lo, "stroke-width": 1.5 * u, "stroke-linejoin": "round" }));
    return g;
  }
}

// Маленький силуэт карты для выбора в лобби
export function thumbnail(data) {
  const svg = el("svg", { viewBox: data.view_box.join(" "), class: "map-thumb", "aria-hidden": "true" });
  for (const t of data.territories) svg.appendChild(el("path", { d: t.path }));
  return svg;
}
