"""
Database adapter for Agent Service
Bridging app.agent with unified storage/pgsql models and database connection
"""
from storage.pgsql.database import init_db, get_session as _get_session
from storage.pgsql.models.agent import AgentSession, AgentMessage, AgentMemory

def get_session():
    """Wrapper to get raw session object"""
    return _get_session()

def get_db():
    """FastAPI Dependency for database session"""
    db = _get_session()
    try:
        yield db
    finally:
        db.close()

__all__ = ["init_db", "get_session", "get_db", "AgentSession", "AgentMessage", "AgentMemory"]
