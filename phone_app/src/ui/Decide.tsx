// Decide, inside the floating sheet. One layout for every kind of decision: who is asking and
// a close button, the question, what will happen (Spends, Shares, Keeps), then the hold or the
// buttons and a row of quiet links. The exact text is one tap away. Every yes sends the exact
// review you were shown; the server refuses it if anything changed.
import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import Animated, { FadeIn, FadeOut, LinearTransition, ZoomIn } from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';
import { cardFor, queueOf, type Entry } from '../lib/home';
import { sayError, useSession, type Receipt } from '../lib/session';
import { ANSWER_LIMIT, decisionQuestion, decisionRows, exactMoney, needsHold, stateLabel } from '../shared/web';
import type { DraftReview, Item, Review } from '../lib/types';
import { HoldButton } from './HoldButton';
import { Bot, Button, Chip, Notice, Pair, Person, T, type Expression } from './parts';
import { EASE, riseIn } from './motion';
import { colour, font } from './theme';

type Close = (note?: string) => void;
const short = (amount: string) => amount.replace(/\.00$/, '');
const cap = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

function CloseButton({ onPress }: { onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel="Close" hitSlop={10}
      style={({ pressed }) => ({ width: 30, height: 30, borderRadius: 15, backgroundColor: colour.raised, alignItems: 'center', justifyContent: 'center', opacity: pressed ? 0.7 : 1 })}>
      <Svg width={12} height={12} viewBox="0 0 24 24"><Path d="M6 6l12 12M18 6L6 18" stroke={colour.secondary} strokeWidth={2.6} strokeLinecap="round" /></Svg>
    </Pressable>
  );
}

/** Who is asking, beside a close button: the first line of every decision. */
function Head({ owner, agent, who, e = 'idle', close }: { owner?: string; agent?: string; who: string; e?: Expression; close: () => void }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      {owner && agent ? <Pair owner={owner} agent={agent} size={22} e={e} /> : null}
      <Text style={{ flex: 1, fontFamily: font.medium, fontSize: 13, color: colour.muted }} numberOfLines={1}>{who}</Text>
      <CloseButton onPress={close} />
    </View>
  );
}

function Title({ children }: { children: React.ReactNode }) {
  return <Text accessibilityRole="header" style={{ fontFamily: font.bold, fontSize: 24, lineHeight: 29, letterSpacing: -0.6, color: colour.text }}>{children}</Text>;
}

/** Spends, Shares, Keeps: a bordered box, label on the left. */
function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <View style={{ borderWidth: 1, borderColor: colour.line, borderRadius: 16 }}>
      {rows.map(([label, text], i) => (
        <View key={label} style={{ flexDirection: 'row', gap: 12, paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: i ? 1 : 0, borderTopColor: colour.line }}>
          <Text style={{ width: 66, fontFamily: font.bold, fontSize: 10.5, letterSpacing: 0.8, color: colour.muted, paddingTop: 2 }}>{label.toUpperCase()}</Text>
          <Text style={{ flex: 1, fontFamily: font.regular, fontSize: 13.5, lineHeight: 19, color: colour.secondary }}>{text}</Text>
        </View>
      ))}
    </View>
  );
}

function Exact({ text, label = 'The exact text' }: { text: string | null; label?: string }) {
  if (!text) return null;
  return (
    <Animated.View entering={FadeIn.duration(220)} exiting={FadeOut.duration(150)} style={{ backgroundColor: colour.raised, borderRadius: 16, padding: 14, gap: 6 }}>
      <T v="label">{label}</T>
      <T v="body" selectable style={{ color: colour.text, fontSize: 14, lineHeight: 21 }}>{text}</T>
    </Animated.View>
  );
}

function Link({ label, onPress, tone }: { label: string; onPress: () => void; tone?: 'danger' | 'quiet' }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" hitSlop={8}>
      <Text style={{ fontFamily: font.semibold, fontSize: 14, color: tone === 'danger' ? colour.danger : tone === 'quiet' ? colour.muted : colour.accentFg }}>{label}</Text>
    </Pressable>
  );
}

function Links({ children }: { children: React.ReactNode }) {
  return <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 22, paddingTop: 2 }}>{children}</View>;
}

function Body({ children }: { children: React.ReactNode }) {
  return <Animated.View layout={LinearTransition.duration(240).easing(EASE)} style={{ gap: 12 }}>{children}</Animated.View>;
}

function ProposalDecision({ entry, item, close, agreed }: { entry: Entry; item: Item; close: Close; agreed: (r: Receipt) => void }) {
  const { backend, state, act } = useSession();
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [deep, setDeep] = useState(false);
  useEffect(() => { backend!.review(item.id).then(setReview, e => setError(sayError(e))); }, [backend, item.id]);
  const c = cardFor(state!, entry);
  const actions = review?.allowed_actions ?? [];
  const question = decisionQuestion(item, { agent: c.agent, owner: c.owner }) as string;
  const rows = decisionRows(item, { agent: c.agent, owner: c.owner, actions }) as [string, string][];
  const hold = needsHold(item, 'accept') as boolean;
  const limit = item.mission_cap ?? (item.team?.record === 'part' ? item.team.compute : null);
  const amount = limit ? short(exactMoney(limit.cap_micro, limit.currency) as string) : '';
  const money = !!(amount && item.mission_cap);

  const decide = async (decision: 'accept' | 'reject') => {
    if (!review || busy) return;
    setBusy(true); setError('');
    try {
      const result = await act(b => b.decide(item.id, review.review_digest, decision)) as { decision_digest?: unknown } | null;
      if (decision === 'reject') { close(`Said no. ${c.agent} will let ${c.owner} know.`); return; }
      const signed = typeof result?.decision_digest === 'string' ? result.decision_digest : undefined;
      agreed({ title: item.title, owner: c.owner, agent: c.agent, amount, digest: signed, at: Date.now(),
        line: item.team?.record === 'result' ? `You merged ${c.agent}’s result.` : money ? `${c.agent} can now pay ${amount} for this, nothing else.` : `${c.agent} has your signed yes.` });
    } catch (e) { setError(sayError(e)); setBusy(false); }
  };
  const release = async () => {
    if (!review || busy) return;
    setBusy(true); setError('');
    try { await act(b => b.release(item.id, review.review_digest)); close(`Sent to ${c.owner}. You will hear back here.`); } catch (e) { setError(sayError(e)); setBusy(false); }
  };

  const settled = !!review && !actions.some(a => a === 'accept' || a === 'release' || a === 'reject');
  const title = settled ? item.title : question;
  return (
    <Body>
      <Head owner={c.owner} agent={c.agent} who={c.team ? `${c.who} · ${c.team}` : c.who} e={settled ? 'idle' : 'look'} close={() => close()} />
      <Title>{title}</Title>
      {settled ? <Chip label={stateLabel(item.state)} tone={item.state === 'accepted' ? 'done' : 'plain'} /> : null}
      <Rows rows={rows} />
      {deep ? <Exact text={review ? review.content : null} /> : null}
      <Notice text={error} tone="danger" />
      {!review && !error ? <ActivityIndicator color={colour.accent} style={{ paddingVertical: 8 }} /> : null}
      {review && actions.includes('accept') ? (
        hold
          ? <HoldButton label={money ? `Pay ${amount}` : item.team?.record === 'access' ? 'Give access' : 'Agree'} disabled={busy}
              title={money ? `Hold to pay ${amount} with ${c.owner}` : item.team?.record === 'access' ? 'Hold to give access' : 'Hold to agree'}
              hint={money ? `${c.agent} can pay this one amount, nothing else. Let go early and nothing happens.` : 'Let go early and nothing happens.'}
              onDone={() => decide('accept')} />
          : <Button label={item.team?.record === 'result' ? 'Merge this result' : item.kind === 'artifact' ? 'Accept' : 'Agree'} busy={busy} onPress={() => decide('accept')} />
      ) : null}
      {review && actions.includes('release') ? <Button label={`Send to ${c.owner}`} busy={busy} onPress={release} /> : null}
      {settled ? <Notice text="Nothing to decide here. This is the saved record." /> : null}
      <Links>
        {review && actions.includes('reject') ? <Link label="Say no" tone="danger" onPress={() => decide('reject')} /> : null}
        {review?.content ? <Link label={deep ? 'Hide the exact text' : 'See the exact text ›'} onPress={() => setDeep(!deep)} /> : null}
        {!settled ? <Link label="Not now" tone="quiet" onPress={() => close('Saved for later. It stays in the queue.')} /> : null}
      </Links>
    </Body>
  );
}

function QuestionDecision({ entry, close }: { entry: Entry; close: Close }) {
  const { approvals, state, act } = useSession();
  const id = entry.key.slice('question:'.length);
  const q = approvals?.questions.find(x => x.question_id === id);
  const c = cardFor(state!, entry);
  const [busy, setBusy] = useState(-1);
  const [error, setError] = useState('');
  if (!q) return <Gone close={close} />;
  const answer = async (option: number) => {
    setBusy(option); setError('');
    try { await act(b => b.answer(q.question_id, option)); close(`Answered. ${c.agent} carries on.`); } catch (e) { setError(sayError(e)); setBusy(-1); }
  };
  return (
    <Body>
      <Head owner={c.owner} agent={c.agent} who={`${c.agent} asks`} e="look" close={() => close()} />
      <Title>{q.question}</Title>
      <View style={{ gap: 10 }}>
        {q.options.map((option, i) => <Button key={option} label={option} kind={i ? 'secondary' : 'primary'} busy={busy === i} disabled={busy >= 0} onPress={() => answer(i)} />)}
      </View>
      <Notice text={error} tone="danger" />
      <T v="small">{ANSWER_LIMIT}</T>
      <Links><Link label="Not now" tone="quiet" onPress={() => close('Saved for later. It stays in the queue.')} /></Links>
    </Body>
  );
}

function MessageDecision({ entry, close }: { entry: Entry; close: Close }) {
  const { approvals, state, act } = useSession();
  const id = entry.key.slice('message:'.length);
  const m = approvals?.messages.find(x => x.draft_id === id);
  const c = cardFor(state!, entry);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!m) return <Gone close={close} />;
  const run = async (send: boolean) => {
    setBusy(true); setError('');
    try { await act(b => (send ? b.approveMessage(m.draft_id, m.digest) : b.declineMessage(m.draft_id))); close(send ? 'Sent, exactly as written.' : `Not sent. ${c.agent} will ask before the next one.`); } catch (e) { setError(sayError(e)); setBusy(false); }
  };
  return (
    <Body>
      <Head owner={c.owner} agent={c.agent} who={c.who} close={() => close()} />
      <Title>Send this message for you?</Title>
      <Exact text={m.text} label="The message" />
      <Rows rows={[['Sends', 'Exactly this text, as your own message, once.'], ['Keeps', 'Everything else. Your assistant asks again before the next one.']]} />
      <Notice text={error} tone="danger" />
      <Button label="Send it" busy={busy} onPress={() => run(true)} />
      <Links>
        <Link label="Don’t send" tone="danger" onPress={() => run(false)} />
        <Link label="Not now" tone="quiet" onPress={() => close('Saved for later. It stays in the queue.')} />
      </Links>
    </Body>
  );
}

function DraftDecision({ entry, close }: { entry: Entry; close: Close }) {
  const { approvals, backend, act } = useSession();
  const id = entry.key.slice('draft:'.length);
  const d = approvals?.drafts.find(x => x.draft_id === id);
  const [review, setReview] = useState<DraftReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (d) backend!.reviewDraft(d.draft_id, d.conversation_id).then(setReview, e => setError(sayError(e))); }, [backend, d]);
  if (!d) return <Gone close={close} />;
  const agree = async () => {
    if (!review) return;
    setBusy(true); setError('');
    try { await act(b => b.approveDraft(d.draft_id, review.review_digest)); close('Agreed to that exact text.'); } catch (e) { setError(sayError(e)); setBusy(false); }
  };
  return (
    <Body>
      <Head who={`Shared draft${d.author_name ? ` by ${d.author_name}` : ''}`} close={() => close()} />
      <Title>Agree to this exact text?</Title>
      <Exact text={review?.text ?? d.text} />
      {review ? <T v="small">{review.scope} With {review.people.join(', ')}.</T> : null}
      <Notice text={error} tone="danger" />
      <Button label="Agree to this text" busy={busy} disabled={!review} onPress={agree} />
      <Links><Link label="Not now" tone="quiet" onPress={() => close()} /></Links>
    </Body>
  );
}

function JoinerDecision({ entry, close }: { entry: Entry; close: Close }) {
  const { act } = useSession();
  const j = entry.joiner!;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (decision: 'add' | 'decline') => {
    setBusy(true); setError('');
    try {
      const result = await act(b => b.decideJoiner(j.invite_id, j.review_digest, decision));
      if (!result.decided) throw new Error('Parlu could not add them just now. Try again in a moment.');
      close(decision === 'add' ? `${cap(j.owner_id)} and ${j.agent_id} are connected.` : 'Declined. Nothing was shared.');
    } catch (e) { setError(sayError(e)); setBusy(false); }
  };
  return (
    <Body>
      <Head owner={j.owner_id} agent={j.agent_id} who="Used your invite" e="look" close={() => close()} />
      <Title>Add {cap(j.owner_id)} and {j.agent_id}?</Title>
      <T v="body">Check this code with {cap(j.owner_id)} before you add them. If it does not match, decline.</T>
      <View style={{ backgroundColor: colour.raised, borderRadius: 16, paddingVertical: 16 }}>
        <Text style={{ fontFamily: font.extrabold, fontSize: 34, letterSpacing: 6, color: colour.text, textAlign: 'center' }}>{j.code}</Text>
      </View>
      <Notice text={error} tone="danger" />
      <Button label={`Add ${cap(j.owner_id)}`} busy={busy} onPress={() => run('add')} />
      <Links><Link label="Decline" tone="danger" onPress={() => run('decline')} /></Links>
    </Body>
  );
}

function Gone({ close }: { close: Close }) {
  return (
    <Body>
      <Head who="Already dealt with" close={() => close()} />
      <Title>This is no longer waiting for you</Title>
      <T v="body">Nothing was changed from here.</T>
    </Body>
  );
}

function Elsewhere({ entry, close }: { entry: Entry; close: Close }) {
  return (
    <Body>
      <Head who="Opens on your computer" close={() => close()} />
      <Title>{entry.title}</Title>
      <T v="body">This one opens on your computer for now. It stays waiting until you get to it.</T>
    </Body>
  );
}

/** Both assistants light up beside their owners, a teal tick pops between them, then the receipt. */
function Agreed({ receipt, close }: { receipt: Receipt; close: Close }) {
  const { state } = useSession();
  const [lit, setLit] = useState(false);
  useEffect(() => { const t = setTimeout(() => setLit(true), 280); return () => clearTimeout(t); }, []);
  const me = state!.identity.owner_id, mine = state!.identity.agent_id;
  const ref = receipt.digest ? `${receipt.digest.slice(0, 4)}…${receipt.digest.slice(-2)}` : '';
  return (
    <View style={{ gap: 14, alignItems: 'center', paddingTop: 6 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} accessible accessibilityLabel={`You and ${receipt.owner} agreed`}>
        <Animated.View entering={FadeIn.duration(260)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <Person name={me} size={34} />
          <Bot name={mine} size={52} e={lit ? 'done' : 'look'} />
        </Animated.View>
        <Animated.View entering={ZoomIn.delay(420).springify().damping(11)} style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: colour.accent, alignItems: 'center', justifyContent: 'center', marginHorizontal: 12 }}>
          <Svg width={15} height={15} viewBox="0 0 24 24"><Path d="M5 12.5l4.5 4.5L19 7.5" stroke="#fff" strokeWidth={3.2} fill="none" strokeLinecap="round" strokeLinejoin="round" /></Svg>
        </Animated.View>
        <Animated.View entering={FadeIn.duration(260).delay(80)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <Person name={receipt.owner ?? 'Them'} size={34} />
          <Bot name={receipt.agent ?? 'Assistant'} size={52} e={lit ? 'done' : 'look'} />
        </Animated.View>
      </View>
      <Animated.View entering={riseIn(480)} style={{ alignItems: 'center', gap: 6 }}>
        <Text accessibilityRole="header" style={{ fontFamily: font.bold, fontSize: 26, letterSpacing: -0.7, color: colour.text, textAlign: 'center' }}>You and {receipt.owner} agreed.</Text>
        <T v="body" style={{ textAlign: 'center', color: colour.muted }}>{receipt.line}</T>
      </Animated.View>
      <Animated.View entering={riseIn(640)} style={{ alignSelf: 'stretch', borderWidth: 1, borderColor: colour.line, borderRadius: 18, padding: 16, gap: 10 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
          <View style={{ gap: 2, flex: 1 }}>
            <T v="small">{receipt.amount ? 'Up to' : 'Agreed'}</T>
            <T v="section" numberOfLines={2}>{receipt.amount || receipt.title}</T>
          </View>
          <View style={{ gap: 4, alignItems: 'flex-end' }}>
            <T v="small">Signed by</T>
            <View style={{ flexDirection: 'row', gap: 4 }}><Person name={me} size={22} /><Person name={receipt.owner ?? 'Them'} size={22} /></View>
          </View>
        </View>
        {receipt.amount ? <T v="small">{receipt.title}</T> : null}
        {ref ? <T v="mono">RECEIPT {ref}</T> : null}
      </Animated.View>
      <Animated.View entering={riseIn(760)} style={{ alignSelf: 'stretch' }}>
        <Button label="Done" onPress={() => close('Receipt saved in Recents.')} />
      </Animated.View>
    </View>
  );
}

/** What the sheet shows for one queue key (or `item:<id>` for any saved piece of work). */
export function DecideContent({ entryKey, close }: { entryKey: string; close: Close }) {
  const { state, approvals, setReceipt } = useSession();
  const [receipt, setLocal] = useState<Receipt | null>(null);
  const entry = useMemo(() => {
    if (!state) return undefined;
    const queued = queueOf(state, approvals).find(e => e.key === entryKey);
    if (queued) return queued;
    // Team mission parts and Recents open here too: look the item up directly.
    const item = entryKey.startsWith('item:') ? state.items.find(i => i.id === entryKey.slice(5)) : undefined;
    return item ? ({ kind: 'proposal', key: entryKey, item, title: item.title } as Entry) : undefined;
    // The entry is fixed when the sheet opens, so a refresh after a yes does not swap it away.
  }, [entryKey]);
  const done: Close = note => { setReceipt(null); close(note); };
  if (receipt) return <Agreed receipt={receipt} close={done} />;
  if (!state || !entry) return <Gone close={close} />;
  const agreed = (r: Receipt) => { setReceipt(r); setLocal(r); };
  switch (entry.kind) {
    case 'proposal': return <ProposalDecision entry={entry} item={entry.item!} close={close} agreed={agreed} />;
    case 'question': return <QuestionDecision entry={entry} close={close} />;
    case 'message': return <MessageDecision entry={entry} close={close} />;
    case 'shared-draft': return <DraftDecision entry={entry} close={close} />;
    case 'joiner': return <JoinerDecision entry={entry} close={close} />;
    default: return <Elsewhere entry={entry} close={close} />;
  }
}

