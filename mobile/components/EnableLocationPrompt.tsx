/**
 * EnableLocationPrompt — Shown when location permission is denied.
 * Explains why location is needed and offers a button to open settings.
 */

import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Linking, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography } from '../constants/theme';
import { t } from '../services/i18n';

interface Props {
  onRetry: () => void;
}

export default function EnableLocationPrompt({ onRetry }: Props) {
  const Colors = useThemeColors();

  const openSettings = () => {
    if (Platform.OS === 'ios') {
      Linking.openURL('app-settings:');
    } else {
      Linking.openSettings();
    }
  };

  return (
    <View style={[styles.container, { backgroundColor: Colors.background }]}>
      <View style={[styles.card, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
        <Ionicons name="location-outline" size={48} color={Colors.primary} />
        <Text style={[styles.title, { color: Colors.textPrimary }]}>
          {t('location.title', 'Location Required')}
        </Text>
        <Text style={[styles.subtitle, { color: Colors.textSecondary }]}>
          {t('location.subtitle', 'Lamba needs your location to show nearby stores and products.')}
        </Text>
        <TouchableOpacity
          style={[styles.button, { backgroundColor: Colors.primary }]}
          onPress={openSettings}
          activeOpacity={0.8}
        >
          <Ionicons name="settings-outline" size={18} color="#FFF" />
          <Text style={styles.buttonText}>
            {t('location.open_settings', 'Open Settings')}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.retryButton, { borderColor: Colors.border }]}
          onPress={onRetry}
          activeOpacity={0.8}
        >
          <Text style={[styles.retryText, { color: Colors.primary }]}>
            {t('location.retry', 'Try Again')}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.xl,
  },
  card: {
    alignItems: 'center',
    padding: Spacing.xxl,
    borderRadius: BorderRadius.xl,
    borderWidth: 1,
    width: '100%',
    maxWidth: 340,
  },
  title: {
    ...Typography.h2,
    marginTop: Spacing.lg,
    textAlign: 'center',
  },
  subtitle: {
    ...Typography.body,
    marginTop: Spacing.sm,
    textAlign: 'center',
    lineHeight: 22,
  },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.xl,
    borderRadius: BorderRadius.lg,
    marginTop: Spacing.xl,
    width: '100%',
    justifyContent: 'center',
  },
  buttonText: {
    color: '#FFF',
    fontWeight: '700',
    fontSize: 15,
  },
  retryButton: {
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.xl,
    borderRadius: BorderRadius.lg,
    marginTop: Spacing.md,
    borderWidth: 1,
    width: '100%',
    alignItems: 'center',
  },
  retryText: {
    fontWeight: '600',
    fontSize: 15,
  },
});
