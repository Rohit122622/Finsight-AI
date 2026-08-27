"""
FinSentry AI — Real-Time Chat & Agent Streaming Service (Phase 2I).

Handles conversational Q&A grounded in session documents, retrieves citations,
persists chat history to MongoDB, and streams responses over WebSockets.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from database.connection import mongodb
from models.chat import ChatMessageModel, ChatRole, CitationSource
from schemas.chat import ChatHistoryResponse, ChatMessageResponse, SendChatMessageRequest
from services.embedding_service import embedding_service
from services.event_bus import event_bus
from services.llm_service import llm_service
from services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


class ChatStreamService:
    """
    Service managing multi-turn conversational financial research and streaming.
    """

    async def send_message(
        self,
        session_id: str,
        user_id: str,
        request: SendChatMessageRequest,
    ) -> ChatMessageResponse:
        """
        Process a user message, retrieve document context (RAG), generate assistant
        response with citations, save to MongoDB, and broadcast via WebSockets.
        """
        db = mongodb.get_db()

                                 
        user_msg = ChatMessageModel(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            role=ChatRole.USER,
            content=request.content,
            created_at=datetime.now(timezone.utc),
        )
        await db.chat_messages.insert_one(user_msg.to_dict())

                                               
        await ws_manager.broadcast_to_session(
            session_id=session_id,
            message={
                "type": "chat_user_message",
                "session_id": session_id,
                "payload": user_msg.model_dump(mode="json"),
            },
        )

                                                                
        citations: List[CitationSource] = []
        context_snippets: List[str] = []

        if request.enable_rag:
            try:
                search_results = await embedding_service.search_session_chunks(
                    session_id=session_id,
                    user_id=user_id,
                    query=request.content,
                    top_k=request.top_k,
                )
                for res in search_results:
                    citations.append(
                        CitationSource(
                            document_id=res.document_id,
                            chunk_id=res.chunk_id,
                            chunk_index=res.chunk_index,
                            snippet=res.text[:300],
                            page_number=res.page_number,
                            similarity_score=res.similarity_score,
                        )
                    )
                    context_snippets.append(
                        f"Document [{res.document_id}] Chunk {res.chunk_index}: {res.text}"
                    )
            except Exception as exc:
                logger.warning("RAG retrieval failed during chat, continuing: %s", exc)

                                                  
        recent_history = await self._get_recent_conversation_history(
            session_id=session_id,
            user_id=user_id,
            limit=6,
        )

        system_prompt = (
            "You are FinSentry AI, an expert autonomous financial research assistant.\n"
            "Analyze financial documents, earnings reports, filings, and balance sheets.\n"
            "Ground your answers strictly in the provided session documents when available.\n"
            "Cite relevant numbers, tables, and sections."
        )

        context_text = "\n\n".join(context_snippets) if context_snippets else "No specific documents found."
        user_prompt = (
            f"Grounding Document Context:\n{context_text}\n\n"
            f"Conversation History:\n{recent_history}\n\n"
            f"User Question: {request.content}\n\n"
            "Provide a comprehensive, accurate financial analysis."
        )

                                        
        assistant_text = llm_service.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )

                                                   
        if not assistant_text:
            if context_snippets:
                assistant_text = (
                    f"Based on the session documents, here is the relevant financial context:\n\n"
                    f"{context_snippets[0][:500]}..."
                )
            else:
                assistant_text = "I have analyzed your query. No specific document matches were found in this session."

                                       
        assistant_msg = ChatMessageModel(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            role=ChatRole.ASSISTANT,
            content=assistant_text,
            agent_name="ResearchAgent",
            sources=citations,
            created_at=datetime.now(timezone.utc),
        )
        await db.chat_messages.insert_one(assistant_msg.to_dict())

                                                                         
        outbound_payload = assistant_msg.model_dump(mode="json")
        await ws_manager.broadcast_to_session(
            session_id=session_id,
            message={
                "type": "chat_complete",
                "session_id": session_id,
                "payload": outbound_payload,
            },
        )
        event_bus.publish_session_event(
            session_id=session_id,
            event_type="chat_complete",
            payload=outbound_payload,
            user_id=user_id,
        )

        return ChatMessageResponse(
            message_id=assistant_msg.message_id,
            session_id=assistant_msg.session_id,
            user_id=assistant_msg.user_id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            agent_name=assistant_msg.agent_name,
            sources=assistant_msg.sources,
            metadata=assistant_msg.metadata,
            created_at=assistant_msg.created_at,
        )

    async def list_chat_history(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50,
        skip: int = 0,
    ) -> ChatHistoryResponse:
        """
        Return ordered chat message history with strict tenant filtering.
        """
        db = mongodb.get_db()
        cursor = (
            db.chat_messages.find({"session_id": session_id, "user_id": user_id})
            .sort("created_at", 1)
            .skip(skip)
            .limit(limit)
        )

        messages: List[ChatMessageResponse] = []
        async for doc in cursor:
            messages.append(
                ChatMessageResponse(
                    message_id=doc.get("message_id", str(doc.get("_id"))),
                    session_id=doc.get("session_id"),
                    user_id=doc.get("user_id"),
                    role=doc.get("role", ChatRole.USER),
                    content=doc.get("content", ""),
                    agent_name=doc.get("agent_name"),
                    sources=doc.get("sources", []),
                    metadata=doc.get("metadata", {}),
                    created_at=doc.get("created_at", datetime.now(timezone.utc)),
                )
            )

        total = await db.chat_messages.count_documents({
            "session_id": session_id,
            "user_id": user_id,
        })

        return ChatHistoryResponse(
            session_id=session_id,
            total=total,
            messages=messages,
        )

    async def delete_chat_history(self, session_id: str, user_id: str) -> int:
        """Clear all messages in a session for the owner user."""
        db = mongodb.get_db()
        result = await db.chat_messages.delete_many({
            "session_id": session_id,
            "user_id": user_id,
        })
        return result.deleted_count

    async def _get_recent_conversation_history(
        self,
        session_id: str,
        user_id: str,
        limit: int = 6,
    ) -> str:
        """Fetch and format recent dialogue turns for prompt context."""
        db = mongodb.get_db()
        cursor = (
            db.chat_messages.find({"session_id": session_id, "user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        docs.reverse()

        lines = []
        for doc in docs:
            role = doc.get("role", "user").capitalize()
            content = doc.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)


chat_stream_service = ChatStreamService()
