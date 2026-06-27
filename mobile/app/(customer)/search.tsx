/**
 * Search Screen — Explore (Eagle Vision) Redesigned.
 *
 * Features:
 *  - Header: Hamburger menu, 'Lamba' wordmark, Avatar
 *  - Search Bar: Full width, pill shaped, integrated camera/image icons. Filter outside.
 *  - Content Feed: Suggestions, Nearby Markets, Hot Deals, Recently Viewed.
 *  - Search Results: Full screen results when search is active.
 *  - Location Denied: Empty state.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  FlatList, ActivityIndicator, Keyboard, ScrollView, Platform, Alert, Image, KeyboardAvoidingView, Modal
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import * as Linking from 'expo-linking';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import {
  textSearch, imageSearch, getCategories, getUser,
  SearchResultItem, SearchFilters, getSearchHistory, addSearchHistory, clearSearchHistory, SearchHistoryEntry
} from '../../services/api';
import ProductCard from '../../components/ProductCard';
import { Colors, Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { t } from '../../services/i18n';

export default function SearchScreen() {
  const router = useRouter();

  // ── Search State ──────────────────────────────────────────
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchType, setSearchType] = useState<'text' | 'image'>('text');
  const [totalResults, setTotalResults] = useState(0);
  const [searchMode, setSearchMode] = useState<string>('exact_matches');
  const [userId, setUserId] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeImageUri, setActiveImageUri] = useState<string | null>(null);

  const [hasSearched, setHasSearched] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [historyList, setHistoryList] = useState<SearchHistoryEntry[]>([]);

  // Faceted Filters State
  const [showFilters, setShowFilters] = useState(false);
  const [filterDistance, setFilterDistance] = useState<number>(5);
  const [filterCity, setFilterCity] = useState<string>('');
  const [filterNature, setFilterNature] = useState<string>('');
  const [filterCategory, setFilterCategory] = useState<string>('');
  const [filterInStock, setFilterInStock] = useState<boolean>(true);
  const [filterPriceMin, setFilterPriceMin] = useState<string>('');
  const [filterPriceMax, setFilterPriceMax] = useState<string>('');

  const [categoriesList, setCategoriesList] = useState<any[]>([]);
  const [locationStatus, setLocationStatus] = useState<'loading' | 'granted' | 'denied'>('loading');
  const [userLocation, setUserLocation] = useState<{ latitude: number; longitude: number } | null>(null);

  const searchInputRef = useRef<TextInput>(null);

  const initPermissionsAndData = async () => {
    try {
      setLocationStatus('loading');
      setError(null);
      
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status === 'granted') {
        const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        const coords = { latitude: loc.coords.latitude, longitude: loc.coords.longitude };
        setUserLocation(coords);
        setLocationStatus('granted');
        
        try {
          const address = await Location.reverseGeocodeAsync(coords);
          if (address && address[0]) {
            const detectedCity = address[0].city || address[0].region || address[0].subregion || '';
            console.log('Detected user city:', detectedCity);
          }
        } catch (geoErr) {
          console.log('Reverse geocoding failed:', geoErr);
        }
      } else {
        setLocationStatus('denied');
      }

      const currentUser = await getUser();
      if (currentUser) {
        setUserId(currentUser.id);
        setUserEmail(currentUser.email);
        loadHistory(currentUser.id);
      }

      const cats = await getCategories();
      setCategoriesList(cats);
    } catch (err) {
      console.error('Failed to initialize search tools:', err);
      setError('Could not connect to service host. Check network connectivity.');
      setLocationStatus('denied'); // fallback
    }
  };

  useEffect(() => {
    initPermissionsAndData();
  }, []);

  const loadHistory = async (uid: string) => {
    try {
      const data = await getSearchHistory(uid);
      setHistoryList(data);
    } catch (err) {
      console.log('Failed to fetch search history:', err);
    }
  };

  const handleSaveSearch = async (queryText: string, count: number) => {
    if (!userId) return;
    try {
      await addSearchHistory(userId, queryText, searchType, count);
      loadHistory(userId);
    } catch (err) {
      console.log('Failed to save search history:', err);
    }
  };

  const executeSearch = async (searchQuery: string, type: 'text' | 'image' = 'text', imageUri?: string) => {
    if (!userLocation) return;
    Keyboard.dismiss();
    setLoading(true);
    setError(null);
    setSearchType(type);
    
    if (type === 'image' && imageUri) {
      setActiveImageUri(imageUri);
      setQuery('');
    } else {
      setActiveImageUri(null);
      setQuery(searchQuery);
    }

    try {
      const minP = filterPriceMin ? parseFloat(filterPriceMin) : undefined;
      const maxP = filterPriceMax ? parseFloat(filterPriceMax) : undefined;
      
      const parsedFilters: SearchFilters = {
        max_distance_km: filterDistance,
        business_nature: filterNature || undefined,
        category_id: filterCategory || undefined,
        in_stock_only: filterInStock,
        price_min: minP,
        price_max: maxP,
        city: filterCity || undefined,
      };

      let response;
      if (type === 'image' && imageUri) {
        response = await imageSearch(imageUri, userLocation.latitude, userLocation.longitude, parsedFilters);
      } else {
        response = await textSearch(searchQuery.trim(), userLocation.latitude, userLocation.longitude, userId || undefined, parsedFilters);
      }

      setResults(response.results);
      setTotalResults(response.total_results);
      setSearchMode(response.search_mode || 'exact_matches');
      setHasSearched(true);

      if (userId) {
        await handleSaveSearch(type === 'image' ? '[Photo Query]' : searchQuery.trim(), response.total_results);
      }
    } catch (err) {
      console.error('Search failed:', err);
      setError('An error occurred while compiling search results.');
    } finally {
      setLoading(false);
    }
  };

  const handleImageSearch = useCallback(async (useCamera: boolean) => {
    if (!userLocation) return;
    setError(null);

    let result;
    if (useCamera) {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Camera access is required.');
        return;
      }
      result = await ImagePicker.launchCameraAsync({ quality: 0.8, allowsEditing: true, aspect: [1, 1] });
    } else {
      result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.8, allowsEditing: true, aspect: [1, 1] });
    }

    if (result.canceled || !result.assets[0]) return;
    executeSearch('', 'image', result.assets[0].uri);
  }, [userLocation, filterDistance, filterNature, filterCategory, filterInStock, filterPriceMin, filterPriceMax, filterCity, userId]);

  const handleOpenSettings = () => {
    if (Platform.OS === 'ios') Linking.openURL('app-settings:');
    else Linking.openSettings();
  };

  // ── Rendering components ──────────────────────────────
  const renderHeader = () => (
    <View style={styles.header}>
      <View style={styles.iconButton} />
      <Text style={styles.headerTitle}>Lamba</Text>
      <TouchableOpacity style={styles.avatarButton} onPress={() => router.push('/(customer)/profile')}>
        <LinearGradient
          colors={[Colors.primary, '#8B83FF']}
          style={styles.avatarGradient}
        >
          <Text style={styles.avatarText}>{userEmail ? userEmail.charAt(0).toUpperCase() : 'L'}</Text>
        </LinearGradient>
      </TouchableOpacity>
    </View>
  );

  const renderSearchBar = () => (
    <View style={styles.searchContainer}>
      <View style={styles.searchBar}>
        {activeImageUri ? (
          <View style={styles.queryImageContainer}>
            <Image source={{ uri: activeImageUri }} style={styles.queryImage} />
            <TouchableOpacity
              style={styles.queryImageCloseBtn}
              onPress={() => {
                setActiveImageUri(null);
                setResults([]);
                setSearchType('text');
                setSearchMode('exact_matches');
                setHasSearched(false);
                setError(null);
              }}
            >
              <Ionicons name="close-circle" size={16} color={Colors.error} />
            </TouchableOpacity>
          </View>
        ) : (
          <Ionicons name="search" size={20} color={Colors.textMuted} style={styles.searchIcon} />
        )}
        <TextInput
          ref={searchInputRef}
          style={styles.searchInput}
          placeholder={activeImageUri ? t('search.visual_search_filtering') : t('search.search_nearby')}
          placeholderTextColor={Colors.textMuted}
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={() => { if (query.trim()) executeSearch(query); setSearchFocused(false); }}
          returnKeyType="search"
          editable={!activeImageUri}
          onFocus={() => setSearchFocused(true)}
          onBlur={() => {
            setTimeout(() => setSearchFocused(false), 200);
          }}
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => { setQuery(''); setResults([]); setHasSearched(false); }} style={styles.clearIcon}>
            <Ionicons name="close-circle" size={20} color={Colors.textMuted} />
          </TouchableOpacity>
        )}
        <View style={styles.searchDivider} />
        <TouchableOpacity onPress={() => handleImageSearch(true)} style={styles.cameraIcon}>
          <Ionicons name="camera" size={20} color={Colors.secondary} />
        </TouchableOpacity>
        <TouchableOpacity onPress={() => handleImageSearch(false)} style={styles.imageIcon}>
          <Ionicons name="image" size={20} color={Colors.secondary} />
        </TouchableOpacity>
      </View>
      <TouchableOpacity style={styles.filterButton} onPress={() => setShowFilters(true)}>
        <Ionicons name="options-outline" size={22} color={showFilters ? Colors.primary : Colors.textPrimary} />
      </TouchableOpacity>
      
      {/* History Dropdown Overlay */}
      {searchFocused && !query && (
        <View style={styles.historyDropdown}>
          <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 250 }}>
            {historyList.length > 0 ? (
              historyList.slice(0, 4).map(item => (
                <TouchableOpacity
                  key={item.id}
                  style={styles.historyDropdownItem}
                  onPress={() => {
                    setSearchFocused(false);
                    Keyboard.dismiss();
                    setQuery(item.query_text);
                    executeSearch(item.query_text);
                  }}
                >
                  <Ionicons name="time-outline" size={20} color={Colors.textSecondary} style={{ marginRight: Spacing.sm }} />
                  <Text style={styles.historyDropdownText}>{item.query_text}</Text>
                </TouchableOpacity>
              ))
            ) : (
              <View style={styles.historyDropdownEmpty}>
                <Ionicons name="search-outline" size={24} color={Colors.textMuted} style={{ marginBottom: 8 }} />
                <Text style={styles.historyDropdownEmptyText}>No recent searches</Text>
              </View>
            )}
          </ScrollView>
        </View>
      )}
    </View>
  );

  const renderExploreFeed = () => (
    <ScrollView contentContainerStyle={styles.feedContent} showsVerticalScrollIndicator={false}>
      {/* Suggestions Row */}
      <View style={styles.suggestionsRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.suggestionsScroll}>
          {['Coffee', 'Bread', 'Water', 'Charger', 'Panadol'].map((sug) => (
            <TouchableOpacity key={sug} style={styles.suggestionChip} onPress={() => executeSearch(sug)}>
              <Text style={styles.suggestionChipText}>{sug}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Nearby Markets */}
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>{t('explore.nearby_markets')}</Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalScroll}>
          {[1, 2, 3].map((_, i) => (
            <TouchableOpacity key={i} style={styles.marketCard} activeOpacity={0.8} onPress={() => router.push('/(customer)/map')}>
              <View style={styles.marketImagePlaceholder}>
                <Ionicons name="storefront-outline" size={32} color={Colors.primary} />
              </View>
              <Text style={styles.marketName} numberOfLines={1}>Supermarket {i+1}</Text>
              <Text style={styles.marketDistance}>1.{i} km</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Hot Deals Near You */}
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>{t('explore.hot_deals')}</Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalScroll}>
          {[1, 2, 3].map((_, i) => (
            <TouchableOpacity key={i} style={styles.dealCard} activeOpacity={0.8} onPress={() => router.push('/(customer)/offers')}>
              <View style={styles.dealImagePlaceholder}>
                <View style={styles.dealBadge}>
                  <Text style={styles.dealBadgeText}>-20%</Text>
                </View>
                <Ionicons name="pricetag-outline" size={32} color={Colors.secondary} />
              </View>
              <Text style={styles.dealName} numberOfLines={1}>Special Offer {i+1}</Text>
              <Text style={styles.dealPrice}>12.00 SAR</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Recently Viewed */}
      {historyList.length > 0 && (
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>{t('explore.recently_viewed')}</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalScroll}>
            {historyList.slice(0, 3).map((item, i) => (
              <TouchableOpacity key={item.id} style={styles.recentCard} activeOpacity={0.8} onPress={() => executeSearch(item.query_text)}>
                <View style={styles.recentIconWrapper}>
                  <Ionicons name="time-outline" size={24} color={Colors.textSecondary} />
                </View>
                <Text style={styles.recentText} numberOfLines={1}>{item.query_text}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}
    </ScrollView>
  );

  // ── Main Render ──────────────────────────────────────────
  if (locationStatus === 'denied') {
    return (
      <View style={styles.deniedContainer}>
        <View style={styles.deniedIconWrapper}>
          <Ionicons name="lock-closed" size={32} color={Colors.error} style={styles.deniedLock} />
          <Ionicons name="location" size={80} color={Colors.error} />
        </View>
        <Text style={styles.deniedTitle}>{t('explore.enable_location')}</Text>
        <Text style={styles.deniedText}>
          {t('explore.enable_location_desc')}
        </Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={handleOpenSettings}>
          <Text style={styles.primaryBtnText}>{t('explore.enable_location_btn')}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.secondaryBtn} onPress={() => setLocationStatus('granted')}>
          <Text style={styles.secondaryBtnText}>{t('explore.browse_without')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        {renderHeader()}
        <View style={styles.searchWrapper}>
          {renderSearchBar()}
        </View>

        {loading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={Colors.primary} />
            <Text style={styles.loadingText}>{t('search.scouting', 'Scouting catalog & physical branches...')}</Text>
          </View>
        ) : hasSearched ? (
          <View style={styles.resultsContainer}>
            {searchMode === 'recommendations' && results.length > 0 && (
              <View style={styles.recommendationBanner}>
                <Ionicons name="sparkles" size={18} color={Colors.primary} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.recommendationBannerTitle}>Recommendations</Text>
                  <Text style={styles.recommendationBannerText}>No exact matches nearby. Showing products related to your request.</Text>
                </View>
              </View>
            )}
            <FlatList
              data={results}
              keyExtractor={(item) => item.product_id}
              renderItem={({ item }) => <ProductCard item={item} />}
              contentContainerStyle={styles.listContent}
              ListEmptyComponent={
                <View style={styles.emptyResultsContainer}>
                  <Ionicons name="search-outline" size={48} color={Colors.textMuted} />
                  <Text style={styles.emptyResultsTitle}>No Results Found</Text>
                  <Text style={styles.emptyResultsText}>Try tweaking your filters or trying a different term nearby.</Text>
                </View>
              }
            />
          </View>
        ) : (
          renderExploreFeed()
        )}
      </SafeAreaView>

      {/* Faceted Filters Sliding Modal */}
      <Modal
        visible={showFilters}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowFilters(false)}
      >
        <View style={styles.modalOverlay}>
          <TouchableOpacity style={styles.modalBackdrop} activeOpacity={1} onPress={() => setShowFilters(false)} />
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('search.filters', 'Filters')}</Text>
              <TouchableOpacity onPress={() => setShowFilters(false)} style={styles.modalCloseBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalBody}>
              
              <Text style={styles.filterLabel}>{t('search.max_distance', 'Max Distance (km)')}: {filterDistance}</Text>
              <View style={styles.filterRow}>
                {[5, 10, 20, 50].map(dist => (
                  <TouchableOpacity 
                    key={dist} 
                    style={[styles.filterChip, filterDistance === dist && styles.filterChipActive]}
                    onPress={() => setFilterDistance(dist)}
                  >
                    <Text style={[styles.filterChipText, filterDistance === dist && styles.filterChipTextActive]}>{dist} km</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.filterLabel}>{t('search.availability', 'Availability')}</Text>
              <TouchableOpacity 
                style={styles.checkboxRow} 
                onPress={() => setFilterInStock(!filterInStock)}
              >
                <Ionicons name={filterInStock ? "checkbox" : "square-outline"} size={24} color={filterInStock ? Colors.primary : Colors.textMuted} />
                <Text style={styles.checkboxText}>{t('search.in_stock_only', 'In Stock Only')}</Text>
              </TouchableOpacity>

              <Text style={styles.filterLabel}>{t('search.price_range', 'Price Range')}</Text>
              <View style={styles.priceInputsContainer}>
                <TextInput
                  style={styles.priceInput}
                  placeholder="Min"
                  placeholderTextColor={Colors.textMuted}
                  keyboardType="numeric"
                  value={filterPriceMin}
                  onChangeText={setFilterPriceMin}
                />
                <Text style={styles.priceSeparator}>-</Text>
                <TextInput
                  style={styles.priceInput}
                  placeholder="Max"
                  placeholderTextColor={Colors.textMuted}
                  keyboardType="numeric"
                  value={filterPriceMax}
                  onChangeText={setFilterPriceMax}
                />
              </View>

              <Text style={styles.filterLabel}>{t('search.city', 'City')}</Text>
              <TextInput
                style={styles.textInput}
                placeholder={t('search.city_placeholder', 'e.g. Dubai')}
                placeholderTextColor={Colors.textMuted}
                value={filterCity}
                onChangeText={setFilterCity}
              />

              <Text style={styles.filterLabel}>{t('search.business_nature', 'Business Nature')}</Text>
              <TextInput
                style={styles.textInput}
                placeholder={t('search.business_nature_placeholder', 'e.g. Grocery')}
                placeholderTextColor={Colors.textMuted}
                value={filterNature}
                onChangeText={setFilterNature}
              />
              
            </ScrollView>
            <View style={styles.modalFooter}>
              <TouchableOpacity 
                style={styles.resetButton} 
                onPress={() => {
                  setFilterDistance(5);
                  setFilterInStock(true);
                  setFilterPriceMin('');
                  setFilterPriceMax('');
                  setFilterCity('');
                  setFilterNature('');
                  setFilterCategory('');
                }}
              >
                <Text style={styles.resetButtonText}>{t('search.reset', 'Reset')}</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                style={styles.applyButton} 
                onPress={() => {
                  setShowFilters(false);
                  if (hasSearched) {
                    if (searchType === 'text') {
                      executeSearch(query);
                    } else if (activeImageUri) {
                      executeSearch('', 'image', activeImageUri);
                    }
                  }
                }}
              >
                <Text style={styles.applyButtonText}>{t('search.apply', 'Apply Filters')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  safeArea: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
  },
  iconButton: {
    width: 40, height: 40, justifyContent: 'center', alignItems: 'flex-start'
  },
  headerTitle: {
    ...Typography.h3,
    color: Colors.textPrimary,
  },
  avatarButton: {
    width: 40, height: 40, justifyContent: 'center', alignItems: 'flex-end'
  },
  avatarGradient: {
    width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center'
  },
  avatarText: {
    fontSize: 14, fontWeight: '700', color: Colors.textOnPrimary
  },
  searchWrapper: {
    paddingHorizontal: Spacing.lg,
    paddingBottom: Spacing.md,
    zIndex: 100,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    zIndex: 1000,
    elevation: 10,
  },
  searchBar: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 26,
    paddingHorizontal: Spacing.lg,
  },
  searchIcon: { marginRight: Spacing.xs },
  searchInput: {
    flex: 1,
    color: Colors.textPrimary,
    ...Typography.body,
    height: '100%',
  },
  clearIcon: { padding: Spacing.xs },
  searchDivider: {
    width: 1, height: 24, backgroundColor: Colors.border, marginHorizontal: Spacing.sm
  },
  cameraIcon: { padding: Spacing.xs, marginRight: 2 },
  imageIcon: { padding: Spacing.xs },
  filterButton: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surfaceElevated,
    justifyContent: 'center', alignItems: 'center',
  },
  queryImageContainer: {
    width: 28, height: 28, borderRadius: 14, position: 'relative', marginRight: Spacing.xs,
    borderWidth: 1, borderColor: Colors.primary,
  },
  queryImage: { width: '100%', height: '100%', borderRadius: 13 },
  queryImageCloseBtn: {
    position: 'absolute', top: -6, right: -6, backgroundColor: Colors.surface, borderRadius: 8, zIndex: 1
  },

  feedContent: { paddingBottom: 100 },
  suggestionsRow: { marginBottom: Spacing.xl, marginTop: Spacing.sm },
  suggestionsScroll: { paddingHorizontal: Spacing.lg, gap: Spacing.sm },
  suggestionChip: {
    height: 36, backgroundColor: Colors.surfaceElevated, borderRadius: 18,
    justifyContent: 'center', paddingHorizontal: Spacing.lg, borderWidth: 1, borderColor: Colors.border
  },
  suggestionChipText: { ...Typography.bodySmall, color: Colors.textPrimary },

  section: { marginBottom: Spacing.xxl },
  sectionHeader: { paddingHorizontal: Spacing.lg, marginBottom: Spacing.md },
  sectionTitle: { ...Typography.h2, color: Colors.textPrimary },
  horizontalScroll: { paddingHorizontal: Spacing.lg, gap: Spacing.md },

  marketCard: { width: 160, gap: Spacing.xs },
  marketImagePlaceholder: {
    width: 160, height: 100, backgroundColor: 'rgba(108, 99, 255, 0.1)',
    borderRadius: BorderRadius.md, justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, borderColor: 'rgba(108, 99, 255, 0.2)'
  },
  marketName: { ...Typography.body, fontWeight: '600', color: Colors.textPrimary, marginTop: 4 },
  marketDistance: { ...Typography.caption, color: Colors.textSecondary },

  dealCard: { width: 140, gap: Spacing.xs },
  dealImagePlaceholder: {
    width: 140, height: 140, backgroundColor: 'rgba(0, 200, 150, 0.1)',
    borderRadius: BorderRadius.md, justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, borderColor: 'rgba(0, 200, 150, 0.2)', position: 'relative'
  },
  dealBadge: {
    position: 'absolute', top: Spacing.sm, left: Spacing.sm,
    backgroundColor: Colors.primary, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4
  },
  dealBadgeText: { ...Typography.caption, color: Colors.textOnPrimary, fontWeight: '700' },
  dealName: { ...Typography.bodySmall, color: Colors.textPrimary, marginTop: 4 },
  dealPrice: { ...Typography.bodySmall, color: Colors.secondary, fontWeight: '700' },

  recentCard: {
    width: 120, height: 80, backgroundColor: Colors.surface, borderRadius: BorderRadius.md,
    borderWidth: 1, borderColor: Colors.border, justifyContent: 'center', alignItems: 'center', gap: Spacing.xs
  },
  recentIconWrapper: {
    width: 36, height: 36, borderRadius: 18, backgroundColor: Colors.surfaceElevated,
    justifyContent: 'center', alignItems: 'center'
  },
  recentText: { ...Typography.caption, color: Colors.textSecondary, paddingHorizontal: Spacing.sm, textAlign: 'center' },

  // Results State
  resultsContainer: { flex: 1 },
  listContent: { paddingHorizontal: Spacing.lg, paddingBottom: 110, paddingTop: Spacing.sm },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { ...Typography.bodySmall, color: Colors.textSecondary, marginTop: Spacing.md },
  emptyResultsContainer: { alignItems: 'center', paddingVertical: Spacing.xxxl },
  emptyResultsTitle: { ...Typography.h3, color: Colors.textSecondary, marginTop: Spacing.lg },
  emptyResultsText: { ...Typography.bodySmall, color: Colors.textMuted, marginTop: Spacing.sm },
  recommendationBanner: {
    flexDirection: 'row', gap: Spacing.md, alignItems: 'center',
    backgroundColor: 'rgba(108, 99, 255, 0.12)', borderLeftWidth: 4,
    borderLeftColor: Colors.primary, marginHorizontal: Spacing.xl,
    marginBottom: Spacing.md, padding: Spacing.md, borderRadius: BorderRadius.md,
  },
  recommendationBannerTitle: { ...Typography.label, color: Colors.primary, fontWeight: '700', fontSize: 13 },
  recommendationBannerText: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2, fontSize: 11 },

  // Denied State
  deniedContainer: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center', padding: Spacing.xxl },
  deniedIconWrapper: { position: 'relative', marginBottom: Spacing.xl },
  deniedLock: { position: 'absolute', top: -10, right: -10, zIndex: 1, backgroundColor: Colors.background, borderRadius: 16, overflow: 'hidden' },
  deniedTitle: { ...Typography.h2, color: Colors.textPrimary, textAlign: 'center' },
  deniedText: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.md, marginBottom: Spacing.xxl, lineHeight: 22 },
  primaryBtn: {
    width: '100%', height: 48, backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    justifyContent: 'center', alignItems: 'center', marginBottom: Spacing.md
  },
  primaryBtnText: { ...Typography.button, color: Colors.textOnPrimary },
  secondaryBtn: { paddingVertical: Spacing.sm },
  secondaryBtnText: { ...Typography.body, color: Colors.textSecondary, textDecorationLine: 'underline' },

  // History Dropdown
  historyDropdown: {
    position: 'absolute',
    top: 60,
    left: Spacing.lg,
    right: Spacing.lg,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    ...Shadows.medium,
    zIndex: 1000,
    elevation: 10,
    overflow: 'hidden',
  },
  historyDropdownItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  historyDropdownText: {
    ...Typography.body,
    color: Colors.textPrimary,
  },
  historyDropdownEmpty: {
    padding: Spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  historyDropdownEmptyText: {
    ...Typography.body,
    color: Colors.textMuted,
  },
  
  // Modal Styles
  modalOverlay: { flex: 1, justifyContent: 'flex-end' },
  modalBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.7)' },
  modalContent: { backgroundColor: Colors.surface, borderTopLeftRadius: BorderRadius.xl, borderTopRightRadius: BorderRadius.xl, height: '80%', padding: Spacing.lg },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.lg },
  modalTitle: { ...Typography.h2, color: Colors.textPrimary },
  modalCloseBtn: { padding: Spacing.xs },
  modalBody: { flex: 1 },
  filterLabel: { ...Typography.h3, color: Colors.textPrimary, marginTop: Spacing.xl, marginBottom: Spacing.md },
  filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  filterChip: { paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.background },
  filterChipActive: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  filterChipText: { ...Typography.body, color: Colors.textSecondary },
  filterChipTextActive: { color: Colors.textOnPrimary, fontWeight: '600' },
  checkboxRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingVertical: Spacing.xs },
  checkboxText: { ...Typography.body, color: Colors.textPrimary },
  priceInputsContainer: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  priceInput: { flex: 1, backgroundColor: Colors.background, borderRadius: BorderRadius.md, padding: Spacing.md, color: Colors.textPrimary, ...Typography.body, borderWidth: 1, borderColor: Colors.border },
  priceSeparator: { color: Colors.textMuted, fontSize: 20 },
  textInput: { backgroundColor: Colors.background, borderRadius: BorderRadius.md, padding: Spacing.md, color: Colors.textPrimary, ...Typography.body, borderWidth: 1, borderColor: Colors.border },
  modalFooter: { flexDirection: 'row', gap: Spacing.md, marginTop: Spacing.lg, paddingBottom: Spacing.xl },
  resetButton: { flex: 1, padding: Spacing.md, borderRadius: BorderRadius.md, backgroundColor: Colors.background, borderWidth: 1, borderColor: Colors.border, alignItems: 'center' },
  resetButtonText: { ...Typography.button, color: Colors.textPrimary },
  applyButton: { flex: 2, padding: Spacing.md, borderRadius: BorderRadius.md, backgroundColor: Colors.primary, alignItems: 'center' },
  applyButtonText: { ...Typography.button, color: Colors.textOnPrimary },
});
