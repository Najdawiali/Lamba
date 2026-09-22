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
 * - 5 evenly-spaced destinations
 * - backBehavior="history" ensures sub-screens pop back to cashier / caller tab
 */

import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../../context/ThemeContext';
import { t } from '../../services/i18n';

export default function MerchantLayout() {
  const Colors = useThemeColors();

  return (
    <Tabs
        backBehavior="history"
        screenOptions={{
          headerShown: false,
          tabBarStyle: {
            backgroundColor: Colors.background,
            borderTopColor: Colors.border,
            borderTopWidth: 1,
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
            href: null, // Hidden from tab bar — reachable via inventory actions
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
      </Tabs>
  );
}