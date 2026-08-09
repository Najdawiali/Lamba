/**
 * Merchant Special Offers Manager Screen
 * Allows merchants to add/remove special offers (BOGO, Percentage Discount)
 * and toggle active status.
 */

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, Alert, Switch, RefreshControl, Image,
  Modal, TextInput, ScrollView
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import {
  getMerchantSpecialOffers, createSpecialOffer, updateSpecialOffer,
  deleteSpecialOffer, getMarketItems, addNewItem, getMyMarket,
  SpecialOfferResponse, MarketItemDashboardResponse
} from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows, TAB_BAR_OVERFLOW } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import { resolveImageUrl } from '../../services/utils';
import { formatPrice } from '../../services/currency';

export default function MerchantOffersScreen() {
  const Colors = useThemeColors();
  const isAr = i18n.locale.includes('ar');
  const [offers, setOffers] = useState<SpecialOfferResponse[]>([]);
  const [products, setProducts] = useState<MarketItemDashboardResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Add Offer Modal States
  const [addModalVisible, setAddModalVisible] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<MarketItemDashboardResponse | null>(null);
  const [offerType, setOfferType] = useState<'BOGO' | 'DISCOUNT'>('BOGO');
  const [discountPercentage, setDiscountPercentage] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Inline Product Selection View Toggle
  const [showSelector, setShowSelector] = useState(false);

  // New Product Inline Creation States
  const [formMode, setFormMode] = useState<'catalog' | 'new'>('catalog');
  const [newItemName, setNewItemName] = useState('');
  const [newItemPrice, setNewItemPrice] = useState('');
  const [newItemBarcode, setNewItemBarcode] = useState('');
  const [newItemImageUri, setNewItemImageUri] = useState<string | null>(null);
  const [marketId, setMarketId] = useState<string | null>(null);

  // Search filter for inline catalog selector
  const [selectorSearch, setSelectorSearch] = useState('');

  const filteredProducts = useMemo(() => {
    if (!selectorSearch.trim()) return products;
    const q = selectorSearch.toLowerCase();
    return products.filter(p =>
      p.name.toLowerCase().includes(q) ||
      (p.category && p.category.toLowerCase().includes(q))
    );
  }, [products, selectorSearch]);

  const loadData = useCallback(async () => {
    try {
      const [fetchedOffers, fetchedProducts] = await Promise.all([
        getMerchantSpecialOffers(),
        getMarketItems(),
      ]);
      setOffers(fetchedOffers);
      setProducts(fetchedProducts);
    } catch (err) {
      console.error('Failed to fetch merchant offers:', err);
      Alert.alert(
        t('common.error', 'Connection Error'),
        t('offers.error_loading', 'Failed to load offers and products. Pull down to refresh.')
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleToggleActive = async (offerId: string, currentStatus: boolean) => {
    try {
      const updated = await updateSpecialOffer(offerId, { is_active: !currentStatus });
      setOffers(prev => prev.map(o => o.id === offerId ? { ...o, is_active: updated.is_active } : o));
    } catch (err) {
      Alert.alert(
        t('common.error', 'Error'),
        t('offers.failed_update', 'Failed to update offer status.')
      );
    }
  };

  const handleDeleteOffer = (offerId: string) => {
    Alert.alert(
      t('offers.confirm_delete', 'Confirm Delete'),
      t('offers.confirm_delete_desc', 'Are you sure you want to delete this special offer?'),
      [
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
        {
          text: t('common.delete', 'Delete'),
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteSpecialOffer(offerId);
              setOffers(prev => prev.filter(o => o.id !== offerId));
            } catch (err) {
              Alert.alert(
                t('common.error', 'Error'),
                t('offers.failed_delete', 'Failed to delete offer.')
              );
            }
          }
        }
      ]
    );
  };

  const pickNewItemImage = async () => {
    const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (permissionResult.granted === false) {
      Alert.alert(
        t('scanner.permission_denied', 'Gallery Permission Required'),
        t('addProduct.media_library_permission', 'Library permissions are required to upload a product photo.')
      );
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.8,
    });

    if (!result.canceled) {
      setNewItemImageUri(result.assets[0].uri);
    }
  };

  const handleCreateOffer = async () => {
    let resolvedItemId = '';
    let enrichedName = '';
    let enrichedImageUrl = '';
    let enrichedPrice = 0;
    let enrichedStock = 10;
    let enrichedCategory = '';

    if (formMode === 'catalog') {
      if (!selectedProduct) {
        Alert.alert(
          t('common.error', 'Alert'),
          t('offers.select_product_prompt', 'Please select a product to apply the offer to.')
        );
        return;
      }
      resolvedItemId = selectedProduct.id;
      enrichedName = selectedProduct.name;
      enrichedImageUrl = selectedProduct.image_url || '';
      enrichedPrice = selectedProduct.price || 0;
      enrichedStock = selectedProduct.stock_count || 0;
      enrichedCategory = selectedProduct.category || '';
    } else {
      // Validate brand new product inputs
      if (!newItemName.trim()) {
        Alert.alert(
          t('common.error', 'Alert'),
          t('addProduct.product_name', 'Please enter the product name.')
        );
        return;
      }

      const priceVal = parseFloat(newItemPrice);
      if (isNaN(priceVal) || priceVal < 0) {
        Alert.alert(
          t('common.error', 'Alert'),
          t('addProduct.price', 'Please enter a valid product price.')
        );
        return;
      }

      if (!newItemImageUri) {
        Alert.alert(
          t('common.error', 'Alert'),
          t('offers.select_image_prompt', 'Please select a picture for the new product.')
        );
        return;
      }

      setSubmitting(true);
      try {
        // Get marketId if not cached
        let mId = marketId;
        if (!mId) {
          const market = await getMyMarket();
          mId = market.id;
          setMarketId(mId);
        }

        const formData = new FormData();
        formData.append('market_id', mId);
        formData.append('name', newItemName.trim());
        formData.append('price', priceVal.toString());
        formData.append('stock_count', '10');
        if (newItemBarcode.trim()) {
          formData.append('barcode', newItemBarcode.trim());
        }

        const filename = newItemImageUri.split('/').pop() || 'photo.jpg';
        const match = /\.(\w+)$/.exec(filename);
        const type = match ? `image/${match[1]}` : 'image/jpeg';

        formData.append('image', {
          uri: newItemImageUri,
          name: filename,
          type,
        } as any);

        const newProductResp = await addNewItem(formData);
        if (!newProductResp.market_item_id) {
          throw new Error('No market_item_id returned from catalog ingestion.');
        }

        resolvedItemId = newProductResp.market_item_id;
        enrichedName = newItemName.trim();
        enrichedImageUrl = newItemImageUri;
        enrichedPrice = priceVal;
        enrichedStock = 10;
        enrichedCategory = '';
      } catch (err: any) {
        console.error('Failed to create new catalog product:', err);
        const errMsg = err?.response?.data?.detail || t('offers.failed_create_product', 'Failed to create new product in catalog.');
        Alert.alert(t('common.error'), errMsg);
        setSubmitting(false);
        return;
      }
    }

    let pct: number | undefined = undefined;
    if (offerType === 'DISCOUNT') {
      const val = parseFloat(discountPercentage);
      if (isNaN(val) || val <= 0 || val > 100) {
        Alert.alert(
          t('common.error', 'Alert'),
          t('offers.invalid_discount', 'Please enter a valid discount percentage between 1 and 100.')
        );
        setSubmitting(false);
        return;
      }
      pct = val;
    }

    if (!submitting) {
      setSubmitting(true);
    }
    
    try {
      const newOffer = await createSpecialOffer({
        market_item_id: resolvedItemId,
        offer_type: offerType,
        discount_percentage: pct,
        description: description.trim() || undefined,
      });

      // Insert product info locally so UI shows it right away
      const enrichedOffer = {
        ...newOffer,
        name: newOffer.name || enrichedName,
        category: newOffer.category || enrichedCategory || null,
        image_url: newOffer.image_url || enrichedImageUrl || null,
        price: newOffer.price != null ? newOffer.price : enrichedPrice,
        stock_count: newOffer.stock_count || enrichedStock,
      };

      setOffers(prev => [enrichedOffer, ...prev]);
      setAddModalVisible(false);
      
      // Reset form states
      setSelectedProduct(null);
      setOfferType('BOGO');
      setDiscountPercentage('');
      setDescription('');
      setFormMode('catalog');
      setNewItemName('');
      setNewItemPrice('');
      setNewItemBarcode('');
      setNewItemImageUri(null);

      Alert.alert(
        t('common.success'),
        t('offers.offer_created')
      );
    } catch (err: any) {
      console.error('Failed to create offer:', err);
      const errMsg = err?.response?.data?.detail || (isAr ? 'فشل إنشاء العرض الخاص.' : 'Failed to create special offer.');
      Alert.alert(t('common.error'), errMsg);
    } finally {
      setSubmitting(false);
    }
  };

  const renderOfferItem = useCallback(({ item }: { item: SpecialOfferResponse }) => {
    const isBogo = item.offer_type === 'BOGO';
    const offerBadgeText = isBogo
      ? (isAr ? 'اشترِ قطعة واحصل على الثانية مجاناً' : 'Buy 1 Get 1 Free')
      : `${item.discount_percentage}% ${isAr ? 'تخفيض' : 'OFF'}`;

    return (
      <View style={[styles.offerCard, !item.is_active && styles.inactiveCard]}>
        <View style={styles.cardHeader}>
          <Image
            source={
              item.image_url
                ? { uri: resolveImageUrl(item.image_url) }
                : require('../../assets/icon.png')
            }
            style={styles.productImage}
          />
          <View style={styles.cardInfo}>
            <Text style={styles.productName} numberOfLines={1}>{item.name}</Text>
            <Text style={styles.productCategory}>{item.category || (isAr ? 'غير مصنف' : 'Uncategorized')}</Text>
            
            <View style={styles.badgeContainer}>
              <View style={[styles.badge, isBogo ? styles.bogoBadge : styles.discountBadge]}>
                <Ionicons
                  name={isBogo ? "gift-outline" : "pricetag-outline"}
                  size={12}
                  color={isBogo ? Colors.background : Colors.textOnPrimary}
                />
                <Text style={[styles.badgeText, isBogo ? styles.bogoBadgeText : styles.discountBadgeText]}>
                  {offerBadgeText}
                </Text>
              </View>
            </View>

            {item.price != null && (
              <Text style={styles.priceText}>
                {formatPrice(item.price)}
              </Text>
            )}
          </View>
        </View>

        {item.description ? (
          <View style={styles.descriptionContainer}>
            <Text style={styles.descriptionText}>{item.description}</Text>
          </View>
        ) : null}

        <View style={styles.divider} />

        <View style={styles.cardActions}>
          <View style={styles.actionLeft}>
            <Text style={styles.statusLabel}>
              {item.is_active ? t('offers.active') : t('offers.inactive')}
            </Text>
            <Switch
              value={item.is_active}
              onValueChange={() => handleToggleActive(item.id, item.is_active)}
              trackColor={{ false: Colors.toggleInactive, true: Colors.toggleOfferActive }}
              thumbColor={'#FFFFFF'}
            />
          </View>

          <TouchableOpacity
            style={styles.deleteButton}
            onPress={() => handleDeleteOffer(item.id)}
          >
            <Ionicons name="trash-outline" size={20} color={Colors.error} />
          </TouchableOpacity>
        </View>
      </View>
    );
  }, [isAr, handleToggleActive, handleDeleteOffer]);

  const styles = useMemo(() => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: Colors.background,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  headerSubtitle: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: 4,
  },
  newOfferBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  addButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.secondary,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    gap: Spacing.xs,
    ...Shadows.small,
  },
  addButtonText: {
    ...Typography.button,
    color: Colors.background,
    fontSize: 14,
  },
  listContent: {
    padding: Spacing.lg,
    paddingBottom: TAB_BAR_OVERFLOW,
  },
  offerCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.small,
  },
  inactiveCard: {
    opacity: 0.6,
  },
  cardHeader: {
    flexDirection: 'row',
  },
  productImage: {
    width: 80,
    height: 80,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surfaceElevated,
  },
  cardInfo: {
    flex: 1,
    marginLeft: Spacing.md,
    justifyContent: 'center',
  },
  productName: {
    ...Typography.h3,
    color: Colors.textPrimary,
  },
  productCategory: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
    textTransform: 'uppercase',
  },
  badgeContainer: {
    flexDirection: 'row',
    marginTop: Spacing.xs,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: BorderRadius.full,
  },
  bogoBadge: {
    backgroundColor: Colors.secondary,
  },
  discountBadge: {
    backgroundColor: Colors.primary,
  },
  badgeText: {
    ...Typography.caption,
    fontSize: 10,
    fontWeight: '700',
    marginLeft: 4,
  },
  bogoBadgeText: {
    color: Colors.background,
  },
  discountBadgeText: {
    color: Colors.textOnPrimary,
  },
  priceText: {
    ...Typography.label,
    color: Colors.textSecondary,
    marginTop: Spacing.sm,
  },
  descriptionContainer: {
    marginTop: Spacing.sm,
    padding: Spacing.sm,
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.sm,
  },
  descriptionText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    fontStyle: 'italic',
  },
  divider: {
    height: 1,
    backgroundColor: Colors.divider,
    marginVertical: Spacing.md,
  },
  cardActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  actionLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusLabel: {
    ...Typography.label,
    color: Colors.textSecondary,
    marginRight: Spacing.sm,
  },
  deleteButton: {
    padding: Spacing.sm,
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.xxxl,
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
    paddingHorizontal: Spacing.xl,
  },
  emptyButton: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    marginTop: Spacing.xl,
  },
  emptyButtonText: {
    ...Typography.button,
    color: Colors.textOnPrimary,
  },

  // Modals Styling
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.lg,
    maxHeight: '90%',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  modalContentFullHeight: {
    height: '90%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
    paddingBottom: Spacing.md,
  },
  modalTitle: {
    ...Typography.h2,
    color: Colors.textPrimary,
  },
  closeButton: {
    padding: 4,
  },
  modalForm: {
    paddingVertical: Spacing.lg,
    paddingBottom: Spacing.xxxl,
  },
  inputLabel: {
    ...Typography.label,
    color: Colors.textPrimary,
    marginTop: Spacing.md,
    marginBottom: Spacing.sm,
  },
  productPicker: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
  },
  pickerPlaceholder: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  pickerPlaceholderText: {
    flex: 1,
    ...Typography.body,
    color: Colors.textMuted,
    marginLeft: Spacing.sm,
  },
  selectedProductRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  miniProductImage: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surfaceElevated,
    marginRight: Spacing.md,
  },
  selectedProductName: {
    ...Typography.h3,
    color: Colors.textPrimary,
  },
  selectedProductPrice: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  typeButtonsRow: {
    flexDirection: 'column',
    gap: Spacing.sm,
  },
  typeOptionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    gap: Spacing.sm,
  },
  typeOptionActiveBogo: {
    backgroundColor: Colors.secondary,
    borderColor: Colors.secondaryLight,
  },
  typeOptionActiveDiscount: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primaryLight,
  },
  typeOptionText: {
    ...Typography.label,
    color: Colors.textSecondary,
  },
  typeOptionTextActiveBogo: {
    color: Colors.background,
    fontWeight: '700',
  },
  typeOptionTextActiveDiscount: {
    color: Colors.textOnPrimary,
    fontWeight: '700',
  },
  textInput: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    color: Colors.textPrimary,
    ...Typography.body,
  },
  textArea: {
    height: 80,
    textAlignVertical: 'top',
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.secondary,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    marginTop: Spacing.xxl,
    gap: Spacing.xs,
    ...Shadows.glow,
  },
  submitButtonText: {
    ...Typography.button,
    color: Colors.background,
  },

  // Segmented Tabs
  segmentContainer: {
    flexDirection: 'row',
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.md,
    padding: 4,
    marginBottom: Spacing.lg,
  },
  segmentBtn: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    borderRadius: BorderRadius.sm,
  },
  segmentActiveBtn: {
    backgroundColor: Colors.surface,
    ...Shadows.small,
  },
  segmentBtnText: {
    ...Typography.label,
    color: Colors.textMuted,
  },
  segmentActiveBtnText: {
    color: Colors.textPrimary,
    fontWeight: '700',
  },
  newProductFieldsContainer: {
    flexDirection: 'column',
    gap: 0,
  },

  // Image Picker Control
  imagePickerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.xl,
    gap: Spacing.sm,
    marginTop: Spacing.xs,
  },
  imagePickerText: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  previewImageContainer: {
    position: 'relative',
    marginTop: Spacing.xs,
    alignSelf: 'flex-start',
  },
  previewImage: {
    width: 120,
    height: 120,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  clearImageBtn: {
    position: 'absolute',
    top: -8,
    right: -8,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.full,
  },

  // Search Bar Inside Catalog Selector
  searchBarInlineContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    marginVertical: Spacing.md,
  },
  searchIconInline: {
    marginRight: Spacing.xs,
  },
  searchBarInline: {
    flex: 1,
    paddingVertical: Spacing.md,
    color: Colors.textPrimary,
    ...Typography.body,
  },
  clearSearchBtnInline: {
    padding: 4,
  },
  selectorListInline: {
    paddingBottom: Spacing.xxl,
  },
  emptySelector: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.xxl,
  },
  emptySelectorText: {
    ...Typography.body,
    color: Colors.textMuted,
    marginTop: Spacing.md,
  },

  // Selector list item row
  selectorItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  selectorItemImage: {
    width: 50,
    height: 50,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surfaceElevated,
  },
  selectorItemName: {
    ...Typography.label,
    color: Colors.textPrimary,
  },
  selectorItemCategory: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
  },
  selectorItemPrice: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontWeight: '600',
    marginTop: 2,
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
      <View style={styles.header}>
        <Text style={styles.headerTitle}>
          {t('offers.title', 'Special Offers')}
        </Text>
        <Text style={styles.headerSubtitle}>
          {t('offers.subtitle', 'Manage and activate product promotions')}
        </Text>
      </View>

      {/* Dedicated New Offer CTA — full-width bar so it's always in correct place */}
      <View style={styles.newOfferBar}>
        <TouchableOpacity
          style={styles.addButton}
          onPress={() => setAddModalVisible(true)}
          activeOpacity={0.85}
        >
          <Ionicons name="add-circle-outline" size={20} color={Colors.background} />
          <Text style={styles.addButtonText}>{t('offers.new_offer', 'New Offer')}</Text>
        </TouchableOpacity>
      </View>

      {/* Main List */}
      <FlatList
        data={offers}
        keyExtractor={(item) => item.id}
        renderItem={renderOfferItem}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor={Colors.primary}
          />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="pricetags-outline" size={60} color={Colors.textMuted} />
            <Text style={styles.emptyTitle}>{t('offers.no_offers_yet', 'No Active Promotions')}</Text>
            <Text style={styles.emptySubtitle}>
              {t('offers.no_offers_prompt', 'Add your first special offer to attract more customers!')}
            </Text>
            <TouchableOpacity
              style={styles.emptyButton}
              onPress={() => setAddModalVisible(true)}
            >
              <Text style={styles.emptyButtonText}>{t('offers.create_offer', 'Create First Offer')}</Text>
            </TouchableOpacity>
          </View>
        }
      />

      {/* Add Offer Modal */}
      <Modal
        visible={addModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => {
          setAddModalVisible(false);
          setShowSelector(false);
          setSelectorSearch('');
        }}
      >
        <View style={styles.modalOverlay}>
          <View style={[styles.modalContent, showSelector && styles.modalContentFullHeight]}>
            {showSelector ? (
              <View style={{ flex: 1, paddingBottom: Spacing.xl }}>
                <View style={styles.modalHeader}>
                  <TouchableOpacity
                    onPress={() => {
                      setShowSelector(false);
                      setSelectorSearch('');
                    }}
                    style={styles.closeButton}
                  >
                    <Ionicons name="arrow-back" size={22} color={Colors.textPrimary} />
                  </TouchableOpacity>
                  <Text style={styles.modalTitle}>
                    {t('offers.select_product', 'Select Product for Offer')}
                  </Text>
                  <View style={{ width: 24 }} />
                </View>

                {/* Search box for filtering products list */}
                <View style={styles.searchBarInlineContainer}>
                  <Ionicons name="search-outline" size={18} color={Colors.textMuted} style={styles.searchIconInline} />
                  <TextInput
                    style={styles.searchBarInline}
                    placeholder={t('offers.search_placeholder', 'Search by name or category...')}
                    placeholderTextColor={Colors.textMuted}
                    value={selectorSearch}
                    onChangeText={setSelectorSearch}
                  />
                  {selectorSearch.length > 0 && (
                    <TouchableOpacity onPress={() => setSelectorSearch('')} style={styles.clearSearchBtnInline}>
                      <Ionicons name="close-circle" size={16} color={Colors.textMuted} />
                    </TouchableOpacity>
                  )}
                </View>

                <FlatList
                  data={filteredProducts}
                  keyExtractor={(item) => item.id}
                  contentContainerStyle={styles.selectorListInline}
                  ListEmptyComponent={
                    <View style={styles.emptySelector}>
                      <Ionicons name="cube-outline" size={40} color={Colors.textMuted} />
                      <Text style={styles.emptySelectorText}>
                        {t('explore.no_results', 'No matching products found.')}
                      </Text>
                    </View>
                  }
                  renderItem={({ item }) => (
                    <TouchableOpacity
                      style={styles.selectorItemRow}
                      onPress={() => {
                        setSelectedProduct(item);
                        setShowSelector(false);
                        setSelectorSearch('');
                      }}
                    >
                      <Image
                        source={
                          item.image_url
                            ? { uri: resolveImageUrl(item.image_url) }
                            : require('../../assets/icon.png')
                        }
                        style={styles.selectorItemImage}
                      />
                      <View style={{ flex: 1, marginHorizontal: Spacing.md }}>
                        <Text style={styles.selectorItemName} numberOfLines={1}>{item.name}</Text>
                        <Text style={styles.selectorItemCategory}>{item.category || t('common.uncategorized', 'Uncategorized')}</Text>
                        <Text style={styles.selectorItemPrice}>
                          {formatPrice(item.price)}
                        </Text>
                      </View>
                      <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
                    </TouchableOpacity>
                  )}
                />
              </View>
            ) : (
              <>
                <View style={styles.modalHeader}>
                  <Text style={styles.modalTitle}>{t('offers.create_offer', 'Create Special Offer')}</Text>
                  <TouchableOpacity
                    onPress={() => {
                      setAddModalVisible(false);
                      setFormMode('catalog');
                      setSelectedProduct(null);
                      setNewItemName('');
                      setNewItemPrice('');
                      setNewItemBarcode('');
                      setNewItemImageUri(null);
                    }}
                    style={styles.closeButton}
                  >
                    <Ionicons name="close" size={24} color={Colors.textPrimary} />
                  </TouchableOpacity>
                </View>

                <ScrollView contentContainerStyle={styles.modalForm} showsVerticalScrollIndicator={false}>
                  {/* Segmented/Tab Selector for Dual Mode */}
                  <View style={styles.segmentContainer}>
                    <TouchableOpacity
                      style={[styles.segmentBtn, formMode === 'catalog' && styles.segmentActiveBtn]}
                      onPress={() => setFormMode('catalog')}
                    >
                      <Text style={[styles.segmentBtnText, formMode === 'catalog' && styles.segmentActiveBtnText]}>
                        {t('offers.choose_catalog')}
                      </Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.segmentBtn, formMode === 'new' && styles.segmentActiveBtn]}
                      onPress={() => setFormMode('new')}
                    >
                      <Text style={[styles.segmentBtnText, formMode === 'new' && styles.segmentActiveBtnText]}>
                        {t('offers.create_new')}
                      </Text>
                    </TouchableOpacity>
                  </View>

                  {formMode === 'catalog' ? (
                    <View>
                      {/* Product Picker Button */}
                      <Text style={styles.inputLabel}>{t('offers.target_product', 'Target Product')}</Text>
                      <TouchableOpacity
                        style={styles.productPicker}
                        onPress={() => setShowSelector(true)}
                      >
                        {selectedProduct ? (
                          <View style={styles.selectedProductRow}>
                            <Image
                              source={
                                selectedProduct.image_url
                                  ? { uri: resolveImageUrl(selectedProduct.image_url) }
                                  : require('../../assets/icon.png')
                              }
                              style={styles.miniProductImage}
                            />
                            <View style={{ flex: 1, marginHorizontal: Spacing.sm }}>
                              <Text style={styles.selectedProductName} numberOfLines={1}>
                                {selectedProduct.name}
                              </Text>
                              <Text style={styles.selectedProductPrice}>
                                {formatPrice(selectedProduct.price)}
                              </Text>
                            </View>
                            <Ionicons name="swap-horizontal-outline" size={20} color={Colors.primary} />
                          </View>
                        ) : (
                          <View style={styles.pickerPlaceholder}>
                            <Ionicons name="cube-outline" size={20} color={Colors.textMuted} />
                            <Text style={styles.pickerPlaceholderText}>
                              {t('offers.choose_catalog_prompt', 'Choose a product from catalog...')}
                            </Text>
                            <Ionicons name="chevron-down" size={18} color={Colors.textMuted} />
                          </View>
                        )}
                      </TouchableOpacity>
                    </View>
                  ) : (
                    <View style={styles.newProductFieldsContainer}>
                      {/* Brand-New Product Fields */}
                      <Text style={styles.inputLabel}>{t('addProduct.product_name')}</Text>
                      <TextInput
                        style={styles.textInput}
                        placeholder={t('addProduct.product_name', 'New product name...')}
                        placeholderTextColor={Colors.textMuted}
                        value={newItemName}
                        onChangeText={setNewItemName}
                      />

                      <Text style={styles.inputLabel}>{t('addProduct.price')}</Text>
                      <TextInput
                        style={styles.textInput}
                        placeholder="e.g. 5.99"
                        placeholderTextColor={Colors.textMuted}
                        keyboardType="numeric"
                        value={newItemPrice}
                        onChangeText={setNewItemPrice}
                      />

                      <Text style={styles.inputLabel}>{t('addProduct.barcode')}</Text>
                      <TextInput
                        style={styles.textInput}
                        placeholder={t('scanner.enter_manually', 'Type product barcode...')}
                        placeholderTextColor={Colors.textMuted}
                        value={newItemBarcode}
                        onChangeText={setNewItemBarcode}
                      />

                      <Text style={styles.inputLabel}>{t('offers.product_picture')}</Text>
                      {newItemImageUri ? (
                        <View style={styles.previewImageContainer}>
                          <Image source={{ uri: newItemImageUri }} style={styles.previewImage} />
                          <TouchableOpacity style={styles.clearImageBtn} onPress={() => setNewItemImageUri(null)}>
                            <Ionicons name="close-circle" size={24} color={Colors.error} />
                          </TouchableOpacity>
                        </View>
                      ) : (
                        <TouchableOpacity style={styles.imagePickerBtn} onPress={pickNewItemImage}>
                          <Ionicons name="camera-outline" size={26} color={Colors.primary} />
                          <Text style={styles.imagePickerText}>{t('offers.select_image')}</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                  )}

                  {/* Offer Type Selection */}
                  <Text style={styles.inputLabel}>{t('offers.offer_type', 'Offer Type')}</Text>
                  <View style={styles.typeButtonsRow}>
                    <TouchableOpacity
                      style={[
                        styles.typeOptionButton,
                        offerType === 'BOGO' && styles.typeOptionActiveBogo
                      ]}
                      onPress={() => setOfferType('BOGO')}
                    >
                      <Ionicons
                        name="gift-outline"
                        size={18}
                        color={offerType === 'BOGO' ? Colors.background : Colors.textSecondary}
                      />
                      <Text style={[
                        styles.typeOptionText,
                        offerType === 'BOGO' && styles.typeOptionTextActiveBogo
                      ]}>
                        {t('offers.bogo', 'Buy 1 Get 1 Free')}
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[
                        styles.typeOptionButton,
                        offerType === 'DISCOUNT' && styles.typeOptionActiveDiscount
                      ]}
                      onPress={() => setOfferType('DISCOUNT')}
                    >
                      <Ionicons
                        name="pricetag-outline"
                        size={18}
                        color={offerType === 'DISCOUNT' ? Colors.textOnPrimary : Colors.textSecondary}
                      />
                      <Text style={[
                        styles.typeOptionText,
                        offerType === 'DISCOUNT' && styles.typeOptionTextActiveDiscount
                      ]}>
                        {isAr ? 'نسبة تخفيض مئوية' : 'Percentage Discount'}
                      </Text>
                    </TouchableOpacity>
                  </View>

                  {/* Percentage input (Conditional) */}
                  {offerType === 'DISCOUNT' && (
                    <View>
                      <Text style={styles.inputLabel}>{isAr ? 'نسبة الخصم المئوية (%)' : 'Discount Percentage (%)'}</Text>
                      <TextInput
                        style={styles.textInput}
                        placeholder="e.g. 20, 50, 75"
                        placeholderTextColor={Colors.textMuted}
                        keyboardType="numeric"
                        value={discountPercentage}
                        onChangeText={setDiscountPercentage}
                      />
                    </View>
                  )}

                  {/* Description Input */}
                  <Text style={styles.inputLabel}>{isAr ? 'تفاصيل العرض (اختياري)' : 'Offer Description (Optional)'}</Text>
                  <TextInput
                    style={[styles.textInput, styles.textArea]}
                    placeholder={isAr ? 'اكتب شروط أو تفاصيل العرض...' : 'Write custom rules or promotion details...'}
                    placeholderTextColor={Colors.textMuted}
                    multiline={true}
                    numberOfLines={3}
                    value={description}
                    onChangeText={setDescription}
                  />

                  {/* Submit Buttons */}
                  <TouchableOpacity
                    style={styles.submitButton}
                    onPress={handleCreateOffer}
                    disabled={submitting}
                  >
                    {submitting ? (
                      <ActivityIndicator color={Colors.background} size="small" />
                    ) : (
                      <>
                        <Ionicons name="checkmark-circle-outline" size={20} color={Colors.background} />
                        <Text style={styles.submitButtonText}>
                          {isAr ? 'تأكيد ونشر العرض' : 'Confirm and Publish Offer'}
                        </Text>
                      </>
                    )}
                  </TouchableOpacity>
                </ScrollView>
              </>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}