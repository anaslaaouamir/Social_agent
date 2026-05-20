# Social Agent Platform 🇲🇦

**Plateforme complète de gestion des réseaux sociaux — Multi-utilisateurs · IA · Temps réel**

[![Python](https://img.shields.io/badge/python-3.11-blue)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)]()
[![React](https://img.shields.io/badge/React-18.3-blue)]()
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4-blue)]()
[![Claude](https://img.shields.io/badge/Claude-Sonnet-purple)]()

---

## 🚀 Démarrage rapide

### Option A — App locale + services Docker

```bash
# 1. Activer l'environnement Python
conda activate mon_projet

# 2. Configurer l'environnement
cp .env.example .env
# Le fichier .env pointe vers localhost pour Postgres/Redis/Elasticsearch

# 3. Démarrer seulement les services
docker compose up -d postgres redis elasticsearch

# 4. Installer les dépendances backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload

# 5. Dans un autre terminal
conda activate mon_projet
cd frontend
npm install
npm run dev
```
# ngrok config add-authtoken COLLE_TON_VRAI_TOKEN_ICI
# ngrok http --domain=shelve-childlike-fall.ngrok-free.dev 8000

## workers celery
# celery -A core.celery_app:celery_app worker --loglevel=info -Q scheduling,publishing,monitoring,analytics,reports

# celery -A core.celery_app:celery_app worker --loglevel=info --pool=solo -Q scheduling,publishing,monitoring,analytics,reports

# celery -A core.celery_app:celery_app worker --loglevel=info --pool=threads --concurrency=4 -Q scheduling,publishing,monitoring,analytics,reports

# celery -A core.celery_app:celery_app beat --loglevel=info

# docker compose up -d postgres redis elasticsearch

python -c "
>> import asyncio
>> from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
>> from sqlalchemy.orm import sessionmaker
>> from core.config import get_settings
>> import uuid
>> 
>> async def insert():
>>     s = get_settings()
>>     engine = create_async_engine(s.database_url)
>>     async with AsyncSession(engine) as db:
>>         from models.domain import SocialAccount, Platform 
>>         account = SocialAccount(
>>             id=uuid.uuid4(),
>>             user_id=uuid.UUID('a310f070-8e14-4969-93c0-e0201365a39a'),
>>             platform=Platform.INSTAGRAM,
>>             account_id='17841474798936522',
>>             account_name='sou_kaina_2003',
>>             access_token='IGAAN1V8MOIO1BZAFpzOF9DekdBcGp3NVFjcFFHNHdPYVVubUMxZAFM0OHVydkpxOWUwd1JGRHExeVN0UmVRd0ZA5SUdzOVRTN2I3LWViRnltR2pndkJhUy1mRmdIQXJwZAFJJbmxWSHBzV2o0MXRQUGZA>>             refresh_token='',
>>             followers_count=0,
>>         )
>>         db.add(account)
>>         await db.commit()
>>         print('? Compte Instagram ajouté !')
>> 
>> asyncio.run(insert())
>> "

Dans ce mode, le backend et le frontend tournent en local, mais la base, Redis et Elasticsearch tournent dans Docker.

### Option B — Stack complète avec Docker

```bash
# 1. Configurer l'environnement
cp .env.example .env

# 2. Lancer toute la stack
docker compose up -d

# URLs :
# Frontend -> http://localhost:3000
# API Docs -> http://localhost:8000/api/docs
# Flower -> http://localhost:5555
# Via Nginx -> http://localhost:80
```

---

## 🏗️ Architecture

```
social-agent/
├── backend/                   # FastAPI — Python 3.11
│   ├── api/
│   │   ├── main.py            # Application + 14 routers
│   │   ├── auth_utils.py      # JWT multi-users
│   │   └── routes/
│   │       ├── auth.py        # Register / Login / Me
│   │       ├── accounts.py    # Connexion plateformes sociales
│   │       ├── posts.py       # CRUD posts + scheduling
│   │       ├── media.py       # Upload + analyse IA
│   │       ├── hashtags.py    # Recommandation + trending
│   │       ├── comments.py    # Analyse sentiment + batch
│   │       ├── dm.py          # Chatbot RAG
│   │       ├── analytics.py   # KPIs + prévisions
│   │       ├── calendar.py    # Planning éditorial
│   │       ├── alerts.py      # Alertes + acquittement
│   │       ├── content.py     # Génération IA (captions)
│   │       ├── timing.py      # Prédiction meilleurs créneaux
│   │       ├── monitoring.py  # ✨ Monitoring temps réel
│   │       └── profile.py     # ✨ Profil utilisateur
│   ├── modules/               # 6 modules IA
│   ├── services/              # Celery workers
│   ├── models/domain.py       # SQLAlchemy (User → SocialAccount → Post)
│   └── alembic/               # Migrations DB
│
├── frontend/                  # React 18 + TypeScript + Tailwind
│   └── src/
│       ├── pages/
│       │   ├── LoginPage.tsx        # Auth
│       │   ├── RegisterPage.tsx     # Inscription
│       │   ├── DashboardPage.tsx    # Tableau de bord
│       │   ├── AccountsPage.tsx     # Connexion plateformes
│       │   ├── InboxPage.tsx        # Boîte de réception unifiée
│       │   ├── CreatePostPage.tsx   # Compositeur multi-plateformes
│       │   ├── PostsPage.tsx        # Liste publications
│       │   ├── MediaLibraryPage.tsx # Médiathèque (drive images)
│       │   ├── HashtagLibraryPage.tsx # Bibliothèque hashtags
│       │   ├── CalendarPage.tsx     # Calendrier éditorial
│       │   ├── AnalyticsPage.tsx    # Analytics + graphiques
│       │   ├── MonitoringPage.tsx   # ✨ Monitoring temps réel
│       │   ├── ChatbotPage.tsx      # Chatbot RAG
│       │   ├── AlertsPage.tsx       # Alertes
│       │   └── SettingsPage.tsx     # ✨ Paramètres profil
│       ├── components/
│       │   ├── layout/AppLayout.tsx # Sidebar + navigation
│       │   └── ui.tsx               # Composants UI partagés
│       ├── lib/api.ts               # Client API Axios
│       └── store/index.ts           # État global Zustand
│
└── docker-compose.yml         # Stack complète
```

---

## ✨ Fonctionnalités ajoutées

### Multi-utilisateurs
- Inscription / Connexion avec JWT (access + refresh tokens)
- Chaque user a ses propres comptes sociaux isolés
- Données 100% séparées par utilisateur

### Plateformes supportées
| Plateforme | Posts | Stories | Reels/TikTok | Analyse |
|---|---|---|---|---|
| Instagram | ✅ | ✅ | ✅ | ✅ |
| Facebook | ✅ | — | — | ✅ |
| Twitter/X | ✅ | — | — | ✅ |
| LinkedIn | ✅ | — | — | ✅ |
| TikTok | ✅ | — | ✅ | ✅ |

### Médiathèque
- Drive d'images organisé par catégorie (Produit, Lifestyle, Promo…)
- Glisser-déposer pour upload
- Sélection directe depuis le compositeur de post

### Bibliothèque de Hashtags
- Groupes par topic (max 5-6 hashtags par groupe)
- Génération IA basée sur description + plateforme
- Optimisation marché marocain (FR/AR)
- Copier en un clic, intégration dans le compositeur

### Boîte de réception unifiée
- Messages de toutes les plateformes
- Labels automatiques : positif / négatif / neutre / spam / toxique
- Détection de leads et de questions
- Réponse suggérée par l'IA
- Analyse batch avec détection de crise

### Compositeur de publications
- Multi-plateformes simultané (poster sur 5 plateformes à la fois)
- Types : Image, Vidéo, Carrousel, Reel, Story
- Sélection médias depuis la bibliothèque
- Sélection hashtags depuis la bibliothèque
- Génération de légendes IA (3-5 variantes)
- Auto-génération hashtags
- Scheduling avec calendrier

### Chatbot RAG
- Réponse automatique aux clients
- Base de connaissances personnalisable
- Ajout de documents de référence
- Support FR / AR / EN
- Détection d'intention + escalade humaine

### Monitoring temps réel
- Dashboard live avec refresh toutes les 15s
- État des workers Celery
- Distribution des sentiments
- File d'attente des publications
- KPIs globaux en temps réel

### Analytics & Data Science
- Prévision de croissance 90 jours (Prophet)
- Prédiction d'engagement avant publication
- Radar de performance multi-axes
- Tendances par type de contenu

---

## 🔧 Configuration

```env
# .env — variables critiques
ANTHROPIC_API_KEY=sk-ant-...        # Claude Sonnet (obligatoire pour IA)
SECRET_KEY=...                       # Min 32 chars (obligatoire)
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://redis:6379/0

# Tokens plateformes (optionnel — mode mock sinon)
INSTAGRAM_ACCESS_TOKEN=...
FACEBOOK_ACCESS_TOKEN=...
TWITTER_ACCESS_TOKEN=...
LINKEDIN_ACCESS_TOKEN=...
TIKTOK_ACCESS_TOKEN=...
```

---

## 🧪 Tests

```bash
cd backend
pytest tests/ -v --cov=. --cov-report=term-missing
```

## 🤗 Datasets via Hugging Face

Pour rester sur `conda` et éviter Kaggle, le projet peut maintenant récupérer les datasets directement depuis Hugging Face.

```bash
conda activate mon_projet311
cd backend
python scripts/download_hf_datasets.py
```

Téléchargement ciblé :

```bash
conda activate mon_projet311
cd backend
python scripts/download_hf_datasets.py sentiment140 toxic
python scripts/download_hf_datasets.py instagram
```

Mappings utilisés :

- `sentiment140` -> `stanfordnlp/sentiment140`
- `toxic` -> `thesofakillers/jigsaw-toxic-comment-classification-challenge`
- `instagram` -> `vargr/main_instagram`

Notes :

- `sentiment140` remplace `kazanova/sentiment140`.
- `toxic` remplace le téléchargement Kaggle de `jigsaw-toxic-comment-classification-challenge`.
- Pour Instagram, Hugging Face ne propose pas le même miroir que `shmalex/instagram-dataset`; le script utilise `vargr/main_instagram`, qui contient bien des colonnes utiles comme `likes`, `comments` et `followers`.
- Les fichiers sont stockés dans `backend/data/datasets/`.

---

## 📦 Stack technique

**Backend** : FastAPI · SQLAlchemy Async · Celery · Redis · PostgreSQL · Elasticsearch · Alembic  
**IA/ML** : Claude Sonnet · BERT Multilingual · XGBoost · Prophet  
**Frontend** : React 18 · TypeScript · Tailwind CSS · Recharts · Zustand · React Router  
**Infra** : Docker Compose · Nginx · S3-compatible · Flower · ngrok
