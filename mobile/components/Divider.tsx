import React from 'react';
import { View, StyleSheet } from 'react-native';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing } from '../constants/theme';

export default function Divider() {
  const Colors = useThemeColors();
  return <View style={[styles.divider, { backgroundColor: Colors.border }]} />;
}

const styles = StyleSheet.create({
  divider: {
    height: StyleSheet.hairlineWidth,
    marginHorizontal: Spacing.lg,
  },
});
