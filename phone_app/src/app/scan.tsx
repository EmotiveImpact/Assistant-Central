// Scan someone's invite QR code. The camera is used only while this screen is open, and
// only a Parlu invite link is accepted.
import React, { useRef, useState } from 'react';
import { View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { inviteFromText } from '../shared/web';
import { Button, Notice, T } from '../ui/parts';
import { colour } from '../ui/theme';

export default function Scan() {
  const [permission, request] = useCameraPermissions();
  const inset = useSafeAreaInsets();
  const done = useRef(false);
  const [note, setNote] = useState('');
  const frame = { flex: 1, backgroundColor: colour.bg, paddingTop: inset.top + 20, paddingBottom: inset.bottom + 20, paddingHorizontal: 20, gap: 14 } as const;
  if (!permission) return <View style={frame} />;
  if (!permission.granted) {
    return (
      <View style={[frame, { justifyContent: 'center' }]}>
        <T v="page">Scan an invite</T>
        <T v="body">Parlu needs the camera to read the code someone shows you. It is not used for anything else.</T>
        <Button label="Allow the camera" onPress={request} />
        <Button label="Cancel" kind="quiet" onPress={() => router.back()} />
      </View>
    );
  }
  return (
    <View style={{ flex: 1, backgroundColor: '#000' }}>
      <CameraView style={{ flex: 1 }} facing="back" barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={({ data }) => {
          if (done.current) return;
          const link = inviteFromText(data);
          if (!link) { setNote('That code is not a Parlu invite.'); return; }
          done.current = true;
          router.dismissTo({ pathname: '/invite', params: { link } });
        }} />
      <View style={{ position: 'absolute', left: 20, right: 20, bottom: inset.bottom + 20, gap: 10 }}>
        <Notice text={note || 'Point the camera at their Parlu invite code.'} />
        <Button label="Cancel" kind="secondary" onPress={() => router.back()} />
      </View>
    </View>
  );
}
