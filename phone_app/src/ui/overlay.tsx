// The floating layer above every screen, as in the mock: one thing at a time floats over the
// page (the Decide sheet, the + menu, your menu or search) on a dimmed ground, and a short
// note can rise above the glass bar. Pages never change underneath while a layer is open.
import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';

export type Layer =
  | { kind: 'decide'; key: string }
  | { kind: 'plus' }
  | { kind: 'avatar' }
  | { kind: 'search' };

export type Note = { id: number; text: string };

type Overlay = {
  layer: Layer | null;
  /** The layer is animating away; it is removed when it calls gone(). */
  closing: boolean;
  note: Note | null;
  open(layer: Layer): void;
  /** Opens a layer, or closes it if that same kind is already open (the + and avatar buttons). */
  toggle(kind: 'plus' | 'avatar' | 'search'): void;
  decide(key: string): void;
  close(note?: string): void;
  gone(): void;
  toast(text: string): void;
  clearNote(id: number): void;
};

const Context = createContext<Overlay | null>(null);

export function OverlayProvider({ children }: { children: React.ReactNode }) {
  const [layer, setLayer] = useState<Layer | null>(null);
  const [closing, setClosing] = useState(false);
  const [note, setNote] = useState<Note | null>(null);
  const counter = useRef(0);

  const toast = useCallback((text: string) => { counter.current += 1; setNote({ id: counter.current, text }); }, []);
  const open = useCallback((next: Layer) => { setLayer(next); setClosing(false); }, []);
  const close = useCallback((text?: string) => { setClosing(true); if (text) toast(text); }, [toast]);
  const gone = useCallback(() => { setLayer(null); setClosing(false); }, []);

  const value = useMemo<Overlay>(() => ({
    layer, closing, note, open, close, gone, toast,
    toggle(kind) { if (layer?.kind === kind && !closing) close(); else open({ kind } as Layer); },
    decide(key) { open({ kind: 'decide', key }); },
    clearNote(id) { setNote(current => (current?.id === id ? null : current)); },
  }), [layer, closing, note, open, close, gone, toast]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useOverlay(): Overlay {
  const value = useContext(Context);
  if (!value) throw new Error('OverlayProvider is missing');
  return value;
}
