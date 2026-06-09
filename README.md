# ITDer — Insider Threat Detection System

A local insider threat detection system that collects Windows activity logs, runs them through trained ML models, and displays anomalies on a web dashboard.

---

## ⚙️ Requirements

- Python 3.x
- Node.js (LTS) — only needed if modifying the frontend build
- Windows OS (for real log collection via `win32evtlog`)

---

## 🚀 Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/rakuda04/ITDer.git
cd ITDer
```

### 2. Install Python dependencies

```bash
cd frontend
pip install -r requirements.txt
```

Also install `pywin32` for Windows event log collection:

```bash
pip install pywin32
```

### 3. Run the dashboard

```bash
python run.py
```

Then open your browser and go to:

```
http://127.0.0.1:5000
```

---

## 🧪 Generating Sample Data

If you don't have real log data, you can generate synthetic logs directly from the dashboard:

1. Open the dashboard at `http://127.0.0.1:5000`
2. Navigate to the **Settings** panel
3. Click **"Run synthetic generator"**
4. Then click **"Run inference"**

The dashboard will populate with simulated anomalies and activity data.

Alternatively, run the generator manually from the terminal:

```bash
cd local_pipeline
python synthetic_generator.py
python inference.py
```

---

## 🔍 How It Works

1. **Log Collection** — `data_collector.py` gathers Windows Event Logs and browser history from the local machine
2. **Preprocessing** — `local_preprocessor.py` cleans and formats the raw logs
3. **Inference** — `inference.py` runs the data through pre-trained ML models (Isolation Forest, Elliptic Envelope, LOF, Random Forest)
4. **Dashboard** — Results are served via Flask and displayed on the React dashboard

---

## 🤖 ML Models

Pre-trained models are located in `cert_pipeline/output/models/`:

| Model | File |
|---|---|
| Isolation Forest | `iso_forest.pkl` |
| Elliptic Envelope | `elliptic_env.pkl` |
| Local Outlier Factor (scaler) | `lof_scaler.pkl` |
| Random Forest (supervised) | `rf_supervised.pkl` |

---

