/**
 * Root Layout — App-wide providers, navigation structure, and push notifications.
 * Uses Expo Router for file-based routing.
 */

import { useEffect, useState } from 'react';
import { Platform, I18nManager } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

import { setupI18n } from '../services/i18n';
import { setupCurrency } from '../services/currency';
import { ThemeProvider, useTheme } from '../context/ThemeContext';
import api from '../services/api';

// Set RTL before first render — synchronous check
try {
  const savedLocale = typeof SecureStore.getItem === 'function' ? SecureStore.getItem('lamba_language') : null;
  const shouldBeRTL = savedLocale ? savedLocale === 'ar' : true; // Arabic is default
  if (I18nManager.isRTL !== shouldBeRTL) {
    I18nManager.allowRTL(shouldBeRTL);
    I18nManager.forceRTL(shouldBeRTL);
  }
} catch (e) {
  console.warn('Error reading saved locale on startup:', e);
}

const isExpoGo = Constants.appOwnership === 'expo' || Constants.executionEnvironment === 'storeClient';

// Configure notification display (guarded for Expo Go)
if (!isExpoGo || Platform.OS !== 'android') {
  try {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: true,
        shouldShowBanner: true,
        shouldShowList: true,
      }),
    });
  } catch {}
}

async function registerForPushNotifications() {
  if (isExpoGo || !Device.isDevice) {
    console.log('Push notifications require a physical device & development build');
    return;
  }

  const settings: any = await Notifications.getPermissionsAsync();
  let finalStatus = settings.status || (settings.granted ? 'granted' : 'denied');

  if (finalStatus !== 'granted') {
    const requested: any = await Notifications.requestPermissionsAsync();
    finalStatus = requested.status || (requested.granted ? 'granted' : 'denied');
  }

  if (finalStatus !== 'granted') {
    console.log('Push notification permission not granted');
    return;
  }

  try {
    const projectId = Constants.expoConfig?.extra?.eas?.projectId || 'c2916c19-6751-44fc-a8ac-669686ac2b97';
    const tokenData = await Notifications.getExpoPushTokenAsync({
      projectId,
    });
    const token = tokenData.data;
    console.log('Push token:', token);

    // Send token to backend
    await api.post('/api/v1/chat/push-token', { token });
  } catch (e) {
    console.log('Failed to get push token:', e);
  }

  // Android notification channel
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('messages', {
      name: 'الرسائل',
      importance: Notifications.AndroidImportance.HIGH,
      sound: 'default',
    });
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 2 },
  },
});

function AppShell() {
  const { colors, isDark, ready } = useTheme();

  if (!ready) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.background }}>
      <QueryClientProvider client={queryClient}>
        <StatusBar style={isDark ? 'light' : 'dark'} />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: colors.background },
            animation: 'slide_from_right',
          }}
        >
          <Stack.Screen name="(auth)" options={{ headerShown: false }} />
          <Stack.Screen name="(customer)" options={{ headerShown: false }} />
          <Stack.Screen name="(merchant)" options={{ headerShown: false }} />
        </Stack>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}

export default function RootLayout() {
  const [isI18nReady, setIsI18nReady] = useState(false);

  useEffect(() => {
    Promise.all([setupI18n(), setupCurrency()]).then(() => setIsI18nReady(true));
    registerForPushNotifications();
  }, []);

  if (!isI18nReady) return null;

  return (
    <ThemeProvider>
      <AppShell />
    </ThemeProvider>
  );
}