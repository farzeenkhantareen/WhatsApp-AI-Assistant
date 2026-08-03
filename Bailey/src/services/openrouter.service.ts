import { env } from '../config/env';
import { logger } from '../config/logger';
import { buildSystemPrompt } from '../prompts/system';
import type { ContextMessage } from '../memory/memory.service';
import { withRetry } from '../utils/retry';
import { bufferToDataUrl } from '../utils/media';

type OpenRouterContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } };

interface OpenRouterMessage {
  role: 'system' | 'user' | 'assistant';
  content: string | OpenRouterContentPart[];
}

export interface GenerateReplyInput {
  history: ContextMessage[];
  userName?: string | null;
  latestUserText: string;
  mediaType?: ContextMessage['mediaType'];
  mediaMime?: string | null;
  mediaBuffer?: Buffer;
}

export class OpenRouterService {
  async generateReply(input: GenerateReplyInput): Promise<string> {
    const messages = this.buildMessages(input);

    return withRetry(
      () => this.streamCompletion(messages),
      {
        retries: env.AI_MAX_RETRIES,
        label: 'openrouter.completion',
        shouldRetry: (error) => {
          const message = error instanceof Error ? error.message : String(error);
          return /429|500|502|503|504|timeout|network|ECONNRESET/i.test(message);
        },
      },
    );
  }

  private buildMessages(input: GenerateReplyInput): OpenRouterMessage[] {
    const messages: OpenRouterMessage[] = [
      { role: 'system', content: buildSystemPrompt(input.userName) },
    ];

    for (const item of input.history) {
      if (item.role === 'system') continue;
      messages.push({
        role: item.role,
        content: item.content,
      });
    }

    const userContent = this.buildUserContent(input);
    messages.push({ role: 'user', content: userContent });
    return messages;
  }

  private buildUserContent(
    input: GenerateReplyInput,
  ): string | OpenRouterContentPart[] {
    const caption = input.latestUserText || this.defaultMediaCaption(input.mediaType);

    if (
      input.mediaType === 'image' &&
      input.mediaBuffer &&
      input.mediaMime?.startsWith('image/')
    ) {
      return [
        { type: 'text', text: caption },
        {
          type: 'image_url',
          image_url: {
            url: bufferToDataUrl(input.mediaBuffer, input.mediaMime),
          },
        },
      ];
    }

    if (input.mediaType && input.mediaType !== 'text') {
      return `${caption}\n\n[Attached ${input.mediaType}${
        input.mediaMime ? ` (${input.mediaMime})` : ''
      }. Describe or help based on the caption and context.]`;
    }

    return caption;
  }

  private defaultMediaCaption(mediaType?: ContextMessage['mediaType']): string {
    switch (mediaType) {
      case 'image':
        return 'The user sent an image.';
      case 'audio':
        return 'The user sent an audio message.';
      case 'pdf':
        return 'The user sent a PDF document.';
      case 'document':
        return 'The user sent a document.';
      default:
        return '';
    }
  }

  private async streamCompletion(messages: OpenRouterMessage[]): Promise<string> {
    const response = await fetch(`${env.OPENROUTER_BASE_URL}/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': env.OPENROUTER_HTTP_REFERER,
        'X-Title': env.OPENROUTER_APP_TITLE,
      },
      body: JSON.stringify({
        model: env.OPENROUTER_MODEL,
        messages,
        stream: true,
      }),
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(`OpenRouter HTTP ${response.status}: ${body.slice(0, 500)}`);
    }

    if (!response.body) {
      throw new Error('OpenRouter response body is empty');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let content = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line || line.startsWith(':')) continue;
        if (!line.startsWith('data:')) continue;

        const data = line.slice(5).trim();
        if (data === '[DONE]') {
          continue;
        }

        try {
          const parsed = JSON.parse(data) as {
            choices?: Array<{ delta?: { content?: string | null } }>;
            error?: { message?: string };
          };
          if (parsed.error?.message) {
            throw new Error(parsed.error.message);
          }
          const delta = parsed.choices?.[0]?.delta?.content;
          if (delta) {
            content += delta;
          }
        } catch (error) {
          if (error instanceof SyntaxError) {
            logger.debug({ line }, 'Skipping non-JSON SSE chunk');
            continue;
          }
          throw error;
        }
      }
    }

    const trimmed = content.trim();
    if (!trimmed) {
      throw new Error('OpenRouter returned empty content');
    }
    return trimmed;
  }
}

export const openRouterService = new OpenRouterService();
