import { inject } from '@angular/core';
import { map, Observable } from 'rxjs';
import { ApiClient } from '@core/http/api-client.service';
import { ExecutionHistoryPort } from '../../ports/execution-history.port';
import { Execution } from '../../models/execution.model';
interface ExecutionDto { id:string; task_id:string; status:'COMPLETED'|'FAILED'; action:string|null; model_name:string|null; result:Record<string,unknown>|null; error:string|null; created_at:string; updated_at:string; validation?:Record<string,unknown>|null; changed_files?:string[]; repair_attempts?:number|null; final_diff?:string|null; }
export class FastApiExecutionHistoryAdapter implements ExecutionHistoryPort {
  private readonly api=inject(ApiClient);
  list():Observable<Execution[]> { return this.api.get<ExecutionDto[]>('/executions').pipe(map(xs=>xs.map(x=>this.map(x)))); }
  getById(taskId:string, executionId:string):Observable<Execution|null> { return this.api.get<ExecutionDto>(`/tasks/${taskId}/run/${executionId}`).pipe(map(x=>this.map(x))); }
  register(_execution:Execution):void { /* backend is source of truth */ }
  private map(x:ExecutionDto):Execution {
    const validation=(x.validation?.['runs'] as Array<Record<string,unknown>>|undefined) ?? [];
    const last=validation.length ? validation[validation.length-1] : undefined;
    return { id:x.id, task_id:x.task_id, status:x.status==='COMPLETED'?'success':'failed', started_at:x.created_at, completed_at:x.updated_at, stdout:x.result?JSON.stringify(x.result,null,2):undefined, stderr:x.error??undefined, command:x.action??undefined, sandbox_status:last?.['status'] as string|undefined, steps:[], tools_used:[], duration_ms:undefined };
  }
}
