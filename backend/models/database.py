import os
from sqlalchemy import create_engine, Column, Integer, JSON, String
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///./campusswap.db'), connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)
Base = declarative_base()
class Record(Base):
    __tablename__ = 'records'
    id = Column(Integer, primary_key=True)
    kind = Column(String, index=True)
    data = Column(JSON)
Base.metadata.create_all(engine)
