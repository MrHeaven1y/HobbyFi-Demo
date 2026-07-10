from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.core.logging import get_logger

# all log from this file will be tagged with this name, making it easier to filter
logger = get_logger("app.database")

# builds the connection engine to the database
engine = create_engine(
    settings.DATABASE_URL, # postgreSQL DB connection String
    pool_pre_ping=True, # test the connection before use it
    pool_size=10, # keep 10 connections ready to in the pool
    max_overflow=20, # allow up to 20 extra temporary connections in peak hours
) # --> efficient reliable connection management

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# implements the Isolation from ACID property at the application level
def get_db():
    """
    FastAPI Dependency to yield a database session per request.
    Ensures the session is closed even if an exception occurs.
    """

    # returns each session of database to each request
    db = SessionLocal()
    
    try:
        yield db
    
    except Exception as e:
        
        logger.error("database_session_error", error=str(e))
        db.rollback()
        raise
    
    finally:
        db.close()
