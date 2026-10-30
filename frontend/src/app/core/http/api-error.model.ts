export interface ApiError {
  status: number;
  message: string;
  detail?: string;
  url?: string;
}

export function createApiError(
  status: number,
  message: string,
  options?: { detail?: string; url?: string },
): ApiError {
  return {
    status,
    message,
    detail: options?.detail,
    url: options?.url,
  };
}

export function isApiError(value: unknown): value is ApiError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'status' in value &&
    'message' in value &&
    typeof (value as ApiError).status === 'number' &&
    typeof (value as ApiError).message === 'string'
  );
}
