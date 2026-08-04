import { MediaType, MessageStatus } from '@prisma/client';
import { env } from '../config/env';
import { logger } from '../config/logger';
import { eventBus, type IncomingMessagePayload } from '../events/eventBus';
import { memoryService } from '../memory/memory.service';
import { openRouterService } from './openrouter.service';
import { whatsappService } from './whatsapp.service';

export class MessageService {
  register(): void {
    eventBus.on('message.received', (payload) => {
      void this.handleIncoming(payload);
    });

    eventBus.on('message.delivered', async ({ waMessageId }) => {
      try {
        await memoryService.updateMessageStatusByWaId(
          waMessageId,
          MessageStatus.delivered,
        );
      } catch (error) {
        logger.error({ err: error, waMessageId }, 'Failed to persist delivered status');
      }
    });

    eventBus.on('message.read', async ({ waMessageId }) => {
      try {
        await memoryService.updateMessageStatusByWaId(
          waMessageId,
          MessageStatus.read,
        );
      } catch (error) {
        logger.error({ err: error, waMessageId }, 'Failed to persist read status');
      }
    });
  }

  private async handleIncoming(payload: IncomingMessagePayload): Promise<void> {
    const { phone } = payload;
    const locked = await memoryService.acquireReplyLock(phone);
    if (!locked) {
      logger.warn({ phone }, 'Reply already in progress, skipping duplicate');
      return;
    }

    try {
      const user = await memoryService.upsertUser(phone, payload.pushName);
      const conversation = await memoryService.getOrCreateConversation(user.id);

      const mediaType = payload.mediaType as MediaType;
      const contentForStore =
        payload.text ||
        `[${payload.mediaType} message${payload.mediaMime ? `: ${payload.mediaMime}` : ''}]`;

      await memoryService.saveMessage({
        conversationId: conversation.id,
        role: 'user',
        content: contentForStore,
        waMessageId: payload.waMessageId,
        mediaType,
        mediaUrl: payload.mediaPath,
        mediaMime: payload.mediaMime,
        quotedWaMessageId: payload.quotedWaMessageId,
        status: MessageStatus.received,
      });

      await memoryService.cacheMessage(phone, {
        role: 'user',
        content: contentForStore,
        mediaType,
        mediaMime: payload.mediaMime,
      });

      const history = await memoryService.getContext(phone, conversation.id);
      // Exclude the message we just saved from history duplication for the model prompt
      const historyWithoutLatest = history.slice(0, -1);

      await whatsappService.setTyping(phone, true);

      const reply = await openRouterService.generateReply({
        history: historyWithoutLatest,
        userName: user.name,
        latestUserText: payload.text,
        mediaType,
        mediaMime: payload.mediaMime,
        mediaBuffer: payload.mediaBuffer,
      });

      const waMessageId = await whatsappService.sendText(phone, reply, {
        quoted: payload.raw,
      });

      await memoryService.saveMessage({
        conversationId: conversation.id,
        role: 'assistant',
        content: reply,
        waMessageId,
        mediaType: MediaType.text,
        aiModel: env.OPENROUTER_MODEL,
        status: MessageStatus.sent,
      });

      await memoryService.cacheMessage(phone, {
        role: 'assistant',
        content: reply,
        mediaType: MediaType.text,
      });
    } catch (error) {
      logger.error({ err: error, phone }, 'Message pipeline failed');
      eventBus.emit('error', { error, context: 'message.pipeline' });
      try {
        await whatsappService.sendText(
          phone,
          'Sorry, I ran into an error processing your message. Please try again shortly.',
        );
      } catch (sendError) {
        logger.error({ err: sendError, phone }, 'Failed to send error reply');
      }
    } finally {
      await whatsappService.setTyping(phone, false).catch(() => undefined);
      await memoryService.releaseReplyLock(phone);
    }
  }

  async sendOutbound(input: {
    phone: string;
    message: string;
    quotedMessageId?: string;
  }): Promise<{ waMessageId: string }> {
    const user = await memoryService.upsertUser(input.phone);
    const conversation = await memoryService.getOrCreateConversation(user.id);

    const waMessageId = await whatsappService.sendText(input.phone, input.message);

    await memoryService.saveMessage({
      conversationId: conversation.id,
      role: 'assistant',
      content: input.message,
      waMessageId,
      quotedWaMessageId: input.quotedMessageId,
      aiModel: 'manual',
      status: MessageStatus.sent,
    });

    await memoryService.cacheMessage(input.phone, {
      role: 'assistant',
      content: input.message,
      mediaType: MediaType.text,
    });

    return { waMessageId };
  }
}

export const messageService = new MessageService();
