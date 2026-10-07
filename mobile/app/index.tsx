/**
 * App Entry — Redirects to gateway or customer search home.
 * All users enter through the customer interface; merchants manage their store via Profile -> Manage my store.
 *
 * A stored token is not proof of a session: it may have expired, been revoked, or belong to an account that
 * was deleted. So the session is checked with the server (GET /auth/me; the API client renews an expired
 * access token on the way). Only a refused session sends the user to login. No connection, a timeout or a
 * server error keep them signed in, so opening the app offline still works.
 */

import { useEffect, useState } from 'react';
import { Redirect } from 'expo-router';
import { View, ActivityIndicator } from 'react-native';
import { getToken, getUser, saveUser, getMe, isSessionEnded } from '../services/api';
import { useThemeColors } from '../context/ThemeContext';

type Start = 'checking' | 'guest' | 'authed' | 'ended';

export default function Index() {
  const Colors = useThemeColors();
  const [start, setStart] = useState<Start>('checking');

  useEffect(() => {
    let alive = true;
    (async () => {
      let next: Start;
      if (!(await getToken())) {
        next = 'guest';
      } else {
        try {
          const me = await getMe();
          await saveUser({ ...(await getUser()), ...me });
          next = 'authed';
        } catch (err) {
          next = isSessionEnded(err) ? 'ended' : 'authed';
        }
      }
      if (alive) setStart(next);
    })();
    return () => { alive = false; };
  }, []);

  if (start === 'checking') {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background }}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  // Not authenticated → go to welcome gateway
  if (start === 'guest') return <Redirect href="/(auth)/gateway" />;

  // The stored session was refused (expired, revoked, account deleted) → login, with the message
  if (start === 'ended') return <Redirect href={{ pathname: '/(auth)/login', params: { sessionEnded: '1' } }} />;

  // Authenticated → always route to customer home
  return <Redirect href="/(customer)/search" />;
}
