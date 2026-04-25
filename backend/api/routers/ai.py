import logging
import os
import base64
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class FileAttachment(BaseModel):
    name: str
    type: str   # MIME: image/jpeg, image/png, application/pdf, text/plain
    data: str   # base64 encoded


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: str = ""
    files: list[FileAttachment] = []


def build_claude_messages(messages: list[ChatMessage], files: list[FileAttachment]) -> list[dict]:
    """Convert messages + files into Claude's multimodal format."""
    result = []

    for i, msg in enumerate(messages):
        is_last_user = (msg.role == 'user' and i == len(messages) - 1)

        if is_last_user and files:
            content: list[Any] = []

            for f in files:
                mime = f.type.lower()
                if mime.startswith('image/'):
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": f.data,
                        }
                    })
                elif mime == 'application/pdf':
                    content.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": f.data,
                        }
                    })
                elif mime.startswith('text/'):
                    try:
                        text_body = base64.b64decode(f.data).decode('utf-8', errors='replace')
                    except Exception:
                        text_body = f.data
                    content.append({
                        "type": "text",
                        "text": f"[Attached file: {f.name}]\n{text_body}"
                    })

            content.append({"type": "text", "text": msg.content})
            result.append({"role": "user", "content": content})
        else:
            result.append({"role": msg.role, "content": msg.content})

    return result


@router.post("/chat")
def chat(req: ChatRequest):
    try:
        import anthropic
        from backend.config import settings
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        system = """You are an AI assistant built into IvyTrader, a professional investment research terminal used by capital market firms (hedge funds, boutique investment firms, family offices).

You help users analyze stocks, interpret financial data, read SEC filings, compare companies with peers, and make sense of market information. When files are attached (PDFs, images, documents), read and analyze them carefully as part of your response.

Be concise, precise, and professional. Focus on investment-relevant insights. When you see financial data, highlight what matters most for investment decisions. Always respond in English."""

        if req.context:
            system += f"\n\nCurrent context data selected by user:\n{req.context}"

        messages = build_claude_messages(req.messages, req.files)

        # Use beta for PDF support
        extra_kwargs: dict = {}
        has_pdf = any(f.type == 'application/pdf' for f in req.files)
        if has_pdf:
            extra_kwargs['betas'] = ['pdfs-2024-09-25']

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            messages=messages,
            **extra_kwargs,
        )
        return {"content": response.content[0].text}

    except Exception as e:
        logger.error(f"AI chat error: {e}")
        raise HTTPException(500, str(e))
