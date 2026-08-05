import type { Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { memoryService } from '../memory/memory.service';

export const listUsersQuerySchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().positive().max(100).default(50),
});

export async function listUsers(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const { page, limit } = listUsersQuerySchema.parse(req.query);
    const result = await memoryService.listUsers(page, limit);
    res.json(result);
  } catch (error) {
    next(error);
  }
}
