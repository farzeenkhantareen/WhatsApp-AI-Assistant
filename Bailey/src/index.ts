import { createApp } from './app';
import { env } from './config/env';
import { logger } from './config/logger';
import { connectDatabase, disconnectDatabase } from './database/prisma';
import { connectRedis, disconnectRedis } from './database/redis';
import { eventBus } from './events/eventBus';
import { messageService } from './services/message.service';
import { whatsappService } from './services/whatsapp.service';
import { ensureDir } from './utils/media';

async function bootstrap(): Promise<void> {
  await ensureDir(env.AUTH_DIR);
  await ensureDir(env.MEDIA_DIR);

  await connectDatabase();
  await connectRedis();

  messageService.register();

  eventBus.on('connection.open', () => {
    logger.info('Event: connection.open');
  });
  eventBus.on('connection.close', (payload) => {
    logger.warn({ payload }, 'Event: connection.close');
  });
  eventBus.on('qr.generated', () => {
    logger.info('Event: qr.generated');
  });
  eventBus.on('message.sent', (payload) => {
    logger.info({ phone: payload.phone, waMessageId: payload.waMessageId }, 'Event: message.sent');
  });
  eventBus.on('error', ({ error, context }) => {
    logger.error({ err: error, context }, 'Event: error');
  });

  await whatsappService.start();

  const app = createApp();
  const server = app.listen(env.PORT, () => {
    logger.info({ port: env.PORT }, 'HTTP server listening');
  });

  const shutdown = async (signal: string) => {
    logger.info({ signal }, 'Shutting down');
    server.close();
    await disconnectRedis();
    await disconnectDatabase();
    process.exit(0);
  };

  process.on('SIGINT', () => void shutdown('SIGINT'));
  process.on('SIGTERM', () => void shutdown('SIGTERM'));

  process.on('unhandledRejection', (reason) => {
    logger.error({ err: reason }, 'Unhandled rejection');
  });

  process.on('uncaughtException', (error) => {
    logger.error({ err: error }, 'Uncaught exception');
  });
}

bootstrap().catch((error) => {
  logger.error({ err: error }, 'Bootstrap failed');
  process.exit(1);
});
