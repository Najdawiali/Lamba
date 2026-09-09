/**
 * Search Screen — Explore (Eagle Vision) Redesigned.
 *
 * Features:
 *  - Header: Profile menu button, 'Lamba' wordmark, Avatar
 *  - Search Bar: Full width, pill shaped, integrated camera/image icons. Filter outside.
 *  - Content Feed: Suggestions, Nearby Markets, Hot Deals, Recently Viewed.
 *  - Search Results: Full screen results when search is active.
 *  - Location Denied: Empty state.
 */

import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  FlatList, Animated, Keyboard, ScrollView, Platform, Alert, Image, KeyboardAvoidingView, Modal
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import * as Linking from 'expo-linking';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useLocation } from '../../../hooks/useLocation';
import EnableLocationPrompt from '../../../components/EnableLocationPrompt';
import {
  textSearch, imageSearch, getCategories, getUser,
  getNearMarkets, getCustomerSpecialOffers, getNearbyItems, createSearchAlert,
  SearchResultItem, SearchFilters, getSearchHistory, addSearchHistory, clearSearchHistory, SearchHistoryEntry,
  NearMarketResponse, CustomerSpecialOfferResponse, NearbyItemResponse,
} from '../../../services/api';
import ProductCard from '../../../components/ProductCard';
import { Spacing, BorderRadius, Typography, Shadows } from '../../../constants/theme';
import { useThemeColors } from '../../../context/ThemeContext';
import { t, i18n } from '../../../services/i18n';
import { formatPrice } from '../../../services/currency';
import { CATEGORY_AR_FALLBACK } from '../../../constants/categories';

export default function SearchScreen() {
  const Colors = useThemeColors();
  const router = useRouter();

  // ── Search State ──────────────────────────────────────────
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchType, setSearchType] = useState<'text' | 'image'>('text');
  const [totalResults, setTotalResults] = useState(0);
  const [searchMode, setSearchMode] = useState<string>('exact_matches');
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeImageUri, setActiveImageUri] = useState<string | null>(null);

  const [hasSearched, setHasSearched] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [historyList, setHistoryList] = useState<SearchHistoryEntry[]>([]);

  // Toast & Error State
  const [toastVisible, setToastVisible] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [searchError, setSearchError] = useState(false);

  // Faceted Filters State
  const [showFilters, setShowFilters] = useState(false);
  const [filterListingType, setFilterListingType] = useState<'product' | 'service' | null>(null);
  const [filterDistance, setFilterDistance] = useState<number>(5);
  const [filterCategory, setFilterCategory] = useState<string | null>(null);
  const [filterInStock, setFilterInStock] = useState<boolean>(true);

  const [categoriesList, setCategoriesList] = useState<any[]>([]);

  // Categories filtered by selected listing type
  const filteredCategories = useMemo(() => {
    if (filterListingType === 'service') {
      const serviceCats: any[] = [];
      const traverse = (nodes: any[]) => {
        for (const node of nodes) {
          // Hide the parent "الخدمات" / "Services" category — it's redundant
          if (node.listing_type === 'service' && node.name !== 'Services' && node.name_ar !== 'الخدمات') {
            serviceCats.push(node);
          }
          if (node.subcategories && node.subcategories.length > 0) {
            traverse(node.subcategories);
          }
        }
      };
      traverse(categoriesList);
      return serviceCats;
    }

    if (filterListingType === 'product') {
      return categoriesList.filter((cat) => {
        return (
          (cat.listing_type === 'product' || cat.listing_type === 'both' || !cat.listing_type) &&
          cat.name !== 'Services' &&
          cat.name_ar !== 'الخدمات'
        );
      });
    }

    // "الكل" (All) — show product root categories + service subcategories, keeping parent "Services" / "الخدمات" hidden
    const allCats: any[] = [];
    for (const cat of categoriesList) {
      if (cat.name === 'Services' || cat.name_ar === 'الخدمات') {
        if (cat.subcategories && cat.subcategories.length > 0) {
          allCats.push(...cat.subcategories);
        }
      } else {
        allCats.push(cat);
      }
    }
    return allCats;
  }, [categoriesList, filterListingType]);
  const { location: userLocation, loading: locationLoading, denied: locationDenied, refresh: refreshLocation } = useLocation();

  const searchInputRef = useRef<TextInput>(null);

  // Explore feed: real nearby markets & hot deals
  const [exploreMarkets, setExploreMarkets] = useState<NearMarketResponse[]>([]);
  const [exploreDeals, setExploreDeals] = useState<CustomerSpecialOfferResponse[]>([]);
  const [nearbyProducts, setNearbyProducts] = useState<NearbyItemResponse[]>([]);

  // Load user profile & categories once on mount
  useEffect(() => {
    (async () => {
      try {
        const currentUser = await getUser();
        if (currentUser) {
          setUserId(currentUser.id);
          setUserEmail(currentUser.email);
          loadHistory(currentUser.id);
        }
      } catch (authErr) {
        console.warn('Failed to fetch current user profile:', authErr);
      }

      try {
        const cats = await getCategories();
        setCategoriesList(cats);
      } catch (catsErr) {
        console.warn('Failed to fetch categories:', catsErr);
      }
    })();
  }, []);

  // Fetch explore feed whenever userLocation becomes available
  useEffect(() => {
    if (!userLocation) return;
    let isMounted = true;
    (async () => {
      try {
        const [markets, deals, items] = await Promise.all([
          getNearMarkets(userLocation.latitude, userLocation.longitude, 10).catch(() => [] as NearMarketResponse[]),
          getCustomerSpecialOffers(userLocation.latitude, userLocation.longitude).catch((e) => {
            console.warn('Explore: getCustomerSpecialOffers failed', e);
            return [] as CustomerSpecialOfferResponse[];
          }),
          getNearbyItems(userLocation.latitude, userLocation.longitude, 15, 10).catch((e) => {
            console.warn('Explore: getNearbyItems failed', e);
            return [] as NearbyItemResponse[];
          }),
        ]);
        if (!isMounted) return;
        setExploreMarkets(markets || []);
        setExploreDeals((deals || []).slice(0, 10));
        setNearbyProducts(items || []);
      } catch (exploreErr) {
        console.warn('Explore feed load failed:', exploreErr);
      }
    })();
    return () => { isMounted = false; };
  }, [userLocation]);

  const loadHistory = async (uid: string) => {
    try {
      const data = await getSearchHistory(uid);
      setHistoryList(data);
    } catch (err) {
      console.warn('Failed to fetch search history:', err);
    }
  };

  const handleSaveSearch = async (queryText: string, count: number) => {
    if (!userId) return;
    try {
      await addSearchHistory(userId, queryText, searchType, count);
      loadHistory(userId);
    } catch (err) {
      console.warn('Failed to save search history:', err);
    }
  };

  const executeSearch = async (searchQuery: string, type: 'text' | 'image' = 'text', imageUri?: string) => {
    if (!userLocation) return;
    const coords = userLocation;
    Keyboard.dismiss();
    setLoading(true);
    setError(null);
    setSearchError(false);
    setSearchType(type);
    
    if (type === 'image' && imageUri) {
      setActiveImageUri(imageUri);
      setQuery('');
    } else {
      setActiveImageUri(null);
      setQuery(searchQuery);
    }

    try {
      const parsedFilters: SearchFilters = {
        max_distance_km: filterDistance,
        category_id: filterCategory || undefined,
        in_stock_only: filterInStock,
        listing_type: filterListingType,
      };

      let response;
      if (type === 'image' && imageUri) {
        response = await imageSearch(imageUri, coords.latitude, coords.longitude, parsedFilters);
        setSuggestion(null);
      } else {
        response = await textSearch(searchQuery.trim(), coords.latitude, coords.longitude, userId || undefined, parsedFilters);
        setSuggestion(response.suggestion || null);
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
      setSearchError(true);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleApplySuggestion = async (suggestedText: string) => {
    setSuggestion(null);
    setQuery(suggestedText);
    await executeSearch(suggestedText);
  };

  const handleNotifyMe = async () => {
    if (!userLocation || !query.trim()) return;
    try {
      await createSearchAlert(query.trim(), userLocation.latitude, userLocation.longitude);
      setToastMessage(`✓ سنبلغك فور توفر "${query.trim()}"`);
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 3000);
    } catch (err) {
      console.warn('Failed to create search alert:', err);
      // Show success anyway — backend auto-creates alerts on zero-result searches
      setToastMessage(`✓ سنبلغك فور توفر "${query.trim()}"`);
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 3000);
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
  }, [userLocation, filterDistance, filterListingType, filterCategory, filterInStock, userId]);

  const handleOpenSettings = () => {
    if (Platform.OS === 'ios') Linking.openURL('app-settings:');
    else Linking.openSettings();
  };

  // ── Animated Skeleton Pulse ─────────────────────────────────
  const skeletonOpacity = useRef(new Animated.Value(0.3)).current;
  useEffect(() => {
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(skeletonOpacity, { toValue: 0.7, duration: 800, useNativeDriver: true }),
        Animated.timing(skeletonOpacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ])
    );
    pulse.start();
    return () => pulse.stop();
  }, [skeletonOpacity]);

  const styles = useMemo(() => StyleSheet.create({
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
    
    // Greeting
    greetingContainer: {
      paddingHorizontal: Spacing.lg,
      paddingTop: Spacing.xs,
      paddingBottom: Spacing.md,
    },
    greetingText: {
      ...Typography.body,
      color: Colors.textSecondary,
      fontWeight: '600',
      textAlign: 'right' as const,
    },

    // Quick Categories
    quickCategoriesScroll: {
      paddingHorizontal: Spacing.lg,
      gap: 16,
      paddingBottom: Spacing.xs,
    },
    quickCategoryItem: {
      alignItems: 'center',
      width: 64,
    },
    quickCategoryCircle: {
      width: 56,
      height: 56,
      borderRadius: 28,
      backgroundColor: Colors.surfaceElevated,
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: 6,
      borderWidth: 1,
      borderColor: Colors.primary + '35',
    },
    quickCategoryEmoji: {
      fontSize: 24,
    },
    quickCategoryLabel: {
      ...Typography.caption,
      color: Colors.textPrimary,
      textAlign: 'center' as const,
      fontWeight: '500',
    },

    // Section Divider
    sectionDivider: {
      height: 1,
      backgroundColor: Colors.border,
      marginHorizontal: Spacing.xl,
      marginVertical: Spacing.lg,
      opacity: 0.5,
    },

    suggestionsRow: { marginBottom: Spacing.xl, marginTop: Spacing.sm },
    suggestionsScroll: { paddingHorizontal: Spacing.lg, gap: Spacing.sm },
    suggestionChip: {
      height: 36, backgroundColor: Colors.surfaceElevated, borderRadius: 18,
      justifyContent: 'center', paddingHorizontal: Spacing.lg, borderWidth: 1, borderColor: Colors.border
    },
    suggestionChipText: { ...Typography.bodySmall, color: Colors.textPrimary },

    section: { marginBottom: Spacing.md },
    sectionHeader: { paddingHorizontal: Spacing.lg, marginBottom: Spacing.md },
    sectionTitle: { ...Typography.h3, color: Colors.textPrimary, fontWeight: '700' },
    horizontalScroll: { paddingHorizontal: Spacing.lg, gap: Spacing.md },

    marketCard: { width: 160, gap: Spacing.xs },
    marketCardEnhanced: {
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.lg,
      padding: Spacing.md,
      width: 135,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    marketIconWrapper: {
      width: 48,
      height: 48,
      borderRadius: 24,
      backgroundColor: Colors.primary + '20',
      justifyContent: 'center',
      alignItems: 'center',
      alignSelf: 'center',
      marginBottom: 8,
    },
    marketCardTitle: {
      ...Typography.bodySmall,
      color: Colors.textPrimary,
      fontWeight: '600',
      textAlign: 'center' as const,
    },
    marketStatusRow: {
      flexDirection: 'row',
      justifyContent: 'center',
      alignItems: 'center',
      marginTop: 6,
      gap: 6,
    },
    marketStatusDot: {
      width: 6,
      height: 6,
      borderRadius: 3,
    },
    marketDistanceText: {
      ...Typography.caption,
      color: Colors.textSecondary,
      fontSize: 11,
    },

    // Nearby Products
    productCard: {
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.lg,
      padding: Spacing.md,
      width: 155,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    productImageWrapper: {
      width: '100%',
      height: 85,
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.md,
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: 8,
      overflow: 'hidden',
    },
    productImage: {
      width: '100%',
      height: '100%',
      resizeMode: 'cover' as const,
    },
    productName: {
      ...Typography.bodySmall,
      color: Colors.textPrimary,
      fontWeight: '600',
      textAlign: 'right' as const,
    },
    productPrice: {
      ...Typography.bodySmall,
      color: Colors.accent || Colors.primary,
      fontWeight: '700',
      textAlign: 'right' as const,
      marginTop: 4,
    },
    productStoreName: {
      ...Typography.caption,
      color: Colors.textSecondary,
      textAlign: 'right' as const,
      marginTop: 2,
    },

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

    recentSearchChip: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.full,
      paddingVertical: Spacing.sm,
      paddingHorizontal: Spacing.lg,
      borderWidth: 1,
      borderColor: Colors.border,
      marginRight: Spacing.xs,
    },
    recentSearchText: {
      ...Typography.bodySmall,
      color: Colors.textPrimary,
      fontWeight: '500',
    },

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
    toggleRow: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.xs },
    toggleBtn: {
      flex: 1, paddingVertical: 10, borderRadius: BorderRadius.md,
      backgroundColor: Colors.surfaceElevated, alignItems: 'center',
      borderWidth: 1, borderColor: Colors.border,
    },
    toggleBtnActive: {
      backgroundColor: Colors.primary,
      borderColor: Colors.primary,
    },
    toggleBtnText: {
      color: Colors.textSecondary,
      fontWeight: '600',
      fontSize: 13,
    },
    toggleBtnTextActive: {
      color: Colors.textOnPrimary,
    },
    filterLabel: { ...Typography.h3, color: Colors.textPrimary, marginTop: Spacing.xl, marginBottom: Spacing.md },
    filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
    filterChip: { paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, borderRadius: BorderRadius.full, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.background },
    filterChipActive: { backgroundColor: Colors.primary, borderColor: Colors.primary },
    filterChipText: { ...Typography.body, color: Colors.textSecondary },
    filterChipTextActive: { color: Colors.textOnPrimary, fontWeight: '600' },
    checkboxRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingVertical: Spacing.xs },
    checkboxText: { ...Typography.body, color: Colors.textPrimary },
    textInput: { backgroundColor: Colors.background, borderRadius: BorderRadius.md, padding: Spacing.md, color: Colors.textPrimary, ...Typography.body, borderWidth: 1, borderColor: Colors.border },
    modalFooter: { flexDirection: 'row', gap: Spacing.md, marginTop: Spacing.lg, paddingBottom: Spacing.xl },
    resetButton: { flex: 1, padding: Spacing.md, borderRadius: BorderRadius.md, backgroundColor: Colors.background, borderWidth: 1, borderColor: Colors.border, alignItems: 'center' },
    resetButtonText: { ...Typography.button, color: Colors.textPrimary },
    applyButton: { flex: 2, padding: Spacing.md, borderRadius: BorderRadius.md, backgroundColor: Colors.primary, alignItems: 'center' },
    applyButtonText: { ...Typography.button, color: Colors.textOnPrimary },

    // Spelling Suggestions
    didYouMeanBanner: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: Colors.surfaceElevated,
      paddingHorizontal: Spacing.md,
      paddingVertical: Spacing.sm,
      marginHorizontal: Spacing.lg,
      marginTop: Spacing.sm,
      borderRadius: 12,
      borderWidth: 1,
      borderColor: Colors.border,
      gap: Spacing.xs,
    },
    didYouMeanContent: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      flexWrap: 'wrap',
    },
    didYouMeanText: {
      ...Typography.body,
      color: Colors.textSecondary,
    },
    didYouMeanLink: {
      ...Typography.body,
      fontWeight: '700' as const,
      color: Colors.primary,
      textDecorationLine: 'underline',
    },
    didYouMeanActions: {
      flexDirection: 'row',
      gap: Spacing.xs,
    },
    didYouMeanYesBtn: {
      backgroundColor: Colors.primary,
      paddingHorizontal: Spacing.md,
      paddingVertical: Spacing.xs,
      borderRadius: 16,
    },
    didYouMeanYesText: {
      color: Colors.textOnPrimary,
      ...Typography.body,
      fontWeight: '700' as const,
      fontSize: 12,
    },
    didYouMeanNoBtn: {
      backgroundColor: Colors.surfaceElevated || Colors.background,
      paddingHorizontal: Spacing.md,
      paddingVertical: Spacing.xs,
      borderRadius: 16,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    didYouMeanNoText: {
      color: Colors.textSecondary,
      ...Typography.body,
      fontSize: 12,
    },

    // ── Skeleton Loading ──────────────────────────────────────────
    skeletonContainer: { paddingHorizontal: Spacing.lg, gap: Spacing.md, paddingTop: Spacing.md },
    skeletonCard: {
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.lg,
      padding: Spacing.lg,
      flexDirection: 'row' as const,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    skeletonImage: {
      width: 48, height: 48,
      borderRadius: BorderRadius.sm,
      backgroundColor: Colors.surfaceElevated,
    },
    skeletonContent: { flex: 1, marginRight: Spacing.md, gap: Spacing.sm },
    skeletonLine: {
      borderRadius: 4,
      backgroundColor: Colors.surfaceElevated,
      alignSelf: 'flex-end' as const,
    },

    // ── Arabic Recommendation Banner ──────────────────────────────
    recBannerAr: {
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.md,
      padding: Spacing.lg,
      marginBottom: Spacing.lg,
      marginHorizontal: Spacing.lg,
      borderLeftWidth: 3,
      borderLeftColor: Colors.primary,
    },
    recBannerTitle: {
      ...Typography.body,
      color: Colors.textPrimary,
      fontWeight: '600' as const,
      textAlign: 'right' as const,
      marginBottom: 4,
    },
    recBannerSubtitle: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
      textAlign: 'right' as const,
      marginBottom: 0,
    },
    notifyBtn: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      backgroundColor: `${Colors.primary}20`,
      borderRadius: BorderRadius.sm,
      paddingVertical: 10,
      paddingHorizontal: 14,
      alignSelf: 'flex-end' as const,
      gap: 6,
    },
    notifyBtnText: {
      ...Typography.bodySmall,
      color: Colors.primary,
    },

    // ── Arabic Empty State ────────────────────────────────────────
    emptyStateAr: {
      alignItems: 'center' as const,
      paddingVertical: Spacing.xxxl,
      paddingHorizontal: Spacing.xl,
    },
    emptyStateTitle: {
      ...Typography.subheading,
      color: Colors.textPrimary,
      textAlign: 'center' as const,
      marginBottom: Spacing.sm,
    },
    emptyStateSubtitle: {
      ...Typography.body,
      color: Colors.textSecondary,
      textAlign: 'center' as const,
      marginBottom: Spacing.xl,
    },
    notifyBtnPrimary: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      backgroundColor: Colors.primary,
      borderRadius: BorderRadius.md,
      paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.xl,
      marginBottom: Spacing.xxl,
      gap: Spacing.sm,
    },
    notifyBtnPrimaryText: {
      ...Typography.body,
      color: Colors.textOnPrimary,
      fontWeight: '600' as const,
    },
    popularLabel: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
      marginBottom: Spacing.md,
      alignSelf: 'flex-end' as const,
    },
    popularChipsRow: {
      flexDirection: 'row' as const,
      flexWrap: 'wrap' as const,
      gap: Spacing.sm,
    },
    popularChip: {
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.full,
      paddingVertical: Spacing.sm,
      paddingHorizontal: 14,
    },
    popularChipText: {
      ...Typography.bodySmall,
      color: Colors.textPrimary,
    },

    // ── Error State ───────────────────────────────────────────────
    errorStateContainer: {
      alignItems: 'center' as const,
      paddingVertical: Spacing.xxxl,
    },
    errorTitle: {
      ...Typography.subheading,
      color: Colors.textPrimary,
      marginBottom: Spacing.sm,
    },
    errorSubtitle: {
      ...Typography.body,
      color: Colors.textSecondary,
      marginBottom: Spacing.xl,
    },
    retryBtn: {
      backgroundColor: Colors.primary,
      borderRadius: BorderRadius.md,
      paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.xl,
    },
    retryBtnText: {
      ...Typography.button,
      color: Colors.textOnPrimary,
    },

    // ── Toast ─────────────────────────────────────────────────────
    toast: {
      position: 'absolute' as const,
      bottom: 100,
      left: Spacing.xl,
      right: Spacing.xl,
      backgroundColor: Colors.secondary,
      borderRadius: BorderRadius.md,
      padding: 14,
      alignItems: 'center' as const,
      ...Shadows.medium,
      zIndex: 9999,
      elevation: 20,
    },
    toastText: {
      color: '#0A0A1A',
      fontSize: 14,
      fontWeight: '600' as const,
    },

    // ── RTL Recent Search ─────────────────────────────────────────
    recentHeaderRow: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      marginBottom: Spacing.md,
      paddingHorizontal: Spacing.lg,
    },
    recentHeaderText: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
    },
    recentClearText: {
      ...Typography.caption,
      color: Colors.primary,
    },
    recentItem: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.lg,
      borderBottomWidth: 1,
      borderBottomColor: Colors.border,
    },
    recentItemText: {
      ...Typography.body,
      color: Colors.textPrimary,
      flex: 1,
      marginRight: 10,
      textAlign: 'right' as const,
    },
  }), [Colors]);

  // ── Rendering components ──────────────────────────────────
  const renderHeader = () => (
    <View style={styles.header}>
      <View style={{ width: 40 }} />
      <Text style={styles.headerTitle}>{t('welcome.title', 'Lamba')}</Text>
      <View style={{ width: 40 }} />
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

  const renderExploreFeed = () => {
    const isAr = !i18n.locale || i18n.locale.includes('ar');

    const getGreeting = () => {
      const hour = new Date().getHours();
      if (hour < 12) return t('explore.good_morning', 'صباح الخير');
      if (hour < 17) return t('explore.good_afternoon', 'مساء الخير');
      return t('explore.good_evening', 'مساء النور');
    };

    const QUICK_CATEGORIES = [
      { key: 'tea', label: { en: 'Tea', ar: 'شاي' }, emoji: '🍵' },
      { key: 'milk', label: { en: 'Milk', ar: 'حليب' }, emoji: '🥛' },
      { key: 'bread', label: { en: 'Bread', ar: 'خبز' }, emoji: '🍞' },
      { key: 'honey', label: { en: 'Honey', ar: 'عسل' }, emoji: '🍯' },
      { key: 'coffee', label: { en: 'Coffee', ar: 'قهوة' }, emoji: '☕' },
      { key: 'oil', label: { en: 'Olive Oil', ar: 'زيت زيتون' }, emoji: '🫒' },
      { key: 'rice', label: { en: 'Rice', ar: 'أرز' }, emoji: '🍚' },
      { key: 'sugar', label: { en: 'Sugar', ar: 'سكر' }, emoji: '🧂' },
      { key: 'eggs', label: { en: 'Eggs', ar: 'بيض' }, emoji: '🥚' },
      { key: 'chicken', label: { en: 'Chicken', ar: 'دجاج' }, emoji: '🍗' },
    ];

    const handleCategorySearch = (cat: typeof QUICK_CATEGORIES[0]) => {
      const searchTerm = isAr ? cat.label.ar : cat.label.en;
      setQuery(searchTerm);
      executeSearch(searchTerm);
    };

    return (
      <ScrollView contentContainerStyle={styles.feedContent} showsVerticalScrollIndicator={false}>
        {/* 1. Time-based Greeting */}
        <View style={styles.greetingContainer}>
          <Text style={styles.greetingText}>
            {getGreeting()} 👋 {t('explore.what_looking_for', 'شو عم تدور عليه اليوم؟')}
          </Text>
        </View>

        {/* 2. Popular Item Shortcuts */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>{t('search.popular_items', 'Popular Items')}</Text>
        </View>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.quickCategoriesScroll}
        >
          {QUICK_CATEGORIES.map((cat) => (
            <TouchableOpacity
              key={cat.key}
              onPress={() => handleCategorySearch(cat)}
              style={styles.quickCategoryItem}
              activeOpacity={0.7}
            >
              <View style={styles.quickCategoryCircle}>
                <Text style={styles.quickCategoryEmoji}>{cat.emoji}</Text>
              </View>
              <Text style={styles.quickCategoryLabel} numberOfLines={1}>
                {isAr ? cat.label.ar : cat.label.en}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <View style={styles.sectionDivider} />

        {/* 3. Nearby Markets */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>{t('explore.nearby_markets')}</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalScroll}>
            {exploreMarkets.length === 0 ? (
              <Text style={[styles.marketName, { color: Colors.textMuted, padding: Spacing.md }]}>
                {t('common.no_items', 'No nearby markets found.')}
              </Text>
            ) : (
              exploreMarkets.map((m) => {
                const marketDisplayName = isAr ? (m.name_ar || m.name) : (m.name_en || m.name);
                const dist = typeof m.distance_km === 'number' ? m.distance_km : parseFloat(String(m.distance_km || 0));
                const distanceText = dist < 0.05
                  ? t('common.very_close', 'قريب جداً')
                  : `${dist.toFixed(1)} ${t('common.km', 'كم')}`;

                return (
                  <TouchableOpacity
                    key={m.id}
                    style={[
                      styles.marketCardEnhanced,
                      {
                        borderColor: m.is_currently_open ? (Colors.accent ? Colors.accent + '40' : Colors.primary + '40') : Colors.border,
                      },
                    ]}
                    activeOpacity={0.8}
                    onPress={() => router.push(`/(customer)/shop/${m.id}`)}
                  >
                    <View style={styles.marketIconWrapper}>
                      <Ionicons name="storefront" size={22} color={Colors.primary} />
                    </View>
                    <Text style={styles.marketCardTitle} numberOfLines={1}>
                      {marketDisplayName}
                    </Text>
                    <View style={styles.marketStatusRow}>
                      <View
                        style={[
                          styles.marketStatusDot,
                          { backgroundColor: m.is_currently_open ? Colors.accent || '#10B981' : Colors.error },
                        ]}
                      />
                      <Text style={styles.marketDistanceText}>{distanceText}</Text>
                    </View>
                  </TouchableOpacity>
                );
              })
            )}
          </ScrollView>
        </View>

        {/* 4. Nearby Products */}
        {nearbyProducts && nearbyProducts.length > 0 && (
          <>
            <View style={styles.sectionDivider} />
            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>{t('explore.nearby_products', 'منتجات قريبة')}</Text>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalScroll}>
                {nearbyProducts.map((product) => {
                  const prodName = isAr ? (product.name_ar || product.name) : (product.name_en || product.name);
                  const storeName = isAr ? (product.market_name_ar || product.market_name) : (product.market_name_en || product.market_name);

                  return (
                    <TouchableOpacity
                      key={product.id || product.market_item_id}
                      style={styles.productCard}
                      activeOpacity={0.8}
                      onPress={() => router.push(`/(customer)/product/${product.market_item_id}`)}
                    >
                      <View style={styles.productImageWrapper}>
                        {product.image_url ? (
                          <Image source={{ uri: product.image_url }} style={styles.productImage} />
                        ) : (
                          <Ionicons name="cube-outline" size={28} color={Colors.primary} />
                        )}
                      </View>
                      <Text style={styles.productName} numberOfLines={1}>
                        {prodName}
                      </Text>
                      <Text style={styles.productPrice}>
                        {formatPrice(product.price)}
                      </Text>
                      <Text style={styles.productStoreName} numberOfLines={1}>
                        {storeName}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>
            </View>
          </>
        )}

        {/* 5. Hot Deals (if available) */}
        {exploreDeals && exploreDeals.length > 0 && (
          <>
            <View style={styles.sectionDivider} />
            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>{t('explore.hot_deals')}</Text>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalScroll}>
                {exploreDeals.map((deal) => {
                  const discount = deal.discount_percentage ?? 0;
                  const dealDisplayName = isAr ? (deal.product_name_ar || deal.product_name) : (deal.product_name_en || deal.product_name);
                  return (
                    <TouchableOpacity
                      key={deal.id}
                      style={styles.dealCard}
                      activeOpacity={0.8}
                      onPress={() => router.push(`/(customer)/product/${deal.market_item_id}`)}
                    >
                      <View style={styles.dealImagePlaceholder}>
                        <View style={styles.dealBadge}>
                          <Text style={styles.dealBadgeText}>-{discount}%</Text>
                        </View>
                        <Ionicons name="pricetag-outline" size={32} color={Colors.secondary} />
                      </View>
                      <Text style={styles.dealName} numberOfLines={1}>{dealDisplayName}</Text>
                      <Text style={styles.dealPrice}>{formatPrice(deal.price)}</Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>
            </View>
          </>
        )}

        {/* 6. Recent Searches */}
        {historyList && historyList.length > 0 && (
          <>
            <View style={styles.sectionDivider} />
            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>{t('search.recent', 'بحث سابق')}</Text>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalScroll}>
                {historyList.slice(0, 10).map((item) => (
                  <TouchableOpacity
                    key={item.id}
                    style={styles.recentSearchChip}
                    activeOpacity={0.8}
                    onPress={() => {
                      setQuery(item.query_text);
                      executeSearch(item.query_text);
                    }}
                  >
                    <Ionicons name="time-outline" size={14} color={Colors.textSecondary} style={{ marginRight: 6 }} />
                    <Text style={styles.recentSearchText}>{item.query_text}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          </>
        )}
      </ScrollView>
    );
  };

  // ── Main Render ──────────────────────────────────────────
  if (locationDenied) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: Colors.background }}>
        <EnableLocationPrompt onRetry={refreshLocation} />
      </SafeAreaView>
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
          /* ── Skeleton Loading State ─────────────────────────────── */
          <View style={styles.skeletonContainer}>
            {[1, 2, 3, 4].map(i => (
              <Animated.View key={i} style={[styles.skeletonCard, { opacity: skeletonOpacity }]}>
                <View style={styles.skeletonImage} />
                <View style={styles.skeletonContent}>
                  <View style={[styles.skeletonLine, { height: 14, width: '70%' }]} />
                  <View style={[styles.skeletonLine, { height: 12, width: '50%' }]} />
                  <View style={[styles.skeletonLine, { height: 12, width: '30%' }]} />
                </View>
              </Animated.View>
            ))}
          </View>
        ) : searchError && !loading ? (
          /* ── Error State ─────────────────────────────────────────── */
          <View style={styles.errorStateContainer}>
            <Ionicons name="wifi-outline" size={48} color={Colors.error} style={{ marginBottom: Spacing.lg, opacity: 0.6 }} />
            <Text style={styles.errorTitle}>{t('search.error_title', 'حدث خطأ في البحث')}</Text>
            <Text style={styles.errorSubtitle}>{t('search.error_subtitle', 'تحقق من اتصالك بالإنترنت')}</Text>
            <TouchableOpacity
              onPress={() => { setSearchError(false); if (query.trim()) executeSearch(query); }}
              style={styles.retryBtn}
            >
              <Text style={styles.retryBtnText}>{t('common.retry', 'إعادة المحاولة')}</Text>
            </TouchableOpacity>
          </View>
        ) : hasSearched ? (
          <View style={styles.resultsContainer}>
            {/* ── Spelling Suggestion Banner ──────────────────────── */}
            {suggestion && (
              <View style={styles.didYouMeanBanner}>
                <Ionicons name="help-circle-outline" size={20} color={Colors.primary} />
                <View style={styles.didYouMeanContent}>
                  <Text style={styles.didYouMeanText}>{t('search.did_you_mean', 'Did you mean: ')}</Text>
                  <TouchableOpacity onPress={() => handleApplySuggestion(suggestion)}>
                    <Text style={styles.didYouMeanLink}>"{suggestion}"</Text>
                  </TouchableOpacity>
                  <Text style={styles.didYouMeanText}>?</Text>
                </View>
                <View style={styles.didYouMeanActions}>
                  <TouchableOpacity style={styles.didYouMeanYesBtn} onPress={() => handleApplySuggestion(suggestion)}>
                    <Text style={styles.didYouMeanYesText}>{t('common.yes', 'Yes')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.didYouMeanNoBtn} onPress={() => setSuggestion(null)}>
                    <Text style={styles.didYouMeanNoText}>{t('common.no', 'No')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}

            {/* ── Arabic Recommendation Banner ────────────────────── */}
            {searchMode === 'recommendations' && results.length > 0 && (
              <View style={styles.recBannerAr}>
                <Text style={styles.recBannerTitle}>
                  {t('search.recommendations_title', { query })}
                </Text>
                <Text style={styles.recBannerSubtitle}>
                  {t('search.recommendations_subtitle', 'لكن قد يعجبك:')}
                </Text>
              </View>
            )}

            {/* ── Results List ────────────────────────────────────── */}
            <FlatList
              data={results}
              keyExtractor={(item) => item.product_id}
              renderItem={({ item }) => <ProductCard item={item} />}
              contentContainerStyle={styles.listContent}
              ListEmptyComponent={
                /* ── Arabic Empty State ──────────────────────────── */
                <View style={styles.emptyStateAr}>
                  <Ionicons name="search-outline" size={64} color={Colors.textSecondary} style={{ marginBottom: Spacing.lg, opacity: 0.5 }} />
                  <Text style={styles.emptyStateTitle}>
                    {t('search.no_match_title', { query })}
                  </Text>
                  <Text style={styles.emptyStateSubtitle}>
                    {t('search.no_match_subtitle', 'جرب البحث بكلمات مختلفة أو تصفح الأقسام')}
                  </Text>

                  {/* Notify Me Button */}
                  <TouchableOpacity onPress={handleNotifyMe} style={styles.notifyBtnPrimary}>
                    <Ionicons name="notifications-outline" size={20} color={Colors.textOnPrimary} />
                    <Text style={styles.notifyBtnPrimaryText}>
                      {t('search.notify_me', 'أبلغني عند توفره')}
                    </Text>
                  </TouchableOpacity>

                  {/* Popular Searches */}
                  <Text style={styles.popularLabel}>{t('search.popular', 'بحث شائع')}</Text>
                  <View style={styles.popularChipsRow}>
                    {['حليب', 'خبز', 'زيت زيتون', 'قهوة', 'شاي', 'عسل', 'أرز', 'سكر'].map(term => (
                      <TouchableOpacity
                        key={term}
                        onPress={() => { setQuery(term); executeSearch(term); }}
                        style={styles.popularChip}
                      >
                        <Text style={styles.popularChipText}>{term}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              }
            />
          </View>
        ) : searchFocused && !query && historyList.length > 0 ? (
          /* ── RTL Recent Searches (input focused, empty query) ──── */
          <View style={{ flex: 1 }}>
            <View style={styles.recentHeaderRow}>
              <Text style={styles.recentHeaderText}>{t('search.recent', 'بحث سابق')}</Text>
              <TouchableOpacity onPress={async () => {
                if (!userId) return;
                try {
                  await clearSearchHistory(userId);
                  setHistoryList([]);
                } catch (err) { console.warn('Failed to clear history:', err); }
              }}>
                <Text style={styles.recentClearText}>{t('search.clear_all', 'مسح الكل')}</Text>
              </TouchableOpacity>
            </View>
            {historyList.slice(0, 8).map(item => (
              <TouchableOpacity
                key={item.id}
                onPress={() => {
                  setSearchFocused(false);
                  Keyboard.dismiss();
                  setQuery(item.query_text);
                  executeSearch(item.query_text);
                }}
                style={styles.recentItem}
              >
                <Ionicons name="time-outline" size={18} color={Colors.textSecondary} />
                <Text style={styles.recentItemText}>{item.query_text}</Text>
              </TouchableOpacity>
            ))}
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
              <Text style={styles.modalTitle}>{t('filter.title', 'فلاتر البحث')}</Text>
              <TouchableOpacity onPress={() => setShowFilters(false)} style={styles.modalCloseBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalBody} showsVerticalScrollIndicator={false}>
              
              {/* Fix 3: Listing Type Toggle (Product / Service / All) */}
              <Text style={styles.filterLabel}>{t('filter.listing_type', 'النوع')}</Text>
              <View style={styles.toggleRow}>
                {[
                  { value: null, label: t('filter.all', 'الكل') },
                  { value: 'product', label: t('filter.products', 'منتجات') },
                  { value: 'service', label: t('filter.services', 'خدمات') },
                ].map(opt => (
                  <TouchableOpacity
                    key={opt.label}
                    onPress={() => {
                      setFilterListingType(opt.value as any);
                      if (filterCategory) {
                        const stillValid = categoriesList.some(c => c.id === filterCategory && (!opt.value || !c.listing_type || c.listing_type === opt.value));
                        if (!stillValid) setFilterCategory(null);
                      }
                    }}
                    style={[
                      styles.toggleBtn,
                      filterListingType === opt.value && styles.toggleBtnActive,
                    ]}
                  >
                    <Text style={[
                      styles.toggleBtnText,
                      filterListingType === opt.value && styles.toggleBtnTextActive,
                    ]}>
                      {opt.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Distance */}
              <Text style={styles.filterLabel}>{t('filter.distance', 'أقصى مسافة (كم)')}: {filterDistance} {t('common.km', 'كم')}</Text>
              <View style={styles.filterRow}>
                {[5, 10, 20, 50].map(dist => (
                  <TouchableOpacity 
                    key={dist} 
                    style={[styles.filterChip, filterDistance === dist && styles.filterChipActive]}
                    onPress={() => setFilterDistance(dist)}
                  >
                    <Text style={[styles.filterChipText, filterDistance === dist && styles.filterChipTextActive]}>{dist} {t('common.km', 'كم')}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Fix 4: Category Chips */}
              <Text style={styles.filterLabel}>{t('filter.category', 'القسم')}</Text>
              <View style={styles.filterRow}>
                <TouchableOpacity
                  onPress={() => setFilterCategory(null)}
                  style={[styles.filterChip, filterCategory === null && styles.filterChipActive]}
                >
                  <Text style={[styles.filterChipText, filterCategory === null && styles.filterChipTextActive]}>
                    {t('filter.all', 'الكل')}
                  </Text>
                </TouchableOpacity>
                {filteredCategories.map(cat => {
                  const isAr = !i18n.locale || i18n.locale.includes('ar');
                  const displayName = isAr ? (cat.name_ar || CATEGORY_AR_FALLBACK[cat.name]) : (cat.name_en || cat.name);
                  if (isAr && !displayName) return null;
                  return (
                    <TouchableOpacity
                      key={cat.id}
                      onPress={() => setFilterCategory(cat.id === filterCategory ? null : cat.id)}
                      style={[styles.filterChip, filterCategory === cat.id && styles.filterChipActive]}
                    >
                      <Text style={[styles.filterChipText, filterCategory === cat.id && styles.filterChipTextActive]}>
                        {displayName}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {/* Availability */}
              <Text style={styles.filterLabel}>{t('filter.availability', 'التوفر')}</Text>
              <TouchableOpacity 
                style={styles.checkboxRow} 
                onPress={() => setFilterInStock(!filterInStock)}
              >
                <Ionicons name={filterInStock ? "checkbox" : "square-outline"} size={24} color={filterInStock ? Colors.primary : Colors.textMuted} />
                <Text style={styles.checkboxText}>{t('filter.available_only', 'المتوفر فقط')}</Text>
              </TouchableOpacity>
              
            </ScrollView>
            <View style={styles.modalFooter}>
              <TouchableOpacity 
                style={styles.resetButton} 
                onPress={() => {
                  setFilterListingType(null);
                  setFilterDistance(5);
                  setFilterInStock(true);
                  setFilterCategory(null);
                }}
              >
                <Text style={styles.resetButtonText}>{t('filter.reset', 'إعادة ضبط')}</Text>
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
                <Text style={styles.applyButtonText}>{t('filter.apply', 'تطبيق الفلاتر')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* ── Toast Notification ────────────────────────────────────── */}
      {toastVisible && (
        <View style={styles.toast}>
          <Text style={styles.toastText}>{toastMessage}</Text>
        </View>
      )}

</KeyboardAvoidingView>
  );
}
