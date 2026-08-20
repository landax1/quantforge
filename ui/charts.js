/* Botiquant chart library — tiny, dependency-free SVG charts.
   Everything renders offline; colors come from CSS variables. */

"use strict";

const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";

  function css(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function el(tag, attrs = {}) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  }

  function svgRoot(container, w, h) {
    container.innerHTML = "";
    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "none" });
    svg.style.width = "100%";
    svg.style.height = "100%";
    svg.style.display = "block";
    container.appendChild(svg);
    return svg;
  }

  function niceTicks(lo, hi, count = 4) {
    if (!isFinite(lo) || !isFinite(hi) || lo === hi) return [lo];
    const span = hi - lo;
    const step = Math.pow(10, Math.floor(Math.log10(span / count)));
    const err = (span / count) / step;
    const mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
    const s = step * mult;
    const ticks = [];
    for (let v = Math.ceil(lo / s) * s; v <= hi + 1e-9; v += s) ticks.push(v);
    return ticks;
  }

  function fmtNum(v) {
    if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1) + "M";
    if (Math.abs(v) >= 1e4) return (v / 1e3).toFixed(1) + "k";
    if (Math.abs(v) >= 100) return v.toFixed(0);
    return (+v.toFixed(2)).toString();
  }

  /* Line/area chart. opts: {series:[{values,color,fill}], labels, baseline, height} */
  function line(container, opts) {
    const W = 900, H = opts.height || 260, padL = 52, padR = 12, padT = 12, padB = 24;
    const svg = svgRoot(container, W, H);
    const all = opts.series.flatMap(s => s.values).filter(v => isFinite(v));
    if (!all.length) return;
    let lo = Math.min(...all), hi = Math.max(...all);
    if (opts.baseline != null) { lo = Math.min(lo, opts.baseline); hi = Math.max(hi, opts.baseline); }
    const span = (hi - lo) || 1;
    lo -= span * 0.04; hi += span * 0.04;

    const X = i => padL + (i / Math.max(opts.series[0].values.length - 1, 1)) * (W - padL - padR);
    const Y = v => H - padB - ((v - lo) / (hi - lo)) * (H - padT - padB);

    for (const t of niceTicks(lo, hi)) {
      svg.appendChild(el("line", { x1: padL, x2: W - padR, y1: Y(t), y2: Y(t),
        stroke: css("--grid", "#232a3b"), "stroke-width": 1 }));
      const label = el("text", { x: padL - 8, y: Y(t) + 4, "text-anchor": "end",
        fill: css("--text-dim", "#8b93a8"), "font-size": 11 });
      label.textContent = fmtNum(t);
      svg.appendChild(label);
    }
    if (opts.baseline != null) {
      svg.appendChild(el("line", { x1: padL, x2: W - padR, y1: Y(opts.baseline), y2: Y(opts.baseline),
        stroke: css("--text-dim", "#8b93a8"), "stroke-dasharray": "4 4", "stroke-width": 1 }));
    }
    if (opts.labels && opts.labels.length > 1) {
      const n = opts.labels.length;
      for (const frac of [0, 0.5, 1]) {
        const i = Math.round(frac * (n - 1));
        const t = el("text", { x: X(i * (opts.series[0].values.length - 1) / (n - 1)),
          y: H - 6, "text-anchor": frac === 0 ? "start" : frac === 1 ? "end" : "middle",
          fill: css("--text-dim", "#8b93a8"), "font-size": 11 });
        t.textContent = String(opts.labels[i]).slice(0, 10);
        svg.appendChild(t);
      }
    }
    for (const s of opts.series) {
      const color = s.color || css("--accent", "#6d8dff");
      const pts = s.values.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
      if (s.fill) {
        const area = `${X(0).toFixed(1)},${(H - padB).toFixed(1)} ${pts} ` +
                     `${X(s.values.length - 1).toFixed(1)},${(H - padB).toFixed(1)}`;
        svg.appendChild(el("polygon", { points: area, fill: color, opacity: 0.12 }));
      }
      svg.appendChild(el("polyline", { points: pts, fill: "none", stroke: color,
        "stroke-width": s.width || 2, opacity: s.opacity || 1 }));
    }
  }

  /* Monte Carlo fan chart: bands {p5,p25,p50,p75,p95}, baseline */
  function fan(container, bands, baseline) {
    const W = 900, H = 260, padL = 52, padR = 12, padT = 12, padB = 20;
    const svg = svgRoot(container, W, H);
    const n = bands.p50.length;
    const all = [...bands.p5, ...bands.p95];
    let lo = Math.min(...all, baseline), hi = Math.max(...all, baseline);
    const span = (hi - lo) || 1; lo -= span * 0.04; hi += span * 0.04;
    const X = i => padL + (i / (n - 1)) * (W - padL - padR);
    const Y = v => H - padB - ((v - lo) / (hi - lo)) * (H - padT - padB);
    for (const t of niceTicks(lo, hi)) {
      svg.appendChild(el("line", { x1: padL, x2: W - padR, y1: Y(t), y2: Y(t),
        stroke: css("--grid", "#232a3b") }));
      const lb = el("text", { x: padL - 8, y: Y(t) + 4, "text-anchor": "end",
        fill: css("--text-dim", "#8b93a8"), "font-size": 11 });
      lb.textContent = fmtNum(t); svg.appendChild(lb);
    }
    const accent = css("--accent", "#6d8dff");
    const band = (loA, hiA, opacity) => {
      const fwd = loA.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`);
      const back = hiA.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).reverse();
      svg.appendChild(el("polygon", { points: [...fwd, ...back].join(" "),
        fill: accent, opacity, stroke: "none" }));
    };
    band(bands.p5, bands.p95, 0.10);
    band(bands.p25, bands.p75, 0.18);
    svg.appendChild(el("line", { x1: padL, x2: W - padR, y1: Y(baseline), y2: Y(baseline),
      stroke: css("--text-dim", "#8b93a8"), "stroke-dasharray": "4 4" }));
    svg.appendChild(el("polyline", {
      points: bands.p50.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" "),
      fill: "none", stroke: accent, "stroke-width": 2 }));
  }

  /* Histogram from {counts, edges}; marker draws a vertical reference line */
  function histogram(container, hist, marker) {
    const W = 900, H = 200, padL = 40, padR = 12, padT = 8, padB = 22;
    const svg = svgRoot(container, W, H);
    const counts = hist.counts, edges = hist.edges;
    const maxC = Math.max(...counts, 1);
    const lo = edges[0], hi = edges[edges.length - 1];
    const X = v => padL + ((v - lo) / (hi - lo || 1)) * (W - padL - padR);
    const accent = css("--accent", "#6d8dff");
    counts.forEach((c, i) => {
      const x0 = X(edges[i]), x1 = X(edges[i + 1]);
      const h = (c / maxC) * (H - padT - padB);
      svg.appendChild(el("rect", { x: x0 + 0.5, y: H - padB - h,
        width: Math.max(x1 - x0 - 1, 1), height: h, fill: accent, opacity: 0.75, rx: 1 }));
    });
    for (const frac of [0, 0.5, 1]) {
      const v = lo + frac * (hi - lo);
      const t = el("text", { x: X(v), y: H - 6,
        "text-anchor": frac === 0 ? "start" : frac === 1 ? "end" : "middle",
        fill: css("--text-dim", "#8b93a8"), "font-size": 11 });
      t.textContent = fmtNum(v); svg.appendChild(t);
    }
    if (marker != null && isFinite(marker)) {
      svg.appendChild(el("line", { x1: X(marker), x2: X(marker), y1: padT, y2: H - padB,
        stroke: css("--warn", "#fbbf24"), "stroke-width": 1.5, "stroke-dasharray": "4 3" }));
    }
  }

  /* Vertical bars: items [{label, value, color?}] */
  function bars(container, items, opts = {}) {
    const W = 900, H = opts.height || 200, padL = 46, padR = 12, padT = 10, padB = 26;
    const svg = svgRoot(container, W, H);
    if (!items.length) return;
    const vals = items.map(d => d.value);
    let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    if (lo === hi) hi = lo + 1;
    const Y = v => H - padB - ((v - lo) / (hi - lo)) * (H - padT - padB);
    for (const t of niceTicks(lo, hi)) {
      svg.appendChild(el("line", { x1: padL, x2: W - padR, y1: Y(t), y2: Y(t),
        stroke: css("--grid", "#232a3b") }));
      const lb = el("text", { x: padL - 8, y: Y(t) + 4, "text-anchor": "end",
        fill: css("--text-dim", "#8b93a8"), "font-size": 11 });
      lb.textContent = fmtNum(t); svg.appendChild(lb);
    }
    const bw = (W - padL - padR) / items.length;
    items.forEach((d, i) => {
      const x = padL + i * bw;
      const y0 = Y(Math.max(0, d.value)), y1 = Y(Math.min(0, d.value));
      const color = d.color || (d.value >= 0 ? css("--pos", "#4ade80") : css("--neg", "#f87171"));
      svg.appendChild(el("rect", { x: x + bw * 0.15, y: y0, width: bw * 0.7,
        height: Math.max(y1 - y0, 1), fill: color, rx: 2, opacity: 0.85 }));
      if (items.length <= 24) {
        const t = el("text", { x: x + bw / 2, y: H - 8, "text-anchor": "middle",
          fill: css("--text-dim", "#8b93a8"), "font-size": 10 });
        t.textContent = String(d.label).slice(0, 8); svg.appendChild(t);
      }
    });
  }

  /* Monthly-returns heat grid rendered as an HTML table */
  function monthlyGrid(container, monthly) {
    const MONTHS = t("chart.months").split(",");
    const years = [...new Set(monthly.map(m => m.year))].sort();
    const map = {};
    monthly.forEach(m => { map[`${m.year}-${m.month}`] = m.return_pct; });
    const maxAbs = Math.max(1, ...monthly.map(m => Math.abs(m.return_pct)));
    let html = `<table class="heat-table"><thead><tr><th></th>${
      MONTHS.map(m => `<th>${m}</th>`).join("")}<th>Year</th></tr></thead><tbody>`;
    for (const y of years) {
      let yearTotal = 1;
      let row = `<tr><th>${y}</th>`;
      for (let mo = 1; mo <= 12; mo++) {
        const v = map[`${y}-${mo}`];
        if (v == null) { row += `<td class="empty">–</td>`; continue; }
        yearTotal *= 1 + v / 100;
        const a = Math.min(Math.abs(v) / maxAbs, 1) * 0.55 + 0.08;
        const bg = v >= 0 ? `rgba(74,222,128,${a})` : `rgba(248,113,113,${a})`;
        row += `<td style="background:${bg}">${v.toFixed(1)}</td>`;
      }
      const tot = (yearTotal - 1) * 100;
      row += `<td class="${tot >= 0 ? "pos" : "neg"}"><b>${tot.toFixed(1)}</b></td></tr>`;
      html += row;
    }
    container.innerHTML = html + "</tbody></table>";
  }

  /* Correlation heatmap as an HTML table */
  function corrGrid(container, names, matrix) {
    let html = `<table class="heat-table corr"><thead><tr><th></th>${
      names.map(n => `<th title="${n}">${n.slice(0, 10)}</th>`).join("")}</tr></thead><tbody>`;
    matrix.forEach((row, i) => {
      html += `<tr><th title="${names[i]}">${names[i].slice(0, 14)}</th>`;
      row.forEach(v => {
        const a = Math.min(Math.abs(v), 1) * 0.6 + 0.05;
        const bg = v >= 0 ? `rgba(109,141,255,${a})` : `rgba(248,113,113,${a})`;
        html += `<td style="background:${bg}">${v.toFixed(2)}</td>`;
      });
      html += "</tr>";
    });
    container.innerHTML = html + "</tbody></table>";
  }

  /* ------------------------------------------------------------ sparkline
     Inline SVG string (no DOM node needed) so it can be embedded straight
     into a table cell while the databank is being rendered. */
  function sparkSvg(values, opts = {}) {
    if (!values || values.length < 2) return "";
    const w = opts.width || 108, h = opts.height || 30, pad = 2;
    let lo = Math.min(...values), hi = Math.max(...values);
    if (!isFinite(lo) || !isFinite(hi)) return "";
    if (lo === hi) { lo -= 1; hi += 1; }
    const X = i => pad + (i / (values.length - 1)) * (w - pad * 2);
    const Y = v => h - pad - ((v - lo) / (hi - lo)) * (h - pad * 2);
    const up = values[values.length - 1] >= values[0];
    const color = up ? css("--pos", "#4ade80") : css("--neg", "#f87171");
    const pts = values.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
    const uid = `sg${Math.random().toString(36).slice(2, 8)}`;
    // baseline = starting capital, so losing stretches show below it
    const base = Y(values[0]);
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"
        preserveAspectRatio="none" aria-hidden="true">
      <defs><linearGradient id="${uid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.35"/>
        <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
      </linearGradient></defs>
      <polygon points="${X(0).toFixed(1)},${h - pad} ${pts} ${X(values.length - 1).toFixed(1)},${h - pad}"
        fill="url(#${uid})"/>
      <line x1="${pad}" x2="${w - pad}" y1="${base.toFixed(1)}" y2="${base.toFixed(1)}"
        stroke="${css("--text-dim", "#8b93a8")}" stroke-width="0.6" stroke-dasharray="2 2" opacity="0.5"/>
      <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.6"
        stroke-linejoin="round" stroke-linecap="round"/>
    </svg>`;
  }

  /* ----------------------------------------------------------- progress ring
     Inline SVG for "cuánto falta para llenar el databank". Devuelve string
     para poder incrustarlo directo en el HTML que se está armando. */
  /* Mueve un anillo YA dibujado en vez de reemplazarlo.

     ringSvg devuelve marcado nuevo con un id de gradiente aleatorio, asi que
     escribirlo de nuevo cambia el nodo y el navegador no tiene desde donde
     animar: la transicion escrita en el propio SVG nunca corre. Con el nodo
     quieto y solo el offset cambiando, el anillo avanza. */
  function ringUpdate(container, fraction) {
    const circulos = container.querySelectorAll("circle");
    if (circulos.length < 2) return false;
    const aro = circulos[1];
    const c = parseFloat(aro.getAttribute("stroke-dasharray") || "0");
    if (!c) return false;
    const f = Math.max(0, Math.min(isFinite(fraction) ? fraction : 0, 1));
    aro.setAttribute("stroke-dashoffset", (c * (1 - f)).toFixed(1));
    // el color de "terminado" tambien cambia sin rehacer el nodo
    if (f >= 1) aro.setAttribute("stroke", css("--pos", "#3ddc97"));
    return true;
  }

  function ringSvg(fraction, opts = {}) {
    const size = opts.size || 124, stroke = opts.stroke || 9;
    const r = (size - stroke) / 2, c = 2 * Math.PI * r;
    const f = Math.max(0, Math.min(isFinite(fraction) ? fraction : 0, 1));
    const uid = `rg${Math.random().toString(36).slice(2, 8)}`;
    const done = f >= 1;
    const a = done ? css("--pos", "#3ddc97") : css("--accent", "#6d8dff");
    const b = done ? css("--pos", "#3ddc97") : css("--accent-2", "#a78bfa");
    return `<svg viewBox="0 0 ${size} ${size}" aria-hidden="true">
      <defs><linearGradient id="${uid}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="${a}"/><stop offset="100%" stop-color="${b}"/>
      </linearGradient></defs>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none"
        stroke="${css("--border", "#222839")}" stroke-width="${stroke}"/>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none"
        stroke="url(#${uid})" stroke-width="${stroke}" stroke-linecap="round"
        stroke-dasharray="${c.toFixed(1)}"
        stroke-dashoffset="${(c * (1 - f)).toFixed(1)}"
        style="transition:stroke-dashoffset .5s cubic-bezier(.22,.61,.36,1)"/>
    </svg>`;
  }

  /* ------------------------------------------------- equity + drawdown */
  /* The headline chart: equity as a filled area, the underwater curve
     beneath it, and a hover readout. opts: {values, labels, initial} */
  function equity(container, opts) {
    const values = opts.values || [];
    if (values.length < 2) return;
    const W = 900, H = opts.height || 300;
    const padL = 58, padR = 14, padT = 14, gap = 10;
    const ddH = Math.round(H * 0.24), eqH = H - ddH - gap - 24;
    const svg = svgRoot(container, W, H);
    container.style.position = "relative";

    const peak = [];
    let mx = -Infinity;
    for (const v of values) { mx = Math.max(mx, v); peak.push(mx); }
    const dd = values.map((v, i) => peak[i] > 0 ? (v - peak[i]) / peak[i] * 100 : 0);

    let lo = Math.min(...values), hi = Math.max(...values);
    const span = (hi - lo) || 1; lo -= span * 0.06; hi += span * 0.06;
    const X = i => padL + (i / (values.length - 1)) * (W - padL - padR);
    const Y = v => padT + eqH - ((v - lo) / (hi - lo)) * eqH;
    const ddLo = Math.min(...dd, -0.5);
    const ddY = v => padT + eqH + gap + (v / ddLo) * ddH;

    const accent = css("--accent", "#6d8dff");
    const neg = css("--neg", "#f87171");
    const dim = css("--text-dim", "#8b93a8");

    for (const t of niceTicks(lo, hi, 4)) {
      svg.appendChild(el("line", { x1: padL, x2: W - padR, y1: Y(t), y2: Y(t),
        stroke: css("--grid", "#232a3b"), "stroke-width": 1 }));
      const lb = el("text", { x: padL - 9, y: Y(t) + 4, "text-anchor": "end",
        fill: dim, "font-size": 11 });
      lb.textContent = fmtNum(t);
      svg.appendChild(lb);
    }

    const grad = el("linearGradient", { id: "eqgrad", x1: "0", y1: "0", x2: "0", y2: "1" });
    grad.appendChild(el("stop", { offset: "0%", "stop-color": accent, "stop-opacity": "0.30" }));
    grad.appendChild(el("stop", { offset: "100%", "stop-color": accent, "stop-opacity": "0.02" }));
    const defs = el("defs"); defs.appendChild(grad); svg.appendChild(defs);

    const pts = values.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
    svg.appendChild(el("polygon", {
      points: `${X(0).toFixed(1)},${padT + eqH} ${pts} ${X(values.length - 1).toFixed(1)},${padT + eqH}`,
      fill: "url(#eqgrad)" }));
    if (opts.initial != null) {
      svg.appendChild(el("line", { x1: padL, x2: W - padR, y1: Y(opts.initial), y2: Y(opts.initial),
        stroke: dim, "stroke-dasharray": "4 4", "stroke-width": 1, opacity: 0.7 }));
    }

    /* La marca del corte: dónde termina el tramo con el que se buscó y empieza
       el que la estrategia nunca vio. Es el dato que hace que mirar la curva
       completa signifique algo — sin la línea, las dos mitades se leen como
       una sola y no hay forma de ver si algo cambió al cruzarla. */
    if (opts.marca && opts.labels && opts.labels.length === values.length) {
      const corte = opts.labels.findIndex(l => l >= opts.marca);
      if (corte > 0) {
        const xc = X(corte);
        svg.appendChild(el("line", { x1: xc, x2: xc, y1: padT, y2: padT + eqH + gap + ddH,
          stroke: css("--warn", "#e59700"), "stroke-width": 1.5,
          "stroke-dasharray": "5 3", opacity: 0.9 }));
        const rot = el("text", { x: xc + 5, y: padT + 11, fill: css("--warn", "#e59700"),
          "font-size": 10, "font-weight": 600 });
        rot.textContent = opts.marcaTexto || "";
        svg.appendChild(rot);
      }
    }
    svg.appendChild(el("polyline", { points: pts, fill: "none", stroke: accent,
      "stroke-width": 2, "stroke-linejoin": "round" }));

    // underwater / drawdown panel
    const ddPts = dd.map((v, i) => `${X(i).toFixed(1)},${ddY(v).toFixed(1)}`).join(" ");
    svg.appendChild(el("polygon", {
      points: `${X(0).toFixed(1)},${padT + eqH + gap} ${ddPts} ${X(values.length - 1).toFixed(1)},${padT + eqH + gap}`,
      fill: neg, opacity: 0.18 }));
    svg.appendChild(el("polyline", { points: ddPts, fill: "none", stroke: neg,
      "stroke-width": 1.2 }));
    const ddLab = el("text", { x: padL - 9, y: padT + eqH + gap + ddH, "text-anchor": "end",
      fill: dim, "font-size": 10 });
    ddLab.textContent = `${ddLo.toFixed(0)}%`;
    svg.appendChild(ddLab);
    const ddTitle = el("text", { x: padL + 4, y: padT + eqH + gap + 11, fill: dim, "font-size": 10 });
    ddTitle.textContent = t("chart.drawdown_from_peak");
    svg.appendChild(ddTitle);

    if (opts.labels && opts.labels.length > 1) {
      for (const frac of [0, 0.5, 1]) {
        const i = Math.round(frac * (values.length - 1));
        const t = el("text", { x: X(i), y: H - 6,
          "text-anchor": frac === 0 ? "start" : frac === 1 ? "end" : "middle",
          fill: dim, "font-size": 11 });
        const li = Math.round(frac * (opts.labels.length - 1));
        t.textContent = String(opts.labels[li]).slice(0, 10);
        svg.appendChild(t);
      }
    }

    // hover crosshair + readout
    const cursor = el("line", { y1: padT, y2: padT + eqH, stroke: css("--text", "#e6e9f2"),
      "stroke-width": 1, opacity: 0 });
    const dot = el("circle", { r: 3.5, fill: accent, opacity: 0 });
    svg.appendChild(cursor); svg.appendChild(dot);
    const tip = document.createElement("div");
    tip.className = "chart-tip";
    container.appendChild(tip);

    svg.addEventListener("mousemove", (ev) => {
      const r = svg.getBoundingClientRect();
      const rel = (ev.clientX - r.left) / r.width * W;
      const i = Math.max(0, Math.min(values.length - 1,
        Math.round((rel - padL) / (W - padL - padR) * (values.length - 1))));
      cursor.setAttribute("x1", X(i)); cursor.setAttribute("x2", X(i));
      cursor.setAttribute("opacity", "0.35");
      dot.setAttribute("cx", X(i)); dot.setAttribute("cy", Y(values[i]));
      dot.setAttribute("opacity", "1");
      const label = opts.labels ? opts.labels[Math.min(i, opts.labels.length - 1)] : "";
      tip.innerHTML = `<b>${fmtNum(values[i])}</b>` +
        `<span>${label || ""}</span><span class="tip-dd">${t("chart.below_peak", { pct: dd[i].toFixed(1) })}</span>`;
      tip.style.opacity = "1";
      tip.style.left = `${Math.min(Math.max(ev.clientX - r.left, 60), r.width - 60)}px`;
    });
    svg.addEventListener("mouseleave", () => {
      cursor.setAttribute("opacity", "0"); dot.setAttribute("opacity", "0");
      tip.style.opacity = "0";
    });
  }

  return { line, fan, histogram, bars, monthlyGrid, corrGrid, sparkSvg, ringSvg, ringUpdate, equity };
})();
