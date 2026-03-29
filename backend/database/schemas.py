from pydantic import BaseModel
from typing import List, Optional

class RecognizeResult(BaseModel):
    student_id: Optional[int]
    score: float

class RecognizeResponse(BaseModel):
    results: List[RecognizeResult]
    message: Optional[str] = None