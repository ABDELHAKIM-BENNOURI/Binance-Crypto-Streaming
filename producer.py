import json
import websocket
from kafka import KafkaProducer
import os
import time
import logging
from dotenv import load_dotenv

# ===========================================================
# CONFIGURATION DU LOGGING (Journalisation)
# ===========================================================
# Permet d'afficher des messages horodatés dans la console
# pour suivre l'état du programme en temps réel.
# Format : [heure] - [niveau] - [message]
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===========================================================
# CHARGEMENT DES VARIABLES D'ENVIRONNEMENT
# ===========================================================
# Lit le fichier .env à la racine du projet pour récupérer
# les paramètres de configuration sans les écrire en dur dans le code.
load_dotenv()

# ===========================================================
# PARAMÈTRES DE CONNEXION (depuis .env)
# ===========================================================
BINANCE_URL = os.getenv("BINANCE_WS_URL")       # URL du WebSocket Binance (multi-flux BTC, ETH...)
KAFKA_BROKER = os.getenv("KAFKA_BROKER")         # Adresse du broker Kafka (ex: localhost:9092)
TOPIC_PREFIX = os.getenv("KAFKA_TOPIC_PREFIX")   # Préfixe des topics Kafka (ex: crypto_trades_)


# ===========================================================
# CALLBACK : RÉCEPTION D'UN MESSAGE
# ===========================================================
# Cette fonction est automatiquement appelée à chaque fois
# que le WebSocket reçoit un nouveau trade de Binance.
def on_message(ws, message):
    try:
        # 1. Désérialisation : on convertit la chaîne JSON en dictionnaire Python
        data = json.loads(message)

        # 2. Format combiné Binance : {"stream": "btcusdt@trade", "data": {...}}
        #    On vérifie que le message contient bien les deux clés attendues.
        if 'stream' in data and 'data' in data:
            trade_data = data['data']  # Les données brutes du trade

            # 3. Extraction du symbole (ex: "BTCUSDT") pour nommer le topic Kafka
            symbol = trade_data.get('s', 'unknown').lower()  # "btcusdt"

            # 4. Construction du nom du topic Kafka dynamiquement
            #    Exemple : "crypto_trades_" + "btcusdt" = "crypto_trades_btcusdt"
            topic = f"{TOPIC_PREFIX}{symbol}"

            # 5. Validation des champs essentiels avant d'envoyer
            #    On vérifie que 'p' (prix), 'q' (quantité), 'T' (timestamp) sont présents.
            if all(k in trade_data for k in ('p', 'q', 'T')):

                # 6. Transformation : remplacer les clés cryptiques Binance
                #    par des noms de champs clairs et lisibles.
                #    Avant : {"e": "trade", "s": "BTCUSDT", "p": "67125.63", ...}
                #    Après : {"event_type": "trade", "symbol": "BTCUSDT", "price": "67125.63", ...}
                trade_propre = {
                    "event_type":   trade_data.get("e"),   # Type d'événement (toujours "trade")
                    "timestamp":    trade_data.get("E"),   # Horodatage de l'événement (ms)
                    "symbol":       trade_data.get("s"),   # Paire crypto (ex: "BTCUSDT")
                    "trade_id":     trade_data.get("t"),   # Identifiant unique du trade
                    "price":        trade_data.get("p"),   # Prix d'exécution
                    "quantity":     trade_data.get("q"),   # Quantité échangée
                    "buyer_id":     trade_data.get("b"),   # ID de l'ordre acheteur
                    "seller_id":    trade_data.get("a"),   # ID de l'ordre vendeur
                    "trade_time":   trade_data.get("T"),   # Horodatage exact du trade (ms)
                    "is_buyer_maker": trade_data.get("m"), # True = acheteur est le maker
                }

                # 7. Publication du message transformé dans Kafka
                #    - key=symbol.encode() : la clé garantit que tous les trades du même
                #      symbole (ex: BTCUSDT) vont toujours dans la même partition Kafka.
                #      → Ordre garanti par symbole + meilleur partitionnement pour Flink.
                producer.send(topic, key=symbol.encode(), value=trade_propre)
                # logger.info(f"Trade {symbol} publié dans Kafka")  # (décommenter pour debug)
            else:
                # Si des champs manquent, on log un avertissement sans planter
                logger.warning(f"Données de trade invalides reçues : {trade_data}")

    except json.JSONDecodeError:
        # Le message reçu n'est pas un JSON valide
        logger.error("Impossible de parser le message JSON de Binance")
    except Exception as e:
        # Toute autre erreur inattendue est capturée ici pour éviter un crash
        logger.error(f"Erreur lors du traitement du message : {e}")


# ===========================================================
# CALLBACK : ERREUR WEBSOCKET
# ===========================================================
# Appelée automatiquement si une erreur de connexion survient
# (ex: timeout, refus de connexion, etc.)
def on_error(ws, error):
    logger.error(f"Erreur WebSocket : {error}")


# ===========================================================
# CALLBACK : FERMETURE DE LA CONNEXION
# ===========================================================
# Appelée automatiquement lorsque la connexion WebSocket est fermée,
# que ce soit normalement ou suite à une erreur.
def on_close(ws, close_status_code, close_msg):
    logger.info(f"### Connexion Fermée : {close_msg} (code: {close_status_code}) ###")


# ===========================================================
# CALLBACK : OUVERTURE DE LA CONNEXION
# ===========================================================
# Appelée automatiquement dès que la connexion WebSocket
# est établie avec succès avec les serveurs Binance.
def on_open(ws):
    logger.info("### Connexion Ouverte avec le WebSocket Binance ###")


# ===========================================================
# FONCTION PRINCIPALE D'INGESTION
# ===========================================================
# Boucle infinie qui maintient la connexion WebSocket active.
# En cas de déconnexion, elle attend 5 secondes puis se reconnecte.
def start_ingestion():
    while True:
        try:
            logger.info(f"Connexion à {BINANCE_URL}...")

            # Création de l'objet WebSocketApp avec les 4 callbacks définis ci-dessus
            ws = websocket.WebSocketApp(
                BINANCE_URL,
                on_message=on_message,   # Appelée à chaque nouveau message
                on_error=on_error,       # Appelée en cas d'erreur
                on_close=on_close,       # Appelée à la fermeture
                on_open=on_open          # Appelée à l'ouverture
            )

            # Lancement de la connexion en mode persistant :
            # - ping_interval=60 : envoie un "ping" toutes les 60s pour maintenir la connexion vivante
            # - ping_timeout=10  : si pas de réponse après 10s, considère la connexion comme morte
            ws.run_forever(ping_interval=60, ping_timeout=10)

        except Exception as e:
            logger.error(f"Connexion échouée : {e}. Nouvelle tentative dans 5 secondes...")

        # Pause avant tentative de reconnexion
        time.sleep(5)


# ===========================================================
# POINT D'ENTRÉE DU PROGRAMME
# ===========================================================
if __name__ == "__main__":

    # 1. Initialisation du producteur Kafka (configuration niveau expert)
    try:
        producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BROKER],  # Adresse du broker Kafka
            # Sérialiseur : convertit le dictionnaire Python en JSON encodé en bytes UTF-8
            # C'est le format attendu par Kafka pour stocker les messages.
            value_serializer=lambda x: json.dumps(x).encode('utf-8'),
            retries=5,                    # Nombre de tentatives en cas d'échec d'envoi
            acks='all',                   # Fiabilité forte : le broker attend la confirmation
                                          # de TOUS les réplicas avant d'accuser réception.
                                          # → Garantit qu'aucun message n'est perdu.
            linger_ms=5,                  # Micro-batching : attend 5ms avant d'envoyer
                                          # pour regrouper plusieurs messages en un seul batch.
                                          # → Réduit le nombre de requêtes réseau = meilleur débit.
            compression_type='gzip'       # Compression des messages avant envoi.
                                          # → Réduit la taille des données (jusqu'à -70%)
                                          #    et améliore les performances réseau.
        )
        logger.info(f"Producteur Kafka connecté à {KAFKA_BROKER}")

        # 2. Lancement de la boucle d'ingestion WebSocket
        start_ingestion()

    except Exception as e:
        # Si Kafka est indisponible au démarrage, on arrête immédiatement
        logger.critical(f"Impossible de démarrer le Producteur Kafka : {e}")
