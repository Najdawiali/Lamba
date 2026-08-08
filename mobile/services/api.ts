/**
 * Lamba API Client
 * 
 * Centralized Axios client with JWT token management via SecureStore.
 * All API calls go through this client.
 */

import axios, { AxiosInstance } from 'axios';
import * as SecureStore from 'expo-secure-store';

// Dynamically resolve API URL based on environment variables (generated dynamically by launcher script)
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'lamba_token';
const USER_KEY = 'lamba_user';

// ── Axios Instance ─────────────────────────────────────────────
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request
api.interceptors.request.use(async (config) => {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch (err) {
    // Ignore locked keychain errors in background state
  }
  return config;
});

// Auto-clear token and redirect on 401 (expired/invalid token)
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      try {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        await SecureStore.deleteItemAsync(USER_KEY);
      } catch {
        // Ignore keychain lock exceptions
      }
    }
    return Promise.reject(error);
  }
);

// ── Token Management ───────────────────────────────────────────
export async function saveToken(token: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
  } catch (err) {
    // Ignore keychain lock exceptions
  }
}

export async function getToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch (err) {
    return null;
  }
}

export async function removeToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(USER_KEY);
  } catch (err) {
    // Ignore keychain lock exceptions
  }
}

export async function saveUser(user: any): Promise<void> {
  try {
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user));
  } catch (err) {
    // Ignore keychain lock exceptions
  }
}

export async function getUser(): Promise<any | null> {
  try {
    const raw = await SecureStore.getItemAsync(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    return null;
  }
}

// ── Types ──────────────────────────────────────────────────────
export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: 'customer' | 'merchant';
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserResponse;
}

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
  description: string | null;
  price: number | null;
  category: string | null;
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

// ── V1 Auth Types ──────────────────────────────────────────────
export interface SignUpRequest {
  email?: string;
  phone_number?: string;
  password: string;
  user_type: 'customer' | 'merchant';
}

export interface SignUpResponse {
  user_id: string;
  message: string;
  channel: 'email' | 'sms';
}

export interface VerifyRequest {
  user_id: string;
  verification_code: string;
}

export interface VerifyResponse {
  verified: boolean;
  message: string;
}

export interface SignInRequest {
  email_or_phone: string;
  password: string;
}

export interface SignInUserInfo {
  id: string;
  email: string | null;
  phone_number: string | null;
  full_name: string | null;
  user_type: 'customer' | 'merchant';
  verified: boolean;
  created_at: string;
}

export interface SignInResponse {
  access_token: string;
  token_type: string;
  user: SignInUserInfo;
}

// ── V1 Auth API ────────────────────────────────────────────────
export async function signUp(data: SignUpRequest): Promise<SignUpResponse> {
  const { data: resp } = await api.post<SignUpResponse>('/api/v1/auth/signup', data);
  return resp;
}

export async function verifyCode(data: VerifyRequest): Promise<VerifyResponse> {
  const { data: resp } = await api.post<VerifyResponse>('/api/v1/auth/verify', data);
  return resp;
}

export async function signIn(emailOrPhone: string, password: string): Promise<SignInResponse> {
  const { data } = await api.post<SignInResponse>('/api/v1/auth/signin', {
    email_or_phone: emailOrPhone,
    password,
  });
  await saveToken(data.access_token);
  await saveUser(data.user);
  return data;
}

// ── V1 Merchant Types ───────────────────────────────────────────
export interface MarketResponse {
  id: string;
  merchant_id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  business_nature?: string | null;
  operating_hours?: Record<string, string> | null;
  employee_directory?: string[] | null;
  is_currently_open: boolean;
  is_manual_override: boolean;
  override_set_at: string | null;
  created_at: string;
}

export interface CatalogItemMatch {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  image_url: string | null;
}

export interface ItemCheckResponse {
  exists: boolean;
  matches: CatalogItemMatch[];
}

export interface ItemLinkResponse {
  success: boolean;
  message: string;
  market_item_id: string;
  stock_count: number;
}

export interface MarketItemDashboardResponse {
  id: string; // market_item.id
  item_id: string; // global_item.id
  name: string;
  description: string | null;
  category: string | null;
  image_url: string | null;
  stock_count: number;
  in_stock: boolean;
  price?: number | null;
}

export interface BarcodeLookupResponse {
  exists_in_branch: boolean;
  market_item_id: string | null;
  global_item_id: string;
  name: string;
  category: string | null;
  image_url: string | null;
  price: number | null;
  stock_count: number | null;
  barcode: string;
}



// ── V1 Merchant API ─────────────────────────────────────────────
export async function getMyMarket(): Promise<MarketResponse> {
  const { data } = await api.get<MarketResponse>('/api/v1/merchant/market');
  return data;
}

export async function createMarket(
  name: string,
  address: string,
  latitude: number,
  longitude: number,
  options?: {
    business_nature?: string;
    operating_hours?: Record<string, string> | null;
    is_currently_open?: boolean;
  },
): Promise<MarketResponse> {
  const { data } = await api.post<MarketResponse>('/api/v1/merchant/market', {
    name, address, latitude, longitude,
    business_nature: options?.business_nature,
    operating_hours: options?.operating_hours ?? null,
    is_currently_open: options?.is_currently_open,
  });
  return data;
}

export async function getMarketItems(): Promise<MarketItemDashboardResponse[]> {
  const { data } = await api.get<MarketItemDashboardResponse[]>('/api/v1/merchant/market/items');
  return data;
}

export async function updateMarketStatus(isOpen: boolean | null, isManual: boolean): Promise<MarketResponse> {
  const { data } = await api.patch<MarketResponse>('/api/v1/merchant/market/status', {
    is_currently_open: isOpen,
    is_manual_override: isManual,
  });
  return data;
}

export async function toggleItemStock(itemId: string, inStock: boolean): Promise<MarketItemDashboardResponse> {
  const { data } = await api.patch<MarketItemDashboardResponse>(`/api/v1/merchant/market/items/${itemId}/stock`, {
    in_stock: inStock
  });
  return data;
}

export async function updateMarketItem(
  itemId: string,
  updates: { name?: string; stock_count?: number; price?: number }
): Promise<MarketItemDashboardResponse> {
  const { data } = await api.patch<MarketItemDashboardResponse>(`/api/v1/merchant/market/items/${itemId}`, updates);
  return data;
}

export async function checkItemName(itemName: string): Promise<ItemCheckResponse> {
  const { data } = await api.post<ItemCheckResponse>('/api/v1/merchant/items/check', {
    item_name: itemName
  });
  return data;
}

export async function linkExistingItem(itemId: string, marketId: string, stockCount: number): Promise<ItemLinkResponse> {
  const { data } = await api.post<ItemLinkResponse>('/api/v1/merchant/items/link', {
    item_id: itemId,
    market_id: marketId,
    stock_count: stockCount
  });
  return data;
}

export async function addNewItem(formData: FormData): Promise<ItemLinkResponse> {
  const { data } = await api.post<ItemLinkResponse>('/api/v1/merchant/items/new', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export interface CSVUploadResponse {
  success: boolean;
  created: number;
  linked: number;
  indexed: number;
  message: string;
}

export async function uploadItemsCSV(marketId: string, formData: FormData): Promise<CSVUploadResponse> {
  const { data } = await api.post<CSVUploadResponse>(
    `/api/v1/merchant/items/upload-csv/${marketId}`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

export async function lookupItemByBarcode(barcode: string): Promise<BarcodeLookupResponse> {
  const { data } = await api.get<BarcodeLookupResponse>(`/api/v1/merchant/market/item/barcode/${barcode}`);
  return data;
}

export async function getInventoryValue(): Promise<{ total_value: number }> {
  const { data } = await api.get<{ total_value: number }>('/api/v1/merchant/market/stats/value');
  return data;
}

export async function linkBarcodeToMarket(itemId: string, price: number, stock: number): Promise<any> {
  const market = await getMyMarket();
  const linkResp = await linkExistingItem(itemId, market.id, stock);
  if (price > 0) {
    await updateMarketItem(linkResp.market_item_id, { price });
  }
  return linkResp;
}


export async function logout(): Promise<void> {
  await removeToken();
}
export interface SearchFilters {
  max_distance_km?: number;
  business_nature?: string;
  category_id?: string;
  in_stock_only?: boolean;
  price_min?: number;
  price_max?: number;
  city?: string;
}

export interface CategoryNode {
  id: string;
  name: string;
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

// ── Search API ─────────────────────────────────────────────────
export async function textSearch(
  query: string, latitude: number, longitude: number,
  userId?: string, filters?: SearchFilters,
): Promise<SearchResponse & { search_mode: string; action: string | null }> {
  const body: Record<string, any> = {
    query_text: query,
    latitude,
    longitude,
  };
  if (userId) {
    body.user_id = userId;
  }
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
  const { data } = await api.post<{ found: boolean; action: string | null; search_mode: string; results: any[] }>('/api/v1/search/hybrid', body);

  const mappedResults: SearchResultItem[] = (data.results || []).map((item) => ({
    product_id: item.market_item_id,
    product_name: item.name || '',
    description: item.description,
    price: item.price,
    category: item.category,
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
    suggestion: data.suggestion || null,
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
    if (filters.max_distance_km !== undefined) {
      formData.append('radius_km', filters.max_distance_km.toString());
    }
    if (filters.in_stock_only !== undefined) {
      formData.append('in_stock_only', filters.in_stock_only ? 'true' : 'false');
    }
    if (filters.price_min !== undefined) {
      formData.append('price_min', filters.price_min.toString());
    }
    if (filters.price_max !== undefined) {
      formData.append('price_max', filters.price_max.toString());
    }
    if (filters.business_nature !== undefined) {
      formData.append('business_nature', filters.business_nature);
    }
    if (filters.category_id !== undefined) {
      formData.append('category_id', filters.category_id);
    }
    if (filters.city !== undefined) {
      formData.append('city', filters.city);
    }
  }

  const { data } = await api.post<{ found: boolean; action: string | null; search_mode?: string; results: any[] }>('/api/v1/search/image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });

  const mappedResults: SearchResultItem[] = (data.results || []).map((item) => ({
    product_id: item.market_item_id,
    product_name: item.name,
    description: item.description,
    price: item.price,
    category: item.category,
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

// ── V1 Customer API ─────────────────────────────────────────────
export interface NearMarketResponse {
  id: string;
  merchant_id: string;
  name: string;
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
  description: string | null;
  category: string;
  image_url: string | null;
  stock_count: number;
  in_stock: boolean;
  price?: number | null;
}

export type MarketCatalogResponse = Record<string, CustomerItemResponse[]>;

export async function getNearMarkets(
  latitude: number,
  longitude: number,
  radiusKm: number = 5.0,
): Promise<NearMarketResponse[]> {
  const { data } = await api.get<NearMarketResponse[]>('/api/v1/customer/near-markets', {
    params: { latitude, longitude, radius_km: radiusKm },
  });
  return data;
}

export async function getMarketCatalog(marketId: string): Promise<MarketCatalogResponse> {
  const { data } = await api.get<MarketCatalogResponse>(`/api/v1/customer/market/${marketId}/items`);
  return data;
}

// ── V1 Ratings API ──────────────────────────────────────────────
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

export async function submitMarketRating(data: RatingCreateRequest): Promise<RatingCreateResponse> {
  const { data: resp } = await api.post<RatingCreateResponse>('/api/v1/customer/rating', data);
  return resp;
}

export async function getMarketRatings(marketId: string): Promise<MarketRatingSummaryResponse> {
  const { data } = await api.get<MarketRatingSummaryResponse>(`/api/v1/customer/market/${marketId}/ratings`);
  return data;
}

// Detailed single product item with operating hours, employee directory, nature, and secondary images
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
  description: string | null;
  category: string;
  image_url: string | null;
  images: string[];
  stock_count: number;
  price: number | null;
  in_stock: boolean;
  shop: ShopDetails;
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
      params: { user_id: userId }
    });
    return Array.isArray(data) ? data : [];
  } catch (err) {
    return [];
  }
}

export async function createSearchAlert(
  queryText: string,
  latitude: number,
  longitude: number,
): Promise<AlertResponse> {
  try {
    const { data } = await api.post<AlertResponse>('/api/v1/customer/alerts', {
      query_text: queryText,
      latitude,
      longitude,
    });
    return data;
  } catch (err) {
    // Graceful fallback for unbuilt POST endpoint
    return {
      id: 'local-alert-' + Date.now(),
      query_text: queryText,
      latitude,
      longitude,
      is_active: true,
      created_at: new Date().toISOString(),
    };
  }
}

const FAVORITES_KEY = 'lamba_favorites';

export async function getFavorites(): Promise<string[]> {
  try {
    const raw = await SecureStore.getItemAsync(FAVORITES_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (err) {
    console.error('Failed to parse persistent favorites:', err);
    return [];
  }
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
  const updated = favs.filter(id => id !== itemId);
  await saveFavorites(updated);
}

export async function isFavorite(itemId: string): Promise<boolean> {
  const favs = await getFavorites();
  return favs.includes(itemId);
}

// ── Special Offers API ──────────────────────────────────────────
export interface SpecialOfferCreateRequest {
  market_item_id: string;
  offer_type: 'BOGO' | 'DISCOUNT' | 'OTHER';
  discount_percentage?: number;
  description?: string;
}

export interface SpecialOfferUpdateRequest {
  is_active?: boolean;
  discount_percentage?: number;
  description?: string;
}

export interface SpecialOfferResponse {
  id: string;
  market_item_id: string;
  offer_type: string;
  discount_percentage: number | null;
  description: string | null;
  power: number;
  is_active: boolean;
  created_at: string;
  name: string;
  category: string | null;
  image_url: string | null;
  price: number | null;
  stock_count: number;
}

export interface CustomerSpecialOfferResponse {
  id: string;
  market_item_id: string;
  offer_type: string;
  discount_percentage: number | null;
  description: string | null;
  power: number;
  is_active: boolean;
  created_at: string;
  product_id: string;
  product_name: string;
  product_description: string | null;
  price: number | null;
  category: string | null;
  image_url: string | null;
  stock_count: number;
  in_stock: boolean;
  shop_id: string;
  shop_name: string;
  shop_address: string;
  latitude: number;
  longitude: number;
  shop_is_open: boolean;
  distance_km: number;
  sorting_score: number;
}

export async function getMerchantSpecialOffers(): Promise<SpecialOfferResponse[]> {
  const { data } = await api.get<SpecialOfferResponse[]>('/api/v1/merchant/offers');
  return data;
}

export async function createSpecialOffer(offer: SpecialOfferCreateRequest): Promise<SpecialOfferResponse> {
  const { data } = await api.post<SpecialOfferResponse>('/api/v1/merchant/offers', offer);
  return data;
}

export async function updateSpecialOffer(offerId: string, offer: SpecialOfferUpdateRequest): Promise<SpecialOfferResponse> {
  const { data } = await api.patch<SpecialOfferResponse>(`/api/v1/merchant/offers/${offerId}`, offer);
  return data;
}

export async function deleteSpecialOffer(offerId: string): Promise<{ message: string }> {
  const { data } = await api.delete<{ message: string }>(`/api/v1/merchant/offers/${offerId}`);
  return data;
}

export interface CustomerOffersFilters {
  query?: string;
  offer_type?: string;
  max_distance_km?: number;
  category_id?: string;
}

export async function getCustomerSpecialOffers(
  latitude: number,
  longitude: number,
  filters?: CustomerOffersFilters,
): Promise<CustomerSpecialOfferResponse[]> {
  try {
    const params: Record<string, any> = { latitude, longitude };
    if (filters) {
      if (filters.query) params.query = filters.query;
      if (filters.offer_type && filters.offer_type !== 'All') params.offer_type = filters.offer_type;
      if (filters.max_distance_km !== undefined) params.max_distance_km = filters.max_distance_km;
      if (filters.category_id) params.category_id = filters.category_id;
    }
    const { data } = await api.get<CustomerSpecialOfferResponse[]>('/api/v1/customer/offers', { params });
    return Array.isArray(data) ? data : [];
  } catch (err) {
    return [];
  }
}

// ── Chat API ──────────────────────────────────────────────────

export interface ChatSession {
  id: string;
  customer_id: string;
  market_id: string;
  created_at: string;
  updated_at: string;
  partner_name?: string;
  last_message?: string;
  unread_count?: number;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  sender_id: string;
  text: string;
  is_read: boolean;
  created_at: string;
}

export async function getChatSessions(): Promise<ChatSession[]> {
  try {
    const { data } = await api.get<ChatSession[]>('/chat/sessions');
    return Array.isArray(data) ? data : [];
  } catch (err) {
    return [];
  }
}

export async function startChatSession(marketId: string): Promise<ChatSession> {
  const { data } = await api.post<ChatSession>(`/chat/start/${marketId}`);
  return data;
}

export async function getChatMessages(sessionId: string): Promise<ChatMessage[]> {
  const { data } = await api.get<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`);
  return data;
}

export async function sendChatMessage(sessionId: string, text: string): Promise<ChatMessage> {
  const { data } = await api.post<ChatMessage>(`/chat/sessions/${sessionId}/messages`, { text });
  return data;
}

// ── POS Cashier API ───────────────────────────────────────────

export interface POSCheckoutItem {
  market_item_id: string;
  quantity: number;
}

export interface POSCheckoutResponse {
  success: boolean;
  total_cost: number;
  items: Array<{
    name: string;
    quantity: number;
    unit_price: number;
    subtotal: number;
  }>;
  alerts?: Array<{
    type: string;
    message: string;
  }>;
}

export interface HistoricalReceiptItem {
  name: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
}

export interface HistoricalReceipt {
  id: string;
  total_cost: number;
  created_at: string;
  items: HistoricalReceiptItem[];
}

export async function checkoutPOS(items: POSCheckoutItem[]): Promise<POSCheckoutResponse> {
  const { data } = await api.post<POSCheckoutResponse>('/api/v1/merchant/checkout', { items });
  return data;
}

export async function getCheckoutHistory(): Promise<HistoricalReceipt[]> {
  const { data } = await api.get<HistoricalReceipt[]>('/api/v1/merchant/checkout/history');
  return data;
}

// ── Search History API ─────────────────────────────────────────

export interface SearchHistoryEntry {
  id: string;
  query_text: string;
  search_type: string;
  result_count: number;
  created_at: string;
}

export async function getSearchHistory(userId: string, limit: number = 20): Promise<SearchHistoryEntry[]> {
  const { data } = await api.get<SearchHistoryEntry[]>('/api/v1/customer/search-history', {
    params: { user_id: userId, limit },
  });
  return data;
}

export async function addSearchHistory(
  userId: string,
  queryText: string,
  searchType: string = 'text',
  resultCount: number = 0
): Promise<SearchHistoryEntry> {
  // Identity (user_id) is taken from the JWT on the server, but we still send
  // it in the body for legacy clients; the body params beat long query strings.
  const { data } = await api.post<SearchHistoryEntry>(
    '/api/v1/customer/search-history',
    {
      user_id: userId,
      query_text: queryText,
      search_type: searchType,
      result_count: resultCount,
    },
  );
  return data;
}

export async function clearSearchHistory(userId: string): Promise<void> {
  await api.delete('/api/v1/customer/search-history', {
    params: { user_id: userId },
  });
}

export default api;

