/**
 * Live password rules, shared by sign-up and password reset.
 *
 * Mirrors the server's policy for instant feedback; the server stays the authority
 * (it also rejects common passwords, obvious patterns and personal details).
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../../context/ThemeContext';
import { Typography } from '../../constants/theme';
import { t } from '../../services/i18n';

export const MIN_PASSWORD_LENGTH = 8;
const ENGLISH_ONLY = /^[\x20-\x7E]*$/;  // printable ASCII: English letters, digits, symbols, space
const RULE_MET = '#43A047';

export function checkPassword(password: string, confirm?: string) {
  return {
    longEnough: password.length >= MIN_PASSWORD_LENGTH,
    englishOnly: ENGLISH_ONLY.test(password),
    matches: confirm === undefined || (confirm.length > 0 && confirm === password),
  };
}

type Props = {
  password: string;
  /** Pass the confirmation field's value to also show "passwords match". */
  confirm?: string;
};

export default function PasswordRules({ password, confirm }: Props) {
  const Colors = useThemeColors();
  if (!password) return null;

  const c = checkPassword(password, confirm);
  const rules = [
    { ok: c.longEnough, key: 'register.rule_min_length', fallback: 'At least 8 characters' },
    { ok: c.englishOnly, key: 'register.rule_english_only', fallback: 'English letters, numbers and symbols only' },
  ];
  if (confirm !== undefined && confirm.length > 0) {
    rules.push({ ok: c.matches, key: 'register.rule_match', fallback: 'Passwords match' });
  }

  return (
    <View style={styles.rules}>
      {rules.map(rule => (
        <View key={rule.key} style={styles.row}>
          <Ionicons
            name={rule.ok ? 'checkmark-circle' : 'close-circle'}
            size={16}
            color={rule.ok ? RULE_MET : Colors.error}
          />
          <Text style={[styles.text, { color: rule.ok ? RULE_MET : Colors.textSecondary }]}>
            {t(rule.key, rule.fallback)}
          </Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  rules: { marginTop: -4, marginBottom: 12 },
  row: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  text: { ...Typography.bodySmall, marginStart: 6 },
});
