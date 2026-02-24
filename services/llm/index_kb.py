# Fashion RAG indexer (Ollama + ChromaDB + sentence-transformers)
# Re-index safe: drops and recreates the collection each run.

import os
import sys
import glob
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv


KB_DIR = Path("./kb")
CHROMA_DIR = Path("./chroma_db")
COLLECTION_NAME = "fashion_kb"
MODEL_NAME = "all-MiniLM-L6-v2"

MAX_CHARS = 900
OVERLAP = 150



def read_text_files(kb_dir: Path):
    patterns = ["**/*.md", "**/*.txt"]
    files = []
    for p in patterns:
        files.extend(kb_dir.glob(p))
    return [f for f in files if f.is_file()]


def chunk_text(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP):
    # Split on double newlines to keep paragraphs together.
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""

    def flush(buf: str):
        if buf.strip():
            chunks.append(buf.strip())

    for para in paragraphs:
        if not current:
            current = para
            continue
        if len(current) + 2 + len(para) <= max_chars:
            current += "\n\n" + para
        else:
            flush(current)
            current = para

    flush(current)

    # If any chunk is still too long, hard-split with overlap.
    final_chunks = []
    for ch in chunks:
        if len(ch) <= max_chars:
            final_chunks.append(ch)
            continue
        start = 0
        while start < len(ch):
            end = min(len(ch), start + max_chars)
            final_chunks.append(ch[start:end].strip())
            if end == len(ch):
                break
            start = max(0, end - overlap)
    return [c for c in final_chunks if c]


def main():
    load_dotenv()
    if os.getenv("HF_TOKEN") and not os.getenv("HUGGINGFACE_HUB_TOKEN"):
        os.environ["HUGGINGFACE_HUB_TOKEN"] = os.getenv("HF_TOKEN")
    if not KB_DIR.exists():
        print(f"ERROR: KB folder not found at {KB_DIR.resolve()}")
        sys.exit(1)

    files = read_text_files(KB_DIR)
    if not files:
        print(f"ERROR: No .md or .txt files found under {KB_DIR.resolve()}")
        sys.exit(1)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    # Use the persistent client API (newer Chroma versions don't expose client.persist()).
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Re-index safe: drop existing collection if it exists.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)


    model = SentenceTransformer(MODEL_NAME)

    all_texts = []
    all_ids = []
    all_metadatas = []

    for f in files:
        rel = f.relative_to(KB_DIR).as_posix()
        text = f.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{rel}::chunk_{i}"
            all_ids.append(chunk_id)
            all_texts.append(chunk)
            all_metadatas.append({"source": rel, "chunk": i})

    if not all_texts:
        print("ERROR: No chunks produced from KB files.")
        sys.exit(1)

    embeddings = model.encode(all_texts, normalize_embeddings=True, show_progress_bar=True).tolist()


    collection.upsert(
        ids=all_ids,
        documents=all_texts,
        metadatas=all_metadatas,
        embeddings=embeddings,
    )

    print(f"Indexed {len(all_texts)} chunks into collection '{COLLECTION_NAME}' at {CHROMA_DIR.resolve()}")


if __name__ == "__main__":
    main()
