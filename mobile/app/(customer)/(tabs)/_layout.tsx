/**
 * Customer Tabs — Bottom tab navigation with 5 tabs.
 * Explore · Map · Offers · Messages · Profile
 *
 * Detail screens (shop/[id], product/[id], favorites) are NOT tabs — they live
 * as siblings in the parent (customer) Stack so that pushing them preserves
 * the active tab state (back returns you to the tab you came from, e.g. Map,
 * instead of resetting to Explore).
 */

import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Typography } from '../../../constants/theme';
import { useThemeColors } from '../../../context/ThemeContext';
import { t } from '../../../services/i18n';

export default function CustomerTabsLayout() {
  const Colors = useThemeColors();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: Colors.surface,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          height: 85,
          paddingBottom: 28,
          paddingTop: 8,
        },
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.textMuted,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
      }}
    >
      <Tabs.Screen
        name="search"
        options={{
          title: t('tabs.explore'),
          tabBarIcon: ({ color, size }) => <Ionicons name="compass-outline" size={24} color={color} />,
        }}
      />
      <Tabs.Screen
        name="map"
        options={{
          title: t('tabs.map'),
          tabBarIcon: ({ color, size }) => <Ionicons name="map-outline" size={24} color={color} />,
        }}
      />
      <Tabs.Screen
        name="offers"
        options={{
          title: t('tabs.offers'),
          tabBarIcon: ({ color, size }) => <Ionicons name="pricetag-outline" size={24} color={color} />,
        }}
      />
      <Tabs.Screen
        name="inbox"
        options={{
          title: t('tabs.messages'),
          tabBarIcon: ({ color, size }) => <Ionicons name="chatbubbles-outline" size={24} color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: t('tabs.profile'),
          tabBarIcon: ({ color, size }) => <Ionicons name="person-outline" size={24} color={color} />,
        }}
      />
    </Tabs>
  );
}