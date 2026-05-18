const { useState, useEffect, useRef } = React;

// ── helpers ───────────────────────────────────────────────────────────────────
const pct        = (v) => (Number(v) * 100).toFixed(1) + "%";
const riskTier   = (s) => s >= 0.75 ? "critical" : s >= 0.40 ? "high" : "medium";
const scoreColor = (v) => v >= 0.75 ? "#dc2626" : v >= 0.40 ? "#d97706" : "#059669";
const scoreGrad  = (v) => v >= 0.75
  ? "linear-gradient(90deg,#dc2626,#ef4444)"
  : v >= 0.40
  ? "linear-gradient(90deg,#d97706,#f59e0b)"
  : "linear-gradient(90deg,#059669,#10b981)";

const TIER = {
  critical: { label: "Critical", dot: "#dc2626", text: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
  high:     { label: "High",     dot: "#d97706", text: "#b45309", bg: "#fffbeb", border: "#fcd34d" },
  medium:   { label: "Medium",   dot: "#059669", text: "#047857", bg: "#f0fdf4", border: "#6ee7b7" },
};
const TIER_DARK = {
  critical: { label: "Critical", dot: "#f87171", text: "#f87171", bg: "#1f1010", border: "#7f1d1d" },
  high:     { label: "High",     dot: "#fbbf24", text: "#fbbf24", bg: "#1c1500", border: "#78350f" },
  medium:   { label: "Medium",   dot: "#34d399", text: "#34d399", bg: "#021c12", border: "#064e3b" },
};

const TABS = [["overview","Overview"],["timeline","Timeline"],["flags","Flags"],["shap","SHAP"]];

// ── theme ─────────────────────────────────────────────────────────────────────
function getInitialDark() {
  const stored = localStorage.getItem("ueba-theme");
  if (stored) return stored === "dark";
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}
function applyTheme(dark) {
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  localStorage.setItem("ueba-theme", dark ? "dark" : "light");
}

// ── data fetching ─────────────────────────────────────────────────────────────
function useApi(url) {
  const [data, setData]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  useEffect(() => {
    setLoading(true);
    fetch(url)
      .then((r) => { if (!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); })
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [url]);
  return { data, loading, error };
}

// ── small components ──────────────────────────────────────────────────────────
function StatCard({ label, value, cls, accent }) {
  return (
    <div className={`scard ${accent}`}>
      <div className="slbl">{label}</div>
      <div className={`sval ${cls}`}>{value}</div>
    </div>
  );
}

function ScoreBar({ label, sub, value }) {
  return (
    <div className="srow">
      <div className="smeta">
        <div>
          <span className="slb2">{label}</span>
          {sub && <div className="ssub">{sub}</div>}
        </div>
        <span className="snum">{pct(value)}</span>
      </div>
      <div className="strk">
        <div className="sfil" style={{ width: (value * 100) + "%", background: scoreGrad(value) }} />
      </div>
    </div>
  );
}

// ── theme toggle button ───────────────────────────────────────────────────────
function ThemeToggle({ dark, onToggle }) {
  return (
    <button className="theme-toggle" onClick={onToggle} title={dark ? "Switch to light mode" : "Switch to dark mode"}>
      {dark ? "☀" : "☾"}
    </button>
  );
}

// ── timeline chart ────────────────────────────────────────────────────────────
function TimelineChart({ daily, sel, dark }) {
  const ref  = useRef(null);
  const inst = useRef(null);

  useEffect(() => {
    if (!ref.current || !daily.length) return;
    if (inst.current) inst.current.destroy();

    const rows     = [...daily].sort((a, b) => new Date(a.date) - new Date(b.date));
    const gridCol  = dark ? "#272d3d" : "#f1f5f9";
    const tickCol  = dark ? "#3d4a5c" : "#94a3b8";
    const ttBg     = dark ? "#181c25" : "#ffffff";
    const ttBorder = dark ? "#272d3d" : "#e2e8f0";
    const ttBody   = dark ? "#e2e8f0" : "#1e293b";
    const ttTitle  = dark ? "#64748b" : "#64748b";

    inst.current = new Chart(ref.current, {
      type: "line",
      data: {
        labels: rows.map((d) => d.date.slice(5)),
        datasets: [
          {
            label: "Combined",
            data: rows.map((d) => +(d.combined_risk_score * 100).toFixed(1)),
            borderColor: "#dc2626", backgroundColor: "rgba(220,38,38,0.06)",
            fill: true, tension: 0.35, borderWidth: 2,
            pointRadius: rows.map((d) => d.above_threshold ? 7 : 2),
            pointBackgroundColor: rows.map((d) => d.above_threshold ? "#dc2626" : "#ef4444"),
            pointBorderColor: rows.map((d) => d.above_threshold ? "rgba(220,38,38,0.25)" : "transparent"),
            pointBorderWidth: rows.map((d) => d.above_threshold ? 5 : 0),
          },
          {
            label: "IsoForest",
            data: rows.map((d) => +(d.iso_score_norm * 100).toFixed(1)),
            borderColor: "#6366f1", borderDash: [6, 3], tension: 0.35,
            fill: false, borderWidth: 1.5, pointRadius: 0,
          },
          {
            label: "Elliptic Env",
            data: rows.map((d) => +(d.lof_score_norm * 100).toFixed(1)),
            borderColor: "#059669", borderDash: [2, 4], tension: 0.35,
            fill: false, borderWidth: 1.5, pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: "index", intersect: false,
            backgroundColor: ttBg, borderColor: ttBorder, borderWidth: 1,
            titleColor: ttTitle, bodyColor: ttBody,
            titleFont: { family: "system-ui" }, bodyFont: { family: "system-ui", size: 11 },
          },
        },
        scales: {
          x: { grid: { color: gridCol }, ticks: { color: tickCol, font: { family: "system-ui", size: 10 }, maxTicksLimit: 10 } },
          y: { min: 0, max: 100, grid: { color: gridCol }, ticks: { color: tickCol, font: { family: "system-ui", size: 10 }, callback: (v) => v + "%" } },
        },
      },
    });
  }, [daily, sel, dark]);

  return <canvas ref={ref} aria-label={`Risk timeline for ${sel}`} />;
}

// ── shap chart ────────────────────────────────────────────────────────────────
function ShapChart({ shap, dark }) {
  const ref  = useRef(null);
  const inst = useRef(null);

  useEffect(() => {
    if (!ref.current || !shap.length) return;
    if (inst.current) inst.current.destroy();

    const latest   = shap[shap.length - 1];
    const feats    = [
      "usb_after_hours_flag","usb_count","job_site_visits_flag","logon_count_zscore",
      "weekend_session_flag","after_hours_session_count","usb_device_diversity_monthly",
      "job_search_plus_usb_week","logon_count_zscore_has_baseline",
    ];
    const vals     = feats.map((f) => +((latest[f] || 0) * 100).toFixed(3));
    const gridCol  = dark ? "#272d3d" : "#f1f5f9";
    const tickCol  = dark ? "#3d4a5c" : "#94a3b8";
    const tickCol2 = dark ? "#94a3b8" : "#475569";
    const ttBg     = dark ? "#181c25" : "#ffffff";
    const ttBorder = dark ? "#272d3d" : "#e2e8f0";
    const ttBody   = dark ? "#e2e8f0" : "#1e293b";

    inst.current = new Chart(ref.current, {
      type: "bar",
      data: {
        labels: feats.map((f) => f.replace(/_/g, " ")),
        datasets: [{
          data: vals,
          backgroundColor: vals.map((v) => v > 0 ? "rgba(220,38,38,0.7)" : "rgba(99,102,241,0.7)"),
          borderRadius: 3, borderWidth: 0,
        }],
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: ttBg, borderColor: ttBorder, borderWidth: 1,
            bodyColor: ttBody, bodyFont: { family: "system-ui", size: 11 },
            callbacks: { label: (ctx) => " " + ctx.parsed.x.toFixed(4) },
          },
        },
        scales: {
          x: { grid: { color: gridCol }, ticks: { color: tickCol, font: { family: "system-ui", size: 10 }, callback: (v) => v.toFixed(1) } },
          y: { grid: { display: false }, ticks: { color: tickCol2, font: { family: "system-ui", size: 10 } } },
        },
      },
    });
  }, [shap, dark]);

  return <canvas ref={ref} aria-label="SHAP feature attribution" />;
}


// ── stepper input ─────────────────────────────────────────────────────────────
function Stepper({ value, onChange, min, max, step = 1 }) {
  const dec = () => onChange(Math.max(min ?? -Infinity, value - step));
  const inc = () => onChange(Math.min(max ??  Infinity, value + step));
  return (
    <div className="stepper">
      <button className="stepper-btn" onClick={dec}>−</button>
      <span className="stepper-val">{value}</span>
      <button className="stepper-btn" onClick={inc}>+</button>
    </div>
  );
}

// ── settings panel ────────────────────────────────────────────────────────────
function SettingsPanel({ onClose, onDone, dark }) {
  const [synthCfg, setSynthCfg] = React.useState({
    n_normal_users: 27, n_insider_users: 3, n_days: 90,
    normal_phase_days: 20, phased: true, random_scenarios: true,
  });
  const [inferCfg, setInferCfg] = React.useState({
    threshold: 0.3793,
  });
  const [running, setRunning] = React.useState(null); // 'synthetic' | 'inference' | null
  const [log, setLog]         = React.useState(null); // {ok, text}

  const run = async (endpoint, cfg) => {
    setRunning(endpoint);
    setLog(null);
    try {
      const r = await fetch(`/api/run/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      });
      const d = await r.json();
      setLog({ ok: d.ok, text: d.ok ? '✓ Done' : (d.output || 'Error') });
      if (d.ok) onDone();
    } catch(e) {
      setLog({ ok: false, text: String(e) });
    }
    setRunning(null);
  };



  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={e => e.stopPropagation()}>
        <div className="settings-hdr">
          <span className="settings-title">Pipeline settings</span>
          <button className="settings-close" onClick={onClose}>✕</button>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">Synthetic population</div>
          <div className="settings-row">
            <label>Normal users</label>
            <Stepper value={synthCfg.n_normal_users} min={1} max={100}
              onChange={v => setSynthCfg(p => ({...p, n_normal_users: v}))} />
          </div>
          <div className="settings-row">
            <label>Insider users</label>
            <Stepper value={synthCfg.n_insider_users} min={1} max={20}
              onChange={v => setSynthCfg(p => ({...p, n_insider_users: v}))} />
          </div>
          <div className="settings-row">
            <label>Days per user</label>
            <Stepper value={synthCfg.n_days} min={10} max={365}
              onChange={v => setSynthCfg(p => ({...p, n_days: v}))} />
          </div>
          <div className="settings-row">
            <label>Normal phase days</label>
            <Stepper value={synthCfg.normal_phase_days} min={1} max={synthCfg.n_days - 1}
              onChange={v => setSynthCfg(p => ({...p, normal_phase_days: v}))} />
          </div>
          <div className="settings-row">
            <label>Phased behavior</label>
            <input type="checkbox" checked={synthCfg.phased}
              onChange={e => setSynthCfg(p => ({...p, phased: e.target.checked}))} />
          </div>
          <div className="settings-row">
            <label>Random scenarios</label>
            <input type="checkbox" checked={synthCfg.random_scenarios}
              onChange={e => setSynthCfg(p => ({...p, random_scenarios: e.target.checked}))} />
          </div>
          <button className="settings-run" disabled={running === 'synthetic'}
            onClick={() => run('synthetic', synthCfg)}>
            {running === 'synthetic' ? 'Running…' : 'Run synthetic generator'}
          </button>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">Inference</div>
          <div className="settings-row">
            <label>Alert threshold</label>
            <Stepper value={inferCfg.threshold} min={0.1} max={0.99} step={0.01}
              onChange={v => setInferCfg({ threshold: +v.toFixed(4) })} />
          </div>
          <div className="settings-note">Unsupervised score above which a day is flagged as anomalous. p99 of synthetic normals = 0.3793.</div>
          <button className="settings-run" disabled={running === 'inference'}
            onClick={() => run('inference', inferCfg)}>
            {running === 'inference' ? 'Running…' : 'Run inference'}
          </button>
        </div>

        {log && (
          <div className={`settings-log ${log.ok ? 'ok' : 'err'}`}>{log.text}</div>
        )}
      </div>
    </div>
  );
}

// ── main app ──────────────────────────────────────────────────────────────────
function App() {
  const { data: usersData, loading: uL, error: uE } = useApi("/api/users");
  const { data: dailyAll,  loading: dL, error: dE } = useApi("/api/daily");
  const { data: shapAll,   loading: sL, error: sE } = useApi("/api/shap");

  const [sel, setSel]   = useState(null);
  const [tab, setTab]   = useState("overview");
  const [dark, setDark] = useState(getInitialDark);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => { applyTheme(dark); }, [dark]);
  const reloadData = () => {
    // Force re-fetch by reloading the page
    window.location.reload();
  };
  const toggleTheme = () => setDark((d) => !d);

  useEffect(() => {
    if (usersData.length && !sel) setSel(usersData[0].user);
  }, [usersData]);

  const loading  = uL || dL || sL;
  const error    = uE || dE || sE;
  const sortedUsers = [...usersData].sort((a, b) =>
    (b.unsupervised_mean ?? b.unsupervised_max ?? 0) - (a.unsupervised_mean ?? a.unsupervised_max ?? 0)
  );
  const user     = usersData.find((u) => u.user === sel);
  const daily    = dailyAll.filter((d) => d.user === sel);
  const shap     = shapAll.filter((d) => d.user === sel);
  const tier     = user ? riskTier(user.unsupervised_mean ?? user.unsupervised_max) : "medium";
  const T        = dark ? TIER_DARK[tier] : TIER[tier];
  const flagged  = daily.filter((d) => d.above_threshold).length;
  const breaches = daily.filter((d) => d.above_threshold).map((d) => d.date.slice(5)).slice(-3);

  if (loading) return (
    <div className="loading">
      <div className="loading-spinner" />
      <span>Loading pipeline data…</span>
    </div>
  );

  if (error) return (
    <div className="error-state">
      <div className="error-icon">⚠</div>
      <div className="error-title">Could not reach the API</div>
      <div className="error-msg">{error}</div>
      <div className="error-hint">Make sure <code>api.py</code> is running on port 5000.</div>
    </div>
  );

  return (
    <div className="dash">

      {/* header */}
      <div className="hdr">
        <div className="hdr-left">
          <div className="logo-wrap">
            <svg className="logo" width="40" height="40" viewBox="0 0 314 314" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="314.002" height="314.002" rx="51.6556" fill="currentColor" className="logo-bg"/>
              <path fillRule="evenodd" clipRule="evenodd" d="M132.585 66.8996C127.563 71.9211 124.16 79.8274 124.16 91.3166C124.16 105.462 128.928 119.787 136.005 130.402C143.401 141.495 151.466 146.054 157.002 146.054C162.538 146.054 170.603 141.495 177.998 130.402C185.075 119.787 189.844 105.462 189.844 91.3166C189.844 79.8274 186.44 71.9211 181.419 66.8996C176.397 61.8781 168.491 58.4744 157.002 58.4744C145.513 58.4744 137.606 61.8781 132.585 66.8996ZM190.885 149.639C192.809 147.369 194.59 144.985 196.216 142.547C205.56 128.531 211.739 110.014 211.739 91.3166C211.739 75.4373 206.932 61.4489 196.901 51.4176C186.869 41.3864 172.881 36.5796 157.002 36.5796C141.122 36.5796 127.134 41.3864 117.103 51.4176C107.072 61.4489 102.265 75.4373 102.265 91.3166C102.265 110.014 108.443 128.531 117.788 142.547C119.413 144.985 121.194 147.369 123.118 149.639C111.253 152.128 99.2161 156.021 88.3419 161.646C66.307 173.044 47.5313 192.559 47.5309 222.685C47.5309 222.684 47.5309 222.685 47.5309 222.685L47.5293 244.578C47.5279 262.717 62.2323 277.423 80.3715 277.423H178.897C184.943 277.423 189.844 272.521 189.844 266.475C189.844 260.429 184.943 255.528 178.897 255.528H80.3715C74.3251 255.528 69.4237 250.626 69.4241 244.579L69.4257 222.686C69.4257 203.549 80.7536 190.222 98.4012 181.093C116.285 171.842 139.076 167.948 157.002 167.948C179.408 167.948 208.582 173.987 226.913 188.243C231.686 191.955 238.564 191.094 242.275 186.322C245.987 181.549 245.127 174.671 240.354 170.959C226.292 160.023 208.347 153.301 190.885 149.639ZM214.945 214.945C219.22 210.669 226.152 210.669 230.427 214.945L244.581 229.098L258.735 214.945C263.01 210.669 269.942 210.669 274.217 214.945C278.492 219.22 278.492 226.151 274.217 230.426L260.063 244.58L274.216 258.734C278.492 263.009 278.492 269.941 274.216 274.216C269.941 278.491 263.01 278.491 258.734 274.216L244.581 260.062L230.428 274.216C226.152 278.491 219.221 278.491 214.946 274.216C210.67 269.941 210.67 263.009 214.946 258.734L229.099 244.58L214.945 230.426C210.67 226.151 210.67 219.22 214.945 214.945Z" fill="var(--logo-icon)"/>
            </svg>
            <div>
              <div className="brand-name">ITDer</div>
              <div className="sub mono">{usersData.length} users · {dailyAll.length} records · local pipeline</div>
            </div>
          </div>
        </div>
        <div className="hdr-right">
          <div className="hdr-controls">
            <button className="settings-btn" onClick={() => setShowSettings(true)} title="Pipeline settings">⚙</button>
            <ThemeToggle dark={dark} onToggle={toggleTheme} />
          </div>
          <select
            className="usr-sel"
            value={sel || ""}
            onChange={(e) => { setSel(e.target.value); setTab("overview"); }}
          >
            {sortedUsers.map((u, i) => (
              <option key={u.user} value={u.user}>
                #{i + 1} {u.user}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* stat cards */}
      {user && (
        <div className="stats">
          <StatCard label="Rank"             value={`#${sortedUsers.findIndex(u => u.user === sel) + 1} of ${usersData.length}`}                  cls={user.rank <= 3 ? "r" : user.rank <= 10 ? "a" : "g"} accent="r" />
          <StatCard label="Anomaly signal"   value={pct(user.unsupervised_mean ?? user.unsupervised_max)}     cls={tier === "critical" ? "r" : tier === "high" ? "a" : "g"} accent="a" />
          <StatCard label="ISO anomalies"    value={user.days_flagged_iso}        cls={user.days_flagged_iso > 5 ? "r" : user.days_flagged_iso > 0 ? "a" : "g"} accent="b" />
          <StatCard label="EE anomalies"     value={user.days_flagged_lof}        cls={user.days_flagged_lof > 5 ? "r" : user.days_flagged_lof > 0 ? "a" : "g"} accent="b" />
          <StatCard label="Both flagged"     value={user.days_flagged_both}       cls={user.days_flagged_both > 0 ? "r" : "g"} accent="r" />
          <StatCard label="Days monitored"   value={user.total_days}              cls="m" accent="b" />
        </div>
      )}

      {/* identity bar — no blinking dot */}
      {user && (
        <div className="ibar">
          <div className="av" style={{ background: T.bg, border: `1px solid ${T.border}`, color: T.text }}>
            {user.user.slice(0, 2).toUpperCase()}
          </div>
          <div style={{ flex: 1 }}>
            <div className="iname">{user.user}</div>
            <div className="imeta">rank #{sortedUsers.findIndex(u => u.user === sel) + 1} · {user.is_synthetic ? "synthetic" : "real user"} · peak {user.peak_date}</div>
          </div>

        </div>
      )}

      {/* tabs */}
      <div className="tabs">
        {TABS.map(([id, lbl]) => (
          <button key={id} className={`tb${tab === id ? " on" : ""}`} onClick={() => setTab(id)}>
            {lbl}
          </button>
        ))}
      </div>

      {/* overview */}
      {tab === "overview" && user && (
        <div className="two">
          <div className="panel">
            <div className="ptitle">Risk leaderboard — {usersData.length} users</div>
            <div className="lb-scroll">
              {sortedUsers.map((u, i) => (
                <div
                  key={u.user}
                  className={`lbrow${u.user === sel ? " sel" : ""}`}
                  onClick={() => setSel(u.user)}
                >
                  <span className="lbrnk">{i + 1}</span>
                  <span className="lbnm">{u.user}</span>
                  <div className="lbtrack">
                    <div className="lbfill" style={{ width: ((u.unsupervised_mean ?? u.unsupervised_max) * 100) + "%", background: scoreGrad(u.unsupervised_mean ?? u.unsupervised_max) }} />
                  </div>
                  <span className="lbdays" style={{ color: u.days_flagged_both > 0 ? scoreColor(u.unsupervised_mean ?? u.unsupervised_max) : "var(--text-4)" }}>
                    {u.days_flagged_both > 0 ? `${u.days_flagged_both}d` : "—"}
                  </span>
                  <span className="lbsc" style={{ color: scoreColor(u.unsupervised_mean ?? u.unsupervised_max) }}>
                    {((u.unsupervised_mean ?? u.unsupervised_max) * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="ptitle">Score breakdown — {user.user}</div>
            <ScoreBar label="Avg anomaly signal"  sub="Mean combined score across all days — matches leaderboard %"   value={user.unsupervised_mean ?? user.unsupervised_max} />
            <ScoreBar label="IsoForest mean"      sub="Avg IsoForest isolation score — how separated from population"  value={user.iso_score_norm_mean ?? 0} />
            <ScoreBar label="Elliptic Env mean"   sub="Avg EE score — distance from normal cluster"                    value={user.lof_score_norm_mean ?? 0} />

            <div className="ptitle" style={{ marginTop: 20 }}>Anomaly detection</div>
            <div className="anogrid">
              {[
                ["Days flagged", user.days_above_threshold, "var(--red)"],
                ["ISO flagged",  user.days_flagged_iso,     "var(--accent)"],
                ["EE flagged",   user.days_flagged_lof,     "var(--green)"],
                ["Both flagged", user.days_flagged_both,    "var(--red)"],
              ].map(([lbl, val, col]) => (
                <div className="anocell" key={lbl}>
                  <div className="anonum" style={{ color: col }}>{val}</div>
                  <div className="anolbl">{lbl}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* timeline */}
      {tab === "timeline" && (
        <div className="panel">
          <div className="panel-hdr">
            <div className="ptitle" style={{ margin: 0 }}>Daily risk score — {sel}</div>
            <div className="legend">
              {[["Combined","#dc2626","solid"],["IsoForest","#6366f1","dashed"],["Elliptic Env","#059669","dotted"]].map(([lbl, col, sty]) => (
                <span key={lbl} className="legitem">
                  <span className="legline" style={sty === "solid" ? { background: col } : { background: "none", border: `1.5px ${sty} ${col}` }} />
                  {lbl}
                </span>
              ))}
              <span className="legitem">
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#dc2626", display: "inline-block" }} />
                Threshold breach
              </span>
            </div>
          </div>
          <div style={{ position: "relative", width: "100%", height: 260 }}>
            <TimelineChart daily={daily} sel={sel} dark={dark} />
          </div>
        </div>
      )}

      {/* flags table */}
      {tab === "flags" && (
        <div className="panel">
          <div className="panel-hdr">
            <div className="ptitle" style={{ margin: 0 }}>Behavioral flags — {sel}</div>
            <div className="legend">
              <span className="legitem"><span className="flag-pill pill-red">ANOM</span> Anomaly detected</span>
              <span className="legitem"><span className="bdot" style={{ background: "var(--red)" }} /> Above threshold</span>
            </div>
          </div>
          <div className="sx" style={{ marginTop: 14 }}>
            <table className="ftable">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Risk score</th>
                  <th>After-hours sessions</th>
                  <th>USB devices</th>
                  <th>USB after-hours</th>
                  <th>Job site visit</th>
                  <th>Weekend session</th>
                  <th>IsoForest</th>
                  <th>Elliptic Env</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {[...daily].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 20).map((row) => {
                  const isBreech = +row.above_threshold === 1;
                  const isoAnom  = +row.iso_prediction === -1;
                  const lofAnom  = +row.lof_prediction === -1;
                  return (
                    <tr key={row.date} className={isBreech ? "ar" : ""}>
                      <td className="f-date">{row.date.slice(5)}</td>
                      <td><span className="f-risk" style={{ color: scoreColor(row.combined_risk_score) }}>{pct(row.combined_risk_score)}</span></td>
                      <td className={+row.after_hours_session_count > 0 ? "f-val-hi" : "f-val"}>{row.after_hours_session_count}</td>
                      <td className={+row.usb_count > 0 ? "f-val-hi" : "f-val"}>{row.usb_count}</td>
                      <td>{+row.usb_after_hours_flag ? <span className="flag-pill pill-red">YES</span> : <span className="f-nil">—</span>}</td>
                      <td>{+row.job_site_visits_flag ? <span className="flag-pill pill-amber">YES</span> : <span className="f-nil">—</span>}</td>
                      <td>{+row.weekend_session_flag ? <span className="flag-pill pill-amber">YES</span> : <span className="f-nil">—</span>}</td>
                      <td>{isoAnom ? <span className="flag-pill pill-red">ANOM</span> : <span className="f-nil">—</span>}</td>
                      <td>{lofAnom ? <span className="flag-pill pill-red">ANOM</span> : <span className="f-nil">—</span>}</td>
                      <td>{isBreech ? <span className="bdot" /> : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* shap */}
      {tab === "shap" && (
        <div className="panel">
          <div className="panel-hdr" style={{ marginBottom: 14 }}>
            <div className="ptitle" style={{ margin: 0 }}>
              Feature attribution (SHAP) — {shap.length ? shap[shap.length - 1].date : "n/a"}
            </div>
            <div className="legend">
              <span className="legitem">
                <span style={{ width: 10, height: 10, borderRadius: 2, background: "rgba(220,38,38,0.7)", display: "inline-block" }} />
                Increases risk
              </span>
              <span className="legitem">
                <span style={{ width: 10, height: 10, borderRadius: 2, background: "rgba(99,102,241,0.7)", display: "inline-block" }} />
                Decreases risk
              </span>
            </div>
          </div>
          {shap.length ? (
            <div style={{ position: "relative", width: "100%", height: 300 }}>
              <ShapChart shap={shap} dark={dark} />
            </div>
          ) : (
            <p className="empty-msg">No SHAP data for this user.</p>
          )}
          <div className="snote">
            SHAP values show each feature's marginal contribution to the supervised model output.
            Red = pushes score up · indigo = pushes down · showing most recent available date.
          </div>
        </div>
      )}

      {showSettings && (
        <SettingsPanel
          onClose={() => setShowSettings(false)}
          onDone={() => { setShowSettings(false); reloadData(); }}
          dark={dark}
        />
      )}
    </div>
  );
}

applyTheme(getInitialDark());
ReactDOM.createRoot(document.getElementById("root")).render(<App />);