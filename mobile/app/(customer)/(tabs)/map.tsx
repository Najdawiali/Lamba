/**
 * Map Screen — Google Maps with nearby shop markers and interactive carousel.
 */

import React, { useEffect, useState, useRef, useCallback, useMemo, memo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator,
  FlatList, Image, Platform, Alert, useWindowDimensions, NativeSyntheticEvent, NativeScrollEvent
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import MapView, { Marker, PROVIDER_GOOGLE } from 'react-native-maps';
import * as Location from 'expo-location';
import * as Linking from 'expo-linking';
import { Ionicons } from '@expo/vector-icons';
import { useLocation } from '../../../hooks/useLocation';
import EnableLocationPrompt from '../../../components/EnableLocationPrompt';
import { getNearMarkets, NearMarketResponse } from '../../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../../constants/theme';
import { useTheme } from '../../../context/ThemeContext';
import { t, i18n } from '../../../services/i18n';
import { getMapStyle, calculateDistanceMeters, openMapDirections, formatDistanceKm } from '../../../services/utils';

const CARD_WIDTH = 280;
const CARD_MARGIN = 10;
const SNAP_INTERVAL = CARD_WIDTH + CARD_MARGIN * 2;

// Default search radius (km) used by the map view — kept in sync with the
// getNearMarkets(…, 10) call below so the visible region reflects the data.
const MAP_RADIUS_KM = 10;

/**
 * Compute MapView latitude/longitude deltas for a given radius in km so the
 * visible region actually encompasses the queried results (instead of a
 * hardcoded 0.02° patch that drops most markers off-screen for a 10 km query).
 */
const regionDeltasForRadius = (radiusKm: number, latitude: number) => {
  const safeRadius = Math.max(radiusKm, 0.5); // never collapse to a single point
  const latitudeDelta = safeRadius / 111.0; // ~111 km per degree of latitude
  const longitudeDelta = safeRadius / (111.0 * Math.max(Math.cos(latitude * Math.PI / 180), 0.1));
  return { latitudeDelta, longitudeDelta };
};

// Pre-rendered pin images (1x–4x densities). Image markers are drawn natively
// by Google Maps, with no view snapshot, so they can't clip and stay cheap at any scale.
const MARKER_DEFAULT = require('../../../assets/images/markers/marker-store.png');
const MARKER_SELECTED = require('../../../assets/images/markers/marker-store-selected.png');
// The pin tip sits at 60/64 of the image height, so the tip points exactly at the store.
const MARKER_ANCHOR = { x: 0.5, y: 0.9375 };

const StoreMarker = memo(function StoreMarker({
  coordinate,
  isSelected,
  onPress,
}: {
  coordinate: { latitude: number; longitude: number };
  isSelected: boolean;
  onPress: () => void;
}) {
  return (
    <Marker
      coordinate={coordinate}
      onPress={onPress}
      zIndex={isSelected ? 10 : 1}
      anchor={MARKER_ANCHOR}
      image={isSelected ? MARKER_SELECTED : MARKER_DEFAULT}
      tracksViewChanges={false}
    />
  );
});

export default function MapScreen() {
  const { colors: Colors, scheme } = useTheme();
  const mapStyle = useMemo(() => getMapStyle(scheme), [scheme]);

  const styles = useMemo(() => StyleSheet.create({
  container: { flex: 1 },
  map: { flex: 1 },
  deniedContainer: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center', padding: Spacing.xxl },
  deniedTitle: { ...Typography.h2, color: Colors.textPrimary, marginTop: Spacing.lg, textAlign: 'center' },
  deniedText: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.md, marginBottom: Spacing.xl },
  settingsBtn: { width: '100%', height: 48, backgroundColor: Colors.primary, borderRadius: BorderRadius.md, justifyContent: 'center', alignItems: 'center' },
  settingsBtnText: { ...Typography.button, color: Colors.textOnPrimary },
  retryBtn: { marginTop: Spacing.md, paddingVertical: Spacing.sm },
  retryBtnText: { ...Typography.bodySmall, color: Colors.textMuted },
  
  titleBar: { position: 'absolute', top: 0, left: 0, right: 0 },
  titleContainer: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, backgroundColor: Colors.surfaceElevated, alignSelf: 'center', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, borderRadius: BorderRadius.full, marginTop: Spacing.sm, borderWidth: 1, borderColor: Colors.border, ...Shadows.small },
  title: { ...Typography.label, color: Colors.textPrimary },
  countBadge: { backgroundColor: Colors.primary, borderRadius: 10, width: 20, height: 20, justifyContent: 'center', alignItems: 'center' },
  countText: { fontSize: 10, fontWeight: '700', color: Colors.textOnPrimary },

  recenterBtn: { position: 'absolute', bottom: 150, right: Spacing.xl, width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surfaceElevated, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: Colors.border, ...Shadows.medium, zIndex: 10 },
  
  loadingOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(10,10,26,0.3)' },
  
  emptyOverlay: { position: 'absolute', bottom: 100, left: Spacing.xl, right: Spacing.xl },
  emptyCard: { backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.xl, padding: Spacing.xl, alignItems: 'center', borderWidth: 1, borderColor: Colors.border, ...Shadows.medium },
  emptyTitle: { ...Typography.h3, color: Colors.textPrimary, marginTop: Spacing.md },
  emptyDesc: { ...Typography.bodySmall, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.sm },

  carouselContainer: { position: 'absolute', bottom: 30, left: 0, right: 0, height: 110 },
  cardContainer: { width: CARD_WIDTH, marginHorizontal: CARD_MARGIN, height: 100, backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.lg, padding: Spacing.md, flexDirection: 'row', alignItems: 'center', gap: Spacing.md, borderWidth: 1, borderColor: Colors.border, ...Shadows.medium },
  cardIcon: { width: 60, height: 60, borderRadius: 30, backgroundColor: 'rgba(108, 99, 255, 0.1)', justifyContent: 'center', alignItems: 'center' },
  cardContent: { flex: 1, justifyContent: 'center' },
  cardTitle: { ...Typography.h3, color: Colors.textPrimary, marginBottom: 2 },
  cardSubtitle: { ...Typography.caption, color: Colors.textSecondary, marginBottom: 8 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  statusBadge: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 10, fontWeight: '700' },
  distanceText: { ...Typography.caption, color: Colors.primary, fontWeight: '600' }
}), [Colors]);
  const mapRef = useRef<MapView>(null);
  const flatListRef = useRef<FlatList>(null);
  const router = useRouter();
  const { width: SCREEN_WIDTH } = useWindowDimensions();

  // Location & Markets
  const { location: userLocation, loading: locationLoading, denied: locationDenied, refresh: refreshLocation } = useLocation();
  const [markets, setMarkets] = useState<NearMarketResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [focusedIndex, setFocusedIndex] = useState(0);

  useEffect(() => {
    if (!userLocation) return;
    let isMounted = true;
    (async () => {
      setLoading(true);
      try {
        const nearbyMarkets = await getNearMarkets(userLocation.latitude, userLocation.longitude, 10);
        if (!isMounted) return;
        setMarkets(nearbyMarkets);

        if (mapRef.current && nearbyMarkets.length > 0) {
          setTimeout(() => {
            const targetLat = Number(nearbyMarkets[0].latitude);
            const targetLng = Number(nearbyMarkets[0].longitude);
            if (!isNaN(targetLat) && !isNaN(targetLng) && targetLat !== 0) {
              const deltas = regionDeltasForRadius(MAP_RADIUS_KM, targetLat);
              mapRef.current?.animateToRegion({
                latitude: targetLat,
                longitude: targetLng,
                latitudeDelta: deltas.latitudeDelta,
                longitudeDelta: deltas.longitudeDelta,
              }, 500);
            }
          }, 500);
        } else if (mapRef.current) {
          setTimeout(() => {
            const deltas = regionDeltasForRadius(MAP_RADIUS_KM, userLocation.latitude);
            mapRef.current?.animateToRegion({
              ...userLocation,
              latitudeDelta: deltas.latitudeDelta,
              longitudeDelta: deltas.longitudeDelta,
            }, 500);
          }, 500);
        }
      } catch (err) {
        console.error('Map load failed:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    })();
    return () => { isMounted = false; };
  }, [userLocation]);

  const onScroll = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const offsetX = event.nativeEvent.contentOffset.x;
    const index = Math.round(offsetX / SNAP_INTERVAL);
    if (index !== focusedIndex && index >= 0 && index < markets.length) {
      setFocusedIndex(index);
      const market = markets[index];
      const deltas = regionDeltasForRadius(MAP_RADIUS_KM, market.latitude);
      mapRef.current?.animateToRegion({
        latitude: market.latitude,
        longitude: market.longitude,
        latitudeDelta: deltas.latitudeDelta,
        longitudeDelta: deltas.longitudeDelta,
      }, 350);
    }
  }, [focusedIndex, markets]);

  const handleMarkerPress = (index: number) => {
    flatListRef.current?.scrollToIndex({ index, animated: true });
  };

  const handleOpenSettings = () => {
    if (Platform.OS === 'ios') {
      Linking.openURL('app-settings:');
    } else {
      Linking.openSettings();
    }
  };

  if (locationDenied) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: Colors.background }}>
        <EnableLocationPrompt onRetry={refreshLocation} />
      </SafeAreaView>
    );
  }

  return (
    <View style={styles.container}>
      <MapView
        ref={mapRef}
        style={styles.map}
        provider={PROVIDER_GOOGLE}
        showsUserLocation
        showsMyLocationButton={false}
        customMapStyle={mapStyle}
        initialRegion={{
          latitude: userLocation?.latitude ?? 31.95,
          longitude: userLocation?.longitude ?? 35.91,
          latitudeDelta: 0.05,
          longitudeDelta: 0.05,
        }}
        onMapReady={() => {}}
      >
        {markets.map((market, index) => {
          const isSelected = focusedIndex === index;
          const lat = Number(market.latitude);
          const lng = Number(market.longitude);
          if (isNaN(lat) || isNaN(lng) || (lat === 0 && lng === 0)) return null;
          return (
            <StoreMarker
              key={market.id}
              coordinate={{ latitude: lat, longitude: lng }}
              isSelected={isSelected}
              onPress={() => handleMarkerPress(index)}
            />
          );
        })}
      </MapView>

      <SafeAreaView style={styles.titleBar} edges={['top']}>
        <View style={styles.titleContainer}>
          <Ionicons name="map" size={18} color={Colors.primary} />
          <Text style={styles.title}>{t('map.nearby_markets', 'Nearby Markets')}</Text>
          {markets.length > 0 ? (
            <View style={styles.countBadge}>
              <Text style={styles.countText}>{markets.length}</Text>
            </View>
          ) : null}
        </View>
      </SafeAreaView>

      <TouchableOpacity
        style={styles.recenterBtn}
        onPress={() => {
          if (userLocation) {
            const deltas = regionDeltasForRadius(MAP_RADIUS_KM, userLocation.latitude);
            mapRef.current?.animateToRegion({
              ...userLocation,
              latitudeDelta: deltas.latitudeDelta,
              longitudeDelta: deltas.longitudeDelta,
            }, 500);
          }
        }}
      >
        <Ionicons name="locate" size={22} color={Colors.primary} />
      </TouchableOpacity>

      {loading ? (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : null}

      {!loading && markets.length === 0 ? (
        <View style={styles.emptyOverlay}>
          <View style={styles.emptyCard}>
            <Ionicons name="storefront-outline" size={40} color={Colors.textMuted} />
            <Text style={styles.emptyTitle}>{t('map.no_markets', 'No markets found')}</Text>
            <Text style={styles.emptyDesc}>{t('map.no_markets_desc', 'Try moving the map to another area.')}</Text>
          </View>
        </View>
      ) : null}

      {!loading && markets.length > 0 ? (
        <View style={styles.carouselContainer}>
          <FlatList
            ref={flatListRef}
            data={markets}
            horizontal
            showsHorizontalScrollIndicator={false}
            snapToInterval={SNAP_INTERVAL}
            snapToAlignment="center"
            decelerationRate="fast"
            onScroll={onScroll}
            scrollEventThrottle={16}
            contentContainerStyle={{ paddingHorizontal: (SCREEN_WIDTH - SNAP_INTERVAL) / 2 + CARD_MARGIN }}
            keyExtractor={item => item.id}
            renderItem={({ item, index }) => (
              <TouchableOpacity
                activeOpacity={0.9}
                onPress={() => router.push(`/(customer)/shop/${item.id}`)}
                style={styles.cardContainer}
              >
                <View style={styles.cardIcon}>
                  <Ionicons name="storefront" size={28} color={Colors.primary} />
                </View>
                <View style={styles.cardContent}>
                  <Text style={styles.cardTitle} numberOfLines={1}>{item.name}</Text>
                  <Text style={styles.cardSubtitle} numberOfLines={1}>{item.address}</Text>
                  <View style={styles.cardFooter}>
                    <View style={styles.statusBadge}>
                      <View style={[styles.statusDot, { backgroundColor: item.is_currently_open ? Colors.success : Colors.error }]} />
                      <Text style={[styles.statusText, { color: item.is_currently_open ? Colors.success : Colors.error }]}>
                        {item.is_currently_open ? t('common.open', 'Open') : t('common.closed', 'Closed')}
                      </Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Text style={styles.distanceText}>
                        {formatDistanceKm(item.distance_km, i18n.locale?.startsWith('ar'))}
                      </Text>
                      <TouchableOpacity
                        onPress={(e) => {
                          e.stopPropagation();
                          openMapDirections(item.latitude, item.longitude, item.name);
                        }}
                        style={{
                          backgroundColor: Colors.primary + '20',
                          borderRadius: 8,
                          paddingHorizontal: 8,
                          paddingVertical: 4,
                          flexDirection: 'row',
                          alignItems: 'center',
                          gap: 4,
                        }}
                      >
                        <Ionicons name="navigate-outline" size={12} color={Colors.primary} />
                        <Text style={{ fontSize: 11, fontWeight: '700', color: Colors.primary }}>
                          {t('common.directions', 'الاتجاهات')}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              </TouchableOpacity>
            )}
          />
        </View>
      ) : null}
    </View>
  );

}
