# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Lee la URL desde una variable de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback local: si no hay DATABASE_URL (por ejemplo, en tu PC), usa SQLite local
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./sabor_de_autor_local.db"

# Corregir prefijo por si alguna vez Supabase devuelve postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    # connect_args={"sslmode": "require"},  # si Supabase lo pidiera, se habilita esto
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
