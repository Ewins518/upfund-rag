from pydantic import BaseModel, Field
from typing import List, Optional

class AskRequest(BaseModel):
    question: str = Field(..., description="User natural language question")
    k: int = Field(5, ge=1, le=20, description="Top-k retrieved chunks")

class Source(BaseModel):
    file: str
    chunk_id: str
    score: float
    snippet: str

class AskResponse(BaseModel):
    answer: str
    sources: List[Source]

class ReindexRequest(BaseModel):
    docs_dir: Optional[str] = Field(default="data/raw_documents")
    clear: bool = Field(default=False, description="Clear namespace before reindexing")