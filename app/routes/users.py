from typing import Annotated
from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models import User
from app.schemas.auth import UserCreate, UserPrivate, Token
from app.services.user_service import register_user, login_user

router = APIRouter(prefix="/users", tags=["Users"])

@router.post(
    "/register",
    response_model = UserPrivate,
    status_code = status.HTTP_201_CREATED
)

async def create_user(user_data: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    return await register_user(
        db, 
        user_data
    )

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Annotated[AsyncSession, Depends(get_db)]):
    return await login_user(
        db=db,
        email=form_data.username,
        password=form_data.password
    )

@router.get("/me", response_model=UserPrivate)
async def get_current_user(current_user: CurrentUser):
    return current_user