import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator,
  Alert, TextInput, Animated, Vibration, Platform, Dimensions, Image, FlatList, ScrollView, Keyboard, TouchableWithoutFeedback, KeyboardAvoidingView
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import {
  lookupItemByBarcode,
  linkBarcodeToMarket,
  updateMarketItem,
  uploadItemPhoto,
  checkoutPOS,
  getMarketItems,
  BarcodeLookupResponse,
  POSCheckoutItem,
  POSCheckoutResponse,
  MarketItemDashboardResponse,
  logout,
} from '../../services/api';
import { formatPrice } from '../../services/currency';
import { resolveImageUrl } from '../../services/utils';
import ReceiptModal from '../../components/ReceiptModal';
import ManualAddModal from '../../components/ManualAddModal';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const VIEWFINDER_SIZE = SCREEN_WIDTH * 0.7;

interface CartItem {
  global_item_id: string;
  market_item_id: string;
  name: string;
  barcode: string;
  price: number;
  quantity: number;
  image_url?: string | null;
}

export default function BarcodeScannerScreen() {
  const router = useRouter();
  const Colors = useThemeColors();

const styles = useMemo(() => StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#000' },
  
  // Real-time HUD banner overlay
  hudOverlay: {
    position: 'absolute',
    top: 130,
    left: Spacing.xl,
    right: Spacing.xl,
    backgroundColor: 'rgba(10, 200, 100, 0.95)',
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    zIndex: 10,
    ...Shadows.medium
  },
  hudText: {
    ...Typography.bodySmall,
    fontWeight: '700',
    color: '#FFF',
  },

  // Viewfinder Overlay Background Styling
  overlayBackground: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'space-between',
  },
  overlayTop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.65)',
    justifyContent: 'center',
  },
  headerSafeArea: { width: '100%' },
  headerOverlay: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
  },
  headerBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.08)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#FFF',
  },

  // Segmented Mode tabs control
  modeSegment: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderRadius: BorderRadius.md,
    padding: 2,
    flex: 1,
    marginHorizontal: Spacing.md,
  },
  modeTab: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: BorderRadius.sm,
  },
  modeTabActive: {
    backgroundColor: Colors.primary,
  },
  modeTabText: {
    ...Typography.caption,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.7)',
  },
  modeTabTextActive: {
    color: '#FFF',
  },

  // Viewfinder Middle Row
  overlayMid: {
    flexDirection: 'row',
    height: VIEWFINDER_SIZE,
  },
  overlaySide: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.65)',
  },
  viewfinder: {
    width: VIEWFINDER_SIZE,
    height: VIEWFINDER_SIZE,
    position: 'relative',
    overflow: 'hidden',
  },
  
  // Viewfinder Corners
  corner: {
    position: 'absolute',
    width: 24,
    height: 24,
    borderColor: Colors.primary,
  },
  cornerTL: { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4, borderTopLeftRadius: 12 },
  cornerTR: { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4, borderTopRightRadius: 12 },
  cornerBL: { bottom: 0, left: 0, borderBottomWidth: 4, borderLeftWidth: 4, borderBottomLeftRadius: 12 },
  cornerBR: { bottom: 0, right: 0, borderBottomWidth: 4, borderRightWidth: 4, borderBottomRightRadius: 12 },

  scannerLine: {
    position: 'absolute',
    left: 2,
    right: 2,
    height: 3,
    backgroundColor: Colors.secondary,
    shadowColor: Colors.secondary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 6,
    elevation: 4,
  },

  overlayBottom: {
    flex: 1.5,
    backgroundColor: 'rgba(0,0,0,0.65)',
    justifyContent: 'flex-start',
    alignItems: 'center',
    paddingTop: Spacing.xl,
  },
  helperText: {
    ...Typography.bodySmall,
    color: 'rgba(255,255,255,0.6)',
    textAlign: 'center',
    paddingHorizontal: Spacing.xl,
  },

  // POS Bottom Summary Bar Styling
  summaryBar: {
    position: 'absolute',
    bottom: 30,
    left: Spacing.lg,
    right: Spacing.lg,
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.lg,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: Spacing.lg,
    ...Shadows.large,
    zIndex: 9,
  },
  summaryInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  cartCountBadge: {
    backgroundColor: '#FFF',
    borderRadius: 12,
    minWidth: 24,
    height: 24,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  cartCountText: {
    fontSize: 12,
    fontWeight: '700',
    color: Colors.primary,
  },
  summaryLabel: {
    ...Typography.body,
    fontWeight: '700',
    color: '#FFF',
  },
  summaryAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  summaryTotal: {
    ...Typography.h3,
    color: '#FFF',
  },

  // Glassmorphic Drawer
  drawerContainer: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(10, 10, 26, 0.95)',
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    paddingBottom: Spacing.xl,
    zIndex: 11,
    ...Shadows.large,
  },
  drawerContent: {
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.sm,
    alignItems: 'center',
  },
  notchWrapper: {
    width: '100%',
    alignItems: 'center',
    paddingVertical: Spacing.xs,
    marginBottom: Spacing.sm,
  },
  notch: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },

  loadingWrapper: {
    paddingVertical: Spacing.xxl,
    alignItems: 'center',
  },
  loadingText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: Spacing.md,
  },

  // Single Item details summary card (Inventory Mode)
  itemSummaryCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    width: '100%',
    marginBottom: Spacing.md,
  },
  thumbWrapper: {
    width: 60,
    height: 60,
    borderRadius: BorderRadius.sm,
    overflow: 'hidden',
    backgroundColor: Colors.surface,
  },
  thumbnail: {
    width: '100%',
    height: '100%',
  },
  placeholderIcon: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  summaryText: {
    flex: 1,
    marginHorizontal: Spacing.md,
  },
  itemName: {
    ...Typography.body,
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  itemCategory: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: Spacing.xs,
    gap: 8,
  },
  badge: {
    paddingVertical: 2,
    paddingHorizontal: 6,
    borderRadius: BorderRadius.sm,
  },
  badgeSuccess: { backgroundColor: 'rgba(0, 217, 126, 0.12)' },
  badgeInfo: { backgroundColor: 'rgba(108, 99, 255, 0.12)' },
  badgeText: { fontSize: 10, fontWeight: '700' },
  badgeTextSuccess: { color: Colors.success },
  badgeTextInfo: { color: Colors.primary },
  barcodeText: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },

  // Configuration stock adjusters
  formContainer: {
    width: '100%',
  },
  formRow: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginBottom: Spacing.lg,
  },
  inputLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  adjusterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    height: 48,
    paddingHorizontal: Spacing.xs,
  },
  adjusterBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.05)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  adjusterInput: {
    flex: 1,
    color: Colors.textPrimary,
    ...Typography.body,
    fontWeight: '700',
  },
  priceInputWrapper: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    height: 48,
    justifyContent: 'center',
    paddingHorizontal: Spacing.md,
  },
  priceInput: {
    color: Colors.textPrimary,
    ...Typography.body,
    fontWeight: '700',
  },

  actionButtons: {
    flexDirection: 'row',
    gap: Spacing.sm,
    width: '100%',
  },
  btn: {
    height: 48,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    flexDirection: 'row',
  },
  btnCancel: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.06)',
  },
  btnSubmit: {
    flex: 2,
    backgroundColor: Colors.primary,
    ...Shadows.small,
  },
  btnTextCancel: {
    ...Typography.button,
    color: Colors.textSecondary,
  },
  btnTextSubmit: {
    ...Typography.button,
    color: '#FFF',
    fontWeight: '700',
  },

  // Unregistered alert layout
  unregisteredContainer: {
    alignItems: 'center',
    paddingVertical: Spacing.md,
    width: '100%',
  },
  alertIconBg: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: 'rgba(255, 77, 106, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  unregisteredTitle: {
    ...Typography.h2,
    color: Colors.error,
    marginBottom: Spacing.sm,
  },
  unregisteredDesc: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    textAlign: 'center',
    paddingHorizontal: Spacing.md,
    marginBottom: Spacing.lg,
    lineHeight: 18,
  },

  // ── POS Transaction styles ──
  posHeader: {
    flexDirection: 'row',
    width: '100%',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.05)',
    paddingBottom: Spacing.sm,
  },
  posTitle: {
    ...Typography.h3,
    color: Colors.textPrimary,
  },
  posClearText: {
    ...Typography.bodySmall,
    color: Colors.error,
    fontWeight: '600',
  },
  cartList: {
    width: '100%',
    maxHeight: 220,
  },
  cartItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.03)',
    width: '100%',
  },
  cartItemText: {
    flex: 1,
    marginRight: Spacing.md,
  },
  cartItemName: {
    ...Typography.bodySmall,
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  cartItemSub: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
  },
  cartItemActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  cartQtyBtn: {
    padding: 4,
  },
  cartQtyVal: {
    color: Colors.textPrimary,
    fontWeight: '700',
    minWidth: 20,
    textAlign: 'center',
  },
  cartDeleteBtn: {
    padding: 4,
    marginLeft: 8,
  },
  receiptSummary: {
    width: '100%',
    backgroundColor: 'rgba(255,255,255,0.02)',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginVertical: Spacing.md,
  },
  receiptRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 2,
  },
  receiptLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  receiptValue: {
    ...Typography.caption,
    color: Colors.textPrimary,
    fontWeight: '600',
  },
  receiptRowDivider: {
    height: 1,
    backgroundColor: 'rgba(255,255,255,0.06)',
    marginVertical: Spacing.xs,
  },
  receiptRowTotal: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 2,
  },
  receiptTotalLabel: {
    ...Typography.bodySmall,
    color: Colors.textPrimary,
    fontWeight: '700',
  },
  receiptTotalValue: {
    ...Typography.h3,
    color: Colors.secondary,
  },

  permissionContainer: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center' },
  permissionContent: { alignItems: 'center', padding: Spacing.xxl },
  permissionIconWrapper: {
    width: 120, height: 120, borderRadius: 60, backgroundColor: 'rgba(108, 99, 255, 0.1)',
    justifyContent: 'center', alignItems: 'center', marginBottom: Spacing.xl,
  },
  permissionTitle: { ...Typography.h2, color: Colors.textPrimary, marginBottom: Spacing.md },
  permissionSubtitle: {
    ...Typography.body, color: Colors.textSecondary, textAlign: 'center',
    lineHeight: 20, marginBottom: Spacing.xxl,
  },
  permissionBtn: {
    backgroundColor: Colors.primary, borderRadius: BorderRadius.md,
    paddingVertical: Spacing.md, paddingHorizontal: Spacing.xxl, ...Shadows.small,
  },
  permissionBtnText: { ...Typography.button, color: Colors.textOnPrimary },
  keyboardDismissBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(108, 99, 255, 0.15)',
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: 'rgba(108, 99, 255, 0.3)',
  },
  keyboardDismissText: {
    ...Typography.caption,
    fontWeight: '700',
    color: Colors.primary,
  },
  manualAddBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: Spacing.md,
    paddingVertical: 10,
    paddingHorizontal: Spacing.lg,
    borderRadius: BorderRadius.md,
    backgroundColor: 'rgba(255, 255, 255, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
  },
  manualAddBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFF',
  },
}), [Colors]);


  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [torch, setTorch] = useState(false);

  // Scanner Modes: 'cashier' (POS sale list) or 'inventory' (original stock/price edit)
  const [scannerMode, setScannerMode] = useState<'cashier' | 'inventory'>('cashier');

  // POS Cashier Cart States
  const [cartItems, setCartItems] = useState<CartItem[]>([]);
  const [showCartDrawer, setShowCartDrawer] = useState(false);
  const [checkingOut, setCheckingOut] = useState(false);
  const [hudMessage, setHudMessage] = useState<string | null>(null);

  // Original Inventory Bottom Sheet States
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [loadingApi, setLoadingApi] = useState(false);
  const [scannedBarcode, setScannedBarcode] = useState('');
  const [scanResult, setScanResult] = useState<BarcodeLookupResponse | null>(null);

  // Original Inventory Form inputs
  const [stockCount, setStockCount] = useState('0');
  const [price, setPrice] = useState('0.00');
  const [savingForm, setSavingForm] = useState(false);
  // Merchant-crowdsourced catalog photo: required when the product has none, optional otherwise
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const photoRequired = !!scanResult && !scanResult.image_url;
  const isArUI = !!i18n.locale?.startsWith('ar');
  const [keyboardVisible, setKeyboardVisible] = useState(false);

  // Continuous scanning synchronous lock to prevent multiple triggers in parallel frames
  const isScanningRef = useRef(false);

  // Professional Invoice/Receipt Screen States
  const [lastReceipt, setLastReceipt] = useState<POSCheckoutResponse | null>(null);
  const [receiptVisible, setReceiptVisible] = useState(false);

  // Manual Add States
  const [manualAddVisible, setManualAddVisible] = useState(false);
  const [inventoryItems, setInventoryItems] = useState<MarketItemDashboardResponse[]>([]);
  const [inventoryLoading, setInventoryLoading] = useState(false);

  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    
    const showSubscription = Keyboard.addListener(showEvent, () => setKeyboardVisible(true));
    const hideSubscription = Keyboard.addListener(hideEvent, () => setKeyboardVisible(false));
    return () => {
      showSubscription.remove();
      hideSubscription.remove();
    };
  }, []);

  // Animations
  const scanLineAnim = useRef(new Animated.Value(0)).current;
  const drawerY = useRef(new Animated.Value(SCREEN_HEIGHT)).current;
  const cartDrawerY = useRef(new Animated.Value(SCREEN_HEIGHT)).current;

  const isAr = i18n.locale?.startsWith('ar');

  useEffect(() => {
    if (!permission) {
      requestPermission();
    }
  }, [permission]);

  // Viewfinder scanner line animation loop
  useEffect(() => {
    scanLineAnim.setValue(0);
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(scanLineAnim, {
          toValue: VIEWFINDER_SIZE - 4,
          duration: 2000,
          useNativeDriver: true,
        }),
        Animated.timing(scanLineAnim, {
          toValue: 0,
          duration: 2000,
          useNativeDriver: true,
        })
      ])
    );
    anim.start();
    return () => anim.stop();
  }, [scanLineAnim]);

  // Handle slide up/down original inventory drawer
  const animateDrawer = (visible: boolean) => {
    Animated.spring(drawerY, {
      toValue: visible ? 0 : SCREEN_HEIGHT,
      useNativeDriver: true,
      tension: 30,
      friction: 8,
    }).start(() => {
      setDrawerVisible(visible);
    });
  };

  // Handle slide up/down cart drawer
  const animateCartDrawer = (visible: boolean) => {
    Animated.spring(cartDrawerY, {
      toValue: visible ? 0 : SCREEN_HEIGHT,
      useNativeDriver: true,
      tension: 30,
      friction: 8,
    }).start(() => {
      setShowCartDrawer(visible);
    });
  };

  const handleBarcodeScanned = async ({ type, data }: { type: string; data: string }) => {
    // Synchronous mutex lock to avoid parallel multi-frame scan triggers (causing random item count)
    if (scanned || loadingApi || drawerVisible || isScanningRef.current) return;
    
    isScanningRef.current = true;

    if (scannerMode === 'inventory') {
      // ── Original Inventory Update Flow ──
      Vibration.vibrate(Platform.OS === 'ios' ? 15 : 60);
      setScanned(true);
      setScannedBarcode(data);
      setLoadingApi(true);
      animateDrawer(true);

      try {
        const result = await lookupItemByBarcode(data);
        setScanResult(result);
        
        if (result.exists_in_branch) {
          setStockCount(result.stock_count?.toString() || '0');
          setPrice(result.price?.toFixed(2) || '0.00');
        } else {
          setStockCount('10');
          setPrice('1.00');
        }
      } catch (err: any) {
        if (err?.response?.status === 404) {
          setScanResult(null);
        } else {
          Alert.alert(t('common.error', 'Connection Error'), t('scanner.failed_checking_product', 'Failed checking product barcode details.'));
          setScanned(false);
          isScanningRef.current = false;
          animateDrawer(false);
        }
      } finally {
        setLoadingApi(false);
      }
    } else {
      // ── Enhanced POS Cashier Flow ──
      setScanned(true);
      setLoadingApi(true);
      
      try {
        const result = await lookupItemByBarcode(data);
        if (result.exists_in_branch && result.market_item_id) {
          // Success: Product registered in branch
          Vibration.vibrate(30);
          
          setCartItems(prev => {
            const existing = prev.find(item => item.market_item_id === result.market_item_id);
            if (existing) {
              return prev.map(item =>
                item.market_item_id === result.market_item_id
                  ? { ...item, quantity: item.quantity + 1 }
                  : item
              );
            } else {
              return [...prev, {
                global_item_id: result.global_item_id,
                market_item_id: result.market_item_id!,
                name: result.name,
                barcode: result.barcode,
                price: result.price || 0.0,
                quantity: 1,
                image_url: result.image_url
              }];
            }
          });

          // Flash temporary HUD green notification
          setHudMessage(`+1 ${result.name} (${formatPrice(result.price)})`);
          setTimeout(() => setHudMessage(null), 1800);

          // Snappy cool-down before next automatic continuous scan
          setTimeout(() => {
            setScanned(false);
            isScanningRef.current = false;
          }, 1000);
        } else {
          // Failure: Product exists in catalog but not branch stock
          Vibration.vibrate([0, 80, 50, 80]);
          Alert.alert(
            t('scanner.not_stocked', 'Not Stocked'),
            t('scanner.not_stocked_desc', 'The product is not carrying stock or price in your branch. Switch to "Update Stock" mode to link it first.'),
            [{ text: t('common.ok', 'OK'), onPress: () => { setScanned(false); isScanningRef.current = false; } }]
          );
        }
      } catch (err: any) {
        Vibration.vibrate([0, 100, 100, 100]);
        if (err?.response?.status === 404) {
          Alert.alert(
            t('scanner.barcode_not_registered', 'Barcode Not Registered'),
            t('scanner.barcode_not_registered_desc', 'Barcode is not registered in the system. Switch to "Update Stock" to ingestion check this brand new item.').replace('{{barcode}}', data),
            [{ text: t('common.ok', 'OK'), onPress: () => { setScanned(false); isScanningRef.current = false; } }]
          );
        } else {
          Alert.alert(t('common.error', 'Connection Error'), t('scanner.failed_checking_product', 'Failed checking product.'), [{ text: t('common.ok', 'OK'), onPress: () => { setScanned(false); isScanningRef.current = false; } }]);
        }
      } finally {
        setLoadingApi(false);
      }
    }
  };

  // Original Inventory stock adjuster
  const adjustStock = (delta: number) => {
    const currentVal = parseInt(stockCount, 10) || 0;
    const newVal = Math.max(0, currentVal + delta);
    setStockCount(newVal.toString());
  };

  // Save stock / price updates
  // Same camera / gallery chooser as add-product (reuses its translation keys)
  const pickProductPhoto = () => {
    Alert.alert(
      t('addProduct.select_image', 'Select Image'),
      t('addProduct.image_source', 'Choose image source'),
      [
        {
          text: t('addProduct.camera', 'Take Photo'),
          onPress: async () => {
            const { status } = await ImagePicker.requestCameraPermissionsAsync();
            if (status !== 'granted') {
              Alert.alert(t('common.error', 'Error'), t('addProduct.camera_permission', 'Camera permission is required'));
              return;
            }
            const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], allowsEditing: true, quality: 0.8 });
            if (!result.canceled && result.assets?.length > 0) setPhotoUri(result.assets[0].uri);
          },
        },
        {
          text: t('addProduct.gallery', 'Choose from Gallery'),
          onPress: async () => {
            const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, quality: 0.8 });
            if (!result.canceled && result.assets?.length > 0) setPhotoUri(result.assets[0].uri);
          },
        },
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
      ],
    );
  };

  const handleSave = async () => {
    if (!scannedBarcode) return;
    if (photoRequired && !photoUri) {
      Alert.alert(
        isArUI ? 'صورة المنتج مطلوبة' : 'Product photo required',
        isArUI ? 'هذا المنتج بلا صورة. التقط صورة له ليظهر بشكل واضح للزبائن.' : 'This product has no photo yet. Take one so customers can recognise it.',
      );
      return;
    }
    const stockVal = parseInt(stockCount, 10);
    const priceVal = parseFloat(price);

    if (isNaN(stockVal) || stockVal < 0) {
      Alert.alert(t('common.error'), t('dashboard.validation_error_stock', 'Please enter a valid stock count'));
      return;
    }
    if (isNaN(priceVal) || priceVal < 0) {
      Alert.alert(t('common.error'), t('dashboard.validation_error_price', 'Please enter a valid price'));
      return;
    }

    setSavingForm(true);
    try {
      if (scanResult?.exists_in_branch && scanResult.market_item_id) {
        await updateMarketItem(scanResult.market_item_id, {
          stock_count: stockVal,
          price: priceVal,
        });
      } else if (scanResult && !scanResult.exists_in_branch) {
        await linkBarcodeToMarket(scanResult.global_item_id, priceVal, stockVal);
      }
      // Photo after the stock is saved: the backend only accepts photos for stocked products.
      // If it fails, the stock stays saved and the next scan asks for the photo again.
      if (scanResult && photoUri) {
        try {
          await uploadItemPhoto(scanResult.global_item_id, photoUri);
        } catch {
          Alert.alert(
            isArUI ? 'تم الحفظ' : 'Saved',
            isArUI ? 'تم حفظ الكمية والسعر، لكن تعذّر رفع الصورة. امسح الباركود مرة أخرى لإضافتها.' : 'Stock and price were saved, but the photo could not be uploaded. Scan the barcode again to add it.',
          );
        }
      }
      Vibration.vibrate(50);
      handleCloseDrawer();
    } catch (err) {
      Alert.alert(t('common.error'), t('scanner.failed_save', 'Failed to save product adjustments.'));
    } finally {
      setSavingForm(false);
    }
  };

  const handleCloseDrawer = () => {
    animateDrawer(false);
    setTimeout(() => {
      setScanned(false);
      isScanningRef.current = false;
      setScanResult(null);
      setScannedBarcode('');
      setPhotoUri(null);
    }, 400);
  };

  // POS Cart Adjustments
  const adjustCartItemQty = (marketItemId: string, delta: number) => {
    setCartItems(prev =>
      prev.map(item => {
        if (item.market_item_id === marketItemId) {
          const newQty = Math.max(1, item.quantity + delta);
          return { ...item, quantity: newQty };
        }
        return item;
      })
    );
  };

  const removeCartItem = (marketItemId: string) => {
    setCartItems(prev => prev.filter(item => item.market_item_id !== marketItemId));
  };

  const calculateTotal = () => {
    return cartItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  };

  const handleCheckoutPOS = async () => {
    if (cartItems.length === 0 || checkingOut) return;
    setCheckingOut(true);

    try {
      const payload: POSCheckoutItem[] = cartItems.map(item => ({
        market_item_id: item.market_item_id,
        quantity: item.quantity
      }));

      const response = await checkoutPOS(payload);
      Vibration.vibrate([0, 40, 60, 40]);
      
      setLastReceipt(response);
      setReceiptVisible(true);
      
      setCartItems([]);
      animateCartDrawer(false);

      if (response.alerts && response.alerts.length > 0) {
        const alertMessages = response.alerts.map(a => a.message).join('\n');
        setTimeout(() => {
          Alert.alert(
            t('lowStock.title', 'Out of Stock Alert'),
            alertMessages,
            [{ text: t('common.ok', 'OK') }]
          );
        }, 600);
      }
    } catch (err: any) {
      if (err?.response?.status === 401) {
        console.warn('POS Checkout failed due to 401 Unauthorized. Logging out.');
        try {
          await logout();
        } catch (logoutErr) {
          // ignore
        }
        router.replace('/(auth)/gateway');
        return;
      }
      console.warn('POS Checkout failed:', err);
      Alert.alert(t('common.error', 'Error'), t('scanner.checkout_error', 'An error occurred during transaction checkout.'));
    } finally {
      setCheckingOut(false);
    }
  };

  const openManualAdd = async () => {
    setManualAddVisible(true);
    setInventoryLoading(true);
    try {
      const items = await getMarketItems();
      setInventoryItems(items.filter(i => i.in_stock));
    } catch (err) {
      console.warn('Failed to load inventory for manual add:', err);
    } finally {
      setInventoryLoading(false);
    }
  };

  const getItemCartQty = (marketItemId: string): number => {
    const item = cartItems.find(c => c.market_item_id === marketItemId);
    return item ? item.quantity : 0;
  };

  const handleIncrementManualItem = (item: MarketItemDashboardResponse) => {
    Vibration.vibrate(25);
    setCartItems(prev => {
      const existing = prev.find(c => c.market_item_id === item.id);
      if (existing) {
        return prev.map(c =>
          c.market_item_id === item.id
            ? { ...c, quantity: c.quantity + 1 }
            : c
        );
      } else {
        return [...prev, {
          global_item_id: item.item_id || item.id,
          market_item_id: item.id,
          name: item.name,
          barcode: '',
          price: item.price || 0,
          quantity: 1,
          image_url: item.image_url,
        }];
      }
    });

    setHudMessage(`+1 ${isAr ? (item.name_ar || item.name) : (item.name_en || item.name)} (${formatPrice(item.price)})`);
    setTimeout(() => setHudMessage(null), 1800);
  };

  const handleDecrementManualItem = (marketItemId: string) => {
    Vibration.vibrate(25);
    setCartItems(prev => {
      const existing = prev.find(c => c.market_item_id === marketItemId);
      if (!existing) return prev;
      if (existing.quantity <= 1) {
        return prev.filter(c => c.market_item_id !== marketItemId);
      }
      return prev.map(c =>
        c.market_item_id === marketItemId
          ? { ...c, quantity: c.quantity - 1 }
          : c
      );
    });
  };

  if (!permission) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permissionContainer}>
        <View style={styles.permissionContent}>
          <View style={styles.permissionIconWrapper}>
            <Ionicons name="camera-outline" size={60} color={Colors.primary} />
          </View>
          <Text style={styles.permissionTitle}>
            {t('scanner.camera_permission_required', 'Camera Permission Required')}
          </Text>
          <Text style={styles.permissionSubtitle}>
            {t('scanner.camera_permission_required_desc', 'We need camera access to scan product barcodes so you can quickly adjust and calculate inventory asset values.')}
          </Text>
          <TouchableOpacity style={styles.permissionBtn} onPress={requestPermission} activeOpacity={0.8}>
            <Text style={styles.permissionBtnText}>
              {t('scanner.request_permission', 'Grant Permission')}
            </Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        enableTorch={torch}
        barcodeScannerSettings={{
          barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code39', 'code128', 'itf14'],
        }}
        onBarcodeScanned={scanned ? undefined : handleBarcodeScanned}
      />

      {/* Real-time green scanning overlay HUD message */}
      {hudMessage && (
        <View style={styles.hudOverlay}>
          <Ionicons name="checkmark-circle" size={20} color={Colors.success} />
          <Text style={styles.hudText}>{hudMessage}</Text>
        </View>
      )}

      {/* Viewfinder Cutout Overlay */}
      <View style={styles.overlayBackground}>
        {/* Top Dark Bar containing Back and Torch controls */}
        <View style={styles.overlayTop}>
          <SafeAreaView style={styles.headerSafeArea} edges={['top']}>
            <View style={styles.headerOverlay}>
              <TouchableOpacity
                onPress={() => {
                  if (router.canGoBack()) {
                    router.back();
                  } else {
                    router.replace('/(merchant)/cashier');
                  }
                }}
                style={styles.headerBtn}
                activeOpacity={0.7}
              >
                <Ionicons name={isAr ? "arrow-forward" : "arrow-back"} size={24} color="#FFF" />
              </TouchableOpacity>
              
              {/* Segmented Mode Selector */}
              <View style={styles.modeSegment}>
                <TouchableOpacity 
                  style={[styles.modeTab, scannerMode === 'cashier' && styles.modeTabActive]} 
                  onPress={() => { setScannerMode('cashier'); setCartItems([]); }}
                  activeOpacity={0.8}
                >
                  <Text style={[styles.modeTabText, scannerMode === 'cashier' && styles.modeTabTextActive]}>
                    {t('scanner.pos_cashier', 'POS Cashier')}
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity 
                  style={[styles.modeTab, scannerMode === 'inventory' && styles.modeTabActive]} 
                  onPress={() => { setScannerMode('inventory'); animateCartDrawer(false); }}
                  activeOpacity={0.8}
                >
                  <Text style={[styles.modeTabText, scannerMode === 'inventory' && styles.modeTabTextActive]}>
                    {t('scanner.inventory', 'Inventory')}
                  </Text>
                </TouchableOpacity>
              </View>

              <TouchableOpacity onPress={() => setTorch(!torch)} style={styles.headerBtn} activeOpacity={0.7}>
                <Ionicons name={torch ? 'flash' : 'flash-off'} size={24} color={torch ? Colors.secondary : '#FFF'} />
              </TouchableOpacity>
            </View>
          </SafeAreaView>
        </View>

        {/* Viewfinder Mid Row */}
        <View style={styles.overlayMid}>
          <View style={styles.overlaySide} />
          
          <View style={styles.viewfinder}>
            <View style={[styles.corner, styles.cornerTL]} />
            <View style={[styles.corner, styles.cornerTR]} />
            <View style={[styles.corner, styles.cornerBL]} />
            <View style={[styles.corner, styles.cornerBR]} />

            {!scanned && (
              <Animated.View style={[
                styles.scannerLine,
                { transform: [{ translateY: scanLineAnim }] }
              ]} />
            )}
          </View>
          
          <View style={styles.overlaySide} />
        </View>

        {/* Bottom Dark Bar */}
        <View style={styles.overlayBottom}>
          <Text style={styles.helperText}>
            {scannerMode === 'cashier' 
              ? t('scanner.position_barcode', 'Position a barcode within the guide to scan.')
              : t('scanner.scan_inventory_instruction', 'Align barcode inside viewfinder to update stock')}
          </Text>

          {scannerMode === 'cashier' && (
            <TouchableOpacity
              style={styles.manualAddBtn}
              onPress={openManualAdd}
              activeOpacity={0.7}
            >
              <Ionicons name="search-outline" size={18} color="#FFF" />
              <Text style={styles.manualAddBtnText}>
                {t('scanner.manual_add', 'Manual Add')}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* POS Bottom Cashier Summary bar */}
      {scannerMode === 'cashier' && cartItems.length > 0 && !showCartDrawer && (
        <TouchableOpacity 
          style={styles.summaryBar} 
          onPress={() => animateCartDrawer(true)}
          activeOpacity={0.9}
        >
          <View style={styles.summaryInfo}>
            <View style={styles.cartCountBadge}>
              <Text style={styles.cartCountText}>{cartItems.reduce((a, b) => a + b.quantity, 0)}</Text>
            </View>
            <Text style={styles.summaryLabel}>{t('scanner.items', 'Scanned Items')}</Text>
          </View>
          <View style={styles.summaryAction}>
            <Text style={styles.summaryTotal}>{formatPrice(calculateTotal())}</Text>
            <Ionicons name="chevron-up" size={20} color="#FFF" />
          </View>
        </TouchableOpacity>
      )}

      <Animated.View style={[
        styles.drawerContainer,
        { transform: [{ translateY: drawerY }] }
      ]}>
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : undefined} 
          style={{ width: '100%' }}
        >
          <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
            <View style={styles.drawerContent}>
          <View style={[styles.notchWrapper, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
            <View style={{ width: 44 }} />
            <View style={styles.notch} />
            {keyboardVisible ? (
              <TouchableOpacity 
                onPress={() => Keyboard.dismiss()} 
                style={styles.keyboardDismissBtn}
                activeOpacity={0.7}
              >
                <Ionicons name="keypad-outline" size={20} color={Colors.primary} />
                <Text style={styles.keyboardDismissText}>{t('common.done', 'Done')}</Text>
              </TouchableOpacity>
            ) : (
              <View style={{ width: 44 }} />
            )}
          </View>

          {loadingApi ? (
            <View style={styles.loadingWrapper}>
              <ActivityIndicator size="large" color={Colors.primary} />
              <Text style={styles.loadingText}>{t('common.loading', 'Searching database...')}</Text>
            </View>
          ) : (
            <View style={{ width: '100%' }}>
              {scanResult ? (
                <View style={{ width: '100%' }}>
                  <View style={styles.itemSummaryCard}>
                    <TouchableOpacity
                      style={[styles.thumbWrapper, photoRequired && !photoUri ? { borderWidth: 2, borderColor: Colors.error, borderStyle: 'dashed' } : null]}
                      onPress={pickProductPhoto}
                      activeOpacity={0.7}
                      accessibilityLabel={isArUI ? 'إضافة صورة للمنتج' : 'Add product photo'}
                    >
                      {photoUri || scanResult.image_url ? (
                        <Image
                          source={{ uri: photoUri || resolveImageUrl(scanResult.image_url) }}
                          style={styles.thumbnail}
                          resizeMode="cover"
                        />
                      ) : (
                        <View style={styles.placeholderIcon}>
                          <Ionicons name="camera-outline" size={24} color={Colors.error} />
                        </View>
                      )}
                    </TouchableOpacity>

                    <View style={styles.summaryText}>
                      <Text style={styles.itemName} numberOfLines={1}>
                        {i18n.locale?.startsWith('ar') ? (scanResult.name_ar || scanResult.name) : (scanResult.name_en || scanResult.name)}
                      </Text>
                      <Text style={styles.itemCategory}>
                        {(i18n.locale?.startsWith('ar') ? (scanResult.category_name_ar || scanResult.category) : (scanResult.category_name_en || scanResult.category)) || t('common.general', 'General')}
                      </Text>
                      <View style={styles.badgeRow}>
                        <View style={[styles.badge, scanResult.exists_in_branch ? styles.badgeSuccess : styles.badgeInfo]}>
                          <Text style={[styles.badgeText, scanResult.exists_in_branch ? styles.badgeTextSuccess : styles.badgeTextInfo]}>
                            {scanResult.exists_in_branch 
                              ? t('inventory.in_stock', 'In My Store') 
                              : t('scanner.not_stocked', 'Not Carrying')}
                          </Text>
                        </View>
                        <Text style={styles.barcodeText}>EAN: {scanResult.barcode}</Text>
                      </View>
                    </View>
                  </View>

                  <Text
                    style={{
                      color: photoRequired && !photoUri ? Colors.error : Colors.textMuted,
                      fontSize: 12,
                      textAlign: isArUI ? 'right' : 'left',
                      marginTop: 6,
                    }}
                  >
                    {photoRequired && !photoUri
                      ? (isArUI ? 'هذا المنتج بلا صورة: اضغط على المربع والتقط صورة (مطلوب).' : 'This product has no photo: tap the box and take one (required).')
                      : photoUri
                        ? (isArUI ? 'سيتم رفع الصورة عند الحفظ.' : 'The photo will be uploaded when you save.')
                        : (isArUI ? 'اضغط على الصورة لإضافة صورة أخرى (اختياري).' : 'Tap the photo to add another one (optional).')}
                  </Text>

                  <View style={styles.formContainer}>
                    <View style={styles.formRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.inputLabel}>
                          {t('inventory.in_stock', 'Stock Quantity')}
                        </Text>
                        <View style={styles.adjusterRow}>
                          <TouchableOpacity style={styles.adjusterBtn} onPress={() => adjustStock(-1)} activeOpacity={0.7}>
                            <Ionicons name="remove" size={20} color={Colors.textPrimary} />
                          </TouchableOpacity>
                          <TextInput
                            style={styles.adjusterInput}
                            keyboardType="number-pad"
                            value={stockCount}
                            onChangeText={setStockCount}
                            textAlign="center"
                          />
                          <TouchableOpacity style={styles.adjusterBtn} onPress={() => adjustStock(1)} activeOpacity={0.7}>
                            <Ionicons name="add" size={20} color={Colors.textPrimary} />
                          </TouchableOpacity>
                        </View>
                      </View>

                      <View style={{ flex: 1 }}>
                        <Text style={styles.inputLabel}>
                          {t('merchant.price', 'Selling Price')}
                        </Text>
                        <View style={styles.priceInputWrapper}>
                          <TextInput
                            style={styles.priceInput}
                            keyboardType="decimal-pad"
                            value={price}
                            onChangeText={setPrice}
                          />
                        </View>
                      </View>
                    </View>

                    <View style={styles.actionButtons}>
                      <TouchableOpacity style={[styles.btn, styles.btnCancel]} onPress={handleCloseDrawer} activeOpacity={0.7}>
                        <Text style={styles.btnTextCancel}>{t('common.cancel', 'Cancel')}</Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={[styles.btn, styles.btnSubmit, (savingForm || (photoRequired && !photoUri)) ? { opacity: 0.5 } : null]}
                        onPress={handleSave}
                        disabled={savingForm || (photoRequired && !photoUri)}
                        activeOpacity={0.8}
                      >
                        {savingForm ? (
                          <ActivityIndicator size="small" color={Colors.textOnPrimary} />
                        ) : (
                          <Text style={styles.btnTextSubmit}>
                            {photoRequired && !photoUri
                              ? (isArUI ? 'التقط صورة أولاً' : 'Take a photo first')
                              : scanResult.exists_in_branch
                                ? t('common.save', 'Save Adjustments')
                                : t('addProduct.add_new', 'Add to My Store')}
                          </Text>
                        )}
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              ) : (
                <View style={styles.unregisteredContainer}>
                  <View style={styles.alertIconBg}>
                    <Ionicons name="barcode-outline" size={44} color={Colors.error} />
                  </View>
                  <Text style={styles.unregisteredTitle}>
                    {t('scanner.unregistered_product', 'Unregistered Product!')}
                  </Text>
                  <Text style={styles.unregisteredDesc}>
                    {t('scanner.barcode_not_found_desc', 'The scanned barcode was not found in the global product catalog. Would you like to register it as a new product in the catalog?').replace('{{barcode}}', scannedBarcode)}
                  </Text>

                  <View style={styles.actionButtons}>
                    <TouchableOpacity style={[styles.btn, styles.btnCancel, { flex: 1 }]} onPress={handleCloseDrawer} activeOpacity={0.7}>
                      <Text style={styles.btnTextCancel}>{t('common.cancel', 'Cancel')}</Text>
                    </TouchableOpacity>

                    <TouchableOpacity 
                      style={[styles.btn, styles.btnSubmit, { flex: 1.5, backgroundColor: Colors.error }]} 
                      activeOpacity={0.8}
                      onPress={() => {
                        handleCloseDrawer();
                        router.push({
                          pathname: '/(merchant)/add-product',
                          params: { initialBarcode: scannedBarcode }
                        });
                      }}
                    >
                      <Text style={styles.btnTextSubmit}>{t('scanner.ingest_new_item', 'Ingest New Item')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </View>
          )}
            </View>
          </TouchableWithoutFeedback>
        </KeyboardAvoidingView>
      </Animated.View>

      {/* ── DRAWER B: POS Cashier Transactions Drawer ── */}
      <Animated.View style={[
        styles.drawerContainer,
        { transform: [{ translateY: cartDrawerY }], maxHeight: SCREEN_HEIGHT * 0.8 }
      ]}>
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : undefined} 
          style={{ width: '100%' }}
        >
          <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
            <View style={styles.drawerContent}>
          <View style={[styles.notchWrapper, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
            <View style={{ width: 44 }} />
            <View style={styles.notch} />
            {keyboardVisible ? (
              <TouchableOpacity 
                onPress={() => Keyboard.dismiss()} 
                style={styles.keyboardDismissBtn}
                activeOpacity={0.7}
              >
                <Ionicons name="keypad-outline" size={20} color={Colors.primary} />
                <Text style={styles.keyboardDismissText}>{t('common.done', 'Done')}</Text>
              </TouchableOpacity>
            ) : (
              <View style={{ width: 44 }} />
            )}
          </View>

          <View style={styles.posHeader}>
            <Text style={styles.posTitle}>{t('scanner.pos_title', 'Active Receipt Checkout')}</Text>
            <TouchableOpacity 
              onPress={() => {
                Alert.alert(
                  t('scanner.reset_pos', 'Reset POS?'),
                  t('scanner.reset_pos_desc', 'Do you want to clear all items in this transaction?'),
                  [
                    { text: t('common.no', 'No') },
                    { text: t('common.yes_clear', 'Yes, Clear'), onPress: () => { setCartItems([]); animateCartDrawer(false); setScanned(false); isScanningRef.current = false; } }
                  ]
                );
              }}
            >
              <Text style={styles.posClearText}>{t('scanner.clear_cart', 'Clear All')}</Text>
            </TouchableOpacity>
          </View>

          <FlatList
            data={cartItems}
            keyExtractor={item => item.market_item_id}
            style={styles.cartList}
            contentContainerStyle={{ paddingBottom: Spacing.md }}
            renderItem={({ item }) => (
              <View style={styles.cartItemRow}>
                <View style={styles.cartItemText}>
                  <Text style={styles.cartItemName} numberOfLines={1}>{item.name}</Text>
                  <Text style={styles.cartItemSub}>{formatPrice(item.price)} × {item.quantity}</Text>
                </View>

                <View style={styles.cartItemActions}>
                  <TouchableOpacity style={styles.cartQtyBtn} onPress={() => adjustCartItemQty(item.market_item_id, -1)}>
                    <Ionicons name="remove-circle-outline" size={22} color={Colors.textPrimary} />
                  </TouchableOpacity>
                  <Text style={styles.cartQtyVal}>{item.quantity}</Text>
                  <TouchableOpacity style={styles.cartQtyBtn} onPress={() => adjustCartItemQty(item.market_item_id, 1)}>
                    <Ionicons name="add-circle-outline" size={22} color={Colors.textPrimary} />
                  </TouchableOpacity>

                  <TouchableOpacity style={styles.cartDeleteBtn} onPress={() => removeCartItem(item.market_item_id)}>
                    <Ionicons name="trash-outline" size={20} color={Colors.error} />
                  </TouchableOpacity>
                </View>
              </View>
            )}
          />

          <View style={styles.receiptSummary}>
            <View style={styles.receiptRow}>
              <Text style={styles.receiptLabel}>{t('scanner.subtotal', 'Subtotal')}</Text>
              <Text style={styles.receiptValue}>{formatPrice(calculateTotal())}</Text>
            </View>
            <View style={styles.receiptRow}>
              <Text style={styles.receiptLabel}>{t('scanner.taxes_inclusive', 'Taxes (Inclusive)')}</Text>
              <Text style={styles.receiptValue}>{formatPrice(0)}</Text>
            </View>
            <View style={styles.receiptRowDivider} />
            <View style={styles.receiptRowTotal}>
              <Text style={styles.receiptTotalLabel}>{t('scanner.total', 'Grand Total')}</Text>
              <Text style={styles.receiptTotalValue}>{formatPrice(calculateTotal())}</Text>
            </View>
          </View>

          <View style={styles.actionButtons}>
            <TouchableOpacity 
              style={[styles.btn, styles.btnCancel, { flex: 1 }]} 
              onPress={() => { animateCartDrawer(false); setScanned(false); }}
              disabled={checkingOut}
            >
              <Text style={styles.btnTextCancel}>{t('common.close', 'Close')}</Text>
            </TouchableOpacity>

            <TouchableOpacity 
              style={[styles.btn, styles.btnSubmit, { flex: 2, backgroundColor: Colors.success }]} 
              onPress={handleCheckoutPOS}
              disabled={checkingOut || cartItems.length === 0}
            >
              {checkingOut ? (
                <ActivityIndicator color={Colors.textOnPrimary} />
              ) : (
                <>
                  <Ionicons name="cash-outline" size={18} color={Colors.textOnPrimary} style={{ marginRight: 6 }} />
                  <Text style={styles.btnTextSubmit}>{t('scanner.checkout', 'Finalize Sale')}</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
            </View>
          </TouchableWithoutFeedback>
        </KeyboardAvoidingView>
      </Animated.View>

      {/* ── DRAWER C: Full Screen Professional Invoice Receipt Modal ── */}
      <ReceiptModal
        visible={receiptVisible}
        receipt={lastReceipt}
        onClose={() => {
          setReceiptVisible(false);
          setLastReceipt(null);
          setScanned(false);
          isScanningRef.current = false;
        }}
        onNewTransaction={() => {
          setReceiptVisible(false);
          setLastReceipt(null);
          setCartItems([]);
          setScanned(false);
          isScanningRef.current = false;
        }}
      />

      {/* Manual Add Search Modal */}
      <ManualAddModal
        visible={manualAddVisible}
        onClose={() => setManualAddVisible(false)}
        items={inventoryItems}
        loading={inventoryLoading}
        getCartQty={getItemCartQty}
        onIncrement={handleIncrementManualItem}
        onDecrement={handleDecrementManualItem}
        cartCount={cartItems.reduce((a, b) => a + b.quantity, 0)}
        cartTotal={calculateTotal()}
      />
    </View>
  );
}