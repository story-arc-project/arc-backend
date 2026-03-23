from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from os import getenv

DATABASE_URL = f"postgresql://{getenv("POSTGRES_USER")}:{getenv("POSTGRES_PASSWORD")}@db:5432/{getenv("POSTGRES_DB")}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
