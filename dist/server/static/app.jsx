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

const TABS = [["overview","Overview"],["timeline","Timeline"],["flags","Flags"],["shap","SHAP"],["info","Info"]];

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
function useApi(url, refresh = 0) {
  const [data, setData]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  useEffect(() => {
    setLoading(true);
    fetch(url, { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); })
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [url, refresh]);
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
            data: rows.map((d) => +(d.ee_score_norm * 100).toFixed(1)),
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
function SettingsPanel({ onClose, onDone, dark, showSynthetic, onToggleSynthetic, synthCfg, setSynthCfg, inferCfg, setInferCfg }) {
  const [running, setRunning]   = React.useState(null);
  const [log, setLog]           = React.useState(null);
  const [mode, setMode]         = React.useState('manual');   // 'manual' | 'scheduled'
  const [schedHour, setSchedHour]   = React.useState(2);
  const [schedMin, setSchedMin]     = React.useState(0);
  const [schedSaving, setSchedSaving] = React.useState(false);
  const [resetting, setResetting] = React.useState(false);
  const [saveLog, setSaveLog] = React.useState(null);

  // Load current schedule on open
  React.useEffect(() => {
    fetch('/api/settings')
      .then(r => r.json())
      .then(d => {
        if (d.schedule_enabled) {
          setMode('scheduled');
          // Parse hour/minute from cron if possible
          const cronParts = (d.schedule_cron || "0 2 * * *").split(' ');
          if (cronParts.length >= 2) {
            setSchedMin(parseInt(cronParts[0]) || 0);
            setSchedHour(parseInt(cronParts[1]) || 2);
          }
        }
      })
      .catch(() => {});
  }, []);

  const run = async (endpoint) => {
    setRunning(endpoint);
    setResetting(false);
    setLog(null);
    try {
      // First, save the current configuration to the database
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          schedule_enabled: mode === 'scheduled',
          schedule_cron: `${schedMin} ${schedHour} * * *`,
          synthCfg: synthCfg,
          inferCfg: inferCfg
        }),
      });

      const payload = { ...inferCfg, ...synthCfg };
      const r = await fetch(`/api/run/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!d.ok) {
        setRunning(null);
        setLog({ ok: false, text: d.output || 'Error' });
        return;
      }
      
      const evt = new EventSource('/api/status_stream');
      evt.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.pipeline_status === 'success') {
            evt.close();
            setRunning(null);
            setLog({ ok: true, text: '✓ Done' });
            onDone();
          } else if (data.pipeline_status === 'failed') {
            evt.close();
            setRunning(null);
            setLog({ ok: false, text: 'Pipeline failed' });
          }
        } catch(err) {}
      };
      evt.onerror = () => {
        evt.close();
        setRunning(null);
        setLog({ ok: false, text: 'Stream error' });
      };
    } catch(e) {
      setRunning(null);
      setLog({ ok: false, text: String(e) });
    }
  };

  const saveSettings = async () => {
    setSchedSaving(true);
    setSaveLog(null);
    try {
      const r = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          schedule_enabled: mode === 'scheduled',
          schedule_cron: `${schedMin} ${schedHour} * * *`,
          synthCfg: synthCfg,
          inferCfg: inferCfg
        }),
      });
      const d = await r.json();
      setSaveLog({ ok: d.ok, text: d.ok ? '✓ Settings saved to database' : (d.error || 'Error saving settings') });
    } catch(e) {
      setSaveLog({ ok: false, text: String(e) });
    }
    setSchedSaving(false);
  };

  const padZ = (n) => String(n).padStart(2, '0');

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={e => e.stopPropagation()}>
        <div className="settings-hdr">
          <span className="settings-title">Pipeline settings</span>
          <button className="settings-close" onClick={onClose}>✕</button>
        </div>

        {/* ── inference trigger mode ── */}
        <div className="settings-section">
          <div className="settings-section-title">Inference trigger</div>
          <div className="settings-mode-toggle">
            <button
              className={`mode-btn${mode === 'manual' ? ' active' : ''}`}
              onClick={() => setMode('manual')}
            >Manual</button>
            <button
              className={`mode-btn${mode === 'scheduled' ? ' active' : ''}`}
              onClick={() => setMode('scheduled')}
            >Scheduled</button>
          </div>

          {mode === 'manual' && (
            <div style={{ marginTop: 12 }}>
              <div className="settings-row">
                <label>Alert threshold</label>
                <Stepper value={inferCfg.threshold} min={0.1} max={0.99} step={0.01}
                  onChange={v => setInferCfg({ threshold: +v.toFixed(4) })} />
              </div>
              <div className="settings-note">p99 of synthetic normals = 0.3793</div>
            </div>
          )}

          {mode === 'scheduled' && (
            <div style={{ marginTop: 12 }}>
              <div className="settings-note" style={{ marginBottom: 10 }}>
                Inference will run automatically at the specified time daily (UTC).
                Manual run button is disabled while scheduled mode is active.
              </div>
              <div className="settings-row">
                <label>Hour (UTC)</label>
                <Stepper value={schedHour} min={0} max={23}
                  onChange={v => setSchedHour(v)} />
              </div>
              <div className="settings-row">
                <label>Minute</label>
                <Stepper value={schedMin} min={0} max={59} step={1}
                  onChange={v => setSchedMin(v)} />
              </div>
              <div className="settings-note">
                Runs daily at {padZ(schedHour)}:{padZ(schedMin)} UTC
              </div>
              <button className="settings-run" disabled={schedSaving}
                onClick={saveSettings}>
                {schedSaving ? 'Saving…' : 'Save schedule'}
              </button>
              {saveLog && (
                <div className={`settings-log ${saveLog.ok ? 'ok' : 'err'}`} style={{ margin: '10px 0 0 0', boxSizing: 'border-box', textAlign: 'center' }}>
                  {saveLog.text}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── show synthetic toggle ── */}
        <div className="settings-section">
          <div className="settings-section-title">Display</div>
          <div className="settings-row">
            <label>Show synthetic users</label>
            <input type="checkbox" checked={showSynthetic}
              onChange={onToggleSynthetic} />
          </div>
          <div className="settings-note">
            Include synthetic background population in the leaderboard and charts.
          </div>
        </div>

        {/* ── synthetic population ── */}
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
        </div>

        <div className="settings-section" style={{ borderBottom: 'none' }}>
          <div className="settings-note" style={{ marginBottom: 15 }}>
            Running the pipeline will generate a fresh synthetic background population using your settings, and then re-evaluate all user risk scores against the new baseline and alert threshold.
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button className="settings-run" disabled={!!running || resetting}
              onClick={() => {
                setSynthCfg({ n_normal_users: 27, n_insider_users: 3, n_days: 90, normal_phase_days: 20, phased: true, random_scenarios: true });
                setInferCfg({ threshold: 0.3793 });
                setResetting(true);
              }}
              style={{ flex: 1, padding: '12px', fontSize: '14px', fontWeight: 'bold', background: resetting ? '#224422' : 'transparent', border: resetting ? '1px solid #44cc44' : '1px solid #4a4a5a', color: resetting ? '#44cc44' : '#a0a0b0', transition: 'all 0.2s' }}>
              {resetting ? '✓ Reset' : 'Reset Default'}
            </button>
            <button className="settings-run" disabled={!!running || mode === 'scheduled'}
              onClick={() => run('inference')}
              style={{ flex: 1.5, padding: '12px', fontSize: '14px', fontWeight: 'bold', opacity: mode === 'scheduled' ? 0.5 : 1 }}>
              {running ? 'Running…' : 'Save & Run Pipeline'}
            </button>
          </div>
        </div>

        {log && (
          <div className={`settings-log ${log.ok ? 'ok' : 'err'}`}>{log.text}</div>
        )}
      </div>
    </div>
  );
}

// ── empty state (get started) ─────────────────────────────────────────────────
function GetStarted({ dark, onSettingsClick, onDone }) {
  const [dbStatus, setDbStatus] = React.useState({ features_count: 0, has_data: false });
  const [running, setRunning] = React.useState(null); // null | 'synthetic' | 'inference'
  const [log, setLog] = React.useState(null);

  React.useEffect(() => {
    const evtSource = new EventSource('/api/status_stream');
    evtSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setDbStatus(data);
        if (data.pipeline_status === 'success' && running === 'processing') {
          onDone(); // Automatically exit GetStarted when processing finishes!
        } else if (data.users_count > 0 && !running) {
          onDone(); // For initial load if data already exists
        }
      } catch (err) {}
    };
    return () => evtSource.close();
  }, [onDone]);

  const handleGenerateAndProcess = async () => {
    setLog(null);
    try {
      setRunning('processing');
      const payload = {
        threshold: 0.3793,
        n_normal_users: 27, n_insider_users: 3, n_days: 90,
        normal_phase_days: 20, phased: true, random_scenarios: true
      };
      let r = await fetch('/api/run/synthetic', { 
        method: 'POST', 
        body: JSON.stringify(payload), 
        headers:{'Content-Type': 'application/json'} 
      });
      let d = await r.json();
      if (!d.ok) throw new Error(d.output || "Error in synthetic generation");

      // The backend worker triggers both synthetic generation and inference automatically,
      // and runs them asynchronously in a single background thread.
      // We DO NOT call onDone() manually here. Instead, we keep `running` as 'processing'.
      // The SSE stream will automatically detect when the worker finishes (data.users_count > 0)
      // and trigger onDone() for us!
    } catch(e) {
      setLog(String(e));
      setRunning(null);
    }
  };

  return (
    <div className="get-started-view">
      <div className="gs-content">
        <div className="logo-wrap" style={{ justifyContent: 'center', marginBottom: 20 }}>
          <svg className="logo" width="60" height="60" viewBox="0 0 314 314" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="314.002" height="314.002" rx="51.6556" fill="currentColor" className="logo-bg"/>
            <path fillRule="evenodd" clipRule="evenodd" d="M132.585 66.8996C127.563 71.9211 124.16 79.8274 124.16 91.3166C124.16 105.462 128.928 119.787 136.005 130.402C143.401 141.495 151.466 146.054 157.002 146.054C162.538 146.054 170.603 141.495 177.998 130.402C185.075 119.787 189.844 105.462 189.844 91.3166C189.844 79.8274 186.44 71.9211 181.419 66.8996C176.397 61.8781 168.491 58.4744 157.002 58.4744C145.513 58.4744 137.606 61.8781 132.585 66.8996ZM190.885 149.639C192.809 147.369 194.59 144.985 196.216 142.547C205.56 128.531 211.739 110.014 211.739 91.3166C211.739 75.4373 206.932 61.4489 196.901 51.4176C186.869 41.3864 172.881 36.5796 157.002 36.5796C141.122 36.5796 127.134 41.3864 117.103 51.4176C107.072 61.4489 102.265 75.4373 102.265 91.3166C102.265 110.014 108.443 128.531 117.788 142.547C119.413 144.985 121.194 147.369 123.118 149.639C111.253 152.128 99.2161 156.021 88.3419 161.646C66.307 173.044 47.5313 192.559 47.5309 222.685C47.5309 222.684 47.5309 222.685 47.5309 222.685L47.5293 244.578C47.5279 262.717 62.2323 277.423 80.3715 277.423H178.897C184.943 277.423 189.844 272.521 189.844 266.475C189.844 260.429 184.943 255.528 178.897 255.528H80.3715C74.3251 255.528 69.4237 250.626 69.4241 244.579L69.4257 222.686C69.4257 203.549 80.7536 190.222 98.4012 181.093C116.285 171.842 139.076 167.948 157.002 167.948C179.408 167.948 208.582 173.987 226.913 188.243C231.686 191.955 238.564 191.094 242.275 186.322C245.987 181.549 245.127 174.671 240.354 170.959C226.292 160.023 208.347 153.301 190.885 149.639ZM214.945 214.945C219.22 210.669 226.152 210.669 230.427 214.945L244.581 229.098L258.735 214.945C263.01 210.669 269.942 210.669 274.217 214.945C278.492 219.22 278.492 226.151 274.217 230.426L260.063 244.58L274.216 258.734C278.492 263.009 278.492 269.941 274.216 274.216C269.941 278.491 263.01 278.491 258.734 274.216L244.581 260.062L230.428 274.216C226.152 278.491 219.221 278.491 214.946 274.216C210.67 269.941 210.67 263.009 214.946 258.734L229.099 244.58L214.945 230.426C210.67 226.151 210.67 219.22 214.945 214.945Z" fill="var(--logo-icon)"/>
          </svg>
        </div>
        
        <h1 className="gs-title">Welcome to ITDer</h1>
        <p className="gs-desc">
          Your database is currently empty. To see anomaly signals, timeline charts, and SHAP feature attribution, you need to collect some data.
        </p>

        <div className="gs-status-bar">
          <div className={`gs-indicator ${dbStatus.has_data ? 'gs-ind-green' : 'gs-ind-red'}`}></div>
          <div className="gs-status-text">
            {dbStatus.has_data 
              ? `Data detected! ${dbStatus.features_count} records ready for processing.`
              : `Waiting for data stream... No records in database.`}
          </div>
        </div>

        <div className="gs-grid">
          <div className="gs-card" style={{ gridColumn: "span 2" }}>
            <h3 className="gs-card-title">Option 1: Collect Real Data</h3>
            <p className="gs-card-desc">
              Deploy the local agent to stream real user activity logs into the ingest API from your endpoints.
            </p>
            <div className="gs-code" style={{ marginBottom: 24, alignSelf: 'flex-start' }}>python dist/installer.py</div>
            
            <h3 className="gs-card-title">Option 2: Use Synthetic Data</h3>
            <p className="gs-card-desc">
              Instantly populate the dashboard with CERT-like anomalous scenarios and normal background activity.
            </p>
            <button 
              className={`gs-btn gs-btn-primary ${running ? 'gs-btn-loading' : ''}`} 
              onClick={handleGenerateAndProcess}
              disabled={!!running}
              style={{ alignSelf: 'flex-start' }}
            >
              {running === 'processing' ? 'Processing data in background...' : 'Generate & Process Data'}
            </button>
            {log && <div className="gs-log err">{log}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── app ───────────────────────────────────────────────────────────────────────
function App() {
  const [synthCfg, setSynthCfg] = React.useState({
    n_normal_users: 27, n_insider_users: 3, n_days: 90,
    normal_phase_days: 20, phased: true, random_scenarios: true,
  });
  const [inferCfg, setInferCfg] = React.useState({
    threshold: 0.3793,
  });
  const [refresh, setRefresh]             = useState(0);
  const [showSynthetic, setShowSynthetic] = useState(true);
  const synthParam = showSynthetic ? "?include_synthetic=true" : "";
  const { data: usersData, loading: uL, error: uE } = useApi(`/api/users${synthParam}`, refresh);
  const { data: dailyAll,  loading: dL, error: dE } = useApi(`/api/daily${synthParam}`, refresh);
  const { data: shapAll,   loading: sL, error: sE } = useApi("/api/shap",               refresh);

  const [sel, setSel]   = useState(null);
  const [tab, setTab]   = useState("overview");
  const [dark, setDark] = useState(getInitialDark);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    fetch('/api/settings')
      .then(r => r.json())
      .then(d => {
        if (d.synthCfg) setSynthCfg(d.synthCfg);
        if (d.inferCfg) setInferCfg(d.inferCfg);
      })
      .catch(() => {});
  }, []);

  useEffect(() => { applyTheme(dark); }, [dark]);
  const reloadData = () => setRefresh(r => r + 1);
  const toggleTheme = () => setDark((d) => !d);

  // Automatically refresh data when any background run finishes
  useEffect(() => {
    let wasRunning = false;
    const evt = new EventSource('/api/status_stream');
    evt.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.pipeline_status === 'running') {
          wasRunning = true;
        } else if (data.pipeline_status === 'success') {
          if (wasRunning) {
            reloadData();
            wasRunning = false;
          }
        }
      } catch(err) {}
    };
    return () => evt.close();
  }, []);

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

  if (!loading && !error && usersData.length === 0) {
    return (
      <div className="dash">
        <div className="hdr" style={{ justifyContent: "flex-end" }}>
          <div className="hdr-controls">
            <ThemeToggle dark={dark} onToggle={toggleTheme} />
          </div>
        </div>
        <GetStarted dark={dark} onSettingsClick={() => setShowSettings(true)} onDone={reloadData} />
        {showSettings && (
          <SettingsPanel
            onClose={() => setShowSettings(false)}
            onDone={() => { setShowSettings(false); reloadData(); }}
            dark={dark}
            showSynthetic={showSynthetic}
            onToggleSynthetic={() => setShowSynthetic(v => !v)}
            synthCfg={synthCfg} setSynthCfg={setSynthCfg}
            inferCfg={inferCfg} setInferCfg={setInferCfg}
          />
        )}
      </div>
    );
  }

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
            {[...usersData].sort((a, b) => {
              const typeA = a.user.includes('insider') ? 1 : a.user.includes('external') ? 2 : 3;
              const typeB = b.user.includes('insider') ? 1 : b.user.includes('external') ? 2 : 3;
              if (typeA !== typeB) return typeA - typeB;
              return a.user.localeCompare(b.user);
            }).map((u) => {
              const rank = sortedUsers.findIndex(su => su.user === u.user) + 1;
              return (
                <option key={u.user} value={u.user}>
                  #{rank} {u.user}
                </option>
              );
            })}
          </select>
        </div>
      </div>

      {/* stat cards */}
      {user && (
        <div className="stats">
          <StatCard label="Rank"             value={`#${sortedUsers.findIndex(u => u.user === sel) + 1} of ${usersData.length}`}                  cls={user.rank <= 3 ? "r" : user.rank <= 10 ? "a" : "g"} accent="r" />
          <StatCard label="Anomaly signal"   value={pct(user.unsupervised_mean ?? user.unsupervised_max)}     cls={tier === "critical" ? "r" : tier === "high" ? "a" : "g"} accent="a" />
          <StatCard label="ISO anomalies"    value={user.days_flagged_iso}        cls={user.days_flagged_iso > 5 ? "r" : user.days_flagged_iso > 0 ? "a" : "g"} accent="b" />
          <StatCard label="EE anomalies"     value={user.days_flagged_ee}        cls={user.days_flagged_ee > 5 ? "r" : user.days_flagged_ee > 0 ? "a" : "g"} accent="b" />
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
        {TABS.filter(([id]) => id !== "info").map(([id, lbl]) => (
          <button key={id} className={`tb${tab === id ? " on" : ""}`} onClick={() => setTab(id)}>
            {lbl}
          </button>
        ))}
        <span className="tabs-spacer" />
        <button className={`tb${tab === "info" ? " on" : ""}`} onClick={() => setTab("info")}>
          Info
        </button>
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
            <ScoreBar label="Elliptic Env mean"   sub="Avg EE score — distance from normal cluster"                    value={user.ee_score_norm_mean ?? 0} />

            <div className="ptitle" style={{ marginTop: 20 }}>Anomaly detection</div>
            <div className="anogrid">
              {[
                ["Days flagged", user.days_above_threshold, "var(--red)"],
                ["ISO flagged",  user.days_flagged_iso,     "var(--accent)"],
                ["EE flagged",   user.days_flagged_ee,     "var(--green)"],
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
                  <th>Active Hours</th>
                  <th>Flags Triggered</th>
                  <th>Volume Spikes</th>
                  <th>AI Models</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {[...daily].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 20).map((row) => {
                  const isBreech = +row.above_threshold === 1;
                  const isoAnom  = +row.iso_prediction === -1;
                  const eeAnom   = +row.ee_prediction === -1;

                  const dt = new Date(row.date + 'T00:00:00Z');
                  const isWeekend = dt.getUTCDay() === 5 || dt.getUTCDay() === 6;

                  // Collect boolean flags
                  const flags = [];
                  if (+row.after_hours_session_count > 0) {
                    flags.push(<span key="ah" className="flag-pill pill-amber" style={{marginRight: 4}}>After-hours login</span>);
                  }

                  if (+row.usb_after_hours_flag) flags.push(<span key="uah" className="flag-pill pill-red" style={{marginRight: 4}}>USB after-hours</span>);
                  if (+row.job_site_visits_flag) flags.push(<span key="js" className="flag-pill pill-amber" style={{marginRight: 4}}>Job site visit</span>);
                  if (+row.weekend_session_flag) flags.push(<span key="ws" className="flag-pill pill-amber" style={{marginRight: 4}}>Weekend session</span>);

                  // Collect z-score spikes
                  const spikes = [];
                  if (+row.logon_count_zscore > 1.5) {
                    const z = Number(row.logon_count_zscore).toFixed(1);
                    spikes.push(<span key="zlogon" className={`flag-pill ${z > 2.5 ? 'pill-red' : 'pill-amber'}`} style={{marginRight: 4}}>Logons (+{z}σ)</span>);
                  }
                  if (+row.usb_count_zscore > 1.5) {
                    const z = Number(row.usb_count_zscore).toFixed(1);
                    spikes.push(<span key="zusb" className={`flag-pill ${z > 2.5 ? 'pill-red' : 'pill-amber'}`} style={{marginRight: 4}}>USB Activity (+{z}σ)</span>);
                  }

                  // Collect AI models
                  const models = [];
                  if (isoAnom) models.push(<span key="iso" className="flag-pill pill-red" style={{marginRight: 4}}>IsoForest</span>);
                  if (eeAnom) models.push(<span key="ee" className="flag-pill pill-red" style={{marginRight: 4}}>Elliptic Env</span>);

                  return (
                    <tr key={row.date} className={`${isBreech ? "ar " : ""}${isWeekend ? "weekend" : ""}`.trim()}>
                      <td className="f-date">
                        {row.date.slice(5)}
                        {isWeekend && <span style={{marginLeft: 6, fontSize: '0.8em', color: 'var(--amber)', opacity: 0.8}}>[W]</span>}
                      </td>
                      <td><span className="f-risk" style={{ color: scoreColor(row.combined_risk_score) }}>{pct(row.combined_risk_score)}</span></td>
                      <td className="f-val-hi">{row.total_active_minutes_day > 0 ? (row.total_active_minutes_day / 60).toFixed(1) + "h" : "—"}</td>
                      <td>{flags.length > 0 ? flags : <span className="f-nil">—</span>}</td>
                      <td>{spikes.length > 0 ? spikes : <span className="f-nil">—</span>}</td>
                      <td>{models.length > 0 ? models : <span className="f-nil">—</span>}</td>
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

      {/* info tab */}
      {tab === "info" && user && (
        <div className="info-grid">

          <div className="panel info-panel">
            <div className="ptitle">CERT insider scenarios</div>

            <div className="scenario-card sc-1">
              <div className="sc-header">
                <span className="sc-badge">Scenario 1</span>
                <span className="sc-name">The Disgruntled Employee — Sabotage</span>
              </div>
              <div className="sc-signals">After-hours logons · USB exfiltration · No prior USB history</div>
              <div className="sc-desc">Employee plants malware or copies files after hours using USB. Typically no prior USB activity, making the spike highly anomalous. Detected by IsoForest isolating the unusual USB + after-hours combination.</div>
            </div>

            <div className="scenario-card sc-2">
              <div className="sc-header">
                <span className="sc-badge">Scenario 2</span>
                <span className="sc-name">The Departing Employee — Data Theft</span>
              </div>
              <div className="sc-signals">Job site visits · USB spike above baseline · Job search + USB compound signal</div>
              <div className="sc-desc">Employee preparing to leave begins visiting job sites and copying files to USB. The compound signal (job search week + USB usage) is a strong indicator. Elliptic Env detects the behavioral drift from normal cluster.</div>
            </div>

            <div className="scenario-card sc-3">
              <div className="sc-header">
                <span className="sc-badge">Scenario 3</span>
                <span className="sc-name">The Disgruntled SysAdmin — Sabotage</span>
              </div>
              <div className="sc-signals">After-hours logons · USB usage · Weekend sessions</div>
              <div className="sc-desc">Privileged user with system access performs after-hours operations including weekend sessions. Similar to Scenario 1 but typically more sustained and with weekend activity. Both IsoForest and Elliptic Env tend to agree on these days.</div>
            </div>

            <div className="sc-note">Scenarios sourced from CERT Insider Threat Dataset r4.2. Synthetic insiders in this pipeline are assigned one scenario each and exhibit that behavioral pattern during their active threat phase.</div>
          </div>

        </div>
      )}

      {showSettings && (
        <SettingsPanel
          onClose={() => setShowSettings(false)}
          onDone={() => { setShowSettings(false); reloadData(); }}
          dark={dark}
          showSynthetic={showSynthetic}
          onToggleSynthetic={() => setShowSynthetic(v => !v)}
          synthCfg={synthCfg} setSynthCfg={setSynthCfg}
          inferCfg={inferCfg} setInferCfg={setInferCfg}
        />
      )}
    </div>
  );
}

applyTheme(getInitialDark());
ReactDOM.createRoot(document.getElementById("root")).render(<App />);