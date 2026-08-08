/**
 * ProductCard — Search result card with premium design.
 *
 * Shows product image, name, price, shop, distance,
 * relevance score badge, and stock status indicator.
 * Includes interactive Rating triggers for hyper-local shops.
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Image, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { SearchResultItem, isFavorite, addFavorite, removeFavorite, startChatSession } from '../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../constants/theme';
import { useThemeColors } from '../context/ThemeContext';
import { t, i18n } from '../services/i18n';
import { resolveImageUrl } from '../services/utils';
import { formatPrice } from '../services/currency';

interface Props {
  item: SearchResultItem;
}

export default function ProductCard({ item }: Props) {
  const router = useRouter();
  const Colors = useThemeColors();

  const styles = useMemo(() => StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.lg,
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
    ...Shadows.small,
    minHeight: 115,
    position: 'relative',
  },
  imageContainer: {
    position: 'absolute',
    start: 0,
    top: 0,
    bottom: 0,
    width: 100,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  image: {
    width: '100%',
    height: '100%',
    resizeMode: 'cover',
  },
  imagePlaceholder: {
    width: '100%',
    height: '100%',
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scoreBadge: {
    position: 'absolute',
    top: Spacing.xs,
    start: Spacing.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  favBtn: {
    position: 'absolute',
    top: Spacing.xs,
    end: Spacing.xs,
    backgroundColor: Colors.modalOverlay,
    width: 28,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.25)',
    ...Shadows.small,
  },
  scoreText: {
    ...Typography.caption,
    color: '#FFFFFF',
    fontWeight: '700',
  },
  scoreTextDark: {
    ...Typography.caption,
    color: '#0A0A1A',
    fontWeight: '700',
  },
  content: {
    flex: 1,
    marginStart: 100,
    padding: Spacing.md,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 2,
  },
  name: {
    ...Typography.h3,
    fontSize: 15,
    color: Colors.textPrimary,
    flex: 1,
  },
  stockDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginLeft: Spacing.sm,
  },
  description: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.sm,
  },
  price: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.secondary,
  },
  currency: {
    fontSize: 12,
    fontWeight: '400',
    color: Colors.textMuted,
  },
  categoryBadge: {
    backgroundColor: Colors.surface,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  categoryText: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  shopDetailsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 2,
    marginBottom: Spacing.sm,
  },
  shopName: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
    flex: 1,
  },
  pillRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
  },
  distancePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    backgroundColor: Colors.surface,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  distanceText: {
    ...Typography.caption,
    color: Colors.secondary,
  },
  ratePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    backgroundColor: Colors.surface,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: Colors.ratePillBorder,
  },
  chatPill: {
    backgroundColor: Colors.chatPillBg,
    borderColor: Colors.chatPillBorder,
  },
  rateText: {
    ...Typography.caption,
    color: Colors.ratePillText,
    fontWeight: '600',
  },
  shopStatusMiniBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 1,
    paddingHorizontal: 6,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    flexShrink: 0,
  },
  statusDotMini: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
  },
  shopStatusMiniText: {
    fontSize: 9,
    fontWeight: '700',
  },
  }), [Colors]);
  const [isFav, setIsFav] = useState(false);
  const rawScore = item.semantic_score != null && !isNaN(item.semantic_score)
    ? item.semantic_score
    : (item.hybrid_score != null && !isNaN(item.hybrid_score) ? item.hybrid_score : null);

  const scorePercent = rawScore !== null
    ? Math.min(100, Math.max(0, Math.round(rawScore * 100)))
    : null;
  const favPressedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const fav = await isFavorite(item.product_id);
        if (!cancelled) setIsFav(fav);
      } catch (err) {
        console.error('Failed to load favorite state in card:', err);
      }
    })();
    return () => { cancelled = true; };
  }, [item.product_id]);

  const handleToggleFavorite = async () => {
    try {
      if (isFav) {
        await removeFavorite(item.product_id);
        setIsFav(false);
        Alert.alert(
          t('favorites.removed'),
          `"${item.product_name}" ${t('favorites.removed_desc')}`
        );
      } else {
        await addFavorite(item.product_id);
        setIsFav(true);
        Alert.alert(
          t('favorites.added'),
          `"${item.product_name}" ${t('favorites.added_desc')}`
        );
      }
    } catch (err) {
      console.error('Failed to toggle favorite in card:', err);
    }
  };

  return (
      <TouchableOpacity
        style={styles.card}
        activeOpacity={0.7}
        onPress={() => {
          if (favPressedRef.current) { favPressedRef.current = false; return; }
          router.push(`/(customer)/product/${item.product_id}`);
        }}
      >
        {/* Image */}
        <View style={styles.imageContainer}>
          {item.image_url ? (
            <Image source={{ uri: resolveImageUrl(item.image_url) }} style={styles.image} />
          ) : (
            <View style={styles.imagePlaceholder}>
              <Ionicons name="cube-outline" size={28} color={Colors.textMuted} />
            </View>
          )}
          {/* Score Badge */}
          {typeof scorePercent === 'number' && scorePercent > 0 && !isNaN(scorePercent) ? (
            <View style={[styles.scoreBadge, { backgroundColor: scorePercent >= 70 ? Colors.success : scorePercent >= 40 ? Colors.warning : Colors.textMuted }]}>
              <Text style={scorePercent >= 70 ? styles.scoreTextDark : styles.scoreText}>
                {Math.min(scorePercent, 100)}%
              </Text>
            </View>
          ) : null}
          {/* Heart Button */}
          <TouchableOpacity
            style={styles.favBtn}
            activeOpacity={0.8}
            onPress={() => {
            favPressedRef.current = true;
            handleToggleFavorite();
          }}
          >
            <Ionicons
              name={isFav ? "heart" : "heart-outline"}
              size={15}
              color={isFav ? Colors.accent : Colors.textOnPrimary}
            />
          </TouchableOpacity>
        </View>

        {/* Content */}
        <View style={styles.content}>
          {/* Product Name & Stock */}
          <View style={styles.nameRow}>
            <Text style={styles.name} numberOfLines={1}>{item.product_name}</Text>
            <View style={[styles.stockDot, { backgroundColor: item.in_stock ? Colors.inStock : Colors.outOfStock }]} />
          </View>

          {/* Description */}
          {Boolean(item.description) ? (
            <Text style={styles.description} numberOfLines={2}>{item.description}</Text>
          ) : null}

          {/* Meta Row */}
          <View style={styles.metaRow}>
            {/* Price */}
            {item.price != null && item.price > 0 ? (
              <Text style={styles.price}>
                {formatPrice(item.price)}
              </Text>
            ) : null}

            {/* Category */}
            {Boolean(item.category) ? (
              <View style={styles.categoryBadge}>
                <Text style={styles.categoryText}>{item.category}</Text>
              </View>
            ) : null}
          </View>

          {/* Shop Details Row */}
          <View style={styles.shopDetailsRow}>
            <Ionicons name="storefront-outline" size={13} color={Colors.textMuted} />
            <Text style={styles.shopName} numberOfLines={1}>{item.shop?.name || ''}</Text>
            <View style={[
              styles.shopStatusMiniBadge,
              {
                backgroundColor: item.shop?.is_currently_open ? Colors.successBg : Colors.errorBg,
                borderColor: item.shop?.is_currently_open ? Colors.successBorder : Colors.errorBorder,
              }
            ]}>
              <View style={[styles.statusDotMini, { backgroundColor: item.shop?.is_currently_open ? Colors.success : Colors.error }]} />
              <Text style={[styles.shopStatusMiniText, { color: item.shop?.is_currently_open ? Colors.success : Colors.error }]}>
                {item.shop?.is_currently_open ? t('common.open') : t('common.closed')}
              </Text>
            </View>
          </View>

          {/* Actions/Pills Row */}
          <View style={styles.pillRow}>
            {/* Distance Pill */}
            <View style={styles.distancePill}>
              <Ionicons name="navigate-outline" size={11} color={Colors.secondary} />
              <Text style={styles.distanceText}>
                {typeof item.distance_km === 'number' ? `${item.distance_km.toFixed(1)} ` : '0 '}{t('common.km')}
              </Text>
            </View>

            {/* Chat / Message Shop Pill */}
            <TouchableOpacity
              style={[styles.ratePill, styles.chatPill]}
              onPress={async () => {
                try {
                  const session = await startChatSession(item.shop.id);
                  router.push(`/(customer)/inbox?sessionId=${session.id}` as any);
                } catch (err) {
                  // Navigate to inbox smoothly without blocking alert dialog
                  router.push('/(customer)/inbox');
                }
              }}
              activeOpacity={0.6}
            >
              <Ionicons name="chatbubbles" size={11} color={Colors.primary} />
              <Text style={[styles.rateText, { color: Colors.primary }]}>{t('inbox.title')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </TouchableOpacity>
  );

}
