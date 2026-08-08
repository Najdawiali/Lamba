/**
 * Product Detail Screen — Full product view, multi-image carousel, and collapsible shop details.
 * Premium dark mode styling matching modern visual guidance rules.
 */

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Image, TouchableOpacity,
  ActivityIndicator, useWindowDimensions, Alert, Share, Modal, TextInput
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Spacing, BorderRadius, Typography, Shadows } from '../../../constants/theme';
import { useThemeColors } from '../../../context/ThemeContext';
import {
  getMarketItemDetails,
  MarketItemDetailsResponse, isFavorite, addFavorite, removeFavorite
} from '../../../services/api';
import { t, i18n } from '../../../services/i18n';
import { getCurrencyCode, formatPrice } from '../../../services/currency';
import { resolveImageUrl, calculateDistanceMeters, roundDistance } from '../../../services/utils';

export default function ProductDetailScreen() {
  const Colors = useThemeColors();
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { width: SCREEN_WIDTH } = useWindowDimensions();
  const isAr = i18n.locale.includes('ar');
  
  const [product, setProduct] = useState<MarketItemDetailsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isFav, setIsFav] = useState(false);

  // Description collapse
  const [descExpanded, setDescExpanded] = useState(false);

  // Collapsible sections state
  const [showHours, setShowHours] = useState(false);

  const loadProductDetails = async () => {
    if (!id) {
      setError(isAr ? 'تعذر استرداد تفاصيل المنتج. تحقق من الاتصال.' : 'Could not retrieve product listing. Check store connectivity.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getMarketItemDetails(id);
      setProduct(data);
    } catch (err) {
      console.error('Failed to load product details:', err);
      setError(isAr ? 'تعذر استرداد تفاصيل المنتج. تحقق من الاتصال.' : 'Could not retrieve product listing. Check store connectivity.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      setProduct(null);
      try {
        const fav = await isFavorite(id);
        setIsFav(fav);
      } catch (err) {
        console.error('Failed to check favorite status:', err);
      }

      await loadProductDetails();
    })();
  }, [id]);

  const handleToggleFavorite = async () => {
    try {
      if (isFav) {
        await removeFavorite(id);
        setIsFav(false);
        if (product) Alert.alert(t('favorites.removed'), `"${product.name}" ` + t('favorites.removed_desc'));
      } else {
        await addFavorite(id);
        setIsFav(true);
        if (product) Alert.alert(t('favorites.added'), `"${product.name}" ` + t('favorites.added_desc'));
      }
    } catch (err) {
      console.error('Failed to update favorites:', err);
    }
  };

  const handleShare = async () => {
    if (!product) return;
    try {
      const priceLabel = product.price != null && product.price > 0 ? formatPrice(product.price) : '';
      await Share.share({
        message: t('product.share_text', { name: product.name, shop: product.shop.name, price: priceLabel }),
      });
    } catch (err) {
      console.error(err);
    }
  };

  const productImages = useMemo(() => {
    if (!product) return [];
    return product.images && product.images.length > 0
      ? product.images
      : (product.image_url ? [product.image_url] : []);
  }, [product?.images, product?.image_url]);

  const styles = useMemo(() => StyleSheet.create({
    container: { flex: 1, backgroundColor: Colors.background },
    loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
    errorText: { ...Typography.body, color: Colors.error, marginTop: Spacing.md, marginBottom: Spacing.md },
    retryBtn: { paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm, backgroundColor: Colors.primary, borderRadius: BorderRadius.md, ...Shadows.small },
    retryBtnText: { ...Typography.button, color: Colors.textOnPrimary },
    scrollContent: { paddingBottom: 40 },

    carouselContainer: { height: 280, backgroundColor: Colors.surface, position: 'relative' },
    carouselImage: { height: 280, resizeMode: 'cover' },
    imagePlaceholder: { height: 280, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.surface },

    heroActionsOverlay: { position: 'absolute', top: 0, left: 0, right: 0, flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingTop: Spacing.sm },
    overlayIconBtn: { width: 32, height: 32, borderRadius: 16, backgroundColor: 'rgba(10, 10, 26, 0.7)', justifyContent: 'center', alignItems: 'center' },

    dotsContainer: { flexDirection: 'row', position: 'absolute', bottom: Spacing.md, left: 0, right: 0, justifyContent: 'center', alignItems: 'center', gap: 6 },
    dot: { width: 8, height: 8, borderRadius: 4 },
    dotActive: { backgroundColor: Colors.primary, width: 18 },
    dotInactive: { backgroundColor: 'rgba(255,255,255,0.4)' },

    stockBadge: { position: 'absolute', bottom: -16, right: Spacing.xl, paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm, borderRadius: BorderRadius.full, ...Shadows.small, borderWidth: 2, borderColor: Colors.background },
    stockText: { ...Typography.label, color: Colors.background, fontWeight: '800' },

    infoSection: { paddingHorizontal: Spacing.xl, paddingTop: Spacing.xxl },
    productName: { ...Typography.h1, color: Colors.textPrimary, marginBottom: Spacing.xs },
    price: { ...Typography.h1, color: Colors.secondary, marginBottom: Spacing.md },
    priceFree: { fontSize: 20, fontWeight: '700', color: Colors.textSecondary, marginBottom: Spacing.md },
    currency: { ...Typography.body, color: Colors.textSecondary },

    categoryBadge: { alignSelf: 'flex-start', backgroundColor: Colors.surfaceElevated, paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs, borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border },
    categoryText: { ...Typography.label, color: Colors.textSecondary },

    section: { paddingHorizontal: Spacing.xl, paddingTop: Spacing.xl },
    sectionTitle: { ...Typography.h3, color: Colors.textPrimary, marginBottom: Spacing.md },
    description: { ...Typography.body, color: Colors.textSecondary, lineHeight: 24 },
    readMoreText: { ...Typography.bodySmall, color: Colors.secondary, fontWeight: '700', marginTop: Spacing.xs },

    shopCard: { backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.xl, padding: Spacing.lg, borderWidth: 1, borderColor: Colors.border, ...Shadows.small },
    shopMetaRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: Spacing.sm },
    shopName: { ...Typography.h3, color: Colors.textPrimary },
    shopAddress: { ...Typography.bodySmall, color: Colors.textMuted, marginTop: 2 },

    viewShopLink: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: Spacing.lg, marginLeft: 32 },
    viewShopText: { ...Typography.bodySmall, color: Colors.secondary, fontWeight: '700' },

    collapsibleTrigger: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: Spacing.md, borderTopWidth: 1, borderTopColor: Colors.border },
    triggerLabel: { ...Typography.body, color: Colors.textPrimary, fontWeight: '600' },
    collapsibleContent: { paddingVertical: Spacing.md, borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.05)' },
    scheduleRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: Spacing.xs },
    scheduleDay: { ...Typography.bodySmall, color: Colors.textSecondary },
    scheduleTime: { ...Typography.bodySmall, color: Colors.textMuted, fontWeight: '600' },
    emptyDetailsText: { ...Typography.bodySmall, color: Colors.textMuted, fontStyle: 'italic' },
  }), [Colors]);

  if (loading && !product) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  if (error || !product) {
    return (
      <View style={styles.loadingContainer}>
        <Ionicons name="alert-circle-outline" size={48} color={Colors.error} />
        <Text style={styles.errorText}>{error || 'Product not found'}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={loadProductDetails}>
          <Text style={styles.retryBtnText}>Retry Load</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Hero image carousel (280px height) */}
        <View style={[styles.carouselContainer, { width: SCREEN_WIDTH }]}>
          <ScrollView
            horizontal
            pagingEnabled
            showsHorizontalScrollIndicator={false}
            onScroll={(e) => {
              const x = e.nativeEvent.contentOffset.x;
              const index = Math.round(x / SCREEN_WIDTH);
              if (index !== activeImageIndex) setActiveImageIndex(index);
            }}
            scrollEventThrottle={32}
          >
            {productImages.length > 0 ? (
              productImages.map((imgUrl, i) => (
                <Image
                  key={i}
                  source={{ uri: resolveImageUrl(imgUrl) }}
                  style={[styles.carouselImage, { width: SCREEN_WIDTH }]}
                />
              ))
            ) : (
              <View style={[styles.imagePlaceholder, { width: SCREEN_WIDTH }]}>
                <Ionicons name="cube-outline" size={72} color={Colors.textMuted} />
              </View>
            )}
          </ScrollView>

          {productImages.length > 1 && (
            <View style={styles.dotsContainer}>
              {productImages.map((_, i) => (
                <View key={i} style={[styles.dot, activeImageIndex === i ? styles.dotActive : styles.dotInactive]} />
              ))}
            </View>
          )}

          {/* Top Actions Overlay */}
          <SafeAreaView style={styles.heroActionsOverlay} edges={['top']}>
            <TouchableOpacity onPress={() => router.back()} style={styles.overlayIconBtn}>
              <Ionicons name="arrow-back" size={20} color={Colors.textPrimary} />
            </TouchableOpacity>
            <View style={{ flexDirection: 'row', gap: Spacing.sm }}>
              <TouchableOpacity onPress={handleToggleFavorite} style={styles.overlayIconBtn}>
                <Ionicons name={isFav ? "heart" : "heart-outline"} size={20} color={isFav ? Colors.primary : Colors.textPrimary} />
              </TouchableOpacity>
              <TouchableOpacity onPress={handleShare} style={styles.overlayIconBtn}>
                <Ionicons name="share-social-outline" size={20} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
          </SafeAreaView>

          {/* Stock availability badge — coarse levels only, no exact counts, so
              competitors can't read merchant inventory levels from the customer app. */}
          <View style={[styles.stockBadge, { backgroundColor: product.in_stock ? Colors.success : Colors.error }]}>
            <Text style={styles.stockText}>
              {product.in_stock
                ? (product.stock_count <= 5 ? t('product.low_stock', 'Low Stock') : t('product.in_stock', 'In Stock'))
                : t('product.out_of_stock', 'Out of Stock')}
            </Text>
          </View>
        </View>

        {/* Info Area */}
        <View style={styles.infoSection}>
          <Text style={styles.productName}>{product.name}</Text>
          {product.price != null && product.price > 0 ? (
            <Text style={styles.price}>
              {formatPrice(product.price)}
            </Text>
          ) : (
            <Text style={styles.priceFree}>{t('product.price_request')}</Text>
          )}
          {Boolean(product.category) ? (
            <View style={styles.categoryBadge}>
              <Text style={styles.categoryText}>{product.category}</Text>
            </View>
          ) : null}
        </View>

        {/* Description */}
        {Boolean(product.description) ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>{t('product.description', 'Description')}</Text>
            <Text style={styles.description} numberOfLines={descExpanded ? undefined : 3}>
              {product.description}
            </Text>
            {Boolean(product.description && product.description.length > 100) ? (
              <TouchableOpacity onPress={() => setDescExpanded(!descExpanded)}>
                <Text style={styles.readMoreText}>{descExpanded ? 'Show less' : t('product.read_more', 'Read more')}</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}

        {/* Shop Info Card */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t('product.store_info', 'Store Info')}</Text>
          <View style={styles.shopCard}>
            <View style={styles.shopMetaRow}>
              <Ionicons name="storefront-outline" size={24} color={product.shop.is_currently_open ? Colors.success : Colors.error} />
              <View style={{ flex: 1, marginLeft: Spacing.sm }}>
                <Text style={styles.shopName}>{product.shop.name}</Text>
                <Text style={styles.shopAddress}>{product.shop.address}</Text>
              </View>
            </View>

            <TouchableOpacity style={styles.viewShopLink} onPress={() => router.push(`/(customer)/shop/${product.shop.id}`)}>
              <Text style={styles.viewShopText}>{t('product.view_full_shop', 'View Full Shop')}</Text>
              <Ionicons name="arrow-forward" size={16} color={Colors.secondary} />
            </TouchableOpacity>

            <TouchableOpacity style={styles.collapsibleTrigger} onPress={() => setShowHours(!showHours)}>
              <Text style={styles.triggerLabel}>{t('product.operating_hours', 'Operating Hours')}</Text>
              <Ionicons name={showHours ? 'chevron-up-outline' : 'chevron-down-outline'} size={18} color={Colors.textMuted} />
            </TouchableOpacity>

            {Boolean(showHours) ? (
              <View style={styles.collapsibleContent}>
                {product.shop.operating_hours ? (
                  Object.entries(product.shop.operating_hours).map(([day, hours]) => (
                    <View key={day} style={styles.scheduleRow}>
                      <Text style={styles.scheduleDay}>{day}</Text>
                      <Text style={styles.scheduleTime}>{hours}</Text>
                    </View>
                  ))
                ) : (
                  <Text style={styles.emptyDetailsText}>{t('product.no_schedule', 'No schedule provided')}</Text>
                )}
              </View>
            ) : null}

          </View>
        </View>
      </ScrollView>

    </View>
  );
}
