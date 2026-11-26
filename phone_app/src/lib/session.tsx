// One signed-in Parlu at a time, held only in memory. The session token never touches
// storage: closing the app or 15 minutes of quiet means unlocking again. Only the address of
// your Parlu is remembered, because it is not a secret.
import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { CentralClient, RequestFailure } from './api';
import { DemoBackend } from './demo';
import type { Approvals, Backend, Identity, State } from './types';

const ADDRESS_KEY = 'parlu.address';

export async function rememberedAddress(): Promise<string> {
  try { return (await SecureStore.getItemAsync(ADDRESS_KEY)) ?? ''; } catch { return ''; }
}
async function rememberAddress(address: string) {
  try { await SecureStore.setItemAsync(ADDRESS_KEY, address); } catch { /* Web has no secure store; typing it again is fine. */ }
}

export type Receipt = { title: string; line: string; amount?: string; owner?: string; agent?: string; digest?: string; at: number };

type Session = {
  backend: Backend | null;
  identity: Identity | null;
  state: State | null;
  approvals: Approvals | null;
  approvalsFailed: boolean;
  /** Set after a write whose outcome is unknown: writes stay blocked until a refresh. */
  uncertain: boolean;
  locked: string;
  receipt: Receipt | null;
  startDemo(): Promise<void>;
  connect(address: string, password: string): Promise<void>;
  unlock(password: string): Promise<void>;
  refresh(): Promise<void>;
  act<T>(write: (backend: Backend) => Promise<T>): Promise<T>;
  lock(message?: string): void;
  leave(): Promise<void>;
  setReceipt(receipt: Receipt | null): void;
};

const Context = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [backend, setBackend] = useState<Backend | null>(null);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [state, setState] = useState<State | null>(null);
  const [approvals, setApprovals] = useState<Approvals | null>(null);
  const [approvalsFailed, setApprovalsFailed] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [locked, setLocked] = useState('');
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const generation = useRef(0);

  const load = useCallback(async (target: Backend) => {
    const epoch = generation.current;
    const [nextState, nextApprovals] = await Promise.all([target.state(), target.approvals()]);
    if (epoch !== generation.current) return;
    setState(nextState);
    setApprovals(nextApprovals);
    setApprovalsFailed(false);
  }, []);

  const handle = useCallback((error: unknown) => {
    if (error instanceof RequestFailure && error.unauthorised) {
      setLocked(error.message);
      setState(null);
      setApprovals(null);
    }
    if (error instanceof RequestFailure && error.unknown) setUncertain(true);
    throw error;
  }, []);

  const begin = useCallback(async (target: Backend, password: string) => {
    generation.current += 1;
    const who = await target.signIn(password);
    setBackend(target);
    setIdentity(who);
    setLocked('');
    setUncertain(false);
    await load(target);
  }, [load]);

  const value = useMemo<Session>(() => ({
    backend, identity, state, approvals, approvalsFailed, uncertain, locked, receipt,
    async startDemo() { await begin(new DemoBackend(), 'demo'); },
    async connect(address, password) {
      const client = new CentralClient(address);
      await begin(client, password);
      await rememberAddress(client.address);
    },
    async unlock(password) {
      if (!backend) throw new Error('Choose a Parlu first.');
      await begin(backend, password);
    },
    async refresh() {
      if (!backend) return;
      try {
        await load(backend);
        setUncertain(false);
      } catch (error) { handle(error); }
    },
    async act(write) {
      if (!backend) throw new Error('Choose a Parlu first.');
      if (uncertain) throw new RequestFailure('An earlier step could not be confirmed. Refresh to see what was saved first.');
      try {
        const result = await write(backend);
        await load(backend).catch(() => undefined);
        return result;
      } catch (error) { return handle(error); }
    },
    lock(message = 'Parlu is locked.') {
      generation.current += 1;
      backend?.signOut();
      setLocked(message);
      setState(null);
      setApprovals(null);
    },
    async leave() {
      generation.current += 1;
      await backend?.signOut();
      setBackend(null); setIdentity(null); setState(null); setApprovals(null); setLocked(''); setUncertain(false); setReceipt(null);
    },
    setReceipt,
  }), [backend, identity, state, approvals, approvalsFailed, uncertain, locked, receipt, begin, load, handle]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSession(): Session {
  const session = useContext(Context);
  if (!session) throw new Error('SessionProvider is missing');
  return session;
}

/** Plain words for any failure, never a stack trace. */
export function sayError(error: unknown): string {
  if (error instanceof RequestFailure) return error.message;
  if (error instanceof Error && error.message && error.message.length < 160 && !/[{}<>]/.test(error.message)) return error.message;
  return 'Something went wrong. Nothing was changed.';
}
