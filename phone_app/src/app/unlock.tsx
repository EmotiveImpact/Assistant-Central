// Unlock again after the 15-minute session ends, or after locking from the menu.
import React, { useState } from 'react';
import { TextInput, View } from 'react-native';
import { Redirect, router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { sayError, useSession } from '../lib/session';
import { DEMO_PASSWORD } from '../lib/demo';
import { Button, Notice, T, Wordmark } from '../ui/parts';
import { colour } from '../ui/theme';
import { fieldStyle } from '../ui/field';

export default function Unlock() {
  const { backend, locked, unlock, leave } = useSession();
  const inset = useSafeAreaInsets();
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!backend) return <Redirect href="/welcome" />;
  const go = async () => {
    setBusy(true); setError('');
    const typed = password; setPassword('');
    try { await unlock(typed); router.replace('/'); } catch (e) { setError(sayError(e)); } finally { setBusy(false); }
  };
  return (
    <View style={{ flex: 1, backgroundColor: colour.bg, paddingTop: inset.top + 20, paddingHorizontal: 24, paddingBottom: inset.bottom + 24, gap: 18 }}>
      <Wordmark />
      <View style={{ flex: 1, justifyContent: 'center', gap: 14 }}>
        <T v="page">Unlock Parlu</T>
        <T v="body" style={{ color: colour.muted }}>{locked || 'Type your password to carry on.'}</T>
        <T v="small">{backend.mode === 'demo' ? `This is the demo. The password is “${DEMO_PASSWORD}”.` : backend.address}</T>
        <TextInput value={password} onChangeText={setPassword} secureTextEntry autoFocus autoCapitalize="none" autoCorrect={false}
          textContentType="password" style={fieldStyle} onSubmitEditing={go} accessibilityLabel="Parlu password" />
        <Notice text={error} tone="danger" />
        <Button label="Unlock" busy={busy} onPress={go} />
        <Button label="Use a different Parlu" kind="quiet" onPress={async () => { await leave(); router.replace('/welcome'); }} />
      </View>
    </View>
  );
}
