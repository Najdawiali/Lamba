/**
 * Merchant Data Hooks
 *
 * useQuery / useMutation wrappers for merchant API calls.
 * Reused across: dashboard, profile, scanner, offers, add-product.
 *
 * Benefits over manual useState+useEffect:
 *  - Automatic loading/error/refetch states
 *  - Background refetch replaces manual setInterval
 *  - Cache invalidation on mutations (toggle stock → items + value refresh)
 *  - Deduplication (two components using useMarket() share one request)
 *  - Pull-to-refresh via refetch() instead of manual setRefreshing
 */

import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getMyMarket,
  getMarketItems,
  getInventoryValue,
  getCheckoutHistory,
  toggleItemStock,
  updateMarketItem,
  updateMarketStatus,
  getOffers,
  createOffer,
  updateOffer,
  deleteOffer,
  MarketResponse,
  MarketItemDashboardResponse,
  HistoricalReceipt,
  OfferResponse,
  OfferCreatePayload,
} from '../services/api';

// ── Query Keys (centralized to avoid typos) ────────────────────
export const merchantKeys = {
  market: ['merchant', 'market'] as const,
  items: ['merchant', 'items'] as const,
  inventoryValue: ['merchant', 'inventoryValue'] as const,
  checkoutHistory: ['merchant', 'checkoutHistory'] as const,
  offers: ['merchant', 'offers'] as const,
};

// ── Queries ────────────────────────────────────────────────────

/**
 * Fetch the merchant's market profile.
 *
 * Options:
 *  - refetchInterval: set to e.g. 15000 to poll for operating-hours status changes
 *  - enabled: false to defer fetching until a condition is met
 */
export function useMarket(options?: { refetchInterval?: number; enabled?: boolean }) {
  return useQuery<MarketResponse>({
    queryKey: merchantKeys.market,
    queryFn: getMyMarket,
    refetchInterval: options?.refetchInterval,
    enabled: options?.enabled,
    retry: (failureCount, error: any) => {
      // Don't retry on auth/not-found — these need navigation, not retries
      if ([401, 403, 404].includes(error?.response?.status)) return false;
      return failureCount < 2;
    },
  });
}

/**
 * Fetch the merchant's inventory items.
 */
export function useMarketItems(options?: { enabled?: boolean }) {
  return useQuery<MarketItemDashboardResponse[]>({
    queryKey: merchantKeys.items,
    queryFn: getMarketItems,
    enabled: options?.enabled,
  });
}

/**
 * Fetch total inventory valuation.
 */
export function useInventoryValue(options?: { enabled?: boolean }) {
  return useQuery<{ total_value: number }>({
    queryKey: merchantKeys.inventoryValue,
    queryFn: getInventoryValue,
    enabled: options?.enabled,
  });
}

/**
 * Fetch POS checkout history (last 14 days).
 */
export function useCheckoutHistory(options?: { enabled?: boolean }) {
  return useQuery<HistoricalReceipt[]>({
    queryKey: merchantKeys.checkoutHistory,
    queryFn: getCheckoutHistory,
    enabled: options?.enabled,
  });
}

// ── Mutations ──────────────────────────────────────────────────

/**
 * Toggle an item's in-stock status.
 * On success: directly patches the cached items list and invalidates inventory value.
 */
export function useToggleStock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, inStock }: { itemId: string; inStock: boolean }) =>
      toggleItemStock(itemId, inStock),
    onSuccess: (updatedItem) => {
      // Instantly update the cached list with the returned item
      queryClient.setQueryData<MarketItemDashboardResponse[]>(
        merchantKeys.items,
        (old) => old?.map(item => item.id === updatedItem.id ? updatedItem : item) ?? [],
      );
      queryClient.invalidateQueries({ queryKey: merchantKeys.inventoryValue });
    },
  });
}

/**
 * Update item details (name, stock_count, price).
 * On success: directly patches the cached items list and invalidates inventory value.
 */
export function useUpdateItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      itemId,
      updates,
    }: {
      itemId: string;
      updates: { name?: string; stock_count?: number; price?: number };
    }) => updateMarketItem(itemId, updates),
    onSuccess: (updatedItem) => {
      // Instantly update the cached list with the returned item
      queryClient.setQueryData<MarketItemDashboardResponse[]>(
        merchantKeys.items,
        (old) => old?.map(item => item.id === updatedItem.id ? updatedItem : item) ?? [],
      );
      queryClient.invalidateQueries({ queryKey: merchantKeys.inventoryValue });
    },
  });
}

/**
 * Refresh what the Stock tab and its totals show, for changes made outside those screens (the scanner links a
 * product, edits stock or price, uploads a photo, or finishes a sale). Without it the Stock tab keeps its
 * cached list: it is 30 s fresh, never refetched on tab focus, and the scanner has no mutation hook to patch it.
 * `{ sale: true }` also refreshes the sales history.
 */
export function useRefreshStock() {
  const queryClient = useQueryClient();
  return useCallback((options?: { sale?: boolean }) => {
    queryClient.invalidateQueries({ queryKey: merchantKeys.items });
    queryClient.invalidateQueries({ queryKey: merchantKeys.inventoryValue });
    if (options?.sale) queryClient.invalidateQueries({ queryKey: merchantKeys.checkoutHistory });
  }, [queryClient]);
}

/**
 * Toggle store open/closed status.
 * On success: invalidates market profile.
 */
export function useUpdateMarketStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ isOpen, isManual }: { isOpen: boolean | null; isManual: boolean }) =>
      updateMarketStatus(isOpen, isManual),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: merchantKeys.market });
    },
  });
}

// ── Offer Queries & Mutations ──────────────────────────────────

/** Fetch merchant's offers list. */
export function useOffers(options?: { enabled?: boolean }) {
  return useQuery<OfferResponse[]>({
    queryKey: merchantKeys.offers,
    queryFn: getOffers,
    enabled: options?.enabled,
  });
}

/** Create a new offer. Invalidates offer list on success. */
export function useCreateOffer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OfferCreatePayload) => createOffer(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: merchantKeys.offers });
    },
  });
}

/** Update an existing offer (toggle active, edit description/expiry). */
export function useUpdateOffer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, payload }: {
      offerId: string;
      payload: { is_active?: boolean; description?: string; expires_at?: string };
    }) => updateOffer(offerId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: merchantKeys.offers });
    },
  });
}

/** Delete an offer. Invalidates offer list on success. */
export function useDeleteOffer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (offerId: string) => deleteOffer(offerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: merchantKeys.offers });
    },
  });
}

