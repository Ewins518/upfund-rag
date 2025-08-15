import os
import re
import uuid
from typing import List, Dict, Iterable, Tuple
import unicodedata
import hashlib

from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
from openai import OpenAI

from pypdf import PdfReader
import docx

# ----------------------- helpers -----------------------

def read_text_from_file(path: str) -> str:
    p = path.lower()
    if p.endswith(".pdf"):
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    if p.endswith(".docx"):
        d = docx.Document(path)
        return "\n".join([p.text for p in d.paragraphs])
    if p.endswith(".txt"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""

def clean_text(text: str) -> str:
    # basic whitespace normalization
    text = re.sub(r"\s+", " ", text)
    return text.strip()

SAFE_ID_CHARS = re.compile(r'[^A-Za-z0-9._:-]')  # allow letters, digits, dot, underscore, colon, dash

def to_ascii_slug(s: str) -> str:
    """
    Convert any string to a safe ASCII slug for Pinecone IDs:
    - NFKD normalize then strip diacritics
    - replace path separators with ':'
    - replace unsafe chars with '_'
    """
    s = s.replace(os.sep, ":")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = SAFE_ID_CHARS.sub("_", s)
    # collapse multiple underscores/colons
    s = re.sub(r'[:_]{2,}', "_", s).strip("._:-")
    return s or "file"

def make_vector_id(relpath: str, chunk_idx: int, chunk_text: str) -> str:
    # stable hash from relpath + chunk index + (optional) chunk_text
    h = hashlib.sha1(f"{relpath}|{chunk_idx}".encode("utf-8")).hexdigest()[:16]
    # sanitize relpath (ASCII) for readability
    base = to_ascii_slug(relpath)[:64]
    return f"{base}:{chunk_idx}:{h}"


def chunk_words(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    words = text.split()
    if not words:
        return []
    step = max(1, chunk_size - overlap)
    chunks = []
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks

# ----------------------- embeddings providers -----------------------

class EmbeddingProvider:
    def __init__(self):
        self.provider = os.getenv("EMBEDDINGS_PROVIDER").lower()
        self.sbert_model_name = os.getenv("SBERT_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.openai_embed_model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")
        self._sbert = None
        self._openai = None

    @property
    def dim(self) -> int:
        if self.provider == "sbert":
            return 384  
        if self.openai_embed_model == "text-embedding-3-large":
            return 3072
        return 1536 
    def _ensure_sbert(self):
        if self._sbert is None:
            self._sbert = SentenceTransformer(self.sbert_model_name)

    def _ensure_openai(self):
        if self._openai is None:
            self._openai = OpenAI()

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self.provider == "sbert":
            self._ensure_sbert()
            return self._sbert.encode(texts, normalize_embeddings=True).tolist()
        # OpenAI
        self._ensure_openai()
        resp = self._openai.embeddings.create(model=self.openai_embed_model, input=texts)
        return [d.embedding for d in resp.data]

# ----------------------- LLM providers -----------------------

class LLMProvider:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        self.model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        self._openai = None

    def _ensure_openai(self):
        if self._openai is None:
            self._openai = OpenAI()

    def answer(self, question: str, contexts: List[str]) -> str:
        # simple, deterministic prompt
        system = (
            "You are a helpful assistant. Answer using ONLY the provided context. "
            "Cite file excerpts when relevant. If unsure, say you don't know."
        )
        context_blob = "\n\n---\n".join(contexts)
        if self.provider == "openai":
            self._ensure_openai()
            resp = self._openai.chat.completions.create(
                model=self.model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Context:\n{context_blob}\n\nQuestion: {question}\nAnswer:"},
                ],
            )
            return resp.choices[0].message.content.strip()
        # fallback: extractive
        return "\n\n".join(contexts[:1])

# ----------------------- Pinecone RAG engine -----------------------

class RAGEngine:
    def __init__(self):
        # env/config
        self.namespace = os.getenv("INDEX_NAMESPACE", "default")
        self.chunk_size = int(os.getenv("CHUNK_SIZE", 500))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", 50))
        self.top_k = int(os.getenv("TOP_K", 5))

        # providers
        self.embedder = EmbeddingProvider()
        self.llm = LLMProvider()

        # pinecone
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY not set")
        self.pc = Pinecone(api_key=api_key)

        self.index_name = os.getenv("PINECONE_INDEX", "upfund-rag")
        cloud = os.getenv("PINECONE_CLOUD", "aws")
        region = os.getenv("PINECONE_REGION", "us-east-1")

        # ensure index exists with correct dimension
        existing = {idx.name for idx in self.pc.list_indexes()}
        if self.index_name not in existing:
            self.pc.create_index(
                name=self.index_name,
                dimension=self.embedder.dim,
                metric="cosine",
                spec=ServerlessSpec(cloud=cloud, region=region),
            )
        self.index = self.pc.Index(self.index_name)

    # --------------- ingestion ---------------
    def _yield_docs(self, docs_dir: str) -> Iterable[Tuple[str, str]]:
        """
        Recursively walk docs_dir, yield (relpath, cleaned_text) for real PDF/DOCX/TXT files.
        Skips lock/temp files like ~$*.docx and empty files.
        """
        base = os.path.abspath(docs_dir)
        for root, _, files in os.walk(docs_dir):
            for f in files:
                # only keep wanted extensions
                if not f.lower().endswith((".pdf", ".docx", ".txt")):
                    continue
                # skip temp/lock files (~$xxx.docx) and hidden files
                if f.startswith("~$") or f.startswith("."):
                    continue
                path = os.path.join(root, f)
                # skip empty files
                if os.path.getsize(path) < 10:  # bytes
                    continue
                relpath = os.path.relpath(path, base)
                try:
                    text = read_text_from_file(path)
                except Exception as e:
                    print(f"[WARN] Skipping {relpath}: {e}")
                    continue
                if text:
                    yield (relpath, clean_text(text))


    def clear_namespace(self):
        # delete all vectors in namespace
        self.index.delete(delete_all=True, namespace=self.namespace)

    def build_index(self, docs_dir: str, clear: bool = False):
        if clear:
            self.clear_namespace()
        to_upsert = []
        for relpath, text in self._yield_docs(docs_dir):
            chunks = chunk_words(text, self.chunk_size, self.chunk_overlap)
            if not chunks:
                continue
            embeddings = self.embedder.embed(chunks)
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                vid = make_vector_id(relpath, i, chunk)
               # vid = make_vector_id(relpath, i) 
                meta = {"file": relpath, "chunk_id": str(i), "text": chunk}
                to_upsert.append({"id": vid, "values": emb, "metadata": meta})
            # upsert in batches for memory safety
            for i in range(0, len(to_upsert), 100):
                batch = to_upsert[i:i+100]
                self.index.upsert(vectors=batch, namespace=self.namespace)
            to_upsert.clear()

    def index_file(self, abs_path: str, base_dir: str = "data/raw_documents"):
        base = os.path.abspath(base_dir)
        abs_path = os.path.abspath(abs_path)
        assert abs_path.startswith(base), "file must be inside base_dir"
        relpath = os.path.relpath(abs_path, base)

        # Skip temp/lock/hidden/unsupported
        fname = os.path.basename(relpath)
        if fname.startswith("~$") or fname.startswith("."):
            return

        if not fname.lower().endswith((".pdf",".docx",".txt")):
            return

        if not os.path.exists(abs_path) or os.path.getsize(abs_path) < 10:
            return

        try:
            text = read_text_from_file(abs_path)
        except Exception as e:
            print(f"[WARN] Skipping {relpath}: {e}")
            return
        if not text:
            return

        #chunks = chunk_by_tokens(text, max_tokens=500, overlap=80)  # ou chunk_words(...)
        chunks = chunk_words(text, self.chunk_size, self.chunk_overlap)
        if not chunks:
            return
        embeddings = self.embedder.embed(chunks)

        to_upsert = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            vid = make_vector_id(relpath, i, chunk)
            meta = {"file": relpath, "chunk_id": str(i), "text": chunk}
            to_upsert.append({"id": vid, "values": emb, "metadata": meta})

        for i in range(0, len(to_upsert), 100):
            batch = to_upsert[i:i+100]
            self.index.upsert(vectors=batch, namespace=self.namespace)


    # --------------- retrieval + generation ---------------
    def retrieve(self, question: str, k: int) -> List[Dict]:
        q_emb = self.embedder.embed([question])[0]
        res = self.index.query(
            vector=q_emb,
            top_k=k,
            include_metadata=True,
            namespace=self.namespace
        )
        matches = getattr(res, "matches", [])
        return matches

    def ask(self, question: str, k: int) -> Tuple[str, List[Dict]]:
        matches = self.retrieve(question, k)
        contexts = []
        for m in matches:
            meta = m.metadata or {}
            text = meta.get("text", "")
            file = meta.get("file", "unknown")  # contient le chemin relatif
            contexts.append(f"[File: {file}]\n{text}")
        answer = self.llm.answer(question, contexts)
        return answer, matches
