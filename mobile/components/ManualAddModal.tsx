import React, { useState, useMemo } from 'react';
import { View, Text, StyleSheet, Modal, FlatList, TouchableOpacity, TextInput, ActivityIndicator, Image } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography, Shadows } from '../constants/theme';
import { t, i18n } from '../services/i18n';
import { formatPrice } from '../services/currency';
import { resolveImageUrl } from '../services/utils';
import { MarketItemDashboardResponse } from '../services/api';

interface Props {
  visible: boolean;
  onClose: () => void;
  items: MarketItemDashboardResponse[];
  loading: boolean;
  getCartQty: (marketItemId: string) => number;
  onIncrement: (item: MarketItemDashboardResponse) => void;
  onDecrement: (marketItemId: string) => void;
  cartCount: number;
  cartTotal: number;
}

export default function ManualAddModal({
  visible,
  onClose,
  items,
  loading,
  getCartQty,
  onIncrement,
  onDecrement,
  cartCount,
  cartTotal,
}: Props) {
  const Colors = useThemeColors();
  const isAr = i18n.locale?.startsWith('ar');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) return items;
    const q = searchQuery.toLowerCase();
    return items.filter(item =>
      item.name.toLowerCase().includes(q) ||
      (item.name_ar && item.name_ar.toLowerCase().includes(q)) ||
      (item.name_en && item.name_en.toLowerCase().includes(q))
    );
  }, [items, searchQuery]);

  const styles = useMemo(() => StyleSheet.create({
    manualAddContainer: {
      flex: 1,
      backgroundColor: Colors.background,
    },
    manualAddHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingHorizontal: Spacing.xl,
      paddingVertical: Spacing.md,
      borderBottomWidth: 1,
      borderBottomColor: Colors.border,
    },
    manualAddTitle: {
      ...Typography.h3,
      color: Colors.textPrimary,
    },
    manualAddSearchBar: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: Colors.surfaceElevated,
      marginHorizontal: Spacing.xl,
      marginVertical: Spacing.md,
      borderRadius: BorderRadius.md,
      paddingHorizontal: Spacing.md,
      height: 44,
      gap: Spacing.sm,
    },
    manualAddSearchInput: {
      flex: 1,
      color: Colors.textPrimary,
      fontSize: 14,
    },
    manualAddItem: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.xl,
      borderBottomWidth: 1,
      borderBottomColor: Colors.border,
    },
    manualAddItemActive: {
      backgroundColor: 'rgba(108, 99, 255, 0.06)',
    },
    manualAddItemName: {
      ...Typography.body,
      fontWeight: '600',
      color: Colors.textPrimary,
    },
    manualAddItemSub: {
      ...Typography.caption,
      color: Colors.textMuted,
      marginTop: 2,
    },
    manualAddPlusBtn: {
      padding: 4,
      justifyContent: 'center',
      alignItems: 'center',
    },
    manualItemStepper: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.full,
      paddingHorizontal: 8,
      paddingVertical: 4,
      borderWidth: 1,
      borderColor: 'rgba(108, 99, 255, 0.3)',
    },
    manualStepperBtn: {
      padding: 2,
      justifyContent: 'center',
      alignItems: 'center',
    },
    manualStepperQty: {
      fontSize: 16,
      fontWeight: '700',
      color: Colors.textPrimary,
      minWidth: 20,
      textAlign: 'center',
    },
    manualAddBottomBar: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: Spacing.xl,
      paddingVertical: Spacing.md,
      backgroundColor: Colors.surface,
      borderTopWidth: 1,
      borderTopColor: Colors.border,
      ...Shadows.medium,
    },
    manualAddCartInfo: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    manualAddCartBadge: {
      backgroundColor: Colors.primary,
      borderRadius: 12,
      minWidth: 24,
      height: 24,
      justifyContent: 'center',
      alignItems: 'center',
      paddingHorizontal: 6,
    },
    manualAddCartBadgeText: {
      fontSize: 12,
      fontWeight: '700',
      color: '#FFF',
    },
    manualAddTotalText: {
      ...Typography.h3,
      color: Colors.textPrimary,
      fontWeight: '700',
    },
    manualAddDoneBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      backgroundColor: Colors.primary,
      paddingVertical: 10,
      paddingHorizontal: Spacing.xl,
      borderRadius: BorderRadius.md,
      ...Shadows.small,
    },
    manualAddDoneBtnText: {
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
      <SafeAreaView style={styles.manualAddContainer} edges={['top', 'bottom']}>
        {/* Header */}
        <View style={styles.manualAddHeader}>
          <Text style={styles.manualAddTitle}>
            {t('scanner.manual_add', 'Manual Add')}
          </Text>
          <TouchableOpacity onPress={onClose}>
            <Ionicons name="close" size={24} color={Colors.textPrimary} />
          </TouchableOpacity>
        </View>

        {/* Search Bar */}
        <View style={styles.manualAddSearchBar}>
          <Ionicons name="search-outline" size={18} color={Colors.textMuted} />
          <TextInput
            style={styles.manualAddSearchInput}
            placeholder={t('scanner.search_products', 'Search products...')}
            placeholderTextColor={Colors.textMuted}
            value={searchQuery}
            onChangeText={setSearchQuery}
            autoFocus
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => setSearchQuery('')}>
              <Ionicons name="close-circle" size={18} color={Colors.textMuted} />
            </TouchableOpacity>
          )}
        </View>

        {/* Product List */}
        {loading ? (
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            <ActivityIndicator size="large" color={Colors.primary} />
          </View>
        ) : (
          <FlatList
            data={filteredItems}
            keyExtractor={item => item.id}
            contentContainerStyle={{ paddingBottom: Spacing.xl }}
            renderItem={({ item }) => {
              const qty = getCartQty(item.id);
              const isSelected = qty > 0;
              return (
                <View style={[styles.manualAddItem, isSelected && styles.manualAddItemActive]}>
                  <View style={{ flex: 1, marginRight: Spacing.sm }}>
                    <Text style={styles.manualAddItemName} numberOfLines={1}>
                      {isAr ? (item.name_ar || item.name) : (item.name_en || item.name)}
                    </Text>
                    <Text style={styles.manualAddItemSub}>
                      {formatPrice(item.price)} · {t('dashboard.stock_label', 'Stock')}: {item.stock_count}
                    </Text>
                  </View>

                  {qty === 0 ? (
                    <TouchableOpacity
                      style={styles.manualAddPlusBtn}
                      onPress={() => onIncrement(item)}
                      activeOpacity={0.7}
                    >
                      <Ionicons name="add-circle-outline" size={28} color={Colors.primary} />
                    </TouchableOpacity>
                  ) : (
                    <View style={styles.manualItemStepper}>
                      <TouchableOpacity
                        style={styles.manualStepperBtn}
                        onPress={() => onDecrement(item.id)}
                        activeOpacity={0.7}
                      >
                        <Ionicons name="remove-circle-outline" size={24} color={Colors.textSecondary} />
                      </TouchableOpacity>
                      <Text style={styles.manualStepperQty}>{qty}</Text>
                      <TouchableOpacity
                        style={styles.manualStepperBtn}
                        onPress={() => onIncrement(item)}
                        activeOpacity={0.7}
                      >
                        <Ionicons name="add-circle" size={24} color={Colors.primary} />
                      </TouchableOpacity>
                    </View>
                  )}
                </View>
              );
            }}
            ListEmptyComponent={
              <View style={{ alignItems: 'center', paddingVertical: Spacing.xxxl }}>
                <Text style={{ color: Colors.textMuted, fontSize: 14 }}>
                  {t('common.no_results', 'No results found')}
                </Text>
              </View>
            }
          />
        )}

        {/* Sticky Bottom Cart Bar */}
        {cartCount > 0 && (
          <View style={styles.manualAddBottomBar}>
            <View style={styles.manualAddCartInfo}>
              <View style={styles.manualAddCartBadge}>
                <Text style={styles.manualAddCartBadgeText}>
                  {cartCount}
                </Text>
              </View>
              <Text style={styles.manualAddTotalText}>{formatPrice(cartTotal)}</Text>
            </View>
            <TouchableOpacity
              style={styles.manualAddDoneBtn}
              onPress={onClose}
              activeOpacity={0.8}
            >
              <Ionicons name="checkmark-circle" size={18} color="#FFF" />
              <Text style={styles.manualAddDoneBtnText}>{t('common.done', 'Done')}</Text>
            </TouchableOpacity>
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
}
