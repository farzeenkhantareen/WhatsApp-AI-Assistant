import {
  MediaType,
  MessageRole,
  MessageStatus,
  type Message,
  type User,
} from '@prisma/client';
import { env } from '../config/env';
import { REDIS_KEYS } from '../config/constants';
import { logger } from '../config/logger';
import { prisma } from '../database/prisma';
import { redis } from '../database/redis';

export interface ContextMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  mediaType?: MediaType;
  mediaMime?: string | null;
  mediaDataUrl?: string;
}

interface CachedMessage {
  role: MessageRole;
  content: string;
  mediaType: MediaType;
  mediaMime?: string | null;
}

export class MemoryService {
  async upsertUser(phone: string, name?: string | null): Promise<User> {
    return prisma.user.upsert({
      where: { phone },
      create: { phone, name: name ?? null },
      update: name ? { name } : {},
    });
  }

  async getOrCreateConversation(userId: string) {
    const existing = await prisma.conversation.findFirst({
      where: { userId, status: 'active' },
      orderBy: { updatedAt: 'desc' },
    });
    if (existing) {
      return existing;
    }
    return prisma.conversation.create({
      data: { userId, status: 'active' },
    });
  }

  async saveMessage(input: {
    conversationId: string;
    role: MessageRole;
    content: string;
    waMessageId?: string;
    mediaType?: MediaType;
    mediaUrl?: string;
    mediaMime?: string;
    quotedWaMessageId?: string;
    aiModel?: string;
    status?: MessageStatus;
  }): Promise<Message> {
    const message = await prisma.message.create({
      data: {
        conversationId: input.conversationId,
        role: input.role,
        content: input.content,
        waMessageId: input.waMessageId,
        mediaType: input.mediaType ?? MediaType.text,
        mediaUrl: input.mediaUrl,
        mediaMime: input.mediaMime,
        quotedWaMessageId: input.quotedWaMessageId,
        aiModel: input.aiModel,
        status: input.status ?? MessageStatus.received,
      },
    });

    await prisma.conversation.update({
      where: { id: input.conversationId },
      data: { updatedAt: new Date() },
    });

    return message;
  }

  async updateMessageStatusByWaId(
    waMessageId: string,
    status: MessageStatus,
  ): Promise<void> {
    await prisma.message.updateMany({
      where: { waMessageId },
      data: { status },
    });
  }

  async cacheMessage(phone: string, message: CachedMessage): Promise<void> {
    const key = REDIS_KEYS.conversation(phone);
    await redis.rpush(key, JSON.stringify(message));
    await redis.ltrim(key, -env.MAX_CONTEXT_MESSAGES, -1);
    await redis.expire(key, env.REDIS_CONV_TTL_SECONDS);
  }

  async getContext(
    phone: string,
    conversationId: string,
  ): Promise<ContextMessage[]> {
    try {
      const cached = await redis.lrange(REDIS_KEYS.conversation(phone), 0, -1);
      if (cached.length > 0) {
        return cached.map((item) => {
          const parsed = JSON.parse(item) as CachedMessage;
          return {
            role: parsed.role as ContextMessage['role'],
            content: parsed.content,
            mediaType: parsed.mediaType,
            mediaMime: parsed.mediaMime,
          };
        });
      }
    } catch (error) {
      logger.warn({ err: error, phone }, 'Redis context miss, falling back to Postgres');
    }

    const messages = await prisma.message.findMany({
      where: {
        conversationId,
        role: { in: [MessageRole.user, MessageRole.assistant] },
      },
      orderBy: { createdAt: 'desc' },
      take: env.MAX_CONTEXT_MESSAGES,
    });

    return messages.reverse().map((m) => ({
      role: m.role as ContextMessage['role'],
      content: m.content,
      mediaType: m.mediaType,
      mediaMime: m.mediaMime,
    }));
  }

  async acquireReplyLock(phone: string, ttlSeconds = 60): Promise<boolean> {
    const result = await redis.set(
      REDIS_KEYS.replyLock(phone),
      '1',
      'EX',
      ttlSeconds,
      'NX',
    );
    return result === 'OK';
  }

  async releaseReplyLock(phone: string): Promise<void> {
    await redis.del(REDIS_KEYS.replyLock(phone));
  }

  async clearConversation(phone: string): Promise<{ deletedMessages: number }> {
    const user = await prisma.user.findUnique({ where: { phone } });
    if (!user) {
      await redis.del(REDIS_KEYS.conversation(phone));
      return { deletedMessages: 0 };
    }

    const conversations = await prisma.conversation.findMany({
      where: { userId: user.id },
      select: { id: true },
    });
    const ids = conversations.map((c) => c.id);

    const result = await prisma.message.deleteMany({
      where: { conversationId: { in: ids } },
    });

    await redis.del(REDIS_KEYS.conversation(phone));
    return { deletedMessages: result.count };
  }

  async listUsers(page = 1, limit = 50) {
    const skip = (page - 1) * limit;
    const [users, total] = await Promise.all([
      prisma.user.findMany({
        skip,
        take: limit,
        orderBy: { updatedAt: 'desc' },
        include: {
          conversations: {
            where: { status: 'active' },
            take: 1,
            orderBy: { updatedAt: 'desc' },
          },
        },
      }),
      prisma.user.count(),
    ]);
    return { users, total, page, limit };
  }

  async listMessages(phone: string, page = 1, limit = 50) {
    const user = await prisma.user.findUnique({ where: { phone } });
    if (!user) {
      return { messages: [], total: 0, page, limit };
    }

    const conversation = await prisma.conversation.findFirst({
      where: { userId: user.id, status: 'active' },
      orderBy: { updatedAt: 'desc' },
    });

    if (!conversation) {
      return { messages: [], total: 0, page, limit };
    }

    const skip = (page - 1) * limit;
    const [messages, total] = await Promise.all([
      prisma.message.findMany({
        where: { conversationId: conversation.id },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.message.count({ where: { conversationId: conversation.id } }),
    ]);

    return { messages: messages.reverse(), total, page, limit, conversationId: conversation.id };
  }
}

export const memoryService = new MemoryService();
