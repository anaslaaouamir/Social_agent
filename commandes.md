# Commandes utiles - stack locale

## Services Docker nécessaires

```bash
docker compose up -d postgres redis elasticsearch
docker compose ps
```

## Backend local

```bash
conda activate mon_projet311
cd backend
uvicorn api.main:app --reload
```

API docs :

```text
http://localhost:8000/api/docs
```

## Frontend local

```bash
cd frontend
npm install
npm run dev
```

Frontend :

```text
http://localhost:3000
```

## Celery workers

```bash
cd backend
celery -A core.celery_app:celery_app worker --loglevel=info --pool=solo -Q scheduling,publishing,monitoring,analytics,reports,nlp
```

Dans un autre terminal :

```bash
cd backend
celery -A core.celery_app:celery_app beat --loglevel=info
```

## Health checks

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/health/detailed
```

## NLP / ML

Tester NLP :

```bash
curl -X POST http://localhost:8000/api/nlp/analyze \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TON_TOKEN" \
  -d '{"text": "Ce produit est absolument nul, arnaque totale !"}'
```

Télécharger datasets Hugging Face :

```bash
cd backend
python scripts/download_hf_datasets.py
```

Entraîner le modèle engagement via API :

```bash
curl -X POST http://localhost:8000/api/nlp/train-engagement \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TON_TOKEN" \
  -d '{"synthetic_size": 30000}'
```

## RAG

Ingérer un fichier :

```bash
curl -X POST http://localhost:8000/api/nlp/rag/ingest \
  -H "Authorization: Bearer TON_TOKEN" \
  -F "file=@/chemin/vers/fichier.pdf"
```

Lister les sources :

```bash
curl -H "Authorization: Bearer TON_TOKEN" \
  http://localhost:8000/api/nlp/rag/sources
```

## URLs utiles

```text
Frontend      http://localhost:3000
FastAPI Docs  http://localhost:8000/api/docs
Elasticsearch http://localhost:9200
Flower        http://localhost:5555
```

 ngrok http --domain=shelve-childlike-fall.ngrok-free.dev 8000  