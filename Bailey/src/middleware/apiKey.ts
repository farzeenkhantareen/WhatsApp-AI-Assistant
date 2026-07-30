import type { NextFunction, Request, Response } from 'express';
import { env } from '../config/env';

export function apiKeyAuth(req: Request, res: Response, next: NextFunction): void {
  const headerKey = req.header('x-api-key');
  const authHeader = req.header('authorization');
  const bearer =
    authHeader?.toLowerCase().startsWith('bearer ')
      ? authHeader.slice(7).trim()
      : undefined;

  const provided = headerKey ?? bearer;
  if (!provided || provided !== env.API_KEY) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }
  next();
}
