from contextlib import asynccontextmanager
from database import models
from database.handler import engine
from fastapi import FastAPI
from services.ban_ws_listener import run as run_ban_websocket_listener
from services.ubisoft_handler import UbisoftHandler
from sqlalchemy.orm import sessionmaker
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import asyncio
import contextlib
import os
import uvicorn

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=os.getenv('ORIGINS'),
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    ),
]

ubisoft_handler = UbisoftHandler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await ubisoft_handler.initialize(
        os.getenv("UBISOFT_EMAIL"),
        os.getenv("UBISOFT_PASSWORD")
    )

    # Add ubisoft_handler to app state to access in routers and other services
    app.state.ubisoft_handler = ubisoft_handler

    # Start ban listener
    # task = asyncio.create_task(run_ban_websocket_listener(ubisoft_handler))
    task = None
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Clean up ubisoft_handler
        await app.state.ubisoft_handler.close()

app = FastAPI(middleware=middleware, docs_url='/siege-spider-api/docs', lifespan=lifespan)
models.Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine)

@app.get("/")
async def root():
    return {"message": "Welcome to Siege Spider API!"}

from rest.user import router as user_router
from rest.lookup import router as lookup_router
from rest.ingest import router as ingest_router
from rest.client import router as client_router

app.include_router(user_router)
app.include_router(lookup_router)
app.include_router(ingest_router)
app.include_router(client_router)

