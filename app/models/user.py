from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )
    
    username: Mapped[str] = mapped_column(
        String(50),
        unique=False,
        nullable=False
    )
    
    email: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        nullable=False,
        index=True,
    )
    
    password_hash: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        default=None
    )