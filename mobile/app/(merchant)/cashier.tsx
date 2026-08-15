/**
 * Cashier Screen — Sales & Transaction operations.
 * Hosts Scan Barcode (POS/Inventory) and Sales History (Receipt logs).
 * Premium dark layout matching the merchant theme.
 */

import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';

export default function CashierScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const isAr = i18n.locale.includes('ar');

  const styles = useMemo(() => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.lg,
    borderBottomWidth: 1,
    borderColor: Colors.border,
    marginBottom: Spacing.xl,
  },
  headerTitle: {
    fontSize: 32,
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  headerSubtitle: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 6,
    lineHeight: 16,
  },
  content: {
    flex: 1,
    paddingHorizontal: Spacing.xl,
    paddingBottom: 140,
    gap: Spacing.lg,
  },
  actionCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.xl,
    borderWidth: 1,
    borderColor: Colors.border,
    minHeight: 96,
    overflow: 'hidden',
    ...Shadows.small,
  },
  cardInner: {
    padding: Spacing.lg,
    alignItems: 'center',
    gap: Spacing.md,
  },
  iconWrapper: {
    width: 54,
    height: 54,
    borderRadius: 27,
    justifyContent: 'center',
    alignItems: 'center',
  },
  primaryIconBg: {
    backgroundColor: 'rgba(108, 99, 255, 0.12)',
  },
  secondaryIconBg: {
    backgroundColor: 'rgba(0, 217, 166, 0.12)',
  },
  textWrapper: {
    flex: 1,
    gap: 4,
  },
  cardTitle: {
    ...Typography.h3,
    color: Colors.textPrimary,
  },
  cardDescription: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    lineHeight: 18,
  },

}), [Colors]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>
          {t('merchant.cashier_ops', 'عمليات الكاشير')}
        </Text>
        <Text style={styles.headerSubtitle}>
          {t('merchant.cashier_ops_desc', 'أدوات نقطة البيع، ماسح الكاشير، وسجل المعاملات')}
        </Text>
      </View>

      {/* Operations Grid/List */}
      <View style={styles.content}>
        {/* Card 1: Scan Barcode (POS Cashier) */}
        <TouchableOpacity
          style={styles.actionCard}
          onPress={() => router.push('/(merchant)/scanner')}
          activeOpacity={0.8}
          accessibilityRole="button"
          accessibilityLabel={t('scanner.scan_barcode', 'مسح الباركود')}
        >
          <View style={[styles.cardInner, { flexDirection: 'row' }]}>
            <View style={[styles.iconWrapper, styles.primaryIconBg]}>
              <Ionicons name="barcode-outline" size={26} color={Colors.primary} />
            </View>
            <View style={styles.textWrapper}>
              <Text style={styles.cardTitle}>{t('scanner.scan_barcode', 'مسح الباركود')}</Text>
              <Text style={styles.cardDescription}>
                {t('merchant.scan_barcode_desc', 'مسح باركود المنتج لإتمام المبيعات أو تحديث الكميات أو ربطه بالمخزون.')}
              </Text>
            </View>
            <Ionicons name={isAr ? "chevron-back" : "chevron-forward"} size={20} color={Colors.textMuted} />
          </View>
        </TouchableOpacity>

        {/* Card 2: Sales History (Receipt Logs) */}
        <TouchableOpacity
          style={styles.actionCard}
          onPress={() => router.push('/(merchant)/history')}
          activeOpacity={0.8}
          accessibilityRole="button"
          accessibilityLabel={t('history.title', 'سجل المبيعات')}
        >
          <View style={[styles.cardInner, { flexDirection: 'row' }]}>
            <View style={[styles.iconWrapper, styles.secondaryIconBg]}>
              <Ionicons name="receipt-outline" size={26} color={Colors.secondary} />
            </View>
            <View style={styles.textWrapper}>
              <Text style={styles.cardTitle}>{t('history.title', 'سجل المبيعات')}</Text>
              <Text style={styles.cardDescription}>
                {t('merchant.history_desc', 'عرض فواتير المبيعات السابقة وتفاصيل الدفع وإجمالي الإيرادات وسجلات الكاشير.')}
              </Text>
            </View>
            <Ionicons name={isAr ? "chevron-back" : "chevron-forward"} size={20} color={Colors.textMuted} />
          </View>
        </TouchableOpacity>

      </View>
    </SafeAreaView>
  );
}
