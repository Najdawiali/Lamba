/**
 * Quick Sale Screen — Manual instant sale without scanning a barcode.
 * Lets the cashier search inventory by name, pick a stocked item, set a quantity
 * with a +/− stepper, confirm the order total, and check out via the POS API.
 *
 * UX conventions mirrored from cashier/dashboard:
 *  - RefreshControl pull-to-refresh
 *  - Loading text + spinner
 *  - Empty-state icon + label
 *  - RTL-aware rows (flexDirection: row-reverse in Arabic)
 *  - Currency via formatPrice() (no hardcoded codes)
 *  - Vibration feedback on successful checkout (matches scanner.tsx)
 *  - Confirm Alert before deducting inventory (single-item cart review)
 */

import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator,
  Alert, TextInput, KeyboardAvoidingView, Platform, Keyboard,
  Image, ScrollView, TouchableWithoutFeedback, RefreshControl, Vibration,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import {
  getMarketItems, checkoutPOS,
  MarketItemDashboardResponse, POSCheckoutResponse,
} from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import { resolveImageUrl } from '../../services/utils';
import { formatPrice } from '../../services/currency';

export default function QuickSaleScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const isAr = i18n.locale?.startsWith('ar');

  const [items, setItems] = useState<MarketItemDashboardResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selected, setSelected] = useState<MarketItemDashboardResponse | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [lastReceipt, setLastReceipt] = useState<POSCheckoutResponse | null>(null);

  const qtyNum = useMemo(() => {
    const v = parseInt(quantity, 10);
    return isNaN(v) ? 0 : Math.max(0, v);
  }, [quantity]);

  const loadItems = useCallback(async () => {
    try {
      const data = await getMarketItems();
      setItems(data.filter((i) => i.in_stock && i.stock_count > 0));
    } catch (err: any) {
      if (err?.response?.status === 404) {
        Alert.alert(
          isAr ? 'يتطلب إعداد المتجر' : 'Market Setup Required',
          isAr
            ? 'يرجى تهيئة متجرك قبل إجراء عمليات البيع.'
            : 'Please complete market onboarding before processing sales.',
          [{ text: 'OK', onPress: () => router.replace('/(merchant)/onboarding') }]
        );
      } else if (err?.response?.status !== 401) {
        Alert.alert(
          isAr ? 'فشل التحميل' : 'Load Failed',
          isAr ? 'تعذّر تحميل المخزون. اسحب للأسفل للتحديث.' : 'Could not load inventory. Pull down to refresh.',
        );
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadItems();
  }, [loadItems]);

  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) return items;
    const q = searchQuery.toLowerCase();
    return items.filter((i) =>
      i.name.toLowerCase().includes(q)
      || (i.category ? i.category.toLowerCase().includes(q) : false)
    );
  }, [items, searchQuery]);

  const unitPrice = selected?.price ?? null;
  const canSell = !!selected
    && qtyNum >= 1
    && qtyNum <= selected.stock_count
    && unitPrice != null
    && unitPrice > 0;

  const totalCost = useMemo(() => {
    if (unitPrice == null) return 0;
    return Math.max(0, unitPrice * qtyNum);
  }, [unitPrice, qtyNum]);

  const sanitizeQty = (raw: string) => {
    const digits = raw.replace(/[^0-9]/g, '').slice(0, 5);
    setQuantity(digits || '');
  };

  const handleSelect = (item: MarketItemDashboardResponse) => {
    // Reflecting just-decremented stock: read latest from items array if present
    const fresh = items.find((p) => p.id === item.id) ?? item;
    setSelected(fresh);
    setQuantity('1');
    setLastReceipt(null);
    Keyboard.dismiss();
  };

  const handleClearSelection = () => {
    setSelected(null);
    setQuantity('1');
    setLastReceipt(null);
    setSearchQuery('');
    Keyboard.dismiss();
  };

  const handleStepQty = (delta: number) => {
    const next = Math.min(Math.max(qtyNum + delta, 1), selected?.stock_count ?? 1);
    setQuantity(String(next));
  };

  const handleCompleteSale = () => {
    if (!selected) {
      Alert.alert(t('common.error', 'Error'), isAr ? 'يرجى اختيار منتج أولاً.' : 'Please select a product first.');
      return;
    }
    if (qtyNum < 1) {
      Alert.alert(t('common.error', 'Error'), isAr ? 'الرجاء إدخال كمية صحيحة.' : 'Please enter a valid quantity.');
      return;
    }
    if (qtyNum > selected.stock_count) {
      Alert.alert(
        isAr ? 'مخزون غير كافٍ' : 'Insufficient Stock',
        isAr
          ? `الكمية المتاحة: ${selected.stock_count}`
          : `Only ${selected.stock_count} unit(s) available in stock.`,
      );
      return;
    }
    if (unitPrice == null) {
      Alert.alert(
        isAr ? 'سعر غير محدد' : 'No Price Set',
        isAr
          ? 'لا يمكن إتمام البيع لمنتج بدون سعر. حدّث السعر أولاً.'
          : 'Cannot complete a sale for an item without a price. Set the price first.',
      );
      return;
    }

    Alert.alert(
      isAr ? 'تأكيد عملية البيع' : 'Confirm Sale',
      isAr
        ? `سيتم بيع ${qtyNum} × ${selected.name} بقيمة ${formatPrice(totalCost)}.`
        : `Complete sale of ${qtyNum} × ${selected.name} for ${formatPrice(totalCost)}?`,
      [
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
        {
          text: isAr ? 'تأكيد' : 'Confirm',
          style: 'destructive',
          onPress: runCheckout,
        },
      ],
    );
  };

  const runCheckout = async () => {
    if (!selected) return;
    setSubmitting(true);
    try {
      const res = await checkoutPOS([{ market_item_id: selected.id, quantity: qtyNum }]);

      // Haptic success feedback (mirrors scanner.tsx checkout)
      try { Vibration.vibrate([0, 60]); } catch { /* no-op on unsupported devices */ }

      setLastReceipt(res);

      // Decrement stock locally so the list + summary stay consistent.
      const remaining = Math.max(0, selected.stock_count - qtyNum);
      setItems((prev) =>
        prev
          .map((p) =>
            p.id === selected.id
              ? { ...p, stock_count: remaining, in_stock: remaining > 0 }
              : p
          )
          .filter((p) => p.stock_count > 0),
      );
      // Refresh selected so the summary reflects remaining stock (or auto-deselect when depleted).
      if (remaining > 0) {
        setSelected((prev) =>
          prev ? { ...prev, stock_count: remaining, in_stock: true } : prev,
        );
      } else {
        setSelected(null);
        setQuantity('1');
      }

      const alertTitle = (res.alerts && res.alerts.length > 0)
        ? (isAr ? 'تم البيع — مع تنبيه' : 'Sale Completed — With Alert')
        : (isAr ? 'تمت عملية البيع' : 'Sale Completed');
      Alert.alert(
        alertTitle,
        res.alerts && res.alerts.length > 0
          ? res.alerts.map((a) => a.message).join('\n')
          : (isAr
              ? `إجمالي: ${formatPrice(res.total_cost)} عبر ${res.items.length} بند.`
              : `Total: ${formatPrice(res.total_cost)} across ${res.items.length} line item(s).`),
        [{ text: isAr ? 'تم' : 'Done' }],
      );
    } catch (err: any) {
      Alert.alert(
        isAr ? 'فشل البيع' : 'Sale Failed',
        err?.response?.data?.detail || (isAr ? 'تعذّر إتمام عملية البيع.' : 'Could not complete the sale.'),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const styles = useMemo(() => StyleSheet.create({
    container: { flex: 1, backgroundColor: Colors.background },
    header: {
      paddingHorizontal: Spacing.xl, paddingVertical: Spacing.lg,
      borderBottomWidth: 1, borderColor: Colors.border, marginBottom: Spacing.lg,
    },
    headerTitle: { fontSize: 28, fontWeight: '700', color: Colors.textPrimary },
    headerSubtitle: { ...Typography.caption, color: Colors.textMuted, marginTop: 6, lineHeight: 16 },
    content: { flex: 1, paddingHorizontal: Spacing.xl, paddingBottom: 140 },
    searchContainer: {
      flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.md, paddingHorizontal: Spacing.lg, height: 44, gap: Spacing.sm,
      marginBottom: Spacing.sm,
    },
    searchInput: { flex: 1, color: Colors.textPrimary, fontSize: 14 },
    counterRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: Spacing.md },
    counterText: { ...Typography.caption, color: Colors.textMuted, fontWeight: '600' },
    listLabel: { ...Typography.caption, color: Colors.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: Spacing.sm },
    row: {
      flexDirection: 'row', alignItems: 'center',
      backgroundColor: Colors.surface, borderRadius: BorderRadius.lg,
      padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: 'transparent',
    },
    rowSelected: { borderColor: Colors.primary, backgroundColor: Colors.surfaceElevated },
    imageWrapper: {
      width: 56, height: 56, borderRadius: BorderRadius.sm,
      backgroundColor: '#1E2040', overflow: 'hidden', marginRight: Spacing.md,
    },
    image: { width: '100%', height: '100%' },
    placeholderIcon: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    rowInfo: { flex: 1 },
    name: { ...Typography.body, color: Colors.textPrimary, fontWeight: '600' },
    stockText: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2 },
    priceText: { ...Typography.caption, color: Colors.secondary, fontWeight: '700', marginTop: 2 },
    noPriceBadge: {
      ...Typography.caption, color: Colors.warning, fontWeight: '700',
      marginTop: 2,
    },
    emptyContainer: { alignItems: 'center', paddingVertical: Spacing.xxxl },
    emptyIconCircle: {
      width: 56, height: 56, borderRadius: 28,
      backgroundColor: '#2A2D4A', justifyContent: 'center', alignItems: 'center',
      marginBottom: Spacing.md,
    },
    emptyTitle: { fontSize: 16, fontWeight: '600', color: Colors.textPrimary, marginBottom: 4 },
    emptyText: { ...Typography.bodySmall, color: Colors.textMuted, textAlign: 'center' },
    summaryCard: {
      backgroundColor: Colors.surface, borderRadius: BorderRadius.lg,
      padding: Spacing.lg, borderWidth: 1, borderColor: Colors.border,
      marginBottom: Spacing.md, ...Shadows.small,
    },
    summaryHeader: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      marginBottom: Spacing.sm,
    },
    summaryLabel: { ...Typography.caption, color: Colors.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
    clearBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, padding: Spacing.xs, borderRadius: 12, backgroundColor: Colors.surfaceElevated },
    clearBtnText: { ...Typography.caption, color: Colors.textSecondary, fontWeight: '700' },
    selectedItemName: { ...Typography.h3, color: Colors.textPrimary, fontWeight: '700' },
    stockBadgeRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.md },
    stockPill: {
      flexDirection: 'row', alignItems: 'center', gap: 4,
      paddingVertical: 2, paddingHorizontal: Spacing.sm, borderRadius: 12,
      backgroundColor: 'rgba(0, 217, 166, 0.1)', borderWidth: 1, borderColor: 'rgba(0, 217, 166, 0.25)',
    },
    stockPillText: { ...Typography.caption, color: Colors.success, fontWeight: '700' },
    unitPriceText: { ...Typography.body, color: Colors.secondary, fontWeight: '700' },
    inputLabel: { ...Typography.bodySmall, color: Colors.textSecondary, fontWeight: '700', marginBottom: Spacing.xs },
    qtyStepper: {
      flexDirection: 'row', alignItems: 'center',
      backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.md,
      borderWidth: 1, borderColor: Colors.border, height: 50, marginBottom: Spacing.md,
    },
    stepperBtn: {
      width: 50, height: '100%', justifyContent: 'center', alignItems: 'center',
    },
    stepperDisabled: { opacity: 0.35 },
    qtyInput: { flex: 1, textAlign: 'center', color: Colors.textPrimary, ...Typography.body, fontWeight: '700' },
    totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: Spacing.xs },
    totalValue: { ...Typography.h2, color: Colors.textPrimary, fontWeight: '800' },
    actionBtn: {
      backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
      height: 54, justifyContent: 'center', alignItems: 'center',
      flexDirection: 'row', gap: Spacing.sm, ...Shadows.small,
    },
    actionBtnDisabled: { backgroundColor: Colors.surfaceElevated, borderWidth: 1, borderColor: Colors.border },
    actionBtnText: { ...Typography.button, color: Colors.textOnPrimary },
    actionBtnSubText: { fontSize: 12, color: Colors.textOnPrimary, fontWeight: '600', opacity: 0.85 },
    receiptCard: {
      backgroundColor: 'rgba(0, 217, 126, 0.06)', borderRadius: BorderRadius.md,
      borderWidth: 1, borderColor: 'rgba(0, 217, 126, 0.25)', padding: Spacing.md, marginBottom: Spacing.md,
    },
    receiptTitle: { ...Typography.label, color: Colors.success, fontWeight: '700', marginBottom: Spacing.sm },
    receiptRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
    receiptText: { ...Typography.bodySmall, color: Colors.textPrimary },
    receiptSubtle: { ...Typography.bodySmall, color: Colors.textMuted },
    loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: Spacing.md },
    loadingText: { ...Typography.bodySmall, color: Colors.textMuted },
  }), [Colors]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={Colors.primary} />
          <Text style={styles.loadingText}>
            {t('common.loading', 'جاري تحميل المخزون...')}
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>
          {t('merchant.quick_sale', 'بيع سريع')}
        </Text>
        <Text style={styles.headerSubtitle}>
          {t('merchant.quick_sale_desc', 'ابحث في المخزون وأتمم عملية البيع دون الحاجة لمسح باركود.')}
        </Text>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
          <ScrollView
            contentContainerStyle={styles.content}
            keyboardShouldPersistTaps="handled"
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.secondary} />
            }
          >
            {/* Search */}
            <View style={styles.searchContainer}>
              <Ionicons name="search-outline" size={18} color={Colors.textMuted} />
              <TextInput
                style={styles.searchInput}
                placeholder={t('merchant.catalog_search_placeholder', 'ابحث بالاسم أو القسم...')}
                placeholderTextColor={Colors.textMuted}
                value={searchQuery}
                onChangeText={setSearchQuery}
                autoCapitalize="none"
              />
              {searchQuery.length > 0 && (
                <TouchableOpacity onPress={() => setSearchQuery('')}>
                  <Ionicons name="close-circle" size={18} color={Colors.textMuted} />
                </TouchableOpacity>
              )}
            </View>

            <View style={styles.counterRow}>
              <Text style={styles.counterText}>
                {t('inventory.results', `${filteredItems.length} منتج`, { count: filteredItems.length })}
              </Text>
              {selected && (
                <TouchableOpacity style={styles.clearBtn} onPress={handleClearSelection} activeOpacity={0.7}>
                  <Ionicons name="close" size={14} color={Colors.textSecondary} />
                  <Text style={styles.clearBtnText}>{t('common.clear', 'مسح')}</Text>
                </TouchableOpacity>
              )}
            </View>

            {/* Item list */}
            <Text style={styles.listLabel}>{t('inventory.in_stock', 'المنتجات المتوفرة')}</Text>
            {filteredItems.length === 0 ? (
              <View style={styles.emptyContainer}>
                <View style={styles.emptyIconCircle}>
                  <Ionicons name="cube-outline" size={26} color={Colors.textMuted} />
                </View>
                <Text style={styles.emptyTitle}>
                  {t('common.no_items', 'لم يتم العثور على منتجات')}
                </Text>
                <Text style={styles.emptyText}>
                  {items.length === 0
                    ? t('inventory.empty_desc', 'المخزون فارغ. أضف منتجات من تبويب الإضافة.')
                    : t('explore.no_results', 'لا توجد نتائج مطابقة لبحثك.')}
                </Text>
              </View>
            ) : (
              filteredItems.map((item) => {
                const isSelected = selected?.id === item.id;
                const hasPrice = item.price != null;
                return (
                  <TouchableOpacity
                    key={item.id}
                    style={[styles.row, isSelected && styles.rowSelected]}
                    onPress={() => handleSelect(item)}
                    activeOpacity={0.7}
                  >
                    <View style={styles.imageWrapper}>
                      {item.image_url ? (
                        <Image source={{ uri: resolveImageUrl(item.image_url) }} style={styles.image} resizeMode="cover" />
                      ) : (
                        <View style={styles.placeholderIcon}>
                          <Ionicons name="cube-outline" size={22} color={Colors.textMuted} />
                        </View>
                      )}
                    </View>
                    <View style={styles.rowInfo}>
                      <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
                      <Text style={styles.stockText}>
                        {t('inventory.in_stock', 'المتوفر:')} {item.stock_count}
                      </Text>
                      {hasPrice
                        ? <Text style={styles.priceText}>{formatPrice(item.price)}</Text>
                        : <Text style={styles.noPriceBadge}>{t('product.price_request', 'بدون سعر')}</Text>}
                    </View>
                    {isSelected && (
                      <Ionicons name="checkmark-circle" size={22} color={Colors.primary} />
                    )}
                  </TouchableOpacity>
                );
              })
            )}

            {/* Selected item summary */}
            {selected && (
              <View style={styles.summaryCard}>
                <View style={styles.summaryHeader}>
                  <Text style={styles.summaryLabel}>{t('common.item', 'المنتج المحدد')}</Text>
                  <TouchableOpacity style={styles.clearBtn} onPress={handleClearSelection} activeOpacity={0.7}>
                    <Ionicons name="close" size={14} color={Colors.textSecondary} />
                    <Text style={styles.clearBtnText}>{t('common.cancel', 'إلغاء التحديد')}</Text>
                  </TouchableOpacity>
                </View>
                <Text style={styles.selectedItemName}>
                  {selected.name}
                </Text>
                <View style={styles.stockBadgeRow}>
                  <View style={styles.stockPill}>
                    <Ionicons name="cube-outline" size={12} color={Colors.success} />
                    <Text style={styles.stockPillText}>
                      {t('inventory.in_stock', 'المتوفر:')} {selected.stock_count}
                    </Text>
                  </View>
                  <Text style={styles.unitPriceText}>
                    {selected.price != null ? formatPrice(selected.price) : t('product.price_request', 'بدون سعر')}
                  </Text>
                </View>

                {/* Quantity Stepper */}
                <Text style={styles.inputLabel}>{t('common.quantity', 'الكمية')}</Text>
                <View style={styles.qtyStepper}>
                  <TouchableOpacity
                    style={[styles.stepperBtn, (qtyNum <= 1) && styles.stepperDisabled]}
                    onPress={() => handleStepQty(-1)}
                    disabled={qtyNum <= 1}
                    activeOpacity={0.6}
                  >
                    <Ionicons name="remove-outline" size={22} color={Colors.textPrimary} />
                  </TouchableOpacity>
                  <TextInput
                    style={styles.qtyInput}
                    value={quantity}
                    onChangeText={sanitizeQty}
                    keyboardType="number-pad"
                    returnKeyType="done"
                    selectTextOnFocus
                  />
                  <TouchableOpacity
                    style={[styles.stepperBtn, (qtyNum >= selected.stock_count) && styles.stepperDisabled]}
                    onPress={() => handleStepQty(1)}
                    disabled={qtyNum >= selected.stock_count}
                    activeOpacity={0.6}
                  >
                    <Ionicons name="add-outline" size={22} color={Colors.textPrimary} />
                  </TouchableOpacity>
                </View>

                {/* Total */}
                <View style={styles.totalRow}>
                  <Text style={styles.summaryLabel}>{t('history.receipt', 'Total')}</Text>
                  <Text style={styles.totalValue}>{formatPrice(totalCost)}</Text>
                </View>
              </View>
            )}

            {/* Last receipt */}
            {lastReceipt && (
              <View style={styles.receiptCard}>
                <Text style={styles.receiptTitle}>✓ {t('scanner.sale_complete', 'Last Sale')}</Text>
                {lastReceipt.items.map((it, idx) => (
                  <View key={idx} style={styles.receiptRow}>
                    <Text style={styles.receiptText}>{it.name} × {it.quantity}</Text>
                    <Text style={styles.receiptText}>{formatPrice(it.subtotal)}</Text>
                  </View>
                ))}
                <View style={[styles.receiptRow, { marginTop: Spacing.sm }]}>
                  <Text style={[styles.receiptText, { fontWeight: '700' }]}>{t('history.receipt', 'Total')}</Text>
                  <Text style={[styles.receiptText, { fontWeight: '700' }]}>{formatPrice(lastReceipt.total_cost)}</Text>
                </View>
                {lastReceipt.alerts && lastReceipt.alerts.length > 0 && (
                  <Text style={[styles.receiptSubtle, { marginTop: Spacing.sm }]}>
                    {lastReceipt.alerts.map((a) => a.message).join('\n')}
                  </Text>
                )}
              </View>
            )}

            {/* Action button */}
            <TouchableOpacity
              style={[styles.actionBtn, !canSell && styles.actionBtnDisabled]}
              onPress={handleCompleteSale}
              disabled={!canSell || submitting}
              activeOpacity={0.85}
            >
              {submitting ? (
                <ActivityIndicator color={Colors.textOnPrimary} />
              ) : (
                <>
                  <Ionicons name="cart-outline" size={20} color={canSell ? Colors.textOnPrimary : Colors.textMuted} />
                  <View>
                    <Text style={[styles.actionBtnText, !canSell && { color: Colors.textMuted }]}>
                      {isAr ? 'إتمام البيع' : 'Complete Sale'}
                    </Text>
                    {canSell && (
                      <Text style={styles.actionBtnSubText}>
                        {qtyNum} × {formatPrice(unitPrice)} = {formatPrice(totalCost)}
                      </Text>
                    )}
                  </View>
                </>
              )}
            </TouchableOpacity>
          </ScrollView>
        </TouchableWithoutFeedback>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}