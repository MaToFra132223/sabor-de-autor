# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# 1) Leemos la contraseña desde variable de entorno
SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")

if not SUPABASE_DB_PASSWORD:
    raise RuntimeError(
        "Falta la variable de entorno SUPABASE_DB_PASSWORD. "
        "Definila en tu entorno local o en Render."
    )

# 2) URL usando el Session Pooler de Supabase
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://postgres.ffcsvvprvqgthetpblos:"
    f"{SUPABASE_DB_PASSWORD}"
    f"@aws-0-us-west-2.pooler.supabase.com:5432/postgres"
)

# 3) Motor
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    # opcional, si algún día Supabase te exige SSL explícito:
    # connect_args={"sslmode": "require"},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
