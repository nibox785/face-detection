from fastapi import FastAPI
from backend.api.routes import router

app = FastAPI(title="Face Attendance System")

app.include_router(router)

@app.get("/")
def root():
    return {"message": "Face Attendance API is running"}