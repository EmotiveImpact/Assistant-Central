// Settings: who you are, which Parlu this is, and how the phone handles your session.
import React from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import Constants from 'expo-constants';
import { useGuard } from '../lib/guard';
import { useSession } from '../lib/session';
import { ANSWER_LIMIT } from '../shared/web';
import { Button, Card, Pair, T } from '../ui/parts';
import { Screen } from '../ui/Screen';
import { colour } from '../ui/theme';

function Line({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ paddingVertical: 12, borderTopWidth: 1, borderTopColor: colour.line, gap: 2 }}>
      <T v="small">{label}</T>
      <T v="bodyBold" selectable>{value}</T>
    </View>
  );
}

export default function Settings() {
  const guard = useGuard();
  const { state, backend, lock, leave } = useSession();
  if (guard || !state || !backend) return guard;
  return (
    <Screen title="Settings">
      <Card style={{ gap: 4 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 10 }}>
          <Pair owner={state.identity.owner_id} agent={state.identity.agent_id} size={34} />
          <View><T v="section">{state.identity.owner_id}</T><T v="small">{state.identity.agent_id}, your assistant</T></View>
        </View>
        <Line label="Connected to" value={backend.mode === 'demo' ? 'The demo, with made-up people' : backend.address} />
        <Line label="Session" value="Ends after 15 minutes, or when you lock Parlu. Kept in memory only." />
        <Line label="AI" value="Parlu runs no AI of its own and never asks for a key. Your own assistant does the thinking." />
      </Card>
      <Card style={{ gap: 6, marginTop: 14 }}>
        <T v="section">Questions from your assistant</T>
        <T v="small">They appear on Home as cards. {ANSWER_LIMIT}</T>
      </Card>
      <Card style={{ gap: 6, marginTop: 14 }}>
        <T v="section">Sending modes and private notes</T>
        <T v="small">How freely your assistant may send for you is set per conversation on your computer, under Approvals. The phone always shows what is waiting.</T>
      </Card>
      <View style={{ gap: 10, marginTop: 22 }}>
        {backend.mode === 'live' ? <Button label="Lock Parlu now" kind="secondary" onPress={() => { lock('Locked. Type your password to carry on.'); router.replace('/unlock'); }} /> : null}
        <Button label={backend.mode === 'demo' ? 'Leave the demo' : 'Use a different Parlu'} kind="danger" onPress={async () => { await leave(); router.replace('/welcome'); }} />
      </View>
      <T v="small" style={{ marginTop: 22, textAlign: 'center' }}>Parlu {Constants.expoConfig?.version ?? ''}</T>
    </Screen>
  );
}
