// Decide. One sheet for every kind of decision on Home. It leads with the person and what
// will happen, shows the exact text, and asks for a hold when money or consent is involved.
// Every yes sends the exact review you were shown; the server refuses it if anything changed.
import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import Svg, { Circle, ClipPath, Defs, G, Text as SvgText } from 'react-native-svg';
import { useGuard } from '../lib/guard';
import { cardFor, queueOf, type Entry } from '../lib/home';
import { sayError, useSession } from '../lib/session';
import { ANSWER_LIMIT, decisionQuestion, decisionRows, exactMoney, needsHold } from '../shared/web';
import type { DraftReview, Item, Review } from '../lib/types';
import { HoldButton } from '../ui/HoldButton';
import { Button, Card, Notice, Pair, T } from '../ui/parts';
import { Sheet } from '../ui/Screen';
import { colour, font } from '../ui/theme';

const short = (amount: string) => amount.replace(/\.00$/, '');

/** Two people's circles meeting, with the amount in the shared part. */
function Agreement({ you, them, amount }: { you: string; them: string; amount: string }) {
  return (
    <View accessible accessibilityLabel={`${amount}, agreed between you and ${them}`} style={{ alignItems: 'center' }}>
      <Svg width={260} height={150} viewBox="0 0 260 150">
        <Defs><ClipPath id="left"><Circle cx={95} cy={75} r={72} /></ClipPath></Defs>
        <Circle cx={95} cy={75} r={72} fill={colour.accent} />
        <Circle cx={165} cy={75} r={72} fill={colour.accentOn} />
        <G clipPath="url(#left)"><Circle cx={165} cy={75} r={72} fill={colour.text} /></G>
        <SvgText x={130} y={82} fill="#fff" fontSize={19} fontFamily={font.bold} textAnchor="middle">{amount}</SvgText>
        <SvgText x={52} y={118} fill="#fff" fontSize={13} fontFamily={font.semibold} textAnchor="middle">You</SvgText>
        <SvgText x={208} y={118} fill="#fff" fontSize={13} fontFamily={font.semibold} textAnchor="middle">{them}</SvgText>
      </Svg>
    </View>
  );
}

function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <Card style={{ padding: 0 }}>
      {rows.map(([label, text], i) => (
        <View key={label} style={{ flexDirection: 'row', gap: 12, padding: 14, borderTopWidth: i ? 1 : 0, borderTopColor: colour.line }}>
          <T v="smallBold" style={{ width: 62 }}>{label}</T>
          <T v="small" style={{ flex: 1, color: colour.secondary }}>{text}</T>
        </View>
      ))}
    </Card>
  );
}

function Exact({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <View style={{ backgroundColor: colour.raised, borderRadius: 16, padding: 14, gap: 6 }}>
      <T v="label">Exactly what was sent</T>
      <T v="body" selectable style={{ color: colour.text }}>{text}</T>
    </View>
  );
}

function ProposalDecision({ entry, item }: { entry: Entry; item: Item }) {
  const { backend, state, act, setReceipt } = useSession();
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { backend!.review(item.id).then(setReview, e => setError(sayError(e))); }, [backend, item.id]);
  const c = cardFor(state!, entry);
  const actions = review?.allowed_actions ?? [];
  const question = decisionQuestion(item, { agent: c.agent, owner: c.owner }) as string;
  const rows = decisionRows(item, { agent: c.agent, owner: c.owner, actions }) as [string, string][];
  const hold = needsHold(item, 'accept') as boolean;
  const limit = item.mission_cap ?? (item.team?.record === 'part' ? item.team.compute : null);
  const amount = limit ? short(exactMoney(limit.cap_micro, limit.currency) as string) : '';

  const decide = async (decision: 'accept' | 'reject') => {
    if (!review || busy) return;
    setBusy(true); setError('');
    try {
      const result = await act(b => b.decide(item.id, review.review_digest, decision)) as { decision_digest?: unknown } | null;
      if (decision === 'accept') {
        const signed = typeof result?.decision_digest === 'string' ? result.decision_digest : undefined;
        setReceipt({ title: item.title, owner: c.owner, agent: c.agent, amount, digest: signed, at: Date.now(),
          line: item.team?.record === 'result' ? `You merged ${c.agent}’s result.` : amount ? `${c.agent} can now pay ${amount} for this, nothing else.` : `${c.agent} has your signed yes.` });
        router.replace('/agreed');
      } else router.back();
    } catch (e) { setError(sayError(e)); setBusy(false); }
  };
  const release = async () => {
    if (!review || busy) return;
    setBusy(true); setError('');
    try { await act(b => b.release(item.id, review.review_digest)); router.back(); } catch (e) { setError(sayError(e)); setBusy(false); }
  };

  const title = hold && amount && item.mission_cap ? `Hold to pay ${amount} with ${c.owner}` : question;
  return (
    <Sheet>
      <Pair owner={c.owner} agent={c.agent} size={24} />
      <T v="label">{c.who}</T>
      <T v="title" accessibilityRole="header" style={{ fontSize: 26, lineHeight: 32 }}>{title}</T>
      {c.team ? <T v="small">{c.team}</T> : null}
      {hold && amount && item.mission_cap ? <Agreement you="You" them={c.owner} amount={amount} /> : null}
      <Rows rows={rows} />
      <Exact text={review ? review.content : null} />
      <Notice text={error} tone="danger" />
      {!review && !error ? <ActivityIndicator color={colour.accent} /> : null}
      {review && actions.includes('accept') ? (
        hold
          ? <HoldButton label={amount && item.mission_cap ? `Pay ${amount}` : item.team?.record === 'access' ? 'Give access' : 'Agree'} onDone={() => decide('accept')} disabled={busy}
              hint={amount && item.mission_cap ? `${c.agent} can pay this one amount, nothing else. Letting go early does nothing.` : 'Letting go early does nothing.'} />
          : <Button label={item.team?.record === 'result' ? 'Merge this result' : item.kind === 'artifact' ? 'Accept' : 'Agree'} busy={busy} onPress={() => decide('accept')} />
      ) : null}
      {review && actions.includes('release') ? <Button label={`Send to ${c.owner}`} busy={busy} onPress={release} /> : null}
      {review && actions.includes('reject') ? <Button label="Say no" kind="secondary" disabled={busy} onPress={() => decide('reject')} /> : null}
      {review && !actions.some(a => a === 'accept' || a === 'release' || a === 'reject') ? <Notice text="There is nothing to decide here any more." /> : null}
      <Button label="Not now" kind="quiet" onPress={() => router.back()} />
    </Sheet>
  );
}

function QuestionDecision({ entry }: { entry: Entry }) {
  const { approvals, state, act } = useSession();
  const id = entry.key.slice('question:'.length);
  const q = approvals?.questions.find(x => x.question_id === id);
  const c = cardFor(state!, entry);
  const [busy, setBusy] = useState(-1);
  const [error, setError] = useState('');
  if (!q) return <Gone />;
  const answer = async (option: number) => {
    setBusy(option); setError('');
    try { await act(b => b.answer(q.question_id, option)); router.back(); } catch (e) { setError(sayError(e)); setBusy(-1); }
  };
  return (
    <Sheet>
      <Pair owner={c.owner} agent={c.agent} size={24} e="look" />
      <T v="label">{c.who} asks</T>
      <T v="title" accessibilityRole="header" style={{ fontSize: 26, lineHeight: 32 }}>{q.question}</T>
      {q.options.map((option, i) => <Button key={option} label={option} kind={i ? 'secondary' : 'primary'} busy={busy === i} disabled={busy >= 0} onPress={() => answer(i)} />)}
      <Notice text={error} tone="danger" />
      <T v="small">{ANSWER_LIMIT}</T>
      <Button label="Not now" kind="quiet" onPress={() => router.back()} />
    </Sheet>
  );
}

function MessageDecision({ entry }: { entry: Entry }) {
  const { approvals, state, act } = useSession();
  const id = entry.key.slice('message:'.length);
  const m = approvals?.messages.find(x => x.draft_id === id);
  const c = cardFor(state!, entry);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!m) return <Gone />;
  const run = async (send: boolean) => {
    setBusy(true); setError('');
    try { await act(b => (send ? b.approveMessage(m.draft_id, m.digest) : b.declineMessage(m.draft_id))); router.back(); } catch (e) { setError(sayError(e)); setBusy(false); }
  };
  return (
    <Sheet>
      <Pair owner={c.owner} agent={c.agent} size={24} />
      <T v="label">{c.who}</T>
      <T v="title" accessibilityRole="header" style={{ fontSize: 26, lineHeight: 32 }}>Send this message for you?</T>
      <Exact text={m.text} />
      <Rows rows={[['Sends', 'Exactly this text, as your own message, once.'], ['Keeps', 'Everything else. Your assistant asks again before the next one.']]} />
      <Notice text={error} tone="danger" />
      <Button label="Send it" busy={busy} onPress={() => run(true)} />
      <Button label="Don’t send" kind="secondary" disabled={busy} onPress={() => run(false)} />
    </Sheet>
  );
}

function DraftDecision({ entry }: { entry: Entry }) {
  const { approvals, backend, act } = useSession();
  const id = entry.key.slice('draft:'.length);
  const d = approvals?.drafts.find(x => x.draft_id === id);
  const [review, setReview] = useState<DraftReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (d) backend!.reviewDraft(d.draft_id, d.conversation_id).then(setReview, e => setError(sayError(e))); }, [backend, d]);
  if (!d) return <Gone />;
  const agree = async () => {
    if (!review) return;
    setBusy(true); setError('');
    try { await act(b => b.approveDraft(d.draft_id, review.review_digest)); router.back(); } catch (e) { setError(sayError(e)); setBusy(false); }
  };
  return (
    <Sheet>
      <T v="label">Shared draft{d.author_name ? ` by ${d.author_name}` : ''}</T>
      <T v="title" accessibilityRole="header">Agree to this exact text?</T>
      <Exact text={review?.text ?? d.text} />
      {review ? <T v="small">{review.scope} With {review.people.join(', ')}.</T> : null}
      <Notice text={error} tone="danger" />
      <Button label="Agree to this text" busy={busy} disabled={!review} onPress={agree} />
      <Button label="Not now" kind="quiet" onPress={() => router.back()} />
    </Sheet>
  );
}

function JoinerDecision({ entry }: { entry: Entry }) {
  const { act } = useSession();
  const j = entry.joiner!;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (decision: 'add' | 'decline') => {
    setBusy(true); setError('');
    try {
      const result = await act(b => b.decideJoiner(j.invite_id, j.review_digest, decision));
      if (!result.decided) throw new Error('Parlu could not add them just now. Try again in a moment.');
      router.back();
    } catch (e) { setError(sayError(e)); setBusy(false); }
  };
  return (
    <Sheet>
      <Pair owner={j.owner_id} agent={j.agent_id} size={28} e="look" />
      <T v="title" accessibilityRole="header">{j.owner_id} and {j.agent_id} used your invite</T>
      <T v="body">Check this code with {j.owner_id} before you add them. If it does not match, decline.</T>
      <T style={{ fontFamily: font.bold, fontSize: 44, letterSpacing: 6, color: colour.text, textAlign: 'center' }}>{j.code}</T>
      <Notice text={error} tone="danger" />
      <Button label={`Add ${j.owner_id}`} busy={busy} onPress={() => run('add')} />
      <Button label="Decline" kind="secondary" disabled={busy} onPress={() => run('decline')} />
    </Sheet>
  );
}

function Gone() {
  return (
    <Sheet>
      <T v="title">This has already been dealt with</T>
      <T v="body">It is no longer waiting for you. Nothing was changed from here.</T>
      <Button label="Back to Home" onPress={() => router.back()} />
    </Sheet>
  );
}

function Elsewhere({ entry }: { entry: Entry }) {
  return (
    <Sheet>
      <T v="title">{entry.title}</T>
      <T v="body">This one opens on your computer for now. It stays waiting until you get to it.</T>
      <Button label="Back to Home" onPress={() => router.back()} />
    </Sheet>
  );
}

export default function Decide() {
  const guard = useGuard();
  const { key } = useLocalSearchParams<{ key: string }>();
  const { state, approvals } = useSession();
  const entry = useMemo(() => {
    if (!state) return undefined;
    const queued = queueOf(state, approvals).find(e => e.key === key);
    if (queued) return queued;
    // Team mission parts open here too, before they are sent: look the item up directly.
    const item = typeof key === 'string' && key.startsWith('item:') ? state.items.find(i => i.id === key.slice(5)) : undefined;
    return item ? ({ kind: 'proposal', key, item, title: item.title } as Entry) : undefined;
  }, [state, approvals, key]);
  if (guard) return guard;
  if (!entry) return <Gone />;
  switch (entry.kind) {
    case 'proposal': return <ProposalDecision entry={entry} item={entry.item!} />;
    case 'question': return <QuestionDecision entry={entry} />;
    case 'message': return <MessageDecision entry={entry} />;
    case 'shared-draft': return <DraftDecision entry={entry} />;
    case 'joiner': return <JoinerDecision entry={entry} />;
    default: return <Elsewhere entry={entry} />;
  }
}
