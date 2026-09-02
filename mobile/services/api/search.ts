/**
 * Lamba API — Search
 */

import api from './client';

// ── Types ──────────────────────────────────────────────────────
export interface ShopInfo {
  id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  phone: string | null;
  is_currently_open: boolean;
  is_manual_override?: boolean;
  override_set_at?: string | null;
}

export interface SearchResultItem {
  product_id: string;
  product_name: string;
  name_ar?: string | null;
  name_en?: string | null;
  description: string | null;
  price: number | null;
  category: string | null;
  category_name_ar?: string | null;
  category_name_en?: string | null;
  image_url: string | null;
  in_stock: boolean;
  shop: ShopInfo;
  distance_km: number;
  semantic_score: number;
  hybrid_score: number;
}

export interface SearchResponse {
  query: string | null;
  search_type: 'text' | 'image';
  radius_km: number;
  total_results: number;
  results: SearchResultItem[];
  suggestion?: string | null;
}

export interface ProductResponse {
  id: string;
  shop_id: string;
  name: string;
  description: string | null;
  price: number | null;
  category: string | null;
  image_url: string | null;
  in_stock: boolean;
  created_at: string;
  updated_at: string;
}

export interface SearchFilters {
  max_distance_km?: number;
  business_nature?: string;
  category_id?: string;
  in_stock_only?: boolean;
  price_min?: number;
  price_max?: number;
  city?: string;
  listing_type?: string | null;
}

// ── Functions ──────────────────────────────────────────────────
export async function textSearch(
  query: string, latitude: number, longitude: number,
  userId?: string, filters?: SearchFilters,
): Promise<SearchResponse & { search_mode: string; action: string | null }> {
  const body: Record<string, any> = { query_text: query, latitude, longitude };
  if (userId) body.user_id = userId;
  if (filters?.listing_type) body.listing_type = filters.listing_type;
  if (filters) {
    const f: Record<string, any> = {};
    if (filters.max_distance_km !== undefined) f.max_distance_km = filters.max_distance_km;
    if (filters.business_nature) f.business_nature = filters.business_nature;
    if (filters.category_id) f.category_id = filters.category_id;
    if (filters.in_stock_only !== undefined) f.in_stock_only = filters.in_stock_only;
    if (filters.price_min !== undefined) f.price_min = filters.price_min;
    if (filters.price_max !== undefined) f.price_max = filters.price_max;
    if (filters.city) f.city = filters.city;
    if (Object.keys(f).length > 0) body.filters = f;
  }

  const { data } = await api.post<{
    found: boolean; action: string | null; search_mode: string; results: any[];
  }>('/api/v1/search/hybrid', body);

  const mappedResults: SearchResultItem[] = (data.results || []).map((item) => ({
    product_id: item.market_item_id,
    product_name: item.name || '',
    name_ar: item.name_ar,
    name_en: item.name_en,
    description: item.description,
    price: item.price,
    category: item.category,
    category_name_ar: item.category_name_ar,
    category_name_en: item.category_name_en,
    image_url: item.image_url,
    in_stock: item.in_stock,
    shop: {
      id: item.market_id,
      name: item.market_name || 'Unknown Store',
      address: item.market_address || '',
      latitude: item.latitude || 0.0,
      longitude: item.longitude || 0.0,
      phone: null,
      is_currently_open: item.market_is_open ?? true,
    },
    distance_km: item.distance_km || 0.0,
    semantic_score: item.semantic_score || 0.0,
    hybrid_score: item.final_score || 0.0,
  }));

  return {
    query,
    search_type: 'text',
    radius_km: filters?.max_distance_km || 5.0,
    total_results: mappedResults.length,
    results: mappedResults,
    search_mode: data.search_mode || 'exact_matches',
    action: data.action || null,
    suggestion: (data as any).suggestion || null,
  };
}

export async function imageSearch(
  imageUri: string, latitude: number, longitude: number,
  filters?: SearchFilters, limit: number = 20,
): Promise<SearchResponse & { search_mode: string; action: string | null }> {
  const formData = new FormData();
  const filename = imageUri.split('/').pop() || 'photo.jpg';
  const match = /\.(\w+)$/.exec(filename);
  const type = match ? `image/${match[1]}` : 'image/jpeg';

  formData.append('image', { uri: imageUri, name: filename, type } as any);
  formData.append('latitude', latitude.toString());
  formData.append('longitude', longitude.toString());
  formData.append('limit', limit.toString());

  if (filters) {
    if (filters.max_distance_km !== undefined) formData.append('radius_km', filters.max_distance_km.toString());
    if (filters.in_stock_only !== undefined) formData.append('in_stock_only', filters.in_stock_only ? 'true' : 'false');
    if (filters.price_min !== undefined) formData.append('price_min', filters.price_min.toString());
    if (filters.price_max !== undefined) formData.append('price_max', filters.price_max.toString());
    if (filters.business_nature !== undefined) formData.append('business_nature', filters.business_nature);
    if (filters.category_id !== undefined) formData.append('category_id', filters.category_id);
    if (filters.city !== undefined) formData.append('city', filters.city);
  }

  const { data } = await api.post<{
    found: boolean; action: string | null; search_mode?: string; results: any[];
  }>('/api/v1/search/image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });

  const mappedResults: SearchResultItem[] = (data.results || []).map((item) => ({
    product_id: item.market_item_id,
    product_name: item.name,
    name_ar: item.name_ar,
    name_en: item.name_en,
    description: item.description,
    price: item.price,
    category: item.category,
    category_name_ar: item.category_name_ar,
    category_name_en: item.category_name_en,
    image_url: item.image_url,
    in_stock: item.in_stock,
    shop: {
      id: item.market_id,
      name: item.market_name,
      address: item.market_address,
      latitude: item.latitude,
      longitude: item.longitude,
      phone: null,
      is_currently_open: item.market_is_open,
    },
    distance_km: item.distance_km,
    semantic_score: item.semantic_score,
    hybrid_score: item.final_score,
  }));

  return {
    query: null,
    search_type: 'image',
    radius_km: filters?.max_distance_km || 5.0,
    total_results: mappedResults.length,
    results: mappedResults,
    search_mode: data.search_mode || 'exact_matches',
    action: data.action,
  };
}
