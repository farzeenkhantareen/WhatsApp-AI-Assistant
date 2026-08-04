import fs from 'fs/promises';
import path from 'path';
import { env } from '../config/env';
import { logger } from '../config/logger';

export async function ensureDir(dir: string): Promise<void> {
  await fs.mkdir(dir, { recursive: true });
}

export async function saveMediaBuffer(
  phone: string,
  fileName: string,
  buffer: Buffer,
): Promise<string> {
  if (buffer.byteLength > env.MAX_MEDIA_BYTES) {
    throw new Error(
      `Media exceeds MAX_MEDIA_BYTES (${buffer.byteLength} > ${env.MAX_MEDIA_BYTES})`,
    );
  }

  const dir = path.join(env.MEDIA_DIR, phone);
  await ensureDir(dir);
  const safeName = fileName.replace(/[^a-zA-Z0-9._-]/g, '_');
  const fullPath = path.join(dir, `${Date.now()}_${safeName}`);
  await fs.writeFile(fullPath, buffer);
  logger.debug({ fullPath, bytes: buffer.byteLength }, 'Media saved');
  return fullPath;
}

export function bufferToDataUrl(buffer: Buffer, mime: string): string {
  return `data:${mime};base64,${buffer.toString('base64')}`;
}

export async function clearAuthDir(authDir: string): Promise<void> {
  try {
    await fs.rm(authDir, { recursive: true, force: true });
    await ensureDir(authDir);
    logger.warn({ authDir }, 'Auth directory cleared for re-authentication');
  } catch (error) {
    logger.error({ err: error, authDir }, 'Failed to clear auth directory');
    throw error;
  }
}
