from fastapi import FastAPI, HTTPException, Depends
from backend.routes.negotiations import identity
from fastapi.middleware.cors import CORSMiddleware
from backend.services.store import seed, all_records, get, save, public_listing
from backend.models.schemas import Listing, StudentCreate
from backend.services.students import students, student_by_id, create_student
from backend.routes.negotiations import demo_only
from backend.models.database import initialize_local_database
app = FastAPI(title="SwApStEr")
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
if initialize_local_database():
    seed()
@app.get('/health')
def health(): return {'status':'ok'}
@app.get('/listings')
def listings(): return [public_listing(x) for x in all_records('listing')]
@app.get('/listings/{id}')
def listing(id:int):
    x=get('listing',id)
    if not x: raise HTTPException(404,'Listing not found')
    return public_listing(x)
@app.post('/listings',status_code=201)
def create_listing(body:Listing, student=Depends(identity)):
    return public_listing(save('listing',dict(body.model_dump(mode='json'),seller=student_by_id(student)['display_name'],seller_id=student,icon={'Calculators':'calculator','Lab kits':'cpu','Drafting':'ruler'}.get(body.category,'book'))))
from backend.routes.negotiations import router
app.include_router(router)
from backend.routes.auth import router as auth_router
app.include_router(auth_router)
from backend.routes.marketplace import router as marketplace_router
app.include_router(marketplace_router)

@app.get('/students')
def list_students():
    demo_only()
    return students()

@app.get('/students/{id}')
def retrieve_student(id: str):
    demo_only()
    profile = student_by_id(id)
    if not profile: raise HTTPException(404, 'Student not found')
    return profile

@app.post('/students', status_code=201)
def add_student(body: StudentCreate):
    demo_only()
    return create_student(body)
