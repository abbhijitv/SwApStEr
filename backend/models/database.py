"""Application engine/session; SQLite alone retains automatic local initialization."""
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from backend.models.database_config import create_database_engine
from backend.models.records import Base, Record

load_dotenv()
engine = create_database_engine()
Session = sessionmaker(bind=engine)


def initialize_local_database():
    """Preserve the SQLite demo. PostgreSQL schema/data must be prepared explicitly."""
    if engine.dialect.name != 'sqlite':
        return False
    Base.metadata.create_all(engine)
    return True
