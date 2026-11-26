import React from 'react';
import { View } from 'react-native';
import { stepShare } from '../shared/web';
import { colour } from './theme';

/** One bar per part of a team mission, filled by how far along it is. */
export function Progress({ parts }: { parts: { step: string }[] }) {
  return (
    <View style={{ flexDirection: 'row', gap: 6 }} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {parts.map((p, i) => (
        <View key={i} style={{ flex: 1, height: 7, borderRadius: 4, backgroundColor: colour.line, overflow: 'hidden' }}>
          <View style={{ width: `${Math.round((stepShare(p.step) as number) * 100)}%`, height: '100%', backgroundColor: p.step === 'Stopped' ? colour.lineStrong : colour.accent, borderRadius: 4 }} />
        </View>
      ))}
    </View>
  );
}

