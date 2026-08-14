import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Image, Dimensions, Linking, Platform } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Spacing, BorderRadius, Typography, Shadows } from '../../../constants/theme';
import { useThemeColors } from '../../../context/ThemeContext';
import { getMarketCatalog, getMarketDetails, MarketCatalogResponse, CustomerItemResponse, ShopDetails } from '../../../services/api';
import { t, isRTL } from '../../../services/i18n';
import { formatPrice } from '../../../services/currency';
import { resolveImageUrl } from '../../../services/utils';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const COLUMN_SPACING = Spacing.md;
const CARD_WIDTH = (SCREEN_WIDTH - Spacing.xl * 2 - COLUMN_SPACING) / 2;

const openDirections = (latitude: number, longitude: number, storeName: string) => {
  const encodedName = encodeURIComponent(storeName);
  const url = Platform.select({
    android: `google.navigation:q=${latitude},${longitude}&label=${encodedName}`,
    ios: `maps://app?daddr=${latitude},${longitude}&q=${encodedName}`,
    default: `https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}&destination_place_id=${encodedName}`,
  });
  if (url) {
    Linking.openURL(url).catch((err) => {
      console.warn('Could not open maps application, falling back to web URL:', err);
      Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}`);
    });
  }
};

export default function ShopCatalogScreen() {
  const Colors = useThemeColors();
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  
  const [catalog, setCatalog] = useState<MarketCatalogResponse | null>(null);
  const [market, setMarket] = useState<ShopDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeCategory, setActiveCategory] = useState<string>('');

  useEffect(() => {
    (async () => {
      if (!id) {
        setError(t('common.error', 'Failed to load catalog'));
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const [catalogData, marketData] = await Promise.all([
          getMarketCatalog(id),
          getMarketDetails(id).catch(() => null),
        ]);
        setCatalog(catalogData);
        setMarket(marketData);
        const categories = Object.keys(catalogData || {});
        if (categories.length > 0) {
          setActiveCategory(categories[0]);
        }
      } catch (err) {
        console.error('Failed to load shop catalog', err);
        setError(t('common.error', 'Failed to load catalog'));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const styles = useMemo(() => StyleSheet.create({
    container: { flex: 1, backgroundColor: Colors.background },
    loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
    errorText: { ...Typography.body, color: Colors.error, marginTop: Spacing.md, marginBottom: Spacing.md },
    retryBtn: { paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm, backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border },
    retryBtnText: { ...Typography.button, color: Colors.textPrimary },

    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, borderBottomWidth: 1, borderBottomColor: Colors.border },
    headerBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: Colors.surfaceElevated, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: Colors.border },
    headerTitle: { ...Typography.h3, color: Colors.textPrimary, flex: 1, textAlign: 'center', marginHorizontal: Spacing.sm },

    storeBanner: {
      padding: Spacing.lg,
      backgroundColor: Colors.surfaceElevated,
      borderBottomWidth: 1,
      borderBottomColor: Colors.border,
    },
    storeHeaderRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.md,
      marginBottom: Spacing.md,
    },
    storeIconWrapper: {
      width: 48,
      height: 48,
      borderRadius: 24,
      backgroundColor: 'rgba(108, 99, 255, 0.1)',
      justifyContent: 'center',
      alignItems: 'center',
    },
    storeNameText: {
      ...Typography.h2,
      color: Colors.textPrimary,
      marginBottom: 2,
    },
    storeAddressText: {
      ...Typography.caption,
      color: Colors.textSecondary,
      marginBottom: 4,
    },
    storeStatusRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
    },
    statusDot: { width: 6, height: 6, borderRadius: 3 },
    statusText: { fontSize: 11, fontWeight: '700' },
    directionsBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: Colors.primary,
      borderRadius: BorderRadius.md,
      paddingVertical: 10,
      paddingHorizontal: Spacing.lg,
      gap: 8,
      ...Shadows.small,
    },
    directionsBtnText: {
      ...Typography.button,
      color: Colors.textOnPrimary,
    },

    tabsContainer: { borderBottomWidth: 1, borderBottomColor: Colors.border },
    tabsScroll: { paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, gap: Spacing.sm },
    tabBtn: { paddingHorizontal: Spacing.lg, paddingVertical: 8, borderRadius: BorderRadius.full, backgroundColor: Colors.surfaceElevated, borderWidth: 1, borderColor: Colors.border },
    tabBtnActive: { backgroundColor: Colors.primary, borderColor: Colors.primary },
    tabText: { ...Typography.bodySmall, color: Colors.textSecondary, fontWeight: '600' },
    tabTextActive: { color: Colors.textOnPrimary },

    gridContainer: { flexDirection: 'row', flexWrap: 'wrap', padding: Spacing.xl, gap: COLUMN_SPACING, paddingBottom: 100 },
    cardContainer: { width: CARD_WIDTH, backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.lg, overflow: 'hidden', borderWidth: 1, borderColor: Colors.border, ...Shadows.small },

    imageContainer: { width: '100%', height: CARD_WIDTH, backgroundColor: Colors.surface, position: 'relative' },
    image: { width: '100%', height: '100%', resizeMode: 'cover' },
    imagePlaceholder: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    outOfStockOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(10, 10, 26, 0.7)', justifyContent: 'center', alignItems: 'center' },
    outOfStockText: { ...Typography.caption, color: Colors.textOnPrimary, fontWeight: '700', backgroundColor: Colors.error, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 },

    cardInfo: { padding: Spacing.sm },
    itemName: { ...Typography.bodySmall, color: Colors.textPrimary, fontWeight: '600', marginBottom: Spacing.xs, height: 36 },

    priceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 },
    priceText: { ...Typography.h3, color: Colors.secondary },
    priceFree: { ...Typography.caption, color: Colors.textSecondary },

    quickAddBtn: { width: 28, height: 28, borderRadius: 14, backgroundColor: Colors.primary, justifyContent: 'center', alignItems: 'center' },

    emptyContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: Spacing.xxl },
    emptyTitle: { ...Typography.h3, color: Colors.textPrimary, marginTop: Spacing.lg },
    emptySubtitle: { ...Typography.bodySmall, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.sm },
  }), [Colors]);

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  if (error || !catalog) {
    return (
      <View style={styles.loadingContainer}>
        <Ionicons name="alert-circle-outline" size={48} color={Colors.error} />
        <Text style={styles.errorText}>{error || ''}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={() => router.back()}>
          <Text style={styles.retryBtnText}>{t('common.back', 'Go Back')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const categories = Object.keys(catalog);
  const activeItems = activeCategory ? catalog[activeCategory] : [];
  const isAr = isRTL();
  const marketDisplayName = market ? (isAr ? (market.name_ar || market.name) : (market.name_en || market.name)) : '';
  const marketDisplayAddress = market ? (isAr ? (market.address_ar || market.address) : (market.address_en || market.address)) : '';

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerBtn}>
          <Ionicons name={isAr ? "arrow-forward" : "arrow-back"} size={22} color={Colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>{marketDisplayName || t('product.view_full_shop', 'Shop Catalog')}</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Store Info Banner with Directions */}
      {market ? (
        <View style={styles.storeBanner}>
          <View style={styles.storeHeaderRow}>
            <View style={styles.storeIconWrapper}>
              <Ionicons name="storefront" size={24} color={Colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.storeNameText} numberOfLines={1}>{marketDisplayName}</Text>
              <Text style={styles.storeAddressText} numberOfLines={2}>{marketDisplayAddress}</Text>
              <View style={styles.storeStatusRow}>
                <View style={[styles.statusDot, { backgroundColor: market.is_currently_open ? Colors.success : Colors.error }]} />
                <Text style={[styles.statusText, { color: market.is_currently_open ? Colors.success : Colors.error }]}>
                  {market.is_currently_open ? t('common.open', 'Open') : t('common.closed', 'Closed')}
                </Text>
              </View>
            </View>
          </View>
          <TouchableOpacity
            onPress={() => openDirections(market.latitude, market.longitude, marketDisplayName)}
            style={styles.directionsBtn}
            activeOpacity={0.8}
          >
            <Ionicons name="navigate-outline" size={18} color={Colors.textOnPrimary} />
            <Text style={styles.directionsBtnText}>
              {t('market.directions', 'Directions')}
            </Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {categories.length > 0 ? (
        <>
          {/* Category Tabs */}
          <View style={styles.tabsContainer}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabsScroll}>
              {categories.map((cat) => {
                const firstItem = catalog[cat]?.[0];
                const catDisplayName = isAr
                  ? (firstItem?.category_name_ar || cat)
                  : (firstItem?.category_name_en || cat);

                return (
                  <TouchableOpacity
                    key={cat}
                    style={[styles.tabBtn, activeCategory === cat && styles.tabBtnActive]}
                    onPress={() => setActiveCategory(cat)}
                  >
                    <Text style={[styles.tabText, activeCategory === cat && styles.tabTextActive]}>
                      {catDisplayName}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>

          {/* Product Grid */}
          <ScrollView contentContainerStyle={styles.gridContainer} showsVerticalScrollIndicator={false}>
            {(activeItems || []).map((item) => {
              const itemName = isAr ? (item.name_ar || item.name) : (item.name_en || item.name);

              return (
                <TouchableOpacity
                  key={item.market_item_id}
                  style={styles.cardContainer}
                  activeOpacity={0.8}
                  onPress={() => router.push(`/(customer)/product/${item.market_item_id}`)}
                >
                  <View style={styles.imageContainer}>
                    {item.image_url ? (
                      <Image source={{ uri: resolveImageUrl(item.image_url) }} style={styles.image} />
                    ) : (
                      <View style={styles.imagePlaceholder}>
                        <Ionicons name="cube-outline" size={32} color={Colors.textMuted} />
                      </View>
                    )}
                    {!item.in_stock ? (
                      <View style={styles.outOfStockOverlay}>
                        <Text style={styles.outOfStockText}>{t('product.out_of_stock', 'Out of Stock')}</Text>
                      </View>
                    ) : null}
                  </View>

                  <View style={styles.cardInfo}>
                    <Text style={styles.itemName} numberOfLines={2}>{itemName}</Text>
                    <View style={styles.priceRow}>
                      {item.price != null && item.price > 0 ? (
                        <Text style={styles.priceText}>
                          {formatPrice(item.price)}
                        </Text>
                      ) : (
                        <Text style={styles.priceFree}>{t('product.price_request', 'Price on request')}</Text>
                      )}
                      {Boolean(item.in_stock) ? (
                        <TouchableOpacity
                          style={styles.quickAddBtn}
                          onPress={() => router.push(`/(customer)/product/${item.market_item_id}`)}
                        >
                          <Ionicons name="add" size={16} color={Colors.textOnPrimary} />
                        </TouchableOpacity>
                      ) : null}
                    </View>
                  </View>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </>
      ) : (
        <View style={styles.emptyContainer}>
          <Ionicons name="basket-outline" size={64} color={Colors.textMuted} />
          <Text style={styles.emptyTitle}>{t('common.no_items', 'No items available')}</Text>
          <Text style={styles.emptySubtitle}>{t('common.no_items_desc', 'This shop has not listed any items yet.')}</Text>
        </View>
      )}
    </SafeAreaView>
  );
}
