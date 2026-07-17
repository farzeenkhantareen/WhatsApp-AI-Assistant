export function normalizePhone(input: string): string {
  return input.replace(/\D/g, '');
}

export function phoneToJid(phone: string): string {
  const digits = normalizePhone(phone);
  if (!digits) {
    throw new Error('Invalid phone number');
  }
  if (digits.includes('@')) {
    return phone;
  }
  return `${digits}@s.whatsapp.net`;
}

export function jidToPhone(jid: string): string {
  return jid.split('@')[0]?.split(':')[0] ?? jid;
}

export function isGroupJid(jid: string): boolean {
  return jid.endsWith('@g.us');
}

export function isBroadcastJid(jid: string): boolean {
  return jid.endsWith('@broadcast') || jid === 'status@broadcast';
}
