from fastapi import FastAPI
from src.db import engine
from src.models import Base

app = FastAPI()

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
