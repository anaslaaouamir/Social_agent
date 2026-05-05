# 1. Rebuild propre (obligatoire après changement requirements.txt)
docker compose down -v           # stoppe tout et supprime les volumes Redis/ES (pas Postgres)
docker compose build --no-cache  # rebuild toutes les images

# 2. Lance l'infrastructure dans l'ordre
docker compose up -d zookeeper
sleep 10
docker compose up -d kafka kafka-ui
sleep 15
docker compose up -d postgres redis elasticsearch
sleep 10
docker compose up -d spark-master spark-worker
docker compose up -d prometheus grafana
docker compose up -d backend celery_worker celery_beat flower frontend nginx

# 3. Vérifie que tout tourne
docker compose ps

# 4. Vérifie les logs backend (cherche "Kafka topics created")
docker compose logs backend --tail=50

# 5. Vérifie Kafka UI → http://localhost:8090
# Tu dois voir les topics : social.comments.raw, social.nlp.results, etc.

# Crée un venv propre (Python 3.11 recommandé)
cd backend
python3.11 -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate          # Windows

# Install de toutes les dépendances (ça prend ~5-10 min, torch est lourd)
pip install --upgrade pip
pip install -r requirements.txt

# Vérifie l'install des paquets critiques
python -c "import confluent_kafka; print('kafka OK')"
python -c "from bertopic import BERTopic; print('bertopic OK')"
python -c "import chromadb; print('chromadb OK')"
python -c "from pyspark.sql import SparkSession; print('pyspark OK')"

# Télécharge les modèles HuggingFace (fait-le une seule fois, ils sont mis en cache)
python - <<'EOF'
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")
print("sentence-transformers: OK")
EOF

python - <<'EOF'
from transformers import pipeline
pipeline("sentiment-analysis", model="cardiffnlp/twitter-roberta-base-sentiment-latest", truncation=True)
print("sentiment model: OK")
EOF

python - <<'EOF'
from transformers import pipeline
pipeline("text-classification", model="unitary/toxic-bert", truncation=True)
print("toxic model: OK")
EOF

# Crée les dossiers nécessaires
mkdir -p data/models data/datasets data/chroma spark/jobs spark/checkpoints
mkdir -p docker/grafana/dashboards docker/grafana/datasources
# Option A — via Docker (recommandé)
docker compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.8,org.postgresql:postgresql:42.7.3 \
  /opt/spark-jobs/stream_processor.py

# Option B — en local (si Spark installé sur ta machine)
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64  # adapte selon ta machine
spark-submit \
  --master local[2] \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.8 \
  spark/jobs/stream_processor.py

# Vérifie que les topics d'output sont créés (dans Kafka UI ou en CLI)
docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list
# Tu dois voir : social.analytics.sentiment_window, social.analytics.engagement_window

# Voir tous les logs en temps réel
docker compose logs -f --tail=100

# Vérifier les topics Kafka et leurs messages
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic social.nlp.results \
  --from-beginning \
  --max-messages 5

# Vérifier la santé du backend (inclut maintenant Kafka)
curl http://localhost:8000/api/health/detailed

# Accès aux UIs
# Kafka UI     → http://localhost:8090
# Spark UI     → http://localhost:8080
# Grafana      → http://localhost:3001  (admin / admin123)
# Flower       → http://localhost:5555  (admin / admin123)
# FastAPI docs → http://localhost:8000/api/docs

# Tester le WebSocket d'alertes (depuis un terminal)
pip install websockets
python - <<'EOF'
import asyncio, websockets, json

async def listen():
    uri = "ws://localhost:8000/ws/alerts"
    async with websockets.connect(uri) as ws:
        print("Connecté aux alertes temps réel")
        async for msg in ws:
            print(json.loads(msg))

asyncio.run(listen())
EOF

# Ingérer un fichier dans le RAG (exemple)
curl -X POST http://localhost:8000/api/nlp/rag/ingest \
  -H "Authorization: Bearer TON_TOKEN" \
  -F "file=@/ton/fichier.pdf"

  # Setup Kaggle API (une seule fois)
pip install kaggle
# Télécharge ton kaggle.json depuis https://www.kaggle.com/settings → API
mkdir -p ~/.kaggle && cp ~/Downloads/kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json

# Télécharge les datasets
mkdir -p data/datasets && cd data/datasets

# Sentiment (1.6M tweets, le meilleur pour commencer)
kaggle datasets download -d kazanova/sentiment140 --unzip

# Engagement Instagram (42K posts avec likes/comments/followers)
kaggle datasets download -d shmalex/instagram-dataset --unzip

# Toxic comments (150K, gold standard)
kaggle competitions download -c jigsaw-toxic-comment-classification-challenge --unzip

# Via HuggingFace (pas besoin de compte Kaggle)
pip install datasets
python - <<'EOF'
from datasets import load_dataset
import pandas as pd

# Tweet sentiment (multilingual)
ds = load_dataset("tweet_eval", "sentiment", split="train")
df = ds.to_pandas()
df.to_csv("tweet_sentiment.csv", index=False)
print(f"Tweet sentiment: {len(df)} lignes")
EOF

cd ../..

# Lance l'entraînement du modèle d'engagement
python - <<'EOF'
import pandas as pd
import numpy as np
from services.ml_engagement import engagement_predictor

# Charge le dataset Instagram
df = pd.read_csv("data/datasets/instagram_posts.csv")  # adapte le nom

# Prépare les features (adapte selon les colonnes réelles du dataset)
df_train = pd.DataFrame({
    "platform": "instagram",
    "content_type": df.get("type", "image"),
    "hour": pd.to_datetime(df["timestamp"]).dt.hour if "timestamp" in df.columns else np.random.randint(0,24,len(df)),
    "day_of_week": pd.to_datetime(df["timestamp"]).dt.dayofweek if "timestamp" in df.columns else np.random.randint(0,7,len(df)),
    "caption_length": df.get("caption", "").str.len() if "caption" in df.columns else 150,
    "hashtag_count": df.get("hashtags", "").str.count("#") if "hashtags" in df.columns else 10,
    "has_emoji": True,
    "has_mention": False,
    "has_question": False,
    "followers": df.get("followers", 10000),
    "historical_avg_er": 0.03,
    "engagement_rate": df.get("engagement_rate", df.get("likes", 100) / df.get("followers", 10000).clip(lower=1)),
})

df_train = df_train.dropna()
print(f"Dataset préparé: {len(df_train)} lignes")
metrics = engagement_predictor.train_on_dataset(df_train)
print(f"Résultats: MAE={metrics['mae']:.4f}, R²={metrics['r2']:.4f}")
EOF

# Teste l'API NLP (backend doit tourner)
curl -X POST http://localhost:8000/api/nlp/analyze \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TON_TOKEN" \
  -d '{"text": "Ce produit est absolument nul, arnaque totale !"}'


ngrok http --domain=shelve-childlike-fall.ngrok-free.dev --request-header-add="ngrok-skip-browser-warning: true" 8000        