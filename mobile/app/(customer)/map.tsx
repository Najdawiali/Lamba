/**
 * Map Screen — Google Maps with nearby shop markers and interactive carousel.
 */

import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
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
import { getNearMarkets, NearMarketResponse } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useTheme } from '../../context/ThemeContext';
import { t } from '../../services/i18n';
import { getMapStyle, calculateDistanceMeters } from '../../services/utils';

const CARD_WIDTH = 280;
const CARD_MARGIN = 10;
const SNAP_INTERVAL = CARD_WIDTH + CARD_MARGIN * 2;

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
  
  markerPin: { width: 40, height: 40, borderRadius: 20, backgroundColor: Colors.surface, borderWidth: 2, borderColor: Colors.primary, justifyContent: 'center', alignItems: 'center', ...Shadows.small },
  markerPinSelected: { backgroundColor: Colors.primary, borderColor: Colors.textOnPrimary, ...Shadows.glow },
  markerArrow: { width: 0, height: 0, borderLeftWidth: 6, borderRightWidth: 6, borderTopWidth: 8, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: Colors.primary, alignSelf: 'center', marginTop: -2 },
  markerArrowSelected: { borderTopColor: Colors.textOnPrimary },

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
  const [locationStatus, setLocationStatus] = useState<'loading' | 'granted' | 'denied'>('loading');
  const [userLocation, setUserLocation] = useState<{ latitude: number; longitude: number } | null>(null);
  const [markets, setMarkets] = useState<NearMarketResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [focusedIndex, setFocusedIndex] = useState(0);

  const initMapData = async () => {
    try {
      setLoading(true);
      setLocationStatus('loading');
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setLocationStatus('denied');
        setLoading(false);
        return;
      }

      setLocationStatus('granted');
      const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const coords = { latitude: loc.coords.latitude, longitude: loc.coords.longitude };
      setUserLocation(coords);

      const nearbyMarkets = await getNearMarkets(coords.latitude, coords.longitude, 10);
      setMarkets(nearbyMarkets);

      if (mapRef.current && nearbyMarkets.length > 0) {
        setTimeout(() => {
          mapRef.current?.animateToRegion({
            latitude: nearbyMarkets[0].latitude,
            longitude: nearbyMarkets[0].longitude,
            latitudeDelta: 0.02,
            longitudeDelta: 0.02,
          }, 500);
        }, 500);
      } else if (mapRef.current) {
        setTimeout(() => {
          mapRef.current?.animateToRegion({
            ...coords,
            latitudeDelta: 0.02,
            longitudeDelta: 0.02,
          }, 500);
        }, 500);
      }
    } catch (err) {
      console.error('Map load failed:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    initMapData();
  }, []);

  const onScroll = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const offsetX = event.nativeEvent.contentOffset.x;
    const index = Math.round(offsetX / SNAP_INTERVAL);
    if (index !== focusedIndex && index >= 0 && index < markets.length) {
      setFocusedIndex(index);
      const market = markets[index];
      mapRef.current?.animateToRegion({
        latitude: market.latitude,
        longitude: market.longitude,
        latitudeDelta: 0.02,
        longitudeDelta: 0.02,
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

  if (locationStatus === 'denied') {
    return (
      <View style={styles.deniedContainer}>
        <Ionicons name="location-outline" size={64} color={Colors.error} />
        <Text style={styles.deniedTitle}>{t('map.requires_location', 'Location Required')}</Text>
        <Text style={styles.deniedText}>
          {t('map.location_desc', 'Please enable location services to find nearby markets.')}
        </Text>
        <TouchableOpacity style={styles.settingsBtn} onPress={handleOpenSettings}>
          <Text style={styles.settingsBtnText}>{t('map.open_settings', 'Open Settings')}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.retryBtn} onPress={initMapData}>
          <Text style={styles.retryBtnText}>{t('common.retry', 'Retry')}</Text>
        </TouchableOpacity>
      </View>
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
      >
        {markets.map((market, index) => {
          const isSelected = focusedIndex === index;
          return (
            <Marker
              key={market.id}
              coordinate={{ latitude: market.latitude, longitude: market.longitude }}
              onPress={() => handleMarkerPress(index)}
              zIndex={isSelected ? 10 : 1}
            >
              <View style={[styles.markerPin, isSelected && styles.markerPinSelected]}>
                <Ionicons name="storefront" size={20} color={isSelected ? Colors.textOnPrimary : Colors.primary} />
              </View>
              <View style={[styles.markerArrow, isSelected && styles.markerArrowSelected]} />
            </Marker>
          );
        })}
      </MapView>

      <SafeAreaView style={styles.titleBar} edges={['top']}>
        <View style={styles.titleContainer}>
          <Ionicons name="map" size={18} color={Colors.primary} />
          <Text style={styles.title}>{t('map.nearby_markets', 'Nearby Markets')}</Text>
          {markets.length > 0 && (
            <View style={styles.countBadge}>
              <Text style={styles.countText}>{markets.length}</Text>
            </View>
          )}
        </View>
      </SafeAreaView>

      <TouchableOpacity
        style={styles.recenterBtn}
        onPress={() => {
          if (userLocation) {
            mapRef.current?.animateToRegion({
              ...userLocation,
              latitudeDelta: 0.02,
              longitudeDelta: 0.02,
            }, 500);
          }
        }}
      >
        <Ionicons name="locate" size={22} color={Colors.primary} />
      </TouchableOpacity>

      {loading && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      )}

      {!loading && markets.length === 0 && (
        <View style={styles.emptyOverlay}>
          <View style={styles.emptyCard}>
            <Ionicons name="storefront-outline" size={40} color={Colors.textMuted} />
            <Text style={styles.emptyTitle}>{t('map.no_markets', 'No markets found')}</Text>
            <Text style={styles.emptyDesc}>{t('map.no_markets_desc', 'Try moving the map to another area.')}</Text>
          </View>
        </View>
      )}

      {!loading && markets.length > 0 && (
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
                    <Text style={styles.distanceText}>{item.distance_km} {t('common.km', 'km')}</Text>
                  </View>
                </View>
              </TouchableOpacity>
            )}
          />
        </View>
      )}
    </View>
  );

}
