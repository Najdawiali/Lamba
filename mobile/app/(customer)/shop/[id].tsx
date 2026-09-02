import React, { useEffect, useState, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  Image, Dimensions, Alert, Modal, TextInput, FlatList
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Spacing, BorderRadius, Typography, Shadows } from '../../../constants/theme';
import { useThemeColors } from '../../../context/ThemeContext';
import {
  getMarketCatalog, MarketCatalogResponse, startConversation,
  getMarketRatings, submitMarketRating, MarketRatingSummaryResponse, getUser,
  getNearMarkets
} from '../../../services/api';
import { t, i18n } from '../../../services/i18n';
import { formatPrice } from '../../../services/currency';
import { resolveImageUrl, openMapDirections } from '../../../services/utils';
import * as Location from 'expo-location';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const COLUMN_SPACING = Spacing.md;
const CARD_WIDTH = (SCREEN_WIDTH - Spacing.xl * 2 - COLUMN_SPACING) / 2;

export default function ShopCatalogScreen() {
  const Colors = useThemeColors();
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [catalog, setCatalog] = useState<MarketCatalogResponse | null>(null);
  const [ratings, setRatings] = useState<MarketRatingSummaryResponse | null>(null);
  const [storeInfo, setStoreInfo] = useState<{ name: string; lat: number; lng: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeCategory, setActiveCategory] = useState<string>('All');
  const [reviewsModalVisible, setReviewsModalVisible] = useState(false);
  const [writeReviewModalVisible, setWriteReviewModalVisible] = useState(false);

  const [ratingScore, setRatingScore] = useState(5);
  const [reviewText, setReviewText] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  const loadData = async () => {
    if (!id) {
      setError(t('common.error', 'Failed to load catalog'));
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const [catalogData, ratingsData] = await Promise.all([
        getMarketCatalog(id).catch(() => null),
        getMarketRatings(id).catch(() => null),
      ]);

      if (catalogData) {
        setCatalog(catalogData);
      }
      if (ratingsData) {
        setRatings(ratingsData);
      }

      try {
        const markets = await getNearMarkets(32.0385, 35.7275, 50); // wide radius to find the store
        const thisMarket = markets.find(m => m.id === id);
        if (thisMarket) {
          setStoreInfo({ name: thisMarket.name, lat: thisMarket.latitude, lng: thisMarket.longitude });
        }
      } catch {}
    } catch (err) {
      console.error('Failed to load shop catalog', err);
      setError(t('common.error', 'Failed to load catalog'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const handleSubmitReview = async () => {
    if (!id) return;
    try {
      setSubmittingReview(true);
      const currentUser = await getUser();
      if (!currentUser || !currentUser.id) {
        Alert.alert(t('common.info', 'تنبيه'), t('profile.login_required', 'يرجى تسجيل الدخول أولاً'));
        return;
      }

      // Fetch user GPS location for 50m geofence verification
      let loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }).catch(() => null);
      const lat = loc?.coords?.latitude || 0.0;
      const lng = loc?.coords?.longitude || 0.0;

      await submitMarketRating({
        market_id: id,
        customer_id: currentUser.id,
        score: ratingScore,
        review: reviewText.trim(),
        latitude: lat,
        longitude: lng,
      });

      Alert.alert(t('common.success', 'تم التقييم'), t('shop.review_submitted', 'شكراً لك، تم إضافة تقييمك بنجاح'));
      setWriteReviewModalVisible(false);
      setReviewText('');

      // Refresh ratings
      const updatedRatings = await getMarketRatings(id).catch(() => null);
      if (updatedRatings) setRatings(updatedRatings);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || 'تعذر إضافة التقييم. تأكد من تواجدك بالقرب من المتجر';
      Alert.alert(t('common.error', 'خطأ'), detail);
    } finally {
      setSubmittingReview(false);
    }
  };

  const handleMessageShop = async () => {
    if (!id) return;
    try {
      const res = await startConversation(id as string);
      router.push({
        pathname: '/(customer)/chat/[id]',
        params: {
          id: res.data.conversation_id,
          marketName: storeInfo?.name || firstItem?.category_name_ar || 'المتجر',
          suggestion: 'مرحباً، أستفسر عن متجركم',
        },
      });
    } catch (e) {
      console.error('Failed to start conversation:', e);
      Alert.alert('خطأ', 'فشل في بدء المحادثة');
    }
  };

  const styles = useMemo(() => StyleSheet.create({
    container: { flex: 1, backgroundColor: Colors.background },
    loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
    errorText: { ...Typography.body, color: Colors.error, marginTop: Spacing.md, marginBottom: Spacing.md },
    retryBtn: { paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm, backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border },
    retryBtnText: { ...Typography.button, color: Colors.textPrimary },

    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, borderBottomWidth: 1, borderBottomColor: Colors.border },
    headerBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: Colors.surfaceElevated, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: Colors.border },
    headerTitle: { ...Typography.h3, color: Colors.textPrimary },

    // Shop Info Card
    shopCard: {
      backgroundColor: Colors.surfaceElevated,
      margin: Spacing.lg,
      borderRadius: BorderRadius.xl,
      padding: Spacing.lg,
      borderWidth: 1,
      borderColor: Colors.border,
      ...Shadows.small,
    },
    shopTitleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    shopName: { ...Typography.h2, color: Colors.textPrimary, flex: 1 },
    ratingBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(255, 184, 0, 0.15)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: BorderRadius.full },
    ratingScoreText: { fontSize: 13, fontWeight: '700', color: Colors.warning },

    actionButtonsRow: { flexDirection: 'row', gap: 8, marginTop: Spacing.lg },
    actionBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: BorderRadius.md, gap: 6, borderWidth: 1 },
    actionBtnPrimary: { backgroundColor: Colors.primary, borderColor: Colors.primary },
    actionBtnSecondary: { backgroundColor: Colors.surface, borderColor: Colors.border },
    actionBtnTextPrimary: { color: '#FFF', fontSize: 13, fontWeight: '600' },
    actionBtnTextSecondary: { color: Colors.textPrimary, fontSize: 13, fontWeight: '600' },

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

    // Modal styling
    modalOverlay: { flex: 1, backgroundColor: 'rgba(10, 10, 26, 0.65)', justifyContent: 'flex-end' },
    modalContainer: { height: '75%', backgroundColor: Colors.background, borderTopLeftRadius: BorderRadius.xl, borderTopRightRadius: BorderRadius.xl, borderWidth: 1, borderColor: Colors.border },
    modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: Spacing.xl, borderBottomWidth: 1, borderColor: Colors.border },
    modalTitle: { ...Typography.h2, color: Colors.textPrimary },
    closeBtn: { padding: Spacing.xs },

    reviewCard: { backgroundColor: Colors.surfaceElevated, padding: Spacing.md, borderRadius: BorderRadius.lg, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.border },
    reviewHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
    reviewerName: { ...Typography.body, color: Colors.textPrimary, fontWeight: '700' },
    reviewDate: { ...Typography.caption, color: Colors.textMuted },
    reviewText: { ...Typography.bodySmall, color: Colors.textSecondary, lineHeight: 20 },
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
  const activeItems = activeCategory === 'All'
    ? Object.values(catalog).flat()
    : (catalog[activeCategory] || []);
  const firstItem = activeItems[0] || (categories[0] ? catalog[categories[0]][0] : null);
  const isAr = i18n.locale?.startsWith('ar');

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerBtn}>
          <Ionicons name={i18n.locale?.startsWith('ar') ? "arrow-forward" : "arrow-back"} size={22} color={Colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{t('product.view_full_shop', 'View Full Shop')}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Shop Info Card with Ratings & Directions */}
        <View style={styles.shopCard}>
          <View style={styles.shopTitleRow}>
            <Text style={styles.shopName}>
              {storeInfo?.name || t('product.view_full_shop', 'View Full Shop')}
            </Text>
            {ratings && ratings.average_score > 0 ? (
              <TouchableOpacity
                style={styles.ratingBadge}
                onPress={() => setReviewsModalVisible(true)}
              >
                <Ionicons name="star" size={14} color="#FFB800" />
                <Text style={styles.ratingScoreText}>
                  {ratings.average_score.toFixed(1)} ({ratings.total_reviews_count})
                </Text>
              </TouchableOpacity>
            ) : null}
          </View>

          {/* Action Buttons: Directions, Message, Reviews */}
          <View style={styles.actionButtonsRow}>
            <TouchableOpacity
              style={[styles.actionBtn, styles.actionBtnPrimary]}
              onPress={() => {
                if (storeInfo) {
                  openMapDirections(storeInfo.lat, storeInfo.lng, storeInfo.name);
                } else {
                  Alert.alert(t('common.info', 'Info'), t('shop.location_unavailable', 'Store location not available'));
                }
              }}
            >
              <Ionicons name="navigate-outline" size={18} color="#FFF" />
              <Text style={styles.actionBtnTextPrimary}>{t('common.directions', 'Directions')}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.actionBtn, styles.actionBtnSecondary]}
              onPress={handleMessageShop}
            >
              <Ionicons name="chatbubble-outline" size={18} color={Colors.primary} />
              <Text style={styles.actionBtnTextSecondary}>{t('common.message', 'Message')}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.actionBtn, styles.actionBtnSecondary]}
              onPress={() => setReviewsModalVisible(true)}
            >
              <Ionicons name="star-outline" size={18} color={Colors.warning} />
              <Text style={styles.actionBtnTextSecondary}>{t('common.reviews', 'Reviews')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {categories.length > 0 ? (
          <>
            {/* Category Tabs */}
            <View style={styles.tabsContainer}>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabsScroll}>
                <TouchableOpacity
                  style={[styles.tabBtn, activeCategory === 'All' && styles.tabBtnActive]}
                  onPress={() => setActiveCategory('All')}
                >
                  <Text style={[styles.tabText, activeCategory === 'All' && styles.tabTextActive]}>
                    {t('dashboard.filter_all', 'All')}
                  </Text>
                </TouchableOpacity>
                {categories.map((cat) => {
                  const catFirstItem = catalog[cat]?.[0];
                  const catDisplayName = isAr
                    ? (catFirstItem?.category_name_ar || cat)
                    : (catFirstItem?.category_name_en || cat);

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
            <View style={styles.gridContainer}>
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
                        <Text style={styles.priceText}>
                          {item.price ? formatPrice(item.price) : 'السعر عند الطلب'}
                        </Text>
                      </View>
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          </>
        ) : null}
      </ScrollView>

      {/* ════════ MODAL: Reviews List ════════ */}
      <Modal visible={reviewsModalVisible} animationType="slide" transparent onRequestClose={() => setReviewsModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('shop.reviews_title', 'Reviews')} ({ratings?.total_reviews_count || 0})</Text>
              <TouchableOpacity onPress={() => setReviewsModalVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>

            <View style={{ padding: Spacing.lg, flex: 1 }}>
              <TouchableOpacity
                style={{
                  backgroundColor: Colors.primary,
                  paddingVertical: 12,
                  borderRadius: BorderRadius.md,
                  alignItems: 'center',
                  marginBottom: Spacing.md,
                }}
                onPress={() => {
                  setReviewsModalVisible(false);
                  setWriteReviewModalVisible(true);
                }}
              >
                <Text style={{ color: '#FFF', fontWeight: '700', fontSize: 14 }}>{t('shop.add_review', '+ Add Your Review')}</Text>
              </TouchableOpacity>

              <FlatList
                data={ratings?.ratings || []}
                keyExtractor={(item) => item.id}
                renderItem={({ item }) => (
                  <View style={styles.reviewCard}>
                    <View style={styles.reviewHeader}>
                      <Text style={styles.reviewerName}>{item.customer_name}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                        <Ionicons name="star" size={14} color="#FFB800" />
                        <Text style={{ fontSize: 13, fontWeight: '700', color: Colors.warning }}>{item.score}</Text>
                      </View>
                    </View>
                    {item.review ? <Text style={styles.reviewText}>{item.review}</Text> : null}
                    <Text style={styles.reviewDate}>
                      {new Date(item.created_at).toLocaleDateString(isAr ? 'ar-EG' : 'en-US')}
                    </Text>
                  </View>
                )}
                ListEmptyComponent={
                  <Text style={{ textAlign: 'center', color: Colors.textMuted, marginTop: 40 }}>
                    {t('shop.no_reviews', 'No reviews yet for this store')}
                  </Text>
                }
              />
            </View>
          </SafeAreaView>
        </View>
      </Modal>

      {/* ════════ MODAL: Write Review ════════ */}
      <Modal visible={writeReviewModalVisible} animationType="slide" transparent onRequestClose={() => setWriteReviewModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={[styles.modalContainer, { height: '55%' }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('shop.write_review', 'Write a Review')}</Text>
              <TouchableOpacity onPress={() => setWriteReviewModalVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>

            <View style={{ padding: Spacing.xl }}>
              <Text style={{ ...Typography.body, color: Colors.textSecondary, marginBottom: Spacing.md, textAlign: 'center' }}>
                {t('shop.select_stars', 'Select your rating (must be near the store)')}
              </Text>

              {/* Star selector */}
              <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 12, marginBottom: Spacing.xl }}>
                {[1, 2, 3, 4, 5].map((star) => (
                  <TouchableOpacity key={star} onPress={() => setRatingScore(star)}>
                    <Ionicons
                      name={star <= ratingScore ? 'star' : 'star-outline'}
                      size={36}
                      color="#FFB800"
                    />
                  </TouchableOpacity>
                ))}
              </View>

              <TextInput
                style={{
                  backgroundColor: Colors.surfaceElevated,
                  borderRadius: BorderRadius.lg,
                  padding: Spacing.md,
                  color: Colors.textPrimary,
                  borderWidth: 1,
                  borderColor: Colors.border,
                  height: 90,
                  textAlignVertical: 'top',
                  marginBottom: Spacing.xl,
                }}
                placeholder={t('shop.review_placeholder', 'Share your experience (optional)...')}
                placeholderTextColor={Colors.textMuted}
                multiline
                value={reviewText}
                onChangeText={setReviewText}
              />

              <TouchableOpacity
                style={{
                  backgroundColor: Colors.primary,
                  paddingVertical: 14,
                  borderRadius: BorderRadius.lg,
                  alignItems: 'center',
                  opacity: submittingReview ? 0.7 : 1,
                }}
                onPress={handleSubmitReview}
                disabled={submittingReview}
              >
                {submittingReview ? (
                  <ActivityIndicator size="small" color="#FFF" />
                ) : (
                  <Text style={{ color: '#FFF', fontWeight: '700', fontSize: 15 }}>{t('shop.submit_review', 'Submit Review')}</Text>
                )}
              </TouchableOpacity>
            </View>
          </SafeAreaView>
        </View>
      </Modal>

    </SafeAreaView>
  );
}
