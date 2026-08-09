/**
 * App Entry — Redirects to gateway or customer search home.
 * All users enter through the customer interface; merchants manage their store via Profile -> Manage my store.
 */

import { useEffect, useState } from 'react';
import { Redirect } from 'expo-router';
import { View, ActivityIndicator } from 'react-native';
import { getToken } from '../services/api';
import { useThemeColors } from '../context/ThemeContext';

export default function Index() {
  const Colors = useThemeColors();
  const [loading, setLoading] = useState(true);
  const [isAuthed, setIsAuthed] = useState(false);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      setIsAuthed(!!token);
      setLoading(false);
    })();
  }, []);

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background }}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  // Not authenticated → go to welcome gateway
  if (!isAuthed) return <Redirect href="/(auth)/gateway" />;

  // Authenticated → always route to customer home
  return <Redirect href="/(customer)/search" />;
}
