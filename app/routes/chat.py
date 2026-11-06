from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
 
from app.core.security import get_current_user  
from app.db.session import get_db                
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, ConversationSummary
from app.services import chat_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
 
router = APIRouter(prefix="/chat", tags=["Chat"])
 
 
@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    try:
        return await chat_service.handle_chat(db, user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        print(f"GraphRAG lỗi: {exc!r}")  # in lỗi ra để còn biết đường sửa
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Hệ thống đang gặp lỗi, bạn thử lại sau nhé.",
        )
 
 
@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return await chat_service.list_conversations(db, user.id)
 
 
@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessage])
async def list_messages(conversation_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    conversation = await chat_service.get_conversation(db, user.id, conversation_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")
    return conversation.messages
 
 
@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    deleted = await chat_service.delete_conversation(db, user.id, conversation_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")