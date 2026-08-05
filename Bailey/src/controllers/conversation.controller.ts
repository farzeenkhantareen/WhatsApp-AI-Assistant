import type { Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { memoryService } from '../memory/memory.service';
import { normalizePhone } from '../utils/jid';

export const deleteConversationParamsSchema = z.object({
  phone: z.string().min(5),
});

export async function deleteConversation(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const { phone: rawPhone } = deleteConversationParamsSchema.parse(req.params);
    const phone = normalizePhone(rawPhone);
    const result = await memoryService.clearConversation(phone);
    res.json({
      ok: true,
      phone,
      deletedMessages: result.deletedMessages,
    });
  } catch (error) {
    next(error);
  }
}
