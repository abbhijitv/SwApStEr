from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from backend.models.database import Session, Record
from backend.models.schemas import Listing

def get(kind, id):
    with Session() as db:
        r = db.get(Record, id)
        return dict(r.data, id=r.id) if r and r.kind == kind else None

def all_records(kind):
    with Session() as db:
        return [dict(r.data, id=r.id) for r in db.query(Record).filter_by(kind=kind).order_by(Record.id).all()]

def save(kind, data, id=None):
    data = dict(data); data.pop('id', None)
    with Session() as db:
        r = db.get(Record, id) if id else Record(kind=kind)
        r.data = data
        db.add(r); db.commit(); db.refresh(r)
        return dict(r.data, id=r.id)

def public_listing(item):
    from backend.services.students import student_by_id
    result = {k:v for k,v in item.items() if k != 'minimum'}
    seller = student_by_id(item.get('seller_id'))
    if seller:
        result['seller'] = seller['display_name']
    return result

def seed():
    from backend.services.students import migrate_students
    migrate_students()
    if all_records('listing'): return
    now = datetime.now(ZoneInfo('America/Phoenix'))
    days = (2-now.weekday()) % 7 or 7
    wed = (now + timedelta(days=days)).replace(hour=16, minute=0, second=0, microsecond=0)
    for name, cat, course, price, minimum, typ, icon in [
        ('TI-84 Plus CE Graphing Calculator','Calculators','MAT 265',35,20,'Rent','calculator'),
        ('Calculus: Early Transcendentals','Textbooks','MAT 266',45,30,'Buy','book'),
        ('Arduino Engineering Starter Kit','Lab kits','EEE 202',28,18,'Rent','cpu'),
        ('University Physics, 15th Edition','Textbooks','PHY 121',40,25,'Buy','book'),
        ('Precision Drafting Tool Set','Drafting','MAE 214',18,12,'Rent','ruler'),
        ('TI-Nspire CX II · premium rental','Calculators','MAT 267',65,50,'Rent','calculator')]:
        item = Listing(title=name,description=f'Ready for your next {course} class. Carefully maintained by a fellow Sun Devil. Includes all essential accessories.',category=cat,course=course,price=price,minimum=minimum,type=typ,windows=[{'start':wed,'end':wed.replace(hour=20)}],available_until=wed+timedelta(days=10))
        save('listing',dict(item.model_dump(mode='json'),seller='Shorya Moses',seller_id='student-b',icon=icon))
