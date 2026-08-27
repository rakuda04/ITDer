<div align="center">
  <img src="https://gist.githubusercontent.com/rakuda04/aac077ee98071e3e88769841e19c3aec/raw/3d6efede751e0ea6053ac1a3a37738cfc8b45365/ss.svg" alt="ITDer Logo" width="400">
  <br>
  <em>Local telemetry. Hybrid machine learning. Explainable threat detection.</em>
</div>

---

## What is ITDer?
ITDer is an insider-threat detection tool that monitors local device telemetry (Windows events, browser history) and flags anomalous user behavior using a hybrid machine learning pipeline. A supervised Random Forest model trained on the CERT insider-threat dataset is then combined with two unsupervised anomaly detectors (Isolation Forest, Elliptic Envelope) and scored against the local user population, and results are explained per-feature using SHAP.

## Repository layout
- `local/` — client-side collector + preprocessor (runs on monitored device) + deployment scripts
- `server/` — API, inference workers, dashboard, Docker services
- `docs/` — development notes and testing process
- `archive/` — earlier iterations of the program

## How it works 
```mermaid
graph TD
    %% Collection Layer
    subgraph Collection Layer
        WE[collectors/windows_events.py] --> COL[data_collector.py]
        BH[collectors/browser_history.py] --> COL
    end

    %% Preprocessing Layer
    subgraph Preprocessing Layer
        COL --> PRE[local_preprocessor.py]
        PRE --> FILT[processors/filters.py<br>Drop Noise]
        FILT --> FEAT[Feature Engineering]
        FEAT --> CLEAN[(Clean Data)]
    end

    %% ML Engine
    subgraph ML Inference Engine
        CLEAN --> INF[inference.py]
        
        INF --> RF(Stage 1: Random Forest)
        INF --> ISO(Stage 2: Isolation Forest)
        INF --> EE(Stage 3: Elliptic Envelope)

        RF --> AGG{Composite Scoring}
        ISO --> AGG
        EE --> AGG

        AGG --> SHAP[SHAP Explainability]
    end

    %% Transmission Bridge
    SHAP -->|POST Data| API[Server / ingest_api.py]

    %% Frontend Dashboard
    subgraph Frontend Dashboard app.jsx
        API --> UI[React Dashboard]
        
        UI --> STATS[Key Risk Metrics<br>• User Rank<br>• Anomaly %<br>• Alert Counts]
        UI --> VIZ[Interactive Visualizations<br>• Timeline Chart<br>• SHAP Chart]
    end

    %% Layer-Specific Dark Mode Styling
    classDef collection fill:#0d2a3f,stroke:#29b6f6,stroke-width:2px,color:#e1f5fe;
    classDef preprocessing fill:#311b3b,stroke:#d05ce3,stroke-width:2px,color:#f8e1fd;
    classDef ml fill:#3e2723,stroke:#ffa726,stroke-width:2px,color:#fff3e0;
    classDef dashboard fill:#142e18,stroke:#66bb6a,stroke-width:2px,color:#e8f5e9;
    
    class WE,BH,COL collection;
    class PRE,FILT,FEAT,CLEAN preprocessing;
    class INF,RF,ISO,EE,AGG,SHAP ml;
    class API,UI,STATS,VIZ dashboard;
```
#  Setup & Installation

## Server Environment

1. `git clone` the repository and run the docker-compose.yml` from `dist/server` directory.

2. Run the server environment using Docker Compose:

   ```bash
   set "COMPOSE_BAKE=false" && docker compose up -d --build
   ```

3. Access the dashboard via your browser at:

   ```
   http://localhost:5001
   ```

   telemetry can be accessed at:
   ```
   http://localhost:5002
   ```

## Local Data Collector Client

1. run the installation script ```installer.py``` found in `/dist` directory on the target device:



2. During setup, you will be prompted to configure the server's API endpoint the default value is ```http://localhost:8000``` but you can change the api endpoint depending on your configuration.

## Limitations
- The supervised model (Random Forest) uses fixed weights from CERT training and is not retrained or fine-tuned on local data.
- Local scoring is validated against a synthetic population, not real labeled local users actual detection accuracy on genuine insider behavior is untested (due to lack of data availability).
