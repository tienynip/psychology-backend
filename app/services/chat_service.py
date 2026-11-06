from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.chat import Conversation, Message
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from app.services.retrieval import OPENAI_MODEL, answer_with_graph_rag, client

MAX_HISTORY_MESSAGES = 16

def make_title(message: str) -> str:
    normalized = " ".join(message.strip().split())
    if len(normalized) <= 52:
        return normalized or "Cuộc trò chuyện mới"
    return normalized[:49].rstrip() + "..."

async def create_conversation(db: AsyncSession, user_id, title: str) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title)
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)
    return conversation

async def get_conversation(db: AsyncSession, user_id, conversation_id: str) -> Conversation | None:
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id
        )
    )
    return result.scalar_one_or_none()
    
async def list_conversations(db: AsyncSession, user_id) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())
    
async def delete_conversation(db: AsyncSession, user_id, conversation_id: str) -> bool:
    conversation = await get_conversation(db, user_id, conversation_id)
    if not conversation:
        return False
    await db.delete(conversation) 
    await db.commit()
    return True

def rewrite_question(message: str, history: list[ChatMessage]) -> str:
    """Viết lại câu hỏi nối tiếp ("còn cách nào khác không?") thành câu hỏi độc lập
    để bước tìm entity trong graph hoạt động. Chưa có lịch sử thì giữ nguyên."""
    if not history:
        return message
    transcript = "\n".join(f"{m.role}: {m.content}" for m in history[-6:])
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": "Analyze the user's latest message in the context of conversation history, infer their intent, and rewrite it as a standalone request without changing its meaning. Keep the same language. Return only the rewritten request."},
            {"role": "user", "content": f"Conversation:\n{transcript}\n\nLatest message: {message}"},
        ],
    )
    return response.output_text.strip() or message

async def handle_chat(db: AsyncSession, user_id, payload: ChatRequest) -> ChatResponse:
    conversation = None
    if payload.conversation_id:
        conversation = await get_conversation(db, user_id, payload.conversation_id)
        if not conversation:
            raise ValueError("Không tìm thấy cuộc trò chuyện của tài khoản này.")
    history: list[ChatMessage] = []
    if conversation and payload.use_context:
        history = [ChatMessage(role=m.role, content=m.content) for m in conversation.messages[-MAX_HISTORY_MESSAGES:]]
    # GraphRAG lỗi thì để lỗi nổi lên (route trả 502) và KHÔNG lưu gì,
    # để lịch sử không bị chèn câu xin lỗi hay cuộc trò chuyện rỗng.
    question = rewrite_question(payload.message, history)
    reply, _retrieval = answer_with_graph_rag(question)
 
    if conversation is None:
        conversation = await create_conversation(db, user_id, make_title(payload.message))
 
    db.add_all([
        Message(conversation_id=conversation.id, role="user", content=payload.message),
        Message(conversation_id=conversation.id, role="assistant", content=reply),
    ])
    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(conversation)
 
    result =  await db.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    )
    messages = result.scalars().all()
    return ChatResponse(
        conversation_id=str(conversation.id),
        conversation_title=conversation.title,
        reply=reply,
        messages=[
            ChatMessage(role=m.role, content=m.content)
            for m in messages
        ]
    )