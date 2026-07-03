/**
 * SkeletonLoader — Animated shimmer placeholder for loading states.
 * Replaces plain ActivityIndicator with premium skeleton UI.
 */

import React, { useEffect, useRef, useMemo } from 'react';
import { View, Animated, StyleSheet, ViewStyle } from 'react-native';
import { BorderRadius, Spacing } from '../constants/theme';
import { useThemeColors } from '../context/ThemeContext';

interface SkeletonProps {
  width?: number | string;
  height?: number;
  borderRadius?: number;
  style?: ViewStyle;
}

function useSkeletonStyles() {
  const Colors = useThemeColors();
  return useMemo(() => StyleSheet.create({
    base: {
      backgroundColor: Colors.surfaceElevated,
    },
    card: {
      flexDirection: 'row',
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.lg,
      marginBottom: Spacing.md,
      borderWidth: 1,
      borderColor: Colors.border,
      overflow: 'hidden',
      minHeight: 115,
    },
    cardContent: {
      flex: 1,
      padding: Spacing.md,
      justifyContent: 'center',
    },
    listItem: {
      flexDirection: 'row',
      alignItems: 'center',
      padding: Spacing.md,
      gap: Spacing.md,
    },
    listItemContent: {
      flex: 1,
    },
    statCard: {
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.md,
      padding: Spacing.lg,
      borderWidth: 1,
      borderColor: Colors.border,
      flex: 1,
    },
  }), [Colors]);
}

function SkeletonPulse({ width = '100%', height = 16, borderRadius = BorderRadius.sm, style }: SkeletonProps) {
  const styles = useSkeletonStyles();
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        styles.base,
        { width: width as any, height, borderRadius, opacity },
        style,
      ]}
    />
  );
}

/** Skeleton card for product lists */
export function SkeletonCard() {
  const styles = useSkeletonStyles();
  return (
    <View style={styles.card}>
      <SkeletonPulse width={100} height={115} borderRadius={0} />
      <View style={styles.cardContent}>
        <SkeletonPulse width="80%" height={14} />
        <SkeletonPulse width="60%" height={12} style={{ marginTop: Spacing.sm }} />
        <SkeletonPulse width="40%" height={16} style={{ marginTop: Spacing.sm }} />
        <SkeletonPulse width="50%" height={10} style={{ marginTop: Spacing.sm }} />
      </View>
    </View>
  );
}

/** Skeleton list item (single row) */
export function SkeletonListItem() {
  const styles = useSkeletonStyles();
  return (
    <View style={styles.listItem}>
      <SkeletonPulse width={40} height={40} borderRadius={20} />
      <View style={styles.listItemContent}>
        <SkeletonPulse width="70%" height={14} />
        <SkeletonPulse width="50%" height={12} style={{ marginTop: Spacing.xs }} />
      </View>
    </View>
  );
}

/** Skeleton stat card for dashboard */
export function SkeletonStatCard() {
  const styles = useSkeletonStyles();
  return (
    <View style={styles.statCard}>
      <SkeletonPulse width="60%" height={12} />
      <SkeletonPulse width="40%" height={24} style={{ marginTop: Spacing.sm }} />
    </View>
  );
}

/** Skeleton grid of product cards */
export function SkeletonProductGrid({ count = 4 }: { count?: number }) {
  return (
    <View>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </View>
  );
}

export default SkeletonPulse;