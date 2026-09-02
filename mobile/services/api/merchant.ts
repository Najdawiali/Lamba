/**
 * Lamba API — Merchant
 */

import api from './client';
import { saveToken, saveUser, getUser } from './client';

// ── Types ──────────────────────────────────────────────────────
export interface MarketResponse {
  id: string;
  merchant_id: string;
  name: string;
  name_ar?: string | null;
  address: string;
  address_ar?: string | null;
  latitude: number;
  longitude: number;
  business_nature?: string | null;
  operating_hours?: Record<string, string> | null;
  employee_directory?: string[] | null;
  phone?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  employees?: string[];
  profile_edited_at?: string | null;
  name_edited_at?: string | null;
  address_edited_at?: string | null;
  is_name_locked?: boolean;
  is_address_locked?: boolean;
  is_profile_locked?: boolean;
  is_currently_open: boolean;
  is_manual_override: boolean;
  override_set_at: string | null;
  created_at: string;
  access_token?: string | null;
}

export interface MarketProfileResponse {
  name?: string;
  name_ar?: string;
  address?: string;
  address_ar?: string;
  contact_phone?: string;
  contact_email?: string;
  employees: string[];
  profile_edited_at?: string;
  name_edited_at?: string;
  address_edited_at?: string;
  is_name_locked: boolean;
  is_address_locked: boolean;
  is_profile_locked: boolean;
}

export interface MarketProfileUpdatePayload {
  name?: string;
  name_ar?: string;
  address?: string;
  address_ar?: string;
  contact_phone?: string;
  contact_email?: string;
}

export interface CatalogItemMatch {
  id: string;
  name: string;
  name_ar?: string | null;
  name_en?: string | null;
  description: string | null;
  category: string | null;
  category_name_ar?: string | null;
  category_name_en?: string | null;
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
  id: string;
  item_id: string;
  name: string;
  name_ar?: string | null;
  name_en?: string | null;
  description: string | null;
  category: string | null;
  category_name_ar?: string | null;
  category_name_en?: string | null;
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
  name_ar?: string | null;
  name_en?: string | null;
  category: string | null;
  category_name_ar?: string | null;
  category_name_en?: string | null;
  image_url: string | null;
  price: number | null;
  stock_count: number | null;
  barcode: string;
}

export interface CSVUploadResponse {
  success: boolean;
  created: number;
  linked: number;
  indexed: number;
  message: string;
}

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

// ── Functions ──────────────────────────────────────────────────
export async function getMyMarket(): Promise<MarketResponse> {
  const { data } = await api.get<MarketResponse>('/api/v1/merchant/market');
  return data;
}

export async function getMyStore(): Promise<MarketResponse | null> {
  try {
    const { data } = await api.get<MarketResponse>('/api/v1/merchant/market');
    return data;
  } catch (err: any) {
    return null;
  }
}

export async function createMarket(
  name: string,
  address: string,
  latitude: number,
  longitude: number,
  options?: {
    business_nature?: string;
    phone?: string;
    operating_hours?: Record<string, string> | null;
    is_currently_open?: boolean;
  },
): Promise<MarketResponse> {
  const { data } = await api.post<MarketResponse>('/api/v1/merchant/market', {
    name, address, latitude, longitude,
    business_nature: options?.business_nature,
    phone: options?.phone,
    operating_hours: options?.operating_hours ?? null,
    is_currently_open: options?.is_currently_open,
  });
  if (data.access_token) {
    await saveToken(data.access_token);
  }
  const currentUser = await getUser();
  if (currentUser) {
    const updatedUser = { ...currentUser, role: 'merchant', user_type: 'merchant' };
    await saveUser(updatedUser);
  }
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

export async function getMarketProfile(): Promise<MarketProfileResponse> {
  const { data } = await api.get<MarketProfileResponse>('/api/v1/merchant/market/profile');
  return data;
}

export async function updateMarketProfile(payload: MarketProfileUpdatePayload): Promise<MarketProfileResponse> {
  const { data } = await api.patch<MarketProfileResponse>('/api/v1/merchant/market/profile', payload);
  return data;
}

export async function updateEmployees(employees: string[]): Promise<MarketProfileResponse> {
  const { data } = await api.put<MarketProfileResponse>('/api/v1/merchant/market/employees', { employees });
  return data;
}

export async function toggleItemStock(itemId: string, inStock: boolean): Promise<MarketItemDashboardResponse> {
  const { data } = await api.patch<MarketItemDashboardResponse>(`/api/v1/merchant/market/items/${itemId}/stock`, {
    in_stock: inStock,
  });
  return data;
}

export async function updateMarketItem(
  itemId: string,
  updates: { name?: string; stock_count?: number; price?: number },
): Promise<MarketItemDashboardResponse> {
  const { data } = await api.patch<MarketItemDashboardResponse>(`/api/v1/merchant/market/items/${itemId}`, updates);
  return data;
}

export async function checkItemName(itemName: string): Promise<ItemCheckResponse> {
  const { data } = await api.post<ItemCheckResponse>('/api/v1/merchant/items/check', { item_name: itemName });
  return data;
}

export async function linkExistingItem(itemId: string, marketId: string, stockCount: number): Promise<ItemLinkResponse> {
  const { data } = await api.post<ItemLinkResponse>('/api/v1/merchant/items/link', {
    item_id: itemId,
    market_id: marketId,
    stock_count: stockCount,
  });
  return data;
}

export async function addNewItem(formData: FormData): Promise<ItemLinkResponse> {
  const { data } = await api.post<ItemLinkResponse>('/api/v1/merchant/items/new', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
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

export async function checkoutPOS(items: POSCheckoutItem[]): Promise<POSCheckoutResponse> {
  const { data } = await api.post<POSCheckoutResponse>('/api/v1/merchant/checkout', { items });
  return data;
}

export async function getCheckoutHistory(): Promise<HistoricalReceipt[]> {
  const { data } = await api.get<HistoricalReceipt[]>('/api/v1/merchant/checkout/history');
  return data;
}
