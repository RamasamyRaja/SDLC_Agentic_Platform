import { inject } from '@angular/core';
import { map, Observable } from 'rxjs';
import { ApiClient } from '@core/http/api-client.service';
import { ReportPort } from '../../ports/report.port';
import { EngineeringReport } from '../../models/report.model';
interface ReportDto { id:string; taskId:string; taskTitle:string; repositoryId:string; repositoryName:string; status:string; generatedAt:string; updatedAt:string; taskSummary:string; repositoryContext:string; analysisSummary:string; agentSummary:string; retrievedContextSummary:string; toolsUsed:string[]; executionResults:string; warnings:string[]; errors:string[]; finalOutcome:string; }
export class FastApiReportAdapter implements ReportPort {
  private readonly api=inject(ApiClient);
  list():Observable<EngineeringReport[]> { return this.api.get<ReportDto[]>('/reports').pipe(map(xs=>xs.map(x=>this.map(x)))); }
  getById(id:string):Observable<EngineeringReport> { return this.api.get<ReportDto>(`/reports/${id}`).pipe(map(x=>this.map(x))); }
  private map(x:ReportDto):EngineeringReport { return { id:x.id,taskId:x.taskId,taskTitle:x.taskTitle,repositoryId:x.repositoryId,repositoryName:x.repositoryName,status:(x.status==='complete'?'complete':x.status==='failed'?'failed':'draft') as EngineeringReport['status'],generatedAt:x.generatedAt,updatedAt:x.updatedAt,taskSummary:x.taskSummary,repositoryContext:x.repositoryContext,analysisSummary:x.analysisSummary,agentSummary:x.agentSummary,retrievedContextSummary:x.retrievedContextSummary,toolsUsed:x.toolsUsed,executionResults:x.executionResults,warnings:x.warnings,errors:x.errors,finalOutcome:x.finalOutcome }; }
}
