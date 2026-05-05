"""
RAG service backed by ChromaDB.
"""
from __future__ import annotations

import base64
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class RAGService:
    """
    Retrieval-augmented generation service for the chatbot.
    Supports common document formats and falls back gracefully for any extension.
    """

    def __init__(self):
        self._client = chromadb.PersistentClient(
            path=settings.chroma_db_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self._collection = self._client.get_or_create_collection(
            name=settings.rag_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: Any = self._embedding_model.encode(texts)
        if hasattr(embeddings, "tolist"):
            return embeddings.tolist()
        return [list(vector) for vector in embeddings]

    def ingest_text(self, text: str, source: str, chunk_size: int = 500, overlap: int = 50):
        if not isinstance(text, str):
            text = str(text)

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += chunk_size - overlap

        if not chunks:
            return 0

        embeddings = self._embed(chunks)
        ids = [f"{source}_{idx}" for idx in range(len(chunks))]
        metadatas = [{"source": source, "chunk_idx": idx} for idx in range(len(chunks))]
        self._collection.upsert(
            documents=chunks,
            embeddings=embeddings,
            ids=ids,
            metadatas=metadatas,
        )
        logger.info("Ingested %s chunks from %s", len(chunks), source)
        return len(chunks)

    def _fallback_bytes_to_text(self, path: Path) -> str:
        raw = path.read_bytes()
        if not raw:
            return f"Empty file: {path.name}"

        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                text = raw.decode(encoding)
                cleaned = text.strip()
                if cleaned:
                    return cleaned
            except UnicodeDecodeError:
                continue

        preview = base64.b64encode(raw[:4096]).decode("ascii")
        return (
            f"Binary file imported: {path.name}\n"
            f"Extension: {path.suffix or 'none'}\n"
            f"Size: {len(raw)} bytes\n"
            f"Base64 preview:\n{preview}"
        )

    def ingest_file(self, file_path: str) -> int:
        path = Path(file_path)
        ext = path.suffix.lower()

        try:
            if ext in {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".yml", ".yaml", ".xml", ".csv", ".log", ".ini"}:
                if ext == ".csv":
                    import pandas as pd

                    text = pd.read_csv(file_path).to_string()
                elif ext == ".json":
                    with open(file_path, encoding="utf-8", errors="ignore") as handle:
                        data = json.load(handle)
                    text = json.dumps(data, ensure_ascii=False, indent=2)
                else:
                    text = path.read_text(encoding="utf-8", errors="ignore")
            elif ext == ".pdf":
                import pypdf

                reader = pypdf.PdfReader(file_path)
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            elif ext in {".docx", ".doc"}:
                from docx import Document

                doc = Document(file_path)
                text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            elif ext in {".xls", ".xlsx"}:
                import pandas as pd

                sheets = pd.read_excel(file_path, sheet_name=None)
                text = "\n\n".join(f"[Sheet: {name}]\n{frame.to_string()}" for name, frame in sheets.items())
            else:
                text = self._fallback_bytes_to_text(path)
        except Exception as exc:
            logger.warning("Structured extraction failed for %s: %s", path.name, exc)
            text = self._fallback_bytes_to_text(path)

        if not str(text).strip():
            text = f"Imported file {path.name} but no extractable text was found."

        return self.ingest_text(text, source=path.name)

    def retrieve(self, query: str, n_results: int = 5) -> list[dict]:
        query_embedding = self._embed([query])[0]
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, self._collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )
        docs = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            docs.append(
                {
                    "text": doc,
                    "source": meta.get("source", "unknown"),
                    "relevance": round(1 - dist, 4),
                }
            )
        return docs

    async def chat_with_rag(
        self,
        user_message: str,
        conversation_history: list[dict],
        system_context: str = "",
        n_context: int = 4,
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        context_docs = self.retrieve(user_message, n_results=n_context)
        context_text = "\n\n".join(
            f"[Source: {doc['source']} | Relevance: {doc['relevance']}]\n{doc['text']}"
            for doc in context_docs
            if doc["relevance"] > 0.3
        )

        system_prompt = f"""Tu es un assistant social media expert.
{system_context}

{f"Contexte documentaire disponible :{chr(10)}{context_text}" if context_text else ""}

Reponds de maniere concise, professionnelle et adaptee au contexte social media.
Si le contexte documentaire est pertinent, utilise-le dans ta reponse."""

        messages = [{"role": msg["role"], "content": msg["content"]} for msg in conversation_history[-10:]]
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text

    def list_sources(self) -> list[str]:
        if self._collection.count() == 0:
            return []
        results = self._collection.get(include=["metadatas"])
        sources = list({metadata.get("source", "") for metadata in results["metadatas"]})
        return sorted(sources)

    def delete_source(self, source: str):
        results = self._collection.get(where={"source": source}, include=["metadatas"])
        if results["ids"]:
            self._collection.delete(ids=results["ids"])
            logger.info("Deleted %s chunks from %s", len(results["ids"]), source)


@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    """Instantiate the RAG stack only when a route actually uses it."""
    return RAGService()
