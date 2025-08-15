# upfund-rag

# RAG Microservices — Flask API + Streamlit UI (Pinecone)

## Demo Video

https://private-user-images.githubusercontent.com/74628423/478518468-fe3c7e26-c529-4ac3-baa8-9774172136ae.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NTUyNzk4NzYsIm5iZiI6MTc1NTI3OTU3NiwicGF0aCI6Ii83NDYyODQyMy80Nzg1MTg0NjgtZmUzYzdlMjYtYzUyOS00YWMzLWJhYTgtOTc3NDE3MjEzNmFlLm1wND9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNTA4MTUlMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjUwODE1VDE3MzkzNlomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPThmYTExNzVlNjg3ZmNiMjU2NDQ0MGNlMmFjNjAyYTg3OTg1NDQ3ZTYwM2JlNTBmNjIyMTkwZDVhNTIxNTY4YjkmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.Lhdwp2D6XFhZoHc9YWdIPO7UGD-okF5cyNOSiGAt9jM

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

Copiez le fichier d’exemple et remplis les clés :

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

1. Télécharger et déposez les docs du [google drive dans](https://drive.google.com/drive/folders/1Mt0Z4yLhOfeDo-1sQMb5IpX-__QwcV-h?usp=sharing) dans `data/raw_documents/`

2. Supprimer tout fichier qui n'est pas pdf/docx/txt

```bash
find . -type f ! \( -iname "*.pdf" -o -iname "*.docx" -o -iname "*.txt" \) -delete
```

3. Lancez l’ingestion (création/rafraîchissement d’index) :

```bash
docker compose exec api python ingestion.py --docs_dir data/raw_documents --clear
```

3. Ouvre l’UI : [http://localhost:8501](http://localhost:8501)

> Vous pouvez aussi **uploader** des fichiers directement depuis l’UI (section “Uploads”) — ceux-là sont stockés dans `data/user_uploads/` et **indexés** à la volée.


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


