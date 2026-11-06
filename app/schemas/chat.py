from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    use_context: bool = True 
    
class ChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    role: str
    content: str
    
class ChatResponse(BaseModel):
    conversation_id: str
    conversation_title: str
    reply: str
    messages: list[ChatMessage]
    
class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    created_at: datetime
    updated_at: datetime