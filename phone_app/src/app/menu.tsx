// The owner menu: everything beyond Home, one tap away.
import React from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { useSession } from '../lib/session';
import { Pair, T } from '../ui/parts';
import { Sheet } from '../ui/Screen';
import { colour } from '../ui/theme';

function Line({ label, note, onPress, tone }: { label: string; note?: string; onPress: () => void; tone?: 'danger' }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label}
      style={({ pressed }) => ({ paddingVertical: 14, borderTopWidth: 1, borderTopColor: colour.line, opacity: pressed ? 0.7 : 1 })}>
      <T v="bodyBold" style={tone === 'danger' ? { color: colour.danger } : undefined}>{label}</T>
      {note ? <T v="small">{note}</T> : null}
    </Pressable>
  );
}

export default function Menu() {
  const { state, backend, lock, leave } = useSession();
  if (!state || !backend) return null;
  const go = (path: '/recents' | '/team' | '/money' | '/invite' | '/settings') => { router.back(); router.push(path); };
  return (
    <Sheet style={{ gap: 0 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Pair owner={state.identity.owner_id} agent={state.identity.agent_id} size={34} />
        <View>
          <T v="section">{state.identity.owner_id}</T>
          <T v="small">With {state.identity.agent_id}, your assistant</T>
        </View>
      </View>
      <Line label="Recents" note="Everything that happened, newest first" onPress={() => go('/recents')} />
      <Line label="Team missions" note="Work split across several people’s assistants" onPress={() => go('/team')} />
      <Line label="Money and assistants" note="Shared budgets and who you are connected to" onPress={() => go('/money')} />
      <Line label="Invite someone" note="A link or QR code to connect" onPress={() => go('/invite')} />
      <Line label="Settings" onPress={() => go('/settings')} />
      {backend.mode === 'demo'
        ? <Line label="Leave the demo" onPress={async () => { router.back(); await leave(); router.replace('/welcome'); }} />
        : <Line label="Lock Parlu" note="Ends this session now" onPress={() => { router.back(); lock('Locked. Type your password to carry on.'); router.replace('/unlock'); }} />}
    </Sheet>
  );
}
