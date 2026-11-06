from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.auth import UserCreate, Token

async def register_user(db: AsyncSession, user_data: UserCreate) -> User:
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalars().first()
    if existing_user is not None:
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail="Email already registed"
        )
    hashed_password = hash_password(user_data.password)
    new_user = User(
        username = user_data.username,
        email = user_data.email,
        password_hash = hashed_password
    )
    try:
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    except Exception:
        await db.rollback()
        raise
    return new_user

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalars().first()
    if (user is None or user.password_hash is None or not verify_password(password, user.password_hash)):
        return None
    return user

async def login_user(db: AsyncSession, email: str, password: str) -> Token:
    user = await authenticate_user(db, email, password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(
        access_token=access_token,
        token_type="bearer",
    )
    