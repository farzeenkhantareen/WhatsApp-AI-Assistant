import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import { apiKeyAuth } from './middleware/apiKey';
import { rateLimit } from './middleware/rateLimit';
import { validate } from './middleware/validate';
import { errorHandler, notFoundHandler } from './middleware/errorHandler';
import { health } from './controllers/health.controller';
import { listUsers, listUsersQuerySchema } from './controllers/users.controller';
import {
  listMessages,
  listMessagesQuerySchema,
} from './controllers/messages.controller';
import { sendMessage, sendBodySchema } from './controllers/send.controller';
import {
  deleteConversation,
  deleteConversationParamsSchema,
} from './controllers/conversation.controller';

export function createApp() {
  const app = express();

  app.set('trust proxy', 1);
  app.use(helmet());
  app.use(cors());
  app.use(express.json({ limit: '1mb' }));

  app.get('/health', health);

  app.use(rateLimit);
  app.use(apiKeyAuth);

  app.get('/users', validate(listUsersQuerySchema, 'query'), listUsers);
  app.get('/messages', validate(listMessagesQuerySchema, 'query'), listMessages);
  app.post('/send', validate(sendBodySchema, 'body'), sendMessage);
  app.delete(
    '/conversation/:phone',
    validate(deleteConversationParamsSchema, 'params'),
    deleteConversation,
  );

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
