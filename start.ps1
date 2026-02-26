# ============================================================
#  START.PS1 — Script de Démarrage Unique
#  Projet : Binance Crypto Streaming
#  Usage  : .\start.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$JarsDir = Join-Path $ProjectDir "jars"

# ---- Couleurs helpers ----
function Write-Header($msg) { Write-Host "`n===========================================" -ForegroundColor Cyan; Write-Host "  $msg" -ForegroundColor Cyan; Write-Host "===========================================" -ForegroundColor Cyan }
function Write-OK($msg)     { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-INFO($msg)   { Write-Host "  [..] $msg" -ForegroundColor Yellow }
function Write-ERR($msg)    { Write-Host "  [!!] $msg" -ForegroundColor Red }

# ============================================================
# ÉTAPE 1 — Vérifier Docker
# ============================================================
Write-Header "ETAPE 1/5 — Vérification de Docker"
try {
    docker info | Out-Null
    Write-OK "Docker est en cours d'exécution."
} catch {
    Write-ERR "Docker n'est pas démarré. Veuillez lancer Docker Desktop puis relancer ce script."
    exit 1
}

# ============================================================
# ÉTAPE 2 — Téléchargement des JARs Flink (si manquants)
# ============================================================
Write-Header "ETAPE 2/5 — JARs Flink"

if (-not (Test-Path $JarsDir)) {
    New-Item -ItemType Directory -Path $JarsDir | Out-Null
    Write-INFO "Dossier 'jars/' créé."
}

$MavenBase = "https://repo1.maven.org/maven2"

$Jars = @{
    "flink-sql-connector-kafka-3.1.0-1.18.jar"    = "$MavenBase/org/apache/flink/flink-sql-connector-kafka/3.1.0-1.18/flink-sql-connector-kafka-3.1.0-1.18.jar"
    "flink-parquet-1.18.0.jar"                     = "$MavenBase/org/apache/flink/flink-parquet/1.18.0/flink-parquet-1.18.0.jar"
    "parquet-column-1.12.3.jar"                    = "$MavenBase/org/apache/parquet/parquet-column/1.12.3/parquet-column-1.12.3.jar"
    "parquet-common-1.12.3.jar"                    = "$MavenBase/org/apache/parquet/parquet-common/1.12.3/parquet-common-1.12.3.jar"
    "parquet-encoding-1.12.3.jar"                  = "$MavenBase/org/apache/parquet/parquet-encoding/1.12.3/parquet-encoding-1.12.3.jar"
    "parquet-format-structures-1.12.3.jar"         = "$MavenBase/org/apache/parquet/parquet-format-structures/1.12.3/parquet-format-structures-1.12.3.jar"
    "parquet-hadoop-1.12.3.jar"                    = "$MavenBase/org/apache/parquet/parquet-hadoop/1.12.3/parquet-hadoop-1.12.3.jar"
}

foreach ($JarName in $Jars.Keys) {
    $JarPath = Join-Path $JarsDir $JarName
    if (Test-Path $JarPath) {
        Write-OK "$JarName (déjà présent)"
    } else {
        Write-INFO "Téléchargement de $JarName ..."
        try {
            Invoke-WebRequest -Uri $Jars[$JarName] -OutFile $JarPath -UseBasicParsing
            Write-OK "$JarName téléchargé."
        } catch {
            Write-ERR "Échec du téléchargement de $JarName : $_"
            exit 1
        }
    }
}

# ============================================================
# ÉTAPE 3 — Installation des dépendances Python
# ============================================================
Write-Header "ETAPE 3/5 — Dépendances Python"
Write-INFO "Installation des packages Python..."
Set-Location $ProjectDir
pip install -r requirements.txt --quiet
Write-OK "Packages Python installés."

# ============================================================
# ÉTAPE 4 — Démarrage de l'infrastructure Docker
# ============================================================
Write-Header "ETAPE 4/5 — Infrastructure Docker (Kafka, Flink, HDFS, QuestDB, Grafana)"
Write-INFO "Lancement des conteneurs Docker..."
Set-Location $ProjectDir
docker-compose up -d
Write-OK "Conteneurs lancés."

# --- Attente que Kafka soit prêt (max 60s) ---
Write-INFO "Attente que Kafka soit opérationnel..."
$MaxWait  = 60
$Interval = 5
$Elapsed  = 0
$KafkaReady = $false

while ($Elapsed -lt $MaxWait) {
    try {
        $result = docker exec (docker-compose ps -q kafka) kafka-topics.sh --bootstrap-server localhost:9092 --list 2>&1
        if ($LASTEXITCODE -eq 0) {
            $KafkaReady = $true
            break
        }
    } catch {}
    Write-INFO "Kafka pas encore prêt... ($Elapsed/$MaxWait s)"
    Start-Sleep -Seconds $Interval
    $Elapsed += $Interval
}

if (-not $KafkaReady) {
    Write-ERR "Kafka n'a pas démarré dans les ${MaxWait}s. Vérifiez avec : docker-compose logs kafka"
    exit 1
}
Write-OK "Kafka est opérationnel !"

# ============================================================
# ÉTAPE 5 — Lancement du Producer et du Processeur Flink
# ============================================================
Write-Header "ETAPE 5/5 — Démarrage des applications Python"
Set-Location $ProjectDir

# Lancement du Producer dans un nouveau terminal
Write-INFO "Démarrage du Producer (WebSocket Binance → Kafka)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ProjectDir'; python producer.py" -WindowStyle Normal

Start-Sleep -Seconds 3

# Lancement du Processeur Flink
Write-INFO "Démarrage du Pipeline Flink ML..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ProjectDir'; python flink_processor.py" -WindowStyle Normal

# ============================================================
# RÉSUMÉ FINAL
# ============================================================
Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "  PROJET LANCÉ AVEC SUCCÈS ! " -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Services disponibles :" -ForegroundColor White
Write-Host "  📊 Flink UI     → http://localhost:8081" -ForegroundColor Cyan
Write-Host "  📈 Grafana      → http://localhost:3000  (admin/admin)" -ForegroundColor Cyan
Write-Host "  🗄️  HDFS NameNode→ http://localhost:9870" -ForegroundColor Cyan
Write-Host "  💹 QuestDB HTTP → http://localhost:9001" -ForegroundColor Cyan
Write-Host "  📡 Kafka Broker → localhost:9092" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Pour arrêter les services Docker :" -ForegroundColor Yellow
Write-Host "  docker-compose down" -ForegroundColor Yellow
Write-Host ""
