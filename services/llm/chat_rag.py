import sys
import os
from pathlib import Path

import requests
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv


CHROMA_DIR = Path("./chroma_db")
COLLECTION_NAME = "fashion_kb"
EMB_MODEL = "all-MiniLM-L6-v2"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"

TOP_K = 4
MIN_SIMILARITY = 0.35  # start lower; tune later


SYSTEM_RULE = (
    "You are a practical fashion assistant.\n"
    "Use ONLY the provided notes to answer.\n"
    "If the notes are insufficient, say you are not sure and ask ONE follow-up question.\n"
    "Do not mention documents, sources, filenames, or the word 'context'.\n"
)

# Simple UX routing
GREETINGS = {"hi", "hello", "hey", "yo", "hiya", "sup"}
HELP_WORDS = {"help", "/help", "?"}


def load_collection():
    if not CHROMA_DIR.exists():
        print(f"ERROR: ChromaDB folder not found at {CHROMA_DIR.resolve()}")
        return None

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        return client.get_collection(name=COLLECTION_NAME)
    except Exception:
        print(f"ERROR: Collection '{COLLECTION_NAME}' not found. Run index_kb.py first.")
        return None


def build_prompt(retrieved_texts: list[str], question: str) -> str:
    notes = "\n\n---\n\n".join(retrieved_texts)
    return (
        f"{SYSTEM_RULE}\n"
        f"NOTES:\n{notes}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"ANSWER:"
    )


def call_ollama(prompt: str) -> str | None:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        # Optional tuning:
        # "options": {"temperature": 0.7, "num_ctx": 4096, "num_predict": 220}
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    except requests.RequestException:
        print("ERROR: Could not connect to Ollama at http://localhost:11434. Is it running?")
        return None

    if resp.status_code != 200:
        print(f"ERROR: Ollama returned status {resp.status_code}: {resp.text}")
        return None

    return resp.json().get("response", "").strip()


def print_help():
    print(
        "\nAssistant: I’m a fashion-only RAG bot right now. I can help with:\n"
        "- color matching (neutrals, contrast, warm/cool)\n"
        "- patterns (floral/stripes/etc.)\n"
        "- occasion dressing (casual, smart-casual, formal)\n\n"
        "Try:\n"
        "- How do neutrals help with bold colors?\n"
        "- How do I style floral without it looking too busy?\n"
        "- What is smart casual?\n"
    )


def main():
    load_dotenv()
    if os.getenv("HF_TOKEN") and not os.getenv("HUGGINGFACE_HUB_TOKEN"):
        os.environ["HUGGINGFACE_HUB_TOKEN"] = os.getenv("HF_TOKEN")

    collection = load_collection()
    if collection is None:
        sys.exit(1)

    embedder = SentenceTransformer(EMB_MODEL)

    print("Fashion RAG Chat. Type 'help' for examples. Type 'exit' to quit.")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not question:
            continue

        q_lower = question.lower().strip()

        if q_lower in {"exit", "quit"}:
            print("Bye.")
            break

        # ✅ Greetings
        if q_lower in GREETINGS:
            print("\nAssistant: Hi! 😊 Ask me a fashion question. Type 'help' for examples.\n")
            continue

        # ✅ Help
        if q_lower in HELP_WORDS:
            print_help()
            continue

        q_emb = embedder.encode([question], normalize_embeddings=True).tolist()[0]

        results = collection.query(
            query_embeddings=[q_emb],
            n_results=TOP_K,
            include=["documents", "metadatas", "distances"],
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            print("\nAssistant: I can only answer fashion questions (colors/patterns/occasions/styling). What are you trying to style?\n")
            continue

        # Assumes cosine distance = 1 - cosine similarity
        top_distance = distances[0] if distances else None
        sim = None if top_distance is None else (1 - top_distance)

        if sim is not None and sim < MIN_SIMILARITY:
            print(
                "\nAssistant: I can only answer fashion questions using my notes.\n"
                "Try asking with an item + occasion, e.g., “How do I style a floral dress for smart casual?”\n"
            )
            continue

        retrieved_texts = [d.strip() for d in docs if d and d.strip()]

        prompt = build_prompt(retrieved_texts, question)
        answer = call_ollama(prompt)
        if answer is None:
            continue

        print(f"\nAssistant: {answer}\n")

        print("Retrieved:")
        for meta in metas:
            if not meta:
                print("- unknown")
                continue
            src = meta.get("source", "unknown")
            ch = meta.get("chunk", "?")
            print(f"- {src} (chunk {ch})")

        if sim is not None:
            print(f"(debug) top similarity: {sim:.3f}")


if __name__ == "__main__":
    main()
