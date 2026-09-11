/**
 * Customer Special Offers Discovery Screen
 * Displays hyper-local BOGO and Discount promotions sorted dynamically by score.
 * Features search, categories, offer type, and distance filters.
 */

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, TextInput, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, Image, Alert, ScrollView, RefreshControl
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import {
  getCustomerSpecialOffers, getCategories, CategoryNode,
  CustomerSpecialOfferResponse, CustomerOffersFilters
} from '../../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../../constants/theme';
import { useThemeColors } from '../../../context/ThemeContext';
import { t, i18n } from '../../../services/i18n';
import { getCurrencyCode, formatPrice } from '../../../services/currency';
import { resolveImageUrl, formatDistanceKm } from '../../../services/utils';
import { useLocation } from '../../../hooks/useLocation';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

export default function CustomerOffersScreen() {
  const Colors = useThemeColors();
  const styles = useMemo(() => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  warningBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.warning,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    gap: Spacing.sm,
  },
  warningText: {
    ...Typography.bodySmall,
    color: Colors.background,
    fontWeight: '700',
    flex: 1,
  },
  header: {
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
    backgroundColor: Colors.surface,
  },
  headerTitleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: {
    ...Typography.h1,
    color: Colors.textPrimary,
  },
  headerSubtitle: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  infoButton: {
    padding: 6,
  },
  infoBox: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginTop: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  infoBoxTitle: {
    ...Typography.label,
    color: Colors.primaryLight,
    marginBottom: Spacing.xs,
  },
  infoBoxBody: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    fontSize: 12,
    lineHeight: 16,
  },
  searchBarContainer: {
    flexDirection: 'row',
    marginVertical: Spacing.md,
    gap: Spacing.sm,
  },
  searchBox: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    height: 48,
    gap: Spacing.sm,
  },
  searchInput: {
    flex: 1,
    color: Colors.textPrimary,
    ...Typography.body,
  },
  filterButton: {
    width: 48,
    height: 48,
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  filterButtonActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primaryLight,
  },
  categoryScroll: {
    marginBottom: Spacing.md,
  },
  categoryScrollContent: {
    gap: Spacing.sm,
    paddingRight: Spacing.lg,
  },
  categoryPill: {
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  categoryPillActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primaryLight,
  },
  categoryPillText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontWeight: '600',
  },
  categoryPillTextActive: {
    color: Colors.textOnPrimary,
  },

  // Filters Tray Styling
  filtersTray: {
    backgroundColor: Colors.surfaceElevated,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
    padding: Spacing.lg,
    ...Shadows.medium,
  },
  trayTitle: {
    ...Typography.h3,
    color: Colors.textPrimary,
    marginBottom: Spacing.md,
  },
  trayLabel: {
    ...Typography.label,
    color: Colors.textSecondary,
    marginTop: Spacing.md,
    marginBottom: Spacing.sm,
  },
  trayPillsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
  },
  trayPill: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  trayPillActive: {
    backgroundColor: Colors.secondary,
    borderColor: Colors.secondaryLight,
  },
  trayPillText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontWeight: '600',
  },
  trayPillTextActive: {
    color: Colors.background,
    fontWeight: '700',
  },
  trayActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: Spacing.xl,
    gap: Spacing.md,
  },
  trayClearBtn: {
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
  },
  trayClearText: {
    ...Typography.button,
    color: Colors.textSecondary,
  },
  trayApplyBtn: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
  },
  trayApplyText: {
    ...Typography.button,
    color: Colors.textOnPrimary,
  },

  // Grid/Cards Styling
  listContent: {
    padding: Spacing.md,
    paddingBottom: Spacing.xxl,
  },
  columnWrapper: {
    justifyContent: 'space-between',
  },
  offerCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    width: '48.5%',
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
    ...Shadows.small,
  },
  cardBadge: {
    position: 'absolute',
    top: Spacing.sm,
    left: Spacing.sm,
    zIndex: 10,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: BorderRadius.full,
  },
  cardBadgeBogo: {
    backgroundColor: Colors.secondary,
  },
  cardBadgeDiscount: {
    backgroundColor: Colors.primary,
  },
  cardBadgeText: {
    ...Typography.caption,
    fontSize: 9,
    fontWeight: '800',
    marginLeft: 3,
  },
  cardBadgeTextBogo: {
    color: Colors.background,
  },
  cardBadgeTextDiscount: {
    color: Colors.textOnPrimary,
  },
  cardImage: {
    width: '100%',
    height: 120,
    backgroundColor: Colors.surfaceElevated,
  },
  cardInfo: {
    padding: Spacing.sm,
  },
  productName: {
    ...Typography.label,
    color: Colors.textPrimary,
  },
  categoryName: {
    ...Typography.caption,
    fontSize: 10,
    color: Colors.textMuted,
    marginTop: 1,
    textTransform: 'uppercase',
  },
  priceText: {
    ...Typography.h3,
    color: Colors.secondary,
  },
  originalPriceText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textDecorationLine: 'line-through',
  },
  descriptionText: {
    ...Typography.bodySmall,
    fontSize: 11,
    color: Colors.textSecondary,
    fontStyle: 'italic',
    marginTop: Spacing.xs,
  },
  cardDivider: {
    height: 1,
    backgroundColor: Colors.divider,
    marginVertical: Spacing.sm,
  },
  shopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  shopName: {
    ...Typography.bodySmall,
    fontSize: 12,
    color: Colors.textSecondary,
    flex: 1,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  metricPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0,217,166,0.1)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
    gap: 2,
  },
  metricText: {
    ...Typography.caption,
    fontSize: 10,
    color: Colors.secondaryLight,
    fontWeight: '600',
  },
  scorePill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,181,69,0.1)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
    gap: 2,
  },
  scoreText: {
    ...Typography.caption,
    fontSize: 10,
    color: Colors.warning,
    fontWeight: '600',
  },

  // Empty State
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.xxxl,
    width: '100%',
  },
  emptyTitle: {
    ...Typography.h2,
    color: Colors.textSecondary,
    marginTop: Spacing.md,
  },
  emptySubtitle: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: Spacing.sm,
    paddingHorizontal: Spacing.xxl,
  },
  resetButton: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    marginTop: Spacing.xl,
  },
  resetButtonText: {
    ...Typography.button,
    color: Colors.textOnPrimary,
  },
  shopStatusMiniBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 1,
    paddingHorizontal: 6,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
  },
  statusDotMini: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
  },
  shopStatusMiniText: {
    fontSize: 9,
    fontWeight: '700',
  },
}), [Colors]);

  const router = useRouter();
  const isAr = i18n.locale.includes('ar');

  // Location
  const { location: userLocation, loading: locationLoading, denied: locationDenied } = useLocation();

  // Offers Data & Loading
  const [offers, setOffers] = useState<CustomerSpecialOfferResponse[]>([]);
  const [categories, setCategories] = useState<CategoryNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Search & Filters State
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedOfferType, setSelectedOfferType] = useState<string>('All');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [maxDistance, setMaxDistance] = useState<number | undefined>(undefined);
  const [showFiltersTray, setShowFiltersTray] = useState(false);
  const [showScoreInfo, setShowScoreInfo] = useState(false);

  const fetchOffers = useCallback(async (coords?: { latitude: number; longitude: number } | null) => {
    const activeCoords = coords || userLocation;
    if (!activeCoords) {
      setOffers([]);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    setLoading(true);
    try {
      const filters: CustomerOffersFilters = {
        query: searchQuery.trim() || undefined,
        offer_type: selectedOfferType === 'All' ? undefined : selectedOfferType,
        max_distance_km: maxDistance,
        category_id: selectedCategory || undefined,
      };

      const fetchedOffers = await getCustomerSpecialOffers(
        activeCoords.latitude,
        activeCoords.longitude,
        filters
      );
      setOffers(Array.isArray(fetchedOffers) ? fetchedOffers : []);
    } catch (err) {
      // Silently fail and fallback to empty state
      setOffers([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userLocation, searchQuery, selectedOfferType, selectedCategory, maxDistance]);

  useEffect(() => {
    (async () => {
      try {
        const cats = await getCategories();
        setCategories(cats);
      } catch (err) {
        console.warn('Failed to load categories tree:', err);
      }
    })();
  }, []);

  useEffect(() => {
    if (userLocation) {
      fetchOffers(userLocation);
    } else if (!locationLoading) {
      setLoading(false);
    }
  }, [userLocation, locationLoading, fetchOffers]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchOffers();
  };

  const handleApplyFilters = () => {
    setShowFiltersTray(false);
    fetchOffers();
  };

  const handleClearFilters = () => {
    setSelectedOfferType('All');
    setSelectedCategory(null);
    setMaxDistance(undefined);
    setSearchQuery('');
    setShowFiltersTray(false);
    
    if (userLocation) {
      // Fetch reset data
      setLoading(true);
      getCustomerSpecialOffers(userLocation.latitude, userLocation.longitude)
        .then(setOffers)
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  };


  const renderOfferCard = ({ item }: { item: CustomerSpecialOfferResponse }) => {
    const isBogo = item.offer_type === 'buy_x_get_y';
    const offerBadgeText = item.offer_summary
      || (isBogo
        ? `Buy ${item.config?.buy ?? ''} Get ${item.config?.get ?? ''} Free`
        : item.discount_percentage != null
          ? `${item.discount_percentage}% ${t('offers.off')}`
          : item.offer_type);

    return (
      <TouchableOpacity
        style={styles.offerCard}
        onPress={() => router.push({ pathname: '/(customer)/product/[id]', params: { id: item.market_item_id } })}
      >
        {/* Badge Overlay */}
        <View style={[styles.cardBadge, isBogo ? styles.cardBadgeBogo : styles.cardBadgeDiscount]}>
          <Ionicons
            name={isBogo ? "gift" : "pricetag"}
            size={12}
            color={isBogo ? Colors.background : Colors.textOnPrimary}
          />
          <Text style={[styles.cardBadgeText, isBogo ? styles.cardBadgeTextBogo : styles.cardBadgeTextDiscount]}>
            {offerBadgeText}
          </Text>
        </View>

        <Image
          source={
            item.image_url
              ? { uri: resolveImageUrl(item.image_url) }
              : require('../../../assets/icon.png')
          }
          style={styles.cardImage}
        />

        <View style={styles.cardInfo}>
          <Text style={styles.productName} numberOfLines={1}>{item.product_name}</Text>
          <Text style={styles.categoryName}>
            {(i18n.locale?.startsWith('ar') ? (item.category_name_ar || item.category) : (item.category_name_en || item.category)) || t('offers.general_promo')}
          </Text>

          {item.price != null && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.xs, marginTop: 4 }}>
              <Text style={styles.priceText}>
                {formatPrice(item.price)}
              </Text>
              {item.discount_percentage != null && item.discount_percentage > 0 && item.discount_percentage < 100 && (
                <Text style={styles.originalPriceText}>
                  {formatPrice(item.price / (1 - item.discount_percentage / 100))}
                </Text>
              )}
            </View>
          )}

          {item.description ? (
            <Text style={styles.descriptionText} numberOfLines={2}>{item.description}</Text>
          ) : null}

          <View style={styles.cardDivider} />

          {/* Shop & Location Proximity */}
          <View style={styles.shopRow}>
            <Ionicons name="storefront-outline" size={14} color={item.shop_is_open ? Colors.success : Colors.error} />
            <Text style={styles.shopName} numberOfLines={1}>{item.shop_name}</Text>
            <View style={[
              styles.shopStatusMiniBadge,
              {
                backgroundColor: item.shop_is_open ? 'rgba(0, 217, 126, 0.1)' : 'rgba(255, 77, 106, 0.1)',
                borderColor: item.shop_is_open ? 'rgba(0, 217, 126, 0.25)' : 'rgba(255, 77, 106, 0.25)',
              }
            ]}>
              <View style={[styles.statusDotMini, { backgroundColor: item.shop_is_open ? Colors.success : Colors.error }]} />
              <Text style={[styles.shopStatusMiniText, { color: item.shop_is_open ? Colors.success : Colors.error }]}>
                {item.shop_is_open ? t('common.open') : t('common.closed')}
              </Text>
            </View>
          </View>

          <View style={styles.metaRow}>
            <View style={styles.metricPill}>
              <Ionicons name="location-outline" size={12} color={Colors.secondary} />
              <Text style={styles.metricText}>
                {formatDistanceKm(item.distance_km, isAr)}
              </Text>
            </View>

            <View style={styles.scorePill}>
              <Ionicons name="star" size={12} color={Colors.warning} />
              <Text style={styles.scoreText}>
                {item.sorting_score.toFixed(1)}
              </Text>
            </View>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Top Banner for Fallback Coordinates */}
      {locationDenied && (
        <View style={styles.warningBanner}>
          <Ionicons name="location-sharp" size={16} color={Colors.background} />
          <Text style={styles.warningText}>
            {t('offers.location_denied')}
          </Text>
        </View>
      )}

      {/* Header with Search and Info */}
      <View style={styles.header}>
        <View style={styles.headerTitleRow}>
          <View>
            <Text style={styles.headerTitle}>{t('offers.title')}</Text>
            <Text style={styles.headerSubtitle}>
              {t('offers.customer_subtitle', 'Deals and discounts near you')}
            </Text>
          </View>
          <TouchableOpacity
            style={styles.infoButton}
            onPress={() => setShowScoreInfo(!showScoreInfo)}
          >
            <Ionicons name="information-circle-outline" size={24} color={Colors.primary} />
          </TouchableOpacity>
        </View>

        {/* Dynamic Score Info Description */}
        {showScoreInfo && (
          <View style={styles.infoBox}>
            <Text style={styles.infoBoxTitle}>{t('offers.how_sorted')}</Text>
            <Text style={styles.infoBoxBody}>
              {t('offers.sort_desc')}
            </Text>
          </View>
        )}

        {/* Search Input Bar */}
        <View style={styles.searchBarContainer}>
          <View style={styles.searchBox}>
            <Ionicons name="search" size={20} color={Colors.textMuted} />
            <TextInput
              style={styles.searchInput}
              placeholder={t('offers.search_placeholder')}
              placeholderTextColor={Colors.textMuted}
              value={searchQuery}
              onChangeText={setSearchQuery}
              onSubmitEditing={() => fetchOffers()}
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity onPress={() => { setSearchQuery(''); fetchOffers(); }}>
                <Ionicons name="close" size={20} color={Colors.textMuted} />
              </TouchableOpacity>
            )}
          </View>
          <TouchableOpacity
            style={[styles.filterButton, showFiltersTray && styles.filterButtonActive]}
            onPress={() => setShowFiltersTray(!showFiltersTray)}
          >
            <Ionicons name="options-outline" size={22} color={showFiltersTray ? Colors.background : Colors.textPrimary} />
          </TouchableOpacity>
        </View>

        {/* Horizontal Category Pills */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.categoryScroll}
          contentContainerStyle={styles.categoryScrollContent}
        >
          <TouchableOpacity
            style={[styles.categoryPill, selectedCategory === null && styles.categoryPillActive]}
            onPress={() => { setSelectedCategory(null); fetchOffers(); }}
          >
            <Text style={[styles.categoryPillText, selectedCategory === null && styles.categoryPillTextActive]}>
              {t('common.all')}
            </Text>
          </TouchableOpacity>
          {categories.map((cat) => {
            const catName = i18n.locale?.startsWith('ar') ? (cat.name_ar || cat.name) : (cat.name_en || cat.name);
            return (
              <TouchableOpacity
                key={cat.id}
                style={[styles.categoryPill, selectedCategory === cat.id && styles.categoryPillActive]}
                onPress={() => { setSelectedCategory(cat.id); fetchOffers(); }}
              >
                <Text style={[styles.categoryPillText, selectedCategory === cat.id && styles.categoryPillTextActive]}>
                  {catName}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* Sliding Faceted Filters Tray */}
      {showFiltersTray && (
        <View style={styles.filtersTray}>
          <Text style={styles.trayTitle}>{t('offers.filters')}</Text>

          {/* Offer Type Selector */}
          <Text style={styles.trayLabel}>{t('offers.offer_type')}</Text>
          <View style={styles.trayPillsRow}>
            {['All', 'buy_x_get_y', 'percentage', 'fixed_amount', 'quantity_price'].map((type) => (
              <TouchableOpacity
                key={type}
                style={[styles.trayPill, selectedOfferType === type && styles.trayPillActive]}
                onPress={() => setSelectedOfferType(type)}
              >
                <Text style={[styles.trayPillText, selectedOfferType === type && styles.trayPillTextActive]}>
                  {type === 'All' ? t('common.all')
                    : type === 'buy_x_get_y' ? (i18n.locale?.startsWith('ar') ? 'اشتر واحصل' : 'Buy X Get Y')
                    : type === 'percentage' ? (i18n.locale?.startsWith('ar') ? 'نسبة تخفيض' : '% Discount')
                    : type === 'fixed_amount' ? (i18n.locale?.startsWith('ar') ? 'تخفيض ثابت' : 'Fixed')
                    : type === 'quantity_price' ? (i18n.locale?.startsWith('ar') ? 'سعر الكمية' : 'Bundle')
                    : type}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Distance Constraint selector */}
          <Text style={styles.trayLabel}>{t('offers.max_distance')}</Text>
          <View style={styles.trayPillsRow}>
            {[
              { label: t('common.all'), val: undefined },
              { label: '< 2km', val: 2.0 },
              { label: '< 5km', val: 5.0 },
              { label: '< 10km', val: 10.0 },
              { label: '< 25km', val: 25.0 }
            ].map((d, index) => (
              <TouchableOpacity
                key={index}
                style={[styles.trayPill, maxDistance === d.val && styles.trayPillActive]}
                onPress={() => setMaxDistance(d.val)}
              >
                <Text style={[styles.trayPillText, maxDistance === d.val && styles.trayPillTextActive]}>
                  {d.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Actions */}
          <View style={styles.trayActions}>
            <TouchableOpacity style={styles.trayClearBtn} onPress={handleClearFilters}>
              <Text style={styles.trayClearText}>{t('common.reset')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.trayApplyBtn} onPress={handleApplyFilters}>
              <Text style={styles.trayApplyText}>{t('offers.apply_filters')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Main Promotions Grid List */}
      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : (
        <FlatList
          data={offers}
          keyExtractor={(item) => item.id}
          renderItem={renderOfferCard}
          contentContainerStyle={styles.listContent}
          numColumns={2}
          columnWrapperStyle={styles.columnWrapper}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              tintColor={Colors.primary}
            />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingVertical: 48, paddingHorizontal: Spacing.xl }}>
              <Ionicons name="pricetag-outline" size={64} color={Colors.textSecondary} style={{ opacity: 0.4 }} />
              <Text style={{ color: Colors.textSecondary, fontSize: 15, marginTop: 16, textAlign: 'center', fontWeight: '600' }}>
                {t('offers.no_deals_title', 'Offers Coming Soon')}
              </Text>
              <Text style={{ color: Colors.textSecondary, fontSize: 13, marginTop: 4, textAlign: 'center' }}>
                {t('offers.no_deals_desc', 'Stay tuned for deals and discounts from nearby stores')}
              </Text>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
}