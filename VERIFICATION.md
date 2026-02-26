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

### Lister les topics créés
```powershell
docker exec -it (docker ps -qf "name=kafka") kafka-topics.sh `
  --bootstrap-server localhost:9092 `
  --list
```
**Attendu** : `crypto_trades_btcusdt` et `crypto_trades_ethusdt`

### Voir les messages en temps réel (topic BTC)
```powershell
docker exec -it (docker ps -qf "name=kafka") kafka-console-consumer.sh `
  --bootstrap-server localhost:9092 `
  --topic crypto_trades_btcusdt `
  --from-beginning `
  --max-messages 5
```
**Attendu** : messages JSON avec `symbol`, `price`, `quantity`, `trade_time`.

### Voir le nombre de messages par topic
```powershell
docker exec -it (docker ps -qf "name=kafka") kafka-run-class.sh kafka.tools.GetOffsetShell `
  --broker-list localhost:9092 `
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
- Onglet **Task Managers** → au moins 1 task manager avec des slots disponibles
- Onglet **Metrics** → débit d'entrée/sortie en records/s

### Vérifier les logs du JobManager
```powershell
docker logs (docker ps -qf "name=flink-jobmanager") --tail 100
```
**Attendu** : pas d'erreur `ClassNotFoundException` (JARs OK) ni de `NullPointerException`.

### Vérifier les logs du TaskManager
```powershell
docker logs (docker ps -qf "name=flink-taskmanager") --tail 100
```

---

## 4. 🗄️ Vérifier HDFS — Fichiers Parquet

### Interface Web HDFS
👉 Ouvrir http://localhost:9870 → onglet **Utilities > Browse the file system**

Chemin à vérifier : `/crypto-data/indicators_expert/`

### Via ligne de commande

#### Lister les fichiers écrits
```powershell
docker exec -it namenode hdfs dfs -ls -R /crypto-data/
```
**Attendu** : dossiers partitionnés par `symbol=BTCUSDT` et `symbol=ETHUSDT` avec des fichiers `.parquet`.

#### Afficher la taille des données stockées
```powershell
docker exec -it namenode hdfs dfs -du -h /crypto-data/
```

#### Vérifier le nombre de blocs et la santé du cluster
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

-- Voir les dernières données reçues
SELECT * FROM trades ORDER BY timestamp DESC LIMIT 20;

-- Compter les entrées par symbole
SELECT symbol, count() FROM trades GROUP BY symbol;
```

---

## 6. 📈 Vérifier Grafana — Dashboard

### Accès
👉 Ouvrir http://localhost:3000  
Login : `admin` / `admin`

### Étapes de vérification
1. **Data Sources** → Réglages > Data sources → QuestDB doit être `Connected` ✅
2. **Dashboard Crypto** → Les panels BTC et ETH doivent afficher des courbes en temps réel
3. **Alertes** → Vérifier que les règles d'alerte sur la volatilité sont actives

---

## 7. 🐍 Vérifier le Producer Python

### Logs en temps réel (dans la fenêtre producer)
Le producer affiche dans la console :
```
2024-xx-xx - INFO - ### Connexion Ouverte avec le WebSocket Binance ###
2024-xx-xx - INFO - Producteur Kafka connecté à localhost:9092
```
Si déconnecté, il affiche `Nouvelle tentative dans 5 secondes...` et reconnecte automatiquement.

### Tester manuellement la connexion Binance
```powershell
# Envoyer une requête test au WebSocket Binance (nécessite wscat ou curl)
curl -s "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
```
**Attendu** : `{"symbol":"BTCUSDT","price":"XXXXX.XX"}`

---

## 8. ❗ Dépannage Rapide

| Symptôme | Vérification | Solution |
|---|---|---|
| Kafka topic absent | `kafka-topics.sh --list` | Relancer `producer.py` |
| Flink job `FAILED` | Logs JobManager | Vérifier JARs dans `jars/` |
| HDFS vide | `hdfs dfs -ls /crypto-data/` | Vérifier ligne INSERT dans `flink_processor.py` |
| Grafana sans données | Console QuestDB | Vérifier sink QuestDB dans Flink |
| Conteneur `Exited` | `docker ps -a` | `docker-compose restart <service>` |

---

## 9. 🛑 Arrêt propre

```powershell
# Arrêter tous les services Docker
docker-compose down

# Arrêter et supprimer les volumes (repart de zéro)
docker-compose down -v
```
