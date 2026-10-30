from datetime import datetime
from pydantic import BaseModel
class ReportResponse(BaseModel):
    id:str; taskId:str; taskTitle:str; repositoryId:str; repositoryName:str; status:str; generatedAt:datetime; updatedAt:datetime
    taskSummary:str; repositoryContext:str; analysisSummary:str; agentSummary:str; retrievedContextSummary:str; toolsUsed:list[str]; executionResults:str; warnings:list[str]; errors:list[str]; finalOutcome:str
