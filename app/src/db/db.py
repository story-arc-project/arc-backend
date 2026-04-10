from typing import Annotated
from fastapi import Depends
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session
from os import getenv
from src.db import models  # pyright: ignore[reportUnusedImport]

DATABASE_URL = f"postgresql://{getenv("POSTGRES_USER")}:{getenv("POSTGRES_PASSWORD")}@db:5432/{getenv("POSTGRES_DB")}"

engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    with engine.connect() as conn:
        _ = conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]