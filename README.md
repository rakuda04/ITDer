<div align="center">
  <img src="https://gist.githubusercontent.com/rakuda04/aac077ee98071e3e88769841e19c3aec/raw/3d6efede751e0ea6053ac1a3a37738cfc8b45365/ss.svg" alt="ITDer Logo" width="400">
  <br>
  <em>Local telemetry. Hybrid machine learning. Explainable threat detection.</em>
</div>

---

## How it works 
```mermaid
graph TD
    subgraph Collection Layer
        A[Windows UMDF<br>USB Events] --> E
        B[Security Logs<br>Logon/Lock] --> E
        C[System Logs<br>Sleep/Wake] --> E
        D[Browser History<br>SQLite] --> E
    end

    subgraph Preprocessing Layer
        E[data_collector.py] --> F{Noise Filters}
        F -->|Drop 60s Logon Noise| G[Clean Data]
        F -->|Drop 1s Phantom USB| G
        G --> H[(local_activity.csv)]
    end

    subgraph ML Inference Engine
        H --> I[inference.py]
        
        I -->|Stage 1| J(Supervised: Random Forest)
        I -->|Stage 2| K(Unsupervised: Isolation Forest)
        I -->|Stage 3| L(Unsupervised: Elliptic Envelope)

        J -.-> M{Risk Aggregation<br>& Composite Scoring}
        K -.-> M
        L -.-> M

        M --> N[Stage 4: SHAP Explainability]
    end

    subgraph Output & Reporting
        N --> O[local_report_daily.csv]
        N --> P[local_report_users.csv]
        N --> Q[local_shap_values.csv]
    end

    classDef default fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef engine fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef storage fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    
    class I,M,N engine;
    class H,O,P,Q storage;