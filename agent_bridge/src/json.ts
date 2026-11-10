/** Bounded, duplicate-key rejecting JSON admission before the MCP SDK parser.
 * JSON.parse alone silently accepts duplicate authority fields. */
export function strictJson(text: string): unknown {
  let i = 0, nodes = 0;
  const fail = (): never => { throw new Error('invalid_json'); };
  const white = () => { while (/[ \t\r\n]/.test(text[i] ?? '') && i < text.length) i++; };
  const string = (): string => {
    const start = i++;
    while (i < text.length) {
      const c = text[i++];
      if (c === '\\') { i++; continue; }
      if (c === '"') {
        const value: unknown = JSON.parse(text.slice(start, i));
        if (typeof value !== 'string' || !value.isWellFormed()) fail();
        return value as string;
      }
    }
    return fail();
  };
  const value = (depth: number): unknown => {
    if (++nodes > 1024 || depth > 16) fail();
    white(); const c = text[i];
    if (c === '"') return string();
    if (c === '{' || c === '[') {
      i++; white(); const object = c === '{'; const end = object ? '}' : ']';
      const keys = new Set<string>();
      const result: Record<string, unknown> | unknown[] = object ? Object.create(null) : [];
      if (text[i] === end) { i++; return result; }
      for (;;) {
        white();
        if (object) {
          if (text[i] !== '"') fail();
          const key = string(); if (keys.has(key)) fail(); keys.add(key);
          white(); if (text[i++] !== ':') fail();
          (result as Record<string, unknown>)[key] = value(depth + 1);
        } else (result as unknown[]).push(value(depth + 1));
        white(); const next = text[i++];
        if (next === end) return result;
        if (next !== ',') fail();
      }
    }
    const primitive = text.slice(i).match(/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/)?.[0];
    if (!primitive) return fail();
    i += primitive.length; const parsed: unknown = JSON.parse(primitive);
    if (typeof parsed === 'number' && !Number.isFinite(parsed)) fail();
    return parsed;
  };
  const result = value(0); white(); if (i !== text.length) fail();
  return result;
}
