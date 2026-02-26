# Binance Crypto Streaming — Architecture Big Data Temps Réel

Pipeline de streaming en temps réel pour les transactions Binance (BTC/USDT et ETH/USDT) avec détection d'anomalies ML.

## 🏗️ Architecture

```
Binance WebSocket → Kafka → Flink (EWMA + Z-Score ML) → HDFS (Parquet)
                                                         → QuestDB
                                                         → Grafana (Dashboard)
```

| Composant | Rôle |
|---|---|
| **Producer Python** | Connexion WebSocket Binance, reconnexion automatique |
| **Apache Kafka** | Transport découplé, un topic par paire crypto |
| **Apache Flink** | Streaming pur, Exactly-Once, Watermarks, State Management |
| **ML Online (EWMA + Z-Score)** | Détection d'anomalies adaptative en temps réel |
| **HDFS** | Stockage Parquet structuré en `/raw`, `/indicators`, `/anomalies` |
| **QuestDB** | Base OLAP pour Grafana |
| **Grafana** | Dashboard comparatif BTC vs ETH + alertes |

## � Démarrage en une seule commande

### Prérequis
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et démarré
- Python 3.8+ installé

### 1. Configurer l'environnement
```powershell
# Copier le fichier de configuration
copy .env.example .env
# Ouvrir .env et remplir les variables si nécessaire (déjà pré-configuré pour BTC/ETH)
```

### 2. Lancer le projet
```powershell
.\start.ps1
```

Le script fait tout automatiquement :
- ✅ Vérifie que Docker est actif
- ✅ Télécharge les JARs Flink (1ère fois seulement, ~50 Mo)
- ✅ Installe les dépendances Python
- ✅ Lance tous les services Docker (Kafka, Flink, HDFS, QuestDB, Grafana)
- ✅ Attend que Kafka soit prêt
- ✅ Démarre le Producer et le Pipeline Flink

## 🌐 Accès aux services

| Service | URL | Identifiants |
|---|---|---|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Flink UI** | http://localhost:8081 | — |
| **HDFS Namenode** | http://localhost:9870 | — |
| **QuestDB** | http://localhost:9001 | — |
| **Kafka** | localhost:9092 | — |

## 🛑 Arrêter le projet

```powershell
docker-compose down
```

## ✅ Conformité Cahier des Charges

- [x] **Ingestion** : WebSocket Binance, reconnexion auto, validation JSON
- [x] **Kafka** : Topic par paire, découplage, haute performance, compression gzip
- [x] **Flink** : Streaming pur, Exactly-Once, Watermarks, State Management
- [x] **ML Online** : EWMA + Z-Score adaptatif, Risk Score 0–100, seuil dynamique
- [x] **HDFS** : Parquet partitionné par symbole (`/indicators_expert/`)
- [x] **Dashboard** : Grafana avec comparaison inter-devises et alertes
