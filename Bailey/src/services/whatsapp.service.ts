import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  getContentType,
  isJidBroadcast,
  isJidGroup,
  useMultiFileAuthState,
  type WAMessage,
  type WASocket,
} from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';
import path from 'path';
import { env } from '../config/env';
import { REDIS_KEYS, SESSION_STATUS } from '../config/constants';
import { logger } from '../config/logger';
import { redis } from '../database/redis';
import { eventBus } from '../events/eventBus';
import type { IncomingMessagePayload } from '../events/eventBus';
import { isBroadcastJid, isGroupJid, jidToPhone, phoneToJid } from '../utils/jid';
import { clearAuthDir, ensureDir, saveMediaBuffer } from '../utils/media';
import { withRetry } from '../utils/retry';
import { sleep } from '../utils/sleep';

function getDisconnectStatusCode(error: unknown): number | undefined {
  if (
    error &&
    typeof error === 'object' &&
    'output' in error &&
    error.output &&
    typeof error.output === 'object' &&
    'statusCode' in error.output
  ) {
    return Number((error.output as { statusCode: number }).statusCode);
  }
  return undefined;
}

export class WhatsAppService {
  private sock: WASocket | null = null;
  private reconnecting = false;
  private started = false;

  get socket(): WASocket | null {
    return this.sock;
  }

  get isConnected(): boolean {
    return Boolean(this.sock?.user);
  }

  async start(): Promise<void> {
    if (this.started) return;
    this.started = true;
    await ensureDir(env.AUTH_DIR);
    await ensureDir(env.MEDIA_DIR);
    await this.connect();
  }

  async connect(): Promise<void> {
    await this.setSessionStatus(SESSION_STATUS.connecting);

    const { state, saveCreds } = await useMultiFileAuthState(env.AUTH_DIR);

    const sock = makeWASocket({
      auth: state,
      printQRInTerminal: false,
      syncFullHistory: false,
      markOnlineOnConnect: true,
      generateHighQualityLinkPreview: false,
    });

    this.sock = sock;

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        await this.setSessionStatus(SESSION_STATUS.qr);
        logger.info('Scan the QR code below with WhatsApp > Linked Devices');
        qrcode.generate(qr, { small: true });
        eventBus.emit('qr.generated', { qr });
      }

      if (connection === 'open') {
        this.reconnecting = false;
        await this.setSessionStatus(SESSION_STATUS.open);
        logger.info({ jid: sock.user?.id }, 'WhatsApp connection opened');
        eventBus.emit('connection.open');
      }

      if (connection === 'close') {
        const statusCode = getDisconnectStatusCode(lastDisconnect?.error);
        const loggedOut = statusCode === DisconnectReason.loggedOut;
        await this.setSessionStatus(SESSION_STATUS.close);
        logger.warn({ statusCode, loggedOut }, 'WhatsApp connection closed');
        eventBus.emit('connection.close', { statusCode, loggedOut });

        if (loggedOut) {
          await clearAuthDir(path.resolve(env.AUTH_DIR));
        }

        if (!this.reconnecting) {
          this.reconnecting = true;
          const delay = loggedOut ? 1000 : 3000;
          logger.info({ delay, loggedOut }, 'Scheduling WhatsApp reconnect');
          await sleep(delay);
          this.reconnecting = false;
          try {
            await this.connect();
          } catch (error) {
            logger.error({ err: error }, 'Reconnect failed');
            eventBus.emit('error', { error, context: 'whatsapp.reconnect' });
            this.reconnecting = false;
            await sleep(5000);
            await this.connect();
          }
        }
      }
    });

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
      if (type !== 'notify') return;
      for (const message of messages) {
        try {
          await this.handleIncomingMessage(message);
        } catch (error) {
          logger.error({ err: error }, 'Failed handling incoming message');
          eventBus.emit('error', { error, context: 'whatsapp.message.received' });
        }
      }
    });

    sock.ev.on('messages.update', async (updates) => {
      for (const update of updates) {
        try {
          const key = update.key;
          const status = update.update?.status;
          if (!key?.id || status == null) continue;

          const phone = key.remoteJid ? jidToPhone(key.remoteJid) : undefined;

          // Baileys status: 3 = DELIVERY_ACK, 4 = READ
          if (status === 3) {
            eventBus.emit('message.delivered', {
              waMessageId: key.id,
              status: 'delivered',
              phone,
            });
          } else if (status === 4) {
            eventBus.emit('message.read', {
              waMessageId: key.id,
              status: 'read',
              phone,
            });
          }
        } catch (error) {
          logger.error({ err: error }, 'Failed handling message status update');
          eventBus.emit('error', { error, context: 'whatsapp.message.status' });
        }
      }
    });
  }

  private async handleIncomingMessage(message: WAMessage): Promise<void> {
    if (!message.message || message.key.fromMe) return;

    const remoteJid = message.key.remoteJid;
    if (!remoteJid) return;

    if (isJidBroadcast(remoteJid) || isBroadcastJid(remoteJid)) return;
    if ((isJidGroup(remoteJid) || isGroupJid(remoteJid)) && !env.ALLOW_GROUPS) {
      return;
    }

    const phone = jidToPhone(remoteJid);
    const waMessageId = message.key.id ?? `${phone}-${Date.now()}`;
    const contentType = getContentType(message.message);
    const parsed = await this.extractContent(message, phone, contentType);

    if (!parsed) return;

    // Read receipt + presence
    try {
      if (message.key) {
        await this.sock?.readMessages([message.key]);
      }
      await this.sock?.sendPresenceUpdate('available', remoteJid);
    } catch (error) {
      logger.debug({ err: error }, 'Failed to send read/presence');
    }

    const payload: IncomingMessagePayload = {
      waMessageId,
      from: remoteJid,
      phone,
      pushName: message.pushName ?? undefined,
      text: parsed.text,
      mediaType: parsed.mediaType,
      mediaPath: parsed.mediaPath,
      mediaMime: parsed.mediaMime,
      mediaBuffer: parsed.mediaBuffer,
      quotedWaMessageId: parsed.quotedWaMessageId,
      raw: message,
    };

    eventBus.emit('message.received', payload);
  }

  private async extractContent(
    message: WAMessage,
    phone: string,
    contentType?: string,
  ): Promise<{
    text: string;
    mediaType: IncomingMessagePayload['mediaType'];
    mediaPath?: string;
    mediaMime?: string;
    mediaBuffer?: Buffer;
    quotedWaMessageId?: string;
  } | null> {
    const msg = message.message;
    if (!msg) return null;

    const quoted =
      msg.extendedTextMessage?.contextInfo?.stanzaId ??
      msg.imageMessage?.contextInfo?.stanzaId ??
      msg.audioMessage?.contextInfo?.stanzaId ??
      msg.documentMessage?.contextInfo?.stanzaId ??
      undefined;

    if (contentType === 'conversation' || contentType === 'extendedTextMessage') {
      const text =
        msg.conversation ||
        msg.extendedTextMessage?.text ||
        '';
      if (!text.trim()) return null;
      return {
        text: text.trim(),
        mediaType: 'text',
        quotedWaMessageId: quoted,
      };
    }

    if (contentType === 'imageMessage' && msg.imageMessage) {
      const buffer = await this.downloadMedia(message);
      const mime = msg.imageMessage.mimetype ?? 'image/jpeg';
      const mediaPath = await saveMediaBuffer(phone, `image.${mime.split('/')[1] ?? 'jpg'}`, buffer);
      return {
        text: (msg.imageMessage.caption ?? '').trim(),
        mediaType: 'image',
        mediaPath,
        mediaMime: mime,
        mediaBuffer: buffer,
        quotedWaMessageId: quoted,
      };
    }

    if (contentType === 'audioMessage' && msg.audioMessage) {
      const buffer = await this.downloadMedia(message);
      const mime = msg.audioMessage.mimetype ?? 'audio/ogg';
      const ext = mime.includes('mpeg') ? 'mp3' : 'ogg';
      const mediaPath = await saveMediaBuffer(phone, `audio.${ext}`, buffer);
      return {
        text: '',
        mediaType: 'audio',
        mediaPath,
        mediaMime: mime,
        mediaBuffer: buffer,
        quotedWaMessageId: quoted,
      };
    }

    if (contentType === 'documentMessage' && msg.documentMessage) {
      const buffer = await this.downloadMedia(message);
      const mime = msg.documentMessage.mimetype ?? 'application/octet-stream';
      const fileName = msg.documentMessage.fileName ?? 'document';
      const isPdf =
        mime === 'application/pdf' || fileName.toLowerCase().endsWith('.pdf');
      const mediaPath = await saveMediaBuffer(phone, fileName, buffer);
      return {
        text: (msg.documentMessage.caption ?? fileName).trim(),
        mediaType: isPdf ? 'pdf' : 'document',
        mediaPath,
        mediaMime: mime,
        mediaBuffer: buffer,
        quotedWaMessageId: quoted,
      };
    }

    logger.debug({ contentType }, 'Unsupported message type ignored');
    return null;
  }

  private async downloadMedia(message: WAMessage): Promise<Buffer> {
    if (!this.sock) {
      throw new Error('WhatsApp socket not ready');
    }
    const buffer = await downloadMediaMessage(
      message,
      'buffer',
      {},
      {
        logger: logger as never,
        reuploadRequest: this.sock.updateMediaMessage,
      },
    );
    return buffer as Buffer;
  }

  async sendText(
    phone: string,
    text: string,
    options?: { quoted?: WAMessage },
  ): Promise<string> {
    if (!this.sock) {
      throw new Error('WhatsApp is not connected');
    }

    const jid = phoneToJid(phone);

    const sent = await withRetry(
      async () => {
        await this.sock!.sendPresenceUpdate('composing', jid);
        const result = await this.sock!.sendMessage(
          jid,
          { text },
          options?.quoted ? { quoted: options.quoted } : undefined,
        );
        await this.sock!.sendPresenceUpdate('paused', jid);
        return result;
      },
      {
        retries: env.SEND_MAX_RETRIES,
        label: 'whatsapp.send',
      },
    );

    const waMessageId = sent?.key?.id ?? `local-${Date.now()}`;
    eventBus.emit('message.sent', { waMessageId, phone, content: text });
    return waMessageId;
  }

  async setTyping(phone: string, composing: boolean): Promise<void> {
    if (!this.sock) return;
    const jid = phoneToJid(phone);
    await this.sock.sendPresenceUpdate(composing ? 'composing' : 'paused', jid);
  }

  private async setSessionStatus(status: string): Promise<void> {
    try {
      await redis.set(REDIS_KEYS.sessionStatus, status);
    } catch (error) {
      logger.debug({ err: error }, 'Failed to update session status in Redis');
    }
  }

  async getSessionStatus(): Promise<string> {
    try {
      return (await redis.get(REDIS_KEYS.sessionStatus)) ?? SESSION_STATUS.close;
    } catch {
      return this.isConnected ? SESSION_STATUS.open : SESSION_STATUS.close;
    }
  }
}

export const whatsappService = new WhatsAppService();
