// Screens that need a signed-in Parlu send you to the right place when there is none.
import React from 'react';
import { Redirect } from 'expo-router';
import { useSession } from './session';

export function useGuard(): React.ReactElement | null {
  const { backend, locked, state } = useSession();
  if (!backend) return <Redirect href="/welcome" />;
  if (locked || !state) return <Redirect href="/unlock" />;
  return null;
}
