// A QR code drawn with the desktop app's own encoder, so both show exactly the same squares.
import React, { useMemo } from 'react';
import Svg, { Path, Rect } from 'react-native-svg';
import { qrMatrix, qrPath } from '../shared/web';
import { colour } from './theme';

export function QR({ value, size = 220 }: { value: string; size?: number }) {
  const drawn = useMemo(() => qrPath(qrMatrix(value)), [value]);
  return (
    <Svg width={size} height={size} viewBox={`0 0 ${drawn.size} ${drawn.size}`} accessibilityRole="image" accessibilityLabel="QR code for this invite">
      <Rect width={drawn.size} height={drawn.size} fill="#fff" />
      <Path d={drawn.path} fill={colour.text} />
    </Svg>
  );
}
