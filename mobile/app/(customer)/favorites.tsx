/**
 * Customer Favorites — Saved markets and items.
 * Uses SecureStore for persistent, local encrypted storage.
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity, RefreshControl,
  ActivityIndicator, Alert, Animated, Easing
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import { getFavorites, getMarketItemDetails, removeFavorite, SearchResultItem } from '../../services/api';
import ProductCard from '../../components/ProductCard';

export default function FavoritesScreen() {
  const Colors = useThemeColors();

  const styles = useMemo(() => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.lg,
  },
  title: {
    ...Typography.h1,
    color: Colors.textPrimary,
  },
  subtitle: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  tabsContainer: {
    paddingHorizontal: Spacing.xl,
    marginBottom: Spacing.lg,
  },
  tabsBackground: {
    flexDirection: 'row',
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.full,
    padding: 4,
    position: 'relative',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  tabActiveIndicator: {
    position: 'absolute',
    top: 4,
    bottom: 4,
    width: '48%',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  tabButton: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
  },
  tabText: {
    ...Typography.body,
    color: Colors.textSecondary,
    fontWeight: '500',
  },
  tabTextActive: {
    color: Colors.textPrimary,
    fontWeight: '700',
  },
  listContent: {
    flexGrow: 1,
    paddingHorizontal: Spacing.xl,
    paddingBottom: Spacing.xl,
  },
  loaderContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loaderText: { ...Typography.bodySmall, color: Colors.textMuted, marginTop: Spacing.sm },
  cardWrapper: {
    position: 'relative',
    marginBottom: Spacing.sm,
  },
  deleteButton: {
    position: 'absolute',
    top: Spacing.md,
    right: Spacing.md,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(226, 75, 74, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(226, 75, 74, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: Spacing.xl,
  },
  emptyIconWrapper: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: 'rgba(255, 107, 157, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.xl,
    borderWidth: 1,
    borderColor: 'rgba(255, 107, 157, 0.2)',
  },
  emptyTitle: {
    ...Typography.h2,
    color: Colors.textPrimary,
    marginBottom: Spacing.sm,
  },
  emptyDesc: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: Spacing.xxl,
  },
  featureList: {
    width: '100%',
    gap: Spacing.md,
    marginBottom: Spacing.xxxl,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  featureIcon: {
    width: 24,
    textAlign: 'center',
  },
  featureText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontSize: 14,
  },
  exploreBtn: {
    backgroundColor: Colors.primary,
    paddingVertical: 14,
    paddingHorizontal: 32,
    borderRadius: BorderRadius.full,
    width: '100%',
    alignItems: 'center',
    ...Shadows.small,
  },
  exploreBtnText: {
    ...Typography.button,
    color: Colors.textOnPrimary,
  },
}), [Colors]);
  const router = useRouter();
  const [favoritesList, setFavoritesList] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<'products' | 'shops'>('products');

  // Animation for tabs
  const slideAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(slideAnim, {
      toValue: activeTab === 'products' ? 0 : 1,
      duration: 250,
      easing: Easing.out(Easing.ease),
      useNativeDriver: false,
    }).start();
  }, [activeTab]);

  const loadFavorites = async () => {
    try {
      setLoading(true);
      const favIds = await getFavorites();
      if (favIds.length === 0) {
        setFavoritesList([]);
        setLoading(false);
        return;
      }

      // Fetch details of all favorite items in parallel
      const details = await Promise.all(
        favIds.map(async (id) => {
          try {
            const item = await getMarketItemDetails(id);
            // Map MarketItemDetailsResponse to SearchResultItem format expected by ProductCard
            return {
              product_id: item.id,
              product_name: item.name,
              description: item.description,
              price: item.price,
              category: item.category,
              image_url: item.image_url,
              in_stock: item.in_stock,
              shop: {
                id: item.shop.id,
                name: item.shop.name,
                address: item.shop.address,
                latitude: item.shop.latitude,
                longitude: item.shop.longitude,
                phone: item.shop.phone ?? null,
                is_currently_open: item.shop.is_currently_open,
              },
              distance_km: 0.0, // Distance can default to 0.0
              semantic_score: 1.0,
              hybrid_score: 1.0,
            } as SearchResultItem;
          } catch (err) {
            console.warn(`Failed to load details for fav item: ${id}. Auto-removing from storage.`, err);
            try {
              await removeFavorite(id);
            } catch (cleanupErr) {
              console.warn(`Failed to auto-remove deleted fav item: ${id}`, cleanupErr);
            }
            return null;
          }
        })
      );

      // Filter out failed loaded items
      setFavoritesList(details.filter((item): item is SearchResultItem => item !== null));
    } catch (err) {
      console.error('Failed to load favorites list:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Re-fetch favorites whenever screen is navigated to
  useFocusEffect(
    useCallback(() => {
      loadFavorites();
    }, [])
  );

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadFavorites();
  }, []);

  const handleRemoveFav = async (itemId: string) => {
    Alert.alert(
      t('favorites.removed', 'Remove Favorite'),
      t('offers.confirm_delete', 'Are you sure you want to remove this item from your favorites?'),
      [
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
        {
          text: t('common.delete', 'Delete'),
          style: 'destructive',
          onPress: async () => {
            await removeFavorite(itemId);
            loadFavorites();
          }
        }
      ]
    );
  };

  const renderEmptyState = () => (
    <View style={styles.emptyContainer}>
      <View style={styles.emptyIconWrapper}>
        <Ionicons name="heart" size={40} color={Colors.accent} />
      </View>
      <Text style={styles.emptyTitle}>
        {t('favorites.empty', 'No favorites yet')}
      </Text>
      <Text style={styles.emptyDesc}>
        {t('favorites.empty_desc', 'Start exploring nearby markets and save your favorite items here')}
      </Text>

      <View style={styles.featureList}>
        <View style={styles.featureItem}>
          <Ionicons name="storefront-outline" size={20} color={Colors.textSecondary} style={styles.featureIcon} />
          <Text style={styles.featureText}>
            {t('favorites.save_markets', 'Save your favorite markets')}
          </Text>
        </View>
        <View style={styles.featureItem}>
          <Ionicons name="bookmark-outline" size={20} color={Colors.textSecondary} style={styles.featureIcon} />
          <Text style={styles.featureText}>
            {t('favorites.track_products', 'Track products you love')}
          </Text>
        </View>
        <View style={styles.featureItem}>
          <Ionicons name="notifications-outline" size={20} color={Colors.textSecondary} style={styles.featureIcon} />
          <Text style={styles.featureText}>
            {t('favorites.get_notified', 'Get notified on price drops')}
          </Text>
        </View>
      </View>

      <TouchableOpacity
        style={styles.exploreBtn}
        activeOpacity={0.8}
        onPress={() => router.replace('/(customer)/search')}
      >
        <Text style={styles.exploreBtnText}>
          {t('favorites.start_exploring', 'Start Exploring')}
        </Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>{t('favorites.title', 'Favorites')}</Text>
        <Text style={styles.subtitle}>
          {t('favorites.subtitle', 'Your saved markets & products')}
        </Text>
      </View>

      {/* Segmented Tabs */}
      <View style={styles.tabsContainer}>
        <View style={styles.tabsBackground}>
          <Animated.View
            style={[
              styles.tabActiveIndicator,
              {
                left: slideAnim.interpolate({
                  inputRange: [0, 1],
                  outputRange: ['2%', '50%'],
                })
              }
            ]}
          />
          <TouchableOpacity
            style={styles.tabButton}
            onPress={() => setActiveTab('products')}
            activeOpacity={0.8}
          >
            <Text style={[styles.tabText, activeTab === 'products' && styles.tabTextActive]}>
              {t('favorites.products_tab', 'Products')}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.tabButton}
            onPress={() => setActiveTab('shops')}
            activeOpacity={0.8}
          >
            <Text style={[styles.tabText, activeTab === 'shops' && styles.tabTextActive]}>
              {t('favorites.shops_tab', 'Shops')}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Content */}
      {loading && !refreshing ? (
        <View style={styles.loaderContainer}>
          <ActivityIndicator size="large" color={Colors.primary} />
          <Text style={styles.loaderText}>{t('common.loading', 'Loading favorites...')}</Text>
        </View>
      ) : activeTab === 'shops' ? (
        // Placeholder for shops tab
        <View style={styles.emptyContainer}>
          <View style={[styles.emptyIconWrapper, { backgroundColor: 'rgba(108, 99, 255, 0.1)', borderColor: 'rgba(108, 99, 255, 0.2)' }]}>
            <Ionicons name="storefront-outline" size={40} color={Colors.primary} />
          </View>
          <Text style={styles.emptyTitle}>
            {t('messages.coming_soon', 'Favorite shops list — coming soon')}
          </Text>
          <Text style={styles.emptyDesc}>
            {t('favorites.save_markets', 'Save shops for quick access and receive updates')}
          </Text>
        </View>
      ) : (
        <FlatList
          data={favoritesList}
          keyExtractor={(item) => item.product_id}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={Colors.primary}
            />
          }
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <View style={styles.cardWrapper}>
              <ProductCard item={item} />
              <TouchableOpacity
                style={styles.deleteButton}
                activeOpacity={0.7}
                onPress={() => handleRemoveFav(item.product_id)}
              >
                <Ionicons name="trash-outline" size={20} color={Colors.error} />
              </TouchableOpacity>
            </View>
          )}
          ListEmptyComponent={renderEmptyState()}
        />
      )}
    </SafeAreaView>
  );
}
