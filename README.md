# Binance Crypto Streaming — Architecture Big Data Temps Réel

Pipeline de streaming en temps réel pour les transactions Binance (BTC/USDT et ETH/USDT) avec détection d'anomalies ML et dashboard Grafana auto-configuré.

## 🏗️ Architecture

```
Binance WebSocket
      │
      ▼
  producer.py ──────────────► Kafka (topics: crypto_trades_btcusdt / ethusdt)
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
          flink_processor.py               questdb_writer.py
          (ML Z-Score, Exactly-Once)       (Kafka → QuestDB)
                    │                               │
                    ▼                               ▼
               HDFS (Parquet)                  QuestDB
                                                   │
                                                   ▼
                                             Grafana Dashboard
                                        (auto-provisionné au démarrage)
```

| Composant | Rôle |
|---|---|
| **`producer.py`** | Connexion WebSocket Binance, reconnexion automatique, envoi vers Kafka |
| **`questdb_writer.py`** | Consumer Kafka → QuestDB via ILP HTTP pour alimenter Grafana |
| **Apache Kafka** | Transport découplé, un topic par paire crypto, compression gzip |
| **Apache Flink** | Streaming pur, Exactly-Once, Z-Score ML, Risk Score dynamique |
| **HDFS** | Stockage Parquet partitionné par symbole dans `/indicators_expert/` |
| **QuestDB** | Base de données time-series pour Grafana (protocol PostgreSQL) |
| **Grafana** | Dashboard auto-configuré : prix BTC/ETH, volumes, compteurs (refresh 5s) |

## 🚀 Démarrage en une seule commande

### Prérequis
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et démarré
- Python 3.8+ installé
- Java 11+ installé (requis par PyFlink)

### 1. Configurer l'environnement
```powershell
copy .env.example .env
# Le fichier est déjà pré-configuré pour BTC/ETH
```

### 2. Lancer le projet
```powershell
.\start.ps1
```

Le script fait tout automatiquement en 5 étapes :

| Étape | Action |
|---|---|
| **1/5** | Vérifie que Docker est actif |
| **2/5** | Télécharge les JARs Flink dans `jars/` (~50 Mo, 1ère fois uniquement) |
| **3/5** | Installe les dépendances Python (`pip install -r requirements.txt`) |
| **4/5** | Lance tous les services Docker et attend que Kafka soit prêt |
| **5/5** | Ouvre 3 terminaux : `producer.py`, `flink_processor.py`, `questdb_writer.py` |

## 🌐 Accès aux services

| Service | URL | Identifiants |
|---|---|---|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Flink UI** | http://localhost:8081 | — |
| **HDFS Namenode** | http://localhost:9870 | — |
| **QuestDB** | http://localhost:9001 | — |
| **Kafka Broker** | localhost:9092 | — |

> 💡 Le dashboard Grafana **"🚀 Binance Crypto Streaming — Vue Temps Réel"** est créé automatiquement au démarrage. Aucune configuration manuelle nécessaire.

## 📁 Structure du projet

```
Binance_Crypto_Streaming/
├── producer.py              # Ingestion WebSocket Binance → Kafka
├── flink_processor.py       # Pipeline ML Flink → HDFS
├── questdb_writer.py        # Consumer Kafka → QuestDB (pour Grafana)
├── start.ps1                # Script de démarrage unique
├── check_ps.ps1             # Script de vérification de l'état
├── docker-compose.yml       # Infrastructure complète (Confluent Kafka, Flink, HDFS, QuestDB, Grafana)
├── requirements.txt         # Dépendances Python
├── jars/                    # JARs Flink téléchargés automatiquement par start.ps1
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── questdb.yml  # Datasource QuestDB auto-configurée
│       └── dashboards/
│           ├── dashboard.yml
│           └── crypto_dashboard.json  # Dashboard 5 panels (prix, volumes, stats)
├── .env                     # Variables d'environnement (non versionné)
├── .env.example             # Modèle de configuration
└── hadoop.env               # Configuration HDFS
```

## 🛑 Arrêter le projet

```powershell
# Arrêt propre (conserve les données)
docker compose down

# Arrêt + suppression des volumes (repart de zéro)
docker compose down --volumes --remove-orphans
```

## ✅ Fonctionnalités

- [x] **Ingestion** : WebSocket Binance multi-stream, reconnexion auto, validation JSON, flush propre
- [x] **Kafka** : Confluent 7.5.0, topic par paire, compression gzip, `acks=all`
- [x] **Flink** : Exactly-Once, Watermarks, Z-Score ML en fenêtre glissante, Risk Score dynamique
- [x] **HDFS** : Parquet partitionné par symbole (`/indicators_expert/`)
- [x] **QuestDB** : Alimentation temps réel via `questdb_writer.py` (ILP HTTP)
- [x] **Grafana** : Dashboard auto-provisionné, refresh 5s, fenêtre 15 min, 5 panels
