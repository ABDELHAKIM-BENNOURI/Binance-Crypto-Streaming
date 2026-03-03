# ============================================================
#  START.PS1 - Script de Demarrage Unique
#  Projet : Binance Crypto Streaming
#  Usage  : .\start.ps1
# ============================================================

# Ne pas bloquer sur toutes les erreurs globalement (gestion manuelle)
$ErrorActionPreference = "Continue"
$ProjectDir = $PSScriptRoot
$JarsDir = Join-Path $ProjectDir "jars"

# ---- Helpers couleurs ----
function Write-Header($msg) {
    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "=============================================" -ForegroundColor Cyan
}
function Write-OK($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-INFO($msg) { Write-Host "  [..] $msg" -ForegroundColor Yellow }
function Write-ERR($msg) { Write-Host "  [!!] $msg" -ForegroundColor Red }

# Detecter docker compose v1 ou v2
function Invoke-DockerCompose {
    # BUG CORRIGE : $Args est une variable automatique PowerShell reservee.
    # Renomme en $DockerArgs pour eviter les conflits de portee.
    param([string[]]$DockerArgs)

    # BUG CORRIGE : $dc2 etait assigne mais jamais utilise.
    # On utilise $null directement pour jeter la sortie.
    $null = docker compose version 2>$null
    if ($LASTEXITCODE -eq 0) {
        # Docker Compose V2 (integre dans Docker Desktop)
        docker compose @DockerArgs
    }
    else {
        # Docker Compose V1 (ancienne commande standalone)
        docker-compose @DockerArgs
    }
}

# ============================================================
# ETAPE 1 - Verifier Docker
# ============================================================
Write-Header "ETAPE 1/5 - Verification de Docker"
try {
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Docker non disponible" }
    Write-OK "Docker est en cours d'execution."
}
catch {
    Write-ERR "Docker n'est pas demarre. Veuillez lancer Docker Desktop puis relancer ce script."
    exit 1
}

# ============================================================
# ETAPE 2 - Telechargement des JARs Flink (si manquants)
# ============================================================
Write-Header "ETAPE 2/5 - JARs Flink"

if (-not (Test-Path $JarsDir)) {
    New-Item -ItemType Directory -Path $JarsDir | Out-Null
    Write-INFO "Dossier 'jars/' cree."
}

$MavenBase = "https://repo1.maven.org/maven2"

$Jars = @{
    "flink-sql-connector-kafka-3.1.0-1.18.jar" = "$MavenBase/org/apache/flink/flink-sql-connector-kafka/3.1.0-1.18/flink-sql-connector-kafka-3.1.0-1.18.jar"
    "flink-parquet-1.18.0.jar"                 = "$MavenBase/org/apache/flink/flink-parquet/1.18.0/flink-parquet-1.18.0.jar"
    "parquet-column-1.12.3.jar"                = "$MavenBase/org/apache/parquet/parquet-column/1.12.3/parquet-column-1.12.3.jar"
    "parquet-common-1.12.3.jar"                = "$MavenBase/org/apache/parquet/parquet-common/1.12.3/parquet-common-1.12.3.jar"
    "parquet-encoding-1.12.3.jar"              = "$MavenBase/org/apache/parquet/parquet-encoding/1.12.3/parquet-encoding-1.12.3.jar"
    "parquet-format-structures-1.12.3.jar"     = "$MavenBase/org/apache/parquet/parquet-format-structures/1.12.3/parquet-format-structures-1.12.3.jar"
    "parquet-hadoop-1.12.3.jar"                = "$MavenBase/org/apache/parquet/parquet-hadoop/1.12.3/parquet-hadoop-1.12.3.jar"
}

foreach ($JarName in $Jars.Keys) {
    $JarPath = Join-Path $JarsDir $JarName
    if (Test-Path $JarPath) {
        Write-OK "$JarName (deja present)"
    }
    else {
        Write-INFO "Telechargement de $JarName ..."
        try {
            Invoke-WebRequest -Uri $Jars[$JarName] -OutFile $JarPath -UseBasicParsing -ErrorAction Stop
            Write-OK "$JarName telecharge."
        }
        catch {
            Write-ERR "Echec du telechargement de $JarName : $_"
            exit 1
        }
    }
}

# ============================================================
# ETAPE 3 - Installation des dependances Python
# ============================================================
Write-Header "ETAPE 3/5 - Dependances Python"
Write-INFO "Installation des packages Python..."
Set-Location $ProjectDir

$reqFile = Join-Path $ProjectDir "requirements.txt"
if (-not (Test-Path $reqFile)) {
    Write-ERR "Fichier requirements.txt introuvable dans $ProjectDir"
    exit 1
}

pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-ERR "Echec de l'installation des packages Python."
    exit 1
}
Write-OK "Packages Python installes."

# ============================================================
# ETAPE 4 - Demarrage de l'infrastructure Docker
# ============================================================
Write-Header "ETAPE 4/5 - Infrastructure Docker (Kafka, Flink, HDFS, QuestDB, Grafana)"
Write-INFO "Lancement des conteneurs Docker..."
Set-Location $ProjectDir
Invoke-DockerCompose "up", "-d"
if ($LASTEXITCODE -ne 0) {
    Write-ERR "Echec du lancement des conteneurs Docker."
    exit 1
}
Write-OK "Conteneurs lances."

# --- Attente que Kafka soit pret (max 60s) ---
Write-INFO "Attente que Kafka soit operationnel..."
$MaxWait = 60
$Interval = 5
$Elapsed = 0
$KafkaReady = $false

while ($Elapsed -lt $MaxWait) {
    try {
        # Recuperer l'ID du conteneur kafka
        $KafkaId = (Invoke-DockerCompose "ps", "-q", "kafka" 2>$null).Trim()
        if ($KafkaId -and $KafkaId -ne "") {
            # Confluent images utilisent 'kafka-topics' (sans .sh)
            $testResult = docker exec $KafkaId kafka-topics --bootstrap-server kafka:9092 --list 2>&1
            if ($LASTEXITCODE -eq 0) {
                $KafkaReady = $true
                break
            }
        }
    }
    catch {}
    Write-INFO "Kafka pas encore pret... ($Elapsed/$MaxWait s)"
    Start-Sleep -Seconds $Interval
    $Elapsed += $Interval
}

if (-not $KafkaReady) {
    Write-ERR "Kafka n'a pas demarre dans les $MaxWait secondes. Verifiez avec : docker compose logs kafka"
    exit 1
}
Write-OK "Kafka est operationnel !"

# --- Attente que QuestDB soit pret (max 60s) ---
Write-INFO "Attente que QuestDB soit operationnel..."
$ElapsedQDB = 0
$QuestDBReady = $false

while ($ElapsedQDB -lt $MaxWait) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:9001/exec?query=select+1" -Method Get -ErrorAction Stop
        if ($response) {
            $QuestDBReady = $true
            break
        }
    }
    catch {}
    Write-INFO "QuestDB pas encore pret... ($ElapsedQDB/$MaxWait s)"
    Start-Sleep -Seconds $Interval
    $ElapsedQDB += $Interval
}

if (-not $QuestDBReady) {
    Write-ERR "QuestDB n'a pas demarre dans les $MaxWait secondes. Verifiez avec : docker compose logs questdb"
    exit 1
}
Write-OK "QuestDB est operationnel !"

# ============================================================
# ETAPE 5 - Lancement du Producer et du Processeur Flink
# ============================================================
Write-Header "ETAPE 5/5 - Demarrage des applications Python"
Set-Location $ProjectDir

$ProducerFile = Join-Path $ProjectDir "producer.py"
$FlinkFile = Join-Path $ProjectDir "flink_processor.py"
$QuestDBWriter = Join-Path $ProjectDir "questdb_writer.py"

if (-not (Test-Path $ProducerFile)) {
    Write-ERR "Fichier producer.py introuvable."
    exit 1
}
if (-not (Test-Path $FlinkFile)) {
    Write-ERR "Fichier flink_processor.py introuvable."
    exit 1
}
if (-not (Test-Path $QuestDBWriter)) {
    Write-ERR "Fichier questdb_writer.py introuvable."
    exit 1
}

# Lancement du Producer dans un nouveau terminal
Write-INFO "Demarrage du Producer (WebSocket Binance -> Kafka)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python producer.py" -WorkingDirectory $ProjectDir -WindowStyle Normal

Start-Sleep -Seconds 3

# Lancement du Processeur Flink
Write-INFO "Demarrage du Pipeline Flink ML..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python flink_processor.py" -WorkingDirectory $ProjectDir -WindowStyle Normal

Start-Sleep -Seconds 2

# Lancement du QuestDB Writer (alimente Grafana en temps reel)
Write-INFO "Demarrage du QuestDB Writer (Kafka -> QuestDB -> Grafana)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python questdb_writer.py" -WorkingDirectory $ProjectDir -WindowStyle Normal

# ============================================================
# RESUME FINAL
# ============================================================
Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "  PROJET LANCE AVEC SUCCES !" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Services disponibles :" -ForegroundColor White
Write-Host "  [UI] Flink UI      -> http://localhost:8081" -ForegroundColor Cyan
Write-Host "  [UI] Grafana       -> http://localhost:3000  (admin/admin)" -ForegroundColor Cyan
Write-Host "  [UI] HDFS NameNode -> http://localhost:9870" -ForegroundColor Cyan
Write-Host "  [UI] QuestDB HTTP  -> http://localhost:9001" -ForegroundColor Cyan
Write-Host "  [OK] Kafka Broker  -> localhost:9092" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Pour arreter les services Docker :" -ForegroundColor Yellow
Write-Host "  docker compose down" -ForegroundColor Yellow
Write-Host ""
