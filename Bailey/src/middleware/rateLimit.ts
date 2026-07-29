import type { NextFunction, Request, Response } from 'express';
import { rateLimitService } from '../services/rate-limit.service';
import { logger } from '../config/logger';

export async function rateLimit(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const ip =
      (req.headers['x-forwarded-for'] as string | undefined)?.split(',')[0]?.trim() ||
      req.ip ||
      'unknown';

    const result = await rateLimitService.hitIp(ip);
    res.setHeader('X-RateLimit-Limit', String(result.limit));
    res.setHeader('X-RateLimit-Remaining', String(result.remaining));

    if (!result.allowed) {
      res.status(429).json({ error: 'Too many requests' });
      return;
    }
    next();
  } catch (error) {
    logger.error({ err: error }, 'Rate limit middleware failed, allowing request');
    next();
  }
}
