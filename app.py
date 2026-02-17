"""
app.py

FastAPI chatbot proxy using Groq API
Run with:
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import os
from typing import Optional, Dict, List
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from systemprompt import SYSTEM_PROMPT

# ==============================
# Load Environment Variables
# ==============================

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.1-8b-instant"
REQUEST_TIMEOUT = 20.0

# ==============================
# FastAPI Initialization
# ==============================

app = FastAPI(title="AgriVision360 Groq Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# In-Memory Conversation Storage
# ==============================

conversation_memory: Dict[str, List[dict]] = {}
MAX_HISTORY = 6  # Keep recent messages
SUMMARY_TRIGGER = 12  # When to summarize


# ==============================
# Pydantic Models
# ==============================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


# ==============================
# Helper: Summarize Conversation
# ==============================

async def summarize_history(messages: List[dict]) -> str:
    """
    Summarizes older chat history to maintain context without token overload.
    """
    summary_prompt = [
        {"role": "system", "content": "Summarize this farming conversation briefly for context retention."},
        {"role": "user", "content": str(messages)}
    ]

    payload = {
        "model": MODEL_NAME,
        "messages": summary_prompt,
        "temperature": 0.3,
        "max_tokens": 220
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(GROQ_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )


# ==============================
# Chat Endpoint
# ==============================

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):

    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY environment variable is not set."
        )

    user_message = request.message.strip()

    if not user_message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty."
        )

    # Create or use existing session
    session_id = request.session_id or str(uuid4())

    # Initialize memory
    if session_id not in conversation_memory:
        conversation_memory[session_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    memory = conversation_memory[session_id]

    # Add user message
    memory.append({"role": "user", "content": user_message})

    # ==============================
    # Smart Memory Management
    # ==============================

    # If conversation grows too large, summarize older messages
    if len(memory) > SUMMARY_TRIGGER:
        old_messages = memory[1:-MAX_HISTORY]  # exclude system + latest messages
        summary = await summarize_history(old_messages)

        # Replace old messages with summary
        memory = [
            memory[0],  # system prompt
            {"role": "system", "content": f"Conversation summary: {summary}"}
        ] + memory[-MAX_HISTORY:]

        conversation_memory[session_id] = memory

    # ==============================
    # Prepare Request to Groq
    # ==============================

    payload = {
        "model": MODEL_NAME,
        "messages": memory,
        "temperature": 0.6,
        "max_tokens": 220  # shorter controlled responses
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                GROQ_API_URL,
                json=payload,
                headers=headers
            )

        response.raise_for_status()
        data = response.json()

        ai_reply = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        if not ai_reply:
            raise HTTPException(
                status_code=500,
                detail="Invalid response format from Groq API."
            )

        # Save assistant reply
        conversation_memory[session_id].append(
            {"role": "assistant", "content": ai_reply}
        )

        return ChatResponse(
            response=ai_reply,
            session_id=session_id
        )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=500,
            detail="Request to Groq API timed out."
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Groq API error: {e.response.text}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
