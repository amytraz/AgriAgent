"""
app.py

FastAPI chatbot proxy using Groq API
Run with:
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import os
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()


# ==============================
# Configuration
# ==============================

# Load Groq API key
GROQ_API_KEY=os.getenv("GROQ_API_KEY")

# Groq OpenAI-compatible endpoint
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Fast + free model options:
MODEL_NAME = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """
You are AgriVision360 AI, an intelligent agricultural assistant designed to support farmers, agribusiness owners, and agricultural students.

Your role is to provide accurate, practical, and easy-to-understand guidance related to:

- Crop selection and seasonal planning
- Soil health and fertilizer recommendations
- Weather-based farming advice
- Pest and disease identification and prevention
- Irrigation methods and water management
- Government agricultural schemes and subsidies (India-focused unless specified otherwise)
- Market prices and crop selling strategies
- Sustainable and modern farming techniques
- Agri-technology and smart farming solutions

Guidelines:
- Always provide clear, actionable, step-by-step advice when applicable.
- Keep explanations simple and avoid unnecessary technical jargon unless requested.
- When location is relevant, ask for the user’s region before giving specific recommendations.
- Prioritize farmer safety, sustainability, and cost-effective solutions.
- If uncertain, clearly state limitations instead of guessing.
- Never provide harmful, illegal, or unsafe agricultural instructions.
- Maintain a supportive, professional, and solution-focused tone.

Your goal is to help farmers make informed decisions, increase productivity, reduce risks, and adopt smart agricultural practices.


"""

REQUEST_TIMEOUT = 20.0


# ==============================
# FastAPI Initialization
# ==============================

app = FastAPI(title="Groq Chatbot Proxy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================
# Pydantic Models
# ==============================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    response: str


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

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.7,
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

        return ChatResponse(response=ai_reply)

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
