import { Observable, of, delay } from 'rxjs';
import { CodeContentPort } from '../../ports/code-content.port';
import { FileContent } from '../../models/code.model';
import { getMockFileContent } from './code.fixtures';

export class MockCodeContentAdapter implements CodeContentPort {
  getFileContent(repositoryId: string, path: string): Observable<FileContent> {
    return of(getMockFileContent(repositoryId, path)).pipe(delay(150));
  }
}
