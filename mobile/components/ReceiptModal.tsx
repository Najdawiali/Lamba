import React, { useMemo } from 'react';
import { View, Text, StyleSheet, Modal, FlatList, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography, Shadows } from '../constants/theme';
import { t, i18n } from '../services/i18n';
import { formatPrice } from '../services/currency';
import { POSCheckoutResponse } from '../services/api';

interface Props {
  visible: boolean;
  receipt: POSCheckoutResponse | null;
  onClose: () => void;
  onNewTransaction: () => void;
}

export default function ReceiptModal({ visible, receipt, onClose, onNewTransaction }: Props) {
  const Colors = useThemeColors();
  const isAr = i18n.locale?.startsWith('ar');

  const styles = useMemo(() => StyleSheet.create({
    receiptScreenContainer: {
      flex: 1,
      backgroundColor: '#0a0a1a',
      padding: Spacing.lg,
    },
    receiptScreenHeader: {
      alignItems: 'center',
      paddingVertical: Spacing.xl,
      borderBottomWidth: 1,
      borderBottomColor: 'rgba(255, 255, 255, 0.05)',
    },
    receiptSuccessIconWrapper: {
      width: 80,
      height: 80,
      borderRadius: 40,
      backgroundColor: 'rgba(0, 217, 126, 0.1)',
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: Spacing.md,
    },
    receiptScreenTitle: {
      ...Typography.h2,
      color: '#FFF',
      fontWeight: '800',
    },
    receiptScreenSubtitle: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
      textAlign: 'center',
      marginTop: 6,
      paddingHorizontal: Spacing.xl,
    },
    receiptScreenDate: {
      ...Typography.caption,
      color: Colors.textMuted,
      marginTop: Spacing.sm,
    },
    receiptScreenBody: {
      flex: 1,
      marginVertical: Spacing.lg,
    },
    receiptBodySectionTitle: {
      ...Typography.caption,
      color: Colors.textSecondary,
      fontWeight: '700',
      textTransform: 'uppercase',
      letterSpacing: 1,
      marginBottom: Spacing.sm,
    },
    receiptScreenDivider: {
      height: 1,
      backgroundColor: 'rgba(255, 255, 255, 0.08)',
      marginVertical: Spacing.xs,
    },
    receiptItemDetailsRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: Spacing.md,
      borderBottomWidth: 1,
      borderBottomColor: 'rgba(255, 255, 255, 0.03)',
    },
    receiptItemDetailsName: {
      ...Typography.bodySmall,
      color: '#FFF',
      fontWeight: '700',
    },
    receiptItemDetailsSub: {
      ...Typography.caption,
      color: Colors.textMuted,
      marginTop: 2,
    },
    receiptItemDetailsSubtotal: {
      ...Typography.body,
      color: '#FFF',
      fontWeight: '700',
    },
    receiptScreenFooter: {
      paddingBottom: Spacing.xl,
    },
    receiptScreenTotalRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: Spacing.md,
    },
    receiptScreenTotalLabel: {
      ...Typography.body,
      color: Colors.textSecondary,
      fontWeight: '700',
      letterSpacing: 1,
    },
    receiptScreenTotalValue: {
      ...Typography.h1,
      color: Colors.secondary,
      fontWeight: '800',
    },
    receiptScreenThanksText: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
      textAlign: 'center',
      fontStyle: 'italic',
      marginVertical: Spacing.lg,
    },
    receiptScreenCloseBtn: {
      height: 52,
      borderRadius: BorderRadius.md,
      backgroundColor: Colors.primary,
      flexDirection: 'row',
      justifyContent: 'center',
      alignItems: 'center',
      ...Shadows.medium,
    },
    receiptScreenCloseBtnText: {
      ...Typography.button,
      color: '#FFF',
      fontWeight: '700',
    },
  }), [Colors]);

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={false}
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.receiptScreenContainer} edges={['top', 'bottom']}>
        {/* Header */}
        <View style={styles.receiptScreenHeader}>
          <View style={styles.receiptSuccessIconWrapper}>
            <Ionicons name="checkmark-circle" size={48} color={Colors.success} />
          </View>
          <Text style={styles.receiptScreenTitle}>
            {t('scanner.transaction_success', 'Transaction Success')}
          </Text>
          <Text style={styles.receiptScreenSubtitle}>
            {t('scanner.transaction_success_desc', 'Invoice registered & inventory levels adjusted')}
          </Text>
          <Text style={styles.receiptScreenDate}>
            {new Date().toLocaleString()}
          </Text>
        </View>

        {/* Purchased Items List */}
        <View style={styles.receiptScreenBody}>
          <Text style={styles.receiptBodySectionTitle}>
            {t('scanner.receipt_summary', 'Receipt Summary')}
          </Text>
          <View style={styles.receiptScreenDivider} />
          
          <FlatList
            data={receipt?.items || []}
            keyExtractor={(item, index) => `${item.name}-${index}`}
            contentContainerStyle={{ paddingVertical: Spacing.sm }}
            renderItem={({ item }) => (
              <View style={styles.receiptItemDetailsRow}>
                <View style={{ flex: 2 }}>
                  <Text style={styles.receiptItemDetailsName}>{item.name}</Text>
                  <Text style={styles.receiptItemDetailsSub}>
                    {formatPrice(item.unit_price)} × {item.quantity}
                  </Text>
                </View>
                <Text style={styles.receiptItemDetailsSubtotal}>
                  {formatPrice(item.subtotal)}
                </Text>
              </View>
            )}
          />
        </View>

        {/* Footer - Grand Total and Close button */}
        <View style={styles.receiptScreenFooter}>
          <View style={styles.receiptScreenDivider} />
          <View style={styles.receiptScreenTotalRow}>
            <Text style={styles.receiptScreenTotalLabel}>{t('scanner.total', 'GRAND TOTAL')}</Text>
            <Text style={styles.receiptScreenTotalValue}>
              {formatPrice(receipt?.total_cost || 0)}
            </Text>
          </View>
          <View style={styles.receiptScreenDivider} />

          <Text style={styles.receiptScreenThanksText}>
            {t('scanner.thanks', 'Thank you for your business!')}
          </Text>

          <TouchableOpacity
            style={styles.receiptScreenCloseBtn}
            onPress={onNewTransaction}
            activeOpacity={0.8}
          >
            <Ionicons name="sparkles-outline" size={18} color={Colors.textOnPrimary} style={{ marginRight: 6 }} />
            <Text style={styles.receiptScreenCloseBtnText}>
              {t('scanner.new_transaction', 'New Transaction')}
            </Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </Modal>
  );
}
