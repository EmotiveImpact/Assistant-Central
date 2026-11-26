// Invite someone with a link or QR code, or join someone else's. Connecting always means
// both people check the same short code first, and the person who made the link says yes.
import React, { useEffect, useState } from 'react';
import { Share, TextInput, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useGuard } from '../lib/guard';
import { sayError, useSession } from '../lib/session';
import { expiresIn, inviteFromText, joinProblem, relayEnabled } from '../shared/web';
import type { InviteReview } from '../lib/types';
import { Button, Card, Notice, Pair, T } from '../ui/parts';
import { QR } from '../ui/QR';
import { Screen } from '../ui/Screen';
import { fieldStyle } from '../ui/field';
import { colour, font } from '../ui/theme';

type Made = { link: string; code: string; join_by: number; label: string };

function Code({ code }: { code: string }) {
  return <T accessibilityLabel={`Code ${code.split('').join(' ')}`} style={{ fontFamily: font.bold, fontSize: 40, letterSpacing: 6, color: colour.text, textAlign: 'center' }}>{code}</T>;
}

export default function Invite() {
  const guard = useGuard();
  const params = useLocalSearchParams<{ link?: string }>();
  const { state, act, backend } = useSession();
  const [label, setLabel] = useState('');
  const [made, setMade] = useState<Made | null>(null);
  const [pasted, setPasted] = useState('');
  const [review, setReview] = useState<{ link: string; value: InviteReview } | null>(null);
  const [joined, setJoined] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const open = async (text: string) => {
    const link = inviteFromText(text);
    setError(''); setReview(null); setJoined('');
    if (!link) { setError('That is not a Parlu invite link. Ask them to send it again.'); return; }
    setBusy('open');
    try { setReview({ link, value: await backend!.openInvite(link) }); } catch (e) { setError(sayError(e)); } finally { setBusy(''); }
  };
  useEffect(() => { if (params.link && backend) open(String(params.link)); }, [params.link, backend]); // eslint-disable-line react-hooks/exhaustive-deps

  if (guard || !state) return guard;
  const relay = relayEnabled(state);

  const make = async () => {
    setBusy('make'); setError('');
    try {
      const result = await act(b => b.createInvite(label));
      if (!result.made) throw new Error('The invite could not be made just now. Try again in a minute.');
      setMade(result);
    } catch (e) { setError(sayError(e)); } finally { setBusy(''); }
  };
  const accept = async () => {
    if (!review || !review.value.ok) return;
    setBusy('accept'); setError('');
    try {
      const result = await act(b => b.acceptInvite(review.link, (review.value as Extract<InviteReview, { ok: true }>).review_digest));
      if (!result.joined) throw new Error(joinProblem(result.reason ?? 'cannot_add', review.value.inviter.owner_id));
      setJoined(`Done. ${review.value.inviter.owner_id} will see your code and add you. You will see them in Money and assistants once they do.`);
      setReview(null); setPasted('');
    } catch (e) { setError(sayError(e)); } finally { setBusy(''); }
  };

  return (
    <Screen title="Invite and join" lead="Connect with someone so your assistants can work together.">
      <Notice text={error} tone="danger" />
      <Notice text={joined} tone="ok" />
      {!relay ? <Notice text="Invites need Parlu to be started with a relay address on your computer, for example --relay https://parlu-relay.vercel.app." /> : null}

      {review ? (
        <Card style={{ gap: 12, marginTop: 14 }}>
          <Pair owner={review.value.inviter.owner_id} agent={review.value.inviter.agent_id} size={30} e="look" />
          <T v="title">{review.value.inviter.owner_id} and {review.value.inviter.agent_id}{review.value.label ? `, “${review.value.label}”` : ''}</T>
          {review.value.ok ? (
            <>
              <T v="body">Check that {review.value.inviter.owner_id} sees this code too. Nothing is shared until they add you.</T>
              <Code code={review.value.code} />
              <Button label={`Connect with ${review.value.inviter.owner_id}`} busy={busy === 'accept'} onPress={accept} />
            </>
          ) : <T v="body">{joinProblem(review.value.reason, review.value.inviter.owner_id)}</T>}
          <Button label="Not now" kind="quiet" onPress={() => setReview(null)} />
        </Card>
      ) : null}

      <T v="section" style={{ marginTop: 22, marginBottom: 10 }}>Invite someone</T>
      {made ? (
        <Card style={{ alignItems: 'center', gap: 12 }}>
          <QR value={made.link} />
          <T v="body" style={{ textAlign: 'center' }}>Show this to {made.label || 'them'} or send the link. When they open it, you both see this code:</T>
          <Code code={made.code} />
          <T v="small">Stops working {expiresIn(made.join_by).toLowerCase()}.</T>
          <Button label="Send the link" style={{ alignSelf: 'stretch' }} onPress={() => Share.share({ message: `Connect with me on Parlu: ${made.link}` }).catch(() => undefined)} />
          <Button label="Make another" kind="quiet" onPress={() => { setMade(null); setLabel(''); }} />
        </Card>
      ) : (
        <View style={{ gap: 10 }}>
          <TextInput value={label} onChangeText={setLabel} placeholder="Who is it for? (optional)" placeholderTextColor={colour.faint} style={fieldStyle} accessibilityLabel="Who is the invite for" maxLength={60} />
          <Button label="Make an invite" busy={busy === 'make'} disabled={!relay} onPress={make} />
        </View>
      )}

      <T v="section" style={{ marginTop: 28, marginBottom: 10 }}>Join someone</T>
      <View style={{ gap: 10 }}>
        <Button label="Scan their code" kind="secondary" disabled={!relay} onPress={() => router.push('/scan')} />
        <TextInput value={pasted} onChangeText={setPasted} placeholder="Or paste their invite link" placeholderTextColor={colour.faint} autoCapitalize="none" autoCorrect={false} style={fieldStyle} accessibilityLabel="Invite link" />
        <Button label="Open the link" kind="secondary" busy={busy === 'open'} disabled={!relay || !pasted.trim()} onPress={() => open(pasted)} />
      </View>

      {state.relay?.invites?.length ? (
        <View style={{ marginTop: 28, gap: 8 }}>
          <T v="label">Your open invites</T>
          {state.relay.invites.map(invite => (
            <View key={invite.id} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colour.line }}>
              <T v="bodyBold">{invite.label || 'Invite'} · {invite.code}</T>
              <T v="small">{invite.state === 'joined' ? 'Used, check on Home' : expiresIn(invite.join_by)}</T>
            </View>
          ))}
        </View>
      ) : null}
    </Screen>
  );
}
