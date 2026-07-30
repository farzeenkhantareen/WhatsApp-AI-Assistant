import { env } from '../config/env';

export function buildSystemPrompt(userName?: string | null): string {
  const base = env.SYSTEM_PROMPT.trim();
  if (userName) {
    return `${base}\n\nThe user's display name is "${userName}". Address them naturally when appropriate.`;
  }
  return base;
}
