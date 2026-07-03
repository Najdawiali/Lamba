/**
 * Customer Layout — Stack wrapping the bottom Tabs and the detail screens.
 *
 * The Tabs live in the `(tabs)` group so that pushing a detail screen
 * (shop/[id], product/[id], favorites) stacks ON TOP of whichever tab is
 * active. Pressing back from a detail screen returns you to the tab you came
 * from (e.g. Map), instead of resetting to the Explore tab — which is what
 * happened when these screens were registered as hidden Tabs.Screen entries.
 */

import { Stack } from 'expo-router';
import { useThemeColors } from '../../context/ThemeContext';
import { t } from '../../services/i18n';

export default function CustomerLayout() {
  const Colors = useThemeColors();

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: Colors.background },
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="favorites" options={{ headerShown: false }} />
      <Stack.Screen
        name="shop/[id]"
        options={{ headerShown: false, animation: 'slide_from_right' }}
      />
      <Stack.Screen
        name="product/[id]"
        options={{ headerShown: false, animation: 'slide_from_right' }}
      />
    </Stack>
  );
}