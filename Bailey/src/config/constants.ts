export const REDIS_KEYS = {
  conversation: (phone: string) => `conv:${phone}:messages`,
  sessionStatus: 'wa:session:status',
  rateLimitIp: (ip: string) => `ratelimit:ip:${ip}`,
  rateLimitPhone: (phone: string) => `ratelimit:phone:${phone}`,
  replyLock: (phone: string) => `lock:reply:${phone}`,
} as const;

export const SESSION_STATUS = {
  connecting: 'connecting',
  open: 'open',
  close: 'close',
  qr: 'qr',
} as const;
