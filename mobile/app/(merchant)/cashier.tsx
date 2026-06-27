/**
 * Cashier Screen — Sales & Transaction operations.
 * Hosts Scan Barcode (POS/Inventory) and Sales History (Receipt logs).
 * Premium dark layout matching the merchant theme.
 */

import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { t, i18n } from '../../services/i18n';

export default function CashierScreen() {
  const router = useRouter();
  const isAr = i18n.locale.includes('ar');

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={[styles.headerTitle, { textAlign: isAr ? 'right' : 'left' }]}>
          {isAr ? 'عمليات الكاشير' : 'Cashier Operations'}
        </Text>
        <Text style={[styles.headerSubtitle, { textAlign: isAr ? 'right' : 'left' }]}>
          {isAr ? 'أدوات البيع وإدارة مبيعات الكاشير وسجل الفواتير' : 'POS sales tools, cashier scanner, and historical transactions'}
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
          accessibilityLabel={t('scanner.scan_barcode')}
        >
          <View style={[styles.cardInner, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
            <View style={[styles.iconWrapper, styles.primaryIconBg]}>
              <Ionicons name="barcode-outline" size={26} color={Colors.primary} />
            </View>
            <View style={[styles.textWrapper, { alignItems: isAr ? 'flex-end' : 'flex-start' }]}>
              <Text style={styles.cardTitle}>{t('scanner.scan_barcode')}</Text>
              <Text style={[styles.cardDescription, { textAlign: isAr ? 'right' : 'left' }]}>
                {isAr 
                  ? 'امسح باركود منتج لتسجيل عملية بيع، تحديث كميات المخزون، أو ربط المنتجات بالمتجر.'
                  : 'Scan a product barcode to process checkouts, update quantities, or link items to inventory.'}
              </Text>
            </View>
            <Ionicons name={isAr ? 'chevron-back' : 'chevron-forward'} size={20} color={Colors.textMuted} />
          </View>
        </TouchableOpacity>

        {/* Card 2: Sales History (Receipt Logs) */}
        <TouchableOpacity
          style={styles.actionCard}
          onPress={() => router.push('/(merchant)/history')}
          activeOpacity={0.8}
          accessibilityRole="button"
          accessibilityLabel={t('history.title')}
        >
          <View style={[styles.cardInner, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
            <View style={[styles.iconWrapper, styles.secondaryIconBg]}>
              <Ionicons name="receipt-outline" size={26} color={Colors.secondary} />
            </View>
            <View style={[styles.textWrapper, { alignItems: isAr ? 'flex-end' : 'flex-start' }]}>
              <Text style={styles.cardTitle}>{t('history.title')}</Text>
              <Text style={[styles.cardDescription, { textAlign: isAr ? 'right' : 'left' }]}>
                {isAr
                  ? 'عرض فواتير المبيعات السابقة، المنتجات المباعة، وإجمالي الإيرادات اليومية والشبكية.'
                  : 'View historical sales receipts, checkout details, aggregate revenue, and cashier records.'}
              </Text>
            </View>
            <Ionicons name={isAr ? 'chevron-back' : 'chevron-forward'} size={20} color={Colors.textMuted} />
          </View>
        </TouchableOpacity>

        {/* Card 3: Quick Sale */}
        <TouchableOpacity
          style={styles.actionCard}
          onPress={() => router.push('/(merchant)/quick-sale')}
          activeOpacity={0.8}
          accessibilityRole="button"
          accessibilityLabel={isAr ? 'بيع سريع' : 'Quick Sale'}
        >
          <View style={[styles.cardInner, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
            <View style={[styles.iconWrapper, styles.secondaryIconBg]}>
              <Ionicons name="cash-outline" size={26} color="#00D68F" />
            </View>
            <View style={[styles.textWrapper, { alignItems: isAr ? 'flex-end' : 'flex-start' }]}>
              <Text style={styles.cardTitle}>{isAr ? 'بيع سريع' : 'Quick Sale'}</Text>
              <Text style={[styles.cardDescription, { textAlign: isAr ? 'right' : 'left' }]}>
                {isAr
                  ? 'أدخل السعر يدوياً لإنشاء تذكرة بيع فورية بدون مسح الباركود.'
                  : 'Manually enter a price to create an instant sale ticket without scanning.'}
              </Text>
            </View>
            <Ionicons name={isAr ? 'chevron-back' : 'chevron-forward'} size={20} color={Colors.textMuted} />
          </View>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
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
    paddingBottom: 24,
    gap: Spacing.lg,
  },
  actionCard: {
    backgroundColor: Colors.surfaceGlass,
    borderRadius: BorderRadius.xl,
    borderWidth: 1,
    borderColor: Colors.border,
    minHeight: 96,
    overflow: 'hidden',
    ...Shadows.medium,
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

});
