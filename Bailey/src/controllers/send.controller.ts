import type { Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { messageService } from '../services/message.service';
import { whatsappService } from '../services/whatsapp.service';
import { HttpError } from '../middleware/errorHandler';
import { normalizePhone } from '../utils/jid';

export const sendBodySchema = z.object({
  phone: z.string().min(5),
  message: z.string().min(1).max(4096),
  quotedMessageId: z.string().optional(),
});

export async function sendMessage(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    if (!whatsappService.isConnected) {
      throw new HttpError(503, 'WhatsApp is not connected');
    }

    const body = sendBodySchema.parse(req.body);
    const phone = normalizePhone(body.phone);
    const result = await messageService.sendOutbound({
      phone,
      message: body.message,
      quotedMessageId: body.quotedMessageId,
    });

    res.status(201).json({
      ok: true,
      phone,
      waMessageId: result.waMessageId,
    });
  } catch (error) {
    next(error);
  }
}
