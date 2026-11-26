// Talks to your own Parlu over its owner API, the same one the desktop app uses. Nothing here
// decides anything on its own: every yes sends the exact review digest you were shown, and
// the server refuses it if the text changed in between.
import type {
  Approvals, Backend, DraftReview, Identity, InviteMade, InviteReview, Review, State, TimelineEntry,
} from './types';
import { validateRelay, validateReview, validateState } from '../shared/web';

const TIMEOUT_MS = 15000;
const MAX_BYTES = 2 * 1024 * 1024;
const LOOPBACK = new Set(['127.0.0.1', 'localhost']);

export class RequestFailure extends Error {
  /** The session ended: sign in again. */
  readonly unauthorised: boolean;
  /** A write may or may not have happened: look before doing anything else. */
  readonly unknown: boolean;
  constructor(message: string, { unauthorised = false, unknown = false } = {}) {
    super(message);
    this.name = 'RequestFailure';
    this.unauthorised = unauthorised;
    this.unknown = unknown;
  }
}

/**
 * The address of your Parlu, cleaned up. It must be https (for example your computer's
 * Tailscale name), or loopback while developing on a simulator. Returns '' when it is not
 * an address we will send a password to.
 */
export function cleanAddress(value: string): string {
  let text = String(value ?? '').trim();
  if (!text || text.length > 256) return '';
  if (!/^[a-z]+:\/\//i.test(text)) text = 'https://' + text;
  let url: URL;
  try { url = new URL(text); } catch { return ''; }
  if (url.username || url.password || url.search || url.hash) return '';
  if (url.pathname !== '/' && url.pathname !== '') return '';
  if (url.protocol === 'http:' && !LOOPBACK.has(url.hostname)) return '';
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return '';
  return url.origin;
}

const isMutation = (method: string, path: string) =>
  method !== 'GET' && !(method === 'POST' && (path === '/api/approvals/timeline' || path === '/api/invites/open'));

type Fetch = typeof fetch;

export class CentralClient implements Backend {
  readonly mode = 'live' as const;
  readonly address: string;
  private token: string | null = null;
  private readonly fetcher: Fetch;

  constructor(address: string, fetcher: Fetch = fetch) {
    const clean = cleanAddress(address);
    if (!clean) throw new Error('That address is not one Parlu can use.');
    this.address = clean;
    this.fetcher = fetcher;
  }

  get signedIn() { return this.token !== null; }

  private async request<T>(path: string, { method = 'GET', body, auth = true }: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
    const mutation = isMutation(method, path);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (auth) {
        if (!this.token) throw new RequestFailure('Unlock Parlu to carry on.', { unauthorised: true });
        headers.Authorization = `Bearer ${this.token}`;
      }
      const response = await this.fetcher(this.address + path, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal, credentials: 'omit', cache: 'no-store', redirect: 'error',
      });
      if (response.status === 401) {
        this.token = null;
        throw new RequestFailure(auth ? 'Your session has ended. Unlock Parlu again.' : 'That password did not unlock Parlu.', { unauthorised: true });
      }
      if (!response.ok) {
        throw new RequestFailure(
          response.status >= 500 && mutation
            ? 'Parlu could not confirm that. Refresh to see what was saved before you try again.'
            : 'Parlu said no to that. Refresh and look at the latest version.',
          { unknown: mutation && response.status >= 500 });
      }
      const raw = await response.text();
      if (raw.length > MAX_BYTES) throw new Error('Response too large');
      return (raw ? JSON.parse(raw) : {}) as T;
    } catch (error) {
      if (error instanceof RequestFailure) throw error;
      throw new RequestFailure(
        mutation ? 'Parlu could not confirm that. Refresh to see what was saved before you try again.'
          : 'Parlu could not be reached. Nothing was changed.',
        { unknown: mutation });
    } finally {
      clearTimeout(timer);
    }
  }

  async signIn(password: string): Promise<Identity> {
    if (typeof password !== 'string' || !password) throw new RequestFailure('Type your Parlu password.');
    const result = await this.request<{ token: string; identity: Identity }>('/api/session', { method: 'POST', body: { password }, auth: false });
    if (typeof result.token !== 'string' || !result.token || result.token.length > 120) throw new RequestFailure('Parlu answered in a way the app could not check.');
    this.token = result.token;
    return result.identity;
  }

  async signOut() {
    const token = this.token;
    this.token = null;
    if (!token) return;
    try {
      await this.fetcher(this.address + '/api/session', {
        method: 'DELETE', headers: { Accept: 'application/json', 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: '{}', credentials: 'omit', cache: 'no-store',
      });
    } catch { /* The session ends by itself within 15 minutes. */ }
  }

  async state(): Promise<State> {
    const value = validateState(await this.request('/api/state')) as unknown as State;
    validateRelay(value.relay);
    return value;
  }

  async approvals(): Promise<Approvals | null> {
    const value = await this.request<Approvals>('/api/approvals');
    if (!Array.isArray(value.messages) || !Array.isArray(value.questions) || !Array.isArray(value.drafts)) throw new RequestFailure('Parlu answered in a way the app could not check.');
    return value;
  }

  async review(itemId: string): Promise<Review> {
    const state = await this.state();
    const item = state.items.find(entry => entry.id === itemId);
    if (!item) throw new RequestFailure('That proposal is no longer here. Refresh.');
    return validateReview(await this.request(`/api/items/${encodeURIComponent(itemId)}/review`), item) as unknown as Review;
  }

  decide(itemId: string, reviewDigest: string, decision: 'accept' | 'reject') {
    return this.request(`/api/items/${encodeURIComponent(itemId)}/decision`, { method: 'POST', body: { review_digest: reviewDigest, decision } });
  }

  release(itemId: string, reviewDigest: string) {
    return this.request(`/api/items/${encodeURIComponent(itemId)}/release`, { method: 'POST', body: { review_digest: reviewDigest } });
  }

  approveMessage(draftId: string, digest: string) {
    return this.request(`/api/approvals/messages/${encodeURIComponent(draftId)}/approve`, { method: 'POST', body: { digest } });
  }

  declineMessage(draftId: string) {
    return this.request(`/api/approvals/messages/${encodeURIComponent(draftId)}/decline`, { method: 'POST', body: {} });
  }

  answer(questionId: string, option: number) {
    return this.request(`/api/approvals/questions/${encodeURIComponent(questionId)}/answer`, { method: 'POST', body: { option } });
  }

  reviewDraft(draftId: string, conversationId: string): Promise<DraftReview> {
    return this.request(`/api/approvals/drafts/${encodeURIComponent(draftId)}/review`, { method: 'POST', body: { conversation_id: conversationId } });
  }

  approveDraft(draftId: string, reviewDigest: string) {
    return this.request(`/api/approvals/drafts/${encodeURIComponent(draftId)}/approve`, { method: 'POST', body: { review_digest: reviewDigest } });
  }

  createInvite(label: string): Promise<InviteMade> {
    return this.request('/api/invites', { method: 'POST', body: label.trim() ? { label: label.trim() } : {} });
  }

  openInvite(link: string): Promise<InviteReview> {
    return this.request('/api/invites/open', { method: 'POST', body: { link } });
  }

  acceptInvite(link: string, reviewDigest: string) {
    return this.request<{ joined: boolean; reason?: string; state?: string }>('/api/invites/accept', { method: 'POST', body: { link, review_digest: reviewDigest } });
  }

  decideJoiner(inviteId: string, reviewDigest: string, decision: 'add' | 'decline') {
    return this.request<{ decided: boolean; added?: boolean; reason?: string }>(`/api/invites/${encodeURIComponent(inviteId)}/joiner`, { method: 'POST', body: { decision, review_digest: reviewDigest } });
  }

  async timeline(): Promise<TimelineEntry[] | null> {
    try {
      const value = await this.request<{ entries: TimelineEntry[] }>('/api/approvals/timeline', { method: 'POST', body: {} });
      return Array.isArray(value.entries) ? value.entries : null;
    } catch (error) {
      if (error instanceof RequestFailure && error.unauthorised) throw error;
      return null;
    }
  }
}
