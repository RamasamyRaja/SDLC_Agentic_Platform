from pydantic import BaseModel
class FileContentResponse(BaseModel):
    path: str
    language: str
    content: str
    lines: int
    size: int
    truncated: bool = False
