/**
 * Shared Utilities — Common helpers used across multiple screens.
 * Avoids duplication of resolveImageUrl, distance calculations, etc.
 */

// ── Image URL Resolution ──────────────────────────────────────
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Resolve a potentially relative image URL to an absolute URL.
 * Returns undefined if url is null/empty.
 */
export const resolveImageUrl = (url: string | null | undefined): string | undefined => {
  if (!url) return undefined;
  if (url.startsWith('http')) return url;
  return `${API_BASE_URL}${url}`;
};

// ── Haversine Distance ────────────────────────────────────────
/**
 * Calculate the distance between two GPS coordinates in meters
 * using the Haversine formula.
 */
export const calculateDistanceMeters = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number => {
  const R = 6371e3; // Earth radius in meters
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const deltaPhi = ((lat2 - lat1) * Math.PI) / 180;
  const deltaLambda = ((lon2 - lon1) * Math.PI) / 180;

  const a =
    Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
    Math.cos(phi1) * Math.cos(phi2) *
    Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c;
};

// ── Distance Formatting ───────────────────────────────────────
/**
 * Format a distance in meters to a human-readable string.
 */
export const roundDistance = (meters: number, isAr: boolean): string => {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} ${isAr ? 'كم' : 'km'}`;
  }
  return `${Math.round(meters)} ${isAr ? 'متر' : 'm'}`;
};

// ── Relative Time Formatting ──────────────────────────────────
/**
 * Format a date string to a human-readable relative time.
 */
export const formatRelativeTime = (dateString: string, isAr: boolean): string => {
  const now = new Date();
  const date = new Date(dateString);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return isAr ? 'الآن' : 'Just now';
  if (diffMins < 60) return isAr ? `منذ ${diffMins} دقيقة` : `${diffMins}m ago`;
  if (diffHours < 24) return isAr ? `منذ ${diffHours} ساعة` : `${diffHours}h ago`;
  if (diffDays < 7) return isAr ? `منذ ${diffDays} يوم` : `${diffDays}d ago`;

  return date.toLocaleDateString(isAr ? 'ar-SA' : 'en-US', {
    month: 'short',
    day: 'numeric',
  });
};

// ── Dark Map Style ────────────────────────────────────────────
/**
 * Shared dark map style for react-native-maps.
 * Previously duplicated in search.tsx and map.tsx.
 */
export const darkMapStyle: any[] = [
  { elementType: 'geometry', stylers: [{ color: '#0A0A1A' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#8B83FF' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#0A0A1A' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#1A1A3E' }] },
  { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#2A2A4A' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#2A2A5A' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#12122A' }] },
  { featureType: 'poi', elementType: 'geometry', stylers: [{ color: '#12122A' }] },
  { featureType: 'poi', elementType: 'labels.text.fill', stylers: [{ color: '#666688' }] },
  { featureType: 'transit', elementType: 'geometry', stylers: [{ color: '#12122A' }] },
  { featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{ color: '#2A2A4A' }] },
];
