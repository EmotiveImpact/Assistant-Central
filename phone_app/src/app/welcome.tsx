// First open: what Parlu is in one line, then try the demo or connect your own Parlu.
import React, { useState } from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useSession, sayError } from '../lib/session';
import { Bot, Button, Notice, Person, T, Wordmark } from '../ui/parts';
import { colour } from '../ui/theme';

export default function Welcome() {
  const { startDemo } = useSession();
  const inset = useSafeAreaInsets();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const demo = async () => {
    setBusy(true); setError('');
    try { await startDemo(); router.replace('/'); } catch (e) { setError(sayError(e)); } finally { setBusy(false); }
  };
  return (
    <View style={{ flex: 1, backgroundColor: colour.bg, paddingTop: inset.top + 20, paddingBottom: inset.bottom + 24, paddingHorizontal: 24, justifyContent: 'space-between' }}>
      <Wordmark size={24} />
      <View style={{ gap: 22 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} accessible accessibilityLabel="Two people, each with their assistant beside them">
          <Person name="Maya" size={52} />
          <Bot name="Juniper" size={58} e="idle" />
          <View style={{ width: 28 }} />
          <Person name="Tom" size={52} />
          <Bot name="Otto" size={58} e="look" />
        </View>
        <T v="page" style={{ fontSize: 38, lineHeight: 42, letterSpacing: -1.7 }}>They do the back and forth. You say yes.</T>
        <T v="body" style={{ fontSize: 17, lineHeight: 25, color: colour.muted }}>
          Your assistant talks to other people’s assistants. Parlu brings you only the decisions, and nothing is sent, shared or paid until you agree.
        </T>
      </View>
      <View style={{ gap: 12 }}>
        <Notice text={error} tone="danger" />
        <Button label="Connect your Parlu" onPress={() => router.push('/connect')} />
        <Button label="Try it with made-up people" kind="secondary" busy={busy} onPress={demo} />
        <T v="small" style={{ textAlign: 'center' }}>You bring your own assistant. Parlu never asks for an AI key.</T>
      </View>
    </View>
  );
}
