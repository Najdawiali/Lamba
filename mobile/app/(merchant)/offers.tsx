/**
 * Merchant Offers Management Screen
 * Complete CRUD management for store offers and promotions.
 */

import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Switch,
  RefreshControl,
  Image,
  Modal,
  TextInput,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import {
  OfferResponse,
  OfferCreatePayload,
  MarketItemDashboardResponse,
} from '../../services/api';
import {
  useMarketItems,
  useOffers,
  useCreateOffer,
  useUpdateOffer,
  useDeleteOffer,
} from '../../hooks/useMerchant';
import { useQueryClient } from '@tanstack/react-query';
import { formatPrice } from '../../services/currency';
import { t, i18n } from '../../services/i18n';
import { useThemeColors } from '../../context/ThemeContext';
import { Spacing, BorderRadius, Typography, Shadows, TAB_BAR_OVERFLOW } from '../../constants/theme';
import { resolveImageUrl } from '../../services/utils';

type OfferTypeKey = 'percentage' | 'fixed_amount' | 'buy_x_get_y' | 'quantity_price';

interface OfferTypeMeta {
  key: OfferTypeKey;
  labelAr: string;
  labelEn: string;
  subtitleAr: string;
  subtitleEn: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
}

const OFFER_TYPES_CONFIG: Record<OfferTypeKey, OfferTypeMeta> = {
  percentage: {
    key: 'percentage',
    labelAr: 'نسبة تخفيض',
    labelEn: 'Percentage Discount',
    subtitleAr: 'مثال: خصم 20%',
    subtitleEn: 'e.g. 20% off',
    icon: 'pricetag-outline',
    color: '#00D68F',
    bg: 'rgba(0, 217, 126, 0.12)',
  },
  fixed_amount: {
    key: 'fixed_amount',
    labelAr: 'تخفيض ثابت',
    labelEn: 'Fixed Discount',
    subtitleAr: 'مثال: خصم 0.50 دينار',
    subtitleEn: 'e.g. 0.50 JOD off',
    icon: 'cash-outline',
    color: '#6C63FF',
    bg: 'rgba(108, 99, 255, 0.12)',
  },
  buy_x_get_y: {
    key: 'buy_x_get_y',
    labelAr: 'اشتر واحصل',
    labelEn: 'Buy X Get Y',
    subtitleAr: 'مثال: اشتر 2 واحصل على 1',
    subtitleEn: 'e.g. Buy 2 Get 1 Free',
    icon: 'gift-outline',
    color: '#9C27B0',
    bg: 'rgba(156, 39, 176, 0.12)',
  },
  quantity_price: {
    key: 'quantity_price',
    labelAr: 'سعر الكمية',
    labelEn: 'Quantity Bundle',
    subtitleAr: 'مثال: 3 بـ 5 دينار',
    subtitleEn: 'e.g. 3 for 5 JOD',
    icon: 'layers-outline',
    color: '#FF9800',
    bg: 'rgba(255, 152, 0, 0.12)',
  },
};

export default function MerchantOffersScreen() {
  const Colors = useThemeColors();
  const isAr = i18n.locale?.startsWith('ar');

  // Query & Mutation hooks
  const queryClient = useQueryClient();
  const { data: offers = [], isLoading: offersLoading } = useOffers();
  const { data: products = [], isLoading: productsLoading } = useMarketItems();
  const loading = offersLoading || productsLoading;
  const [refreshing, setRefreshing] = useState(false);

  const createOfferMutation = useCreateOffer();
  const updateOfferMutation = useUpdateOffer();
  const deleteOfferMutation = useDeleteOffer();

  // Create Modal state
  const [modalVisible, setModalVisible] = useState(false);
  const [createStep, setCreateStep] = useState<1 | 2 | 3>(1);
  const [searchProductQuery, setSearchProductQuery] = useState('');
  const [selectedProduct, setSelectedProduct] = useState<MarketItemDashboardResponse | null>(null);
  const [selectedOfferType, setSelectedOfferType] = useState<OfferTypeKey>('percentage');

  // Form Inputs
  const [percentInput, setPercentInput] = useState('');
  const [amountInput, setAmountInput] = useState('');
  const [buyInput, setBuyInput] = useState('');
  const [getInput, setGetInput] = useState('');
  const [quantityInput, setQuantityInput] = useState('');
  const [priceInput, setPriceInput] = useState('');
  const [descriptionInput, setDescriptionInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionInProgressId, setActionInProgressId] = useState<string | null>(null);

  // ── Pull to Refresh ───────────────────────────────────────────
  const onRefresh = async () => {
    setRefreshing(true);
    await queryClient.invalidateQueries({ queryKey: ['merchant'] });
    setRefreshing(false);
  };

  // ── Reset Create Form ─────────────────────────────────────────
  const resetCreateForm = () => {
    setCreateStep(1);
    setSearchProductQuery('');
    setSelectedProduct(null);
    setSelectedOfferType('percentage');
    setPercentInput('');
    setAmountInput('');
    setBuyInput('');
    setGetInput('');
    setQuantityInput('');
    setPriceInput('');
    setDescriptionInput('');
    setSubmitting(false);
  };

  const openCreateModal = () => {
    resetCreateForm();
    setModalVisible(true);
  };

  const closeCreateModal = () => {
    setModalVisible(false);
    resetCreateForm();
  };

  // ── Toggle Active / Inactive ──────────────────────────────────
  const handleToggleActive = async (offer: OfferResponse) => {
    const newActive = !offer.is_active;
    setActionInProgressId(offer.id);
    try {
      await updateOfferMutation.mutateAsync({
        offerId: offer.id,
        payload: { is_active: newActive },
      });
    } catch (err: any) {
      Alert.alert(
        isAr ? 'خطأ' : 'Error',
        err?.response?.data?.detail ||
          (isAr ? 'فشل تحديث حالة العرض' : 'Failed to update offer status')
      );
    } finally {
      setActionInProgressId(null);
    }
  };

  // ── Delete Offer ──────────────────────────────────────────────
  const handleDeleteOffer = (offer: OfferResponse) => {
    const title = isAr ? 'حذف العرض' : 'Delete Offer';
    const message = isAr
      ? `هل أنت متأكد من رغبتك في حذف عرض "${offer.item_name_ar || offer.item_name || 'المنتج'}"؟`
      : `Are you sure you want to delete this offer?`;

    Alert.alert(title, message, [
      { text: isAr ? 'إلغاء' : 'Cancel', style: 'cancel' },
      {
        text: isAr ? 'حذف' : 'Delete',
        style: 'destructive',
        onPress: async () => {
          setActionInProgressId(offer.id);
          try {
            await deleteOfferMutation.mutateAsync(offer.id);
          } catch (err: any) {
            Alert.alert(
              isAr ? 'خطأ' : 'Error',
              err?.response?.data?.detail ||
                (isAr ? 'فشل حذف العرض' : 'Failed to delete offer')
            );
          } finally {
            setActionInProgressId(null);
          }
        },
      },
    ]);
  };

  // ── Submit Create Offer ───────────────────────────────────────
  const handleSubmitOffer = async () => {
    if (!selectedProduct) {
      Alert.alert(
        isAr ? 'تنبيه' : 'Alert',
        isAr ? 'يرجى اختيار منتج أولاً' : 'Please select a product first'
      );
      setCreateStep(1);
      return;
    }

    let config: Record<string, any> = {};

    if (selectedOfferType === 'percentage') {
      const p = parseFloat(percentInput.trim());
      if (isNaN(p) || p <= 0 || p > 100) {
        Alert.alert(
          isAr ? 'قيمة غير صحيحة' : 'Invalid Value',
          isAr
            ? 'يرجى إدخال نسبة خصم صحيحة بين 1% و 100%'
            : 'Please enter a valid discount percentage between 1 and 100'
        );
        return;
      }
      config = { percent: p };
    } else if (selectedOfferType === 'fixed_amount') {
      const a = parseFloat(amountInput.trim());
      if (isNaN(a) || a <= 0) {
        Alert.alert(
          isAr ? 'قيمة غير صحيحة' : 'Invalid Value',
          isAr
            ? 'يرجى إدخال مبلغ خصم أكبر من صفر'
            : 'Please enter a discount amount greater than 0'
        );
        return;
      }
      if (selectedProduct.price && a >= selectedProduct.price) {
        Alert.alert(
          isAr ? 'تنبيه' : 'Warning',
          isAr
            ? 'مبلغ الخصم يجب أن يكون أقل من سعر المنتج الأصلي'
            : 'Discount amount must be less than the original price'
        );
        return;
      }
      config = { amount: a };
    } else if (selectedOfferType === 'buy_x_get_y') {
      const b = parseInt(buyInput.trim(), 10);
      const g = parseInt(getInput.trim(), 10);
      if (isNaN(b) || b < 1 || isNaN(g) || g < 1) {
        Alert.alert(
          isAr ? 'قيمة غير صحيحة' : 'Invalid Value',
          isAr
            ? 'يرجى إدخال أعداد صحيحة (1 أو أكثر) لكل من كمية الشراء والهدية'
            : 'Please enter valid quantities (>= 1) for buy and get'
        );
        return;
      }
      config = { buy: b, get: g };
    } else if (selectedOfferType === 'quantity_price') {
      const q = parseInt(quantityInput.trim(), 10);
      const pr = parseFloat(priceInput.trim());
      if (isNaN(q) || q < 2) {
        Alert.alert(
          isAr ? 'قيمة غير صحيحة' : 'Invalid Value',
          isAr
            ? 'يرجى إدخال كمية صحيحة (2 أو أكثر)'
            : 'Please enter a valid quantity of 2 or more'
        );
        return;
      }
      if (isNaN(pr) || pr <= 0) {
        Alert.alert(
          isAr ? 'قيمة غير صحيحة' : 'Invalid Value',
          isAr
            ? 'يرجى إدخال سعر إجمالي صحيح أكبر من صفر'
            : 'Please enter a valid total price greater than 0'
        );
        return;
      }
      config = { quantity: q, price: pr };
    }

    const payload: OfferCreatePayload = {
      market_item_id: selectedProduct.id,
      offer_type: selectedOfferType,
      config,
      description: descriptionInput.trim() || undefined,
    };

    setSubmitting(true);
    try {
      await createOfferMutation.mutateAsync(payload);
      closeCreateModal();
      Alert.alert(
        isAr ? 'تم بنجاح' : 'Success',
        isAr
          ? 'تم إنشاء العرض ونشره بنجاح في متجرك'
          : 'Offer has been published successfully!'
      );
    } catch (err: any) {
      Alert.alert(
        isAr ? 'خطأ' : 'Error',
        err?.response?.data?.detail ||
          (isAr
            ? 'فشل إنشاء العرض، يرجى المحاولة مرة أخرى'
            : 'Failed to create offer. Please try again.')
      );
    } finally {
      setSubmitting(false);
    }
  };

  // ── Offer Readable Summary Helper ─────────────────────────────
  const getOfferSummary = (offer: OfferResponse): string => {
    switch (offer.offer_type) {
      case 'percentage':
        return isAr
          ? `خصم ${offer.config?.percent ?? 0}%`
          : `${offer.config?.percent ?? 0}% off`;
      case 'fixed_amount':
        return isAr
          ? `خصم ${offer.config?.amount ?? 0} دينار`
          : `${offer.config?.amount ?? 0} JOD off`;
      case 'buy_x_get_y':
        return isAr
          ? `اشتر ${offer.config?.buy ?? 0} واحصل على ${offer.config?.get ?? 0} مجاناً`
          : `Buy ${offer.config?.buy ?? 0} Get ${offer.config?.get ?? 0} Free`;
      case 'quantity_price':
        return isAr
          ? `${offer.config?.quantity ?? 0} بـ ${offer.config?.price ?? 0} دينار`
          : `${offer.config?.quantity ?? 0} for ${offer.config?.price ?? 0} JOD`;
      default:
        return '';
    }
  };

  // ── Filter Products for Step 1 ────────────────────────────────
  const filteredProducts = useMemo(() => {
    if (!searchProductQuery.trim()) return products;
    const q = searchProductQuery.toLowerCase().trim();
    return products.filter((p) => {
      const name = (p.name || '').toLowerCase();
      const cat = (p.category || '').toLowerCase();
      return name.includes(q) || cat.includes(q);
    });
  }, [products, searchProductQuery]);

  // ── Render Single Offer Card ──────────────────────────────────
  const renderOfferCard = ({ item }: { item: OfferResponse }) => {
    const meta =
      OFFER_TYPES_CONFIG[item.offer_type as OfferTypeKey] ||
      OFFER_TYPES_CONFIG.percentage;
    const productName = item.item_name_ar || item.item_name || (isAr ? 'منتج غير معروف' : 'Item');
    const summary = getOfferSummary(item);
    const resolvedImg = resolveImageUrl(item.item_image_url);

    return (
      <View
        style={[
          styles.offerCard,
          {
            backgroundColor: Colors.surface,
            borderColor: item.is_active ? Colors.border : 'rgba(150, 150, 150, 0.2)',
            opacity: item.is_active ? 1 : 0.72,
          },
        ]}
      >
        {/* Card Header: Image + Product Info + Badge */}
        <View style={[styles.cardHeader, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
          {resolvedImg ? (
            <Image source={{ uri: resolvedImg }} style={styles.productThumbnail} />
          ) : (
            <View style={[styles.productThumbnailPlaceholder, { backgroundColor: Colors.border }]}>
              <Ionicons name="cube-outline" size={24} color={Colors.textMuted} />
            </View>
          )}

          <View style={[styles.productDetails, { alignItems: isAr ? 'flex-end' : 'flex-start' }]}>
            <View style={[styles.badgeAndStatusRow, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
              <View style={[styles.typeBadge, { backgroundColor: meta.bg }]}>
                <Ionicons name={meta.icon} size={12} color={meta.color} style={{ marginRight: 4 }} />
                <Text style={[styles.typeBadgeText, { color: meta.color }]}>
                  {isAr ? meta.labelAr : meta.labelEn}
                </Text>
              </View>

              {!item.is_active && (
                <View style={[styles.inactiveBadge, { backgroundColor: 'rgba(150, 150, 150, 0.15)' }]}>
                  <Text style={[styles.inactiveBadgeText, { color: Colors.textMuted }]}>
                    {isAr ? 'معطل' : 'Inactive'}
                  </Text>
                </View>
              )}
            </View>

            <Text
              style={[
                styles.productName,
                { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
              ]}
              numberOfLines={2}
            >
              {productName}
            </Text>

            {item.item_price !== null && item.item_price !== undefined && (
              <Text style={[styles.originalPrice, { color: Colors.textMuted }]}>
                {isAr ? 'السعر الأصلي:' : 'Original:'}{' '}
                <Text style={{ color: Colors.textSecondary, fontWeight: '600' }}>
                  {formatPrice(item.item_price)}
                </Text>
              </Text>
            )}
          </View>
        </View>

        {/* Offer Summary Banner */}
        <View
          style={[
            styles.summaryBanner,
            {
              backgroundColor: meta.bg,
              borderLeftColor: isAr ? 'transparent' : meta.color,
              borderRightColor: isAr ? meta.color : 'transparent',
              flexDirection: isAr ? 'row-reverse' : 'row',
            },
          ]}
        >
          <Ionicons name={meta.icon} size={18} color={meta.color} />
          <Text
            style={[
              styles.summaryText,
              { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
            ]}
          >
            {summary}
          </Text>
        </View>

        {/* Optional Description */}
        {!!item.description && (
          <Text
            style={[
              styles.offerDescription,
              { color: Colors.textSecondary, textAlign: isAr ? 'right' : 'left' },
            ]}
            numberOfLines={2}
          >
            {item.description}
          </Text>
        )}

        {/* Card Footer: Toggle Switch + Delete Button */}
        <View
          style={[
            styles.cardFooter,
            {
              borderTopColor: Colors.border,
              flexDirection: isAr ? 'row-reverse' : 'row',
            },
          ]}
        >
          {/* Active Switch */}
          <View style={[styles.toggleContainer, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
            <Switch
              value={item.is_active}
              onValueChange={() => handleToggleActive(item)}
              disabled={actionInProgressId === item.id}
              trackColor={{
                false: Colors.toggleInactive || '#333333',
                true: Colors.toggleOfferActive || Colors.primary,
              }}
              thumbColor="#FFFFFF"
              ios_backgroundColor={Colors.toggleInactive || '#333333'}
            />
            <Text style={[styles.toggleLabel, { color: item.is_active ? Colors.textPrimary : Colors.textMuted }]}>
              {item.is_active ? (isAr ? 'العرض نشط' : 'Active') : (isAr ? 'العرض متوقف' : 'Paused')}
            </Text>
          </View>

          {/* Delete Button */}
          <TouchableOpacity
            style={styles.deleteButton}
            onPress={() => handleDeleteOffer(item)}
            disabled={actionInProgressId === item.id}
            activeOpacity={0.7}
          >
            <Ionicons name="trash-outline" size={20} color={Colors.error} />
            <Text style={[styles.deleteButtonText, { color: Colors.error }]}>
              {isAr ? 'حذف' : 'Delete'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  // ── Render Empty State ────────────────────────────────────────
  const renderEmptyState = () => (
    <View style={styles.emptyContainer}>
      <View style={[styles.emptyIconCircle, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
        <Ionicons name="pricetags-outline" size={48} color={Colors.primary} />
      </View>
      <Text style={[styles.emptyTitle, { color: Colors.textPrimary }]}>
        {isAr ? 'لا توجد عروض بعد' : 'No Offers Yet'}
      </Text>
      <Text style={[styles.emptySubtitle, { color: Colors.textMuted }]}>
        {isAr
          ? 'أنشئ عروضاً وخصومات لجذب زبائن جدد وزيادة مبيعات متجرك'
          : 'Create promotions and discounts to attract more shoppers to your store.'}
      </Text>
      <TouchableOpacity
        style={[styles.emptyCreateButton, { backgroundColor: Colors.primary }]}
        onPress={openCreateModal}
        activeOpacity={0.8}
      >
        <Ionicons name="add-circle-outline" size={20} color="#FFFFFF" style={{ marginRight: 6 }} />
        <Text style={styles.emptyCreateButtonText}>
          {isAr ? 'إنشاء أول عرض' : 'Create First Offer'}
        </Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: Colors.background }]} edges={['top']}>
      {/* Screen Header */}
      <View style={[styles.header, { borderBottomColor: Colors.border }]}>
        <View style={{ alignItems: isAr ? 'flex-end' : 'flex-start' }}>
          <Text
            style={[styles.headerTitle, { color: Colors.textPrimary }]}
            numberOfLines={1}
            adjustsFontSizeToFit
          >
            {t('offers.title', 'Special Offers')}
          </Text>
          <Text style={[styles.headerSubtitle, { color: Colors.textMuted }]}>
            {t('offers.subtitle', 'Manage your store promotions')}
          </Text>
        </View>
      </View>

      {/* Main List / Loading */}
      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.primary} />
          <Text style={[styles.loadingText, { color: Colors.textMuted }]}>
            {isAr ? 'جاري تحميل العروض...' : 'Loading offers...'}
          </Text>
        </View>
      ) : (
        <FlatList
          data={offers}
          keyExtractor={(item) => item.id}
          renderItem={renderOfferCard}
          contentContainerStyle={[
            styles.listContent,
            offers.length === 0 && styles.flexGrow,
          ]}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={Colors.primary}
              colors={[Colors.primary]}
            />
          }
          ListEmptyComponent={renderEmptyState}
        />
      )}

      {/* FAB: Green circle with white "+" bottom-right */}
      {offers.length > 0 && (
        <TouchableOpacity
          style={[styles.fab, { backgroundColor: Colors.tabActive }]}
          onPress={openCreateModal}
          activeOpacity={0.85}
        >
          <Ionicons name="add" size={32} color="#FFFFFF" />
        </TouchableOpacity>
      )}

      {/* ── CREATE OFFER 3-STEP MODAL ────────────────────────────── */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={closeCreateModal}
      >
        <SafeAreaView style={[styles.modalSafeArea, { backgroundColor: Colors.background }]}>
          {/* Modal Header */}
          <View style={[styles.modalHeader, { borderBottomColor: Colors.border }]}>
            <View style={styles.modalHeaderRow}>
              {createStep > 1 ? (
                <TouchableOpacity
                  style={styles.modalBackButton}
                  onPress={() => setCreateStep((prev) => (prev - 1) as 1 | 2)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <Ionicons
                    name={isAr ? 'arrow-forward' : 'arrow-back'}
                    size={24}
                    color={Colors.textPrimary}
                  />
                </TouchableOpacity>
              ) : (
                <View style={{ width: 32 }} />
              )}

              <View style={{ alignItems: 'center' }}>
                <Text style={[styles.modalTitle, { color: Colors.textPrimary }]}>
                  {createStep === 1 && (isAr ? 'اختر المنتج' : 'Select Product')}
                  {createStep === 2 && (isAr ? 'نوع العرض' : 'Offer Type')}
                  {createStep === 3 && (isAr ? 'تفاصيل العرض' : 'Offer Details')}
                </Text>
                <Text style={[styles.stepIndicator, { color: Colors.textMuted }]}>
                  {isAr ? `خطوة ${createStep} من 3` : `Step ${createStep} of 3`}
                </Text>
              </View>

              <TouchableOpacity
                style={styles.modalCloseButton}
                onPress={closeCreateModal}
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              >
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
          </View>

          {/* ── STEP 1: PICK PRODUCT ───────────────────────────── */}
          {createStep === 1 && (
            <View style={styles.stepContainer}>
              {/* Product Search Bar */}
              <View
                style={[
                  styles.searchBarContainer,
                  {
                    backgroundColor: Colors.surface,
                    borderColor: Colors.border,
                    flexDirection: isAr ? 'row-reverse' : 'row',
                  },
                ]}
              >
                <Ionicons name="search-outline" size={20} color={Colors.textMuted} />
                <TextInput
                  style={[
                    styles.searchInput,
                    {
                      color: Colors.textPrimary,
                      textAlign: isAr ? 'right' : 'left',
                    },
                  ]}
                  placeholder={
                    isAr
                      ? 'ابحث باسم المنتج أو الصنف...'
                      : 'Search by product name or category...'
                  }
                  placeholderTextColor={Colors.textMuted}
                  value={searchProductQuery}
                  onChangeText={setSearchProductQuery}
                  clearButtonMode="while-editing"
                />
                {!!searchProductQuery && (
                  <TouchableOpacity onPress={() => setSearchProductQuery('')}>
                    <Ionicons name="close-circle" size={18} color={Colors.textMuted} />
                  </TouchableOpacity>
                )}
              </View>

              {/* Product Selection List */}
              <FlatList
                data={filteredProducts}
                keyExtractor={(item) => item.id}
                contentContainerStyle={styles.pickerListContent}
                renderItem={({ item }) => {
                  const resolvedImg = resolveImageUrl(item.image_url);
                  return (
                    <TouchableOpacity
                      style={[
                        styles.productPickRow,
                        {
                          backgroundColor: Colors.surface,
                          borderColor: Colors.border,
                          flexDirection: isAr ? 'row-reverse' : 'row',
                        },
                      ]}
                      onPress={() => {
                        setSelectedProduct(item);
                        setCreateStep(2);
                      }}
                      activeOpacity={0.7}
                    >
                      {resolvedImg ? (
                        <Image source={{ uri: resolvedImg }} style={styles.pickThumbnail} />
                      ) : (
                        <View
                          style={[
                            styles.pickThumbnailPlaceholder,
                            { backgroundColor: Colors.border },
                          ]}
                        >
                          <Ionicons name="cube-outline" size={20} color={Colors.textMuted} />
                        </View>
                      )}

                      <View
                        style={[
                          styles.pickProductInfo,
                          { alignItems: isAr ? 'flex-end' : 'flex-start' },
                        ]}
                      >
                        <Text
                          style={[
                            styles.pickProductName,
                            { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
                          ]}
                          numberOfLines={1}
                        >
                          {item.name}
                        </Text>
                        <Text style={[styles.pickProductMeta, { color: Colors.textMuted }]}>
                          {item.category || (isAr ? 'منتج عام' : 'General')} • {isAr ? 'المتوفر:' : 'Stock:'}{' '}
                          <Text style={{ color: Colors.textSecondary, fontWeight: '600' }}>
                            {item.stock_count}
                          </Text>
                        </Text>
                      </View>

                      <View style={{ alignItems: isAr ? 'flex-start' : 'flex-end' }}>
                        <Text style={[styles.pickProductPrice, { color: Colors.primary }]}>
                          {formatPrice(item.price)}
                        </Text>
                        <Ionicons
                          name={isAr ? 'chevron-back' : 'chevron-forward'}
                          size={18}
                          color={Colors.textMuted}
                          style={{ marginTop: 4 }}
                        />
                      </View>
                    </TouchableOpacity>
                  );
                }}
                ListEmptyComponent={
                  <View style={styles.emptyPickerContainer}>
                    <Ionicons name="search" size={36} color={Colors.textMuted} />
                    <Text style={[styles.emptyPickerText, { color: Colors.textMuted }]}>
                      {isAr
                        ? 'لم يتم العثور على منتجات مطابقة'
                        : 'No matching products found'}
                    </Text>
                  </View>
                }
              />
            </View>
          )}

          {/* ── STEP 2: PICK OFFER TYPE ────────────────────────── */}
          {createStep === 2 && (
            <ScrollView style={styles.stepContainer} contentContainerStyle={styles.stepContentScroll}>
              {/* Selected Product Context Banner */}
              {selectedProduct && (
                <View
                  style={[
                    styles.contextCard,
                    {
                      backgroundColor: Colors.surface,
                      borderColor: Colors.border,
                      flexDirection: isAr ? 'row-reverse' : 'row',
                    },
                  ]}
                >
                  <View
                    style={[
                      styles.contextInfo,
                      { alignItems: isAr ? 'flex-end' : 'flex-start' },
                    ]}
                  >
                    <Text style={[styles.contextLabel, { color: Colors.textMuted }]}>
                      {isAr ? 'المنتج المحدد' : 'Selected Product'}
                    </Text>
                    <Text style={[styles.contextName, { color: Colors.textPrimary }]} numberOfLines={1}>
                      {selectedProduct.name}
                    </Text>
                  </View>
                  <Text style={[styles.contextPrice, { color: Colors.primary }]}>
                    {formatPrice(selectedProduct.price)}
                  </Text>
                </View>
              )}

              <Text
                style={[
                  styles.sectionInstruction,
                  { color: Colors.textSecondary, textAlign: isAr ? 'right' : 'left' },
                ]}
              >
                {isAr
                  ? 'اختر نوع العرض المناسب لترويج هذا المنتج:'
                  : 'Choose the offer structure for this product:'}
              </Text>

              {/* 4 Offer Type Cards */}
              {(Object.keys(OFFER_TYPES_CONFIG) as OfferTypeKey[]).map((key) => {
                const meta = OFFER_TYPES_CONFIG[key];
                return (
                  <TouchableOpacity
                    key={key}
                    style={[
                      styles.typeCard,
                      {
                        backgroundColor: Colors.surface,
                        borderColor: Colors.border,
                        flexDirection: isAr ? 'row-reverse' : 'row',
                      },
                    ]}
                    onPress={() => {
                      setSelectedOfferType(key);
                      setCreateStep(3);
                    }}
                    activeOpacity={0.75}
                  >
                    {/* Icon Container */}
                    <View style={[styles.typeIconContainer, { backgroundColor: meta.bg }]}>
                      <Ionicons name={meta.icon} size={26} color={meta.color} />
                    </View>

                    {/* Titles */}
                    <View
                      style={[
                        styles.typeTextContainer,
                        { alignItems: isAr ? 'flex-end' : 'flex-start' },
                      ]}
                    >
                      <Text style={[styles.typeCardTitle, { color: Colors.textPrimary }]}>
                        {isAr ? meta.labelAr : meta.labelEn}
                      </Text>
                      <Text style={[styles.typeCardSubtitle, { color: Colors.textMuted }]}>
                        {isAr ? meta.subtitleAr : meta.subtitleEn}
                      </Text>
                    </View>

                    {/* Action Arrow */}
                    <Ionicons
                      name={isAr ? 'chevron-back' : 'chevron-forward'}
                      size={20}
                      color={Colors.textMuted}
                    />
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          )}

          {/* ── STEP 3: CONFIGURE AND SUBMIT ───────────────────── */}
          {createStep === 3 && (
            <KeyboardAvoidingView
              behavior={Platform.OS === 'ios' ? 'padding' : undefined}
              style={{ flex: 1 }}
            >
              <ScrollView style={styles.stepContainer} contentContainerStyle={styles.stepContentScroll}>
                {/* Context Card: Product + Type Badge */}
                {selectedProduct && (
                  <View
                    style={[
                      styles.contextCard,
                      {
                        backgroundColor: Colors.surface,
                        borderColor: Colors.border,
                        flexDirection: isAr ? 'row-reverse' : 'row',
                      },
                    ]}
                  >
                    <View
                      style={[
                        styles.contextInfo,
                        { alignItems: isAr ? 'flex-end' : 'flex-start' },
                      ]}
                    >
                      <Text style={[styles.contextName, { color: Colors.textPrimary }]} numberOfLines={1}>
                        {selectedProduct.name}
                      </Text>
                      <View
                        style={[
                          styles.typeBadge,
                          {
                            backgroundColor: OFFER_TYPES_CONFIG[selectedOfferType].bg,
                            marginTop: 4,
                          },
                        ]}
                      >
                        <Text
                          style={[
                            styles.typeBadgeText,
                            { color: OFFER_TYPES_CONFIG[selectedOfferType].color },
                          ]}
                        >
                          {isAr
                            ? OFFER_TYPES_CONFIG[selectedOfferType].labelAr
                            : OFFER_TYPES_CONFIG[selectedOfferType].labelEn}
                        </Text>
                      </View>
                    </View>
                    <Text style={[styles.contextPrice, { color: Colors.primary }]}>
                      {formatPrice(selectedProduct.price)}
                    </Text>
                  </View>
                )}

                {/* ── Type 1: Percentage ─────────────────────── */}
                {selectedOfferType === 'percentage' && (
                  <View style={styles.formGroup}>
                    <Text
                      style={[
                        styles.inputLabel,
                        { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
                      ]}
                    >
                      {isAr ? 'نسبة الخصم (%) *' : 'Discount Percentage (%) *'}
                    </Text>
                    <TextInput
                      style={[
                        styles.textInput,
                        {
                          backgroundColor: Colors.surface,
                          borderColor: Colors.border,
                          color: Colors.textPrimary,
                          textAlign: isAr ? 'right' : 'left',
                        },
                      ]}
                      keyboardType="number-pad"
                      placeholder={isAr ? 'مثال: 20، 50، 75' : 'e.g. 20, 50, 75'}
                      placeholderTextColor={Colors.textMuted}
                      value={percentInput}
                      onChangeText={setPercentInput}
                    />

                    {/* Preview Calculation */}
                    {!!percentInput && !isNaN(parseFloat(percentInput)) && selectedProduct?.price && (
                      <View style={[styles.previewBox, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
                        <Text style={[styles.previewLabel, { color: Colors.textMuted }]}>
                          {isAr ? 'معاينة سعر الزبون بعد الخصم:' : 'Customer price after discount:'}
                        </Text>
                        <Text style={[styles.previewValue, { color: Colors.success }]}>
                          {formatPrice(
                            Math.max(
                              0,
                              selectedProduct.price * (1 - parseFloat(percentInput) / 100)
                            )
                          )}
                        </Text>
                      </View>
                    )}
                  </View>
                )}

                {/* ── Type 2: Fixed Amount ───────────────────── */}
                {selectedOfferType === 'fixed_amount' && (
                  <View style={styles.formGroup}>
                    <Text
                      style={[
                        styles.inputLabel,
                        { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
                      ]}
                    >
                      {isAr ? 'مبلغ الخصم (دينار) *' : 'Discount Amount (JOD) *'}
                    </Text>
                    <TextInput
                      style={[
                        styles.textInput,
                        {
                          backgroundColor: Colors.surface,
                          borderColor: Colors.border,
                          color: Colors.textPrimary,
                          textAlign: isAr ? 'right' : 'left',
                        },
                      ]}
                      keyboardType="decimal-pad"
                      placeholder={isAr ? 'مثال: 0.50' : 'e.g. 0.50'}
                      placeholderTextColor={Colors.textMuted}
                      value={amountInput}
                      onChangeText={setAmountInput}
                    />

                    {/* Preview Calculation */}
                    {!!amountInput && !isNaN(parseFloat(amountInput)) && selectedProduct?.price && (
                      <View style={[styles.previewBox, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
                        <Text style={[styles.previewLabel, { color: Colors.textMuted }]}>
                          {isAr ? 'معاينة سعر الزبون بعد الخصم:' : 'Customer price after discount:'}
                        </Text>
                        <Text style={[styles.previewValue, { color: Colors.success }]}>
                          {formatPrice(Math.max(0, selectedProduct.price - parseFloat(amountInput)))}
                        </Text>
                      </View>
                    )}
                  </View>
                )}

                {/* ── Type 3: Buy X Get Y ─────────────────────── */}
                {selectedOfferType === 'buy_x_get_y' && (
                  <View style={styles.formGroup}>
                    <View style={[styles.rowInputs, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
                      <View style={{ flex: 1 }}>
                        <Text
                          style={[
                            styles.inputLabel,
                            { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
                          ]}
                        >
                          {isAr ? 'اشتر (الكمية) *' : 'Buy Quantity *'}
                        </Text>
                        <TextInput
                          style={[
                            styles.textInput,
                            {
                              backgroundColor: Colors.surface,
                              borderColor: Colors.border,
                              color: Colors.textPrimary,
                              textAlign: isAr ? 'right' : 'left',
                            },
                          ]}
                          keyboardType="number-pad"
                          placeholder={isAr ? 'مثال: 2' : 'e.g. 2'}
                          placeholderTextColor={Colors.textMuted}
                          value={buyInput}
                          onChangeText={setBuyInput}
                        />
                      </View>

                      <View style={{ width: Spacing.md }} />

                      <View style={{ flex: 1 }}>
                        <Text
                          style={[
                            styles.inputLabel,
                            { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
                          ]}
                        >
                          {isAr ? 'واحصل على مجاناً *' : 'Get Free *'}
                        </Text>
                        <TextInput
                          style={[
                            styles.textInput,
                            {
                              backgroundColor: Colors.surface,
                              borderColor: Colors.border,
                              color: Colors.textPrimary,
                              textAlign: isAr ? 'right' : 'left',
                            },
                          ]}
                          keyboardType="number-pad"
                          placeholder={isAr ? 'مثال: 1' : 'e.g. 1'}
                          placeholderTextColor={Colors.textMuted}
                          value={getInput}
                          onChangeText={setGetInput}
                        />
                      </View>
                    </View>

                    {/* Preview summary text */}
                    {!!buyInput && !!getInput && (
                      <View style={[styles.previewBox, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
                        <Text style={[styles.previewValue, { color: OFFER_TYPES_CONFIG.buy_x_get_y.color }]}>
                          {isAr
                            ? `اشتر ${buyInput} واحصل على ${getInput} مجاناً`
                            : `Buy ${buyInput} Get ${getInput} Free`}
                        </Text>
                      </View>
                    )}
                  </View>
                )}

                {/* ── Type 4: Quantity Bundle ─────────────────── */}
                {selectedOfferType === 'quantity_price' && (
                  <View style={styles.formGroup}>
                    <View style={[styles.rowInputs, { flexDirection: isAr ? 'row-reverse' : 'row' }]}>
                      <View style={{ flex: 1 }}>
                        <Text
                          style={[
                            styles.inputLabel,
                            { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
                          ]}
                        >
                          {isAr ? 'الكمية *' : 'Quantity *'}
                        </Text>
                        <TextInput
                          style={[
                            styles.textInput,
                            {
                              backgroundColor: Colors.surface,
                              borderColor: Colors.border,
                              color: Colors.textPrimary,
                              textAlign: isAr ? 'right' : 'left',
                            },
                          ]}
                          keyboardType="number-pad"
                          placeholder={isAr ? 'مثال: 3' : 'e.g. 3'}
                          placeholderTextColor={Colors.textMuted}
                          value={quantityInput}
                          onChangeText={setQuantityInput}
                        />
                      </View>

                      <View style={{ width: Spacing.md }} />

                      <View style={{ flex: 1 }}>
                        <Text
                          style={[
                            styles.inputLabel,
                            { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
                          ]}
                        >
                          {isAr ? 'السعر الإجمالي (دينار) *' : 'Total Bundle Price (JOD) *'}
                        </Text>
                        <TextInput
                          style={[
                            styles.textInput,
                            {
                              backgroundColor: Colors.surface,
                              borderColor: Colors.border,
                              color: Colors.textPrimary,
                              textAlign: isAr ? 'right' : 'left',
                            },
                          ]}
                          keyboardType="decimal-pad"
                          placeholder={isAr ? 'مثال: 5.00' : 'e.g. 5.00'}
                          placeholderTextColor={Colors.textMuted}
                          value={priceInput}
                          onChangeText={setPriceInput}
                        />
                      </View>
                    </View>

                    {/* Preview summary text */}
                    {!!quantityInput && !!priceInput && (
                      <View style={[styles.previewBox, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
                        <Text style={[styles.previewValue, { color: OFFER_TYPES_CONFIG.quantity_price.color }]}>
                          {isAr
                            ? `${quantityInput} قطع بـ ${priceInput} دينار`
                            : `${quantityInput} for ${priceInput} JOD`}
                        </Text>
                      </View>
                    )}
                  </View>
                )}

                {/* Description (Optional) */}
                <View style={styles.formGroup}>
                  <Text
                    style={[
                      styles.inputLabel,
                      { color: Colors.textPrimary, textAlign: isAr ? 'right' : 'left' },
                    ]}
                  >
                    {isAr ? 'وصف العرض (اختياري)' : 'Offer Description (Optional)'}
                  </Text>
                  <TextInput
                    style={[
                      styles.textAreaInput,
                      {
                        backgroundColor: Colors.surface,
                        borderColor: Colors.border,
                        color: Colors.textPrimary,
                        textAlign: isAr ? 'right' : 'left',
                      },
                    ]}
                    multiline
                    numberOfLines={3}
                    placeholder={
                      isAr
                        ? 'اكتب شروط أو تفاصيل إضافية للعرض...'
                        : 'Enter extra conditions or details for the offer...'
                    }
                    placeholderTextColor={Colors.textMuted}
                    value={descriptionInput}
                    onChangeText={setDescriptionInput}
                  />
                </View>

                {/* Submit Action Button */}
                <TouchableOpacity
                  style={[
                    styles.submitButton,
                    { backgroundColor: Colors.tabActive },
                    submitting && { opacity: 0.7 },
                  ]}
                  onPress={handleSubmitOffer}
                  disabled={submitting}
                  activeOpacity={0.85}
                >
                  {submitting ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={styles.submitButtonText}>
                      {isAr ? 'تأكيد ونشر العرض' : 'Confirm & Publish Offer'}
                    </Text>
                  )}
                </TouchableOpacity>
              </ScrollView>
            </KeyboardAvoidingView>
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

// ── Styles ──────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    borderBottomWidth: 1,
  },
  headerTitle: {
    ...Typography.h2,
    fontSize: 20,
  },
  headerSubtitle: {
    ...Typography.caption,
    marginTop: 2,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.xl,
  },
  loadingText: {
    ...Typography.bodySmall,
    marginTop: Spacing.md,
  },
  listContent: {
    padding: Spacing.lg,
    paddingBottom: TAB_BAR_OVERFLOW,
  },
  flexGrow: {
    flexGrow: 1,
  },

  // ── Offer Card ──
  offerCard: {
    borderWidth: 1,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.lg,
    ...Shadows.small,
  },
  cardHeader: {
    alignItems: 'center',
  },
  productThumbnail: {
    width: 60,
    height: 60,
    borderRadius: BorderRadius.md,
    backgroundColor: '#333333',
  },
  productThumbnailPlaceholder: {
    width: 60,
    height: 60,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  productDetails: {
    flex: 1,
    marginHorizontal: Spacing.md,
  },
  badgeAndStatusRow: {
    alignItems: 'center',
    marginBottom: 4,
  },
  typeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 3,
    borderRadius: BorderRadius.xl,
  },
  typeBadgeText: {
    ...Typography.badge,
  },
  inactiveBadge: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
    marginHorizontal: 6,
  },
  inactiveBadgeText: {
    ...Typography.badge,
    fontSize: 10,
  },
  productName: {
    ...Typography.subheading,
    marginBottom: 2,
  },
  originalPrice: {
    ...Typography.caption,
  },
  summaryBanner: {
    marginVertical: Spacing.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.sm,
    borderLeftWidth: 3,
    borderRightWidth: 3,
    alignItems: 'center',
    gap: Spacing.sm,
  },
  summaryText: {
    ...Typography.body,
    fontWeight: '700',
    flex: 1,
  },
  offerDescription: {
    ...Typography.caption,
    marginBottom: Spacing.sm,
  },
  cardFooter: {
    borderTopWidth: 1,
    paddingTop: Spacing.md,
    marginTop: Spacing.xs,
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  toggleContainer: {
    alignItems: 'center',
    gap: Spacing.sm,
  },
  toggleLabel: {
    ...Typography.caption,
    fontWeight: '600',
  },
  deleteButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.sm,
    gap: 4,
  },
  deleteButtonText: {
    ...Typography.caption,
    fontWeight: '600',
  },

  // ── Empty State ──
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.xxxl,
  },
  emptyIconCircle: {
    width: 90,
    height: 90,
    borderRadius: 45,
    borderWidth: 1,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  emptyTitle: {
    ...Typography.h2,
    marginBottom: Spacing.xs,
  },
  emptySubtitle: {
    ...Typography.bodySmall,
    textAlign: 'center',
    marginBottom: Spacing.xl,
  },
  emptyCreateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.full,
    ...Shadows.small,
  },
  emptyCreateButtonText: {
    ...Typography.button,
    color: '#FFFFFF',
  },

  // ── FAB ──
  fab: {
    position: 'absolute',
    bottom: 20,
    right: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    justifyContent: 'center',
    alignItems: 'center',
    ...Shadows.medium,
  },

  // ── Modal ──
  modalSafeArea: {
    flex: 1,
  },
  modalHeader: {
    borderBottomWidth: 1,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
  },
  modalHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalBackButton: {
    width: 32,
    justifyContent: 'center',
  },
  modalCloseButton: {
    width: 32,
    alignItems: 'flex-end',
    justifyContent: 'center',
  },
  modalTitle: {
    ...Typography.h3,
  },
  stepIndicator: {
    ...Typography.muted,
    marginTop: 2,
  },
  stepContainer: {
    flex: 1,
  },
  stepContentScroll: {
    padding: Spacing.lg,
    paddingBottom: Spacing.xxxl,
  },

  // ── Modal Step 1: Product Picker ──
  searchBarContainer: {
    margin: Spacing.lg,
    marginBottom: Spacing.xs,
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Platform.OS === 'ios' ? Spacing.sm : 2,
    alignItems: 'center',
    gap: Spacing.sm,
  },
  searchInput: {
    flex: 1,
    ...Typography.body,
  },
  pickerListContent: {
    padding: Spacing.lg,
    paddingTop: Spacing.sm,
  },
  productPickRow: {
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    alignItems: 'center',
  },
  pickThumbnail: {
    width: 44,
    height: 44,
    borderRadius: BorderRadius.sm,
    backgroundColor: '#333333',
  },
  pickThumbnailPlaceholder: {
    width: 44,
    height: 44,
    borderRadius: BorderRadius.sm,
    justifyContent: 'center',
    alignItems: 'center',
  },
  pickProductInfo: {
    flex: 1,
    marginHorizontal: Spacing.md,
  },
  pickProductName: {
    ...Typography.body,
    fontWeight: '600',
  },
  pickProductMeta: {
    ...Typography.caption,
    marginTop: 2,
  },
  pickProductPrice: {
    ...Typography.price,
  },
  emptyPickerContainer: {
    alignItems: 'center',
    paddingVertical: Spacing.xxl,
    gap: Spacing.sm,
  },
  emptyPickerText: {
    ...Typography.bodySmall,
  },

  // ── Modal Step 2: Offer Types ──
  contextCard: {
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  contextInfo: {
    flex: 1,
  },
  contextLabel: {
    ...Typography.caption,
  },
  contextName: {
    ...Typography.subheading,
  },
  contextPrice: {
    ...Typography.price,
    fontWeight: '700',
  },
  sectionInstruction: {
    ...Typography.body,
    marginBottom: Spacing.md,
  },
  typeCard: {
    borderWidth: 1,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
    alignItems: 'center',
  },
  typeIconContainer: {
    width: 52,
    height: 52,
    borderRadius: 26,
    justifyContent: 'center',
    alignItems: 'center',
  },
  typeTextContainer: {
    flex: 1,
    marginHorizontal: Spacing.md,
  },
  typeCardTitle: {
    ...Typography.subheading,
  },
  typeCardSubtitle: {
    ...Typography.caption,
    marginTop: 2,
  },

  // ── Modal Step 3: Form Configuration ──
  formGroup: {
    marginBottom: Spacing.lg,
  },
  inputLabel: {
    ...Typography.bodySmall,
    fontWeight: '600',
    marginBottom: Spacing.xs,
  },
  textInput: {
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Platform.OS === 'ios' ? Spacing.md : Spacing.sm,
    ...Typography.body,
  },
  textAreaInput: {
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    ...Typography.body,
    height: 80,
    textAlignVertical: 'top',
  },
  rowInputs: {
    alignItems: 'center',
  },
  previewBox: {
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginTop: Spacing.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  previewLabel: {
    ...Typography.caption,
    marginBottom: 2,
  },
  previewValue: {
    ...Typography.subheading,
    fontWeight: '700',
  },
  submitButton: {
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: Spacing.md,
    ...Shadows.small,
  },
  submitButtonText: {
    ...Typography.button,
    color: '#FFFFFF',
    fontSize: 16,
  },
});