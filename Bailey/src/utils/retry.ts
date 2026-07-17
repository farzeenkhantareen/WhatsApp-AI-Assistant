import { logger } from '../config/logger';
import { jitteredBackoff, sleep } from './sleep';

export interface RetryOptions {
  retries: number;
  baseMs?: number;
  maxMs?: number;
  label?: string;
  shouldRetry?: (error: unknown) => boolean;
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions,
): Promise<T> {
  const { retries, baseMs = 500, maxMs = 15_000, label = 'operation', shouldRetry } = options;
  let lastError: unknown;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      const retryable = shouldRetry ? shouldRetry(error) : true;
      if (!retryable || attempt === retries) {
        break;
      }
      const delay = jitteredBackoff(attempt, baseMs, maxMs);
      logger.warn(
        { err: error, attempt: attempt + 1, retries, delay, label },
        `${label} failed, retrying`,
      );
      await sleep(delay);
    }
  }

  throw lastError;
}
