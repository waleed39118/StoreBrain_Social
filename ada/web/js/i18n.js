// Arabic-first bilingual UI. Switching language flips direction (RTL/LTR) instantly.
const dict = {
  ar: {
    app: 'أدا', tagline: 'مساعدتك الذكية في المتجر', loading: 'جارٍ التحميل…',
    nav_pos: 'نقطة البيع', nav_chat: 'اسأل أدا', nav_products: 'المنتجات', nav_dashboard: 'لوحة التحكم',
    nav_alerts: 'التنبيهات', nav_sales: 'المبيعات', nav_staff: 'الموظفون', nav_settings: 'الإعدادات',
    online: 'متصل', offline: 'غير متصل — البيع يعمل وسيُزامَن تلقائياً', pending_sync: 'بانتظار المزامنة: {n}',
    login_title: 'تسجيل الدخول', owner_tab: 'صاحب المحل', staff_tab: 'موظف', phone: 'رقم الجوال',
    send_code: 'أرسل رمز الدخول', code: 'رمز التحقق (6 أرقام)', verify: 'دخول', pin: 'الرمز السري (PIN)',
    code_sent: 'إذا كان الرقم مسجلاً فقد أُرسل الرمز برسالة SMS.', change_number: 'تغيير الرقم',
    resend: 'إعادة الإرسال', resend_in: 'إعادة الإرسال بعد {s} ث', first_setup: 'الإعداد لأول مرة',
    setup_code: 'رمز الإعداد (من شاشة التثبيت)', show_pairing: 'عرض رمز ربط هاتف الرسائل',
    pairing_help: 'ثبّت تطبيق «بوابة رسائل أدا» على هاتف أندرويد فيه شريحة، ثم امسح هذا الرمز. بعدها سجّل الدخول برقمك.',
    copy: 'نسخ', copied: 'تم النسخ ✓', logout: 'تسجيل الخروج', logout_all: 'الخروج من كل الأجهزة',
    search_products: 'ابحث بالاسم أو الباركود…', all: 'الكل', cart: 'السلة', cart_empty: 'السلة فارغة — امسح باركوداً أو اختر منتجاً',
    total: 'الإجمالي', checkout: 'إتمام البيع', cash: 'نقداً', card: 'بطاقة', transfer: 'تحويل', other: 'أخرى',
    clear_cart: 'إفراغ', scan_camera: 'مسح بالكاميرا', not_found_barcode: 'الباركود غير موجود: {c}',
    out_of_stock: 'نفد المخزون', in_stock: 'متوفر: {n}', sale_done: 'تم البيع ✓', sale_offline: 'تم البيع دون اتصال — ستُزامَن العملية تلقائياً',
    print_receipt: 'طباعة الإيصال', new_sale: 'بيع جديد', receipt: 'إيصال', receipt_no: 'رقم الإيصال',
    subtotal: 'المجموع قبل الضريبة', vat: 'ضريبة القيمة المضافة', vat_no: 'الرقم الضريبي', cashier: 'الكاشير',
    qty: 'الكمية', price: 'السعر', name: 'الاسم', sku: 'الرمز', barcode: 'الباركود', category: 'الفئة', stock: 'المخزون',
    cost: 'التكلفة', reorder_level: 'حد إعادة الطلب', lead_time: 'مدة التوريد (أيام)', expiry: 'تاريخ الانتهاء',
    name_ar: 'الاسم بالعربية', name_en: 'الاسم بالإنجليزية', condition: 'الحالة', active: 'نشط',
    add_product: 'إضافة منتج', edit_product: 'تعديل منتج', save: 'حفظ', cancel: 'إلغاء', saved: 'تم الحفظ ✓',
    restock: 'استلام بضاعة', restock_qty: 'الكمية المستلمة', import_excel: 'استيراد من Excel / CSV', download_template: 'تنزيل القالب',
    import_mode: 'طريقة الكمية', mode_set: 'جرد (استبدال الكمية)', mode_add: 'استلام (إضافة للكمية)',
    preview: 'معاينة', apply_import: 'تطبيق الاستيراد', skip_invalid: 'تجاهل الصفوف الخاطئة',
    import_summary: 'جديد: {c} • تحديث: {u} • متجاهل: {s}', import_errors: 'أخطاء ({n})', row: 'صف',
    unknown_cols: 'أعمدة غير معروفة (ستُتجاهل): {c}', choose_file: 'اختر ملفاً',
    chat_placeholder: 'اكتب سؤالك… مثل: كم باقي من الحليب؟', send: 'إرسال', hold_to_talk: 'تحدث', listening: 'أستمع…',
    speak_replies: 'قراءة الردود بصوت', chat_hello: 'أهلاً! أنا أدا. اسألني عن المخزون، أو قل «بيع 2 حليب»، أو «ماذا أطلب؟»',
    mic_denied: 'لا يمكن استخدام الميكروفون', voice_failed: 'تعذّر فهم التسجيل',
    today_revenue: 'مبيعات اليوم', today_sales: 'عدد العمليات', avg_ticket: 'متوسط الفاتورة', items_sold: 'القطع المباعة',
    low_stock: 'منتجات منخفضة', unread_alerts: 'تنبيهات جديدة', last7: 'آخر 7 أيام', top_today: 'الأكثر مبيعاً اليوم',
    reorder_list: 'قائمة إعادة الطلب', best_sellers: 'الأكثر مبيعاً (30 يوماً)', obsolete: 'منتجات راكدة', diversify: 'تنويع الفئات',
    order_qty: 'كمية الطلب', days_cover: 'أيام التغطية', est_cost: 'التكلفة التقديرية', units: 'الوحدات', revenue: 'الإيراد', trend: 'الاتجاه',
    nothing_here: 'لا شيء هنا بعد', mark_all_read: 'تعليم الكل كمقروء', mark_read: 'مقروء',
    staff_add: 'إضافة موظف', role: 'الصلاحية', manager: 'مدير', cashier_role: 'كاشير', owner: 'المالك',
    deactivate: 'إيقاف', activate: 'تفعيل', reset_pin: 'تغيير الرمز', my_sessions: 'أجهزتي المتصلة', this_device: 'هذا الجهاز', revoke: 'إلغاء',
    store_profile: 'بيانات المتجر', store_name: 'اسم المتجر', store_phone: 'هاتف المتجر', address: 'العنوان',
    tax_number: 'الرقم الضريبي', currency: 'العملة', tax_rate: 'نسبة الضريبة %', prices_include_tax: 'الأسعار شاملة الضريبة',
    timezone: 'المنطقة الزمنية', language: 'اللغة', receipt_footer: 'تذييل الإيصال',
    sms_phone: 'هاتف الرسائل (بوابة SMS)', gw_online: 'متصل ✓', gw_offline: 'غير متصل', last_seen: 'آخر ظهور',
    send_test_sms: 'إرسال رسالة اختبار', test_sms_sent: 'أُرسلت رسالة الاختبار إلى قائمة الانتظار',
    local_ai: 'الذكاء الاصطناعي المحلي', ai_on: 'يعمل على خادمك ✓', ai_off: 'غير مفعّل (تعمل أدا بالقواعد)', ai_unreachable: 'مفعّل لكن غير متاح الآن',
    backups: 'النسخ الاحتياطية', backup_now: 'نسخة احتياطية الآن', download: 'تنزيل',
    welcome_setup: 'مرحباً بك في أدا! لنجهّز متجرك في دقيقة.', load_demo: 'تحميل منتجات تجريبية للتجربة', finish_setup: 'ابدأ العمل',
    install_app: 'تثبيت التطبيق', update_ready: 'يتوفر تحديث جديد', reload: 'تحديث',
    scan_title: 'مسح الباركود', scan_hint: 'وجّه الكاميرا نحو الباركود', camera_denied: 'لا يمكن الوصول إلى الكاميرا',
    error_generic: 'حدث خطأ: {m}', offline_action: 'هذا الإجراء يحتاج اتصالاً بالإنترنت', confirm: 'تأكيد',
    history: 'سجل المبيعات', load_more: 'المزيد', channel_offline: 'دون اتصال', yes: 'نعم', no: 'لا',
  },
  en: {
    app: 'Ada', tagline: 'Your smart store assistant', loading: 'Loading…',
    nav_pos: 'Point of sale', nav_chat: 'Ask Ada', nav_products: 'Products', nav_dashboard: 'Dashboard',
    nav_alerts: 'Alerts', nav_sales: 'Sales', nav_staff: 'Staff', nav_settings: 'Settings',
    online: 'Online', offline: 'Offline — selling still works and will sync automatically', pending_sync: 'Waiting to sync: {n}',
    login_title: 'Sign in', owner_tab: 'Owner', staff_tab: 'Staff', phone: 'Mobile number',
    send_code: 'Send sign-in code', code: 'Verification code (6 digits)', verify: 'Sign in', pin: 'PIN',
    code_sent: 'If this number is registered, a code was sent by SMS.', change_number: 'Change number',
    resend: 'Resend', resend_in: 'Resend in {s}s', first_setup: 'First-time setup',
    setup_code: 'Setup code (from the install screen)', show_pairing: 'Show SMS-phone pairing code',
    pairing_help: 'Install the “Ada SMS Gateway” app on an Android phone with a SIM and scan this code. Then sign in with your number.',
    copy: 'Copy', copied: 'Copied ✓', logout: 'Sign out', logout_all: 'Sign out of all devices',
    search_products: 'Search by name or barcode…', all: 'All', cart: 'Cart', cart_empty: 'Cart is empty — scan a barcode or pick a product',
    total: 'Total', checkout: 'Complete sale', cash: 'Cash', card: 'Card', transfer: 'Transfer', other: 'Other',
    clear_cart: 'Clear', scan_camera: 'Scan with camera', not_found_barcode: 'Barcode not found: {c}',
    out_of_stock: 'Out of stock', in_stock: 'In stock: {n}', sale_done: 'Sale completed ✓', sale_offline: 'Sold offline — will sync automatically',
    print_receipt: 'Print receipt', new_sale: 'New sale', receipt: 'Receipt', receipt_no: 'Receipt no.',
    subtotal: 'Subtotal (excl. VAT)', vat: 'VAT', vat_no: 'VAT no.', cashier: 'Cashier',
    qty: 'Qty', price: 'Price', name: 'Name', sku: 'SKU', barcode: 'Barcode', category: 'Category', stock: 'Stock',
    cost: 'Cost', reorder_level: 'Reorder level', lead_time: 'Lead time (days)', expiry: 'Expiry date',
    name_ar: 'Arabic name', name_en: 'English name', condition: 'Condition', active: 'Active',
    add_product: 'Add product', edit_product: 'Edit product', save: 'Save', cancel: 'Cancel', saved: 'Saved ✓',
    restock: 'Receive stock', restock_qty: 'Quantity received', import_excel: 'Import from Excel / CSV', download_template: 'Download template',
    import_mode: 'Quantity mode', mode_set: 'Stock-take (replace quantity)', mode_add: 'Goods received (add to quantity)',
    preview: 'Preview', apply_import: 'Apply import', skip_invalid: 'Skip invalid rows',
    import_summary: 'New: {c} • Updated: {u} • Skipped: {s}', import_errors: 'Errors ({n})', row: 'Row',
    unknown_cols: 'Unknown columns (ignored): {c}', choose_file: 'Choose file',
    chat_placeholder: 'Ask anything… e.g. how many eggs are left?', send: 'Send', hold_to_talk: 'Talk', listening: 'Listening…',
    speak_replies: 'Read replies aloud', chat_hello: "Hi! I'm Ada. Ask me about stock, say “sell 2 milk”, or “what should I reorder?”",
    mic_denied: 'Microphone not available', voice_failed: 'Could not understand the recording',
    today_revenue: "Today's sales", today_sales: 'Transactions', avg_ticket: 'Average ticket', items_sold: 'Items sold',
    low_stock: 'Low-stock items', unread_alerts: 'New alerts', last7: 'Last 7 days', top_today: 'Top sellers today',
    reorder_list: 'Reorder list', best_sellers: 'Best sellers (30 days)', obsolete: 'Obsolete items', diversify: 'Category mix',
    order_qty: 'Order qty', days_cover: 'Days of cover', est_cost: 'Est. cost', units: 'Units', revenue: 'Revenue', trend: 'Trend',
    nothing_here: 'Nothing here yet', mark_all_read: 'Mark all read', mark_read: 'Read',
    staff_add: 'Add staff member', role: 'Role', manager: 'Manager', cashier_role: 'Cashier', owner: 'Owner',
    deactivate: 'Deactivate', activate: 'Activate', reset_pin: 'Change PIN', my_sessions: 'My signed-in devices', this_device: 'This device', revoke: 'Revoke',
    store_profile: 'Store profile', store_name: 'Store name', store_phone: 'Store phone', address: 'Address',
    tax_number: 'VAT number', currency: 'Currency', tax_rate: 'VAT rate %', prices_include_tax: 'Prices include VAT',
    timezone: 'Time zone', language: 'Language', receipt_footer: 'Receipt footer',
    sms_phone: 'SMS phone (gateway)', gw_online: 'Online ✓', gw_offline: 'Offline', last_seen: 'Last seen',
    send_test_sms: 'Send test SMS', test_sms_sent: 'Test SMS queued',
    local_ai: 'Local AI', ai_on: 'Running on your server ✓', ai_off: 'Disabled (Ada uses rules)', ai_unreachable: 'Enabled but unreachable',
    backups: 'Backups', backup_now: 'Back up now', download: 'Download',
    welcome_setup: "Welcome to Ada! Let's set up your store in a minute.", load_demo: 'Load sample products to try it out', finish_setup: 'Start working',
    install_app: 'Install app', update_ready: 'A new version is available', reload: 'Update',
    scan_title: 'Scan barcode', scan_hint: 'Point the camera at the barcode', camera_denied: 'Camera not available',
    error_generic: 'Error: {m}', offline_action: 'This action needs an internet connection', confirm: 'Confirm',
    history: 'Sales history', load_more: 'Load more', channel_offline: 'offline', yes: 'Yes', no: 'No',
  },
};

let lang = 'ar';
try { lang = localStorage.getItem('ada.lang') || (navigator.language?.startsWith('ar') ? 'ar' : 'ar'); } catch { /* ignore */ }

export function t(key, vars = {}) {
  const s = dict[lang][key] ?? dict.en[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '');
}
export const getLang = () => lang;
export function setLang(l) {
  lang = l === 'en' ? 'en' : 'ar';
  try { localStorage.setItem('ada.lang', lang); } catch { /* ignore */ }
  applyLang();
}
export function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  document.title = `${t('app')} — ${t('tagline')}`;
}
export const pname = (p) => (lang === 'ar' && p.name_ar) ? p.name_ar : p.name_en;
