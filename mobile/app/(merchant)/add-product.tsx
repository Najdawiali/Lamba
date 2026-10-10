/**
 * Upgraded Add Product/Service Screen — Two-step Catalog Integration & AI Ingestion.
 * Full-width segmented control with "Add New" as the default active tab.
 * Product / Service type toggle, dynamic conditional fields, Category Tree selectors, and Multi-Image uploads.
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, Alert, ActivityIndicator, KeyboardAvoidingView, Platform, Image, Modal, Switch
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { CameraView, useCameraPermissions } from 'expo-camera';
import {
  checkItemName, linkExistingItem, addNewItem,
  uploadItemsCSV, getCategories, CatalogItemMatch, updateMarketItem,
} from '../../services/api';
import { useQueryClient } from '@tanstack/react-query';
import { useMarket, merchantKeys } from '../../hooks/useMerchant';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import { categoryLabel } from '../../utils/categoryLabel';
import { resolveImageUrl } from '../../services/utils';
import { localizeServerMessage } from '../../utils/serverMessage';

export default function AddProductScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const Colors = useThemeColors();
  const params = useLocalSearchParams<{ barcode?: string }>();
  const isAr = i18n.locale?.startsWith('ar');
  
  // Market setup via hook
  const { data: marketData, isLoading: loadingMarket } = useMarket();
  const marketId = marketData?.id ?? null;

  // Full-width segmented control state ("new" is default)
  const [activeTab, setActiveTab] = useState<'new' | 'catalog' | 'bulk'>('new');

  // General state
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [matches, setMatches] = useState<CatalogItemMatch[]>([]);
  const [selectedMatch, setSelectedMatch] = useState<CatalogItemMatch | null>(null);
  const [stockCount, setStockCount] = useState('10');
  const [linkPrice, setLinkPrice] = useState('');
  const [barcode, setBarcode] = useState('');
  
  // Product / Service Toggle & Conditional Fields State
  const [listingType, setListingType] = useState<'product' | 'service'>('product');
  const [stockStatus, setStockStatus] = useState('available');
  const [gender, setGender] = useState<string | null>(null);
  const [appointmentRequired, setAppointmentRequired] = useState(false);
  const [homeServiceAvailable, setHomeServiceAvailable] = useState(false);

  // Inline scanner state
  const [showScanner, setShowScanner] = useState(false);
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();

  // New Item (AI pipeline) state
  const [newItemName, setNewItemName] = useState('');
  const [newItemDesc, setNewItemDesc] = useState('');
  const [newItemPrice, setNewItemPrice] = useState('1.00');
  
  // CSV Upload State
  const [shops, setShops] = useState<any[]>([]);
  const [selectedShopId, setSelectedShopId] = useState('');
  const [loadingShops, setLoadingShops] = useState(true);
  const [csvUploadResult, setCsvUploadResult] = useState<{ created: number; indexed: number } | null>(null);

  // Multi-Image State
  const [imageUri, setImageUri] = useState<string | null>(null); // Primary Image
  const [secondaryImageUris, setSecondaryImageUris] = useState<string[]>([]); // Secondary Images

  // Categories Tree State
  const [categoriesTree, setCategoriesTree] = useState<any[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedSubcategory, setSelectedSubcategory] = useState<string>('');

  const resetForm = useCallback(() => {
    setNewItemName('');
    setNewItemDesc('');
    setStockCount('10');
    setNewItemPrice('');
    setImageUri(null);
    setSecondaryImageUris([]);
    setStockStatus('available');
    setSelectedCategory('');
    setSelectedSubcategory('');
    setGender(null);
    setAppointmentRequired(false);
    setHomeServiceAvailable(false);
    setShowScanner(false);
    setSearchQuery('');
    setHasSearched(false);
    setMatches([]);
    setSelectedMatch(null);
    setLinkPrice('');
    setListingType('product');
    setCsvUploadResult(null);
    setLoading(false);

    if (params.barcode) {
      setBarcode(params.barcode);
      setActiveTab('new');
    } else {
      setBarcode('');
      setActiveTab('catalog');
    }
  }, [params.barcode]);

  useFocusEffect(
    useCallback(() => {
      resetForm();
    }, [resetForm])
  );

  useEffect(() => {
    if (params.barcode) {
      setBarcode(params.barcode);
      setListingType('product');
      setActiveTab('new');
    }
  }, [params.barcode]);

  // Filter categories by listing type (product vs service vs both)
  const filteredCategories = useMemo(() => {
    return categoriesTree.filter(c => 
      !c.listing_type || c.listing_type === listingType || c.listing_type === 'both'
    );
  }, [categoriesTree, listingType]);

  const subcategories = useMemo(() => {
    if (!selectedCategory) return [];
    const cat = categoriesTree.find(c => c.id === selectedCategory);
    if (!cat?.subcategories) return [];
    return cat.subcategories.filter((sub: any) => 
      !sub.listing_type || sub.listing_type === listingType || sub.listing_type === 'both'
    );
  }, [categoriesTree, selectedCategory, listingType]);

  useEffect(() => {
    if (marketData) {
      setShops([marketData]);
      setSelectedShopId(marketData.id);
      setLoadingShops(false);
    }
  }, [marketData]);

  useEffect(() => {
    (async () => {
      try {
        const cats = await getCategories();
        setCategoriesTree(cats);
      } catch (err) {
        console.warn('Failed to load categories tree:', err);
      }
    })();
  }, []);

  // 1. Fuzzy Search Check Catalog
  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      Alert.alert(t('common.error', 'Error'), t('search.placeholder', 'Please enter a name to search the catalog.'));
      return;
    }
    setLoading(true);
    setSelectedMatch(null);
    try {
      const resp = await checkItemName(searchQuery.trim());
      setMatches(resp.matches);
      setHasSearched(true);
    } catch (err: any) {
      Alert.alert(t('common.error', 'Search Failed'), t('search.network_error', 'Failed to query global catalog.'));
    } finally {
      setLoading(false);
    }
  };

  // 2. Link Existing Item
  const handleLinkItem = async () => {
    if (!selectedMatch || !marketId) return;
    const stockNum = parseInt(stockCount);
    if (isNaN(stockNum) || stockNum < 0) {
      Alert.alert(t('common.error', 'Error'), t('addProduct.quantity', 'Please enter a valid stock count.'));
      return;
    }

    setLoading(true);
    try {
      const resp = await linkExistingItem(selectedMatch.id, marketId, stockNum);
      const priceNum = parseFloat(linkPrice);
      if (!isNaN(priceNum) && priceNum > 0 && resp.market_item_id) {
        try {
          await updateMarketItem(resp.market_item_id, { price: priceNum });
        } catch (priceErr) {
          console.warn('Optional price update skipped or failed:', priceErr);
        }
      }
      if (resp.success) {
        Alert.alert(t('common.success', 'Success'), resp.message, [
          {
            text: t('common.ok', 'OK'),
            onPress: () => {
              resetForm();
              queryClient.invalidateQueries({ queryKey: merchantKeys.items });
              queryClient.invalidateQueries({ queryKey: merchantKeys.inventoryValue });
              router.replace('/(merchant)/dashboard');
            },
          },
        ]);
      }
    } catch (err: any) {
      Alert.alert(t('common.error', 'Linking Failed'), err?.response?.data?.detail || t('scanner.failed_save', 'Failed to link item.'));
    } finally {
      setLoading(false);
    }
  };

  // 3. Primary Photo Picker
  const pickImage = () => {
    Alert.alert(
      t('addProduct.select_image', 'Select Image'),
      t('addProduct.image_source', 'Choose image source'),
      [
        {
          text: t('addProduct.camera', 'Take Photo'),
          onPress: async () => {
            const { status } = await ImagePicker.requestCameraPermissionsAsync();
            if (status !== 'granted') {
              Alert.alert(t('common.error', 'Error'), t('addProduct.camera_permission', 'Camera permission is required'));
              return;
            }
            const result = await ImagePicker.launchCameraAsync({
              mediaTypes: ['images'],
              allowsEditing: true,
              quality: 0.8,
            });
            if (!result.canceled && result.assets?.length > 0) {
              setImageUri(result.assets[0].uri);
            }
          },
        },
        {
          text: t('addProduct.gallery', 'Choose from Gallery'),
          onPress: async () => {
            const result = await ImagePicker.launchImageLibraryAsync({
              mediaTypes: ['images'],
              allowsEditing: true,
              quality: 0.8,
            });
            if (!result.canceled && result.assets?.length > 0) {
              setImageUri(result.assets[0].uri);
            }
          },
        },
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
      ],
    );
  };
  const handlePickImage = pickImage;

  // 4. Secondary Detail Photos Picker
  const pickSecondaryImage = () => {
    Alert.alert(
      t('addProduct.select_image', 'Select Image'),
      t('addProduct.image_source', 'Choose image source'),
      [
        {
          text: t('addProduct.camera', 'Take Photo'),
          onPress: async () => {
            const { status } = await ImagePicker.requestCameraPermissionsAsync();
            if (status !== 'granted') {
              Alert.alert(t('common.error', 'Error'), t('addProduct.camera_permission', 'Camera permission is required'));
              return;
            }
            const result = await ImagePicker.launchCameraAsync({
              mediaTypes: ['images'],
              allowsEditing: true,
              quality: 0.8,
            });
            if (!result.canceled && result.assets?.length > 0) {
              setSecondaryImageUris(prev => [...prev, result.assets[0].uri]);
            }
          },
        },
        {
          text: t('addProduct.gallery', 'Choose from Gallery'),
          onPress: async () => {
            const result = await ImagePicker.launchImageLibraryAsync({
              mediaTypes: ['images'],
              allowsMultipleSelection: true,
              quality: 0.8,
            });
            if (!result.canceled && result.assets?.length > 0) {
              const uris = result.assets.map(asset => asset.uri);
              setSecondaryImageUris(prev => [...prev, ...uris]);
            }
          },
        },
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
      ],
    );
  };
  const handlePickSecondaryImages = pickSecondaryImage;

  // 5. Ingest Brand-New Product / Service via AI Pipeline
  const handleAddNewItem = async () => {
    if (!newItemName.trim() || !imageUri || !marketId) {
      Alert.alert(
        t('common.error', 'Error'),
        t('addProduct.required', 'Item name and primary photo are mandatory for new catalog ingestion.')
      );
      return;
    }

    const stockNum = parseInt(stockCount);
    if (listingType === 'product' && (isNaN(stockNum) || stockNum < 0)) {
      Alert.alert(t('common.error', 'Error'), t('addProduct.quantity', 'Please enter a valid stock count.'));
      return;
    }

    const priceVal = parseFloat(newItemPrice);
    if (isNaN(priceVal) || priceVal < 0) {
      Alert.alert(t('common.error', 'Error'), t('addProduct.price', 'Please enter a valid price.'));
      return;
    }

    // Build attributes payload
    const attributes: Record<string, any> = {};
    if (listingType === 'service') {
      if (gender) attributes.gender = gender;
      attributes.appointment_required = appointmentRequired;
      attributes.home_service_available = homeServiceAvailable;
    }
    if (listingType === 'product') {
      attributes.stock_status = stockStatus;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('market_id', marketId);
      formData.append('name', newItemName.trim());
      formData.append('price', priceVal.toString());
      if (newItemDesc.trim()) {
        formData.append('description', newItemDesc.trim());
      }
      if (listingType === 'product' && barcode.trim()) {
        formData.append('barcode', barcode.trim());
      }
      formData.append('stock_count', listingType === 'product' ? stockNum.toString() : '99');
      formData.append('listing_type', listingType || 'product');
      formData.append('attributes', JSON.stringify(attributes));

      // Pass category_id if chosen
      if (selectedSubcategory) {
        formData.append('category_id', selectedSubcategory);
      } else if (selectedCategory) {
        formData.append('category_id', selectedCategory);
      }

      // Attach Primary Image
      const filename = imageUri.split('/').pop() || 'photo.jpg';
      const match = /\.(\w+)$/.exec(filename);
      const type = match ? `image/${match[1]}` : 'image/jpeg';

      formData.append('image', {
        uri: imageUri,
        name: filename,
        type,
      } as any);

      // Attach Multiple Secondary Images
      secondaryImageUris.forEach((uri, idx) => {
        const secFilename = uri.split('/').pop() || `photo_sec_${idx}.jpg`;
        const secMatch = /\.(\w+)$/.exec(secFilename);
        const secType = secMatch ? `image/${secMatch[1]}` : 'image/jpeg';
        
        formData.append('secondary_images', {
          uri,
          name: secFilename,
          type,
        } as any);
      });

      const resp = await addNewItem(formData);
      if (resp.success) {
        Alert.alert(
          isAr ? 'تمت الإضافة بنجاح' : 'AI Ingestion Complete',
          isAr 
            ? 'تم تصنيف وفهرسة ونشر العنصر في متجرك بنجاح!' 
            : 'Your item was successfully auto-categorized, vector-encoded, and added to your store!',
          [
            {
              text: isAr ? 'حسناً' : 'Great',
              onPress: () => {
                resetForm();
                queryClient.invalidateQueries({ queryKey: merchantKeys.items });
                queryClient.invalidateQueries({ queryKey: merchantKeys.inventoryValue });
                router.replace('/(merchant)/dashboard');
              },
            },
          ]
        );
      }
    } catch (err: any) {
      // detail is a string, or {code, message} for 409 barcode_exists: never hand the object to the alert
      Alert.alert(
        isAr ? 'فشلت الإضافة' : 'AI Ingestion Failed',
        localizeServerMessage(
          err?.response?.data?.detail,
          !!isAr,
          isAr ? 'حدث خطأ أثناء معالجة ونشر العنصر.' : 'An error occurred during AI extraction.',
        )
      );
    } finally {
      setLoading(false);
    }
  };

  const triggerNewForm = () => {
    setNewItemName(searchQuery);
    setActiveTab('new');
    setMatches([]);
    setHasSearched(false);
  };

  const handleCSVUpload = async () => {
    if (!selectedShopId) {
      Alert.alert(t('common.error', 'Error'), isAr ? 'يرجى اختيار متجر أولاً' : 'Please select a shop first');
      return;
    }

    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['text/csv', 'application/vnd.ms-excel'],
        copyToCacheDirectory: true,
      });

      if (result.canceled || !result.assets[0]) return;

      const file = result.assets[0];
      setLoading(true);
      setCsvUploadResult(null);

      const formData = new FormData();
      formData.append('file', {
        uri: file.uri,
        name: file.name,
        type: file.mimeType || 'text/csv',
      } as any);

      const response = await uploadItemsCSV(selectedShopId, formData);

      setCsvUploadResult(response);
      queryClient.invalidateQueries({ queryKey: merchantKeys.items });
      queryClient.invalidateQueries({ queryKey: merchantKeys.inventoryValue });
      Alert.alert(t('common.success', 'Success'), response.message, [
        {
          text: t('common.ok', 'OK'),
          onPress: () => {
            resetForm();
            router.replace('/(merchant)/dashboard');
          },
        },
      ]);
    } catch (err: any) {
      Alert.alert(isAr ? 'فشل الرفع' : 'Upload Failed', err?.response?.data?.detail || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const styles = useMemo(() => StyleSheet.create({
    container: { flex: 1, backgroundColor: Colors.background },
    loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
    header: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md,
    },
    backButton: {
      width: 40, height: 40, borderRadius: 20, backgroundColor: Colors.surface,
      justifyContent: 'center', alignItems: 'center',
    },
    headerTitle: { fontSize: 20, fontWeight: '700', color: Colors.textPrimary },
    scroll: { padding: Spacing.xl, paddingBottom: 140 },
    section: { width: '100%' },
    label: {
      ...Typography.label, color: Colors.textSecondary, marginBottom: Spacing.xs,
      fontSize: 13, fontWeight: '700',
    },
    
    // Type Toggle Styling (Product vs Service)
    typeToggleContainer: {
      flexDirection: 'row',
      backgroundColor: Colors.surface,
      borderRadius: 12,
      padding: 4,
      marginBottom: 16,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    typeToggleBtn: {
      flex: 1,
      paddingVertical: 10,
      borderRadius: 8,
      alignItems: 'center',
      justifyContent: 'center',
    },
    typeToggleBtnActive: {
      backgroundColor: Colors.primary,
    },
    typeToggleText: {
      fontSize: 14,
      fontWeight: '700',
      color: Colors.textSecondary,
    },
    typeToggleTextActive: {
      color: '#FFFFFF',
    },

    // Chip options container
    chipRow: {
      flexDirection: 'row',
      gap: 8,
      marginBottom: 16,
      flexWrap: 'wrap',
    },
    chipBtn: {
      paddingVertical: 8,
      paddingHorizontal: 14,
      borderRadius: 8,
      backgroundColor: Colors.surfaceElevated,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    chipBtnActive: {
      backgroundColor: Colors.primary,
      borderColor: Colors.primaryLight,
    },
    chipText: {
      fontSize: 13,
      fontWeight: '600',
      color: Colors.textSecondary,
    },
    chipTextActive: {
      color: '#FFFFFF',
      fontWeight: '700',
    },

    // Switch row container
    switchRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 16,
      paddingVertical: 4,
    },

    catalogScanBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.sm,
      height: 52, backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
      marginBottom: Spacing.md, ...Shadows.small,
    },
    catalogScanBtnText: { ...Typography.label, color: Colors.textOnPrimary, fontWeight: '700' },
    searchRow: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.lg },
    searchInput: {
      flex: 1, height: 52, backgroundColor: Colors.surface, borderRadius: BorderRadius.md,
      borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.lg,
      color: Colors.textPrimary, ...Typography.body,
    },
    searchBtn: {
      width: 52, height: 52, backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
      justifyContent: 'center', alignItems: 'center', ...Shadows.small,
    },
    matchesWrapper: { marginBottom: Spacing.xl },
    matchesHeading: { ...Typography.bodySmall, color: Colors.textSecondary, fontWeight: '700', marginBottom: Spacing.sm },
    matchCard: {
      flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface,
      borderRadius: BorderRadius.md, borderWidth: 1, borderColor: Colors.border,
      padding: Spacing.md, marginBottom: Spacing.xs,
    },
    matchCardActive: { borderColor: Colors.secondary, backgroundColor: Colors.surfaceElevated, ...Shadows.small },
    matchThumb: { width: 44, height: 44, borderRadius: BorderRadius.sm, marginHorizontal: Spacing.sm },
    matchName: { ...Typography.body, color: Colors.textPrimary, fontWeight: '600' },
    matchCategory: { ...Typography.caption, color: Colors.textMuted },
    matchDesc: { ...Typography.bodySmall, color: Colors.textSecondary, fontSize: 11, marginTop: 2 },
    linkConfigCard: {
      backgroundColor: Colors.surfaceGlass, borderRadius: BorderRadius.xl,
      padding: Spacing.xl, borderWidth: 1, borderColor: Colors.border,
      ...Shadows.medium, marginBottom: Spacing.xl,
    },
    configHeading: { ...Typography.h3, color: Colors.textPrimary, marginBottom: Spacing.lg, textAlign: 'center' },
    fieldGroup: { marginBottom: Spacing.lg },
    configLabel: {
      ...Typography.label, color: Colors.textSecondary, marginBottom: Spacing.xs,
      fontSize: 12, fontWeight: '700',
    },
    input: {
      backgroundColor: Colors.surface, borderRadius: BorderRadius.md, borderWidth: 1,
      borderColor: Colors.border, paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md,
      color: Colors.textPrimary, ...Typography.body, height: 52,
    },
    multiline: { height: 80, paddingTop: Spacing.md },
    submitBtn: {
      width: '100%', height: 52, backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
      justifyContent: 'center', alignItems: 'center', flexDirection: 'row', gap: Spacing.sm,
      overflow: 'hidden', ...Shadows.small, marginTop: Spacing.sm,
    },
    gradientBtn: {
      flex: 1, flexDirection: 'row', justifyContent: 'center', alignItems: 'center',
      gap: Spacing.sm, width: '100%', height: '100%',
    },
    submitBtnText: { ...Typography.button, color: Colors.textOnPrimary, fontSize: 16, fontWeight: '700' },
    buttonDisabled: { opacity: 0.6 },
    fallbackBox: {
      backgroundColor: 'rgba(255, 255, 255, 0.02)', borderRadius: BorderRadius.md,
      borderWidth: 1, borderColor: Colors.border, padding: Spacing.xl,
      alignItems: 'center', marginTop: Spacing.lg,
    },
    fallbackText: { ...Typography.bodySmall, color: Colors.textMuted, marginBottom: Spacing.sm, textAlign: 'center' },
    fallbackBtn: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
    fallbackBtnText: { ...Typography.label, color: Colors.primary, fontWeight: '700' },
    card: {
      backgroundColor: Colors.surfaceGlass, borderRadius: BorderRadius.xl,
      padding: Spacing.xl, borderWidth: 1, borderColor: Colors.border, ...Shadows.medium,
    },
    photoPickerBtn: {
      height: 120, backgroundColor: Colors.surface, borderWidth: 1, borderStyle: 'dashed',
      borderColor: Colors.primary, borderRadius: BorderRadius.md, justifyContent: 'center',
      alignItems: 'center', gap: Spacing.sm,
    },
    photoPickerText: { ...Typography.caption, color: Colors.textSecondary, fontWeight: '600' },
    imagePreviewContainer: {
      height: 150, borderRadius: BorderRadius.md, overflow: 'hidden', position: 'relative',
      borderWidth: 1, borderColor: Colors.border,
    },
    imagePreview: { width: '100%', height: '100%' },
    removeImageBtn: {
      position: 'absolute', top: Spacing.sm, right: Spacing.sm, width: 36, height: 36,
      borderRadius: 18, backgroundColor: Colors.surfaceGlass, justifyContent: 'center',
      alignItems: 'center', borderWidth: 1, borderColor: Colors.border,
    },
    horizontalScroll: { paddingVertical: Spacing.xs },
    categoryPill: {
      paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm, borderRadius: BorderRadius.full,
      backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border, marginHorizontal: 4,
    },
    categoryPillActive: { backgroundColor: Colors.primary, borderColor: Colors.primaryLight },
    categoryPillText: { ...Typography.bodySmall, color: Colors.textSecondary },
    categoryPillTextActive: { color: Colors.textOnPrimary, fontWeight: '700' },
    secondaryScroll: { paddingVertical: Spacing.xs, flexDirection: 'row', gap: Spacing.md },
    secThumbContainer: { position: 'relative', width: 80, height: 80, marginHorizontal: 4 },
    secThumb: { width: 80, height: 80, borderRadius: BorderRadius.md, borderWidth: 1, borderColor: Colors.border },
    removeSecBtn: { position: 'absolute', top: -4, right: -4, zIndex: 5 },
    addSecBtn: {
      width: 80, height: 80, borderRadius: BorderRadius.md, borderWidth: 1, borderStyle: 'dashed',
      borderColor: Colors.primary, justifyContent: 'center', alignItems: 'center', gap: 4,
      backgroundColor: Colors.surface,
    },
    addSecText: { ...Typography.caption, color: Colors.primary, fontSize: 10, fontWeight: '600' },
    barcodeInputRow: { flexDirection: 'row', gap: Spacing.sm, alignItems: 'center' },
    inlineScanBtn: {
      width: 52, height: 52, backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
      justifyContent: 'center', alignItems: 'center',
    },
    scannerModalContainer: { flex: 1, backgroundColor: '#000' },
    scannerModalHeader: {
      position: 'absolute', top: Platform.OS === 'ios' ? 60 : 40,
      left: 0, right: 0, zIndex: 10, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20,
    },
    scannerCloseBtn: { padding: 8, backgroundColor: 'rgba(0,0,0,0.5)', borderRadius: 20 },
    scannerModalTitle: { color: '#FFF', fontSize: 18, fontWeight: 'bold', marginStart: 16 },
    scannerOverlay: { ...StyleSheet.absoluteFillObject, justifyContent: 'center', alignItems: 'center' },
    scannerTargetBox: {
      width: 280, height: 180, borderWidth: 2, borderColor: Colors.secondary,
      backgroundColor: 'transparent', borderRadius: BorderRadius.md,
    },
    shopList: { flexDirection: 'row', gap: Spacing.sm, flexWrap: 'wrap', marginTop: Spacing.xs },
    shopOption: {
      flexDirection: 'row', alignItems: 'center', gap: Spacing.xs,
      backgroundColor: Colors.surface, paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md,
      borderRadius: BorderRadius.md, borderWidth: 1, borderColor: Colors.border,
    },
    shopOptionActive: { backgroundColor: Colors.primary, borderColor: Colors.primaryLight },
    shopText: { ...Typography.body, color: Colors.textMuted },
    shopTextActive: { color: Colors.textOnPrimary, fontWeight: '700' },
    uploadArea: {
      borderWidth: 2, borderColor: Colors.border, borderStyle: 'dashed',
      borderRadius: BorderRadius.xl, padding: Spacing.xxxl, alignItems: 'center',
      marginBottom: Spacing.xl, backgroundColor: Colors.surface,
    },
    uploadAreaDisabled: { opacity: 0.7 },
    uploadIcon: {
      width: 72, height: 72, borderRadius: 36, backgroundColor: Colors.surfaceElevated,
      justifyContent: 'center', alignItems: 'center', marginBottom: Spacing.lg, ...Shadows.glow,
    },
    uploadTitle: { ...Typography.h3, color: Colors.textPrimary, marginBottom: Spacing.sm },
    uploadText: { ...Typography.bodySmall, color: Colors.textMuted, textAlign: 'center' },
    resultCard: {
      flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
      backgroundColor: Colors.surface, borderRadius: BorderRadius.md, padding: Spacing.lg,
      marginBottom: Spacing.xl, borderWidth: 1, borderColor: Colors.success,
    },
    resultInfo: { flex: 1 },
    resultTitle: { ...Typography.body, color: Colors.success, fontWeight: '600' },
    resultDetail: { ...Typography.bodySmall, color: Colors.textSecondary, marginTop: 2 },
    helpCard: {
      backgroundColor: Colors.surface, borderRadius: BorderRadius.md, padding: Spacing.lg,
      borderWidth: 1, borderColor: Colors.border,
    },
    helpTitle: { ...Typography.label, color: Colors.textSecondary, marginBottom: Spacing.md, textAlign: isAr ? 'right' : 'left' },
    codeBlock: {
      backgroundColor: Colors.background, borderRadius: BorderRadius.sm, padding: Spacing.md,
    },
    code: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 11, color: Colors.textMuted, lineHeight: 18 },
  }), [Colors, isAr]);

  if (loadingMarket) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity
            onPress={() => {
              if (router.canGoBack()) {
                router.back();
              } else {
                router.replace('/(merchant)/dashboard');
              }
            }}
            style={styles.backButton}
            activeOpacity={0.7}
          >
            <Ionicons name={isAr ? "arrow-forward" : "arrow-back"} size={24} color={Colors.textPrimary} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>{t('merchant.add_product_title', 'Add Product / Service')}</Text>
          <View style={{ width: 40 }} />
        </View>

        {/* Full-width Segmented Control Tabs */}
        <View style={{
          flexDirection: 'row',
          backgroundColor: Colors.surface,
          borderRadius: 10,
          padding: 3,
          marginHorizontal: 16,
          marginBottom: 16,
          borderWidth: 1,
          borderColor: Colors.border,
        }}>
          {[
            { key: 'new', label: t('merchant.tab_new', 'Add New') },
            { key: 'catalog', label: t('merchant.tab_catalog', 'From Catalog') },
            { key: 'bulk', label: t('merchant.tab_bulk', 'Bulk Upload') },
          ].map(tab => (
            <TouchableOpacity
              key={tab.key}
              onPress={() => setActiveTab(tab.key as any)}
              style={{
                flex: 1,
                paddingVertical: 10,
                borderRadius: 8,
                backgroundColor: activeTab === tab.key ? Colors.primary : 'transparent',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              activeOpacity={0.8}
            >
              <Text style={{
                color: activeTab === tab.key ? '#FFFFFF' : Colors.textSecondary,
                fontSize: 13,
                fontWeight: '600',
              }}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">

          {/* TAB 1: Ingest New Item (Product / Service) — Default Tab */}
          {activeTab === 'new' && (
            <View style={styles.section}>
              <View style={styles.card}>
                
                {/* 1. Type Toggle at top of form */}
                <View style={styles.typeToggleContainer}>
                  <TouchableOpacity
                    onPress={() => setListingType('product')}
                    style={[
                      styles.typeToggleBtn,
                      listingType === 'product' && styles.typeToggleBtnActive,
                    ]}
                    activeOpacity={0.8}
                  >
                    <Text style={[
                      styles.typeToggleText,
                      listingType === 'product' && styles.typeToggleTextActive,
                    ]}>
                      🏷️ {t('merchant.product_toggle', 'Product')}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    onPress={() => setListingType('service')}
                    style={[
                      styles.typeToggleBtn,
                      listingType === 'service' && styles.typeToggleBtnActive,
                    ]}
                    activeOpacity={0.8}
                  >
                    <Text style={[
                      styles.typeToggleText,
                      listingType === 'service' && styles.typeToggleTextActive,
                    ]}>
                      🔧 {t('merchant.service_toggle', 'Service')}
                    </Text>
                  </TouchableOpacity>
                </View>

                {/* 2. Barcode Input (Product only) */}
                {listingType === 'product' && (
                  <View style={styles.fieldGroup}>
                    <Text style={styles.configLabel}>{t('merchant.barcode', 'Barcode')}</Text>
                    <View style={styles.barcodeInputRow}>
                      <TextInput
                        style={[styles.input, { flex: 1, marginBottom: 0 }]}
                        value={barcode}
                        onChangeText={setBarcode}
                        placeholder={t('merchant.scan_barcode', 'Scan or enter barcode')}
                        placeholderTextColor={Colors.textMuted}
                        keyboardType="number-pad"
                      />
                      <TouchableOpacity 
                        style={styles.inlineScanBtn}
                        onPress={async () => {
                          if (!cameraPermission?.granted) {
                            const result = await requestCameraPermission();
                            if (result.granted) setShowScanner(true);
                          } else {
                            setShowScanner(true);
                          }
                        }}
                        activeOpacity={0.8}
                      >
                        <Ionicons name="barcode-outline" size={24} color={Colors.textOnPrimary} />
                      </TouchableOpacity>
                    </View>
                  </View>
                )}

                {/* 3. Product / Service Name (Shared) */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>
                    {t('merchant.item_name', 'Item Name')} *
                  </Text>
                  <TextInput
                    style={styles.input}
                    value={newItemName}
                    onChangeText={setNewItemName}
                    placeholder={t('merchant.item_name_placeholder', 'e.g. Natural Honey')}
                    placeholderTextColor={Colors.textMuted}
                  />
                </View>

                {/* 4. Description (Shared) */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>{t('merchant.description', 'Description (for AI categorization)')}</Text>
                  <TextInput
                    style={[styles.input, styles.multiline]}
                    value={newItemDesc}
                    onChangeText={setNewItemDesc}
                    placeholder={
                      listingType === 'product'
                        ? t('merchant.desc_product_hint', 'Describe ingredients, brand, or flavor profile...')
                        : t('merchant.desc_service_hint', 'Describe service details, duration, requirements...')
                    }
                    placeholderTextColor={Colors.textMuted}
                    multiline
                    numberOfLines={3}
                    textAlignVertical="top"
                  />
                </View>

                {/* 5. Dynamic Category Tree selector (Filtered by listingType) */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>{t('merchant.select_category', 'Select Category')}</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.horizontalScroll}>
                    {filteredCategories.map((cat) => {
                      const isActive = selectedCategory === cat.id;
                      const catName = i18n.locale?.startsWith('ar') ? (cat.name_ar || cat.name) : (cat.name_en || cat.name);
                      return (
                        <TouchableOpacity
                          key={cat.id}
                          style={[styles.categoryPill, isActive && styles.categoryPillActive]}
                          onPress={() => {
                            setSelectedCategory(isActive ? '' : cat.id);
                            setSelectedSubcategory('');
                          }}
                        >
                          <Text style={[styles.categoryPillText, isActive && styles.categoryPillTextActive]}>
                            {catName}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </ScrollView>
                </View>

                {/* Subcategory selector row */}
                {selectedCategory && subcategories.length > 0 && (
                  <View style={styles.fieldGroup}>
                    <Text style={styles.configLabel}>{t('addProduct.subcategory', 'Subcategory (Optional)')}</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.horizontalScroll}>
                      {subcategories.map((sub: any) => {
                        const isActive = selectedSubcategory === sub.id;
                        const subName = i18n.locale?.startsWith('ar') ? (sub.name_ar || sub.name) : (sub.name_en || sub.name);
                        return (
                          <TouchableOpacity
                            key={sub.id}
                            style={[styles.categoryPill, isActive && styles.categoryPillActive]}
                            onPress={() => setSelectedSubcategory(isActive ? '' : sub.id)}
                          >
                            <Text style={[styles.categoryPillText, isActive && styles.categoryPillTextActive]}>
                              {subName}
                            </Text>
                          </TouchableOpacity>
                        );
                      })}
                    </ScrollView>
                  </View>
                )}

                {/* 6. Product-only fields: Stock Status & Stock Count */}
                {listingType === 'product' && (
                  <>
                    {/* Stock Status Chips */}
                    <View style={styles.fieldGroup}>
                      <Text style={styles.configLabel}>{t('merchant.stock_status', 'Stock Availability')}</Text>
                      <View style={styles.chipRow}>
                        {[
                          { key: 'available', label: t('merchant.available', 'Available') },
                          { key: 'limited', label: t('merchant.limited', 'Limited') },
                          { key: 'out_of_stock', label: t('merchant.out_of_stock', 'Out of Stock') },
                        ].map(st => (
                          <TouchableOpacity
                            key={st.key}
                            onPress={() => setStockStatus(st.key)}
                            style={[
                              styles.chipBtn,
                              stockStatus === st.key && styles.chipBtnActive,
                            ]}
                          >
                            <Text style={[
                              styles.chipText,
                              stockStatus === st.key && styles.chipTextActive,
                            ]}>
                              {st.label}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>

                    {/* Stock Count */}
                    <View style={styles.fieldGroup}>
                      <Text style={styles.configLabel}>{t('merchant.stock_count', 'Initial Stock Count')}</Text>
                      <TextInput
                        style={styles.input}
                        keyboardType="numeric"
                        value={stockCount}
                        onChangeText={setStockCount}
                      />
                    </View>
                  </>
                )}

                {/* 7. Service-only fields: Target Audience / Gender, Appointment Required, Home Service */}
                {listingType === 'service' && (
                  <>
                    {/* Target Audience / Gender */}
                    <View style={styles.fieldGroup}>
                      <Text style={styles.configLabel}>{t('merchant.target_audience', 'Target Audience')}</Text>
                      <View style={styles.chipRow}>
                        {[
                          { value: 'male', label: t('merchant.men', 'Men') },
                          { value: 'female', label: t('merchant.women', 'Women') },
                          { value: 'unisex', label: t('merchant.all_audience', 'Unisex / All') },
                        ].map(opt => (
                          <TouchableOpacity
                            key={opt.value}
                            onPress={() => setGender(gender === opt.value ? null : opt.value)}
                            style={[
                              styles.chipBtn,
                              gender === opt.value && styles.chipBtnActive,
                            ]}
                          >
                            <Text style={[
                              styles.chipText,
                              gender === opt.value && styles.chipTextActive,
                            ]}>
                              {opt.label}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>

                    {/* Appointment Required */}
                    <View style={styles.switchRow}>
                      <Text style={styles.configLabel}>{t('merchant.appointment_required', 'Appointment Required?')}</Text>
                      <Switch
                        value={appointmentRequired}
                        onValueChange={setAppointmentRequired}
                        trackColor={{ true: Colors.primary, false: Colors.surfaceElevated }}
                        thumbColor={Platform.OS === 'android' ? (appointmentRequired ? Colors.primaryLight : '#f4f3f4') : undefined}
                      />
                    </View>

                    {/* Home Service Available */}
                    <View style={styles.switchRow}>
                      <Text style={styles.configLabel}>{t('merchant.home_service', 'Home Service Available?')}</Text>
                      <Switch
                        value={homeServiceAvailable}
                        onValueChange={setHomeServiceAvailable}
                        trackColor={{ true: Colors.primary, false: Colors.surfaceElevated }}
                        thumbColor={Platform.OS === 'android' ? (homeServiceAvailable ? Colors.primaryLight : '#f4f3f4') : undefined}
                      />
                    </View>
                  </>
                )}

                {/* 8. Price (Shared) */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>{t('addProduct.price_jod', 'Price (JOD)')}</Text>
                  <TextInput
                    style={styles.input}
                    keyboardType="decimal-pad"
                    value={newItemPrice}
                    onChangeText={setNewItemPrice}
                    placeholder="0.00"
                    placeholderTextColor={Colors.textMuted}
                  />
                </View>

                {/* 9. Primary Image Picker (Shared) */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>{t('merchant.primary_photo', 'Primary Thumbnail Photo *')}</Text>
                  {imageUri ? (
                    <View style={styles.imagePreviewContainer}>
                      <Image source={{ uri: imageUri }} style={styles.imagePreview} />
                      <TouchableOpacity style={styles.removeImageBtn} onPress={() => setImageUri(null)}>
                        <Ionicons name="trash-outline" size={18} color={Colors.error} />
                      </TouchableOpacity>
                    </View>
                  ) : (
                    <TouchableOpacity style={styles.photoPickerBtn} onPress={pickImage} activeOpacity={0.7}>
                      <Ionicons name="camera-outline" size={32} color={Colors.primary} />
                      <Text style={styles.photoPickerText}>{t('merchant.add_photo', 'Select Primary Photo')}</Text>
                    </TouchableOpacity>
                  )}
                </View>

                {/* 10. Secondary Gallery Photos Picker (Shared) */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>{t('merchant.photos', 'Secondary Gallery Photos')}</Text>
                  
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.secondaryScroll}>
                    {secondaryImageUris.map((uri, idx) => (
                      <View key={idx} style={styles.secThumbContainer}>
                        <Image source={{ uri }} style={styles.secThumb} />
                        <TouchableOpacity
                          style={styles.removeSecBtn}
                          onPress={() => setSecondaryImageUris(prev => prev.filter((_, i) => i !== idx))}
                        >
                          <Ionicons name="close-circle" size={16} color={Colors.error} />
                        </TouchableOpacity>
                      </View>
                    ))}
                    
                    <TouchableOpacity style={styles.addSecBtn} onPress={pickSecondaryImage} activeOpacity={0.7}>
                      <Ionicons name="add" size={20} color={Colors.primary} />
                      <Text style={styles.addSecText}>{t('merchant.add_photo', 'Detail Photo')}</Text>
                    </TouchableOpacity>
                  </ScrollView>
                </View>

                {/* 11. Submit Button */}
                <TouchableOpacity
                  style={[styles.submitBtn, loading && styles.buttonDisabled]}
                  onPress={handleAddNewItem}
                  disabled={loading}
                  activeOpacity={0.85}
                >
                  {loading ? (
                    <ActivityIndicator color={Colors.textOnPrimary} />
                  ) : (
                    <LinearGradient
                      colors={[Colors.primary, Colors.primaryDark]}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 0 }}
                      style={styles.gradientBtn}
                    >
                      <Ionicons name="save-outline" size={20} color={Colors.textOnPrimary} />
                      <Text style={styles.submitBtnText}>
                        {listingType === 'product' 
                          ? t('merchant.submit_product', 'Save Product')
                          : t('merchant.submit_service', 'Save Service')}
                      </Text>
                    </LinearGradient>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* TAB 2: Fuzzy Check Catalog */}
          {activeTab === 'catalog' && (
            <View style={styles.section}>
              <Text style={styles.label}>{t('merchant.tab_catalog', 'Scan or Check Global Catalog')}</Text>
              {/* Barcode route: the scanner in Inventory mode finds the catalog product and links it to this shop */}
              <TouchableOpacity
                style={styles.catalogScanBtn}
                onPress={() => router.push({ pathname: '/(merchant)/scanner', params: { mode: 'inventory' } })}
                activeOpacity={0.85}
                accessibilityRole="button"
                accessibilityLabel={t('merchant.scan_barcode', 'Scan Barcode')}
              >
                <Ionicons name="barcode-outline" size={22} color={Colors.textOnPrimary} />
                <Text style={styles.catalogScanBtnText}>{t('merchant.scan_barcode', 'Scan Barcode')}</Text>
              </TouchableOpacity>
              <View style={styles.searchRow}>
                <TextInput
                  style={styles.searchInput}
                  placeholder={t('merchant.catalog_search_placeholder', 'Enter item name (e.g. Sidr Honey)')}
                  placeholderTextColor={Colors.textMuted}
                  value={searchQuery}
                  onChangeText={(val) => {
                    setSearchQuery(val);
                    setHasSearched(false);
                  }}
                />
                <TouchableOpacity style={styles.searchBtn} onPress={handleSearch} disabled={loading} activeOpacity={0.8}>
                  {loading ? (
                    <ActivityIndicator color={Colors.textOnPrimary} />
                  ) : (
                    <Ionicons name="search" size={22} color={Colors.textOnPrimary} />
                  )}
                </TouchableOpacity>
              </View>

              {/* Fuzzy matches results */}
              {hasSearched && matches.length > 0 && (
                <View style={styles.matchesWrapper}>
                  <Text style={styles.matchesHeading}>{t('inventory.results', 'Matches Found in Catalog:')}</Text>
                  {matches.map((item) => {
                    const isSelected = selectedMatch?.id === item.id;
                    return (
                      <TouchableOpacity
                        key={item.id}
                        style={[styles.matchCard, isSelected && styles.matchCardActive]}
                        onPress={() => setSelectedMatch(item)}
                        activeOpacity={0.8}
                      >
                        {item.image_url && (
                          <Image
                            source={{ uri: resolveImageUrl(item.image_url) }}
                            style={styles.matchThumb}
                          />
                        )}
                        <View style={{ flex: 1 }}>
                          <Text style={styles.matchName}>
                            {i18n.locale?.startsWith('ar') ? (item.name_ar || item.name) : (item.name_en || item.name)}
                          </Text>
                          <Text style={styles.matchCategory}>
                            {categoryLabel(item, i18n.locale?.startsWith('ar'), t('common.general', 'General'))}
                          </Text>
                          {!!item.description && (
                            <Text style={styles.matchDesc} numberOfLines={1}>{item.description}</Text>
                          )}
                        </View>
                        <Ionicons
                          name={isSelected ? 'checkmark-circle' : 'ellipse-outline'}
                          size={22}
                          color={isSelected ? Colors.secondary : Colors.textMuted}
                        />
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}

              {/* Match Selected Options */}
              {selectedMatch && (
                <View style={styles.linkConfigCard}>
                  <Text style={styles.configHeading}>{t('inventory.in_stock', 'Link Stock Parameters')}</Text>
                  
                  <View style={styles.fieldGroup}>
                    <Text style={styles.configLabel}>{t('merchant.stock_count', 'Initial Stock Count')}</Text>
                    <TextInput
                      style={styles.input}
                      keyboardType="numeric"
                      value={stockCount}
                      onChangeText={setStockCount}
                    />
                  </View>

                  <View style={styles.fieldGroup}>
                    <Text style={styles.configLabel}>{isAr ? 'السعر (دينار) (اختياري)' : 'Price (JOD) (Optional)'}</Text>
                    <TextInput
                      style={styles.input}
                      keyboardType="decimal-pad"
                      value={linkPrice}
                      onChangeText={setLinkPrice}
                      placeholder={isAr ? '0.00 (اختياري)' : '0.00 (Optional)'}
                      placeholderTextColor={Colors.textMuted}
                    />
                  </View>

                  <TouchableOpacity style={styles.submitBtn} onPress={handleLinkItem} disabled={loading} activeOpacity={0.85}>
                    {loading ? (
                      <ActivityIndicator color={Colors.textOnPrimary} />
                    ) : (
                      <>
                        <Ionicons name="link-outline" size={18} color={Colors.textOnPrimary} />
                        <Text style={styles.submitBtnText}>{t('common.save', 'Link to Market Stock')}</Text>
                      </>
                    )}
                  </TouchableOpacity>
                </View>
              )}

              {/* Fallback to Ingest New */}
              {hasSearched && (
                <View style={styles.fallbackBox}>
                  <Text style={styles.fallbackText}>
                    {matches.length > 0 
                      ? t('explore.no_results', "Don't see your exact product in the matches?")
                      : t('explore.no_results', 'No matches found in the global catalog.')}
                  </Text>
                  <TouchableOpacity style={styles.fallbackBtn} onPress={triggerNewForm} activeOpacity={0.7}>
                    <Text style={styles.fallbackBtnText}>{t('merchant.tab_new', 'Ingest as Brand-New AI Item')}</Text>
                    <Ionicons name="arrow-forward" size={16} color={Colors.primary} />
                  </TouchableOpacity>
                </View>
              )}
            </View>
          )}

          {/* TAB 3: Bulk CSV Upload */}
          {activeTab === 'bulk' && (
            <View style={styles.section}>
              <Text style={styles.label}>{t('merchant.bulk_upload_title', 'Upload bulk items CSV')}</Text>
              
              {/* Shop Selector */}
              {shops.length > 0 && (
                <View style={{ marginBottom: Spacing.xl }}>
                  <Text style={styles.configLabel}>{t('merchant.store_name', 'Select Shop')}</Text>
                  <View style={styles.shopList}>
                    {shops.map(shop => (
                      <TouchableOpacity
                        key={shop.id}
                        style={[styles.shopOption, selectedShopId === shop.id && styles.shopOptionActive]}
                        onPress={() => setSelectedShopId(shop.id)}
                      >
                        <Ionicons name="storefront" size={16}
                          color={selectedShopId === shop.id ? Colors.textOnPrimary : Colors.textMuted} />
                        <Text style={[styles.shopText, selectedShopId === shop.id && styles.shopTextActive]}>
                          {shop.name}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              )}

              {/* Upload Area */}
              <TouchableOpacity
                style={[styles.uploadArea, loading && styles.uploadAreaDisabled]}
                onPress={handleCSVUpload}
                disabled={loading}
                activeOpacity={0.7}
              >
                {loading ? (
                  <View style={{ alignItems: 'center' }}>
                    <ActivityIndicator size="large" color={Colors.primary} />
                    <Text style={[styles.uploadText, { marginTop: Spacing.sm }]}>{t('common.loading', 'Processing & indexing with CLIP...')}</Text>
                  </View>
                ) : (
                  <View style={{ alignItems: 'center' }}>
                    <View style={styles.uploadIcon}>
                      <Ionicons name="cloud-upload" size={40} color={Colors.primary} />
                    </View>
                    <Text style={styles.uploadTitle}>{t('merchant.bulk_upload_title', 'Tap to select CSV file')}</Text>
                    <Text style={styles.uploadText}>
                      {t('merchant.bulk_upload_desc', 'Expected columns: name, description, price, category, in_stock, listing_type')}
                    </Text>
                  </View>
                )}
              </TouchableOpacity>

              {/* Upload Result */}
              {csvUploadResult && (
                <View style={styles.resultCard}>
                  <Ionicons name="checkmark-circle" size={24} color={Colors.success} />
                  <View style={styles.resultInfo}>
                    <Text style={styles.resultTitle}>{t('common.success', 'Import Complete')}</Text>
                    <Text style={styles.resultDetail}>
                      {csvUploadResult.created} {t('scanner.items', 'items created')}, {csvUploadResult.indexed} {t('inventory.in_stock', 'indexed for search')}
                    </Text>
                  </View>
                </View>
              )}

              {/* CSV Format Help */}
              <View style={styles.helpCard}>
                <Text style={styles.helpTitle}>{t('merchant.bulk_upload_title', 'CSV Format Example')}</Text>
                <View style={styles.codeBlock}>
                  <Text style={styles.code}>name,description,price,category,in_stock,listing_type</Text>
                  <Text style={styles.code}>Green Tea,Organic matcha,45.00,Tea,true,product</Text>
                  <Text style={styles.code}>Men Haircut,Beard and haircut,15.00,Beauty,true,service</Text>
                </View>
              </View>
            </View>
          )}

        </ScrollView>
      </KeyboardAvoidingView>

      {/* Inline Barcode Scanner Modal */}
      <Modal visible={showScanner} animationType="slide" transparent={false} onRequestClose={() => setShowScanner(false)}>
        <View style={styles.scannerModalContainer}>
          <View style={styles.scannerModalHeader}>
            <TouchableOpacity onPress={() => setShowScanner(false)} style={styles.scannerCloseBtn} activeOpacity={0.7}>
              <Ionicons name="close" size={28} color="#FFF" />
            </TouchableOpacity>
            <Text style={styles.scannerModalTitle}>{t('scanner.scan_barcode', 'Scan Product Barcode')}</Text>
          </View>
          {showScanner && (
            <CameraView
              style={StyleSheet.absoluteFillObject}
              facing="back"
              barcodeScannerSettings={{
                barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code39', 'code128', 'itf14'],
              }}
              onBarcodeScanned={({ data }) => {
                setBarcode(data);
                setShowScanner(false);
              }}
            />
          )}
          {/* Scanner Overlay Box */}
          <View style={styles.scannerOverlay} pointerEvents="none">
            <View style={styles.scannerTargetBox} />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}