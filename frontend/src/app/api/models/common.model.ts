export type RequestStatus = 'idle' | 'loading' | 'success' | 'error';

export interface RequestState<T> {
  status: RequestStatus;
  data: T | null;
  error: string | null;
}

export type StatusVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'running';

export function initialRequestState<T>(): RequestState<T> {
  return { status: 'idle', data: null, error: null };
}
