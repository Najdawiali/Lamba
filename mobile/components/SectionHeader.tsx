import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, Typography } from '../constants/theme';

interface Props {
  title: string;
}

export default function SectionHeader({ title }: Props) {
  const Colors = useThemeColors();
  return (
    <View style={[styles.container, { borderBottomColor: Colors.border }]}>  
      <Text style={[styles.title, { color: Colors.textSecondary }]}>{title}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.xl,
    paddingBottom: Spacing.sm,
  },
  title: {
    ...Typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    fontWeight: '600',
  },
});
