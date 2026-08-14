/**
 * Merchant Profile Screen — Account info, market details, settings, and logout.
 * Premium dark UI with mint/green accent to distinguish from customer profile.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Alert, ScrollView, ActivityIndicator,
  Modal, Switch, RefreshControl
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import {
  getUser, getMyMarket, logout, MarketResponse,
  getInventoryValue, getCheckoutHistory, getMarketItems, updateMarketStatus,
  HistoricalReceipt
} from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n, toggleLanguage } from '../../services/i18n';
import { formatPrice } from '../../services/currency';
import ThemePreferenceRow from '../../components/ThemePreferenceRow';
import Constants from 'expo-constants';

export default function MerchantProfileScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const [user, setUser] = useState<any>(null);
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [loadingMarket, setLoadingMarket] = useState(true);
  const isAr = i18n.locale.includes('ar');

  // Relocated Analytics & Status States
  const [analyticsVisible, setAnalyticsVisible] = useState(false);
  const [totalAssetsValue, setTotalAssetsValue] = useState<number>(0);
  const [historyReceipts, setHistoryReceipts] = useState<HistoricalReceipt[]>([]);
  const [totalProducts, setTotalProducts] = useState<number>(0);
  const [inStockCount, setInStockCount] = useState<number>(0);
  const [loadingStats, setLoadingStats] = useState(false);
  const [refreshingStats, setRefreshingStats] = useState(false);

  const loadAnalyticsData = useCallback(async () => {
    try {
      setLoadingStats(true);
      const freshMarket = await getMyMarket();
      setMarket(freshMarket);

      try {
        const valResp = await getInventoryValue();
        setTotalAssetsValue(valResp.total_value);
      } catch (valErr) {
        console.warn('Failed to load inventory valuation in profile:', valErr);
      }

      try {
        const historyData = await getCheckoutHistory();
        setHistoryReceipts(historyData);
      } catch (histErr) {
        console.warn('Failed to load transaction history in profile:', histErr);
      }

      try {
        const items = await getMarketItems();
        setTotalProducts(items.length);
        setInStockCount(items.filter((p: any) => p.in_stock).length);
      } catch (itemsErr) {
        console.warn('Failed to load products list count in profile:', itemsErr);
      }
    } catch (err) {
      console.warn('Failed to load analytics in profile:', err);
    } finally {
      setLoadingStats(false);
      setRefreshingStats(false);
    }
  }, []);

  useEffect(() => {
    if (analyticsVisible) {
      loadAnalyticsData();
    }
  }, [analyticsVisible, loadAnalyticsData]);

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

  useEffect(() => {
    (async () => {
      try {
        const userData = await getUser();
        setUser(userData);
      } catch (err) {
        console.error('Failed to get user data:', err);
      }

      try {
        const marketData = await getMyMarket();
        setMarket(marketData);
      } catch {
        // No market set up yet
      } finally {
        setLoadingMarket(false);
      }
    })();
  }, []);

  const handleLogout = () => {
    Alert.alert(
      t('profile.logout_title'),
      t('profile.logout_confirm'),
      [
        { text: t('common.cancel'), style: 'cancel' },
        {
          text: t('profile.logout'),
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/(auth)/gateway');
          },
        },
      ],
    );
  };

  const displayName = user?.name || user?.email || user?.phone_number || (isAr ? 'التاجر' : 'Merchant');
  const initials = displayName.charAt(0).toUpperCase();

  const appVersion = Constants.expoConfig?.version || '1.0.0';

  const styles = useMemo(() => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scroll: {
    paddingHorizontal: Spacing.xl,
    paddingBottom: 140,
  },
  backToShoppingBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: Colors.primary,
    marginTop: Spacing.lg,
    marginBottom: Spacing.xs,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 18,
    ...Shadows.small,
  },
  backToShoppingInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  backToShoppingBannerText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  menuDivider: {
    height: 1,
    backgroundColor: Colors.border,
    marginVertical: Spacing.xs,
    opacity: 0.5,
  },
  modalContainer: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  modalScroll: {
    paddingBottom: Spacing.xxxl,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.lg,
    borderBottomWidth: 1,
    borderColor: Colors.border,
    marginBottom: Spacing.xl,
  },
  modalTitle: {
    ...Typography.h2,
    color: Colors.textPrimary,
  },
  modalCloseBtn: {
    padding: Spacing.xs,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: Spacing.md,
  },
  loadingText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
  },
  statusCardContainer: {
    backgroundColor: Colors.surfaceGlass,
    borderRadius: BorderRadius.xl,
    padding: Spacing.lg,
    marginHorizontal: Spacing.xl,
    marginBottom: Spacing.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.medium,
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
    borderRadius: BorderRadius.md,
    padding: 2,
    gap: 2,
  },
  segmentBtn: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    borderRadius: BorderRadius.md - 2,
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
  assetsGlowCard: {
    marginHorizontal: Spacing.xl,
    marginBottom: Spacing.lg,
    borderRadius: BorderRadius.xl,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(108, 99, 255, 0.25)',
    backgroundColor: Colors.surfaceElevated,
    ...Shadows.medium,
  },
  assetsGlowInner: {
    padding: Spacing.lg,
    alignItems: 'center',
    gap: Spacing.md,
  },
  assetsIconWrapper: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: 'rgba(108, 99, 255, 0.12)',
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
  lowStockWarningCard: {
    marginHorizontal: Spacing.xl,
    marginBottom: Spacing.lg,
    borderRadius: BorderRadius.xl,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255, 77, 106, 0.35)',
    backgroundColor: 'rgba(255, 77, 106, 0.06)',
    ...Shadows.medium,
  },
  lowStockInner: {
    padding: Spacing.lg,
    alignItems: 'center',
    gap: Spacing.md,
  },
  lowStockIconWrapper: {
    width: 46,
    height: 46,
    borderRadius: 23,
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
  lowStockSubText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontWeight: '500',
    marginTop: 2,
  },
  analyticsCard: {
    marginHorizontal: Spacing.xl,
    marginBottom: Spacing.lg,
    borderRadius: BorderRadius.xl,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.surface,
    padding: Spacing.lg,
    ...Shadows.medium,
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
    borderRadius: BorderRadius.md,
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
  statsRow: {
    flexDirection: 'row',
    paddingHorizontal: Spacing.xl,
    gap: Spacing.sm,
    marginBottom: Spacing.lg,
  },
  statCard: {
    flex: 1,
    backgroundColor: Colors.surfaceGlass,
    borderRadius: BorderRadius.xl,
    paddingVertical: Spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.small,
  },
  statNumber: {
    ...Typography.h2,
    color: Colors.textPrimary,
  },
  statLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
  },
  header: {
    paddingVertical: Spacing.lg,
  },
  headerTitle: {
    fontSize: 32,
    fontWeight: '700',
    color: Colors.textPrimary,
  },

  // Profile Card
  profileCard: {
    backgroundColor: Colors.surfaceGlass,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
    marginBottom: Spacing.lg,
    ...Shadows.medium,
  },
  avatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.md,
    shadowColor: Colors.secondary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 20,
    elevation: 8,
  },
  avatarText: {
    fontSize: 28,
    fontWeight: '700',
    color: Colors.textOnPrimary,
  },
  displayName: {
    ...Typography.h3,
    color: Colors.textPrimary,
    marginBottom: Spacing.sm,
  },
  roleBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.full,
    backgroundColor: 'rgba(0, 217, 166, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(0, 217, 166, 0.2)',
    marginBottom: Spacing.sm,
  },
  roleBadgeText: {
    ...Typography.caption,
    color: Colors.secondary,
    fontWeight: '700',
  },
  memberSince: {
    ...Typography.caption,
    color: Colors.textMuted,
  },

  // Sections
  sectionCard: {
    backgroundColor: Colors.surfaceGlass,
    borderRadius: BorderRadius.xl,
    padding: Spacing.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    marginBottom: Spacing.lg,
  },
  sectionTitle: {
    ...Typography.label,
    color: Colors.textMuted,
    textTransform: 'uppercase',
    marginBottom: Spacing.md,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.md,
    gap: Spacing.md,
  },
  menuIcon: {
    width: 40,
    height: 40,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  menuContent: {
    flex: 1,
  },
  menuLabel: {
    ...Typography.body,
    color: Colors.textPrimary,
    fontWeight: '500',
  },
  menuValue: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
    marginTop: 1,
  },
  loadingRow: {
    paddingVertical: Spacing.lg,
    alignItems: 'center',
  },
  setupButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.lg,
    backgroundColor: 'rgba(0, 217, 166, 0.06)',
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: 'rgba(0, 217, 166, 0.15)',
    borderStyle: 'dashed',
  },
  setupText: {
    ...Typography.button,
    color: Colors.secondary,
  },

  // Logout
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.lg,
    backgroundColor: 'rgba(255, 77, 106, 0.06)',
    borderRadius: BorderRadius.xl,
    borderWidth: 1,
    borderColor: 'rgba(255, 77, 106, 0.15)',
    marginBottom: Spacing.lg,
  },
  logoutText: {
    ...Typography.button,
    color: Colors.error,
  },
  footer: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
  },
}), [Colors]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>{t('profile.title', 'حسابي')}</Text>
        </View>

        {/* Profile Card */}
        <View style={styles.profileCard}>
          <LinearGradient
            colors={[Colors.secondary, '#33E4BC']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.avatar}
          >
            <Text style={styles.avatarText}>{initials}</Text>
          </LinearGradient>

          <Text style={styles.displayName}>{displayName}</Text>

          <View style={styles.roleBadge}>
            <Ionicons name="storefront-outline" size={14} color={Colors.secondary} />
            <Text style={styles.roleBadgeText}>
              {t('merchant.seller_account', 'حساب البائع')}
            </Text>
          </View>

          {user?.created_at && (
            <Text style={styles.memberSince}>
              {t('profile.member_since', 'عضو منذ')}{' '}
              {new Date(user.created_at).toLocaleDateString(isAr ? 'ar-EG' : undefined)}
            </Text>
          )}
        </View>

        {/* Back to Shopping Banner (under Account card, matching Customer profile style) */}
        <TouchableOpacity
          onPress={() => router.replace('/(customer)/search')}
          style={styles.backToShoppingBanner}
          activeOpacity={0.85}
        >
          <Ionicons name={isAr ? "chevron-back" : "chevron-forward"} size={20} color="#FFF" />
          <View style={styles.backToShoppingInner}>
            <Text style={styles.backToShoppingBannerText}>
              {t('merchant.back_to_shopping', 'العودة للتسوق')}
            </Text>
            <Ionicons name="cart" size={20} color="#FFF" />
          </View>
        </TouchableOpacity>

        {/* Market Info Card */}
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>{t('merchant.my_store', 'متجري')}</Text>

          {loadingMarket ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator size="small" color={Colors.secondary} />
            </View>
          ) : market ? (
            <>
              <View style={styles.menuItem}>
                <View style={[styles.menuIcon, { backgroundColor: 'rgba(0, 217, 166, 0.1)' }]}>
                  <Ionicons name="storefront" size={20} color={Colors.secondary} />
                </View>
                <View style={styles.menuContent}>
                  <Text style={styles.menuLabel}>{market.name}</Text>
                  <Text style={styles.menuValue}>{market.address}</Text>
                </View>
              </View>
              <View style={styles.menuItem}>
                <View style={[styles.menuIcon, { backgroundColor: 'rgba(108, 99, 255, 0.1)' }]}>
                  <Ionicons name="location" size={20} color={Colors.primary} />
                </View>
                <View style={styles.menuContent}>
                  <Text style={styles.menuLabel}>{t('merchant.coordinates', 'الإحداثيات')}</Text>
                  <Text style={styles.menuValue}>
                    {market.latitude.toFixed(4)}, {market.longitude.toFixed(4)}
                  </Text>
                </View>
              </View>

              <View style={styles.menuDivider} />

              <TouchableOpacity
                style={styles.menuItem}
                onPress={() => setAnalyticsVisible(true)}
                activeOpacity={0.7}
                accessibilityRole="button"
                accessibilityLabel={t('merchant.analytics_status', 'إحصائيات وحالة المتجر')}
              >
                <View style={[styles.menuIcon, { backgroundColor: 'rgba(0, 217, 166, 0.1)' }]}>
                  <Ionicons name="bar-chart-outline" size={20} color={Colors.secondary} />
                </View>
                <View style={styles.menuContent}>
                  <Text style={styles.menuLabel}>{t('merchant.analytics_status', 'إحصائيات وحالة المتجر')}</Text>
                  <Text style={styles.menuValue}>
                    {t('merchant.analytics_desc', 'تتبع المبيعات وقيمة المخزون وحالة المتجر')}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
              </TouchableOpacity>
            </>
          ) : (
            <TouchableOpacity
              style={styles.setupButton}
              onPress={() => router.push('/(merchant)/onboarding')}
              activeOpacity={0.8}
            >
              <Ionicons name="add-circle-outline" size={20} color={Colors.secondary} />
              <Text style={styles.setupText}>
                {t('onboarding.title', 'إعداد المتجر')}
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Settings Section */}
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>{t('profile.preferences', 'التفضيلات')}</Text>

          <TouchableOpacity style={styles.menuItem} onPress={toggleLanguage} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(108, 99, 255, 0.1)' }]}>
              <Ionicons name="language" size={20} color={Colors.primary} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.language', 'اللغة')}</Text>
              <Text style={styles.menuValue}>{t('profile.language_name', 'العربية')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.menuItem} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(0, 217, 166, 0.1)' }]}>
              <Ionicons name="notifications-outline" size={20} color={Colors.secondary} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.notifications', 'الإشعارات')}</Text>
              <Text style={styles.menuValue}>{t('profile.enabled', 'مفعّل')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Appearance — theme picker */}
        <ThemePreferenceRow />

        {/* About */}
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>{t('profile.about', 'حول التطبيق')}</Text>

          <View style={styles.menuItem}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(255, 107, 157, 0.1)' }]}>
              <Ionicons name="information-circle-outline" size={20} color={Colors.accent} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.version', 'الإصدار')}</Text>
              <Text style={styles.menuValue}>{appVersion}</Text>
            </View>
          </View>
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout} activeOpacity={0.8}>
          <Ionicons name="log-out-outline" size={20} color={Colors.error} />
          <Text style={styles.logoutText}>{t('profile.logout', 'تسجيل الخروج')}</Text>
        </TouchableOpacity>

        <Text style={styles.footer}>Lamba v{appVersion} • {t('profile.tagline', 'آمن ومحلي للغاية')}</Text>
      </ScrollView>

      {/* Analytics & Store Status Modal */}
      <Modal
        visible={analyticsVisible}
        animationType="slide"
        onRequestClose={() => setAnalyticsVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer} edges={['top']}>
          {/* Modal Header */}
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{t('merchant.analytics_status', 'Store Analytics & Status')}</Text>
            <TouchableOpacity 
              onPress={() => setAnalyticsVisible(false)}
              style={styles.modalCloseBtn}
            >
              <Ionicons name="close" size={24} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>

          {loadingStats && !refreshingStats ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={Colors.secondary} />
              <Text style={styles.loadingText}>{t('common.loading', 'Loading analytics...')}</Text>
            </View>
          ) : (
            <ScrollView
              contentContainerStyle={styles.modalScroll}
              refreshControl={
                <RefreshControl
                  refreshing={refreshingStats}
                  onRefresh={() => {
                    setRefreshingStats(true);
                    loadAnalyticsData();
                  }}
                  tintColor={Colors.secondary}
                />
              }
            >
              {/* Store Status Control Card */}
              {market && (
                <View style={styles.statusCardContainer}>
                  <View style={styles.statusCardHeader}>
                    <View style={styles.statusCardTitleRow}>
                      <View style={[styles.statusDot, { backgroundColor: market.is_currently_open ? Colors.success : Colors.error }]} />
                      <Text style={styles.statusCardTitle}>
                        {t('common.store_status')}: <Text style={[styles.statusCardValue, { color: market.is_currently_open ? Colors.success : Colors.error }]}>
                          {market.is_currently_open ? t('common.open') : t('common.closed')}
                        </Text>
                      </Text>
                    </View>
                    <Text style={styles.statusCardSubtitle}>
                      {market.is_manual_override ? t('common.manual_override') : t('common.automatic_schedule')}
                    </Text>
                  </View>

                  {/* Mode Selector Segmented Control */}
                  <View style={styles.segmentedContainer}>
                    <TouchableOpacity
                      style={[styles.segmentBtn, !market.is_manual_override && styles.segmentBtnActive]}
                      onPress={async () => {
                        try {
                          const updated = await updateMarketStatus(null, false);
                          setMarket(updated);
                        } catch (err) {
                          Alert.alert(t('common.error'), isAr ? 'فشل تحويل المتجر إلى الوضع التلقائي' : 'Failed to set store to automatic mode');
                        }
                      }}
                    >
                      <Text style={[styles.segmentText, !market.is_manual_override && styles.segmentTextActive]}>
                        {t('common.automatic_schedule')}
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.segmentBtn, market.is_manual_override && styles.segmentBtnActive]}
                      onPress={async () => {
                        try {
                          const updated = await updateMarketStatus(market.is_currently_open, true);
                          setMarket(updated);
                        } catch (err) {
                          Alert.alert(t('common.error'), isAr ? 'فشل تحويل المتجر إلى وضع التجاوز اليدوي' : 'Failed to set store to manual override mode');
                        }
                      }}
                    >
                      <Text style={[styles.segmentText, market.is_manual_override && styles.segmentTextActive]}>
                        {t('common.manual_override')}
                      </Text>
                    </TouchableOpacity>
                  </View>

                  {/* Manual Switch */}
                  {market.is_manual_override && (
                    <View style={styles.manualSwitchRow}>
                      <Text style={styles.manualSwitchLabel}>{t('common.reverts_at_midnight')}</Text>
                      <Switch
                        value={market.is_currently_open}
                        onValueChange={async (value) => {
                          try {
                            const updated = await updateMarketStatus(value, true);
                            setMarket(updated);
                          } catch (err) {
                            Alert.alert(t('common.error'), isAr ? 'فشل تغيير حالة المتجر' : 'Failed to override store status');
                          }
                        }}
                        trackColor={{ false: '#444466', true: Colors.primaryDark }}
                        thumbColor={market.is_currently_open ? Colors.success : Colors.textMuted}
                      />
                    </View>
                  )}
                </View>
              )}

              {/* Inventory Assets Value Glow Card */}
              {market && (
                <View style={styles.assetsGlowCard}>
                  <View style={styles.assetsGlowInner}>
                    <View style={styles.assetsIconWrapper}>
                      <Ionicons name="calculator-outline" size={22} color={Colors.primary} />
                    </View>
                    <View style={styles.assetsTextWrapper}>
                      <Text style={styles.assetsLabel}>{t('dashboard.inventory_value', 'إجمالي قيمة أصول المخزون')}</Text>
                      <Text style={styles.assetsValue}>
                        {formatPrice(totalAssetsValue)}
                      </Text>
                    </View>
                  </View>
                </View>
              )}

              {/* Sales Performance Card */}
              {market && (
                <View style={styles.analyticsCard}>
                  <View style={styles.analyticsHeader}>
                    <Ionicons name="trending-up-outline" size={20} color={Colors.secondary} />
                    <Text style={styles.analyticsTitle}>
                      {t('dashboard.sales_performance', 'أداء المبيعات والتحليلات اليومية')}
                    </Text>
                  </View>
                  
                  <View style={styles.analyticsDivider} />

                  <View style={styles.trendRows}>
                    {/* Daily Trend */}
                    <View style={styles.trendRow}>
                      <View style={styles.trendLabelCol}>
                        <Text style={styles.trendLabel}>{t('dashboard.todays_sales', 'مبيعات اليوم')}</Text>
                        <Text style={styles.trendVal}>{formatPrice(stats.todaySales)}</Text>
                      </View>
                      
                      <View style={[styles.trendBadge, stats.todaySales >= stats.yesterdaySales ? styles.trendBadgeUp : styles.trendBadgeDown]}>
                        <Ionicons 
                          name={stats.todaySales >= stats.yesterdaySales ? 'trending-up' : 'trending-down'} 
                          size={14} 
                          color={stats.todaySales >= stats.yesterdaySales ? Colors.success : Colors.error} 
                        />
                        <Text style={[styles.trendBadgeText, { color: stats.todaySales >= stats.yesterdaySales ? Colors.success : Colors.error }]}>
                          {stats.todaySales >= stats.yesterdaySales ? '+' : ''}{stats.dailyChange.toFixed(1)}%
                        </Text>
                      </View>
                    </View>

                    <View style={styles.trendRowDivider} />

                    {/* Weekly Trend */}
                    <View style={styles.trendRow}>
                      <View style={styles.trendLabelCol}>
                        <Text style={styles.trendLabel}>{t('dashboard.this_weeks_sales', 'مبيعات هذا الأسبوع')}</Text>
                        <Text style={styles.trendVal}>{formatPrice(stats.thisWeekSales)}</Text>
                      </View>
                      
                      <View style={[styles.trendBadge, stats.thisWeekSales >= stats.lastWeekSales ? styles.trendBadgeUp : styles.trendBadgeDown]}>
                        <Ionicons 
                          name={stats.thisWeekSales >= stats.lastWeekSales ? 'trending-up' : 'trending-down'} 
                          size={14} 
                          color={stats.thisWeekSales >= stats.lastWeekSales ? Colors.success : Colors.error} 
                        />
                        <Text style={[styles.trendBadgeText, { color: stats.thisWeekSales >= stats.lastWeekSales ? Colors.success : Colors.error }]}>
                          {stats.thisWeekSales >= stats.lastWeekSales ? '+' : ''}{stats.weeklyChange.toFixed(1)}%
                        </Text>
                      </View>
                    </View>
                  </View>

                  {/* Daily Dynamic Analysis Insights box */}
                  <View style={styles.insightsBox}>
                    <View style={styles.insightsHeaderRow}>
                      <Ionicons name="sparkles-outline" size={16} color={Colors.primary} />
                      <Text style={styles.insightsHeaderTitle}>
                        {t('dashboard.daily_summary_analysis', 'تحليل الملخص اليومي')}
                      </Text>
                    </View>
                    <Text style={styles.insightsBodyText}>
                      {stats.summaryAnalysis}
                    </Text>
                  </View>
                </View>
              )}

              {/* Stats Summary cards */}
              <View style={styles.statsRow}>
                <View style={styles.statCard}>
                  <Text style={[styles.statNumber, { color: Colors.secondary }]}>{market ? 1 : 0}</Text>
                  <Text style={styles.statLabel}>{t('dashboard.store_active', 'المتجر نشط')}</Text>
                </View>
                
                <View style={styles.statCard}>
                  <Text style={styles.statNumber}>{totalProducts}</Text>
                  <Text style={styles.statLabel}>{t('dashboard.catalog_items', 'عناصر الكتالوج')}</Text>
                </View>
                
                <View style={[styles.statCard, { borderColor: Colors.success }]}>
                  <Text style={[styles.statNumber, { color: Colors.success }]}>{inStockCount}</Text>
                  <Text style={styles.statLabel}>{t('dashboard.in_stock', 'متوفر')}</Text>
                </View>
              </View>

              {/* Deficiencies Warnings (Low Stock Button) */}
              <TouchableOpacity
                style={styles.lowStockWarningCard}
                onPress={() => {
                  setAnalyticsVisible(false);
                  router.push('/(merchant)/low-stock');
                }}
                activeOpacity={0.8}
              >
                <View style={styles.lowStockInner}>
                  <View style={styles.lowStockIconWrapper}>
                    <Ionicons name="warning-outline" size={22} color={Colors.error} />
                  </View>
                  <View style={styles.lowStockTextWrapper}>
                    <Text style={styles.lowStockLabel}>
                      {t('lowStock.title', 'تنبيهات نقص المخزون')}
                    </Text>
                    <Text style={styles.lowStockSubText}>
                      {t('merchant.low_stock_manage', 'اضغط لإدارة المنتجات التي أوشكت على النفاد')}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
                </View>
              </TouchableOpacity>

            </ScrollView>
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}