/**
 * useLocation — Shared GPS hook for all location-dependent screens.
 *
 * Returns:
 *  - location: { latitude, longitude } | null
 *  - loading: true while requesting permission / getting position
 *  - denied: true if user denied location permission
 *  - refresh: function to retry getting location
 *
 * Usage:
 *   const { location, loading, denied, refresh } = useLocation();
 *   if (loading) return <LoadingSpinner />;
 *   if (denied) return <EnableLocationPrompt onRetry={refresh} />;
 *   // location is guaranteed non-null here
 */

import { useState, useEffect, useCallback } from 'react';
import * as Location from 'expo-location';

interface LocationState {
  location: { latitude: number; longitude: number } | null;
  loading: boolean;
  denied: boolean;
}

export function useLocation() {
  const [state, setState] = useState<LocationState>({
    location: null,
    loading: true,
    denied: false,
  });

  const refresh = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, denied: false }));
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setState({ location: null, loading: false, denied: true });
        return;
      }
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      setState({
        location: {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        },
        loading: false,
        denied: false,
      });
    } catch (error) {
      // GPS hardware failure — rare, treat as denied
      setState({ location: null, loading: false, denied: true });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { ...state, refresh };
}
