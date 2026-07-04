/**
 * Merchant Layout — Bottom tab navigation with 5 evenly-spaced tabs.
 * Stock (Dashboard), Cashier, Offers, Inbox, Profile
 * Hidden screens: Onboarding, Scanner, History, Low-Stock, Quick-Sale, Add-Product
 *
 * Tab bar spec:
 * - Active tint: #00D68F (teal-green)
 * - Inactive tint: #5A5E7A
 * - Background: #0A0B14
 * - Top border: #1E2040
 * - 5 evenly-spaced destinations (no center slot hack)
 *
 * "Add product" is the merchant's primary *action*, not a destination — so it
 * is rendered as a Floating Action Button (FAB) hovering above the bar (right
 * edge, bottom-aligned; mirrored to left in RTL). The FAB auto-hides on
 * full-screen routes where the tab bar is already hidden. Pattern follows
 * Material Design + iOS HIG (≤5 tab destinations + FAB for primary action).
 */

import React, { useMemo } from 'react';
import { View, StyleSheet, Platform, Pressable } from 'react-native';
import { Tabs, useRouter, usePathname } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Spacing, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';

// Routes on which the FAB should be hidden (full-screen flows / own action target).
const FAB_HIDDEN_TRAILS = [
  '/onboarding',
  '/scanner',
  '/quick-sale',
  '/history',
  '/low-stock',
  '/add-product',
];

export default function MerchantLayout() {
  const Colors = useThemeColors();
  const router = useRouter();
  const pathname = usePathname();
  const isAr = i18n.locale?.startsWith('ar');

  const fabVisible = !FAB_HIDDEN_TRAILS.some((p) => pathname.endsWith(p));

  const styles = useMemo(() => StyleSheet.create({
    wrapper: { flex: 1 },
    fab: {
      position: 'absolute',
      width: 60,
      height: 60,
      borderRadius: 30,
      backgroundColor: Colors.tabActive,
      justifyContent: 'center',
      alignItems: 'center',
      bottom: Platform.OS === 'ios' ? 104 : 80, // clears the 88/64 tab bar + safe area
      // RTL: FAB mirrors to the left edge
      ...(isAr ? { left: Spacing.lg } : { right: Spacing.lg }),
      ...Shadows.glow,
    },
    fabPressed: {
      transform: [{ scale: 0.94 }],
      opacity: 0.9,
    },
    fabIcon: {
      marginTop: 2, // visual centering of the + glyph
    },
  }), [Colors, isAr]);

  return (
    <View style={styles.wrapper}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarStyle: {
            backgroundColor: Colors.background,
            borderTopColor: Colors.border,
            borderTopWidth: 1,
            height: Platform.OS === 'ios' ? 88 : 64,
            paddingBottom: Platform.OS === 'ios' ? 28 : 8,
            paddingTop: 8,
            paddingHorizontal: 4,
          },
          tabBarItemStyle: {
            paddingHorizontal: 4,
            paddingVertical: 4,
          },
          tabBarActiveTintColor: Colors.tabActive,
          tabBarInactiveTintColor: Colors.tabInactive,
          tabBarLabelStyle: { fontSize: 11, fontWeight: '600', marginTop: 2 },
          tabBarIconStyle: { marginBottom: 0 },
        }}
      >
        <Tabs.Screen
          name="dashboard"
          options={{
            title: t('tabs.dashboard'),
            tabBarIcon: ({ color, size }) => <Ionicons name="grid-outline" size={size} color={color} />,
          }}
        />
        <Tabs.Screen
          name="cashier"
          options={{
            title: t('tabs.cashier'),
            tabBarIcon: ({ color, size }) => <Ionicons name="card-outline" size={size} color={color} />,
          }}
        />
        <Tabs.Screen
          name="offers"
          options={{
            title: t('tabs.offers'),
            tabBarIcon: ({ color, size }) => <Ionicons name="pricetag-outline" size={size} color={color} />,
          }}
        />
        <Tabs.Screen
          name="inbox"
          options={{
            title: t('tabs.inbox'),
            tabBarIcon: ({ color, size }) => <Ionicons name="chatbubbles-outline" size={size} color={color} />,
          }}
        />
        <Tabs.Screen
          name="profile"
          options={{
            title: t('tabs.profile'),
            tabBarIcon: ({ color, size }) => <Ionicons name="person-outline" size={size} color={color} />,
          }}
        />
        <Tabs.Screen
          name="add-product"
          options={{
            href: null, // Hidden from tab bar — reachable via the FAB
          }}
        />
        <Tabs.Screen
          name="onboarding"
          options={{
            href: null, // Hidden from tab bar — shown as modal when market not set up
          }}
        />
        <Tabs.Screen
          name="scanner"
          options={{
            href: null, // Hidden from tab bar — navigated programmatically
            tabBarStyle: { display: 'none' }, // Hide tab bar during scanning
          }}
        />
        <Tabs.Screen
          name="history"
          options={{
            href: null, // Hidden from tab bar — navigated programmatically
          }}
        />
        <Tabs.Screen
          name="low-stock"
          options={{
            href: null,
          }}
        />
        <Tabs.Screen
          name="quick-sale"
          options={{
            href: null, // Hidden from tab bar — navigated from Cashier
          }}
        />
      </Tabs>

      {fabVisible && (
        <Pressable
          style={({ pressed }) => [styles.fab, pressed && styles.fabPressed]}
          onPress={() => router.push('/(merchant)/add-product')}
          accessibilityRole="button"
          accessibilityLabel={t('tabs.add', 'Add Product')}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Ionicons name="add" size={32} color="#FFFFFF" style={styles.fabIcon} />
        </Pressable>
      )}
    </View>
  );
}