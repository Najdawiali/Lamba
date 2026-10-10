/**
 * Upgraded Merchant Dashboard — Modern V1 inventory overview.
 * Integrates PostGIS store checking (redirection to onboarding)
 * and displays stocked catalog items with responsive toggles.
 */

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, Alert, Switch, RefreshControl, Image,
  Modal, TextInput, Animated, Platform, Keyboard, KeyboardAvoidingView, TouchableWithoutFeedback,
  ScrollView
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import {
  toggleItemStock, updateMarketItem, logout,
  MarketItemDashboardResponse,
} from '../../services/api';
import {
  useMarket, useMarketItems, useInventoryValue, useCheckoutHistory,
  useToggleStock, useUpdateItem, merchantKeys,
} from '../../hooks/useMerchant';
import { useQueryClient } from '@tanstack/react-query';
import { Spacing, BorderRadius, Typography, Shadows, TAB_BAR_OVERFLOW } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, toggleLanguage, i18n } from '../../services/i18n';
import { resolveImageUrl } from '../../services/utils';
import { formatPrice, getCurrencyCode } from '../../services/currency';
import { CATEGORY_AR_FALLBACK } from '../../constants/categories';

export default function DashboardScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const queryClient = useQueryClient();

  // ── Server State (replaces manual useState + useEffect + loadData) ──
  const {
    data: market,
    isLoading: marketLoading,
    error: marketError,
  } = useMarket({ refetchInterval: 15000 }); // replaces the 15s setInterval

  const { data: products = [], isLoading: itemsLoading } = useMarketItems();
  const { data: inventoryData } = useInventoryValue();
  const { data: historyReceipts = [] } = useCheckoutHistory();

  const totalAssetsValue = inventoryData?.total_value ?? 0;
  const loading = marketLoading || itemsLoading;
  const [refreshing, setRefreshing] = useState(false);

  const toggleStockMutation = useToggleStock();
  const updateItemMutation = useUpdateItem();

  // Navigate away on auth/setup errors
  useEffect(() => {
    if (!marketError) return;
    const status = (marketError as any)?.response?.status;
    // 401 is handled globally (renew, or end the session and go to login)
    if (status === 403) {
      logout().then(() => router.replace('/(auth)/login'));
    } else if (status === 404) {
      router.replace('/(merchant)/onboarding');
    }
  }, [marketError, router]);

  // Edit Product Modal States
  const [selectedProduct, setSelectedProduct] = useState<MarketItemDashboardResponse | null>(null);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editName, setEditName] = useState('');
  const [editStock, setEditStock] = useState('');
  const [editPrice, setEditPrice] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);

  // Search & Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');

  const isAr = i18n.locale?.startsWith('ar');

  // Custom Toast/Banner notification states
  interface NotificationState {
    visible: boolean;
    type: 'success' | 'info' | 'error';
    title: string;
    message: string;
  }
  const [notification, setNotification] = useState<NotificationState>({
    visible: false,
    type: 'success',
    title: '',
    message: '',
  });

  const bannerY = React.useRef(new Animated.Value(200)).current;
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null);

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

  const dismissNotification = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    Animated.timing(bannerY, {
      toValue: 200,
      duration: 300,
      useNativeDriver: true,
    }).start(() => {
      setNotification(prev => ({ ...prev, visible: false }));
    });
  }, [bannerY]);

  const showNotification = useCallback((type: 'success' | 'info' | 'error', title: string, message: string) => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setNotification({ visible: true, type, title, message });
    
    // Animate in
    Animated.spring(bannerY, {
      toValue: 0,
      useNativeDriver: true,
      tension: 40,
      friction: 8,
    }).start();

    // Auto dismiss after 6 seconds
    timeoutRef.current = setTimeout(() => {
      dismissNotification();
    }, 6000);
  }, [bannerY, dismissNotification]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  // Track store status changes for toast notifications
  const lastOpenState = React.useRef<boolean | null>(null);
  const lastOverrideState = React.useRef<boolean | null>(null);

  useEffect(() => {
    if (!market) return;
    if (lastOpenState.current === null) {
      // First load — just record state, don't notify
      lastOpenState.current = market.is_currently_open;
      lastOverrideState.current = market.is_manual_override;
      return;
    }
    if (
      market.is_currently_open !== lastOpenState.current &&
      !market.is_manual_override &&
      !lastOverrideState.current
    ) {
      const statusText = market.is_currently_open ? t('common.open') : t('common.closed');
      showNotification('success', t('common.store_status'), `${t('common.status_updated_auto')} (${statusText})`);
    }
    lastOpenState.current = market.is_currently_open;
    lastOverrideState.current = market.is_manual_override;
  }, [market, showNotification]);

  const handleToggleStock = async (itemId: string, currentStatus: boolean) => {
    const newStatus = !currentStatus;
    if (newStatus) {
      // Toggling ON → open edit modal so merchant enters real stock count
      Keyboard.dismiss();
      const product = products.find(p => p.id === itemId);
      if (product) {
        setTimeout(() => handleOpenEdit(product), 300);
      }
      return;
    }
    // Toggling OFF → set stock to 0
    try {
      await toggleStockMutation.mutateAsync({ itemId, inStock: false });
      await updateItemMutation.mutateAsync({ itemId, updates: { stock_count: 0 } });
    } catch (err) {
      Alert.alert(t('common.error'), isAr ? 'فشل تغيير حالة توفر المنتج بالمخزون.' : 'Failed to toggle product stock status.');
    }
  };

  const handleOpenEdit = (product: MarketItemDashboardResponse) => {
    setSelectedProduct(product);
    setEditName(product.name);
    setEditStock(product.stock_count.toString());
    setEditPrice(product.price != null ? product.price.toString() : '');
    setEditModalVisible(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedProduct) return;
    if (!editName.trim()) {
      Alert.alert(t('common.error'), isAr ? 'لا يمكن ترك اسم المنتج فارغاً' : 'Product name cannot be empty');
      return;
    }
    const stockVal = parseInt(editStock, 10);
    const priceVal = parseFloat(editPrice);
    if (isNaN(stockVal) || stockVal < 0) {
      Alert.alert(t('common.error'), isAr ? 'يرجى إدخال كمية مخزون صحيحة' : 'Please enter a valid stock count');
      return;
    }
    if (isNaN(priceVal) || priceVal < 0) {
      Alert.alert(t('common.error'), isAr ? 'يرجى إدخال سعر صحيح' : 'Please enter a valid price');
      return;
    }
    setSavingEdit(true);
    try {
      const updated = await updateItemMutation.mutateAsync({
        itemId: selectedProduct.id,
        updates: { name: editName.trim(), stock_count: stockVal, price: priceVal },
      });
      // If item was out of stock and we're setting a new count, toggle it back on
      if (!selectedProduct.in_stock && stockVal > 0) {
        await toggleStockMutation.mutateAsync({ itemId: selectedProduct.id, inStock: true });
      }
      setEditModalVisible(false);
      setSelectedProduct(null);
    } catch (err: any) {
      const detailMsg = err?.response?.data?.detail;
      Alert.alert(
        t('common.error'),
        detailMsg || (isAr ? 'تعذر حفظ تعديلات المنتج.' : 'Could not update item details.')
      );
    } finally {
      setSavingEdit(false);
    }
  };



  const stats = useMemo(() => {
    const todayStr = new Date().toISOString().substring(0, 10);
    
    const yesterdayDate = new Date();
    yesterdayDate.setDate(yesterdayDate.getDate() - 1);
    const yesterdayStr = yesterdayDate.toISOString().substring(0, 10);

    let todaySales = 0;
    let yesterdaySales = 0;
    let thisWeekSales = 0;
    let lastWeekSales = 0;

    let todayTxCount = 0;
    const todaySoldItems: Record<string, number> = {};

    const oneDayMs = 24 * 60 * 60 * 1000;
    const nowMs = new Date().getTime();

    historyReceipts.forEach(r => {
      const receiptDateStr = r.created_at.substring(0, 10);
      const receiptTime = new Date(r.created_at).getTime();
      const ageDays = (nowMs - receiptTime) / oneDayMs;

      if (receiptDateStr === todayStr) {
        todaySales += r.total_cost;
        todayTxCount += 1;
        r.items.forEach(item => {
          todaySoldItems[item.name] = (todaySoldItems[item.name] || 0) + item.quantity;
        });
      } else if (receiptDateStr === yesterdayStr) {
        yesterdaySales += r.total_cost;
      }

      if (ageDays <= 7) {
        thisWeekSales += r.total_cost;
      } else if (ageDays > 7 && ageDays <= 14) {
        lastWeekSales += r.total_cost;
      }
    });

    const dailyChange = yesterdaySales > 0 ? ((todaySales - yesterdaySales) / yesterdaySales) * 100 : 0;
    const weeklyChange = lastWeekSales > 0 ? ((thisWeekSales - lastWeekSales) / lastWeekSales) * 100 : 0;

    let topSellingItem = '';
    let topSellingQty = 0;
    Object.keys(todaySoldItems).forEach(name => {
      if (todaySoldItems[name] > topSellingQty) {
        topSellingQty = todaySoldItems[name];
        topSellingItem = name;
      }
    });

    const totalItemsSoldToday = Object.values(todaySoldItems).reduce((sum, qty) => sum + qty, 0);

    let summaryAnalysis = '';
    if (todayTxCount > 0) {
      const trendText = todaySales >= yesterdaySales 
        ? (yesterdaySales > 0 
            ? `${isAr ? 'بزيادة قدرها' : 'representing a'} ${dailyChange.toFixed(1)}% ${isAr ? 'عن يوم أمس' : 'increase compared to yesterday'}`
            : (isAr ? 'مع عدم وجود مبيعات مسجلة يوم أمس' : 'with zero sales recorded yesterday'))
        : `${isAr ? 'بانخفاض قدره' : 'representing a'} ${Math.abs(dailyChange).toFixed(1)}% ${isAr ? 'عن يوم أمس' : 'decrease compared to yesterday'}`;

      const topItemText = topSellingItem 
        ? `, ${isAr ? 'وكان المنتج الأكثر مبيعاً هو' : 'and your top-performing item was'} "${topSellingItem}" (${topSellingQty} ${isAr ? 'قطع' : 'units'})`
        : '';

      summaryAnalysis = isAr 
        ? `اليوم، حققت مبيعات بقيمة ${formatPrice(todaySales)} عبر ${todayTxCount} عمليات دفع كاشير (${trendText}). تم بيع إجمالي ${totalItemsSoldToday} قطع من المنتجات${topItemText}. يستمر المتجر في الأداء الجيد، ويرجى مراقبة مستويات المخزون للمنتجات النشطة.`
        : `Today you generated ${formatPrice(todaySales)} across ${todayTxCount} POS checkouts (${trendText}). A total of ${totalItemsSoldToday} units were sold${topItemText}. The store continues to track well; monitor stock counts for high-velocity items.`;
    } else {
      const yesterdayText = yesterdaySales > 0
        ? (isAr 
            ? `يوم أمس حققت مبيعات بقيمة ${formatPrice(yesterdaySales)}.`
            : `Yesterday you generated ${formatPrice(yesterdaySales)} in transaction value.`)
        : (isAr
            ? 'لم تسجل أي مبيعات يوم أمس أيضاً.'
            : 'No sales were recorded yesterday either.');

      summaryAnalysis = isAr
        ? `لم تقم بإجراء أي عمليات بيع كاشير اليوم حتى الآن. ${yesterdayText} ابدأ بمسح المنتجات في وضع الكاشير (POS) لتسجيل المبيعات تلقائياً وتحديث المخزون.`
        : `You have not processed any POS cashier transactions today. ${yesterdayText} Align barcodes in POS Cashier mode to register checkouts and auto-adjust inventory.`;
    }

    return {
      todaySales,
      yesterdaySales,
      thisWeekSales,
      lastWeekSales,
      dailyChange,
      weeklyChange,
      todayTxCount,
      totalItemsSoldToday,
      topSellingItem,
      summaryAnalysis
    };
  }, [historyReceipts, isAr]);

  const totalProducts = products.length;
  const inStockCount = useMemo(() => products.filter(p => p.in_stock).length, [products]);
  const lowStockCount = useMemo(() => products.filter(p => p.stock_count <= 10 || !p.in_stock).length, [products]);

  // Extract unique categories for filter chips
  const categories = useMemo(() => {
    const map = new Map<string, { name: string; name_ar?: string | null; name_en?: string | null }>();
    products.forEach(p => {
      if (p.category && !map.has(p.category)) {
        map.set(p.category, {
          name: p.category,
          name_ar: p.category_name_ar || CATEGORY_AR_FALLBACK[p.category] || p.category,
          name_en: p.category_name_en || p.category,
        });
      }
    });
    return [
      { name: 'All', name_ar: 'الكل', name_en: 'All' },
      ...Array.from(map.values()),
    ];
  }, [products]);

  // Filtered products by search and category
  const filteredProducts = useMemo(() => {
    let filtered = products;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(p =>
        p.name.toLowerCase().includes(q) ||
        (p.name_ar && p.name_ar.toLowerCase().includes(q)) ||
        (p.category && p.category.toLowerCase().includes(q)) ||
        (p.category_name_ar && p.category_name_ar.includes(searchQuery.trim()))
      );
    }
    if (activeCategory !== 'All' && activeCategory !== t('dashboard.filter_all', 'All')) {
      filtered = filtered.filter(p => p.category === activeCategory);
    }
    return filtered;
  }, [products, searchQuery, activeCategory]);

  const styles = useMemo(() => StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: {
    paddingHorizontal: Spacing.xl, paddingTop: Spacing.lg, paddingBottom: Spacing.sm,
  },
  headerTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTextCol: {
    flex: 1,
    alignItems: 'center',
  },
  emptyAddBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: Spacing.lg,
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.tabActive,
  },
  emptyAddBtnText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  fab: {
    position: 'absolute',
    bottom: 20,
    right: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: Colors.tabActive,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
  },
  greeting: { fontSize: 22, fontWeight: '700', color: Colors.textPrimary, textAlign: 'center' },
  subtitle: { fontSize: 14, color: Colors.textMuted, marginTop: 2, textAlign: 'center' },

  // Stat Chips
  statChipsRow: {
    flexDirection: 'row', paddingHorizontal: Spacing.xl, gap: Spacing.xs, marginBottom: Spacing.md,
  },
  statChip: {
    flex: 1, backgroundColor: Colors.surfaceElevated, borderRadius: 8,
    paddingVertical: Spacing.xs, paddingHorizontal: Spacing.sm,
    alignItems: 'center', flexDirection: 'column', gap: 1,
  },
  statChipNumber: { fontSize: 16, fontWeight: '700', color: Colors.textPrimary },
  statChipLabel: { fontSize: 9, fontWeight: '600', color: Colors.textMuted, textTransform: 'uppercase' },

  // Search Bar
  searchContainer: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    paddingHorizontal: Spacing.xl, marginBottom: Spacing.sm,
  },
  searchBar: {
    flex: 1, flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.lg, height: 44, gap: Spacing.sm,
  },
  searchScanBtn: {
    width: 44, height: 44, borderRadius: BorderRadius.md, backgroundColor: Colors.tabActive,
    justifyContent: 'center', alignItems: 'center',
  },
  searchInput: { flex: 1, color: Colors.textPrimary, fontSize: 14 },

  // Filter Chips
  filterRow: {
    marginBottom: Spacing.lg,
    marginTop: Spacing.xs,
    height: 48,
    overflow: 'visible',
  },
  filterRowContent: {
    paddingHorizontal: Spacing.xl,
    paddingEnd: Spacing.xxxl,
    gap: 0,
    alignItems: 'stretch',
  },
  filterChip: {
    paddingHorizontal: Spacing.xl,
    height: 48,
    justifyContent: 'center',
    alignItems: 'center',
    borderBottomWidth: 2.5,
    borderBottomColor: 'transparent',
  },
  filterChipActive: {
    borderBottomColor: Colors.primary,
  },
  filterChipText: {
    fontSize: 15,
    fontWeight: '400',
    color: Colors.textMuted,
  },
  filterChipTextActive: {
    color: Colors.textPrimary,
    fontWeight: '700',
  },

  // Product List & Cards
  listContent: { paddingHorizontal: Spacing.xl, paddingBottom: TAB_BAR_OVERFLOW },
  productRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surface, borderRadius: BorderRadius.lg,
    padding: Spacing.lg, marginBottom: Spacing.sm,
  },
  imageWrapper: {
    width: 80, height: 80,
    borderRadius: BorderRadius.sm,
    backgroundColor: '#1E2040',
    overflow: 'hidden',
    marginEnd: Spacing.lg,
  },
  productImage: { width: '100%', height: '100%' },
  placeholderIconWrapper: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  productInfo: { flex: 1, marginEnd: Spacing.md },
  productName: { fontSize: 17, fontWeight: '600', color: Colors.textPrimary },
  categoryLabel: { fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  stockCountText: { fontSize: 13, color: Colors.textSecondary, marginTop: 2 },
  stockControl: { alignItems: 'center' },
  stockToggleLabel: { fontSize: 12, color: Colors.textSecondary, marginBottom: 4 },

  // Empty State
  emptyContainer: { alignItems: 'center', paddingVertical: Spacing.xxxl },
  emptyIconCircle: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: '#2A2D4A', justifyContent: 'center', alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  emptyTitle: { fontSize: 18, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  emptyText: { fontSize: 14, color: Colors.textMuted, textAlign: 'center', paddingHorizontal: Spacing.xl },

  // Edit Modal Styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(10, 10, 26, 0.6)',
    justifyContent: 'flex-end',
  },
  modalBackdropDismiss: {
    flex: 1,
    width: '100%',
  },
  modalContent: {
    backgroundColor: Colors.surface,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    padding: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.border,
    borderBottomWidth: 0,
    ...Shadows.large,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.xl,
  },
  modalTitle: {
    ...Typography.h2,
    color: Colors.textPrimary,
  },
  inputLabel: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    fontWeight: '700',
    marginBottom: Spacing.xs,
  },
  modalInputWrapper: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.md,
    height: 50,
    justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  modalInput: {
    color: Colors.textPrimary,
    ...Typography.body,
  },
  inputRow: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginBottom: Spacing.lg,
  },
  modalActions: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginTop: Spacing.md,
    marginBottom: Spacing.lg,
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
  metaInfoRow: {
    flexDirection: 'column',
    gap: 2,
    alignItems: 'flex-start',
    marginTop: 6,
  },
  priceText: {
    ...Typography.caption,
    color: Colors.secondary,
    fontWeight: '700',
  },
  nameRowInline: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  editIcon: {
    marginTop: 2,
  },
  statusCardContainer: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginHorizontal: Spacing.lg,
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.small,
  },
  statusCardHeader: {
    marginBottom: Spacing.md,
  },
  statusCardTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  statusCardTitle: {
    ...Typography.body,
    color: Colors.textPrimary,
    fontWeight: '600',
  },
  statusCardValue: {
    fontWeight: '700',
  },
  statusCardSubtitle: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
  },
  segmentedContainer: {
    flexDirection: 'row',
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.sm,
    padding: 2,
    gap: 2,
  },
  segmentBtn: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    borderRadius: BorderRadius.sm - 2,
  },
  segmentBtnActive: {
    backgroundColor: Colors.surface,
    ...Shadows.small,
  },
  segmentText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontWeight: '600',
  },
  segmentTextActive: {
    color: Colors.primary,
    fontWeight: '700',
  },
  manualSwitchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: Spacing.md,
    paddingTop: Spacing.sm,
    borderTopWidth: 1,
    borderColor: Colors.border,
  },
  manualSwitchLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  toastContainer: {
    position: 'absolute',
    bottom: Platform.OS === 'ios' ? 110 : 90,
    left: Spacing.lg,
    right: Spacing.lg,
    zIndex: 9999,
  },
  toastInner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(18, 18, 42, 0.95)',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.medium,
  },
  toast_success: {
    borderColor: 'rgba(0, 217, 126, 0.4)',
  },
  toast_info: {
    borderColor: 'rgba(108, 99, 255, 0.4)',
  },
  toast_error: {
    borderColor: 'rgba(255, 77, 106, 0.4)',
  },
  toastIconWrapper: {
    // Dynamic margin in JSX handles RTL beautifully
  },
  toastTextWrapper: {
    flex: 1,
  },
  toastTitle: {
    ...Typography.label,
    color: Colors.textPrimary,
  },
  toastMessage: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    fontSize: 12,
    marginTop: 2,
  },
  toastCloseBtn: {
    marginStart: Spacing.xs,
    padding: Spacing.xs,
  },
  scannerIconButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(108, 99, 255, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(108, 99, 255, 0.3)',
    borderRadius: BorderRadius.xl,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    gap: 6,
    alignSelf: 'center',
  },
  scannerBtnText: {
    ...Typography.bodySmall,
    color: Colors.primary,
    fontWeight: '700',
  },
  assetsGlowCard: {
    marginHorizontal: Spacing.lg,
    marginBottom: Spacing.md,
    borderRadius: BorderRadius.md,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(108, 99, 255, 0.25)',
    backgroundColor: Colors.surfaceElevated,
    ...Shadows.small,
  },
  assetsGlowInner: {
    padding: Spacing.md,
    alignItems: 'center',
    gap: Spacing.md,
  },
  assetsIconWrapper: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(108, 99, 255, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  assetsTextWrapper: {
    flex: 1,
  },
  assetsLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  assetsValue: {
    ...Typography.h2,
    color: Colors.textPrimary,
    fontWeight: '800',
    marginTop: 2,
  },
  currencyLabel: {
    fontSize: 14,
    color: Colors.secondary,
    fontWeight: '700',
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
  lowStockWarningCard: {
    marginHorizontal: Spacing.lg,
    marginBottom: Spacing.md,
    borderRadius: BorderRadius.md,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: Colors.errorBorder,
    backgroundColor: Colors.surface,
    ...Shadows.small,
  },
  lowStockInner: {
    padding: Spacing.md,
    alignItems: 'center',
    gap: Spacing.md,
  },
  lowStockIconWrapper: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: Colors.errorBg,
    justifyContent: 'center',
    alignItems: 'center',
  },
  lowStockTextWrapper: {
    flex: 1,
  },
  lowStockLabel: {
    fontSize: 13,
    color: Colors.error,
    fontWeight: '700',
  },
  lowStockValue: {
    ...Typography.body,
    fontWeight: '800',
    color: Colors.textPrimary,
    marginTop: 2,
  },
  lowStockSubText: {
    fontSize: 12,
    color: Colors.textSecondary,
    fontWeight: '400',
  },
  analyticsCard: {
    marginHorizontal: Spacing.lg,
    marginBottom: Spacing.md,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.surface,
    padding: Spacing.md,
    ...Shadows.small,
  },
  analyticsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.sm,
  },
  analyticsTitle: {
    ...Typography.body,
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  analyticsDivider: {
    height: 1,
    backgroundColor: Colors.border,
    marginBottom: Spacing.md,
  },
  trendRows: {
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  trendRow: {
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  trendLabelCol: {
    flex: 1,
  },
  trendLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  trendVal: {
    ...Typography.body,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginTop: 2,
  },
  trendBadge: {
    borderRadius: BorderRadius.sm,
    paddingHorizontal: 8,
    paddingVertical: 4,
    alignItems: 'center',
    gap: 4,
    borderWidth: 1,
  },
  trendBadgeUp: {
    backgroundColor: 'rgba(0, 217, 126, 0.08)',
    borderColor: 'rgba(0, 217, 126, 0.25)',
  },
  trendBadgeDown: {
    backgroundColor: 'rgba(255, 77, 106, 0.08)',
    borderColor: 'rgba(255, 77, 106, 0.25)',
  },
  trendBadgeText: {
    fontSize: 11,
    fontWeight: '700',
  },
  trendRowDivider: {
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
  },
  insightsBox: {
    backgroundColor: 'rgba(108, 99, 255, 0.05)',
    borderRadius: BorderRadius.sm,
    borderWidth: 1,
    borderColor: 'rgba(108, 99, 255, 0.15)',
    padding: Spacing.md,
    marginTop: Spacing.xs,
  },
  insightsHeaderRow: {
    alignItems: 'center',
    gap: 6,
    marginBottom: 6,
  },
  insightsHeaderTitle: {
    fontSize: 10,
    fontWeight: '800',
    color: Colors.primary,
    letterSpacing: 0.5,
  },
  insightsBodyText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    lineHeight: 18,
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
      {/* Toast Notification Banner */}
      {notification.visible && (
        <Animated.View style={[
          styles.toastContainer,
          { transform: [{ translateY: bannerY }] }
        ]}>
          <View style={[styles.toastInner, styles[`toast_${notification.type}` as const]]}>
            <View style={styles.toastIconWrapper}>
              <Ionicons
                name={notification.type === 'success' ? 'checkmark-circle' : notification.type === 'error' ? 'alert-circle' : 'information-circle'}
                size={26}
                color={notification.type === 'success' ? Colors.success : notification.type === 'error' ? Colors.error : Colors.primary}
              />
            </View>
            <View style={styles.toastTextWrapper}>
              <Text style={styles.toastTitle}>{notification.title}</Text>
              <Text style={styles.toastMessage}>{notification.message}</Text>
            </View>
            <TouchableOpacity onPress={dismissNotification} style={styles.toastCloseBtn}>
              <Ionicons name="close" size={18} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>
        </Animated.View>
      )}

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerTopRow}>
          <View style={styles.headerTextCol}>
            <Text style={styles.greeting} numberOfLines={1}>
              {(isAr && market?.name_ar) ? market.name_ar : (market?.name || t('tabs.dashboard', 'المخزون'))}
            </Text>
            <Text style={styles.subtitle} numberOfLines={1}>
              {(isAr && market?.address_ar) ? market.address_ar : (market?.address || t('merchant.dashboard_subtitle', 'إدارة المخزون والمبيعات'))}
            </Text>
          </View>
        </View>
      </View>

      {/* Stat Chips Row */}
      <View style={styles.statChipsRow}>
        <View style={styles.statChip}>
          <Ionicons name="cube-outline" size={16} color={Colors.secondary} />
          <Text style={styles.statChipNumber}>{totalProducts}</Text>
          <Text style={styles.statChipLabel}>{t('dashboard.total_items', 'إجمالي العناصر')}</Text>
        </View>
        <View style={styles.statChip}>
          <Ionicons name="checkmark-circle-outline" size={16} color={Colors.secondary} />
          <Text style={styles.statChipNumber}>{inStockCount}</Text>
          <Text style={styles.statChipLabel}>{t('dashboard.in_stock', 'متوفر')}</Text>
        </View>
        <View style={styles.statChip}>
          <Ionicons name="warning-outline" size={16} color={Colors.warning} />
          <Text style={styles.statChipNumber}>{lowStockCount}</Text>
          <Text style={styles.statChipLabel}>{t('dashboard.low_stock', 'مخزون منخفض')}</Text>
        </View>
      </View>

      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <View style={styles.searchBar}>
          <Ionicons name="search-outline" size={18} color={Colors.textMuted} />
          <TextInput
            style={styles.searchInput}
            placeholder={t('dashboard.search_placeholder', 'بحث في المخزون...')}
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
        <TouchableOpacity
          style={styles.searchScanBtn}
          onPress={() => router.push({ pathname: '/(merchant)/scanner', params: { mode: 'inventory' } })}
          activeOpacity={0.8}
          accessibilityRole="button"
          accessibilityLabel={t('merchant.scan_barcode', 'مسح الباركود')}
        >
          <Ionicons name="barcode-outline" size={24} color="#FFFFFF" />
        </TouchableOpacity>
      </View>

      {/* Category Filter Chips */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filterRow}
        contentContainerStyle={styles.filterRowContent}
      >
        {categories.map((cat) => {
          const displayName = isAr
            ? (cat.name_ar || CATEGORY_AR_FALLBACK[cat.name] || cat.name)
            : (cat.name_en || cat.name);
          const isSelected = activeCategory === cat.name;
          return (
            <TouchableOpacity
              key={cat.name}
              style={[
                styles.filterChip,
                isSelected && styles.filterChipActive,
              ]}
              onPress={() => setActiveCategory(cat.name)}
              activeOpacity={0.7}
            >
              <Text style={[
                styles.filterChipText,
                isSelected && styles.filterChipTextActive,
              ]}>
                {displayName}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* Product List */}
      <FlatList
        data={filteredProducts}
        keyExtractor={(item) => item.id}
        refreshControl={
          <RefreshControl 
            refreshing={refreshing} 
            onRefresh={async () => {
              setRefreshing(true);
              await queryClient.invalidateQueries({ queryKey: ['merchant'] });
              setRefreshing(false);
            }}
            tintColor={Colors.secondary} 
          />
        }
        contentContainerStyle={styles.listContent}
        renderItem={({ item }) => {
          const truncatedName = item.name.length > 26 ? item.name.substring(0, 26) + '…' : item.name;
          return (
          <TouchableOpacity
            style={styles.productRow}
            onPress={() => handleOpenEdit(item)}
            activeOpacity={0.7}
          >
            {/* Product Image Thumbnail */}
            <View style={styles.imageWrapper}>
              {item.image_url ? (
                <Image
                  source={{ uri: resolveImageUrl(item.image_url) }}
                  style={styles.productImage}
                  resizeMode="cover"
                />
              ) : (
                <View style={styles.placeholderIconWrapper}>
                  <Ionicons name="cube-outline" size={28} color={Colors.textMuted} />
                </View>
              )}
            </View>

            {/* Product Metadata Info */}
            <View style={styles.productInfo}>
              <Text style={styles.productName} numberOfLines={1}>
                {isAr ? (item.name_ar || truncatedName) : (item.name_en || truncatedName)}
              </Text>
              <Text style={styles.categoryLabel}>
                {(isAr
                  ? (item.category_name_ar || CATEGORY_AR_FALLBACK[item.category || ''] || item.category)
                  : (item.category_name_en || item.category)) || t('common.general', 'عام')}
              </Text>
              <Text style={styles.priceText}>{formatPrice(item.price)}</Text>
              <Text style={styles.stockCountText}>{t('dashboard.stock_label', 'المخزون')}: {item.stock_count}</Text>
            </View>

            {/* In-Stock Status Control */}
            <View style={styles.stockControl}>
              <Text style={styles.stockToggleLabel}>{t('dashboard.in_stock', 'متوفر')}</Text>
              <Switch
                value={item.in_stock}
                onValueChange={() => handleToggleStock(item.id, item.in_stock)}
                trackColor={{ false: Colors.toggleInactive, true: Colors.toggleStockActive }}
                thumbColor={'#FFFFFF'}
              />
            </View>
          </TouchableOpacity>
          );
        }}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <View style={styles.emptyIconCircle}>
              <Ionicons name="cube-outline" size={28} color={Colors.textMuted} />
            </View>
            <Text style={styles.emptyTitle}>{t('dashboard.no_products', "لا توجد منتجات بالمخزون في هذا المتجر.")}</Text>
            <Text style={styles.emptyText}>{t('dashboard.empty_subtitle', "أضف أو امسح منتجك الأول للبدء.")}</Text>
            <TouchableOpacity
              style={styles.emptyAddBtn}
              onPress={() => router.push('/(merchant)/add-product')}
              activeOpacity={0.8}
            >
              <Ionicons name="add" size={20} color="#FFFFFF" />
              <Text style={styles.emptyAddBtnText}>{t('dashboard.add_product', 'إضافة منتج')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.scannerIconButton, { marginTop: Spacing.md }]}
              onPress={() => router.push({ pathname: '/(merchant)/scanner', params: { mode: 'inventory' } })}
              activeOpacity={0.8}
              accessibilityRole="button"
            >
              <Ionicons name="barcode-outline" size={20} color={Colors.primary} />
              <Text style={styles.scannerBtnText}>{t('merchant.scan_barcode', 'مسح الباركود')}</Text>
            </TouchableOpacity>
          </View>
        }
      />

      {/* Floating Add Product Button */}
      {products.length > 0 && (
        <TouchableOpacity
          style={styles.fab}
          onPress={() => router.push('/(merchant)/add-product')}
          activeOpacity={0.8}
        >
          <Ionicons name="add" size={28} color="#FFFFFF" />
        </TouchableOpacity>
      )}

      {/* Edit Product Modal */}
      <Modal
        visible={editModalVisible}
        transparent
        animationType="slide"
        statusBarTranslucent
        onRequestClose={() => setEditModalVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.modalOverlay}
        >
          <TouchableWithoutFeedback onPress={() => setEditModalVisible(false)}>
            <View style={styles.modalBackdropDismiss} />
          </TouchableWithoutFeedback>
          <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
            <ScrollView
              style={styles.modalContent}
              contentContainerStyle={{ paddingBottom: 40 }}
              bounces={false}
              keyboardShouldPersistTaps="handled"
            >
              {/* Modal Header */}
              <View style={styles.modalHeader}>
                <Text style={styles.modalTitle}>{t('dashboard.edit_product', 'تعديل تفاصيل المنتج')}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.md }}>
                  {keyboardVisible && (
                    <TouchableOpacity 
                      onPress={() => Keyboard.dismiss()} 
                      style={styles.keyboardDismissBtn}
                      activeOpacity={0.7}
                    >
                      <Ionicons name="keypad-outline" size={18} color={Colors.primary} />
                      <Text style={styles.keyboardDismissText}>{t('rating.done', 'تم')}</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity onPress={() => setEditModalVisible(false)}>
                    <Ionicons name="close" size={24} color={Colors.textPrimary} />
                  </TouchableOpacity>
                </View>
              </View>

              {/* Inputs */}
              <Text style={styles.inputLabel}>{t('dashboard.product_name', 'اسم المنتج')}</Text>
              <View style={styles.modalInputWrapper}>
                <TextInput
                  style={styles.modalInput}
                  placeholder={t('dashboard.product_name', 'اسم المنتج')}
                  placeholderTextColor={Colors.textMuted}
                  value={editName}
                  onChangeText={setEditName}
                />
              </View>

              <View style={styles.inputRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.inputLabel}>{t('dashboard.stock_count', 'كمية المخزون')}</Text>
                  <View style={styles.modalInputWrapper}>
                    <TextInput
                      style={styles.modalInput}
                      placeholder={t('dashboard.stock_count', 'كمية المخزون')}
                      placeholderTextColor={Colors.textMuted}
                      value={editStock}
                      onChangeText={setEditStock}
                      keyboardType="number-pad"
                    />
                  </View>
                </View>

                <View style={{ flex: 1 }}>
                  <Text style={styles.inputLabel}>{t('dashboard.price_cost', isAr ? 'السعر/التكلفة (دينار)' : 'Price/Cost (JOD)')}</Text>
                  <View style={styles.modalInputWrapper}>
                    <TextInput
                      style={styles.modalInput}
                      placeholder={t('dashboard.price_cost', isAr ? 'السعر/التكلفة (دينار)' : 'Price/Cost (JOD)')}
                      placeholderTextColor={Colors.textMuted}
                      value={editPrice}
                      onChangeText={setEditPrice}
                      keyboardType="decimal-pad"
                    />
                  </View>
                </View>
              </View>

              {/* Action Buttons */}
              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={[styles.modalBtn, styles.modalBtnCancel]}
                  onPress={() => setEditModalVisible(false)}
                  disabled={savingEdit}
                >
                  <Text style={styles.modalBtnTextCancel}>{t('common.cancel', 'إلغاء')}</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.modalBtn, styles.modalBtnSave]}
                  onPress={handleSaveEdit}
                  disabled={savingEdit}
                >
                  {savingEdit ? (
                    <ActivityIndicator color={Colors.textOnPrimary} />
                  ) : (
                    <Text style={styles.modalBtnTextSave}>{t('dashboard.save_changes', 'حفظ التغييرات')}</Text>
                  )}
                </TouchableOpacity>
              </View>
            </ScrollView>
          </TouchableWithoutFeedback>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}