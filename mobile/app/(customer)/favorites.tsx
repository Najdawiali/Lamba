/**
 * Favorites Screen — Shows products the user has saved via the heart icon.
 *
 * Favorites are stored locally in SecureStore as an array of market_item IDs.
 * This screen fetches full item details for each saved ID and displays them
 * in a scrollable list with remove capability.
 */

import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, RefreshControl, Alert, Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useFocusEffect } from 'expo-router';
import { useThemeColors } from '../../context/ThemeContext';
import { Spacing, BorderRadius, Typography } from '../../constants/theme';
import { t, i18n } from '../../services/i18n';
import { formatPrice } from '../../services/currency';
import { resolveImageUrl } from '../../services/utils';
import {
  getFavorites, removeFavorite,
  getMarketItemDetails, MarketItemDetailsResponse,
} from '../../services/api';

export default function FavoritesScreen() {
  const Colors = useThemeColors();
  const router = useRouter();
  const isAr = i18n.locale?.startsWith('ar');

  const [items, setItems] = useState<MarketItemDetailsResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadFavorites = useCallback(async () => {
    try {
      const favIds = await getFavorites();
      if (favIds.length === 0) {
        setItems([]);
        return;
      }

      // Fetch details for each favorite (parallel)
      const results = await Promise.allSettled(
        favIds.map(id => getMarketItemDetails(id))
      );

      const validItems = results
        .filter((r): r is PromiseFulfilledResult<MarketItemDetailsResponse> => r.status === 'fulfilled')
        .map(r => r.value);

      setItems(validItems);
    } catch (err) {
      console.error('Failed to load favorites:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Reload when screen comes into focus (e.g., after adding/removing from another screen)
  useFocusEffect(
    useCallback(() => {
      loadFavorites();
    }, [loadFavorites])
  );

  const handleRemove = (itemId: string, itemName: string) => {
    Alert.alert(
      t('favorites.remove_title', 'Remove from Favorites'),
      t('favorites.remove_confirm', `Remove "${itemName}" from your favorites?`),
      [
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
        {
          text: t('common.remove', 'Remove'),
          style: 'destructive',
          onPress: async () => {
            await removeFavorite(itemId);
            setItems(prev => prev.filter(i => i.id !== itemId));
          },
        },
      ],
    );
  };

  const renderItem = ({ item }: { item: MarketItemDetailsResponse }) => {
    const displayName = isAr ? (item.name_ar || item.name) : (item.name_en || item.name);
    const imageUrl = item.image_url ? resolveImageUrl(item.image_url) : null;

    return (
      <TouchableOpacity
        style={[styles.card, { backgroundColor: Colors.surface, borderColor: Colors.border }]}
        activeOpacity={0.7}
        onPress={() => router.push(`/(customer)/shop/${item.shop?.id}` as any)}
      >
        <View style={[styles.imageBox, { backgroundColor: Colors.surfaceElevated }]}>
          {imageUrl ? (
            <Image source={{ uri: imageUrl }} style={styles.image} />
          ) : (
            <Ionicons name="cube-outline" size={32} color={Colors.textMuted} />
          )}
        </View>

        <View style={styles.info}>
          <Text style={[styles.name, { color: Colors.textPrimary }]} numberOfLines={2}>
            {displayName}
          </Text>
          {item.shop && (
            <Text style={[styles.shopName, { color: Colors.textMuted }]} numberOfLines={1}>
              {isAr ? (item.shop.name || '') : (item.shop.name || '')}
            </Text>
          )}
          {item.price != null && (
            <Text style={[styles.price, { color: Colors.primary }]}>
              {formatPrice(item.price)}
            </Text>
          )}
          {!item.in_stock && (
            <Text style={[styles.outOfStock, { color: Colors.error }]}>
              {t('common.out_of_stock', 'Out of Stock')}
            </Text>
          )}
        </View>

        <TouchableOpacity
          style={styles.removeBtn}
          onPress={() => handleRemove(item.id, displayName)}
          hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
        >
          <Ionicons name="heart" size={22} color={Colors.error} />
        </TouchableOpacity>
      </TouchableOpacity>
    );
  };

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: Colors.background }]} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerBtn}>
            <Ionicons name={isAr ? 'arrow-forward' : 'arrow-back'} size={22} color={Colors.textPrimary} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: Colors.textPrimary }]}>
            {t('favorites.title', 'My Favorites')}
          </Text>
          <View style={{ width: 40 }} />
        </View>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: Colors.background }]} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerBtn}>
          <Ionicons name={isAr ? 'arrow-forward' : 'arrow-back'} size={22} color={Colors.textPrimary} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: Colors.textPrimary }]}>
          {t('favorites.title', 'My Favorites')}
        </Text>
        <View style={{ width: 40 }} />
      </View>

      {items.length === 0 ? (
        <View style={styles.center}>
          <Ionicons name="heart-outline" size={64} color={Colors.textMuted} />
          <Text style={[styles.emptyTitle, { color: Colors.textPrimary }]}>
            {t('favorites.empty', 'No favorites yet')}
          </Text>
          <Text style={[styles.emptySubtitle, { color: Colors.textMuted }]}>
            {t('favorites.empty_hint', 'Tap the heart icon on any product to save it here')}
          </Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => { setRefreshing(true); loadFavorites(); }}
              tintColor={Colors.primary}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
  },
  headerBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { ...Typography.h3, textAlign: 'center' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: Spacing.xl },
  emptyTitle: { ...Typography.h3, marginTop: Spacing.lg, textAlign: 'center' },
  emptySubtitle: { ...Typography.body, marginTop: Spacing.sm, textAlign: 'center' },
  list: { padding: Spacing.lg, gap: Spacing.md },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
  },
  imageBox: {
    width: 72, height: 72,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
    marginEnd: Spacing.md,
  },
  image: { width: 72, height: 72, resizeMode: 'cover' },
  info: { flex: 1, marginEnd: Spacing.sm },
  name: { ...Typography.body, fontWeight: '600' },
  shopName: { ...Typography.caption, marginTop: 2 },
  price: { ...Typography.body, fontWeight: '700', marginTop: 4 },
  outOfStock: { ...Typography.caption, marginTop: 2 },
  removeBtn: { padding: Spacing.sm },
});
