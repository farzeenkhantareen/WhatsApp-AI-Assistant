import { EventEmitter } from 'events';
import type { WAMessage } from '@whiskeysockets/baileys';

export interface IncomingMessagePayload {
  waMessageId: string;
  from: string;
  phone: string;
  pushName?: string;
  text: string;
  mediaType: 'text' | 'image' | 'audio' | 'document' | 'pdf';
  mediaPath?: string;
  mediaMime?: string;
  mediaBuffer?: Buffer;
  quotedWaMessageId?: string;
  raw: WAMessage;
}

export interface MessageStatusPayload {
  waMessageId: string;
  status: 'delivered' | 'read';
  phone?: string;
}

export interface AppEvents {
  'connection.open': [];
  'connection.close': [{ statusCode?: number; loggedOut: boolean }];
  'qr.generated': [{ qr: string }];
  'message.received': [IncomingMessagePayload];
  'message.sent': [{ waMessageId: string; phone: string; content: string }];
  'message.delivered': [MessageStatusPayload];
  'message.read': [MessageStatusPayload];
  error: [{ error: unknown; context?: string }];
}

class TypedEventBus {
  private readonly emitter = new EventEmitter();

  constructor() {
    this.emitter.setMaxListeners(50);
  }

  on<K extends keyof AppEvents>(
    event: K,
    listener: (...args: AppEvents[K]) => void,
  ): this {
    this.emitter.on(event, listener as (...args: unknown[]) => void);
    return this;
  }

  once<K extends keyof AppEvents>(
    event: K,
    listener: (...args: AppEvents[K]) => void,
  ): this {
    this.emitter.once(event, listener as (...args: unknown[]) => void);
    return this;
  }

  off<K extends keyof AppEvents>(
    event: K,
    listener: (...args: AppEvents[K]) => void,
  ): this {
    this.emitter.off(event, listener as (...args: unknown[]) => void);
    return this;
  }

  emit<K extends keyof AppEvents>(event: K, ...args: AppEvents[K]): boolean {
    return this.emitter.emit(event, ...args);
  }
}

export const eventBus = new TypedEventBus();
