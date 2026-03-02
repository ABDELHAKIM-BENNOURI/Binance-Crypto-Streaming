# 🔍 Guide de Vérification du Pipeline — Binance Crypto Streaming

Ce document liste toutes les commandes pour vérifier que chaque composant reçoit et traite bien les données.

---

## 1. 🐳 Vérifier que tous les conteneurs Docker sont actifs

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Résultat attendu** : tous les conteneurs en statut `Up`.

| Conteneur | Port |
|---|---|
| zookeeper | 2181 |
| kafka | 9092 |
| flink-jobmanager | 8081 |
| flink-taskmanager | — |
| namenode | 9870, 9000 |
| datanode | — |
| questdb | 9001 |
| grafana | 3000 |

---

## 2. 📡 Vérifier Kafka — Topics et Messages

> ⚠️ Les images Confluent utilisent `kafka-topics` (sans `.sh`)

### Lister les topics créés
```powershell
docker exec -it (docker ps -qf "name=kafka") kafka-topics `
  --bootstrap-server kafka:9092 `
  --list
```
**Attendu** : `crypto_trades_btcusdt` et `crypto_trades_ethusdt`

### Voir les messages en temps réel (topic BTC)
```powershell
docker exec -it (docker ps -qf "name=kafka") kafka-console-consumer `
  --bootstrap-server kafka:9092 `
  --topic crypto_trades_btcusdt `
  --from-beginning `
  --max-messages 5
```
**Attendu** : messages JSON avec `symbol`, `price`, `quantity`, `trade_time`.

### Voir le nombre de messages par topic
```powershell
docker exec -it (docker ps -qf "name=kafka") kafka-run-class `
  kafka.tools.GetOffsetShell `
  --broker-list kafka:9092 `
  --topic crypto_trades_btcusdt
```

### Lire les logs du broker Kafka
```powershell
docker logs (docker ps -qf "name=kafka") --tail 50
```

---

## 3. 🔥 Vérifier Flink — Jobs et Pipeline

### Interface Web Flink
👉 Ouvrir http://localhost:8081

Vérifier :
- Onglet **Jobs** → le job doit être en état `RUNNING`
- Onglet **Task Managers** → au moins 1 task manager actif
- Onglet **Metrics** → débit d'entrée/sortie en records/s

### Vérifier les logs du JobManager
```powershell
docker logs (docker ps -qf "name=flink-jobmanager") --tail 100
```
**Attendu** : pas d'erreur `ClassNotFoundException` ni de `NullPointerException`.

### Vérifier les logs du TaskManager
```powershell
docker logs (docker ps -qf "name=flink-taskmanager") --tail 100
```

---

## 4. 🗄️ Vérifier HDFS — Fichiers Parquet

### Interface Web HDFS
👉 Ouvrir http://localhost:9870 → **Utilities > Browse the file system**

Chemin à vérifier : `/crypto-data/indicators_expert/`

### Via ligne de commande

#### Lister les fichiers écrits
```powershell
docker exec -it namenode hdfs dfs -ls -R /crypto-data/
```
**Attendu** : dossiers `symbol=BTCUSDT` et `symbol=ETHUSDT` avec fichiers `.parquet`.

#### Taille des données stockées
```powershell
docker exec -it namenode hdfs dfs -du -h /crypto-data/
```

#### Santé du cluster HDFS
```powershell
docker exec -it namenode hdfs dfsadmin -report
```
**Attendu** : `Live datanodes: 1`, aucun bloc corrompu.

---

## 5. 💹 Vérifier QuestDB — Données Analytiques

### Interface Web QuestDB
👉 Ouvrir http://localhost:9001

Dans la console SQL, exécuter :
```sql
-- Voir les tables disponibles
SHOW TABLES;

-- Voir les dernières données reçues (alimentées par questdb_writer.py)
SELECT * FROM trades ORDER BY timestamp DESC LIMIT 20;

-- Compter les entrées par symbole
SELECT symbol, count() FROM trades GROUP BY symbol;
```

### Vérifier que `questdb_writer.py` tourne
Dans la fenêtre terminal du writer, vous devez voir :
```
INFO - ✅ QuestDB Writer démarré — alimentation de Grafana en temps réel...
INFO - 💹 50 trades envoyés à QuestDB
INFO - 💹 100 trades envoyés à QuestDB
```

---

## 6. 📈 Vérifier Grafana — Dashboard Auto-Provisionné

### Accès
👉 Ouvrir http://localhost:3000  
Login : `admin` / `admin`

### Le dashboard est automatiquement disponible
Menu **Dashboards** → dossier **"Crypto Streaming"** → **"🚀 Binance Crypto Streaming — Vue Temps Réel"**

### Panels disponibles
| Panel | Description |
|---|---|
| **💹 Prix BTC & ETH** | Courbe temps réel, mise à jour toutes les 5s |
| **₿ BTC Dernier Prix** | Stat en temps réel |
| **Ξ ETH Dernier Prix** | Stat en temps réel |
| **📊 Trades reçus** | Compteur fenêtre active |
| **📦 Volume BTC & ETH** | Quantités échangées |

### Vérifications
1. **Data Sources** → Réglages > Data sources → QuestDB doit être `Connected` ✅
2. **Dashboard** → les panels doivent afficher des courbes en temps réel
3. **Fenêtre de temps** → mettre sur `Last 15 minutes` pour voir les données récentes

---

## 7. 🐍 Vérifier le Producer Python

### Logs en temps réel
```
INFO - Producteur Kafka connecté à localhost:9092
INFO - ### Connexion Ouverte avec le WebSocket Binance ###
```
Si déconnecté, il affiche `Nouvelle tentative dans 5 secondes...` et reconnecte automatiquement.

### Tester manuellement la connexion Binance
```powershell
curl -s "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
```
**Attendu** : `{"symbol":"BTCUSDT","price":"XXXXX.XX"}`

---

## 8. ❗ Dépannage Rapide

| Symptôme | Cause probable | Solution |
|---|---|---|
| Kafka topic absent | Producer pas démarré | Relancer `python producer.py` |
| `kafka-topics.sh not found` | Image Confluent (pas Bitnami) | Utiliser `kafka-topics` sans `.sh` |
| Flink job `FAILED` | JARs manquants | Vérifier dossier `jars/` |
| HDFS vide | Pipeline Flink pas encore lancé | Vérifier `flink_processor.py` |
| Grafana sans données | `questdb_writer.py` pas lancé | Relancer `python questdb_writer.py` |
| Grafana sans dashboard | Provisioning non monté | Vérifier volume dans `docker-compose.yml` |
| Conteneur `Exited` | Crash au démarrage | `docker compose logs <service>` |

---

## 9. 🛑 Arrêt propre

```powershell
# Arrêter tous les services Docker (conserve les données)
docker compose down

# Arrêter et supprimer les volumes (repart de zéro)
docker compose down --volumes --remove-orphans
```
