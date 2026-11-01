"""Persistent profiles and an additive, idempotent legacy-data migration."""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.schema import CreateIndex
from backend.models.database import Session, Record, engine
from backend.models.records import student_identity_index

MIGRATION = 'dynamic_students_v1'

def now():
    return datetime.now(timezone.utc).isoformat()

def public_student(record):
    data = record.data
    return {key: data.get(key) for key in ('display_name', 'university', 'course_or_major', 'created_at', 'initial_role')} | {'id': data['identity']}

def students():
    with Session() as db:
        return [public_student(r) for r in db.query(Record).filter_by(kind='student').order_by(Record.id).all()]

def student_by_id(identity):
    return next((s for s in students() if s['id'] == identity), None)

def create_student(body):
    data = dict(body.model_dump(), identity='student-' + uuid.uuid4().hex, created_at=now(), initial_role=None)
    with Session() as db:
        record = Record(kind='student', data=data)
        db.add(record)
        db.commit()
        return public_student(record)

def backup_database():
    database = engine.url.database
    if engine.dialect.name != 'sqlite' or not database or database == ':memory:':
        return None
    source = Path(database).resolve()
    backup_dir = source.parent / 'backups'
    backup_dir.mkdir(exist_ok=True)
    destination = backup_dir / (source.stem + '-before-students-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db')
    with sqlite3.connect(source) as original, sqlite3.connect(destination) as backup:
        original.backup(backup)
    return str(destination)

def migrate_students():
    with Session() as db:
        if any(r.data.get('version') == MIGRATION for r in db.query(Record).filter_by(kind='migration')):
            return
        if db.query(Record).first():
            backup_database()
        timestamp = now()
        records = db.query(Record).all()
        profiles = {r.data.get('identity'): r for r in records if r.kind == 'student'}
        # Only the known original demo names are renamed. Other user data is retained.
        defaults = [('student-a', 'Abbhijit', 'Alex Rivera', 'Buyer'),
                    ('student-b', 'Shorya Moses', 'Maya Chen', 'Seller'),
                    ('student-c', 'Oumar', None, 'Buyer or Seller')]
        for identity, name, legacy, role in defaults:
            record = profiles.get(identity)
            if record is None:
                record = Record(kind='student', data={'identity': identity, 'display_name': name})
                db.add(record)
                profiles[identity] = record
            data = dict(record.data)
            previous = data.get('display_name', data.get('name'))
            if previous == legacy or not previous:
                data['display_name'] = name
                if previous:
                    data.setdefault('legacy_display_name', previous)
            else:
                data.setdefault('display_name', previous)
            data.setdefault('initial_role', role)
            record.data = data
        # Repair missing legacy references by preserving their IDs, never reassigning ownership.
        references = {}
        for record in records:
            data = record.data
            if record.kind in ('listing', 'negotiation'):
                for key, name_key in [('seller_id', 'seller'), ('buyer_id', 'buyer')]:
                    if data.get(key): references.setdefault(data[key], data.get(name_key) or 'Student')
            elif record.kind == 'session' and data.get('student'):
                references.setdefault(data['student'], 'Student')
        for identity, name in references.items():
            if identity not in profiles:
                record = Record(kind='student', data={'identity': identity, 'display_name': name})
                db.add(record)
                profiles[identity] = record
        for record in profiles.values():
            data = dict(record.data)
            data.setdefault('display_name', data.get('name', 'Student'))
            for key, value in [('university', None), ('course_or_major', None), ('created_at', timestamp)]:
                data.setdefault(key, value)
            record.data = data
        db.flush()
        # A unique ID index protects newly created profiles without changing the records schema.
        # SQLite cannot reflect expression indexes reliably. Let each database
        # handle existence atomically instead of relying on checkfirst reflection.
        db.execute(CreateIndex(student_identity_index, if_not_exists=True))
        db.add(Record(kind='migration', data={'version': MIGRATION, 'created_at': timestamp}))
        db.commit()
