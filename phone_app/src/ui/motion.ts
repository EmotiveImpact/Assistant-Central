// Motion, taken from the approved full app mock: sheets rise over 300ms on the mock's
// cubic-bezier(.2,.8,.2,1), the dim and menus fade in over 200 to 250ms, and pages slide
// in from 30px to the right over 250ms. Everything runs on the UI thread through Reanimated.
import { useEffect } from 'react';
import { Easing, FadeInDown, FadeInRight, FadeInUp, useSharedValue, withTiming, type SharedValue } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';

export const EASE = Easing.bezier(0.2, 0.8, 0.2, 1);
export const OUT = Easing.out(Easing.cubic);

export const RISE_MS = 300;
export const FADE_MS = 250;
export const LEAVE_MS = 200;

// Entrances use Reanimated's built-in animations rather than custom keyframes: on the web,
// custom keyframes are pinned in place with absolute positioning when they finish, which
// breaks the layout of everything after them.

/** Pages and opened items: a short slide from the right, as in the mock. */
export const slideIn = FadeInRight.duration(260).easing(OUT);

/** A list row arriving, a little after the one above it. */
export const rowIn = (index: number) => FadeInUp.duration(240).delay(Math.min(index, 10) * 28).easing(OUT);

/** Rises from below and fades in. */
export const riseIn = (delay = 0) => FadeInUp.duration(320).delay(delay).easing(EASE);

/** The next card coming forward from the stack behind it. */
export const cardForward = FadeInDown.duration(300).easing(EASE);

/**
 * 0 to 1 when a layer appears, back to 0 when it is asked to close, then `gone` runs so the
 * layer can be removed. Each floating layer maps this one value to its own movement.
 */
export function useAppear(closing: boolean, gone: () => void, inMs = FADE_MS, outMs = LEAVE_MS): SharedValue<number> {
  const p = useSharedValue(0);
  useEffect(() => { p.value = withTiming(1, { duration: inMs, easing: EASE }); }, [p, inMs]);
  useEffect(() => {
    if (!closing) return;
    p.value = withTiming(0, { duration: outMs, easing: OUT }, finished => { if (finished) scheduleOnRN(gone); });
  }, [closing, p, outMs, gone]);
  return p;
}
