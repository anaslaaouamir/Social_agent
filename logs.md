# Logs des changements

Date: 2026-05-12

## Dataset sentiment

- Ajout du nouveau dataset local:
  - `backend/data/datasets/sentiment_quadrilingual_3333.csv`
- Suppression des anciens dossiers de datasets locaux dans `backend/data/datasets`:
  - `instagram`
  - `spam_comments`
  - `toxic`
- Etat actuel de `backend/data/datasets`:
  - seul `sentiment_quadrilingual_3333.csv` est conserve.

## Modele BERT sentiment

- Extraction du nouveau modele fine-tune depuis:
  - `C:\Users\lalib\Downloads\mbert_models_selective.zip`
- Destination du modele utilise par le backend:
  - `backend/data/models/mbert_sentiment_finetuned`
- Le modele contient les labels:
  - `negative`
  - `neutral`
  - `positive`
- Le pipeline NLP existant pointe deja vers ce dossier via `SENTIMENT_MODEL_DIR`, donc le nouveau modele remplace l'ancien modele BERT sentiment local.

## Adaptations code

### `backend/services/dataset_loader.py`

- Ajout de la constante:
  - `QUADRILINGUAL_SENTIMENT_CSV = DATASET_DIR / "sentiment_quadrilingual_3333.csv"`
- Ajout de la fonction:
  - `load_quadrilingual_sentiment()`
- Cette fonction:
  - lit uniquement le CSV quadrilingue local;
  - valide les colonnes `text` et `sentiment_label`;
  - nettoie le texte;
  - garde seulement les labels `negative`, `neutral`, `positive`;
  - retourne les colonnes `text` et `sentiment_label`.
- Suppression du fallback Sentiment140:
  - plus de telechargement `stanfordnlp/sentiment140`;
  - plus de lecture `sentiment140.zip`;
  - suppression de l'import `zipfile`.
- `load_sentiment140()` reste disponible seulement pour compatibilite, mais charge maintenant le CSV quadrilingue local.

### `backend/scripts/train_mbert.py`

- Le script d'entrainement sentiment utilise maintenant:
  - `load_quadrilingual_sentiment`
- L'ancien import:
  - `load_sentiment140`
  a ete remplace pour le fine-tuning sentiment.
- La description du script a ete ajustee:
  - de `local/available project datasets`
  - vers `local project datasets`.

## Verifications faites

- Chargement du dataset quadrilingue OK:
  - `3333` lignes
  - `neutral: 1123`
  - `positive: 1106`
  - `negative: 1104`
- Compilation Python OK pour:
  - `backend/services/dataset_loader.py`
  - `backend/services/nlp_pipeline.py`
  - `backend/scripts/train_mbert.py`
- Resolution du chemin modele sentiment OK:
  - `data/models/mbert_sentiment_finetuned`

## Note environnement

- Le test d'inference complet n'a pas pu charger `transformers` dans l'environnement Python actif.
- Dans l'environnement backend avec `backend/requirements.txt` installe, le pipeline chargera le modele local `mbert_sentiment_finetuned`.

## Donnees/modeles non supprimes

- `backend/data/models/mbert_toxic_finetuned` est encore present car il correspond au modele toxicite, pas a l'ancien modele BERT sentiment.
- `backend/data/models/engagement_model.pkl` est encore present car il correspond au modele d'engagement, pas au sentiment.
- `backend/data/models/training_logs` est encore present pour les logs d'entrainement.

---

Date: 2026-05-13

## Optimisation du pipeline NLP

Fichier modifie:

- `backend/services/nlp_pipeline.py`

Changements appliques:

- Ajout de `_clean_text()` pour normaliser les textes avant inference:
  - suppression des repetitions de plus de 3 caracteres;
  - nettoyage des espaces en debut/fin de texte.
- Integration du nettoyage dans `process()` des le debut du traitement.
- Integration du nettoyage avant les appels aux modeles sentiment et toxicite.
- Simplification de `analyze_sentiment()`:
  - suppression du calcul `weighted_rating` par etoiles;
  - selection directe du resultat avec le score le plus eleve;
  - mapping explicite vers `negative`, `neutral`, `positive`;
  - fallback vers `neutral` si le label retourne n'est pas reconnu.
- Ajustement de `detect_toxic()`:
  - seuil modele passe de `0.45` a `0.7`;
  - seuil heuristique passe aussi de `0.45` a `0.7`.

Verification:

- Compilation Python OK:
  - `python -m py_compile backend/services/nlp_pipeline.py`

---

Date: 2026-05-13

## Alignement final des labels mBERT

Fichier modifie:

- `backend/services/nlp_pipeline.py`

Changements appliques:

- Ajustement de `_clean_text()` pour etre moins agressif avec la Darija latine:
  - les repetitions de 4 caracteres ou plus sont reduites a 2 caracteres;
  - les doubles lettres naturelles comme `llah` ou `bzzaf` sont conservees.
- Mise a jour de `analyze_sentiment()` pour suivre le mapping mBERT 3 classes:
  - `LABEL_0` -> `negative`;
  - `LABEL_1` -> `neutral`;
  - `LABEL_2` -> `positive`.
- Conservation de la compatibilite avec les labels directs du fichier `config.json`:
  - `NEGATIVE`;
  - `NEUTRAL`;
  - `POSITIVE`.
- Retour du score sentiment en polarite:
  - negatif: `-confidence`;
  - neutre: `0.0`;
  - positif: `+confidence`.
- Simplification de `detect_toxic()` pour les modeles binaires:
  - detection de `LABEL_1` ou `toxic`;
  - seuil conserve a `0.7`;
  - retour non-toxique si aucun label toxique reconnu.

Verification:

- Compilation Python OK:
  - `python -m py_compile backend/services/nlp_pipeline.py`

---

Date: 2026-05-13

## Suppression propre de Spark

Fichiers/dossiers modifies:

- `spark/`
- `commandes.md`

Changements appliques:

- Suppression du dossier `spark` du projet.
- Suppression du fichier Spark suivi par Git:
  - `spark/jobs/stream_processor.py`
- Nettoyage de la mention restante dans `commandes.md`:
  - le titre `stack sans Kafka/Spark` devient `stack locale`.

Verification:

- Recherche globale OK:
  - aucune occurrence restante de `spark`, `pyspark`, `Spark` ou `stream_processor` hors `logs.md`.
- `docker-compose.yml` ne contient deja plus de service Spark.
- `backend/requirements.txt` ne contient pas de dependance PySpark.

---

Date: 2026-05-13

## Correction affichage des reponses Inbox

Fichiers modifies:

- `frontend/src/pages/InboxPage.tsx`
- `backend/api/routes/dm.py`

Changements appliques:

- Suppression du message exemple code en dur dans la conversation Inbox:
  - retrait de la bulle `Bonjour, merci pour votre message...`;
  - retrait du texte `Exemple de reponse valide dans la fenetre 24h`.
- Suppression de la fonction frontend `validReplyExample()`.
- Apres un envoi reussi depuis l'Inbox:
  - ajout immediat de la reponse dans la conversation locale;
  - la bulle envoyee est marquee comme message de la Page;
  - le champ de saisie est vide apres succes.
- Augmentation de l'historique Facebook charge par conversation:
  - passage a `messages.limit(100)` dans l'appel Graph API.

Verification:

- Build frontend OK:
  - `npm.cmd run build`

## 2026-05-14 - Mediatheque par groupes et selection propre dans la creation de publication

Fichiers modifies:

- `frontend/src/pages/MediaLibraryPage.tsx`
- `frontend/src/pages/CreatePostPage.tsx`

Changements:

- Remplacement des categories fixes de la mediatheque par des groupes libres crees par l'utilisateur.
- Conservation de la compatibilite avec les anciens medias: l'ancienne valeur `category` devient automatiquement un groupe.
- Ajout d'un bouton `Nouveau groupe` dans la mediatheque.
- L'ajout d'un media demande maintenant le groupe cible au lieu d'une categorie.
- Dans `Nouvelle publication`, la bibliotheque media s'ouvre avec des groupes et permet de selectionner plusieurs medias avant de fermer.
- Dans `Nouvelle publication`, les hashtags de bibliotheque s'affichent par groupe selectionnable.
- La generation IA de hashtags utilise d'abord `/api/hashtags/generate`, qui tient compte des tendances serveur, puis garde `/recommend` comme fallback.

Verification:

- Build frontend OK:
  - `npm.cmd run build`

## 2026-05-14 - Verification LLM des sentiments negatifs

Fichier modifie:

- `backend/services/nlp_pipeline.py`

Changements:

- Ajout d'une deuxieme verification Hugging Face quand mBERT classe un texte en `negative`.
- Le LLM ne s'execute que pour les labels negatifs afin de rester leger.
- Le prompt demande de choisir uniquement entre:
  - `negative`;
  - `neutral`.
- Une demande neutre de type prix, contact, processus, devis ou information peut etre corrigee en `neutral`.
- Une vraie plainte, insatisfaction, accusation, colere ou perte de temps reste `negative`.
- Si `HUGGING_FACE_API` n'est pas configure ou si l'appel echoue, le pipeline garde le resultat mBERT + couche metier existante.

Note hashtags:

- Les tendances hashtags actuelles ne viennent pas encore des APIs live des reseaux sociaux.
- `/api/hashtags/trending` utilise une base interne dans `HashtagIntelligenceSystem`.
- `/api/hashtags/generate` utilise le LLM central pour generer des hashtags.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/services/nlp_pipeline.py`

## 2026-05-14 - Fallback final JSON contenu et silence HF indisponible

Fichiers modifies:

- `backend/modules/content_generation.py`
- `backend/services/nlp_pipeline.py`

Changements:

- Ajout d'un fallback final `_best_effort_parse_response` pour la generation de contenu.
- Si le JSON LLM reste invalide apres reparation, le backend extrait quand meme:
  - captions;
  - hashtags.
- Cela evite de tomber directement sur le fallback generique quand le LLM renvoie un JSON casse avec `Unterminated string`.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/modules/content_generation.py backend/services/nlp_pipeline.py`

## 2026-05-14 - Reparation parsing JSON generation contenu

Fichier modifie:

- `backend/modules/content_generation.py`

Changements:

- Amelioration de `_parse_response` pour les reponses LLM JSON presque valides.
- Extraction du premier objet JSON equilibre dans une reponse LLM.
- Reparation des retours ligne, retours chariot et tabs non echappes uniquement a l'interieur des chaines JSON.
- Objectif: eviter les erreurs `Unterminated string` quand une caption LLM contient un retour ligne brut.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/modules/content_generation.py`



## 2026-05-14 - Hashtags bases sur tendances plateforme + LLM

Fichier modifie:

- `backend/api/routes/hashtags.py`

Changements:

- Ajout d'une extraction de tendances hashtags depuis les posts live des comptes connectes.
- Les hashtags observes dans les captions recentes sont scores avec:
  - frequence;
  - likes;
  - commentaires;
  - partages.
- `/api/hashtags/trending` retourne maintenant:
  - d'abord les tendances observees dans les posts live connectes (`observed_live_posts`);
  - puis le fallback marche interne (`internal_market_baseline`) si les APIs ne fournissent pas assez de donnees.
- `/api/hashtags/generate` envoie maintenant au LLM:
  - caption;
  - sujet;
  - plateforme;
  - tendances live observees;
  - fallback marche interne.
- Le LLM doit utiliser les tendances pertinentes pour le caption et ignorer les tendances non pertinentes.
- La reponse inclut maintenant:
  - `hashtags`;
  - `performance_score`;
  - `trend_context`;
  - `trend_sources`.

Note:

- Les plateformes ne fournissent pas toutes une API officielle de hashtags trending.
- Quand l'API officielle n'existe pas ou n'est pas disponible, le projet utilise les hashtags observes dans les posts live des comptes connectes comme signal reel de tendance disponible.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/api/routes/hashtags.py`

## 2026-05-14 - Fallback Hugging Face verification sentiment

Fichier modifie:

- `backend/services/nlp_pipeline.py`

Changements:

- Remplacement du modele de verification sentiment `mistralai/Mistral-7B-Instruct-v0.3`, indisponible sur l'endpoint Hugging Face actuel.
- Ajout d'une liste de modeles legers pour la verification des labels negatifs:
  - `google/flan-t5-small`;
  - `google/flan-t5-base`.
- Si le premier modele est indisponible, le pipeline essaie le suivant.
- Si tous les modeles HF echouent, le pipeline garde le resultat mBERT + couche metier et ne bloque pas l'analyse.
- Le prompt a ete simplifie pour une classification stricte `negative` ou `neutral`.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/services/nlp_pipeline.py`

## 2026-05-14 - Question processus neutre et badge humain requis

Fichiers modifies:

- `backend/services/nlp_pipeline.py`
- `frontend/src/pages/InboxPage.tsx`

Changements:

- Ajout des termes de demande/processus dans la couche metier NLP:
  - quoi;
  - processus;
  - procedure/procedure;
  - methode/methode;
  - travail/travailler;
  - agent/agents.
- Une question comme `c'est quoi votre processus de travail sur les agents` n'est plus forcee en negatif si aucun feedback negatif explicite n'est present.
- Suppression du doublon visuel `Humain requis` affiche une deuxieme fois sous le badge `Auto-repondu`.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/services/nlp_pipeline.py`
- Build frontend OK:
  - `npm.cmd run build`

## 2026-05-14 - Fallback LLM si Claude refuse la cle

Fichier modifie:

- `backend/services/llm_orchestrator.py`

Changements:

- Ajout de constantes de modeles pour Claude et Hugging Face.
- Si Claude renvoie une erreur pendant l'appel LLM et que `HUGGING_FACE_API` est configure, l'orchestrateur bascule automatiquement vers `mistralai/Mistral-7B-Instruct-v0.3`.
- Le modele retourne dans `LLMResponse.model` correspond maintenant au provider reellement utilise.
- La cle Claude invalide ne bloque plus l'auto-reponse RAG si le fallback Hugging Face est disponible.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/services/llm_orchestrator.py`

## 2026-05-14 - Alertes equipe depuis auto-reponse RAG

Fichier modifie:

- `backend/api/routes/nlp.py`

Changements:

- L'endpoint `/api/nlp/rag-autoreply` cree maintenant une alerte equipe quand une auto-reponse RAG necessite une revue humaine.
- Declenchement de l'alerte si:
  - le score RAG est sous le seuil;
  - l'envoi plateforme echoue;
  - la reponse IA contient une transmission au service client, une demande de devis ou une consultation humaine.
- L'alerte est dedupliquee via `ensure_activity_alert` avec `target_key`.
- L'alerte contient:
  - canal DM/commentaire;
  - plateforme;
  - message client;
  - reponse IA envoyee;
  - score RAG;
  - seuil configure;
  - lien d'action vers l'Inbox.
- La reponse API expose maintenant `requires_team_review`.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/api/routes/nlp.py`

## 2026-05-14 - Anti-doublon auto-reponse et neutralisation questions

Fichiers modifies:

- `frontend/src/pages/InboxPage.tsx`
- `backend/services/nlp_pipeline.py`

Changements:

- Correction de l'anti-doublon des auto-reponses RAG:
  - ancienne cle basee surtout sur `message.id`;
  - nouvelle cle stable basee sur compte, plateforme, conversation/cible, timestamp et texte normalise.
- Compatibilite avec les anciennes cles `rag_autoRepliedIds` pour ne pas perdre les messages deja traites.
- Les statuts `Humain requis` utilisent aussi la nouvelle cle stable.
- Les questions metier neutres ne sont plus forcees en negatif si elles ne contiennent pas de feedback explicitement negatif:
  - combien;
  - comment;
  - prix;
  - tarif;
  - devis;
  - contact;
  - contacter;
  - WhatsApp.
- Les vrais retours negatifs restent negatifs:
  - pas aime;
  - gaspille/gaspille mon temps;
  - perdu mon temps.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/services/nlp_pipeline.py`
- Build frontend OK:
  - `npm.cmd run build`

## 2026-05-14 - Correction scoring RAG

Fichiers modifies:

- `backend/services/rag_service.py`
- `frontend/src/pages/InboxPage.tsx`
- `frontend/src/components/RagFloatingPanel.tsx`

Changements:

- Correction du calcul de pertinence RAG pour Chroma en distance cosine.
- Ancien calcul: `1 - distance`, trop severe pour cosine.
- Nouveau calcul: `1 - distance / 2`, borne entre `0` et `1`.
- Ajout de la distance brute dans les documents retournes par `retrieve`.
- Ajout du score de confiance dans l'historique des auto-reponses RAG.
- Affichage du score dans le panneau RAG pour comprendre pourquoi une reponse est envoyee ou bascule en `Humain requis`.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/services/rag_service.py`
- Build frontend OK:
  - `npm.cmd run build`

## 2026-05-14 - Rafraichissement reactif Inbox

Fichier modifie:

- `frontend/src/pages/InboxPage.tsx`

Changements:

- La page Messages rafraichit maintenant les DMs en arriere-plan toutes les 8 secondes.
- Les commentaires du post selectionne rafraichissent aussi toutes les 8 secondes.
- Les posts restent sur un intervalle plus leger de 45 secondes.
- Ajout d'un refresh immediat quand la fenetre reprend le focus ou quand l'onglet redevient visible.
- Ajout de gardes `useRef` pour eviter les requetes de refresh qui se chevauchent.
- Le cache existant reste utilise pour ne pas vider l'ecran pendant les refreshs.

Verification:

- Build frontend OK:
  - `npm.cmd run build`

## 2026-05-14 - Correction scroll panneau RAG

Fichier modifie:

- `frontend/src/components/RagFloatingPanel.tsx`

Changements:

- Le panneau `RAG Assistant` est maintenant scrollable sur toute sa hauteur.
- La zone basse `Base de connaissance` / upload fichiers / ajout de texte reste accessible meme quand les reglages du haut prennent beaucoup d'espace.
- Ajout de `overflowY: auto` sur le panneau complet et retrait du scroll limite a la sous-zone interne.

Verification:

- Build frontend OK:
  - `npm.cmd run build`

## 2026-05-14 - Ameliorations auto-reponse RAG

Fichiers modifies:

- `frontend/src/components/RagFloatingPanel.tsx`
- `frontend/src/pages/InboxPage.tsx`
- `frontend/src/lib/api.ts`
- `backend/api/routes/nlp.py`

Changements:

- Remplacement visuel du bouton flottant RAG par une icone robot.
- Ajout d'un badge de statut sur l'icone flottante:
  - vert quand l'auto-reponse est active;
  - gris quand elle est desactivee.
- Ajout d'un toggle d'auto-reponse par compte connecte avec stockage local `rag_account_<account_id>`.
- Ajout d'un slider `Seuil de confiance` stocke dans `rag_confidenceThreshold`.
- Ajout de templates fallback par langue:
  - francais;
  - arabe;
  - darija;
  - anglais.
- Ajout d'un historique local des 10 dernieres auto-reponses dans le panneau RAG via `rag_autoReplyHistory`.
- L'Inbox transmet maintenant au backend:
  - `language: auto`;
  - `confidence_threshold`;
  - `fallback_templates`;
  - les informations de reponse DM/commentaire.
- Les auto-reponses DM et commentaires respectent maintenant:
  - le scope DMs/commentaires;
  - le toggle global;
  - le toggle par compte;
  - la protection `rag_autoReplyEnabledAt`;
  - la deduplication `rag_autoRepliedIds`.
- Ajout du badge `Humain requis` quand la confiance RAG est trop basse ou quand l'envoi plateforme echoue.
- Ajout du stockage local `rag_humanRequiredIds` pour garder le statut humain requis visible apres rafraichissement.
- Backend `/api/nlp/rag-autoreply`:
  - detecte automatiquement la langue avec `nlp_pipeline.detect_language`;
  - ajoute une normalisation simple Darija/Arabe;
  - repond dans la langue detectee;
  - compare la pertinence RAG au seuil fourni;
  - utilise le fallback de langue quand le seuil n'est pas atteint;
  - tente l'envoi reel via `_send_unified_reply` pour DMs et commentaires quand les identifiants sont fournis.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend/api/routes/nlp.py`
- Build frontend OK:
  - `npm.cmd run build`

---
Date: 2026-05-13

## Orchestration Claude LangGraph avec memoire durable

Fichiers modifies:

- `backend/services/llm_orchestrator.py`
- `backend/models/domain.py`
- `backend/alembic/versions/0004_add_llm_memory_entries.py`
- `backend/api/main.py`
- `backend/modules/content_generation.py`
- `backend/services/rag_service.py`
- `backend/api/routes/content.py`
- `backend/api/routes/nlp.py`
- `backend/api/routes/dm.py`
- `backend/api/routes/hashtags.py`
- `backend/requirements.txt`
- `frontend/src/lib/api.ts`
- `frontend/src/pages/HashtagLibraryPage.tsx`
- `frontend/src/pages/InboxPage.tsx`

Changements:

- Ajout d'un service central `ClaudeLangGraphOrchestrator` pour concentrer les appels Claude au backend.
- Ajout d'une memoire durable SQL via la table `llm_memory_entries`.
- Ajout d'une migration Alembic `0004_add_llm_memory_entries`.
- Ajout de `langgraph==0.1.9` dans les dependances backend.
- La generation de contenu passe maintenant par l'orchestrateur central avec session memoire par utilisateur.
- Le chat RAG utilise l'orchestrateur central avec contexte documentaire et memoire durable.
- La generation de hashtags IA ne contacte plus Claude depuis le frontend; elle passe par `/api/hashtags/generate`.
- L'analyse IA manuelle des DMs ne contacte plus Claude depuis le frontend; elle passe par `/api/dm/analyze`.
- Les appels Anthropic directs hors orchestrateur ont ete supprimes du chemin actif.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend\services\llm_orchestrator.py backend\services\rag_service.py backend\modules\content_generation.py backend\api\routes\content.py backend\api\routes\dm.py backend\api\routes\hashtags.py backend\api\routes\nlp.py backend\models\domain.py backend\api\main.py backend\alembic\versions\0004_add_llm_memory_entries.py`
- Recherche OK:
  - `rg "api\.anthropic\.com|fetch\('https://api\.anthropic|AsyncAnthropic|Anthropic\(|messages\.create" backend frontend\src -S`
  - resultat attendu: uniquement `backend/services/llm_orchestrator.py` contient l'appel Claude direct.
- Build frontend OK:
  - `npm.cmd run build`

---
Date: 2026-05-13

## Compteur alertes et doublons DM

Fichiers modifies:

- `backend/services/social_activity_store.py`
- `backend/api/routes/alerts.py`
- `frontend/src/components/layout/AppLayout.tsx`
- `frontend/src/pages/AlertsPage.tsx`

Changements:

- Le nombre rouge a cote de `Alertes` se met maintenant a jour selon le nombre reel d'alertes non acquittees.
- Le compteur se rafraichit au chargement, toutes les 30 secondes, et apres une action sur les alertes.
- Les alertes retournees par l'API sont dedupliquees par compte, type d'alerte et `target_key`.
- Un DM negatif/toxique utilise maintenant une cle stable par conversation, sinon par expediteur, pour eviter plusieurs alertes identiques pour le meme chat.
- Les anciens doublons ne sont pas supprimes de la base, mais ils sont masques dans l'affichage et dans le compteur.

Verification:

- Compilation backend OK:
  - `python -m py_compile services\social_activity_store.py api\routes\alerts.py`
- Build frontend OK:
  - `npm.cmd run build`

---

Date: 2026-05-13

## Cache UI et rafraichissement discret

Fichiers modifies:

- `frontend/src/store/index.ts`
- `frontend/src/pages/PostsPage.tsx`
- `frontend/src/pages/InboxPage.tsx`
- `frontend/src/pages/AlertsPage.tsx`

Objectif:

- Garder les donnees deja telechargees visibles quand l'utilisateur change de page.
- Eviter qu'un retour depuis une alerte affiche une page vide en attendant un nouveau fetch.
- Rafraichir les donnees en arriere-plan sans interrompre l'utilisateur.

Changements appliques:

- Ajout de `useResourceCache` dans le store frontend:
  - cache en memoire par cle;
  - stockage de `data` et `updatedAt`;
  - non persistant apres refresh navigateur, volontairement.
- `PostsPage` utilise maintenant un cache par compte et filtre:
  - les posts restent visibles au retour sur la page;
  - refresh discret toutes les `45s` pour le live;
  - refresh discret toutes les `90s` pour les filtres DB.
- `AlertsPage` utilise maintenant un cache par filtre:
  - les alertes restent visibles au retour;
  - refresh discret toutes les `30s`;
  - acquitter une alerte met aussi le cache a jour.
- `InboxPage` utilise maintenant un cache pour:
  - DMs par compte;
  - posts live par compte;
  - commentaires par post.
- Les DMs/posts/commentaires restent affiches pendant le refresh arriere-plan.
- Les reponses DM ajoutees localement sont aussi synchronisees dans le cache pour rester visibles si l'utilisateur navigue ailleurs puis revient.

Verification:

- Build frontend OK:
  - `npm.cmd run build`

Note:

- Le cache est volontairement en memoire:
  - il survit aux changements de pages;
  - il ne survit pas au refresh navigateur complet;
  - la base PostgreSQL reste la source de verite durable.

---

Date: 2026-05-13

## Persistance activite live et alertes actionnables

Fichiers modifies:

- `backend/services/social_activity_store.py`
- `backend/api/routes/posts.py`
- `backend/api/routes/dm.py`
- `backend/api/routes/alerts.py`
- `backend/api/routes/monitoring.py`
- `backend/core/runtime_state.py`
- `backend/api/main.py`
- `frontend/src/pages/AlertsPage.tsx`
- `frontend/src/pages/InboxPage.tsx`
- `frontend/src/pages/MonitoringPage.tsx`

Changements appliques:

- Ajout du service `social_activity_store.py` pour centraliser:
  - persistance des posts live dans `posts`;
  - persistance des commentaires live analyses dans `comments`;
  - persistance des DMs/conversations live dans `direct_messages`;
  - creation d'alertes dedupliquees dans `alerts`.
- Les posts live affiches via `/api/posts/live/feed` sont maintenant upsertes en base.
- Les commentaires live affiches via `/api/posts/live/comments` sont maintenant:
  - analyses par le pipeline NLP;
  - stockes en base;
  - relies au post stocke;
  - enrichis avec `stored_comment_id`.
- Les DMs live affiches via `/api/dm/live` sont maintenant:
  - analyses;
  - stockes en base;
  - enrichis avec `stored_dm_id`.
- Creation automatique d'alertes pour:
  - commentaire negatif;
  - commentaire toxique;
  - DM negatif;
  - DM toxique;
  - risque de crise sur un post quand la proportion de commentaires negatifs/toxiques depasse le seuil.
- Les alertes contiennent maintenant `metadata` et `action_url`:
  - ouverture directe vers l'Inbox messages;
  - ouverture directe vers l'Inbox posts/commentaires.
- La page Alertes affiche un bouton `Ouvrir` quand une alerte contient une destination.
- L'Inbox lit les parametres d'URL:
  - `tab=messages`;
  - `tab=posts`;
  - `dm=...`;
  - `post=...`;
  - `filter=negative`.
- Suppression de la notion runtime `alert_consumer`:
  - remplacee par `celery_monitor`;
  - le monitoring affiche maintenant `Celery Monitor`.

Architecture confirmee:

- Le suivi commentaires/alertes passe par Celery:
  - `services.comment_monitor.monitor_all_accounts`;
  - `services.comment_monitor.monitor_account`;
  - planification dans `core/celery_app.py`.

Verification:

- Compilation backend OK:
  - `python -m py_compile services/social_activity_store.py api/routes/posts.py api/routes/dm.py api/routes/alerts.py api/routes/monitoring.py core/runtime_state.py api/main.py`
- Recherche OK:
  - plus de `alert_consumer` ou `Alert Consumer` dans `backend` / `frontend/src`.
- Build frontend OK:
  - `npm.cmd run build`

Note:

- L'orchestration Claude par LangGraph avec memoire durable reste un chantier separe a faire proprement:
  - service LLM central;
  - graphe LangGraph;
  - memoire conversationnelle persistante;
  - remplacement des appels frontend directs a Anthropic.

---

Date: 2026-05-13

## Optimisation programmation de post

Fichiers modifies:

- `backend/services/ml_engagement.py`
- `backend/api/routes/timing.py`
- `frontend/src/pages/CreatePostPage.tsx`

Probleme identifie:

- La recommandation timing rendait la page de creation/programmmation lourde:
  - le frontend relancait `/api/timing/predict` pendant les changements de legende et hashtags;
  - le backend calculait la heatmap en appelant `predict()` pour chaque heure;
  - `predict()` relancait lui-meme une recherche du meilleur timing sur la semaine.

Changements appliques:

- Ajout de `predict_rate()` dans `ml_engagement.py` pour calculer uniquement le score d'une case timing.
- `api/routes/timing.py` utilise maintenant `predict_rate()` pour construire la heatmap.
- `CreatePostPage.tsx` ne relance plus le timing sur `caption.length` ou `hashtags.length`.
- Le timing se recalcule seulement quand:
  - le compte selectionne change;
  - le type de contenu change;
  - la liste des comptes disponibles change.

Verification:

- Compilation backend OK:
  - `python -m py_compile services/ml_engagement.py api/routes/timing.py`
- Test manuel modele OK:
  - `predict_rate()`
  - `predict()`
- Build frontend OK:
  - `npm.cmd run build`

---

Date: 2026-05-13

## Correction routes live posts/commentaires

Fichier modifie:

- `backend/api/routes/posts.py`

Probleme identifie:

- Les routes live:
  - `/api/posts/live/feed`
  - `/api/posts/live/comments`
  etaient declarees apres la route dynamique:
  - `/api/posts/{post_id}`
- Selon l'ordre de resolution FastAPI, `live` pouvait etre interprete comme un `post_id`, ce qui pouvait empecher l'affichage des posts live et donc des commentaires associes.

Changement applique:

- Deplacement des routes `/live/feed` et `/live/comments` avant les routes dynamiques `/{post_id}`.
- Aucune logique de recuperation Facebook/Instagram n'a ete changee.

Verification:

- Ordre des routes verifie:
  - `/live/feed`
  - `/live/comments`
  - `/{post_id}`
- Compilation backend OK:
  - `python -m py_compile api/routes/posts.py`

---

Date: 2026-05-13

## Suppression reach et fallbacks anciens modeles

Fichiers modifies:

- `backend/services/ml_engagement.py`
- `backend/services/nlp_pipeline.py`
- `backend/api/routes/nlp.py`
- `backend/api/routes/posts.py`
- `frontend/src/pages/PostsPage.tsx`
- `frontend/src/pages/InboxPage.tsx`
- `backend/tests/test_all_modules.py`

Changements appliques:

- Suppression complete de la prediction de reach dans le modele engagement:
  - plus de champ `predicted_reach`;
  - plus de metriques `reach_mae` / `reach_r2`;
  - plus d'affichage reach dans les pages Publications et Inbox.
- Le modele engagement predit maintenant seulement:
  - `engagement_rate`;
  - meilleur jour/heure de publication;
  - type de contenu recommande;
  - importance des features.
- Suppression du fallback heuristique dans `ml_engagement.py`:
  - si le modele engagement/timing n'est pas entraine, une erreur explicite est levee;
  - les anciens fichiers `.pkl` sont ignores s'ils ne portent pas la cible `engagement_timing`.
- Re-entrainement de `backend/data/models/engagement_model.pkl` avec `Instagram_Analytics.csv`.
- Suppression des anciens fallbacks HuggingFace dans `nlp_pipeline.py`:
  - plus de fallback vers `nlptown/bert-base-multilingual-uncased-sentiment`;
  - plus de fallback vers `unitary/multilingual-toxic-xlm-roberta`;
  - les modeles sentiment/toxicite utilisent uniquement les dossiers locaux fine-tunes.
- Suppression de l'heuristique toxicite par mots-cles:
  - plus de `_detect_toxic_heuristic`;
  - plus de dictionnaire `_toxic_keywords`.

Evaluation du modele engagement/timing re-entraine:

- `engagement_mae`: `4.723269667732753e-06`
- `engagement_r2`: `0.999994750522921`
- `r2`: `0.999994750522921`
- `cv_r2_mean`: `0.9999661336629488`
- `cv_r2_std`: `3.592353468600599e-05`
- `accuracy`: `0.8893333333333333`
- `f1_weighted`: `0.8889758419458444`
- `n_train`: `23999`
- `n_test`: `6000`
- `real_data_rows`: `29999`

Verification:

- Compilation backend OK:
  - `python -m py_compile services/ml_engagement.py services/dataset_loader.py services/nlp_pipeline.py api/routes/nlp.py api/routes/posts.py api/routes/timing.py`
- Tests cibles OK:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_all_modules.py -q -k "engagement_predictor_model_prediction or dataset_loader"`
- Recherche OK:
  - plus de `predicted_reach`, `predictedReach`, `reach_mae`, `reach_r2`, `_heuristic_predict`, `nlptown`, `unitary/multilingual-toxic` dans les fichiers projet cibles.
- Build frontend OK:
  - `npm.cmd run build`
- Compilation backend OK:
  - `python -m py_compile backend/api/routes/dm.py`
- Recherche OK:
  - plus de message exemple code en dur dans `InboxPage.tsx`.

---

Date: 2026-05-13

## Couche metier sentiment pour demandes neutres

Fichier modifie:

- `backend/services/nlp_pipeline.py`

Changements appliques:

- Ajout d'une couche d'ajustement apres le modele BERT sentiment.
- Ajout de `_looks_like_request_or_requirement()` pour detecter les messages de demande ou de besoin:
  - exemples: `je veux`, `je cherche`, `besoin`, `i want`, `we need`, `bghit`, `khasni`.
- Ajout de `_has_explicit_negative_feedback()` pour conserver les vrais avis negatifs:
  - exemples: `nul`, `arnaque`, `horrible`, `probleme`, `scam`, `bad`, `khayb`.
- Ajout de `_adjust_sentiment_for_business_context()`:
  - si BERT predit `negative`;
  - et que le message ressemble a une demande/exigence;
  - et qu'il ne contient pas de vrai feedback negatif explicite;
  - alors le sentiment est converti en `neutral`.

Objectif:

- Eviter que les negations descriptives ou exigences utilisateur soient classees comme negatives.
- Exemple vise:
  - `je veux un agent qui n'invente pas...` -> `neutral`.

Verification:

- Compilation Python OK:
  - `python -m py_compile backend/services/nlp_pipeline.py`
- Test mocke OK:
  - demande avec negation descriptive -> `neutral`;
  - vraie plainte `nul et horrible` -> `negative`;
  - message positif -> `positive`.

---

Date: 2026-05-13

## Nouveau modele engagement/reach/timing Instagram

Fichiers modifies:

- `backend/services/dataset_loader.py`
- `backend/services/ml_engagement.py`
- `backend/api/routes/nlp.py`
- `backend/api/routes/posts.py`
- `frontend/src/pages/CreatePostPage.tsx`
- `frontend/src/pages/PostsPage.tsx`
- `frontend/src/pages/InboxPage.tsx`
- `backend/tests/test_all_modules.py`

Donnees ajoutees localement:

- `backend/data/datasets/Instagram_Analytics.csv`
  - extrait depuis `C:\Users\lalib\Downloads\archive.zip`.

Modele entraine:

- `backend/data/models/engagement_model.pkl`


---
Date: 2026-05-13

## Orchestration Claude LangGraph avec memoire durable

Fichiers modifies:

- `backend/services/llm_orchestrator.py`
- `backend/models/domain.py`
- `backend/alembic/versions/0004_add_llm_memory_entries.py`
- `backend/api/main.py`
- `backend/modules/content_generation.py`
- `backend/services/rag_service.py`
- `backend/api/routes/content.py`
- `backend/api/routes/nlp.py`
- `backend/api/routes/dm.py`
- `backend/api/routes/hashtags.py`
- `backend/requirements.txt`
- `frontend/src/lib/api.ts`
- `frontend/src/pages/HashtagLibraryPage.tsx`
- `frontend/src/pages/InboxPage.tsx`

Changements:

- Ajout d'un service central `ClaudeLangGraphOrchestrator` pour concentrer les appels Claude au backend.
- Ajout d'une memoire durable SQL via la table `llm_memory_entries`.
- Ajout d'une migration Alembic `0004_add_llm_memory_entries`.
- Ajout de `langgraph==0.1.9` dans les dependances backend.
- La generation de contenu passe maintenant par l'orchestrateur central avec session memoire par utilisateur.
- Le chat RAG utilise l'orchestrateur central avec contexte documentaire et memoire durable.
- La generation de hashtags IA ne contacte plus Claude depuis le frontend; elle passe par `/api/hashtags/generate`.
- L'analyse IA manuelle des DMs ne contacte plus Claude depuis le frontend; elle passe par `/api/dm/analyze`.
- Les appels Anthropic directs hors orchestrateur ont ete supprimes du chemin actif.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend\services\llm_orchestrator.py backend\services\rag_service.py backend\modules\content_generation.py backend\api\routes\content.py backend\api\routes\dm.py backend\api\routes\hashtags.py backend\api\routes\nlp.py backend\models\domain.py backend\api\main.py backend\alembic\versions\0004_add_llm_memory_entries.py`
- Recherche OK:
  - `rg "api\.anthropic\.com|fetch\('https://api\.anthropic|AsyncAnthropic|Anthropic\(|messages\.create" backend frontend\src -S`
  - resultat attendu: uniquement `backend/services/llm_orchestrator.py` contient l'appel Claude direct.
- Build frontend OK:
  - `npm.cmd run build`

---
Date: 2026-05-14

## RAG Assistant flottant et auto-reponse

Fichiers modifies:

- `frontend/src/components/layout/AppLayout.tsx`
- `frontend/src/components/RagFloatingPanel.tsx`
- `frontend/src/pages/InboxPage.tsx`
- `frontend/src/lib/api.ts`
- `backend/api/routes/nlp.py`
- `backend/services/rag_service.py`
- `backend/services/llm_orchestrator.py`
- `backend/core/config.py`
- `.env.example`

Changements:

- Suppression de l'entree `Chatbot RAG` de la navigation laterale.
- Ajout du composant flottant `RagFloatingPanel` accessible depuis toutes les pages.
- Le panneau contient:
  - bouton flottant a droite;
  - panneau lateral 340px;
  - toggle `Reponse automatique` persiste dans `localStorage` avec la cle `rag_autoReply`;
  - scopes persistants `rag_scope_dms` et `rag_scope_comments`;
  - upload drag-and-drop de fichiers RAG;
  - ajout de texte manuel;
  - presets rapides;
  - liste et suppression des sources RAG.
- Montage global de `RagFloatingPanel` dans `AppLayout`.
- Ajout de l'endpoint `/api/nlp/rag-autoreply` pour generer une reponse RAG et, si les identifiants de reponse sont fournis, tenter l'envoi via les services plateforme existants.
- L'Inbox appelle l'auto-reponse RAG pour les nouveaux DMs/commentaires quand le toggle et le scope sont actifs.
- Les items auto-traites affichent un badge `Auto-repondu`.
- Protection contre les reponses massives sur anciens messages: seules les activites posterieures a `rag_autoReplyEnabledAt` sont traitees.
- Le modele d'embedding RAG est remplace par `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Ajout de `HUGGING_FACE_API` dans la configuration et `.env.example`.
- Ajout d'un fallback Hugging Face `mistralai/Mistral-7B-Instruct-v0.3` dans l'orchestrateur LLM lorsque Claude n'est pas configure.

Notes:

- L'auto-reponse tente l'envoi reel seulement lorsque `account_id`, `reply_mode`, `reply_target_id` et les infos necessaires sont disponibles.
- Sinon l'endpoint renvoie une reponse RAG avec `delivery_status=generated_only`, pour eviter d'envoyer au mauvais endroit.

Verification:

- Compilation backend OK:
  - `python -m py_compile backend\api\routes\nlp.py backend\services\rag_service.py backend\services\llm_orchestrator.py backend\core\config.py backend\api\routes\content.py backend\api\routes\dm.py`
- Recherche OK:
  - `rg "to: '/chatbot'|RAG Assistant|ragAutoReply|rag-autoreply|paraphrase-multilingual-MiniLM-L12-v2|HUGGING_FACE_API|_call_huggingface|rag_autoReply" frontend backend .env.example -S`
- Build frontend OK:
  - `npm.cmd run build`

---
Date: 2026-05-15

## Correction prediction timing et score engagement

Fichiers modifies:

- `backend/services/dataset_loader.py`
- `backend/services/ml_engagement.py`
- `backend/data/models/engagement_model.pkl`

Changements:

- Correction d'une fuite de cible dans `historical_avg_er`:
  - avant: `historical_avg_er` etait egal a `engagement_rate`;
  - maintenant: moyenne historique anterieure par compte, avec fallback global anterieur.
- Re-entrainement de `engagement_model.pkl` sur `Instagram_Analytics.csv`.
- Ajout d'un blend runtime pour le score d'engagement:
  - 80% taux historique du compte;
  - 20% prediction modele;
  - objectif: score absolu plus stable, modele utilise surtout pour les variations timing.




