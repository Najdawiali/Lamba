import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  RefreshControl,
  LayoutAnimation,
  Platform,
  UIManager,
  ScrollView
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { getCheckoutHistory, HistoricalReceipt, logout } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import { formatPrice } from '../../services/currency';

// Enable LayoutAnimation for smooth card expansion on Android
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export default function ReceiptHistoryScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const [receipts, setReceipts] = useState<HistoricalReceipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState('today');

  const isAr = i18n.locale?.startsWith('ar');

  const dateFilters = [
    { key: 'today', label: t('history.today', 'Today') },
    { key: 'week', label: t('history.this_week', 'This Week') },
    { key: 'month', label: t('history.this_month', 'This Month') },
    { key: 'all', label: t('history.all_time', 'All Time') },
  ];

  const fetchHistory = useCallback(async (showIndicator = true) => {
    if (showIndicator) setLoading(true);
    try {
      const data = await getCheckoutHistory();
      setReceipts(data);
    } catch (err: any) {
      if (err?.response?.status === 401) {
        console.warn('Failed to load transaction history due to 401 Unauthorized. Logging out.');
        try {
          await logout();
        } catch (logoutErr) {
          // ignore
        }
        router.replace('/(auth)/gateway');
        return;
      }

      console.warn('Failed to load transaction history:', err);
      Alert.alert(
        t('common.error', 'خطأ'),
        t('history.fetch_failed', 'فشل استرداد سجلات المعاملات.')
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchHistory(false);
  };

  const toggleExpand = (id: string) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    if (expandedId === id) {
      setExpandedId(null);
    } else {
      setExpandedId(id);
    }
  };

  // Aggregate Metrics over the 14-day frame
  const totalSalesVolume = receipts.reduce((sum, r) => sum + r.total_cost, 0);
  const totalTransactionsCount = receipts.length;
  const totalItemsSold = receipts.reduce(
    (sum, r) => sum + r.items.reduce((s, item) => s + item.quantity, 0),
    0
  );

  const formatDate = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString(i18n.locale || 'en', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return isoString;
    }
  };

  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString(i18n.locale || 'en', {
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return '';
    }
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
  metricsContainer: {
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    gap: Spacing.sm,
  },
  mainMetricCard: {
    backgroundColor: 'rgba(108, 99, 255, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(108, 99, 255, 0.2)',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    ...Shadows.small,
  },
  metricLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  metricValue: {
    ...Typography.h1,
    color: Colors.primary,
    fontWeight: '800',
    marginTop: 4,
  },
  metricCurrency: {
    fontSize: 18,
    color: Colors.secondary,
    fontWeight: '700',
  },
  subMetricsRow: {
    gap: Spacing.sm,
  },
  subMetricCard: {
    flex: 1,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    padding: Spacing.sm,
    alignItems: 'center',
    ...Shadows.small,
  },
  subMetricValue: {
    ...Typography.h3,
    color: Colors.textPrimary,
    fontWeight: '700',
  },
  subMetricLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
    fontSize: 10,
  },
  listContent: {
    paddingHorizontal: Spacing.lg,
    paddingBottom: 140,
  },
  receiptCard: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.sm,
    overflow: 'hidden',
    ...Shadows.small,
  },
  receiptHeaderRow: {
    padding: Spacing.md,
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  receiptSummary: {
    flex: 1,
  },
  receiptIdRow: {
    alignItems: 'center',
    gap: 8,
  },
  receiptIdLabel: {
    ...Typography.body,
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  timeBadge: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: BorderRadius.full,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  timeText: {
    fontSize: 10,
    fontWeight: '600',
    color: Colors.textSecondary,
  },
  receiptDate: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 4,
  },
  receiptTotalCol: {
    justifyContent: 'center',
  },
  receiptCostValue: {
    ...Typography.body,
    fontWeight: '700',
    color: Colors.secondary,
  },
  itemCountRow: {
    alignItems: 'center',
    marginTop: 2,
  },
  itemCountText: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
  receiptDetails: {
    paddingHorizontal: Spacing.md,
    paddingBottom: Spacing.md,
    backgroundColor: 'rgba(255, 255, 255, 0.01)',
  },
  divider: {
    height: 1,
    backgroundColor: Colors.border,
    marginBottom: Spacing.sm,
  },
  detailsSectionTitle: {
    ...Typography.caption,
    color: Colors.textMuted,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginBottom: Spacing.xs,
  },
  itemDetailRow: {
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.02)',
  },
  detailItemName: {
    ...Typography.bodySmall,
    color: Colors.textPrimary,
    fontWeight: '600',
  },
  detailItemSub: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
  },
  detailItemSubtotal: {
    ...Typography.bodySmall,
    color: Colors.textPrimary,
    fontWeight: '700',
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: Spacing.xxxl,
  },
  emptyIconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: Colors.surfaceElevated,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: Colors.textPrimary,
    marginBottom: Spacing.sm,
  },
  emptyDesc: {
    fontSize: 14,
    color: Colors.textSecondary,
    textAlign: 'center',
    paddingHorizontal: Spacing.xl,
    marginBottom: Spacing.xl,
  },
  emptyCta: {
    backgroundColor: Colors.secondary,
    borderRadius: BorderRadius.md,
    height: 48,
    width: 200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyCtaText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },

  // Date filter pills
  filterRow: { marginBottom: Spacing.md, maxHeight: 40 },
  filterRowContent: { paddingHorizontal: Spacing.lg, gap: Spacing.sm },
  filterPill: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 20,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    justifyContent: 'center',
  },
  filterPillActive: { backgroundColor: Colors.primary },
  filterPillText: { fontSize: 13, fontWeight: '600', color: Colors.textMuted },
  filterPillTextActive: { color: '#FFFFFF' },
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
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backBtn}
          onPress={() => router.back()}
          activeOpacity={0.7}
        >
          <Ionicons name="arrow-back" size={24} color={Colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {t('history.title')}
        </Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Metrics Banner */}
      <View style={styles.metricsContainer}>
        <View style={styles.mainMetricCard}>
          <Text style={styles.metricLabel}>
            {t('history.total_sales')}
          </Text>
          <Text style={styles.metricValue}>
            {formatPrice(totalSalesVolume)}
          </Text>
        </View>

        <View style={styles.subMetricsRow}>
          <View style={styles.subMetricCard}>
            <Ionicons name="receipt-outline" size={18} color={Colors.primary} style={{ marginBottom: 4 }} />
            <Text style={styles.subMetricValue}>{totalTransactionsCount}</Text>
            <Text style={styles.subMetricLabel}>
              {t('history.transactions')}
            </Text>
          </View>

          <View style={styles.subMetricCard}>
            <Ionicons name="cube-outline" size={18} color={Colors.secondary} style={{ marginBottom: 4 }} />
            <Text style={styles.subMetricValue}>{totalItemsSold}</Text>
            <Text style={styles.subMetricLabel}>
              {t('history.items_sold')}
            </Text>
          </View>
        </View>
      </View>

      {/* Date Filter Bar */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filterRow}
        contentContainerStyle={styles.filterRowContent}
      >
        {dateFilters.map((f) => (
          <TouchableOpacity
            key={f.key}
            style={[
              styles.filterPill,
              dateFilter === f.key && styles.filterPillActive,
            ]}
            onPress={() => setDateFilter(f.key)}
            activeOpacity={0.7}
          >
            <Text style={[
              styles.filterPillText,
              dateFilter === f.key && styles.filterPillTextActive,
            ]}>
              {f.label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Receipts Timeline */}
      <FlatList
        data={receipts}
        keyExtractor={item => item.id}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor={Colors.primary}
          />
        }
        contentContainerStyle={styles.listContent}
        renderItem={({ item }) => {
          const isExpanded = expandedId === item.id;
          return (
            <View style={styles.receiptCard}>
              <TouchableOpacity
                style={styles.receiptHeaderRow}
                onPress={() => toggleExpand(item.id)}
                activeOpacity={0.8}
              >
                <View style={styles.receiptSummary}>
                  <View style={styles.receiptIdRow}>
                    <Text style={styles.receiptIdLabel}>#{item.id.substring(0, 8).toUpperCase()}</Text>
                    <View style={styles.timeBadge}>
                      <Text style={styles.timeText}>{formatTime(item.created_at)}</Text>
                    </View>
                  </View>
                  <Text style={styles.receiptDate}>{formatDate(item.created_at)}</Text>
                </View>

                <View style={styles.receiptTotalCol}>
                  <Text style={styles.receiptCostValue}>{formatPrice(item.total_cost)}</Text>
                  <View style={styles.itemCountRow}>
                    <Text style={styles.itemCountText}>
                      {item.items.reduce((s, i) => s + i.quantity, 0)} {t('scanner.items')}
                    </Text>
                    <Ionicons
                      name={isExpanded ? 'chevron-up' : 'chevron-down'}
                      size={14}
                      color={Colors.textMuted}
                      style={{ marginLeft: 4, marginRight: 4 }}
                    />
                  </View>
                </View>
              </TouchableOpacity>

              {isExpanded && (
                <View style={styles.receiptDetails}>
                  <View style={styles.divider} />
                  <Text style={styles.detailsSectionTitle}>
                    {t('history.receipt')}
                  </Text>

                  {item.items.map((prod, idx) => (
                    <View
                      key={`${prod.name}-${idx}`}
                      style={styles.itemDetailRow}
                    >
                      <View style={{ flex: 2 }}>
                        <Text style={styles.detailItemName}>{prod.name}</Text>
                        <Text style={styles.detailItemSub}>
                          {formatPrice(prod.unit_price)} × {prod.quantity}
                        </Text>
                      </View>
                      <Text style={styles.detailItemSubtotal}>
                        {formatPrice(prod.subtotal)}
                      </Text>
                    </View>
                  ))}
                </View>
              )}
            </View>
          );
        }}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <View style={styles.emptyIconCircle}>
              <Ionicons name="receipt-outline" size={36} color={Colors.textMuted} />
            </View>
            <Text style={styles.emptyTitle}>
              {t('history.no_history', 'لا توجد مبيعات بعد')}
            </Text>
            <Text style={styles.emptyDesc}>
              {t('history.no_history_desc', 'أول عملية بيع ستظهر هنا.')}
            </Text>
            <TouchableOpacity
              style={styles.emptyCta}
              onPress={() => router.push('/(merchant)/scanner')}
              activeOpacity={0.8}
            >
              <Text style={styles.emptyCtaText}>{t('history.go_to_cashier', 'الذهاب إلى الكاشير')} {isAr ? '←' : '→'}</Text>
            </TouchableOpacity>
          </View>
        }
      />
    </SafeAreaView>
  );
}