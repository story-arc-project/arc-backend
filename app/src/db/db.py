from contextlib import contextmanager
from typing import Annotated
from fastapi import Depends
from sqlmodel import create_engine, Session
from os import getenv
from src.db import models  # pyright: ignore[reportUnusedImport]

DATABASE_URL = f"postgresql://{getenv("POSTGRES_USER")}:{getenv("POSTGRES_PASSWORD")}@db:5432/{getenv("POSTGRES_DB")}"

engine = create_engine(DATABASE_URL)

@contextmanager
def session_scope():
    with Session(engine) as session:
        yield session

def get_session():
    with session_scope() as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]