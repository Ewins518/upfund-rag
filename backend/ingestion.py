import argparse
from rag_engine import RAGEngine

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="(Re)build Pinecone index from documents")
    parser.add_argument("--docs_dir", type=str, default="data/raw_documents", help="Directory with PDFs/DOCX/TXT")
    parser.add_argument("--clear", action="store_true", help="Clear namespace before indexing")
    args = parser.parse_args()

    engine = RAGEngine()
    engine.build_index(args.docs_dir, clear=args.clear)
    print("Indexing complete.")