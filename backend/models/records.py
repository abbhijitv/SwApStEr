"""Portable record metadata; importing it never opens or changes a database."""
from sqlalchemy import Column, Index, Integer, JSON, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Record(Base):
    __tablename__ = 'records'
    id = Column(Integer, primary_key=True)
    kind = Column(String, index=True)
    data = Column(JSON)


# SQLAlchemy compiles JSON extraction and the partial index for each dialect.
# Keep the existing SQLite index name and uniqueness semantics.
student_identity_index = Index(
    'unique_student_identity',
    Record.data['identity'].as_string(),
    unique=True,
    sqlite_where=Record.kind == 'student',
    postgresql_where=Record.kind == 'student',
)
