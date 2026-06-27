/**
 * Merchant Layout — Bottom tab navigation with 6 visible tabs.
 * Stock (Dashboard), Cashier, Add, Offers, Inbox, Profile
 * Hidden screens: Onboarding, Scanner, History, Low-Stock
 *
 * Tab bar spec:
 * - Active tint: #00D68F (teal-green)
 * - Inactive tint: #5A5E7A
 * - Background: #0A0B14
 * - Top border: #1E2040
 * - Height: 56px + safe area inset
 * - "Add" center tab uses a prominent + icon
 * - Scanner hides the tab bar entirely
 */

import React from 'react';
import { View, StyleSheet, Platform } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing } from '../../constants/theme';
import { t } from '../../services/i18n';

export default function MerchantLayout() {

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: Colors.background,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          height: Platform.OS === 'ios' ? 85 : 65,
          paddingBottom: Platform.OS === 'ios' ? 28 : 8,
          paddingTop: 8,
        },
        tabBarActiveTintColor: Colors.tabActive,
        tabBarInactiveTintColor: Colors.tabInactive,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
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
        name="add-product"
        options={{
          title: t('tabs.add'),
          tabBarIcon: ({ focused }) => (
            <View style={styles.addButton}>
              <Ionicons name="add" size={28} color="#FFFFFF" />
            </View>
          ),
          tabBarLabel: () => null,
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

const styles = StyleSheet.create({
  addButton: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: Colors.tabActive,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Platform.OS === 'ios' ? 20 : 10,
    shadowColor: '#00D68F',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
});
