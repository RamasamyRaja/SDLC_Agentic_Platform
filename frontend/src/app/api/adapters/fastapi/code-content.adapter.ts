import { inject } from '@angular/core';
import { map, Observable } from 'rxjs';
import { ApiClient } from '@core/http/api-client.service';
import { CodeContentPort } from '../../ports/code-content.port';
import { FileContent } from '../../models/code.model';
interface FileDto { path: string; language: string; content: string; lines: number; size: number; truncated: boolean; }
export class FastApiCodeContentAdapter implements CodeContentPort {
  private readonly api = inject(ApiClient);
  getFileContent(repositoryId: string, path: string): Observable<FileContent> {
    return this.api.get<FileDto>(`/repositories/${repositoryId}/files/content`, { path }).pipe(
      map((x) => ({ path: x.path, language: x.language, content: x.content, lines: x.lines, size: x.size, isMock: false })),
    );
  }
}
