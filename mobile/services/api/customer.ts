/**
 * Lamba API — Customer
 */

import * as SecureStore from 'expo-secure-store';
import api from './client';

// ── Types ──────────────────────────────────────────────────────
export interface NearMarketResponse {
  id: string;
  merchant_id: string;
  name: string;
  name_ar?: string | null;
  name_en?: string | null;
  address: string;
  latitude: number;
  longitude: number;
  distance_km: number;
  phone: string | null;
  is_currently_open: boolean;
  is_manual_override: boolean;
  override_set_at: string | null;
  average_rating: number;
  total_reviews: number;
  created_at: string;
}

export interface CustomerItemResponse {
  id: string;
  market_item_id: string;
  name: string;
  name_ar?: string | null;
  name_en?: string | null;
  description: string | null;
  category: string;
  category_name_ar?: string | null;
  category_name_en?: string | null;
  image_url: string | null;
  stock_count: number;
  in_stock: boolean;
  price?: number | null;
}

export type MarketCatalogResponse = Record<string, CustomerItemResponse[]>;

export interface NearbyItemResponse {
  id: string;
  market_item_id: string;
  name: string;
  name_ar?: string | null;
  name_en?: string | null;
  price: number;
  market_id: string;
  market_name: string;
  market_name_ar?: string | null;
  market_name_en?: string | null;
  category_name?: string | null;
  category_name_ar?: string | null;
  category_name_en?: string | null;
  image_url?: string | null;
  is_in_stock: boolean;
}

export interface RatingCreateRequest {
  market_id: string;
  customer_id: string;
  score: number;
  review?: string;
  latitude: number;
  longitude: number;
}

export interface RatingCreateResponse {
  status: string;
  stored_at: string;
}

export interface RatingDetailResponse {
  id: string;
  customer_name: string;
  score: number;
  review: string | null;
  created_at: string;
}

export interface MarketRatingSummaryResponse {
  average_score: number;
  total_reviews_count: number;
  ratings: RatingDetailResponse[];
}

export interface ShopDetails {
  id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  phone: string | null;
  business_nature: string;
  operating_hours: Record<string, string> | null;
  employee_directory: string[] | null;
  is_currently_open: boolean;
  is_manual_override: boolean;
  override_set_at: string | null;
  average_rating: number;
  total_reviews: number;
}

export interface MarketItemDetailsResponse {
  id: string;
  item_id: string;
  name: string;
  name_ar?: string | null;
  name_en?: string | null;
  description: string | null;
  category: string;
  category_name_ar?: string | null;
  category_name_en?: string | null;
  image_url: string | null;
  images: string[];
  stock_count: number;
  price: number | null;
  in_stock: boolean;
  shop: ShopDetails;
}

export interface CategoryNode {
  id: string;
  name: string;
  name_ar?: string | null;
  name_en?: string | null;
  listing_type?: string | null;
  subcategories: CategoryNode[];
}

export interface AlertResponse {
  id: string;
  query_text: string;
  is_active: boolean;
  created_at: string;
  latitude: number;
  longitude: number;
}

export interface SearchHistoryEntry {
  id: string;
  query_text: string;
  search_type: string;
  result_count: number;
  created_at: string;
}

// ── Functions ──────────────────────────────────────────────────
export async function getNearMarkets(
  latitude: number, longitude: number, radiusKm: number = 5.0,
): Promise<NearMarketResponse[]> {
  const { data } = await api.get<NearMarketResponse[]>('/api/v1/customer/near-markets', {
    params: { latitude, longitude, radius_km: radiusKm },
  });
  return data;
}

export async function getNearbyItems(
  latitude: number, longitude: number, radiusKm: number = 15.0, limit: number = 12,
): Promise<NearbyItemResponse[]> {
  const { data } = await api.get<NearbyItemResponse[]>('/api/v1/customer/nearby-items', {
    params: { latitude, longitude, radius_km: radiusKm, limit },
  });
  return data;
}

export async function getMarketCatalog(marketId: string): Promise<MarketCatalogResponse> {
  const { data } = await api.get<MarketCatalogResponse>(`/api/v1/customer/market/${marketId}/items`);
  return data;
}

export async function submitMarketRating(data: RatingCreateRequest): Promise<RatingCreateResponse> {
  const { data: resp } = await api.post<RatingCreateResponse>('/api/v1/customer/rating', data);
  return resp;
}

export async function getMarketRatings(marketId: string): Promise<MarketRatingSummaryResponse> {
  const { data } = await api.get<MarketRatingSummaryResponse>(`/api/v1/customer/market/${marketId}/ratings`);
  return data;
}

export async function getMarketItemDetails(marketItemId: string): Promise<MarketItemDetailsResponse> {
  const { data } = await api.get<MarketItemDetailsResponse>(`/api/v1/customer/item/${marketItemId}`);
  return data;
}

export async function getCategories(): Promise<CategoryNode[]> {
  const { data } = await api.get<CategoryNode[]>('/api/v1/customer/categories');
  return data;
}

export async function getCustomerAlerts(userId: string): Promise<AlertResponse[]> {
  try {
    const { data } = await api.get<AlertResponse[]>('/api/v1/customer/alerts', {
      params: { user_id: userId },
    });
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}

export async function createSearchAlert(
  queryText: string, latitude: number, longitude: number,
): Promise<AlertResponse> {
  try {
    const { data } = await api.post<AlertResponse>('/api/v1/customer/alerts', {
      query_text: queryText, latitude, longitude,
    });
    return data;
  } catch {
    return {
      id: 'local-alert-' + Date.now(),
      query_text: queryText, latitude, longitude,
      is_active: true, created_at: new Date().toISOString(),
    };
  }
}

// ── Reports & account ─────────────────────────────────────────
export type ReportReason = 'restricted_item' | 'wrong_info' | 'offensive' | 'spam' | 'other';

/** Report a product listing. Resolves on success and when the user already reported it. */
export async function reportProduct(
  globalItemId: string, marketId: string | null, reason: ReportReason, details?: string,
): Promise<void> {
  await api.post('/api/v1/reports', {
    global_item_id: globalItemId, market_id: marketId, reason, details,
  });
}

/** Permanently delete the signed-in account (customer or merchant). */
export async function deleteAccount(): Promise<void> {
  await api.delete('/api/v1/account');
}

// ── Favorites (SecureStore) ────────────────────────────────────
const FAVORITES_KEY = 'lamba_favorites';

export async function getFavorites(): Promise<string[]> {
  try {
    const raw = await SecureStore.getItemAsync(FAVORITES_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

export async function saveFavorites(favs: string[]): Promise<void> {
  await SecureStore.setItemAsync(FAVORITES_KEY, JSON.stringify(favs));
}

export async function addFavorite(itemId: string): Promise<void> {
  const favs = await getFavorites();
  if (!favs.includes(itemId)) {
    favs.push(itemId);
    await saveFavorites(favs);
  }
}

export async function removeFavorite(itemId: string): Promise<void> {
  const favs = await getFavorites();
  await saveFavorites(favs.filter(id => id !== itemId));
}

export async function isFavorite(itemId: string): Promise<boolean> {
  const favs = await getFavorites();
  return favs.includes(itemId);
}

// ── Search History ─────────────────────────────────────────────
export async function getSearchHistory(userId: string, limit: number = 20): Promise<SearchHistoryEntry[]> {
  const { data } = await api.get<SearchHistoryEntry[]>('/api/v1/customer/search-history', {
    params: { user_id: userId, limit },
  });
  return data;
}

export async function addSearchHistory(
  userId: string, queryText: string, searchType: string = 'text', resultCount: number = 0,
): Promise<SearchHistoryEntry> {
  const { data } = await api.post<SearchHistoryEntry>('/api/v1/customer/search-history', {
    user_id: userId, query_text: queryText, search_type: searchType, result_count: resultCount,
  });
  return data;
}

export async function clearSearchHistory(userId: string): Promise<void> {
  await api.delete('/api/v1/customer/search-history', { params: { user_id: userId } });
}
