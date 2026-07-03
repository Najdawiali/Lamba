/**
 * ThemePreferenceRow — Appearance selector (System / Light / Dark).
 *
 * Mirrors the glassmorphic settings card style used in profile screens.
 * Calls `setMode()` from ThemeContext immediately and persists via SecureStore.
 */

import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme, ThemeMode } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography, getShadows } from '../constants/theme';
import { t } from '../services/i18n';

const OPTIONS: Array<{ key: ThemeMode; icon: keyof typeof Ionicons.glyphMap; labelKey: string; descKey: string }> = [
  { key: 'system', icon: 'phone-portrait-outline', labelKey: 'profile.theme_system', descKey: 'profile.theme_system_desc' },
  { key: 'light', icon: 'sunny-outline', labelKey: 'profile.theme_light', descKey: 'profile.theme_light_desc' },
  { key: 'dark', icon: 'moon-outline', labelKey: 'profile.theme_dark', descKey: 'profile.theme_dark_desc' },
];

interface Props {
  style?: ViewStyle;
}

export default function ThemePreferenceRow({ style }: Props) {
  const { colors, mode, setMode } = useTheme();
  const shadows = useMemo(() => getShadows(mode === 'system' ? 'dark' : mode), [mode]);

  const styles = useMemo(
    () =>
      StyleSheet.create({
        card: {
          backgroundColor: colors.surface,
          borderRadius: BorderRadius.xl,
          padding: Spacing.lg,
          borderWidth: 1,
          borderColor: colors.border,
          marginBottom: Spacing.lg,
          ...shadows.medium,
        },
        title: {
          ...Typography.label,
          color: colors.textMuted,
          textTransform: 'uppercase',
          marginBottom: Spacing.xs,
        },
        subtitle: {
          ...Typography.caption,
          color: colors.textSecondary,
          marginBottom: Spacing.md,
        },
        optionRow: {
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.md,
          paddingVertical: Spacing.md,
        },
        optionIcon: {
          width: 40,
          height: 40,
          borderRadius: 12,
          justifyContent: 'center',
          alignItems: 'center',
          backgroundColor: 'rgba(108, 99, 255, 0.1)',
        },
        optionContent: {
          flex: 1,
        },
        optionLabel: {
          ...Typography.body,
          color: colors.textPrimary,
          fontWeight: '500',
        },
        optionDesc: {
          ...Typography.caption,
          color: colors.textMuted,
          marginTop: 1,
        },
        radioOuter: {
          width: 22,
          height: 22,
          borderRadius: 11,
          borderWidth: 2,
          borderColor: colors.border,
          justifyContent: 'center',
          alignItems: 'center',
        },
        radioOuterActive: {
          borderColor: colors.primary,
        },
        radioInner: {
          width: 10,
          height: 10,
          borderRadius: 5,
          backgroundColor: colors.primary,
        },
        divider: {
          height: 1,
          backgroundColor: colors.divider,
        },
      }),
    [colors, shadows],
  );

  return (
    <View style={[styles.card, style]}>
      <Text style={styles.title}>{t('profile.appearance')}</Text>
      <Text style={styles.subtitle}>{t('profile.appearance_desc')}</Text>

      {OPTIONS.map((opt, idx) => {
        const active = mode === opt.key;
        return (
          <React.Fragment key={opt.key}>
            <TouchableOpacity
              style={styles.optionRow}
              activeOpacity={0.7}
              onPress={() => setMode(opt.key)}
            >
              <View style={[styles.optionIcon, { backgroundColor: `${colors.primary}1A` }]}>
                <Ionicons name={opt.icon} size={20} color={colors.primary} />
              </View>
              <View style={styles.optionContent}>
                <Text style={styles.optionLabel}>{t(opt.labelKey)}</Text>
                <Text style={styles.optionDesc}>{t(opt.descKey)}</Text>
              </View>
              <View style={[styles.radioOuter, active && styles.radioOuterActive]}>
                {active && <View style={styles.radioInner} />}
              </View>
            </TouchableOpacity>
            {idx < OPTIONS.length - 1 && <View style={styles.divider} />}
          </React.Fragment>
        );
      })}
    </View>
  );
}