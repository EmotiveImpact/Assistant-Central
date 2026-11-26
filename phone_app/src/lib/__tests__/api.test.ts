import { CentralClient, RequestFailure, cleanAddress } from '../api';

type Call = { url: string; init: RequestInit };

function fakeFetch(responses: Array<{ status: number; body?: unknown } | Error>) {
  const calls: Call[] = [];
  const fetcher = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    const next = responses.shift();
    if (!next) throw new Error('No response queued');
    if (next instanceof Error) throw next;
    return { status: next.status, ok: next.status >= 200 && next.status < 300, text: async () => (next.body === undefined ? '' : JSON.stringify(next.body)) };
  }) as unknown as typeof fetch;
  return { fetcher, calls };
}

const identity = { owner_id: 'maya', agent_id: 'Juniper' };
const hex = (c: string) => c.repeat(64);

describe('cleanAddress', () => {
  it('accepts private https names and loopback only', () => {
    expect(cleanAddress('my-mac.tail1234.ts.net')).toBe('https://my-mac.tail1234.ts.net');
    expect(cleanAddress(' https://My-Mac.tail1234.ts.net/ ')).toBe('https://my-mac.tail1234.ts.net');
    expect(cleanAddress('http://127.0.0.1:8877')).toBe('http://127.0.0.1:8877');
    expect(cleanAddress('http://192.168.1.20:8877')).toBe('');
    expect(cleanAddress('http://my-mac.tail1234.ts.net')).toBe('');
    expect(cleanAddress('https://user:pw@host.example')).toBe('');
    expect(cleanAddress('https://host.example/path')).toBe('');
    expect(cleanAddress('https://host.example/?q=1')).toBe('');
    expect(cleanAddress('ftp://host.example')).toBe('');
    expect(cleanAddress('')).toBe('');
  });
});

describe('CentralClient', () => {
  it('signs in once and sends the session as a bearer token, with no cookies', async () => {
    const { fetcher, calls } = fakeFetch([{ status: 200, body: { token: 'tok-1', identity } }, { status: 200, body: { messages: [], questions: [], drafts: [], drafts_available: true, count: 0 } }]);
    const client = new CentralClient('my-mac.tail1234.ts.net', fetcher);
    await expect(client.signIn('a long password')).resolves.toEqual(identity);
    expect(calls[0].url).toBe('https://my-mac.tail1234.ts.net/api/session');
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ password: 'a long password' });
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBeUndefined();
    await client.approvals();
    const headers = calls[1].init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer tok-1');
    expect(headers.Origin).toBeUndefined();
    expect(calls[1].init.credentials).toBe('omit');
  });

  it('sends exactly the reviewed digest with a decision', async () => {
    const { fetcher, calls } = fakeFetch([{ status: 200, body: { token: 't', identity } }, { status: 200, body: { state: 'accepted', decision_digest: hex('d') } }]);
    const client = new CentralClient('https://host.example', fetcher);
    await client.signIn('pw');
    await client.decide(hex('a'), hex('b'), 'accept');
    expect(calls[1].url).toBe(`https://host.example/api/items/${hex('a')}/decision`);
    expect(calls[1].init.method).toBe('POST');
    expect(JSON.parse(String(calls[1].init.body))).toEqual({ review_digest: hex('b'), decision: 'accept' });
  });

  it('turns a 401 into a locked session and forgets the token', async () => {
    const { fetcher } = fakeFetch([{ status: 200, body: { token: 't', identity } }, { status: 401 }]);
    const client = new CentralClient('https://host.example', fetcher);
    await client.signIn('pw');
    const error = await client.answer('q1', 0).catch(e => e as RequestFailure) as RequestFailure;
    expect(error).toBeInstanceOf(RequestFailure);
    expect(error.unauthorised).toBe(true);
    expect(client.signedIn).toBe(false);
  });

  it('marks a write whose outcome is unknown, but not a read', async () => {
    const { fetcher } = fakeFetch([{ status: 200, body: { token: 't', identity } }, { status: 503 }, new Error('offline'), { status: 503 }]);
    const client = new CentralClient('https://host.example', fetcher);
    await client.signIn('pw');
    expect((await client.approveMessage('m1', hex('c')).catch(e => e) as RequestFailure).unknown).toBe(true);
    expect((await client.release(hex('a'), hex('b')).catch(e => e) as RequestFailure).unknown).toBe(true);
    expect((await client.openInvite('https://relay.example/invite#x').catch(e => e) as RequestFailure).unknown).toBe(false);
  });

  it('refuses an address it will not send a password to', () => {
    expect(() => new CentralClient('http://192.168.1.20:8877')).toThrow();
  });
});
