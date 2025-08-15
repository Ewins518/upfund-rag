import os
from flask import Flask, request, jsonify
from pydantic import ValidationError
from models import AskRequest, AskResponse, ReindexRequest, Source
from rag_engine import RAGEngine
import werkzeug
from werkzeug.utils import secure_filename

app = Flask(__name__)
engine = RAGEngine()

@app.get("/healthcheck")
def health():
    return jsonify({"status": "ok", "index": engine.index_name, "namespace": engine.namespace}), 200

@app.post("/ask")
def ask():
    try:
        payload = AskRequest(**request.get_json(force=True))
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    answer, matches = engine.ask(payload.question, payload.k)
    sources = []
    for m in matches:
        meta = m.metadata or {}
        snippet = meta.get("text", "")[:220]
        s = Source(file=meta.get("file", "unknown"),
                   chunk_id=str(meta.get("chunk_id", "")),
                   score=float(getattr(m, "score", 0.0) or 0.0),
                   snippet=snippet)
        sources.append(s)
    resp = AskResponse(answer=answer, sources=sources)
    return jsonify(resp.model_dump()), 200

@app.post("/reindex")
def reindex():
    # trigger ingestion inside container (e.g. from Streamlit)
    data = request.get_json(silent=True) or {}
    try:
        payload = ReindexRequest(**data)
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    engine.build_index(payload.docs_dir, clear=payload.clear)
    return jsonify({"status": "reindexed", "docs_dir": payload.docs_dir, "cleared": payload.clear}), 200

UPLOAD_DIR = "data/user_uploads"   # 👈 dossier dédié aux uploads manuels
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    fn = secure_filename(f.filename)
    if not fn.lower().endswith((".pdf", ".docx", ".txt")):
        return jsonify({"error": "Unsupported file type"}), 400

    # Create save path, preserving relative structure if needed
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    save_path = os.path.join(UPLOAD_DIR, fn)
    f.save(save_path)

    # Index the file in Pinecone
    try:
        print(f"[UPLOAD] Saved to {save_path}, starting index...")
        engine.index_file(save_path, base_dir=UPLOAD_DIR)
        print(f"[UPLOAD] Successfully indexed {fn}")
        return jsonify({"status": "saved", "path": save_path, "ingested": True}), 200

    except Exception as e:
        print(f"[UPLOAD] Indexing failed: {e}")
        return jsonify({
            "status": "saved",
            "path": save_path,
            "ingested": False,
            "error": str(e)
        }), 200

@app.get("/list_user_uploads")
def list_user_uploads():
    docs = []
    base = os.path.abspath(UPLOAD_DIR)
    if os.path.isdir(base):
        for root, _, files in os.walk(base):
            for f in files:
                fl = f.lower()
                if fl.endswith((".pdf",".docx",".txt")) and not f.startswith(("~$",".")):
                    path = os.path.join(root, f)
                    rel = os.path.relpath(path, base)
                    try:
                        size = os.path.getsize(path)
                    except:
                        size = 0
                    docs.append({"path": rel, "size": size})
    docs.sort(key=lambda d: d["path"])
    return jsonify({"docs": docs}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)  