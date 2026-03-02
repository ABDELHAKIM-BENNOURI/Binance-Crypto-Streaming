import json
import logging
import os
import time
from kafka import KafkaConsumer
from dotenv import load_dotenv
import urllib.request
import urllib.error

# ===========================================================
# CONFIGURATION DU LOGGING
# ===========================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# ===========================================================
# PARAMÈTRES
# ===========================================================
KAFKA_BROKER    = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC_PREFIX    = os.getenv("KAFKA_TOPIC_PREFIX", "crypto_trades_")
QUESTDB_URL     = "http://localhost:9001/write"   # Port 9001 = hôte → 9000 interne QuestDB
SYMBOLS         = ["btcusdt", "ethusdt"]
TOPICS          = [f"{TOPIC_PREFIX}{s}" for s in SYMBOLS]

# ===========================================================
# ÉCRITURE VERS QUESTDB (Protocole ILP — InfluxDB Line Protocol)
# ===========================================================
# Format ILP : measurement,tag=val field=val timestamp_ns
# QuestDB accepte ce format sur le endpoint HTTP /write
def write_to_questdb(symbol: str, price: float, quantity: float,
                     is_buyer_maker: bool, trade_time_ms: int):
    try:
        timestamp_ns = trade_time_ms * 1_000_000  # ms → nanosecondes
        buyer_maker_int = 1 if is_buyer_maker else 0

        line = (
            f"trades,"
            f"symbol={symbol.upper()} "
            f"price={price},"
            f"quantity={quantity},"
            f"is_buyer_maker={buyer_maker_int}i "
            f"{timestamp_ns}\n"
        )

        data = line.encode("utf-8")
        req = urllib.request.Request(QUESTDB_URL, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 204):
                logger.warning(f"QuestDB a répondu avec le code {resp.status}")

    except urllib.error.URLError as e:
        logger.error(f"Impossible d'écrire dans QuestDB : {e}")
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'écriture QuestDB : {e}")


# ===========================================================
# CONSOMMATEUR KAFKA — Lit les trades et les envoie à QuestDB
# ===========================================================
def start_writer():
    logger.info(f"Connexion à Kafka ({KAFKA_BROKER}) sur les topics : {TOPICS}")

    consumer = KafkaConsumer(
        *TOPICS,
        bootstrap_servers=[KAFKA_BROKER],
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="latest",       # Lire seulement les nouveaux messages
        enable_auto_commit=True,
        group_id="questdb-writer-group",
        consumer_timeout_ms=10_000
    )

    logger.info("✅ QuestDB Writer démarré — alimentation de Grafana en temps réel...")
    count = 0

    try:
        while True:
            try:
                for msg in consumer:
                    trade = msg.value

                    # Extraction et validation des champs
                    try:
                        price       = float(trade.get("price", 0))
                        quantity    = float(trade.get("quantity", 0))
                        symbol      = trade.get("symbol", "UNKNOWN")
                        trade_time  = int(trade.get("trade_time", time.time() * 1000))
                        is_bm       = bool(trade.get("is_buyer_maker", False))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Champ invalide ignoré : {e}")
                        continue

                    # Envoi vers QuestDB
                    write_to_questdb(symbol, price, quantity, is_bm, trade_time)
                    count += 1

                    # Log tous les 50 trades pour ne pas spammer la console
                    if count % 50 == 0:
                        logger.info(f"  💹 {count} trades envoyés à QuestDB")

            except Exception as e:
                logger.error(f"Erreur de consommation Kafka : {e}. Reconnexion dans 5s...")
                time.sleep(5)

    except KeyboardInterrupt:
        logger.info("Arrêt demandé (Ctrl+C).")
    finally:
        consumer.close()
        logger.info(f"QuestDB Writer arrêté. Total envoyé : {count} trades.")


# ===========================================================
# POINT D'ENTRÉE
# ===========================================================
if __name__ == "__main__":
    start_writer()
