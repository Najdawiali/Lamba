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
  getMyMarket, getMarketItems, toggleItemStock, updateMarketItem, updateMarketStatus,
  getInventoryValue, getCheckoutHistory, logout, MarketResponse, MarketItemDashboardResponse,
  HistoricalReceipt
} from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, toggleLanguage, i18n } from '../../services/i18n';
import { resolveImageUrl } from '../../services/utils';
import { formatPrice, getCurrencyCode } from '../../services/currency';

export default function DashboardScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [products, setProducts] = useState<MarketItemDashboardResponse[]>([]);
  const [historyReceipts, setHistoryReceipts] = useState<HistoricalReceipt[]>([]);
  const [totalAssetsValue, setTotalAssetsValue] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

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

  const lastOpenState = React.useRef<boolean | null>(null);
  const lastOverrideState = React.useRef<boolean | null>(null);

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

  const bannerY = React.useRef(new Animated.Value(-150)).current;
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
      toValue: -150,
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

  useEffect(() => {
    if (market) {
      if (lastOpenState.current === null) {
        lastOpenState.current = market.is_currently_open;
        lastOverrideState.current = market.is_manual_override;
      }
    }
  }, [market]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const freshMarket = await getMyMarket();
        if (
          lastOpenState.current !== null &&
          freshMarket.is_currently_open !== lastOpenState.current &&
          !freshMarket.is_manual_override &&
          !lastOverrideState.current
        ) {
          const statusText = freshMarket.is_currently_open ? t('common.open') : t('common.closed');
          showNotification(
            'success',
            t('common.store_status'),
            `${t('common.status_updated_auto')} (${statusText})`
          );
        }
        
        lastOpenState.current = freshMarket.is_currently_open;
        lastOverrideState.current = freshMarket.is_manual_override;
        setMarket(freshMarket);
      } catch (err) {
        // Log background failures as a warning to avoid throwing full-screen developer crash overlays in Expo Go
        console.warn('Background status check failed:', err);
      }
    }, 15000);
    
    return () => clearInterval(interval);
  }, [showNotification]);

  const loadData = useCallback(async () => {
    try {
      // 1. Fetch Market profile (Ticket 2.1)
      const marketProfile = await getMyMarket();
      setMarket(marketProfile);
      
      // 2. Fetch market products (Ticket 2.2)
      const items = await getMarketItems();
      setProducts(items);

      // 3. Fetch inventory total assets value
      try {
        const valResp = await getInventoryValue();
        setTotalAssetsValue(valResp.total_value);
      } catch (valErr) {
        console.warn('Failed to load inventory valuation:', valErr);
      }

      // 4. Fetch checkout history for sales analytics
      try {
        const historyData = await getCheckoutHistory();
        setHistoryReceipts(historyData);
      } catch (histErr) {
        console.warn('Failed to load transaction history for stats:', histErr);
      }
    } catch (err: any) {
      if (err?.response?.status === 401) {
        console.warn('Failed to load merchant data due to 401 Unauthorized. Logging out.');
        try {
          await logout();
        } catch (logoutErr) {
          // ignore
        }
        router.replace('/(auth)/gateway');
        return;
      }
      
      console.warn('Failed to load merchant data:', err);
      // Redirection Hook: if 404 is received, merchant lacks store parameters!
      if (err?.response?.status === 404) {
        router.replace('/(merchant)/onboarding');
      } else {
        Alert.alert('Connection Error', 'Could not sync with local server. Swipe down to refresh.');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggleStock = async (itemId: string, currentStatus: boolean) => {
    try {
      await toggleItemStock(itemId, !currentStatus);
      
      // Update local array
      setProducts(prev => prev.map(p =>
        p.id === itemId ? { ...p, in_stock: !currentStatus } : p
      ));

      // Refresh inventory valuation
      try {
        const valResp = await getInventoryValue();
        setTotalAssetsValue(valResp.total_value);
      } catch (valErr) {
        console.warn('Failed to refresh inventory value:', valErr);
      }
    } catch (err) {
      Alert.alert(t('common.error'), 'Failed to toggle product stock status.');
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
      Alert.alert('Validation Error', 'Product name cannot be empty');
      return;
    }
    const stockVal = parseInt(editStock, 10);
    const priceVal = parseFloat(editPrice);
    if (isNaN(stockVal) || stockVal < 0) {
      Alert.alert('Validation Error', 'Please enter a valid stock count');
      return;
    }
    if (isNaN(priceVal) || priceVal < 0) {
      Alert.alert('Validation Error', 'Please enter a valid price');
      return;
    }
    setSavingEdit(true);
    try {
      const updated = await updateMarketItem(selectedProduct.id, {
        name: editName.trim(),
        stock_count: stockVal,
        price: priceVal,
      });
      setProducts(prev => prev.map(p => p.id === selectedProduct.id ? updated : p));
      setEditModalVisible(false);
      setSelectedProduct(null);
      Alert.alert('Success', 'Product updated successfully');

      // Refresh inventory valuation
      try {
        const valResp = await getInventoryValue();
        setTotalAssetsValue(valResp.total_value);
      } catch (valErr) {
        console.warn('Failed to refresh inventory value:', valErr);
      }
    } catch (err) {
      Alert.alert('Save Failed', 'Could not update item details. Please check connection and try again.');
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
        ? `اليوم، حققت مبيعات بقيمة ${todaySales.toFixed(2)} ر.س عبر ${todayTxCount} عمليات دفع كاشير (${trendText}). تم بيع إجمالي ${totalItemsSoldToday} قطع من المنتجات${topItemText}. يستمر المتجر في الأداء الجيد، ويرجى مراقبة مستويات المخزون للمنتجات النشطة.`
        : `Today you generated ${todaySales.toFixed(2)} SAR across ${todayTxCount} POS checkouts (${trendText}). A total of ${totalItemsSoldToday} units were sold${topItemText}. The store continues to track well; monitor stock counts for high-velocity items.`;
    } else {
      const yesterdayText = yesterdaySales > 0
        ? (isAr 
            ? `يوم أمس حققت مبيعات بقيمة ${yesterdaySales.toFixed(2)} ر.س.`
            : `Yesterday you generated ${yesterdaySales.toFixed(2)} SAR in transaction value.`)
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
  const lowStockCount = useMemo(() => products.filter(p => p.stock_count <= 10 && p.stock_count > 0).length, [products]);

  // Extract unique categories for filter chips
  const categories = useMemo(() => {
    const cats = new Set<string>();
    products.forEach(p => { if (p.category) cats.add(p.category); });
    return [t('dashboard.filter_all', 'All'), ...Array.from(cats)];
  }, [products]);

  // Filtered products by search and category
  const filteredProducts = useMemo(() => {
    let filtered = products;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(p => p.name.toLowerCase().includes(q) || (p.category && p.category.toLowerCase().includes(q)));
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
  greeting: { fontSize: 32, fontWeight: '700', color: Colors.textPrimary },
  subtitle: { fontSize: 14, color: Colors.textMuted, marginTop: 2 },

  // Stat Chips
  statChipsRow: {
    flexDirection: 'row', paddingHorizontal: Spacing.xl, gap: Spacing.sm, marginBottom: Spacing.lg,
  },
  statChip: {
    flex: 1, backgroundColor: Colors.surfaceElevated, borderRadius: 10,
    paddingVertical: Spacing.sm, paddingHorizontal: Spacing.md,
    alignItems: 'center', flexDirection: 'column', gap: 2,
  },
  statChipNumber: { fontSize: 20, fontWeight: '700', color: Colors.textPrimary },
  statChipLabel: { fontSize: 10, fontWeight: '600', color: Colors.textMuted, textTransform: 'uppercase' },

  // Search Bar
  searchContainer: { paddingHorizontal: Spacing.xl, marginBottom: Spacing.sm },
  searchBar: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.lg, height: 44, gap: Spacing.sm,
  },
  searchInput: { flex: 1, color: Colors.textPrimary, fontSize: 14 },

  // Filter Chips
  filterRow: { marginBottom: Spacing.md, height: 46 },
  filterRowContent: { paddingHorizontal: Spacing.xl, gap: Spacing.sm, alignItems: 'center', paddingVertical: 4 },
  filterChip: {
    backgroundColor: Colors.surfaceElevated, borderRadius: 20,
    paddingHorizontal: Spacing.lg, height: 36,
    justifyContent: 'center', alignItems: 'center',
  },
  filterChipActive: { backgroundColor: Colors.primary },
  filterChipText: { fontSize: 13, fontWeight: '600', color: Colors.textMuted },
  filterChipTextActive: { color: '#FFFFFF' },

  // Product List & Cards
  listContent: { paddingHorizontal: Spacing.xl, paddingBottom: 100 },
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
    marginRight: Spacing.lg,
  },
  productImage: { width: '100%', height: '100%' },
  placeholderIconWrapper: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  productInfo: { flex: 1, marginRight: Spacing.md },
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
    top: Platform.OS === 'ios' ? 60 : 30,
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
    marginLeft: Spacing.xs,
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
    borderColor: 'rgba(255, 77, 106, 0.35)',
    backgroundColor: 'rgba(255, 77, 106, 0.06)',
    ...Shadows.small,
  },
  lowStockInner: {
    padding: Spacing.md,
    alignItems: 'center',
    gap: Spacing.md,
  },
  lowStockIconWrapper: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255, 77, 106, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  lowStockTextWrapper: {
    flex: 1,
  },
  lowStockLabel: {
    ...Typography.caption,
    color: Colors.error,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  lowStockValue: {
    ...Typography.body,
    fontWeight: '800',
    color: Colors.textPrimary,
    marginTop: 2,
  },
  lowStockSubText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontWeight: '500',
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
          <View style={[styles.toastInner, styles[`toast_${notification.type}` as const], { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
            <View style={[styles.toastIconWrapper, { marginRight: isAr ? 0 : Spacing.md, marginLeft: isAr ? Spacing.md : 0 }]}>
              <Ionicons
                name={notification.type === 'success' ? 'checkmark-circle' : notification.type === 'error' ? 'alert-circle' : 'information-circle'}
                size={26}
                color={notification.type === 'success' ? Colors.success : notification.type === 'error' ? Colors.error : Colors.primary}
              />
            </View>
            <View style={styles.toastTextWrapper}>
              <Text style={[styles.toastTitle, { textAlign: isAr ? 'right' : 'left' }]}>{notification.title}</Text>
              <Text style={[styles.toastMessage, { textAlign: isAr ? 'right' : 'left' }]}>{notification.message}</Text>
            </View>
            <TouchableOpacity onPress={dismissNotification} style={styles.toastCloseBtn}>
              <Ionicons name="close" size={18} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>
        </Animated.View>
      )}

      {/* Header */}
      <View style={styles.header}>
        <Text style={[styles.greeting, { textAlign: isAr ? 'right' : 'left' }]} numberOfLines={1}>
          {market?.name || t('dashboard.title')}
        </Text>
        <Text style={[styles.subtitle, { textAlign: isAr ? 'right' : 'left' }]} numberOfLines={1}>
          {market?.address || t('dashboard.subtitle')}
        </Text>
      </View>

      {/* Stat Chips Row */}
      <View style={styles.statChipsRow}>
        <View style={styles.statChip}>
          <Ionicons name="cube-outline" size={16} color={Colors.secondary} />
          <Text style={styles.statChipNumber}>{totalProducts}</Text>
          <Text style={styles.statChipLabel}>{t('dashboard.total_items', 'Total Items')}</Text>
        </View>
        <View style={styles.statChip}>
          <Ionicons name="checkmark-circle-outline" size={16} color={Colors.secondary} />
          <Text style={styles.statChipNumber}>{inStockCount}</Text>
          <Text style={styles.statChipLabel}>{t('dashboard.in_stock', 'In Stock')}</Text>
        </View>
        <View style={styles.statChip}>
          <Ionicons name="warning-outline" size={16} color={Colors.warning} />
          <Text style={styles.statChipNumber}>{lowStockCount}</Text>
          <Text style={styles.statChipLabel}>{t('dashboard.low_stock', 'Low Stock')}</Text>
        </View>
      </View>

      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <View style={styles.searchBar}>
          <Ionicons name="search-outline" size={18} color={Colors.textMuted} />
          <TextInput
            style={styles.searchInput}
            placeholder={t('dashboard.search_placeholder', 'Search inventory…')}
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
      </View>

      {/* Category Filter Chips */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filterRow}
        contentContainerStyle={styles.filterRowContent}
      >
        {categories.map((cat) => (
          <TouchableOpacity
            key={cat}
            style={[
              styles.filterChip,
              activeCategory === cat && styles.filterChipActive,
            ]}
            onPress={() => setActiveCategory(cat)}
            activeOpacity={0.7}
          >
            <Text style={[
              styles.filterChipText,
              activeCategory === cat && styles.filterChipTextActive,
            ]}>
              {cat}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Product List */}
      <FlatList
        data={filteredProducts}
        keyExtractor={(item) => item.id}
        refreshControl={
          <RefreshControl 
            refreshing={refreshing} 
            onRefresh={() => { setRefreshing(true); loadData(); }}
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
              <Text style={styles.productName} numberOfLines={1}>{truncatedName}</Text>
              <Text style={styles.categoryLabel}>{item.category || t('common.general', 'General')}</Text>
              <Text style={styles.priceText}>{formatPrice(item.price)}</Text>
              <Text style={styles.stockCountText}>{t('dashboard.stock_label', 'Stock')}: {item.stock_count}</Text>
            </View>

            {/* In-Stock Status Control */}
            <View style={styles.stockControl}>
              <Text style={styles.stockToggleLabel}>{t('dashboard.in_stock')}</Text>
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
            <Text style={styles.emptyTitle}>{t('dashboard.no_products', "No stocked products in this market.")}</Text>
            <Text style={styles.emptyText}>{"Add or scan your first item to get started."}</Text>
          </View>
        }
      />

      {/* Edit Product Modal */}
      <Modal
        visible={editModalVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setEditModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={{ width: '100%' }}
          >
            <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
              <View style={styles.modalContent}>
                {/* Modal Header */}
                <View style={[styles.modalHeader, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
                  <Text style={styles.modalTitle}>{t('dashboard.edit_product', 'Edit Product Details')}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.md }}>
                    {keyboardVisible && (
                      <TouchableOpacity 
                        onPress={() => Keyboard.dismiss()} 
                        style={styles.keyboardDismissBtn}
                        activeOpacity={0.7}
                      >
                        <Ionicons name="keypad-outline" size={18} color={Colors.primary} />
                        <Text style={styles.keyboardDismissText}>{t('rating.done', 'Done')}</Text>
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity onPress={() => setEditModalVisible(false)}>
                      <Ionicons name="close" size={24} color={Colors.textPrimary} />
                    </TouchableOpacity>
                  </View>
                </View>

            {/* Inputs */}
            <Text style={styles.inputLabel}>{t('dashboard.product_name', 'Product Name')}</Text>
            <View style={styles.modalInputWrapper}>
              <TextInput
                style={styles.modalInput}
                placeholder={t('dashboard.product_name', 'Product Name')}
                placeholderTextColor={Colors.textMuted}
                value={editName}
                onChangeText={setEditName}
              />
            </View>

            <View style={styles.inputRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.inputLabel}>{t('dashboard.stock_count', 'Stock Count')}</Text>
                <View style={styles.modalInputWrapper}>
                  <TextInput
                    style={styles.modalInput}
                    placeholder={t('dashboard.stock_count', 'Stock Count')}
                    placeholderTextColor={Colors.textMuted}
                    value={editStock}
                    onChangeText={setEditStock}
                    keyboardType="number-pad"
                  />
                </View>
              </View>

              <View style={{ flex: 1 }}>
                <Text style={styles.inputLabel}>{t('dashboard.price_cost', 'Price/Cost (SAR)')}</Text>
                <View style={styles.modalInputWrapper}>
                  <TextInput
                    style={styles.modalInput}
                    placeholder={t('dashboard.price_cost', 'Price')}
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
                <Text style={styles.modalBtnTextCancel}>{t('common.cancel', 'Cancel')}</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.modalBtn, styles.modalBtnSave]}
                onPress={handleSaveEdit}
                disabled={savingEdit}
              >
                {savingEdit ? (
                  <ActivityIndicator color={Colors.textOnPrimary} />
                ) : (
                  <Text style={styles.modalBtnTextSave}>{t('dashboard.save_changes', 'Save Changes')}</Text>
                )}
              </TouchableOpacity>
            </View>
              </View>
            </TouchableWithoutFeedback>
          </KeyboardAvoidingView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}