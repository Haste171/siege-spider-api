import os
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DB_URL")

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

# engine = create_engine(
#     DATABASE_URL,
#     pool_size=40,          # Increased from 20 to 40 base connections
#     max_overflow=30,       # Keeps 30 overflow (total max 70)
#     pool_pre_ping=True,
#     pool_recycle=3600,     # Keep 1 hour recycle time
#     pool_timeout=60,       # Keep 1 minute timeout
#     connect_args={
#         "keepalives": 1,
#         "keepalives_idle": 300,      # Keep 5 minutes
#         "keepalives_interval": 30,    # Keep 30 seconds
#         "keepalives_count": 5,        # Keep 5 attempts
#         "connect_timeout": 60         # Keep 1 minute timeout
#     }
# )

# scoped session to ensure thread safety
SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
)

Base = declarative_base()
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        # Set statement timeout (11 minutes)
        db.execute(text("SET statement_timeout = '660s'"))
        # Set idle transaction timeout (11 minutes)
        db.execute(text("SET idle_in_transaction_session_timeout = '660s'"))
        yield db
    except Exception as e:
        db.rollback()  # Restore explicit rollback
        raise e
    finally:
        db.close()