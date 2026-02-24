# Fashion RAG (Ollama + ChromaDB + Sentence-Transformers)

A minimal local Retrieval-Augmented Generation (RAG) chatbot for fashion advice.

This project indexes local fashion notes stored in `./kb`, embeds them using sentence-transformers, stores them in a persistent ChromaDB vector database, and queries a local Ollama model via HTTP to generate grounded, fashion-only answers.

No cloud LLM APIs are required.

---

## Features
- Fully local RAG pipeline
- Persistent vector database (ChromaDB)
- Fashion-only scope with guardrails
- Uses only retrieved notes (reduces hallucinations)
- CLI-based chat interface
- Windows-friendly setup

---

## Requirements
- Windows (PowerShell or CMD)
- Python 3.10+
- Ollama installed and running locally

---

## Install Ollama (Windows)

1. Download and install the official Ollama Windows application.
2. Open PowerShell and pull the default model:
   ```powershell
   ollama pull mistral
   ```
3. (Optional) Quick test:
   ```powershell
   ollama run mistral
   ```

Ollama runs a local API at:
```
http://localhost:11434
```

---

## Project Setup

```powershell
cd "D:\Personal\LLM Test\Ollama"

python -m venv .venv
.\.venv\Scripts\activate

python -m pip install --upgrade pip
pip install chromadb sentence-transformers requests python-dotenv
```

---

## Configuration

Create a `.env` file:

```env
HF_TOKEN=PASTE_YOUR_HUGGINGFACE_TOKEN_HERE
```

The Hugging Face token is optional but recommended to avoid rate limits when downloading the embedding model.

---

## Knowledge Base

Place fashion notes as `.txt` or `.md` files under:

```
kb/
```

Example files:
- `color_rules.txt`
- `patterns.md`
- `occasions.md`

These files are the only knowledge source used by the chatbot.

---

## Index the Knowledge Base

Run once (or whenever KB files change):

```powershell
python index_kb.py
```

This process:
- Reads all files under `./kb`
- Chunks the text
- Embeds chunks using `all-MiniLM-L6-v2`
- Stores vectors and metadata in `./chroma_db`
- Creates the `fashion_kb` collection

---

## Start the Chatbot

```powershell
python chat_rag.py
```

Commands:
- Ask fashion questions directly
- Type `help` for examples
- Type `exit` to quit

---

## Example Questions
- How do neutrals help with bold colors?
- How can I style floral patterns without looking busy?
- What is smart casual?
- How should I dress for a formal event?

---

## Project Structure

```
Ollama/
├─ chat_rag.py
├─ index_kb.py
├─ README.md
├─ .env
├─ .env.example
├─ kb/
│  ├─ color_rules.txt
│  ├─ patterns.md
│  └─ occasions.md
├─ chroma_db/
└─ .venv/
```

---

## Architecture Overview

1. Knowledge Base (`./kb/*.md`, `./kb/*.txt`)
2. Indexing (`index_kb.py`)
   - Chunk KB files
   - Embed with `all-MiniLM-L6-v2`
   - Store vectors and metadata in ChromaDB (`fashion_kb`)
3. Chat (`chat_rag.py`)
   - Embed user question
   - Retrieve top-K chunks
   - Build strict prompt using retrieved notes
   - Call Ollama via `POST /api/generate`
   - Print answer and retrieved sources

---

## Guardrails
- Fashion-only scope
- Similarity threshold to reduce off-topic answers
- Model instructed to use only retrieved notes
- Clarifying follow-up when information is insufficient

---

## Troubleshooting

- Ollama not running: ensure Ollama is open and reachable at `http://localhost:11434`
- No collection found: run `python index_kb.py`
- Hugging Face warnings: safe to ignore or set `HF_TOKEN`

---

## Customization

Edit constants in the scripts:

chat_rag.py:
- OLLAMA_MODEL
- TOP_K
- MIN_SIMILARITY

index_kb.py:
- MAX_CHARS
- OVERLAP
