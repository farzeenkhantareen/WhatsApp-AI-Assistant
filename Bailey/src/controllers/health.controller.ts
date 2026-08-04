import type { Request, Response, NextFunction } from 'express';
import { prisma } from '../database/prisma';
import { isRedisHealthy } from '../database/redis';
import { whatsappService } from '../services/whatsapp.service';

export async function health(
  _req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    let databaseOk = false;
    try {
      await prisma.$queryRaw`SELECT 1`;
      databaseOk = true;
    } catch {
      databaseOk = false;
    }

    const redisOk = await isRedisHealthy();
    const whatsappStatus = await whatsappService.getSessionStatus();
    const whatsappOk = whatsappService.isConnected;

    const ok = databaseOk && redisOk;

    res.status(ok ? 200 : 503).json({
      status: ok ? 'ok' : 'degraded',
      uptime: process.uptime(),
      checks: {
        database: databaseOk ? 'up' : 'down',
        redis: redisOk ? 'up' : 'down',
        whatsapp: {
          status: whatsappStatus,
          connected: whatsappOk,
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    next(error);
  }
}
