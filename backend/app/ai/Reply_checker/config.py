"""
Tunable limits, required fields and word lists for the checker package.

Everything you may want to adjust without touching logic lives here (the big
complexity dictionaries are in dictionaries.py).
"""

from __future__ import annotations

MAX_TITLE_CHARS = 90
MAX_EXPLANATION_SENTENCES = 3
MAX_ACTION_SENTENCES = 2
MAX_WORDS_PER_SENTENCE = 25
MAX_LONG_WORD_SHARE = 0.10      # share of words with >= LONG_WORD_LETTERS letters
LONG_WORD_LETTERS = 12
MIN_ARABIC_SHARE = 0.60         # for lang="ar": Arabic letters / all letters
MAX_ARABIC_SHARE_EN = 0.10      # for lang="en"

COMPLEXITY_COFACTOR = 1.0
AR_COMPLEXITY_COFACTOR = 1.0
MAX_COMPLEXITY_RATING = 0.25
MAX_AR_COMPLEXITY_RATING = 0.25
 
REQUIRED_FIELDS = ("title", "explanation", "recommended_action")

BANNED_WORDS: dict[str, list[str]] = {
    "en": [
        "deauth", "deauthentication", "bssid", "ssid", "802.11", "packet",
        "probe request", "beacon", "channel", "signal strength", "rssi",
        "mac address", "frame",
        # --- 802.11 frames and identifiers ---
        "de-auth", "disassoc", "reassoc", "essid", "802.1x", "probe response",
        "association request", "sequence number", "monitor mode", "promiscuous",
        "mac-address", "wlan", "ieee", "dbm", "ghz", "mhz",
        # --- wireless security standards ---
        "wpa", "wep", "wps", "tkip", "ccmp", "psk", "eapol", "pmkid", "pmf",
        "handshake", "radius server",
        # --- network layers and protocols ---
        "tcp", "udp", "icmp", "dhcp", "dns", "arp", "vlan", "subnet",
        "ip address", "ssl", "tls", "gateway",  # gateway (borderline)
        # --- attack names and techniques ---
        "evil twin", "evil-twin", "rogue", "access point", "man-in-the-middle",
        "man in the middle", "mitm", "spoof", "sniff", "eavesdrop", "ddos",
        "brute force", "brute-force", "exploit", "zero-day", "cve",
        "reconnaissance", "captive portal", "cryptograph", "firmware",
        # --- tools and internal system names ---
        "wireshark", "pcap", "nmap", "esp32", "mqtt", "json",
    ],
    "ar": [
        # --- deauthentication / disassociation ---
        "فك المصادقة", "إلغاء المصادقة", "الغاء المصادقة", "فصل المصادقة",
        "إلغاء الارتباط", "الغاء الارتباط", "فك الارتباط",
        "إلغاء الاقتران", "الغاء الاقتران",
        # --- frames / packets (phrases only: bare "إطار"/"حزمة" are everyday words) ---
        "إطارات الإدارة", "إطارات الادارة", "إطار الإدارة", "إطار الادارة",
        "إطارات التحكم", "إطارات المصادقة", "إطارات الشبكة", "إطارات لاسلكية",
        "إطار لاسلكي", "إطار المنارة", "إطارات المنارة",
        "حزمة بيانات", "حزم بيانات", "حزم البيانات", "حزمة البيانات",
        "التقاط الحزم", "اعتراض الحزم", "تحليل الحزم",
        # --- access point / evil twin / man-in-the-middle ---
        "نقطة الوصول", "نقطة وصول", "نقاط الوصول", "نقاط وصول",
        "التوأم الشرير", "توأم شرير", "التوأم الخبيث", "توأم خبيث",
        "الرجل في المنتصف", "رجل في المنتصف", "الرجل الوسيط", "رجل وسيط",
        "هجوم الوسيط",
        # --- identifiers (translated and transliterated) ---
        "عنوان ماك", "عنوان الماك",
        "اس اس اي دي", "اس اس آي دي", "إس إس آي دي", "إس إس أي دي",
        "بي اس اس اي دي", "بي اس اس آي دي", "بي إس إس آي دي",
        # --- signal / channel / beacon / probe ---
        "قوة الإشارة", "قوة الاشارة", "قوه الاشارة",
        "قناة الواي فاي", "قناة الشبكة", "قناة لاسلكية", "رقم القناة",
        "بيكون", "بيكن", "إشارة المنارة", "إشارات المنارة",
        "طلب فحص", "استجابة فحص",
        "وضع المراقبة", "وضع الاستماع", "وضع عشوائي", "الوضع العشوائي",
        # --- security standards and protocols (transliterated) ---
        "دبليو بي إيه", "دبليو بي ايه", "دبليو بي أي", "وي بي إيه",
        "دبليو إي بي", "دبليو بي إس",
        "دي إن إس", "دي ان اس", "تي سي بي", "يو دي بي", "دي اتش سي بي",
        "في لان", "المصافحة الرباعية", "مصافحة رباعية",
        "حجب الخدمة", "رفض الخدمة", "ديدوس", "دي دوس",
        "البوابة المقيدة", "بوابة مقيدة",
        "برنامج ثابت", "البرنامج الثابت",
        "جيجاهرتز", "غيغاهرتز", "ميجاهرتز", "ميغاهرتز", "ديسيبل",
        # --- tools and internal system names ---
        "وايرشارك", "إم كيو تي تي", "ام كيو تي تي",
    ],
}
 
UNSAFE_PHRASES: dict[str, list[str]] = {
    "en": [
        # --- original list ---
        "hack back", "jam", "jamming", "jammed", "retaliate",
        "retaliating", "retaliation", "take revenge",
        "send disconnect", "track down", "confront the person",
        "disable your security", "turn off your firewall",
        # --- offence and retaliation ---
        "counterattack", "counter-attack", "counter attack",
        "strike back", "fight back", "hit back", "get revenge", "seek revenge",
        "get even", "pay them back", "teach them a lesson",
        "teach him a lesson", "teach her a lesson",
        "teach the person a lesson", "hack them", "hack him", "hack her",
        "hack their", "hack the attacker", "hire a hacker", "ddos",
        "flood their", "crack their",
        # --- tracking, confronting and exposing people ---
        "track them down", "track him down", "track her down", "hunt down",
        "find out who", "find the attacker", "find the person",
        "locate the attacker", "locate the person", "identify the attacker",
        "identify the person", "unmask", "stalk", "spy on",
        "confront them", "confront the attacker", "confront the owner",
        "confront whoever", "confront anyone", "accuse", "accusing",
        "threaten them", "threaten the person", "name and shame",
        "post their name", "publish their name", "expose their identity",
        # --- intruding on customers ---
        "check customers' phones", "check customers’ phones",
        "search customers", "search their phones", "go through their phones",
        "inspect their phones", "take their phones", "confiscate",
        # --- weakening the owner's own security ---
        "disable the firewall", "disable your firewall",
        "turn off the firewall", "switch off your firewall",
        "switch off the firewall", "disable your antivirus",
        "turn off your antivirus", "disable encryption", "turn off encryption",
        "disable the encryption", "turn off security", "disable security",
        "turn off the security", "disable the security", "switch off security",
        "turn off wifi security", "disable wifi security",
        "remove the password", "remove your password",
        "remove the wifi password", "remove your wifi password",
        "disable the password", "turn off the password",
        "make your network open", "make your wifi open",
        "leave your network open", "leave your wifi open",
        # --- asking for credentials / phishing-style instructions ---
        "send us your password", "give us your password",
        "enter your password here", "click the link", "click this link",
        "click here", "open the link", "follow this link",
        # --- commands and hacking tools ---
        "run this command", "run the following command", "type this command",
        "open a terminal", "open the terminal", "open command prompt",
        "open the command prompt", "use the command line", "sudo", "kali",
        "aircrack", "aireplay", "airodump", "metasploit", "wifiphisher",
        "hashcat", "mdk3", "mdk4", "reaver",
        # --- dismissing the alert / false assurance ---
        "ignore this alert", "ignore the alert", "ignore this warning",
        "ignore the warning", "safe to ignore", "you can ignore this",
        "just ignore", "100% safe", "completely safe", "totally safe",
        "fully protected", "completely protected", "guaranteed safe",
        "no danger at all",
        # --- claiming actions Prodos cannot take (it only observes and advises) ---
        "we have blocked", "we blocked", "we will block", "we are blocking",
        "we have stopped", "we stopped the", "we will stop the",
        "we have fixed", "we fixed", "we have removed", "we removed the",
        "we have disconnected", "we disconnected", "we took action",
        "we have taken action", "we are handling it",
    ],
    "ar": [
        # --- offence and retaliation ---
        "اهجم", "اهجموا", "قم بالهجوم", "قم بهجوم", "شن هجوم", "شن هجوما",
        "هجوم مضاد", "هجوما مضادا", "رد بهجوم",
        "انتقم", "انتقم منه", "انتقم منهم", "الانتقام", "خذ بثأرك",
        "خذ حقك بيدك", "رد الصاع", "رد بالمثل", "الرد بالمثل",
        "علمه درسا", "علمهم درسا", "لقنه درسا", "لقنهم درسا",
        "عاقبه", "عاقبهم",
        # --- jamming ---
        "جهاز تشويش", "أجهزة تشويش", "اجهزة تشويش", "جهاز التشويش",
        "أجهزة التشويش", "اجهزة التشويش", "التشويش على", "قم بالتشويش",
        "قم بتشويش", "احجب الإشارة", "احجب الاشارة",
        # --- hacking ---
        "قم باختراق", "قم بإختراق", "قم بالاختراق", "اختراق مضاد",
        "اختراق عكسي", "استأجر هاكر", "استاجر هاكر",
        # --- tracking, confronting and exposing people ---
        "تتبع الشخص", "تتبعه", "تتبعهم", "تعقبه", "تعقبهم", "تعقب الشخص",
        "ابحث عن المهاجم", "ابحث عن الشخص", "اعثر على المهاجم",
        "اعثر على الشخص", "حدد هوية المهاجم", "حدد هوية الشخص",
        "حدد موقع المهاجم", "حدد مكان المهاجم", "لاحقه", "لاحقهم", "طارده",
        "طاردهم", "واجه الشخص", "واجهه", "واجههم", "واجه المهاجم",
        "واجه صاحب", "اتهمه", "اتهمهم", "اتهم الشخص", "هدده", "هددهم",
        "تجسس عليه", "تجسس عليهم", "افضحه", "افضحهم", "اكشف هويته",
        "اكشف هويتهم", "انشر اسمه",
        # --- intruding on customers ---
        "فتش العملاء", "فتش الزبائن", "فتش هواتفهم", "افحص هواتف العملاء",
        "افحص هواتفهم", "صادر هواتفهم", "خذ هواتفهم",
        # --- weakening the owner's own security ---
        "عطل جدار الحماية", "أوقف جدار الحماية", "اوقف جدار الحماية",
        "أغلق جدار الحماية", "اغلق جدار الحماية", "أطفئ جدار الحماية",
        "اطفئ جدار الحماية", "عطل الحماية", "أوقف الحماية", "اوقف الحماية",
        "أطفئ الحماية", "اطفئ الحماية", "عطل التشفير", "أوقف التشفير",
        "اوقف التشفير", "عطل الأمان", "عطل الامان", "أوقف الأمان",
        "اوقف الامان", "احذف كلمة المرور", "ألغ كلمة المرور",
        "الغ كلمة المرور", "أزل كلمة المرور", "ازل كلمة المرور",
        "احذف كلمة السر", "اترك الشبكة مفتوحة", "اجعل الشبكة مفتوحة",
        # --- asking for credentials / phishing-style instructions ---
        "أرسل لنا كلمة المرور", "ارسل لنا كلمة المرور",
        "أرسل لنا كلمة السر", "ارسل لنا كلمة السر",
        "اعطنا كلمة المرور", "أعطنا كلمة المرور",
        "أدخل كلمة المرور هنا", "ادخل كلمة المرور هنا",
        "اضغط على الرابط", "اضغط هنا", "افتح الرابط",
        # --- commands and hacking tools ---
        "افتح موجه الأوامر", "افتح موجه الاوامر", "افتح سطر الأوامر",
        "افتح سطر الاوامر", "شغل الأمر التالي", "شغل الامر التالي",
        "نفذ الأمر التالي", "نفذ الامر التالي", "كالي لينكس", "ايركراك",
        "اير كراك", "ميتاسبلويت",
        # --- dismissing the alert / false assurance ---
        "تجاهل التنبيه", "تجاهل هذا التنبيه", "تجاهل التحذير",
        "تجاهل هذا التحذير", "آمن تماما", "آمنة تماما", "امن تماما",
        "امنة تماما", "محمي بالكامل", "محمية بالكامل",
        # --- claiming actions Prodos cannot take ---
        "قمنا بحظر", "قمنا بإيقاف", "قمنا بايقاف", "سنقوم بحظر",
        "سنقوم بإيقاف", "سنقوم بايقاف", "سنحظر", "حظرنا",
        "أوقفنا الهجوم", "اوقفنا الهجوم", "تم حظر المهاجم",
        "تم إيقاف الهجوم", "تم ايقاف الهجوم", "تم صد الهجوم",
    ],
}