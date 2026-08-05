import type { Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { memoryService } from '../memory/memory.service';
import { normalizePhone } from '../utils/jid';

export const listMessagesQuerySchema = z.object({
  phone: z.string().min(5),
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().positive().max(100).default(50),
});

export async function listMessages(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const query = listMessagesQuerySchema.parse(req.query);
    const phone = normalizePhone(query.phone);
    const result = await memoryService.listMessages(phone, query.page, query.limit);
    res.json(result);
  } catch (error) {
    next(error);
  }
}
