// The shapes the owner API returns, as far as the phone reads them. The server stays the
// authority: these types describe what we show, they never grant anything.

export type Identity = { owner_id: string; agent_id: string; signing_key?: string; exchange_key?: string };

export type Peer = {
  peer_id: string;
  fingerprint?: string;
  owner_id: string;
  agent_id: string;
  state: string;
};

export type MissionCap = { cap_micro: number; currency: string };

export type TeamRecord = {
  record: 'part' | 'result' | 'access';
  rules?: { must?: string[]; must_not?: string[] } | null;
  compute?: { cap_micro: number; currency: string } | null;
  checks?: { rule: string; kept: boolean }[];
  compute_used?: { micro: number; currency: string } | null;
  what?: string;
  why?: string;
  hours?: number;
};

/** A room record riding inside a task proposal: a note (finding, idea, plan, change of mind) or a vote. */
export type RoomRecord =
  | { record: 'note'; room: string; thread: string; note: 'finding' | 'idea' | 'plan' | 'change'; stage: 'researching' | 'doing' | 'done'; summary: string; replaces: string | null; why: string | null }
  | { record: 'vote'; room: string; thread: string; question: string; rule: 'most' | 'all'; stance: 'yes' | 'no' | 'abstain'; vote_id: string; why: string | null };

export type Item = {
  id: string;
  kind: 'task' | 'artifact';
  direction: 'incoming' | 'outgoing';
  state: string;
  historical_state?: string;
  title: string;
  context: string;
  peer_id: string;
  parent_id: string | null;
  created_at: number;
  expires: number;
  task_id?: string;
  artifact_digest?: string;
  mission_cap?: MissionCap | null;
  team?: TeamRecord | null;
  room?: RoomRecord | null;
  [key: string]: unknown;
};

export type Relay = {
  enabled: true;
  relay_host: string;
  invites: { id: string; label: string; code: string; created: number; join_by: number; state: 'open' | 'joined'; link?: string }[];
  joiners: { invite_id: string; label: string; code: string; owner_id: string; agent_id: string; fingerprint: string; known: boolean; review_digest: string }[];
  links: { peer_id: string; state: 'joining' | 'waiting' | 'connected' | 'closed'; expires?: number }[];
  [key: string]: unknown;
};

export type State = {
  identity: Identity;
  items: Item[];
  peers: Peer[];
  relay?: Relay;
  /** Present when this Parlu has an approvals desk (conversations are set up). */
  approvals?: { enabled: boolean };
  /** The saved audit history. It has no clock, so its sequence gives the order things happened. */
  history?: { sequence: number; event: string; item_id?: string }[];
  [key: string]: unknown;
};

export type Question = {
  question_id: string;
  question: string;
  options: string[];
  state: 'waiting' | 'answered' | 'expired';
  answer: string | null;
  expires_at: number;
  assistant_id?: string;
  conversation_id?: string;
};

export type WaitingMessage = { draft_id: string; assistant_id: string; conversation_id: string; text: string; digest: string };

export type SharedDraft = { draft_id: string; conversation_id: string; text: string; author_name?: string; [key: string]: unknown };

export type Approvals = {
  messages: WaitingMessage[];
  questions: Question[];
  drafts: SharedDraft[];
  drafts_available: boolean;
  count: number;
};

export type Review = {
  item_id: string;
  content: string | null;
  allowed_actions: ('accept' | 'reject' | 'release' | 'cancel')[];
  review_digest: string;
  context: string;
  artifact_digest: string;
  [key: string]: unknown;
};

export type DraftReview = { draft_id: string; text: string; people: string[]; review_digest: string; scope: string; expires_at: number };

export type InviteMade = { made: true; id: string; label: string; code: string; join_by: number; link: string; state: string } | { made: false; relay: string };

export type InviteReview =
  | { ok: true; inviter: { owner_id: string; agent_id: string; fingerprint: string }; label: string; relay_host: string; code: string; known: boolean; review_digest: string }
  | { ok: false; inviter: { owner_id: string; agent_id: string; fingerprint: string }; label: string; relay_host: string; reason: string };

export type TimelineEntry = { seq: number; at: number; conversation_id: string | null; role: string; kind: string; ref: string | null; detail: Record<string, unknown> };

/** What the screens need from a Parlu, whether it is your own or the built-in demo. */
export interface Backend {
  readonly mode: 'demo' | 'live';
  readonly address: string;
  signIn(password: string): Promise<Identity>;
  signOut(): Promise<void>;
  state(): Promise<State>;
  /** Questions, messages and shared drafts waiting for you. Only asked for when state says the desk is on. */
  approvals(): Promise<Approvals | null>;
  review(itemId: string): Promise<Review>;
  decide(itemId: string, reviewDigest: string, decision: 'accept' | 'reject'): Promise<unknown>;
  release(itemId: string, reviewDigest: string): Promise<unknown>;
  approveMessage(draftId: string, digest: string): Promise<unknown>;
  declineMessage(draftId: string): Promise<unknown>;
  answer(questionId: string, option: number): Promise<unknown>;
  reviewDraft(draftId: string, conversationId: string): Promise<DraftReview>;
  approveDraft(draftId: string, reviewDigest: string): Promise<unknown>;
  createInvite(label: string): Promise<InviteMade>;
  openInvite(link: string): Promise<InviteReview>;
  acceptInvite(link: string, reviewDigest: string): Promise<{ joined: boolean; reason?: string; state?: string }>;
  decideJoiner(inviteId: string, reviewDigest: string, decision: 'add' | 'decline'): Promise<{ decided: boolean; added?: boolean; reason?: string }>;
  timeline(): Promise<TimelineEntry[] | null>;
}
