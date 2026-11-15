/** Preserve an existing setting's JSON type while editing it. */
export function displaySettingValue(value: unknown): string {
  return value !== null && typeof value === 'object' ? JSON.stringify(value) : String(value);
}

export function parseSettingValue(raw: string, previous?: unknown): unknown {
  if (typeof previous === 'string') return raw;
  if (typeof previous === 'number') {
    if (!raw.trim() || !Number.isFinite(Number(raw))) throw new Error('Enter a finite number.');
    return Number(raw);
  }
  if (typeof previous === 'boolean') {
    if (raw !== 'true' && raw !== 'false') throw new Error('Enter true or false.');
    return raw === 'true';
  }
  if (previous !== undefined && previous !== null && typeof previous === 'object') {
    const parsed = JSON.parse(raw);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed) !== Array.isArray(previous)) {
      throw new Error(Array.isArray(previous) ? 'Enter a JSON list.' : 'Enter a JSON object.');
    }
    return parsed;
  }
  const text = raw.trim();
  if (text.startsWith('{') || text.startsWith('[')) return JSON.parse(text);
  if (text === 'true' || text === 'false') return text === 'true';
  if (text && Number.isFinite(Number(text))) return Number(text);
  return raw;
}
