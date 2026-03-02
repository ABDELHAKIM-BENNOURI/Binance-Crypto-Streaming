import os
from dotenv import load_dotenv
# CheckpointingMode a été déplacé vers pyflink.datastream dans PyFlink 1.17+
from pyflink.datastream import StreamExecutionEnvironment, CheckpointingMode
from pyflink.table import StreamTableEnvironment

# Chargement des variables d'environnement depuis .env
load_dotenv()

# ===========================================================
# CONFIGURATION DES JARs FLINK
# ===========================================================
# Les JARs sont téléchargés automatiquement par start.ps1
# dans le dossier "jars/" à la racine du projet.
JARS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jars")

REQUIRED_JARS = [
    "flink-sql-connector-kafka-3.1.0-1.18.jar",
    "flink-parquet-1.18.0.jar",
    "parquet-column-1.12.3.jar",
    "parquet-common-1.12.3.jar",
    "parquet-encoding-1.12.3.jar",
    "parquet-format-structures-1.12.3.jar",
    "parquet-hadoop-1.12.3.jar",
]

# Avertissement si des JARs sont manquants
MISSING_JARS = [j for j in REQUIRED_JARS if not os.path.exists(os.path.join(JARS_DIR, j))]
if MISSING_JARS:
    print(f"[ATTENTION] JARs manquants dans {JARS_DIR}/ :")
    for j in MISSING_JARS:
        print(f"  - {j}")
    print("  → Lancez 'start.ps1' pour les télécharger automatiquement.")

# Construction de la liste des JARs disponibles pour PyFlink
JARS_URIS = ";".join(
    f"file:///{os.path.join(JARS_DIR, j).replace(os.sep, '/')}"
    for j in REQUIRED_JARS
    if os.path.exists(os.path.join(JARS_DIR, j))
)


# ===========================================================
# CONFIGURATION FLINK (Exactly-Once Streaming)
# ===========================================================
def setup_flink():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.get_checkpoint_config().set_checkpointing_mode(CheckpointingMode.EXACTLY_ONCE)
    env.enable_checkpointing(10000)  # Checkpoint toutes les 10 secondes

    # Chargement des JARs dans le classloader Flink
    if JARS_URIS:
        env.add_jars(*JARS_URIS.split(";"))

    t_env = StreamTableEnvironment.create(env)
    return env, t_env


# ===========================================================
# POINT D'ENTRÉE — FIX BUG #2 : tout le code d'exécution
# est maintenant dans __main__ pour éviter son déclenchement
# accidentel lors d'un simple import du module.
# ===========================================================
if __name__ == "__main__":

    # FIX BUG #4 : lecture du broker depuis .env au lieu d'être hardcodé
    KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")

    env, t_env = setup_flink()

    # ===========================================================
    # ÉTAPE 1 : SOURCE KAFKA — Lecture des trades en temps réel
    # ===========================================================
    # FIX BUG #4 : 'bootstrap.servers' utilise la variable KAFKA_BROKER
    t_env.execute_sql(f"""
        CREATE TABLE trades_source (
            event_type      STRING,
            timestamp       BIGINT,
            symbol          STRING,
            trade_id        BIGINT,
            price           STRING,
            quantity        STRING,
            buyer_id        BIGINT,
            seller_id       BIGINT,
            trade_time      BIGINT,
            is_buyer_maker  BOOLEAN,

            event_time AS TO_TIMESTAMP(FROM_UNIXTIME(trade_time / 1000)),
            row_date AS DATE_FORMAT(TO_TIMESTAMP(FROM_UNIXTIME(trade_time / 1000)), 'yyyy-MM-dd'),
            WATERMARK FOR event_time AS event_time - INTERVAL '1' SECOND
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'crypto_trades_btcusdt,crypto_trades_ethusdt',
            'properties.bootstrap.servers' = '{KAFKA_BROKER}',
            'properties.group.id' = 'flink-ml-online-expert',
            'format' = 'json'
        )
    """)

    # ===========================================================
    # ÉTAPE 2 : PRÉPARATION DES FEATURES
    # ===========================================================
    t_env.execute_sql("""
        CREATE VIEW trades_features AS
        SELECT
            symbol,
            CAST(price AS DOUBLE)    AS price,
            CAST(quantity AS DOUBLE) AS quantity,
            is_buyer_maker,
            event_time,
            row_date
        FROM trades_source
    """)

    # ===========================================================
    # ÉTAPE 3 : ÉTAT ML — Moyenne et volatilité adaptatives
    # ===========================================================
    t_env.execute_sql("""
        CREATE VIEW ml_expert_state AS
        SELECT
            symbol,
            row_date,
            event_time,
            price,
            AVG(price) OVER (
                PARTITION BY symbol
                ORDER BY event_time
                ROWS BETWEEN 100 PRECEDING AND CURRENT ROW
            ) AS adapted_mean,
            STDDEV_SAMP(price) OVER (
                PARTITION BY symbol
                ORDER BY event_time
                ROWS BETWEEN 100 PRECEDING AND CURRENT ROW
            ) AS adapted_std
        FROM trades_features
    """)

    # ===========================================================
    # ÉTAPE 4 : INFÉRENCE ML — Calcul du Z-Score
    # ===========================================================
    t_env.execute_sql("""
        CREATE VIEW ml_expert_inference AS
        SELECT
            symbol,
            row_date,
            event_time,
            price,
            adapted_mean,
            (price - adapted_mean) / NULLIF(adapted_std, 0) AS z_score
        FROM ml_expert_state
    """)

    # ===========================================================
    # ÉTAPE 5 : SCORE DE RISQUE (non plafonné)
    # FIX BUG #3 : le CASE WHEN qui plafonnait risk_score à 100
    # est supprimé. ABS(z_score) * 20 peut maintenant dépasser 100,
    # ce qui rend la condition CRITICAL dans ml_final_alerts atteignable.
    # ===========================================================
    t_env.execute_sql("""
        CREATE VIEW ml_risk_analysis AS
        SELECT
            symbol,
            row_date,
            event_time,
            price,
            z_score,
            ABS(z_score) * 20 AS risk_score,
            AVG(ABS(z_score)) OVER (
                PARTITION BY symbol
                ORDER BY event_time
                ROWS BETWEEN 50 PRECEDING AND CURRENT ROW
            ) * 3 AS dynamic_threshold
        FROM ml_expert_inference
    """)

    # ===========================================================
    # ÉTAPE 6 : ALERTING — Détection des anomalies
    # La condition WHEN risk_score > 100 est maintenant réalisable
    # grâce au FIX BUG #3 ci-dessus.
    # ===========================================================
    t_env.execute_sql("""
        CREATE VIEW ml_final_alerts AS
        SELECT
            symbol,
            row_date,
            event_time                      AS window_start,
            'EXPERT_ONLINE_ML_ANOMALY'      AS alert_type,
            CASE
                WHEN risk_score > 100 THEN 'CRITICAL: Market Outlier'
                WHEN risk_score > dynamic_threshold THEN 'WARNING: Unusual Volatility'
                ELSE 'NORMAL'
            END AS risk_level,
            CONCAT('Risk=', CAST(risk_score AS STRING), ', Z=', CAST(z_score AS STRING)) AS description
        FROM ml_risk_analysis
        WHERE risk_score > dynamic_threshold
    """)

    # ===========================================================
    # ÉTAPE 7 : STOCKAGE HDFS (Sink Parquet)
    # ===========================================================
    t_env.execute_sql("""
        CREATE TABLE hdfs_expert_indicators_sink (
            symbol              STRING,
            price               DOUBLE,
            risk_score          DOUBLE,
            dynamic_threshold   DOUBLE,
            event_time          TIMESTAMP(3)
        ) PARTITIONED BY (symbol) WITH (
            'connector' = 'filesystem',
            'path' = 'hdfs://localhost:9000/crypto-data/indicators_expert/',
            'format' = 'parquet'
        )
    """)

    # ===========================================================
    # LANCEMENT DU JOB FLINK
    # ===========================================================
    print("=" * 60)
    print("  Moteur ML Temps Réel EXPERT — Démarrage du pipeline...")
    print("=" * 60)

    statement_set = t_env.create_statement_set()
    statement_set.add_insert(
        "hdfs_expert_indicators_sink",
        t_env.sql_query("SELECT symbol, price, risk_score, dynamic_threshold, event_time FROM ml_risk_analysis")
    )
    job = statement_set.execute()

    print(f"  ✅ Job Flink démarré ! ID : {job.get_job_client().get_job_id()}")
    print("  📊 Dashboard Flink   → http://localhost:8081")
    print("  📈 Dashboard Grafana → http://localhost:3000")
    print("  🗄️  Interface HDFS   → http://localhost:9870")
    # FIX Bug B : QuestDB retiré des prints — aucune sink QuestDB n'est définie dans ce pipeline.
