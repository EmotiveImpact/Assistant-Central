// Connect to the Parlu running on your computer. The phone signs in with the same password
// and gets the same short session as the desktop: it holds no keys of its own.
import React, { useEffect, useState } from 'react';
import { TextInput, View } from 'react-native';
import { router } from 'expo-router';
import { cleanAddress } from '../lib/api';
import { rememberedAddress, sayError, useSession } from '../lib/session';
import { Button, Card, Notice, T } from '../ui/parts';
import { Screen } from '../ui/Screen';
import { colour } from '../ui/theme';
import { fieldStyle } from '../ui/field';

export default function Connect() {
  const { connect } = useSession();
  const [address, setAddress] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { rememberedAddress().then(saved => { if (saved) setAddress(current => current || saved); }); }, []);
  const go = async () => {
    setError('');
    if (!cleanAddress(address)) { setError('Use your computer’s secure address, starting with https. A plain http address only works on this device.'); return; }
    setBusy(true);
    const typed = password; setPassword('');
    try { await connect(address, typed); router.replace('/'); } catch (e) { setError(sayError(e)); } finally { setBusy(false); }
  };
  return (
    <Screen title="Connect your Parlu" lead="Your phone talks to the Parlu on your computer. Your keys stay there.">
      <View style={{ gap: 14 }}>
        <T v="smallBold">Your computer’s address</T>
        <TextInput value={address} onChangeText={setAddress} placeholder="https://your-computer.tailnet.ts.net" placeholderTextColor={colour.faint}
          autoCapitalize="none" autoCorrect={false} keyboardType="url" textContentType="URL" style={fieldStyle} accessibilityLabel="Your computer’s address" />
        <T v="smallBold">Parlu password</T>
        <TextInput value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" autoCorrect={false} textContentType="password"
          placeholder="The one you unlock Parlu with" placeholderTextColor={colour.faint} style={fieldStyle} onSubmitEditing={go} accessibilityLabel="Parlu password" />
        <Notice text={error} tone="danger" />
        <Button label="Unlock" busy={busy} onPress={go} />
      </View>
      <Card style={{ marginTop: 26, gap: 8, backgroundColor: colour.raised, borderWidth: 0 }}>
        <T v="bodyBold">Setting up the address</T>
        <T v="small">On your computer, start Parlu with a phone address, then share it privately with Tailscale. Your phone needs Tailscale too.</T>
        <T v="mono" selectable>{'tailscale serve --bg 8877\npython -m workspace_ui.server serve \\\n  --directory ~/parlu --phone-host your-computer.tailnet.ts.net'}</T>
        <T v="small">The session lasts 15 minutes, like on your computer. The app keeps your password and session only in memory.</T>
      </Card>
    </Screen>
  );
}
