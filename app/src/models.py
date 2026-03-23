from sqlalchemy import Column, Integer, Text, ForeignKey, Date, TIMESTAMP
from sqlalchemy.sql import func
from src.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(Text, unique=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Career(Base):
    __tablename__ = "careers"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(Text)
    company = Column(Text)
    start_date = Column(Date)
    end_date = Column(Date)
