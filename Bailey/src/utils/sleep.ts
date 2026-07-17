export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function jitteredBackoff(attempt: number, baseMs = 500, maxMs = 15_000): number {
  const exp = Math.min(maxMs, baseMs * 2 ** attempt);
  const jitter = Math.floor(Math.random() * Math.min(250, exp * 0.2));
  return exp + jitter;
}
