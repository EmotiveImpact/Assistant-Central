import React from 'react';
import { View } from 'react-native';
import { Stack } from 'expo-router/stack';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { useFonts } from 'expo-font';
import { PlusJakartaSans_400Regular } from '@expo-google-fonts/plus-jakarta-sans/400Regular';
import { PlusJakartaSans_500Medium } from '@expo-google-fonts/plus-jakarta-sans/500Medium';
import { PlusJakartaSans_600SemiBold } from '@expo-google-fonts/plus-jakarta-sans/600SemiBold';
import { PlusJakartaSans_700Bold } from '@expo-google-fonts/plus-jakarta-sans/700Bold';
import { PlusJakartaSans_800ExtraBold } from '@expo-google-fonts/plus-jakarta-sans/800ExtraBold';
import { SessionProvider } from '../lib/session';
import { GlassBar } from '../ui/Glass';
import { Layers } from '../ui/Layers';
import { OverlayProvider } from '../ui/overlay';
import { colour } from '../ui/theme';

export default function Layout() {
  const [loaded] = useFonts({ PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold, PlusJakartaSans_700Bold, PlusJakartaSans_800ExtraBold });
  if (!loaded) return <View style={{ flex: 1, backgroundColor: colour.bg }} />;
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colour.bg }}>
      <SafeAreaProvider>
        <SessionProvider>
          <OverlayProvider>
            <StatusBar style="dark" />
            {/* Pages cross-fade quickly; their content slides in from the right as in the mock.
                Decisions, menus and search float above in Layers, never as new pages. */}
            <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colour.bg }, animation: 'fade', animationDuration: 160 }}>
              <Stack.Screen name="index" />
              <Stack.Screen name="welcome" />
              <Stack.Screen name="connect" />
              <Stack.Screen name="unlock" />
              <Stack.Screen name="scan" options={{ presentation: 'fullScreenModal', animation: 'slide_from_bottom' }} />
            </Stack>
            <GlassBar />
            <Layers />
          </OverlayProvider>
        </SessionProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
