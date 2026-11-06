from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import Base, engine
from app.models import User
from app.routes.users import router as users_router
from app.db.neo4j import init_neo4j, close_neo4j
from app.routes import chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    init_neo4j()
    yield
    close_neo4j()
    await engine.dispose()
    
app = FastAPI(lifespan=lifespan)
app.include_router(chat.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(users_router, prefix="/api")

@app.get("/health/live", tags=["Health"])
async def health_live():
    return {"status": "ok"}