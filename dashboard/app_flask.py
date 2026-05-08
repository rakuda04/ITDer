"""
ITDer – Flask Dashboard
Run: python dashboard/app_flask.py
Open: http://localhost:5000
"""
from flask import Flask, jsonify, render_template, send_from_directory
import pandas as pd
import networkx as nx
import os, json

app = Flask(__name__, template_folder="templates", static_folder="static")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# ── Load & merge data once ─────────────────────────────────────────────────────
def load():
    features    = pd.read_csv(os.path.join(DATA_DIR, "merged_features.csv"))
    scores      = pd.read_csv(os.path.join(DATA_DIR, "anomaly_scores.csv"))
    file_access = pd.read_csv(os.path.join(DATA_DIR, "file_access.csv"), parse_dates=["access_time"])
    usb_usage   = pd.read_csv(os.path.join(DATA_DIR, "usb_usage.csv"),   parse_dates=["plug_time","unplug_time"])
    df = pd.merge(features, scores, on="user")
    return df, file_access, usb_usage

DF, FILE_ACCESS, USB_USAGE = load()

def infer_reason(row):
    if row.get("out_of_session_access", 0) > 0:
        return "Abnormal file operations"
    h = row.get("mean_login_hour", 12)
    if h < 6 or h > 22:
        return "Unusual login patterns"
    if row.get("usb_per_day", 0) > 0.5:
        return "USB misuse"
    return "Anomalous behaviour"

def fake_cert(row):
    v = max(row.get("isolation_forest",0), row.get("oneclass_svm",0), row.get("autoencoder",0))
    return round(min(v / 2.0, 0.99), 2)

def fake_time(i):
    return f"{12+(i*83%7):02d}:{(i*37)%60:02d}"

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/anomaly")
def api_anomaly():
    df = DF.copy()
    red_col = "is_red_team_x" if "is_red_team_x" in df.columns else "is_red_team"
    rows = []
    for model in ["isolation_forest", "oneclass_svm", "autoencoder"]:
        tmp = df.copy()
        tmp["rank"] = tmp[model].rank(ascending=False).astype(int)
        tmp_sorted = tmp.sort_values(model, ascending=False).reset_index(drop=True)
        for i, (_, row) in enumerate(tmp_sorted.iterrows()):
            rows.append({
                "model":      model,
                "user":       row["user"],
                "score":      round(float(row[model]), 4),
                "rank":       int(row["rank"]),
                "risk":       round(float(row[model]), 2),
                "reasoning":  infer_reason(row),
                "certainty":  fake_cert(row),
                "time":       fake_time(i),
                "is_red":     int(row.get(red_col, 0)),
            })
    return jsonify(rows)

@app.route("/api/stats")
def api_stats():
    df = DF.copy()
    red_col = "is_red_team_x" if "is_red_team_x" in df.columns else "is_red_team"
    return jsonify({
        "total_users":  len(df),
        "red_team":     int(df[red_col].sum()),
        "high_risk":    int((df["isolation_forest"] > df["isolation_forest"].quantile(0.8)).sum()),
        "threat_months": [10,10,12,14,17,20,19,16,15,16,21,22],
        "threat_labels": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
        "threat_types":  [
            {"name":"Unusual login patterns","pct":62},
            {"name":"USB misuse","pct":25},
            {"name":"Network anomalies","pct":13},
        ],
        "top_threats": [
            { "user": r["user"], "iso": round(float(r["isolation_forest"]),4),
              "rank": int(r["rank"]), "risk": round(float(r["isolation_forest"]),2),
              "reasoning": infer_reason(r), "certainty": fake_cert(r), "time": fake_time(i) }
            for i,(_, r) in enumerate(
                df.assign(rank=df["isolation_forest"].rank(ascending=False).astype(int))
                  .sort_values("isolation_forest", ascending=False)
                  .head(3).iterrows()
            )
        ],
    })

@app.route("/api/graph")
def api_graph():
    G = nx.Graph()
    for _, r in FILE_ACCESS.iterrows(): G.add_edge(r["user"], r["file"],   kind="access")
    for _, r in USB_USAGE.iterrows():   G.add_edge(r["user"], r["device"], kind="usb")

    df = DF.copy()
    scores_map = {}
    for _, row in df.iterrows():
        anomaly  = max(row["isolation_forest"], row["oneclass_svm"], row["autoencoder"])
        red_col  = "is_red_team_x" if "is_red_team_x" in row.index else "is_red_team"
        red_team = int(row[red_col])
        scores_map[row["user"]] = {"anomaly": anomaly, "red": red_team,
                                   "high_risk": (anomaly > 1.0) or (red_team == 1)}

    high = {n for n,v in scores_map.items() if v["high_risk"]}
    conn = set()
    for n in high:
        conn.add(n)
        conn.update(G.neighbors(n))
    subG = G.subgraph(conn)

    nodes, edges = [], []
    for node in subG.nodes():
        if node in scores_map:
            s = scores_map[node]["anomaly"]
            r = scores_map[node]["red"]
            color = "#e74c3c" if r else ("#e67e22" if s>1.5 else "#f1c40f" if s>1.0 else "#3ad4f8")
            size  = 28 if r else (20 if s>1.5 else 14 if s>1.0 else 9)
            label = f"{node} {'🔴' if r else ''}"
        elif str(node).startswith("file"):
            color,size,label = "#27ae60", 7, node
        elif str(node).startswith("usb"):
            color,size,label = "#8e44ad", 7, node
        else:
            color,size,label = "#2c3e50", 7, str(node)
        nodes.append({"id": str(node), "label": label, "color": color, "size": size})
    for e in subG.edges(data=True):
        edges.append({"from": str(e[0]), "to": str(e[1]),
                      "color": "#1a3040" if e[2].get("kind")=="access" else "#6c3483"})
    return jsonify({"nodes": nodes, "edges": edges})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
