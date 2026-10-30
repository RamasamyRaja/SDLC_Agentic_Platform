from enum import Enum
from pydantic import BaseModel, Field
class SandboxCommand(str, Enum):
    AUTO="auto"; COMPILE="compile"; TEST="test"; LINT="lint"; BUILD="build"
class SandboxRequest(BaseModel): command: SandboxCommand=SandboxCommand.AUTO
class SandboxResponse(BaseModel):
    id:str; task_id:str; repository_id:str; command:str; status:str; exit_code:int|None=None; stdout:str=""; stderr:str=""; duration_ms:int|None=None; metadata:dict=Field(default_factory=dict)
