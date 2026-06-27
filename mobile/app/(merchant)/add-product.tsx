/**
 * Upgraded Add Product Screen — Two-step Catalog Integration & AI Ingestion.
 * Step 1: Fuzzy search global catalog to check for existing item.
 * Step 2: Link existing item with stock OR ingest new product via CLIP/MiniLM AI.
 * Now equipped with dynamic Category Tree selectors and Multi-Image uploads.
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, Alert, ActivityIndicator, KeyboardAvoidingView, Platform, Image, Modal
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { CameraView, useCameraPermissions } from 'expo-camera';
import api, {
  getMyMarket, checkItemName, linkExistingItem, addNewItem,
  getCategories, CatalogItemMatch, getMyShops
} from '../../services/api';
import { Colors, Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { t, i18n } from '../../services/i18n';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

export default function AddProductScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ barcode?: string }>();
  
  // Market setup check
  const [marketId, setMarketId] = useState<string | null>(null);
  const [loadingMarket, setLoadingMarket] = useState(true);

  // General state
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [matches, setMatches] = useState<CatalogItemMatch[]>([]);
  const [selectedMatch, setSelectedMatch] = useState<CatalogItemMatch | null>(null);
  const [stockCount, setStockCount] = useState('10');
  const [barcode, setBarcode] = useState('');
  
  // Inline scanner state
  const [showScanner, setShowScanner] = useState(false);
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();

  useEffect(() => {
    if (params.barcode) {
      setBarcode(params.barcode);
      setActiveMode('create');
      setShowNewForm(true);
    }
  }, [params.barcode]);

  // New Item (AI pipeline) and CSV state
  const [showNewForm, setShowNewForm] = useState(false);
  const [activeMode, setActiveMode] = useState<'search' | 'create' | 'csv'>('search');
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

  const subcategories = useMemo(() => {
    if (!selectedCategory) return [];
    return categoriesTree.find(c => c.id === selectedCategory)?.subcategories || [];
  }, [categoriesTree, selectedCategory]);

  useEffect(() => {
    (async () => {
      try {
        const market = await getMyMarket();
        setMarketId(market.id);
        
        // Load categories tree
        const cats = await getCategories();
        setCategoriesTree(cats);

        // Load shops for CSV upload
        try {
          const shopList = await getMyShops();
          setShops(shopList);
          if (shopList.length > 0) {
            setSelectedShopId(shopList[0].id);
          }
        } catch (err) {
          // Non-blocking catch
        }
      } catch (err: any) {
        Alert.alert(
          'Market Required',
          'You need to initialize your market before managing stocks.',
          [{ text: 'OK', onPress: () => router.replace('/(merchant)/onboarding') }]
        );
      } finally {
        setLoadingMarket(false);
        setLoadingShops(false);
      }
    })();
  }, []);

  // 1. Fuzzy Search Check Catalog
  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      Alert.alert('Error', 'Please enter a name to search the catalog.');
      return;
    }
    setLoading(true);
    setSelectedMatch(null);
    setShowNewForm(false);
    try {
      const resp = await checkItemName(searchQuery.trim());
      setMatches(resp.matches);
      setHasSearched(true);
    } catch (err: any) {
      Alert.alert('Search Failed', 'Failed to query global catalog.');
    } finally {
      setLoading(false);
    }
  };

  // 2. Link Existing Item
  const handleLinkItem = async () => {
    if (!selectedMatch || !marketId) return;
    const stockNum = parseInt(stockCount);
    if (isNaN(stockNum) || stockNum < 0) {
      Alert.alert('Error', 'Please enter a valid stock count.');
      return;
    }

    setLoading(true);
    try {
      const resp = await linkExistingItem(selectedMatch.id, marketId, stockNum);
      if (resp.success) {
        Alert.alert('Success', resp.message, [
          { text: 'OK', onPress: () => router.replace('/(merchant)/dashboard') }
        ]);
      }
    } catch (err: any) {
      Alert.alert('Linking Failed', err?.response?.data?.detail || 'Failed to link item.');
    } finally {
      setLoading(false);
    }
  };

  // 3. Primary Photo Picker
  const handlePickImage = async () => {
    const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (permissionResult.granted === false) {
      Alert.alert(t('scanner.permission_denied', 'Permission Required'), t('addProduct.media_library_permission', 'Library permissions are required to upload a product photo.'));
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [4, 3],
      quality: 0.8,
    });

    if (!result.canceled) {
      setImageUri(result.assets[0].uri);
    }
  };

  // 4. Secondary Detail Photos Picker
  const handlePickSecondaryImages = async () => {
    const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (permissionResult.granted === false) {
      Alert.alert(t('scanner.permission_denied', 'Permission Required'), t('addProduct.media_library_permission_secondary', 'Library permissions are required to upload secondary photos.'));
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      quality: 0.8,
    });

    if (!result.canceled && result.assets) {
      const uris = result.assets.map(asset => asset.uri);
      setSecondaryImageUris(prev => [...prev, ...uris]);
    }
  };

  // 5. Ingest Brand-New Product
  const handleAddNewItem = async () => {
    if (!newItemName.trim() || !imageUri || !marketId) {
      Alert.alert('Error', 'Item name and primary photo are mandatory for new catalog ingestion.');
      return;
    }

    const stockNum = parseInt(stockCount);
    if (isNaN(stockNum) || stockNum < 0) {
      Alert.alert('Error', 'Please enter a valid stock count.');
      return;
    }

    const priceVal = parseFloat(newItemPrice);
    if (isNaN(priceVal) || priceVal < 0) {
      Alert.alert('Error', 'Please enter a valid price.');
      return;
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
      if (barcode.trim()) {
        formData.append('barcode', barcode.trim());
      }
      formData.append('stock_count', stockNum.toString());

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
          type: secType,
        } as any);
      });

      const resp = await addNewItem(formData);
      if (resp.success) {
        Alert.alert(
          'AI Ingestion Complete',
          'Your product was successfully auto-categorized, vector-encoded, and added to your store!',
          [{ text: 'Great', onPress: () => router.replace('/(merchant)/dashboard') }]
        );
      }
    } catch (err: any) {
      Alert.alert(
        'AI Ingestion Failed',
        err?.response?.data?.detail || 'An error occurred during AI extraction.'
      );
    } finally {
      setLoading(false);
    }
  };

  const resolveImageUrl = (url: string | null): string | undefined => {
    if (!url) return undefined;
    if (url.startsWith('http')) return url;
    return `${API_BASE_URL}${url}`;
  };

  const triggerNewForm = () => {
    setNewItemName(searchQuery);
    setShowNewForm(true);
    setActiveMode('create');
    setMatches([]);
    setHasSearched(false);
  };

  const handleCSVUpload = async () => {
    if (!selectedShopId) {
      Alert.alert('Error', 'Please select a shop first');
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

      const response = await api.post(`/api/products/upload-csv/${selectedShopId}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setCsvUploadResult(response.data);
      Alert.alert('Success', response.data.message);
    } catch (err: any) {
      Alert.alert('Upload Failed', err?.response?.data?.detail || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

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
          <TouchableOpacity onPress={() => router.back()} style={styles.backButton} activeOpacity={0.7}>
            <Ionicons name="arrow-back" size={24} color={Colors.textPrimary} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Add Product</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          
          {/* Segmented Tab Selector */}
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.tabScroll}
            contentContainerStyle={styles.tabScrollContainer}
          >
            <TouchableOpacity
              style={[styles.tabButton, activeMode === 'search' && styles.tabButtonActive]}
              onPress={() => {
                setActiveMode('search');
                setShowNewForm(false);
              }}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityLabel={t('addProduct.search_catalog')}
            >
              <Ionicons name="search" size={16} color={activeMode === 'search' ? Colors.secondary : Colors.textMuted} />
              <Text style={[styles.tabText, activeMode === 'search' && styles.tabTextActive]} numberOfLines={1}>
                {t('addProduct.search_catalog')}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.tabButton, activeMode === 'create' && styles.tabButtonActive]}
              onPress={() => {
                setActiveMode('create');
                setShowNewForm(true);
              }}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityLabel={t('addProduct.add_new')}
            >
              <Ionicons name="add-circle" size={16} color={activeMode === 'create' ? Colors.secondary : Colors.textMuted} />
              <Text style={[styles.tabText, activeMode === 'create' && styles.tabTextActive]} numberOfLines={1}>
                {t('addProduct.add_new')}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.tabButton, activeMode === 'csv' && styles.tabButtonActive]}
              onPress={() => {
                setActiveMode('csv');
                setShowNewForm(false);
              }}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityLabel={t('addProduct.bulk_csv')}
            >
              <Ionicons name="cloud-upload" size={16} color={activeMode === 'csv' ? Colors.secondary : Colors.textMuted} />
              <Text style={[styles.tabText, activeMode === 'csv' && styles.tabTextActive]} numberOfLines={1}>
                {t('addProduct.bulk_csv')}
              </Text>
            </TouchableOpacity>
          </ScrollView>

          {/* STEP 1: Fuzzy Check Catalog */}
          {!showNewForm && activeMode === 'search' && (
            <View style={styles.section}>
              <Text style={styles.label}>1. Scan or Check Global Catalog</Text>
              <View style={styles.searchRow}>
                <TextInput
                  style={styles.searchInput}
                  placeholder="Enter item name (e.g. Sidr Honey)"
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
                  <Text style={styles.matchesHeading}>Matches Found in Catalog:</Text>
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
                          <Text style={styles.matchName}>{item.name}</Text>
                          <Text style={styles.matchCategory}>{item.category || 'General'}</Text>
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
                  <Text style={styles.configHeading}>Link Stock Parameters</Text>
                  
                  <View style={styles.fieldGroup}>
                    <Text style={styles.configLabel}>Initial Stock Count</Text>
                    <TextInput
                      style={styles.input}
                      keyboardType="numeric"
                      value={stockCount}
                      onChangeText={setStockCount}
                    />
                  </View>

                  <TouchableOpacity style={styles.submitBtn} onPress={handleLinkItem} disabled={loading} activeOpacity={0.85}>
                    {loading ? (
                      <ActivityIndicator color={Colors.textOnPrimary} />
                    ) : (
                      <>
                        <Ionicons name="link-outline" size={18} color={Colors.textOnPrimary} />
                        <Text style={styles.submitBtnText}>Link to Market Stock</Text>
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
                      ? "Don't see your exact product in the matches?"
                      : "No matches found in the global catalog."}
                  </Text>
                  <TouchableOpacity style={styles.fallbackBtn} onPress={triggerNewForm} activeOpacity={0.7}>
                    <Text style={styles.fallbackBtnText}>Ingest as Brand-New AI Product</Text>
                    <Ionicons name="arrow-forward" size={16} color={Colors.primary} />
                  </TouchableOpacity>
                </View>
              )}
            </View>
          )}

          {/* STEP 2: Ingest New Item (CLIP / MiniLM) */}
          {showNewForm && (
            <View style={styles.section}>
              <View style={styles.newHeaderRow}>
                <Text style={styles.label}>2. Ingest Brand-New Catalog Product</Text>
                <TouchableOpacity onPress={() => setShowNewForm(false)} activeOpacity={0.6}>
                  <Text style={styles.cancelLink}>Cancel</Text>
                </TouchableOpacity>
              </View>

              <View style={styles.card}>
                {/* Barcode Input with Scan Button */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>Barcode (Optional)</Text>
                  <View style={styles.barcodeInputRow}>
                    <TextInput
                      style={[styles.input, { flex: 1, marginBottom: 0 }]}
                      value={barcode}
                      onChangeText={setBarcode}
                      placeholder="Scan or enter barcode"
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

                {/* Product Name */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>Product Name *</Text>
                  <TextInput
                    style={styles.input}
                    value={newItemName}
                    onChangeText={setNewItemName}
                    placeholder="Enter brand name and product type"
                    placeholderTextColor={Colors.textMuted}
                  />
                </View>

                {/* Description */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>Description (for AI categorization)</Text>
                  <TextInput
                    style={[styles.input, styles.multiline]}
                    value={newItemDesc}
                    onChangeText={setNewItemDesc}
                    placeholder="Describe ingredients, brand, or flavor profile..."
                    placeholderTextColor={Colors.textMuted}
                    multiline
                    numberOfLines={3}
                    textAlignVertical="top"
                  />
                </View>

                {/* Dynamic Category Tree selector */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>Select Serving Category</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.horizontalScroll}>
                    {categoriesTree.map((cat) => {
                      const isActive = selectedCategory === cat.id;
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
                            {cat.name}
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
                        return (
                          <TouchableOpacity
                            key={sub.id}
                            style={[styles.categoryPill, isActive && styles.categoryPillActive]}
                            onPress={() => setSelectedSubcategory(isActive ? '' : sub.id)}
                          >
                            <Text style={[styles.categoryPillText, isActive && styles.categoryPillTextActive]}>
                              {sub.name}
                            </Text>
                          </TouchableOpacity>
                        );
                      })}
                    </ScrollView>
                  </View>
                )}

                {/* Stock Count */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>Initial Stock Count</Text>
                  <TextInput
                    style={styles.input}
                    keyboardType="numeric"
                    value={stockCount}
                    onChangeText={setStockCount}
                  />
                </View>

                {/* Price */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>Selling Price (SAR) *</Text>
                  <TextInput
                    style={styles.input}
                    keyboardType="decimal-pad"
                    value={newItemPrice}
                    onChangeText={setNewItemPrice}
                    placeholder="0.00"
                    placeholderTextColor={Colors.textMuted}
                  />
                </View>

                {/* Primary Image Picker */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>Primary Thumbnail Photo *</Text>
                  {imageUri ? (
                    <View style={styles.imagePreviewContainer}>
                      <Image source={{ uri: imageUri }} style={styles.imagePreview} />
                      <TouchableOpacity style={styles.removeImageBtn} onPress={() => setImageUri(null)}>
                        <Ionicons name="trash-outline" size={18} color={Colors.error} />
                      </TouchableOpacity>
                    </View>
                  ) : (
                    <TouchableOpacity style={styles.photoPickerBtn} onPress={handlePickImage} activeOpacity={0.7}>
                      <Ionicons name="camera-outline" size={32} color={Colors.primary} />
                      <Text style={styles.photoPickerText}>Select Primary Photo</Text>
                    </TouchableOpacity>
                  )}
                </View>

                {/* Multiple Secondary Images picker grid */}
                <View style={styles.fieldGroup}>
                  <Text style={styles.configLabel}>Secondary Gallery Photos (Upload Multiple)</Text>
                  
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
                    
                    <TouchableOpacity style={styles.addSecBtn} onPress={handlePickSecondaryImages} activeOpacity={0.7}>
                      <Ionicons name="add" size={20} color={Colors.primary} />
                      <Text style={styles.addSecText}>Detail Photo</Text>
                    </TouchableOpacity>
                  </ScrollView>
                </View>

                {/* Submit AI Ingestion */}
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
                      <Text style={styles.submitBtnText}>Save Product</Text>
                    </LinearGradient>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* STEP 3: Bulk CSV Upload */}
          {activeMode === 'csv' && (
            <View style={styles.section}>
              <Text style={styles.label}>Upload bulk products CSV</Text>
              
              {/* Shop Selector */}
              {shops.length > 0 && (
                <View style={{ marginBottom: Spacing.xl }}>
                  <Text style={styles.configLabel}>Select Shop</Text>
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
                    <Text style={[styles.uploadText, { marginTop: Spacing.sm }]}>Processing & indexing with CLIP...</Text>
                  </View>
                ) : (
                  <View style={{ alignItems: 'center' }}>
                    <View style={styles.uploadIcon}>
                      <Ionicons name="cloud-upload" size={40} color={Colors.primary} />
                    </View>
                    <Text style={styles.uploadTitle}>Tap to select CSV file</Text>
                    <Text style={styles.uploadText}>
                      Expected columns: name, description, price, category, in_stock
                    </Text>
                  </View>
                )}
              </TouchableOpacity>

              {/* Upload Result */}
              {csvUploadResult && (
                <View style={styles.resultCard}>
                  <Ionicons name="checkmark-circle" size={24} color={Colors.success} />
                  <View style={styles.resultInfo}>
                    <Text style={styles.resultTitle}>Import Complete</Text>
                    <Text style={styles.resultDetail}>
                      {csvUploadResult.created} products created, {csvUploadResult.indexed} indexed for search
                    </Text>
                  </View>
                </View>
              )}

              {/* CSV Format Help */}
              <View style={styles.helpCard}>
                <Text style={styles.helpTitle}>CSV Format Example</Text>
                <View style={styles.codeBlock}>
                  <Text style={styles.code}>name,description,price,category,in_stock</Text>
                  <Text style={styles.code}>Green Tea,Organic matcha,45.00,Tea,true</Text>
                  <Text style={styles.code}>Honey,Pure sidr honey,120.00,Honey,true</Text>
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
            <Text style={styles.scannerModalTitle}>Scan Product Barcode</Text>
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

const styles = StyleSheet.create({
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
  headerTitle: { fontSize: 20, fontWeight: '600', color: Colors.textPrimary },
  scroll: { padding: Spacing.xl, paddingBottom: Spacing.xxxl },
  section: { width: '100%' },
  label: {
    ...Typography.label, color: Colors.textSecondary, marginBottom: Spacing.md,
    fontSize: 14, fontWeight: '700', textTransform: 'uppercase'
  },
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
  matchThumb: { width: 44, height: 44, borderRadius: BorderRadius.sm, marginRight: Spacing.md },
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
    textTransform: 'uppercase', fontSize: 11,
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
  submitBtnText: { ...Typography.button, color: Colors.textOnPrimary },
  buttonDisabled: { opacity: 0.6 },
  fallbackBox: {
    backgroundColor: 'rgba(255, 255, 255, 0.02)', borderRadius: BorderRadius.md,
    borderWidth: 1, borderColor: Colors.border, padding: Spacing.xl,
    alignItems: 'center', marginTop: Spacing.lg,
  },
  fallbackText: { ...Typography.bodySmall, color: Colors.textMuted, marginBottom: Spacing.sm },
  fallbackBtn: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
  fallbackBtnText: { ...Typography.label, color: Colors.primary, fontWeight: '700' },
  newHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.md },
  cancelLink: { ...Typography.bodySmall, color: Colors.error, fontWeight: '600' },
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

  // Categories Selector Horizontal Row
  horizontalScroll: { paddingVertical: Spacing.xs },
  categoryPill: {
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm, borderRadius: BorderRadius.full,
    backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border, marginRight: Spacing.sm,
  },
  categoryPillActive: { backgroundColor: Colors.primary, borderColor: Colors.primaryLight },
  categoryPillText: { ...Typography.bodySmall, color: Colors.textSecondary },
  categoryPillTextActive: { color: Colors.textOnPrimary, fontWeight: '700' },

  // Secondary Photo Upload Styling
  secondaryScroll: { paddingVertical: Spacing.xs, flexDirection: 'row', gap: Spacing.md },
  secThumbContainer: { position: 'relative', width: 80, height: 80, marginRight: Spacing.sm },
  secThumb: { width: 80, height: 80, borderRadius: BorderRadius.md, borderWidth: 1, borderColor: Colors.border },
  removeSecBtn: { position: 'absolute', top: -4, right: -4, zIndex: 5 },
  addSecBtn: {
    width: 80, height: 80, borderRadius: BorderRadius.md, borderWidth: 1, borderStyle: 'dashed',
    borderColor: Colors.primary, justifyContent: 'center', alignItems: 'center', gap: 4,
    backgroundColor: Colors.surface,
  },
  addSecText: { ...Typography.caption, color: Colors.primary, fontSize: 10, fontWeight: '600' },

  // Segmented Tab Selector Styling
  tabScroll: {
    marginBottom: Spacing.lg,
    maxHeight: 52,
  },
  tabScrollContainer: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: 4,
    borderWidth: 1,
    borderColor: Colors.border,
    alignItems: 'center',
    gap: Spacing.xs,
  },
  tabButton: {
    paddingHorizontal: Spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.xs,
    paddingVertical: 10,
    borderRadius: BorderRadius.sm,
    height: 42,
  },
  tabButtonActive: {
    backgroundColor: Colors.surfaceElevated,
    ...Shadows.small,
  },
  tabText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
    fontWeight: '600',
  },
  tabTextActive: {
    color: Colors.secondary,
    fontWeight: '700',
  },
  
  // Scanner styles
  barcodeInputRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    alignItems: 'center',
  },
  inlineScanBtn: {
    width: 52,
    height: 52,
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scannerModalContainer: {
    flex: 1,
    backgroundColor: '#000',
  },
  scannerModalHeader: {
    position: 'absolute',
    top: Platform.OS === 'ios' ? 60 : 40,
    left: 0,
    right: 0,
    zIndex: 10,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  scannerCloseBtn: {
    padding: 8,
    backgroundColor: 'rgba(0,0,0,0.5)',
    borderRadius: 20,
  },
  scannerModalTitle: {
    color: '#FFF',
    fontSize: 18,
    fontWeight: 'bold',
    marginLeft: 16,
  },
  scannerOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scannerTargetBox: {
    width: 280,
    height: 180,
    borderWidth: 2,
    borderColor: Colors.secondary,
    backgroundColor: 'transparent',
    borderRadius: BorderRadius.md,
  },
  
  // CSV Upload Styles
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
  helpTitle: { ...Typography.label, color: Colors.textSecondary, marginBottom: Spacing.md },
  codeBlock: {
    backgroundColor: Colors.background, borderRadius: BorderRadius.sm, padding: Spacing.md,
  },
  code: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 11, color: Colors.textMuted, lineHeight: 18 },
});
