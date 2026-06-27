/**
 * App Entry — Redirects to gateway or appropriate role-specific home.
 */

import { useEffect, useState } from 'react';
import { Redirect } from 'expo-router';
import { View, ActivityIndicator } from 'react-native';
import { getToken, getUser } from '../services/api';
import { Colors } from '../constants/theme';

export default function Index() {
  const [loading, setLoading] = useState(true);
  const [isAuthed, setIsAuthed] = useState(false);
  const [userRole, setUserRole] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      const user = await getUser();
      setIsAuthed(!!token);
      // Support both 'role' (legacy) and 'user_type' (v1) field names
      setUserRole(user?.user_type ?? user?.role ?? null);
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

  // Not authenticated → go to role-selection gateway
  if (!isAuthed) return <Redirect href="/(auth)/gateway" />;

  // Authenticated → route to the correct role's home tab
  if (userRole === 'merchant') return <Redirect href="/(merchant)/dashboard" />;
  return <Redirect href="/(customer)/search" />;
}
