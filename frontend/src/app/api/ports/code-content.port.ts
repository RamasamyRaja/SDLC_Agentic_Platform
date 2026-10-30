import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import { FileContent } from '../models/code.model';

export interface CodeContentPort {
  getFileContent(repositoryId: string, path: string): Observable<FileContent>;
}

export const CODE_CONTENT_PORT = new InjectionToken<CodeContentPort>('CODE_CONTENT_PORT');
