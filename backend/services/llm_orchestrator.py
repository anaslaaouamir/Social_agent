"""Central Claude orchestration with LangGraph and durable SQL memory."""
from __future__ import annotations

import json
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any, NotRequired, TypedDict
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from models.domain import LLMMemoryEntry

logger = logging.getLogger(__name__)


class LLMConfigurationError(RuntimeError):
    """Raised when no supported LLM provider is configured."""


class LLMState(TypedDict, total=False):
    user_id: str
    session_id: str
    feature: str
    user_message: str
    system_prompt: str
    history: list[dict[str, str]]
    memory: NotRequired[list[dict[str, str]]]
    rag_context: NotRequired[str]
    reply: NotRequired[str]
    use_rag: bool
    persist_memory: bool
    metadata: dict[str, Any]


@dataclass
class LLMRequest:
    user_message: str
    system_prompt: str
    user_id: uuid.UUID | str
    session_id: str
    feature: str = "general"
    history: list[dict[str, str]] = field(default_factory=list)
    use_rag: bool = False
    persist_memory: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 1024


@dataclass
class LLMResponse:
    text: str
    model: str
    session_id: str
    memory_saved: bool


class DurableLLMMemory:
    """Small SQL-backed memory store shared by all Claude features."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def load(
        self,
        *,
        user_id: uuid.UUID | str,
        session_id: str,
        limit: int = 12,
    ) -> list[dict[str, str]]:
        result = await self.db.execute(
            select(LLMMemoryEntry)
            .where(
                LLMMemoryEntry.user_id == uuid.UUID(str(user_id)),
                LLMMemoryEntry.session_id == session_id,
            )
            .order_by(LLMMemoryEntry.created_at.desc())
            .limit(limit)
        )
        entries = list(reversed(result.scalars().all()))
        return [{"role": entry.role, "content": entry.content} for entry in entries]

    async def append(
        self,
        *,
        user_id: uuid.UUID | str,
        session_id: str,
        role: str,
        content: str,
        feature: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        cleaned = str(content or "").strip()
        if not cleaned:
            return
        self.db.add(
            LLMMemoryEntry(
                user_id=uuid.UUID(str(user_id)),
                session_id=session_id,
                role=role,
                content=cleaned,
                feature=feature,
                metadata_=metadata or {},
            )
        )


class ClaudeLangGraphOrchestrator:
    """Single backend entry point for Claude calls, graph flow, RAG, and memory."""

    CLAUDE_MODEL = "claude-sonnet-4-20250514"
    GROQ_MODEL = "llama-3.1-8b-instant"

    def __init__(self):
        settings = get_settings()
        self.anthropic_api_key = settings.anthropic_api_key
        self.groq_api_key = settings.groq_api_key
        self.model = self.CLAUDE_MODEL if self.anthropic_api_key else self.GROQ_MODEL
        self._graph = None
        self._last_model = self.model

    def _ensure_configured(self) -> None:
        if not self.anthropic_api_key and not self.groq_api_key:
            raise LLMConfigurationError("ANTHROPIC_API_KEY or GROQ_API_KEY is not configured")

    async def _call_llm(self, *, system_prompt: str, messages: list[dict[str, str]], max_tokens: int) -> str:
        self._ensure_configured()
        if self.anthropic_api_key:
            try:
                self._last_model = self.CLAUDE_MODEL
                return await self._call_claude(system_prompt=system_prompt, messages=messages, max_tokens=max_tokens)
            except Exception as exc:
                if not self.groq_api_key:
                    raise
                logger.warning("Claude call failed, falling back to Groq: %s", exc)
                
        # If no Claude key or Claude fails, call Groq
        return await self._call_groq(system_prompt=system_prompt, messages=messages, max_tokens=max_tokens)

    async def _call_claude(self, *, system_prompt: str, messages: list[dict[str, str]], max_tokens: int) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.anthropic_api_key)
        response = await client.messages.create(
            model=self.CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        return str(response.content[0].text)

    async def _call_huggingface(self, *, system_prompt: str, messages: list[dict[str, str]], max_tokens: int) -> str:
        from huggingface_hub import InferenceClient

        prompt_parts = [f"<s>[INST] {system_prompt.strip()}"]
        for message in messages:
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                prompt_parts.append(f"[/INST] {content}</s><s>[INST]")
            else:
                prompt_parts.append(content)
        prompt = "\n".join(prompt_parts).strip()
        if not prompt.endswith("[/INST]"):
            prompt = f"{prompt} [/INST]"

        self._last_model = self.HUGGINGFACE_MODEL
        client = InferenceClient(model=self.HUGGINGFACE_MODEL, token=self.hugging_face_api)
        result = await asyncio.to_thread(
            client.text_generation,
            prompt,
            max_new_tokens=max_tokens,
            temperature=0.3,
            return_full_text=False,
        )
        return str(result).strip()
    
    async def _call_groq(self, *, system_prompt: str, messages: list[dict[str, str]], max_tokens: int) -> str:
        from groq import AsyncGroq

        self._last_model = self.GROQ_MODEL
        client = AsyncGroq(api_key=self.groq_api_key)
        
        # Groq uses the exact same message format as OpenAI/Claude
        formatted_messages = [{"role": "system", "content": system_prompt}]
        formatted_messages.extend(messages)

        response = await client.chat.completions.create(
            model=self.GROQ_MODEL,
            messages=formatted_messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return str(response.choices[0].message.content).strip()

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception as exc:
            logger.warning("LangGraph unavailable, using linear Claude orchestration: %s", exc)
            return None

        graph = StateGraph(LLMState)

        async def prepare_context(state: LLMState) -> LLMState:
            if not state.get("use_rag"):
                return state
            try:
                from services.rag_service import get_rag_service

                docs = get_rag_service().retrieve(state["user_message"], n_results=4)
                context = "\n\n".join(
                    f"[Source: {doc['source']} | Relevance: {doc['relevance']}]\n{doc['text']}"
                    for doc in docs
                    if float(doc.get("relevance") or 0) > 0.3
                )
                if context:
                    state["rag_context"] = context
            except Exception as exc:
                logger.warning("RAG context skipped in LLM graph: %s", exc)
            return state

        async def generate(state: LLMState) -> LLMState:
            memory = state.get("memory", [])
            history = state.get("history", [])
            messages = [
                msg for msg in [*memory, *history]
                if msg.get("role") in {"user", "assistant"} and msg.get("content")
            ][-16:]
            messages.append({"role": "user", "content": state["user_message"]})

            system_prompt = state["system_prompt"]
            if state.get("rag_context"):
                system_prompt = (
                    f"{system_prompt}\n\n"
                    "Contexte documentaire disponible, a utiliser seulement s'il est pertinent:\n"
                    f"{state['rag_context']}"
                )
            state["reply"] = await self._call_llm(
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=int(state.get("max_tokens") or 1024),
            )
            return state

        graph.add_node("prepare_context", prepare_context)
        graph.add_node("generate", generate)
        graph.add_edge(START, "prepare_context")
        graph.add_edge("prepare_context", "generate")
        graph.add_edge("generate", END)
        return graph.compile()

    async def _run_graph(self, state: LLMState) -> LLMState:
        if self._graph is None:
            self._graph = self._build_graph()
        if self._graph is not None:
            return await self._graph.ainvoke(state)

        if state.get("use_rag"):
            try:
                from services.rag_service import get_rag_service

                docs = get_rag_service().retrieve(state["user_message"], n_results=4)
                state["rag_context"] = "\n\n".join(
                    f"[Source: {doc['source']} | Relevance: {doc['relevance']}]\n{doc['text']}"
                    for doc in docs
                    if float(doc.get("relevance") or 0) > 0.3
                )
            except Exception as exc:
                logger.warning("RAG context skipped in linear LLM flow: %s", exc)

        messages = [*state.get("memory", []), *state.get("history", [])][-16:]
        messages.append({"role": "user", "content": state["user_message"]})
        system_prompt = state["system_prompt"]
        if state.get("rag_context"):
            system_prompt = f"{system_prompt}\n\nContexte documentaire:\n{state['rag_context']}"
        state["reply"] = await self._call_llm(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=int(state.get("max_tokens") or 1024),
        )
        return state

    async def generate_text(self, request: LLMRequest, db: AsyncSession | None = None) -> LLMResponse:
        memory_messages: list[dict[str, str]] = []
        memory_saved = False
        memory = DurableLLMMemory(db) if db is not None else None

        if memory is not None and request.persist_memory:
            memory_messages = await memory.load(user_id=request.user_id, session_id=request.session_id)

        state: LLMState = {
            "user_id": str(request.user_id),
            "session_id": request.session_id,
            "feature": request.feature,
            "user_message": request.user_message,
            "system_prompt": request.system_prompt,
            "history": request.history,
            "memory": memory_messages,
            "use_rag": request.use_rag,
            "persist_memory": request.persist_memory,
            "metadata": request.metadata,
            "max_tokens": request.max_tokens,
        }
        final_state = await self._run_graph(state)
        reply = str(final_state.get("reply") or "").strip()

        if memory is not None and request.persist_memory and reply:
            await memory.append(
                user_id=request.user_id,
                session_id=request.session_id,
                role="user",
                content=request.user_message,
                feature=request.feature,
                metadata=request.metadata,
            )
            await memory.append(
                user_id=request.user_id,
                session_id=request.session_id,
                role="assistant",
                content=reply,
                feature=request.feature,
                metadata=request.metadata,
            )
            memory_saved = True

        return LLMResponse(
            text=reply,
            model=self._last_model,
            session_id=request.session_id,
            memory_saved=memory_saved,
        )

    async def generate_json(self, request: LLMRequest, db: AsyncSession | None = None) -> dict[str, Any]:
        response = await self.generate_text(request, db=db)
        text = response.text.strip()
        for prefix in ("```json", "```"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        text = text.rstrip("`").strip()
        return json.loads(text)


_orchestrator: ClaudeLangGraphOrchestrator | None = None


def get_llm_orchestrator() -> ClaudeLangGraphOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ClaudeLangGraphOrchestrator()
    return _orchestrator
