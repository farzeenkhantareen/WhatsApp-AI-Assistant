import { config as loadEnv } from 'dotenv';
import { z } from 'zod';

loadEnv();

const envSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().positive().default(3000),
  LOG_LEVEL: z
    .enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace', 'silent'])
    .default('info'),
  API_KEY: z.string().min(16, 'API_KEY must be at least 16 characters'),

  OPENROUTER_API_KEY: z.string().min(1, 'OPENROUTER_API_KEY is required'),
  OPENROUTER_MODEL: z.string().min(1).default('openai/gpt-4o-mini'),
  OPENROUTER_BASE_URL: z.string().url().default('https://openrouter.ai/api/v1'),
  OPENROUTER_HTTP_REFERER: z.string().url().default('http://localhost:3000'),
  OPENROUTER_APP_TITLE: z.string().default('Bailey WhatsApp AI Assistant'),

  SYSTEM_PROMPT: z
    .string()
    .min(1)
    .default('You are a helpful WhatsApp assistant. Be concise, friendly, and accurate.'),
  MAX_CONTEXT_MESSAGES: z.coerce.number().int().positive().default(20),
  AI_MAX_RETRIES: z.coerce.number().int().nonnegative().default(3),
  SEND_MAX_RETRIES: z.coerce.number().int().nonnegative().default(3),

  DATABASE_URL: z.string().min(1, 'DATABASE_URL is required'),
  REDIS_URL: z.string().min(1, 'REDIS_URL is required'),
  REDIS_CONV_TTL_SECONDS: z.coerce.number().int().positive().default(3600),

  AUTH_DIR: z.string().default('./auth_info'),
  MEDIA_DIR: z.string().default('./media'),
  ALLOW_GROUPS: z
    .string()
    .default('false')
    .transform((v) => v.toLowerCase() === 'true' || v === '1'),
  MAX_MEDIA_BYTES: z.coerce.number().int().positive().default(16 * 1024 * 1024),

  RATE_LIMIT_WINDOW_MS: z.coerce.number().int().positive().default(60_000),
  RATE_LIMIT_MAX: z.coerce.number().int().positive().default(60),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
  console.error('Invalid environment configuration:');
  for (const issue of parsed.error.issues) {
    console.error(`  - ${issue.path.join('.')}: ${issue.message}`);
  }
  process.exit(1);
}

export const env = parsed.data;
export type Env = z.infer<typeof envSchema>;
