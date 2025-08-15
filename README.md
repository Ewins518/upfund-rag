# upfund-rag

# RAG Microservices — Flask API + Streamlit UI (Pinecone)

Deux services **Docker** :

* **backend** : API Flask pour ingestion, retrieval et génération (RAG)
* **frontend** : UI **Streamlit** type chat (noir/blanc), upload de documents, historique de conversations

**Vector store** : Pinecone (serverless).
**Embeddings** : OpenAI
**Documents** acceptés : PDF / DOCX / TXT.

---

## 📦 Structure du repo

```
upfund-rag/
  backend/
    main.py
    rag_engine.py
    models.py
    ingestion.py
    requirements.txt
    Dockerfile
  frontend/
    app.py
    requirements.txt
    Dockerfile
  data/
    raw_documents/      # ingestion “bulk”
    user_uploads/       # fichiers uploadés depuis l’UI (/upload)
  docker-compose.yml
  .env.example
  README.md
```

---

## 🔑 Prérequis & Clés API

* Docker & Docker Compose
* Compte **Pinecone** (serverless)
* clé **OpenAI** 

Copie le fichier d’exemple et remplis les clés :

```bash
cp .env.example .env
```


> 💡 **Pinecone** : l’index est créé à la volée avec la bonne dimension, soit, 3072 pour OpenAI.

---

## 🚀 Démarrage

Depuis la racine du projet :

```bash
docker compose up --build -d
```

Ensuite :

1. Dépose tes docs “bulk” dans `data/raw_documents/`
2. Lance l’ingestion (création/rafraîchissement d’index) :

```bash
docker compose exec api python ingestion.py --docs_dir data/raw_documents --clear
```

3. Ouvre l’UI : [http://localhost:8501](http://localhost:8501)

> Tu peux aussi **uploader** des fichiers directement depuis l’UI (section “Uploads”) — ceux-là sont stockés dans `data/user_uploads/` et **indexés** à la volée.


## 🧱 Stack technique

* **Backend** : Python 3.11, Flask, Pydantic, Gunicorn
* **Vector store** : Pinecone (serverless)
* **Embeddings** : OpenAI (`text-embedding-3-large`)
* **LLM** : OpenAI (`gpt-4o-mini` par défaut) — configurable
* **Parsing** : `pypdf`, `python-docx`, `.txt` natif
* **Frontend** : Streamlit (chat minimaliste, noir/blanc, upload, historique)

---

## 🧩 Endpoints récap

* `GET /healthcheck` → status API + index + namespace
* `POST /ask` → `{question, k}` → `{answer, sources:[{file, chunk_id, score, snippet}]}`
* `POST /reindex` → `{docs_dir?, clear?}`
* `POST /upload` → `multipart/form-data` (`file=@doc.pdf`) → indexation incrémentale
* `GET /list_user_uploads` → `{"docs":[{"path","size"}]}`

---

## 🧯 Dépannage

* **`Namespace not found` / `Index not found`**
  → Vérifie `PINECONE_API_KEY`, `PINECONE_INDEX`, `PINECONE_REGION`. L’index est créé automatiquement si l’API a les droits.

* **`Vector ID must be ASCII`**
  → Les IDs vectoriels sont normalisés (slug + hash). Évite les caractères spéciaux dans les noms de fichiers quand possible.

* **Fichier DOCX “\~\$”**
  → Ce sont des **verrous Office** temporaires. Ils sont ignorés à l’ingestion.

* **Pas de nouveaux records après upload**
  → Regarde les logs backend (`docker compose logs -f api`). L’upload doit appeler `engine.index_file(save_path, base_dir=data/user_uploads)`.

* **L’UI ne voit pas les docs**
  → L’UI liste **uniquement** les fichiers uploadés via `/upload` (pas `raw_documents`). Côté Docker, assure-toi que `./data/user_uploads:/app/data/user_uploads:rw` est monté sur **api**.

---
