import { REDIS_KEYS } from '../config/constants';
import { env } from '../config/env';
import { redis } from '../database/redis';

export class RateLimitService {
  async hit(key: string, windowMs = env.RATE_LIMIT_WINDOW_MS, max = env.RATE_LIMIT_MAX) {
    const now = Date.now();
    const windowStart = now - windowMs;

    const multi = redis.multi();
    multi.zremrangebyscore(key, 0, windowStart);
    multi.zadd(key, now, `${now}:${Math.random()}`);
    multi.zcard(key);
    multi.pexpire(key, windowMs);
    const results = await multi.exec();

    const count = Number(results?.[2]?.[1] ?? 0);
    return {
      allowed: count <= max,
      remaining: Math.max(0, max - count),
      count,
      limit: max,
      resetMs: windowMs,
    };
  }

  async hitIp(ip: string) {
    return this.hit(REDIS_KEYS.rateLimitIp(ip));
  }

  async hitPhone(phone: string) {
    return this.hit(REDIS_KEYS.rateLimitPhone(phone));
  }
}

export const rateLimitService = new RateLimitService();
