/* LidSense dashboard. The same file runs in two places:
 *  - cloud (PHP + MySQL): read-only, needs login, can show several devices
 *  - Raspberry Pi touchscreen (Flask + SQLite): single device, with session controls
 * Both answer the same api/*.php URLs, so this file has one code path.
 */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const S = { device: "", range: "6h", metric: "s11_db", info: null, bands: [], lastSeq: null,
              trend: null, sweep: null, readings: [] };

  // ------------------------------------------------------------------ helpers
  async function api(path, opts) {
    const r = await fetch("api/" + path, { cache: "no-store", credentials: "same-origin", ...opts });
    if (r.status === 401) { location.href = "login.php"; throw new Error("login"); }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    return j;
  }
  const q = (extra = {}) => new URLSearchParams({ device: S.device, ...extra }).toString();
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmt = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(d).replace("-", "\u2212");
  const ghz = (hz, d = 4) => hz ? (hz / 1e9).toFixed(d) : "—";
  const signed = (v, d = 1) => (v === null || v === undefined) ? "—" : (v > 0 ? "+" : "") + fmt(v, d);
  const tm = (iso, withDate) => {
    if (!iso) return "—";
    const d = new Date(iso);
    const opt = { hour: "2-digit", minute: "2-digit", second: "2-digit" };
    return withDate ? d.toLocaleString([], { month: "short", day: "numeric", ...opt }) : d.toLocaleTimeString([], opt);
  };
  const ago = (iso) => {
    if (!iso) return "—";
    const s = Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000));
    return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : tm(iso, true);
  };
  function klass(label) {
    if (!label) return "none";
    if (/hypo|dehyd/i.test(label)) return "hypo";
    if (/hyper|over/i.test(label)) return "hyper";
    return "eu";
  }
  function classify(s11) {
    if (s11 === null || s11 === undefined) return null;
    for (const b of S.bands) if (b.below_s11_db === undefined || b.below_s11_db === null || s11 < b.below_s11_db) return b.label;
    return S.bands.length ? S.bands[S.bands.length - 1].label : null;
  }
  const colorFor = (r) => r.quality && r.quality !== "good" ? css("--bad")
    : css("--" + klass(r.status || classify(r.s11_db)));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ------------------------------------------------------------------ init
  async function init() {
    S.info = await api("info.php");
    S.bands = S.info.bands || [];
    const devs = S.info.devices || [];
    const sel = $("device");
    sel.innerHTML = devs.map((d) => `<option value="${esc(d.device_id)}">${esc(d.name)}</option>`).join("");
    S.device = (devs[0] && devs[0].device_id) || "";
    sel.hidden = devs.length < 2;
    sel.onchange = () => { S.device = sel.value; S.lastSeq = null; refreshAll(); };
    const cloud = S.info.source === "cloud";
    $("source").textContent = cloud ? `Cloud · ${S.info.user || ""}` : "This device";
    $("logout").hidden = !cloud;
    $("controls").hidden = !S.info.controls;
    if (!devs.length) { $("status").textContent = "No devices yet"; return; }

    document.querySelectorAll("#range button").forEach((b) => b.onclick = () => {
      S.range = b.dataset.r; setOn("#range", b); loadReadings();
    });
    document.querySelectorAll("#metric button").forEach((b) => b.onclick = () => {
      S.metric = b.dataset.m; setOn("#metric", b); drawTrend();
    });
    document.querySelectorAll("[data-action]").forEach((b) => b.onclick = () => control(b.dataset.action, null, b));
    $("subject-form").onsubmit = (e) => { e.preventDefault(); control("subject", $("subject").value.trim()); };
    $("csv").onclick = (e) => { e.preventDefault(); location.href = "api/export.php?" + q({ range: S.range === "1h" || S.range === "6h" ? "24h" : S.range }); };
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { drawTrend(); drawSweep(S.lastSweep); });

    await refreshAll();
    setInterval(loadLatest, 5000);
    setInterval(loadAlerts, 10000);
    setInterval(loadSweep, 15000);
    setInterval(loadReadings, 30000);
  }
  const setOn = (sel, btn) => document.querySelectorAll(sel + " button").forEach((x) => x.classList.toggle("on", x === btn));
  const refreshAll = () => Promise.allSettled([loadLatest(), loadReadings(), loadSweep(), loadAlerts()]);

  // ------------------------------------------------------------------ latest + status
  async function loadLatest() {
    let j;
    try { j = await api("latest.php?" + q()); }
    catch (e) { setConn(false, "server unreachable"); return; }
    const st = j.status || {};
    const r = j.reading;
    setConn(j.online, j.online ? "online" : "offline");

    const offSkin = j.online && st.state === "no_contact";
    const label = !offSkin && r && r.quality === "good" ? r.status : null;
    const el = $("status");
    el.textContent = offSkin ? "Not on skin" : label || (r ? "Unreliable" : "Waiting for data");
    el.className = "status " + (offSkin ? "none" : klass(label));
    $("state-msg").textContent = j.online ? (st.message || "") : `Device offline — last heartbeat ${ago(S.info.devices.find((d) => d.device_id === S.device)?.last_seen)}`;

    const qual = $("quality");
    qual.textContent = r ? (r.quality || "").replace("_", " ") : "";
    qual.className = "chip " + (r && r.quality === "good" ? "good" : r ? "warn" : "");
    $("k-s11").textContent = fmt(r?.s11_db, 1);
    $("k-freq").textContent = ghz(r?.resonant_freq_hz);
    $("k-delta").textContent = signed(r?.delta_db);
    $("k-subject").textContent = r?.subject || st.subject || "—";
    $("k-time").textContent = ago(r?.measured_at);
    $("f-rl").textContent = r ? `${fmt(r.return_loss_db, 2)} dB` : "—";
    $("f-bw").textContent = r?.bandwidth_hz ? `${fmt(r.bandwidth_hz / 1e6, 1)} MHz / ${fmt(r.q_factor, 0)}` : "—";
    const b = st.baseline;
    $("f-base").textContent = b ? `${fmt(b.return_loss_db, 1)} dB (n=${b.n})` : "not set";
    $("f-cal").textContent = st.calibration || "—";
    $("f-outbox").textContent = st.outbox ?? "—";

    if (S.info.controls) {
      const cap = st.baseline_capture;
      $("baseline-info").textContent = cap ? `Capturing baseline… ${cap.have}/${cap.need} good readings`
        : b ? `Baseline for ${b.subject || "default"}: return loss ${fmt(b.return_loss_db, 2)} dB ± ${fmt(b.sd_db, 2)}`
        : "No baseline for this participant yet.";
      if (document.activeElement !== $("subject")) $("subject").value = st.subject || "";
      $("free-air-hint")?.remove();
      if (!st.free_air_recorded) $("baseline-info").insertAdjacentHTML("afterend",
        `<p id="free-air-hint" class="small" style="color:var(--hypo)">Record a free-air reference so the device can tell when the sensor is off the skin.</p>`);
    }

    const al = $("alert");
    if (st.active_alert && j.online) {
      al.hidden = false;
      al.className = "alert" + (st.active_alert === "check_contact" ? " warn" : "");
      $("alert-title").textContent = { dehydration: "Dehydration alert", hyperhydration: "Over-hydration alert",
                                       check_contact: "Check sensor" }[st.active_alert] || "Alert";
      $("alert-msg").textContent = st.active_alert_message || "";
    } else al.hidden = true;

    if (r && r.seq !== S.lastSeq) {
      const first = S.lastSeq === null;
      S.lastSeq = r.seq;
      if (!first) appendReading(r);
    }
  }
  function setConn(on, text) {
    const c = $("conn");
    c.textContent = text;
    c.className = "pill " + (on ? "on" : "off");
  }

  // ------------------------------------------------------------------ readings + trend
  async function loadReadings() {
    try {
      const j = await api("readings.php?" + q({ range: S.range }));
      S.readings = j.readings || [];
      S.bucketed = !!j.bucket_s;
      drawTrend(); drawTable();
    } catch (e) { console.warn(e); }
  }
  function appendReading(r) {
    if (S.bucketed) return;
    S.readings.push(r);
    drawTrend(); drawTable();
  }

  const bandPlugin = {
    id: "bands",
    beforeDatasetsDraw(chart) {
      if (S.metric !== "s11_db" && S.metric !== "delta_db") return;
      const { ctx, chartArea: a, scales: { y } } = chart;
      ctx.save();
      if (S.metric === "s11_db") {
        let upper = y.max;
        const lims = S.bands.map((b) => b.below_s11_db).filter((v) => v !== undefined && v !== null);
        // bands are ordered from most negative S11 upwards
        const edges = [y.min, ...lims, y.max];
        S.bands.forEach((b, i) => {
          const lo = Math.max(edges[i], y.min), hi = Math.min(edges[i + 1], upper);
          if (hi <= lo) return;
          ctx.fillStyle = css("--band-" + klass(b.label));
          const top = y.getPixelForValue(hi), bot = y.getPixelForValue(lo);
          ctx.fillRect(a.left, top, a.right - a.left, bot - top);
        });
      } else {
        const t = S.info.alert_delta_db || 3;
        const top = y.getPixelForValue(Math.min(y.max, Math.max(y.min, t)));
        ctx.fillStyle = css("--band-hypo");
        ctx.fillRect(a.left, a.top, a.right - a.left, top - a.top);
      }
      ctx.restore();
    },
  };

  function drawTrend() {
    const m = S.metric;
    const rows = S.readings.filter((r) => r[m] !== null && r[m] !== undefined);
    const scale = m === "resonant_freq_hz" ? 1e-9 : 1;
    const data = rows.map((r) => ({ x: new Date(r.measured_at).getTime(), y: r[m] * scale, r }));
    const yTitle = { s11_db: "S11 at resonance (dB)", delta_db: "Drier than baseline (dB)", resonant_freq_hz: "Resonant frequency (GHz)" }[m];
    const grid = css("--grid"), muted = css("--muted");
    const spanH = data.length ? (data[data.length - 1].x - data[0].x) / 3.6e6 : 0;
    const cfg = {
      type: "line",
      data: { datasets: [{
        data, parsing: false, borderColor: css("--muted"), borderWidth: 1.25, tension: 0.25,
        pointRadius: data.length > 600 ? 1.5 : 3, pointHoverRadius: 6,
        pointBackgroundColor: data.map((p) => colorFor(p.r)), pointBorderWidth: 0,
        segment: { borderColor: (c) => colorFor(c.p1.raw.r) + "99" },
        spanGaps: S.bucketed ? 3.6e6 : 120000,
      }] },
      options: {
        animation: false, maintainAspectRatio: false, interaction: { mode: "nearest", intersect: false },
        scales: {
          x: { type: "linear", grid: { color: grid }, ticks: { color: muted, maxTicksLimit: 7,
               callback: (v) => spanH > 30 ? new Date(v).toLocaleDateString([], { month: "short", day: "numeric" })
                 : new Date(v).toLocaleTimeString([], spanH < 0.25 ? { hour: "2-digit", minute: "2-digit", second: "2-digit" }
                                                                   : { hour: "2-digit", minute: "2-digit" }) } },
          y: { title: { display: true, text: yTitle, color: muted }, grid: { color: grid }, ticks: { color: muted },
               reverse: false, grace: "10%" },
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            title: (it) => tm(new Date(it[0].raw.x).toISOString(), true),
            label: (it) => {
              const r = it.raw.r;
              const st = r.status || classify(r.s11_db) || r.quality;
              return [`${st}`, `S11 ${fmt(r.s11_db, 2)} dB · ${ghz(r.resonant_freq_hz)} GHz`,
                      r.delta_db !== null && r.delta_db !== undefined ? `vs. baseline ${signed(r.delta_db, 2)} dB` : ""].filter(Boolean);
            } } },
        },
      },
      plugins: [bandPlugin],
    };
    if (S.trend) S.trend.destroy();
    S.trend = new Chart($("trend"), cfg);
  }

  function drawTable() {
    const rows = S.readings.slice(-25).reverse();
    $("rows").innerHTML = rows.length ? rows.map((r) => {
      const st = r.status || (S.bucketed ? classify(r.s11_db) : null);
      return `<tr><td>${tm(r.measured_at, true)}</td><td>${esc(r.subject || "")}</td>
        <td>${st ? `<span class="tag ${klass(st)}">${esc(st)}</span>` : "—"}</td>
        <td class="num">${fmt(r.s11_db, 2)}</td><td class="num">${ghz(r.resonant_freq_hz)}</td>
        <td class="num">${signed(r.delta_db, 2)}</td><td>${esc((r.quality || "").replace("_", " "))}${S.bucketed ? ` (avg of ${r.n})` : ""}</td></tr>`;
    }).join("") : `<tr><td colspan="7" class="muted">No readings in this time range.</td></tr>`;
  }

  // ------------------------------------------------------------------ sweep
  async function loadSweep() {
    try { const j = await api("sweep.php?" + q()); S.lastSweep = j.sweep; drawSweep(j.sweep); }
    catch (e) { console.warn(e); }
  }
  function drawSweep(sw) {
    if (!sw) { $("sweep-time").textContent = "no sweep yet"; return; }
    $("sweep-time").textContent = tm(sw.measured_at, true);
    const n = sw.s11_db.length, step = (sw.stop_hz - sw.start_hz) / (n - 1);
    const pts = sw.s11_db.map((v, i) => ({ x: (sw.start_hz + i * step) / 1e9, y: v }));
    let min = pts[0];
    for (const p of pts) if (p.x >= 2.0 && p.x <= 2.5 && p.y < min.y) min = p;
    const grid = css("--grid"), muted = css("--muted");
    const lims = S.bands.map((b) => b.below_s11_db).filter((v) => v !== undefined && v !== null);
    const cfg = {
      type: "line",
      data: { datasets: [
        { data: pts, parsing: false, borderColor: css("--accent"), borderWidth: 2, pointRadius: 0, tension: 0.2 },
        ...lims.map((v) => ({ data: [{ x: pts[0].x, y: v }, { x: pts[n - 1].x, y: v }], parsing: false,
          borderColor: muted, borderDash: [5, 4], borderWidth: 1, pointRadius: 0 })),
        { data: [min], parsing: false, pointRadius: 5, pointBackgroundColor: css("--" + klass(classify(min.y))), showLine: false },
      ] },
      options: {
        animation: false, maintainAspectRatio: false,
        scales: {
          x: { type: "linear", title: { display: true, text: "Frequency (GHz)", color: muted }, grid: { color: grid }, ticks: { color: muted } },
          y: { title: { display: true, text: "S11 (dB)", color: muted }, grid: { color: grid }, ticks: { color: muted } },
        },
        plugins: { legend: { display: false }, tooltip: { callbacks: {
          label: (it) => `${it.raw.x.toFixed(3)} GHz: ${it.raw.y.toFixed(2)} dB` } } },
      },
    };
    if (S.sweep) S.sweep.destroy();
    S.sweep = new Chart($("sweep"), cfg);
  }

  // ------------------------------------------------------------------ alerts + controls
  async function loadAlerts() {
    try {
      const j = await api("alerts.php?" + q());
      const a = j.alerts || [];
      $("alerts").innerHTML = a.length ? a.map((x) => `<li><time>${tm(x.created_at, true)}</time>
        <span class="ev ${esc(x.event)}">${esc(x.event)}${x.subject ? " · " + esc(x.subject) : ""}</span>
        <span>${esc(x.message)}</span></li>`).join("") : `<li class="muted">No alerts yet.</li>`;
    } catch (e) { console.warn(e); }
  }
  async function control(action, value, btn) {
    if (action === "clear_baseline" && !confirmInline(btn)) return;
    try {
      if (btn) btn.disabled = true;
      await api("control.php", { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify({ action, value }) });
      setTimeout(loadLatest, 400);
    } catch (e) { $("baseline-info").textContent = "Error: " + e.message; }
    finally { if (btn) setTimeout(() => btn.disabled = false, 800); }
  }
  // two-tap confirmation (no blocking browser dialogs on the kiosk)
  function confirmInline(btn) {
    if (btn.dataset.armed) { delete btn.dataset.armed; btn.textContent = "Clear baseline"; return true; }
    btn.dataset.armed = "1"; btn.textContent = "Tap again to clear";
    setTimeout(() => { delete btn.dataset.armed; btn.textContent = "Clear baseline"; }, 3000);
    return false;
  }

  init().catch((e) => { if (e.message !== "login") { $("status").textContent = "Cannot load"; $("state-msg").textContent = e.message; } });
})();
