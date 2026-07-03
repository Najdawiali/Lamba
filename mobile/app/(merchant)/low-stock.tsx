import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, Alert, RefreshControl, Image,
  Modal, TextInput, Animated, Platform, Keyboard,
  KeyboardAvoidingView, TouchableWithoutFeedback, Vibration, ScrollView
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getMarketItems, updateMarketItem, logout, MarketItemDashboardResponse } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import { resolveImageUrl } from '../../services/utils';

type StockFilterMode = 'all' | 'out_of_stock' | 'critical' | 'low';

export default function LowStockScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const [products, setProducts] = useState<MarketItemDashboardResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filterMode, setFilterMode] = useState<StockFilterMode>('all');

  // Quick Replenish Modal States
  const [replenishModalVisible, setReplenishModalVisible] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<MarketItemDashboardResponse | null>(null);
  const [replenishCount, setReplenishCount] = useState('10');
  const [savingReplenish, setSavingReplenish] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);

  const isAr = i18n.locale?.startsWith('ar');

  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    
    const showSubscription = Keyboard.addListener(showEvent, () => setKeyboardVisible(true));
    const hideSubscription = Keyboard.addListener(hideEvent, () => setKeyboardVisible(false));
    return () => {
      showSubscription.remove();
      hideSubscription.remove();
    };
  }, []);

  const loadData = useCallback(async (showIndicator = true) => {
    if (showIndicator) setLoading(true);
    try {
      const items = await getMarketItems();
      setProducts(items);
    } catch (err: any) {
      if (err?.response?.status === 401) {
        console.warn('Failed to load replenishment data due to 401 Unauthorized. Logging out.');
        try {
          await logout();
        } catch (logoutErr) {
          // ignore
        }
        router.replace('/(auth)/gateway');
        return;
      }
      
      console.warn('Failed to load replenishment items:', err);
      Alert.alert(
        isAr ? 'خطأ في الاتصال' : 'Connection Error',
        isAr ? 'تعذر جلب بيانات المخزون. يرجى سحب الشاشة للأسفل للتحديث.' : 'Could not query branch items. Swipe down to refresh.'
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isAr]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData(false);
  };

  // Open inline replenish modal
  const handleOpenReplenish = (product: MarketItemDashboardResponse) => {
    setSelectedProduct(product);
    setReplenishCount('10'); // Default replenish value recommendation
    setReplenishModalVisible(true);
  };

  // Save replenished stock
  const handleSaveReplenish = async () => {
    if (!selectedProduct) return;
    const addCount = parseInt(replenishCount, 10);
    
    if (isNaN(addCount) || addCount <= 0) {
      Alert.alert(
        isAr ? 'خطأ في التحقق' : 'Validation Error',
        isAr ? 'الرجاء إدخال كمية صحيحة لإضافتها للمخزون' : 'Please enter a valid positive stock quantity to add'
      );
      return;
    }

    setSavingReplenish(true);
    try {
      const newStockTotal = (selectedProduct.stock_count || 0) + addCount;
      const updated = await updateMarketItem(selectedProduct.id, {
        stock_count: newStockTotal,
      });
      
      // Update local state instantly
      setProducts(prev => prev.map(p => p.id === selectedProduct.id ? updated : p));
      setReplenishModalVisible(false);
      setSelectedProduct(null);
      Vibration.vibrate(50);
      
      Alert.alert(
        isAr ? 'تمت إعادة تعبئة المخزون' : 'Stock Replenished',
        isAr 
          ? `تم تحديث كمية (${updated.name}) بنجاح لتصبح: ${newStockTotal} قطع.`
          : `Successfully incremented (${updated.name}) stock level by ${addCount} units.`
      );
    } catch (err) {
      Alert.alert(
        isAr ? 'فشل التحديث' : 'Replenish Failed',
        isAr ? 'تعذر حفظ المخزون الجديد. يرجى المحاولة مرة أخرى.' : 'Could not update stock levels. Please check connection and try again.'
      );
    } finally {
      setSavingReplenish(false);
    }
  };

  const adjustReplenishQty = (delta: number) => {
    const val = parseInt(replenishCount, 10) || 0;
    const newVal = Math.max(1, val + delta);
    setReplenishCount(newVal.toString());
  };

  const { lowStockItems, categoryGroups } = useMemo(() => {
    // 1. Filter low stock items (stock count <= 10)
    const lowStock = products.filter(p => p.stock_count <= 10);

    // 2. Further filter based on segmented filter modes
    const filteredItems = lowStock.filter(p => {
      if (filterMode === 'out_of_stock') return p.stock_count === 0;
      if (filterMode === 'critical') return p.stock_count >= 1 && p.stock_count <= 5;
      if (filterMode === 'low') return p.stock_count >= 6 && p.stock_count <= 10;
      return true; // 'all'
    });

    // 3. Sort items by priority (stock ascending: 0 first, then 1, 2, 3...)
    const sortedItems = [...filteredItems].sort((a, b) => a.stock_count - b.stock_count);

    // 4. Group sorted items by category
    const categoriesMap: Record<string, MarketItemDashboardResponse[]> = {};
    sortedItems.forEach(item => {
      const cat = item.category || (isAr ? 'عام' : 'General');
      if (!categoriesMap[cat]) {
        categoriesMap[cat] = [];
      }
      categoriesMap[cat].push(item);
    });

    const groups = Object.keys(categoriesMap).map(catName => ({
      categoryName: catName,
      items: categoriesMap[catName]
    })).sort((a, b) => a.categoryName.localeCompare(b.categoryName));

    return { lowStockItems: lowStock, categoryGroups: groups };
  }, [products, filterMode, isAr]);

  const getPriorityColor = (stock: number) => {
    if (stock === 0) return Colors.error;
    if (stock <= 5) return Colors.critical; // #FF6B35 — critical orange
    return Colors.warning; // #FFA726 — low stock amber
  };

  const getPriorityText = (stock: number) => {
    if (stock === 0) return isAr ? 'نفذ المخزون' : 'OUT OF STOCK';
    if (stock <= 5) return isAr ? 'حرج' : 'CRITICAL';
    return isAr ? 'منخفض' : 'LOW STOCK';
  };

  const styles = useMemo(() => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
  },
  header: {
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    ...Typography.h2,
    color: Colors.textPrimary,
  },
  filterContainer: {
    paddingVertical: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  filterScroll: {
    paddingHorizontal: Spacing.lg,
    gap: Spacing.xs,
  },
  filterTab: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.full,
    paddingHorizontal: 16,
    paddingVertical: 8,
    marginEnd: 6,
  },
  filterTabActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  tabBadge: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginEnd: 6,
  },
  filterTabText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    fontWeight: '600',
  },
  filterTabTextActive: {
    color: '#FFF',
    fontWeight: '700',
  },
  listContent: {
    paddingHorizontal: Spacing.lg,
    paddingBottom: Spacing.xxl,
  },
  categorySection: {
    marginTop: Spacing.lg,
  },
  categoryHeaderRow: {
    alignItems: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  categoryHeaderTitle: {
    ...Typography.bodySmall,
    color: Colors.primary,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  categoryHeaderLine: {
    flex: 1,
    height: 1,
    backgroundColor: 'rgba(108, 99, 255, 0.15)',
    marginStart: Spacing.sm,
  },
  productCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.small,
  },
  imageWrapper: {
    width: 50,
    height: 50,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surfaceElevated,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  productImage: {
    width: '100%',
    height: '100%',
  },
  placeholderIconWrapper: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  productDetails: {
    flex: 1,
    marginHorizontal: Spacing.md,
  },
  productName: {
    ...Typography.body,
    fontWeight: '600',
    color: Colors.textPrimary,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 6,
  },
  priorityBadge: {
    borderWidth: 1,
    borderRadius: BorderRadius.sm - 2,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  priorityBadgeText: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  stockCountLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
  replenishBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    gap: 4,
    ...Shadows.small,
  },
  replenishBtnText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#FFF',
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: Spacing.xxl * 1.5,
  },
  emptyIconBg: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: 'rgba(0, 217, 126, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(0, 217, 126, 0.2)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
    paddingHorizontal: Spacing.xxl,
  },

  // Modal styling
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(10, 10, 26, 0.6)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: Colors.surface,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    paddingHorizontal: Spacing.xl,
    paddingBottom: Spacing.xxl,
    borderWidth: 1,
    borderColor: Colors.border,
    borderBottomWidth: 0,
    ...Shadows.large,
  },
  notchWrapper: {
    width: '100%',
    alignItems: 'center',
    paddingVertical: Spacing.sm,
  },
  notch: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  modalTitle: {
    ...Typography.h2,
    color: Colors.textPrimary,
  },
  productModalSummary: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
    marginBottom: Spacing.lg,
  },
  modalThumbWrapper: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surfaceElevated,
    overflow: 'hidden',
  },
  modalThumb: {
    width: '100%',
    height: '100%',
  },
  modalTextWrapper: {
    flex: 1,
    marginHorizontal: Spacing.md,
  },
  modalItemName: {
    ...Typography.body,
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  modalItemSub: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
  },
  inputLabel: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    fontWeight: '700',
    marginBottom: Spacing.sm,
  },
  adjusterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.sm,
    marginBottom: Spacing.xl,
  },
  adjusterBtn: {
    width: 40,
    height: 40,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  adjusterBtnText: {
    fontSize: 12,
    fontWeight: '800',
    color: Colors.primary,
  },
  adjusterInput: {
    width: 70,
    height: 40,
    color: Colors.textPrimary,
    ...Typography.h2,
    fontWeight: '700',
  },
  modalActions: {
    flexDirection: 'row',
    gap: Spacing.md,
  },
  modalBtn: {
    flex: 1,
    height: 52,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalBtnCancel: {
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  modalBtnSave: {
    flexDirection: 'row',
    backgroundColor: Colors.primary,
    ...Shadows.small,
  },
  modalBtnTextCancel: {
    ...Typography.button,
    color: Colors.textSecondary,
  },
  modalBtnTextSave: {
    ...Typography.button,
    color: Colors.textOnPrimary,
  },
  keyboardDismissBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(108, 99, 255, 0.15)',
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: 'rgba(108, 99, 255, 0.3)',
  },
  keyboardDismissText: {
    ...Typography.caption,
    fontWeight: '700',
    color: Colors.primary,
  },
}), [Colors]);

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={[styles.header, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
        <TouchableOpacity
          style={styles.backBtn}
          onPress={() => router.back()}
          activeOpacity={0.7}
        >
          <Ionicons name={isAr ? 'arrow-forward' : 'arrow-back'} size={24} color={Colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {isAr ? 'لوحة إعادة تعبئة المخزون' : 'Replenishment Board'}
        </Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Segmented Filter Control */}
      <View style={styles.filterContainer}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={[styles.filterScroll, { flexDirection: isAr ? 'row-reverse' : 'row' }]}
        >
          <TouchableOpacity
            style={[styles.filterTab, filterMode === 'all' && styles.filterTabActive]}
            onPress={() => setFilterMode('all')}
          >
            <Text style={[styles.filterTabText, filterMode === 'all' && styles.filterTabTextActive]}>
              {isAr ? 'الكل' : 'All Alerts'} ({lowStockItems.length})
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.filterTab, filterMode === 'out_of_stock' && styles.filterTabActive]}
            onPress={() => setFilterMode('out_of_stock')}
          >
            <View style={[styles.tabBadge, { backgroundColor: Colors.error }]} />
            <Text style={[styles.filterTabText, filterMode === 'out_of_stock' && styles.filterTabTextActive]}>
              {isAr ? 'نفذ المخزون' : 'Out of Stock'} ({lowStockItems.filter(p => p.stock_count === 0).length})
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.filterTab, filterMode === 'critical' && styles.filterTabActive]}
            onPress={() => setFilterMode('critical')}
          >
            <View style={[styles.tabBadge, { backgroundColor: '#FF9500' }]} />
            <Text style={[styles.filterTabText, filterMode === 'critical' && styles.filterTabTextActive]}>
              {isAr ? 'حرج' : 'Critical'} ({lowStockItems.filter(p => p.stock_count >= 1 && p.stock_count <= 5).length})
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.filterTab, filterMode === 'low' && styles.filterTabActive]}
            onPress={() => setFilterMode('low')}
          >
            <View style={[styles.tabBadge, { backgroundColor: '#FFCC00' }]} />
            <Text style={[styles.filterTabText, filterMode === 'low' && styles.filterTabTextActive]}>
              {isAr ? 'منخفض' : 'Low'} ({lowStockItems.filter(p => p.stock_count >= 6 && p.stock_count <= 10).length})
            </Text>
          </TouchableOpacity>
        </ScrollView>
      </View>

      {/* Grouped Replenishment List */}
      <FlatList
        data={categoryGroups}
        keyExtractor={item => item.categoryName}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor={Colors.primary}
          />
        }
        contentContainerStyle={styles.listContent}
        renderItem={({ item: group }) => (
          <View style={styles.categorySection}>
            {/* Category Header */}
            <View style={[styles.categoryHeaderRow, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
              <Ionicons name="folder-open-outline" size={16} color={Colors.primary} />
              <Text style={styles.categoryHeaderTitle}>{group.categoryName}</Text>
              <View style={styles.categoryHeaderLine} />
            </View>

            {/* Items inside this category */}
            {group.items.map(item => (
              <View key={item.id} style={[styles.productCard, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
                {/* Image */}
                <View style={styles.imageWrapper}>
                  {item.image_url ? (
                    <Image
                      source={{ uri: resolveImageUrl(item.image_url) }}
                      style={styles.productImage}
                      resizeMode="cover"
                    />
                  ) : (
                    <View style={styles.placeholderIconWrapper}>
                      <Ionicons name="cube-outline" size={20} color={Colors.textMuted} />
                    </View>
                  )}
                </View>

                {/* Details */}
                <View style={[styles.productDetails, { alignItems: isAr ? 'flex-end' : 'flex-start' }]}>
                  <Text style={styles.productName} numberOfLines={1}>{item.name}</Text>
                  
                  <View style={[styles.badgeRow, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
                    {/* Priority Alert Badge */}
                    <View style={[styles.priorityBadge, { borderColor: getPriorityColor(item.stock_count) }]}>
                      <Text style={[styles.priorityBadgeText, { color: getPriorityColor(item.stock_count) }]}>
                        {getPriorityText(item.stock_count)}
                      </Text>
                    </View>
                    <Text style={styles.stockCountLabel}>
                      {isAr ? `الكمية الحالية: ${item.stock_count}` : `Qty Remaining: ${item.stock_count}`}
                    </Text>
                  </View>
                </View>

                {/* Replenish Action Trigger */}
                <TouchableOpacity
                  style={styles.replenishBtn}
                  onPress={() => handleOpenReplenish(item)}
                  activeOpacity={0.8}
                >
                  <Ionicons name="add" size={16} color="#FFF" />
                  <Text style={styles.replenishBtnText}>{isAr ? 'تعبئة' : 'Replenish'}</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <View style={styles.emptyIconBg}>
              <Ionicons name="checkmark-circle-outline" size={44} color={Colors.success} />
            </View>
            <Text style={styles.emptyText}>
              {isAr
                ? 'رائع! لا توجد منتجات أوشكت على النفاذ في متجرك حالياً.'
                : 'Excellent! No items are currently running low or out of stock.'}
            </Text>
          </View>
        }
      />

      {/* Quick Replenish Modal */}
      <Modal
        visible={replenishModalVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setReplenishModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={{ width: '100%' }}
          >
            <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
              <View style={styles.modalContent}>
                {/* Modal Notch Header */}
                <View style={styles.notchWrapper}>
                  <View style={styles.notch} />
                </View>

                {selectedProduct && (
                  <View style={{ width: '100%' }}>
                    {/* Header */}
                    <View style={[styles.modalHeader, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
                      <Text style={styles.modalTitle}>{isAr ? 'شحن المخزون السريع' : 'Quick Stock Replenish'}</Text>
                      {keyboardVisible && (
                        <TouchableOpacity
                          onPress={() => Keyboard.dismiss()}
                          style={styles.keyboardDismissBtn}
                          activeOpacity={0.7}
                        >
                          <Ionicons name="keypad-outline" size={16} color={Colors.primary} />
                          <Text style={styles.keyboardDismissText}>{isAr ? 'تم' : 'Done'}</Text>
                        </TouchableOpacity>
                      )}
                    </View>

                    {/* Product Summary */}
                    <View style={[styles.productModalSummary, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
                      <View style={styles.modalThumbWrapper}>
                        {selectedProduct.image_url ? (
                          <Image
                            source={{ uri: resolveImageUrl(selectedProduct.image_url) }}
                            style={styles.modalThumb}
                          />
                        ) : (
                          <View style={styles.placeholderIconWrapper}>
                            <Ionicons name="cube-outline" size={18} color={Colors.textMuted} />
                          </View>
                        )}
                      </View>
                      <View style={[styles.modalTextWrapper, { alignItems: isAr ? 'flex-end' : 'flex-start' }]}>
                        <Text style={styles.modalItemName} numberOfLines={1}>{selectedProduct.name}</Text>
                        <Text style={styles.modalItemSub}>
                          {isAr 
                            ? `المخزون الحالي: ${selectedProduct.stock_count} قطع` 
                            : `Current Stock Count: ${selectedProduct.stock_count}`}
                        </Text>
                      </View>
                    </View>

                    {/* Incrementor Fields */}
                    <Text style={[styles.inputLabel, { textAlign: isAr ? 'right' : 'left' }]}>
                      {isAr ? 'الكمية المراد إضافتها للمخزون' : 'Add Stock Quantity'}
                    </Text>

                    <View style={[styles.adjusterRow, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
                      <TouchableOpacity style={styles.adjusterBtn} onPress={() => adjustReplenishQty(-5)} activeOpacity={0.7}>
                        <Text style={styles.adjusterBtnText}>-5</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.adjusterBtn} onPress={() => adjustReplenishQty(-1)} activeOpacity={0.7}>
                        <Ionicons name="remove" size={20} color={Colors.textPrimary} />
                      </TouchableOpacity>
                      <TextInput
                        style={styles.adjusterInput}
                        keyboardType="number-pad"
                        value={replenishCount}
                        onChangeText={setReplenishCount}
                        textAlign="center"
                      />
                      <TouchableOpacity style={styles.adjusterBtn} onPress={() => adjustReplenishQty(1)} activeOpacity={0.7}>
                        <Ionicons name="add" size={20} color={Colors.textPrimary} />
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.adjusterBtn} onPress={() => adjustReplenishQty(5)} activeOpacity={0.7}>
                        <Text style={styles.adjusterBtnText}>+5</Text>
                      </TouchableOpacity>
                    </View>

                    {/* Action buttons */}
                    <View style={styles.modalActions}>
                      <TouchableOpacity
                        style={[styles.modalBtn, styles.modalBtnCancel]}
                        onPress={() => { setReplenishModalVisible(false); setSelectedProduct(null); }}
                        disabled={savingReplenish}
                      >
                        <Text style={styles.modalBtnTextCancel}>{isAr ? 'إلغاء' : 'Cancel'}</Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={[styles.modalBtn, styles.modalBtnSave]}
                        onPress={handleSaveReplenish}
                        disabled={savingReplenish}
                      >
                        {savingReplenish ? (
                          <ActivityIndicator color={Colors.textOnPrimary} />
                        ) : (
                          <>
                            <Ionicons name="cube-outline" size={16} color="#FFF" style={{ marginRight: 6 }} />
                            <Text style={styles.modalBtnTextSave}>{isAr ? 'تأكيد الشحن' : 'Replenish'}</Text>
                          </>
                        )}
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
              </View>
            </TouchableWithoutFeedback>
          </KeyboardAvoidingView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}