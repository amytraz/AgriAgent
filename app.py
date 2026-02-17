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
# System Prompt
# ==============================


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
MAX_HISTORY = 8  # number of past messages to keep (excluding system prompt)

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

    # Create new session if not provided
    session_id = request.session_id or str(uuid4())

    # Initialize conversation memory
    if session_id not in conversation_memory:
        conversation_memory[session_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    # Add user message
    conversation_memory[session_id].append(
        {"role": "user", "content": user_message}
    )

    # Trim conversation history
    if len(conversation_memory[session_id]) > MAX_HISTORY + 1:
        conversation_memory[session_id] = (
            [conversation_memory[session_id][0]] +
            conversation_memory[session_id][-MAX_HISTORY:]
        )

    payload = {
        "model": MODEL_NAME,
        "messages": conversation_memory[session_id],
        "temperature": 0.6,
        "max_tokens": 500
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

        # Save assistant reply to memory
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
