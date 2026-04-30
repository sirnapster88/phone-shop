import re
from collections import Counter


class SmartParser:
    """
    Универсальный парсер файлов прайс-листов.
    Логика:
    1. Читаем xlsx/xls/csv
    2. Ищем строки, где есть цена
    3. Собираем все остальные ячейки строки в product_text
    4. Разбираем product_text на brand / model / memory / color
    """

    BRAND_ALIASES = {
        "iphone": "iPhone",
        "apple": "Apple",
        "samsung": "Samsung",
        "xiaomi": "Xiaomi",
        "redmi": "Redmi",
        "poco": "Poco",
        "realme": "Realme",
        "oppo": "Oppo",
        "vivo": "Vivo",
        "oneplus": "OnePlus",
        "google": "Google",
        "pixel": "Pixel",
        "honor": "Honor",
        "huawei": "Huawei",
        "nothing": "Nothing",
        "motorola": "Motorola",
        "nokia": "Nokia",
        "sony": "Sony",
        "tecno": "Tecno",
        "infinix": "Infinix",
        "asus": "Asus",
        "lenovo": "Lenovo",
        "hp": "HP",
        "dell": "Dell",
        "msi": "MSI",
        "acer": "Acer",
        "macbook": "MacBook",
        "ipad": "iPad",
        "watch": "Watch",
        "airpods": "AirPods",
    }

    MEMORY_PATTERN = re.compile(
        r"(?<!\d)(32|64|128|256|512|1024|2048)\s*(tb|gb|гб|g)?(?!\d)",
        re.IGNORECASE,
    )


    MODEL_KEYWORDS = {
        "pro", "max", "plus", "mini", "ultra", "air", "lite", "note",
        "fe", "se", "fold", "flip", "prime", "turbo", "play", "book",
        "galaxy", "redmi", "poco", "pixel", "nord", "xperia", "mate",
        "nova", "magic", "pad", "tab",
    }

    NOISE_WORDS = {
        "шт", "нал", "внал", "цена", "price", "usd", "eur", "руб", "₽",
    }

    def __init__(self, file_path):
        self.file_path = file_path
        self.df = None
        self.file_brand = None

    @staticmethod
    def _get_pandas():
        import pandas as pd
        return pd

    @staticmethod
    def _is_missing(value):
        if value is None:
            return True
        try:
            return bool(SmartParser._get_pandas().isna(value))
        except Exception:
            return False

    def read_file(self):
        try:
            pd = self._get_pandas()
            lower = self.file_path.lower()

            if lower.endswith((".xlsx", ".xls")):
                self.df = pd.read_excel(self.file_path, header=None)
                return True

            for encoding in ("utf-8", "utf-8-sig", "cp1251"):
                for delimiter in (",", ";", "\t"):
                    try:
                        self.df = pd.read_csv(
                            self.file_path,
                            header=None,
                            delimiter=delimiter,
                            encoding=encoding,
                        )
                        return True
                    except Exception:
                        continue
        except Exception:
            return False

        return False

    def normalize_text(self, value):
        if self._is_missing(value):
            return ""
        text = str(value).replace("\xa0", " ").strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def normalize_price(self, value):
        if self._is_missing(value):
            return None

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)

        text = self.normalize_text(value)
        if not text:
            return None

        cleaned = re.sub(r"[^\d,.\s]", "", text).replace(" ", "")
        if not cleaned:
            return None

        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

        try:
            return float(cleaned)
        except Exception:
            digits = re.sub(r"[^\d]", "", cleaned)
            return float(digits) if digits else None

    def detect_file_brand(self):
        """
        Ищем бренд в верхних строках файла.
        Например:
        - отдельная ячейка "iPhone"
        - шапка/секция с названием бренда
        """
        found = []

        for row_idx in range(min(len(self.df), 10)):
            row = [self.normalize_text(x) for x in self.df.iloc[row_idx].tolist()]
            non_empty = [x for x in row if x]

            if not non_empty:
                continue

            if len(non_empty) == 1:
                cell = non_empty[0].lower()
                for alias, brand in self.BRAND_ALIASES.items():
                    if cell == alias:
                        return brand

            for cell in non_empty[:3]:
                lower_cell = cell.lower()
                for alias, brand in self.BRAND_ALIASES.items():
                    if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lower_cell):
                        found.append(brand)

        if found:
            return Counter(found).most_common(1)[0][0]
        return None

    def row_to_product_text_and_price(self, row):
        """
        Из строки берем:
        - одну наиболее похожую на цену ячейку
        - остальные непустые ячейки склеиваем в product_text
        """
        values = list(row)

        candidates = []
        for idx, cell in enumerate(values):
            price = self.normalize_price(cell)
            if price is not None:
                candidates.append((idx, price))

        if not candidates:
            return "", None

        price_idx, price = candidates[-1]

        parts = []
        for idx, cell in enumerate(values):
            if idx == price_idx:
                continue
            text = self.normalize_text(cell)
            if text:
                parts.append(text)

        product_text = " ".join(parts).strip()
        product_text = re.sub(r"\s+", " ", product_text)

        return product_text, price

    def extract_brand(self, text):
        lower = text.lower()

        for alias, brand in sorted(self.BRAND_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lower):
                new_text = re.sub(
                    rf"(?<!\w){re.escape(alias)}(?!\w)",
                    " ",
                    text,
                    count=1,
                    flags=re.IGNORECASE,
                )
                new_text = re.sub(r"\s+", " ", new_text).strip()
                return brand, new_text

        return "", text

    def extract_memory(self, text):
        """
        Ищем память не как первое число, а как наиболее вероятное значение памяти.
        Приоритет:
        1. число с явным суффиксом gb/tb/гб
        2. последнее подходящее число в строке
        """
        matches = list(self.MEMORY_PATTERN.finditer(text))
        if not matches:
            return "", text

        chosen = None

        # 1. Сначала ищем память с явным указанием единиц
        for match in matches:
            full = match.group(0).lower()
            if any(unit in full for unit in ("gb", "tb", "гб", "g")):
                chosen = match

        # 2. Если явных единиц нет, берем последнее подходящее число
        if chosen is None:
            chosen = matches[-1]

        memory = chosen.group(1)

        new_text = text[:chosen.start()] + " " + text[chosen.end():]
        new_text = re.sub(r"\s+", " ", new_text).strip()

        return memory, new_text


    def cleanup_tokens(self, text):
        text = re.sub(r"[^\w\s+/-]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return [t for t in text.split() if t]

    def normalize_token_case(self, token):
        special = {
            "pro": "Pro",
            "max": "Max",
            "plus": "Plus",
            "mini": "Mini",
            "ultra": "Ultra",
            "air": "Air",
            "lite": "Lite",
            "note": "Note",
            "fe": "FE",
            "se": "SE",
            "fold": "Fold",
            "flip": "Flip",
            "galaxy": "Galaxy",
            "pixel": "Pixel",
            "redmi": "Redmi",
            "poco": "Poco",
            "watch": "Watch",
            "macbook": "MacBook",
            "ipad": "iPad",
            "airpods": "AirPods",
            'aw': 'AW',
        }

        lower = token.lower()
        if token.isdigit():
            return token
        if lower in special:
            return special[lower]
        if len(token) <= 2 and token.isalpha():
            return token.upper()
        return token.capitalize()

    def split_model_and_color(self, text):
        """
        Цвет берем как остаток после модели.
        Модель определяем как начальную "содержательную" часть строки.
        """
        tokens = self.cleanup_tokens(text)
        if not tokens:
            return "", ""

        model_tokens = []
        color_tokens = []
        seen_number = False

        for i, token in enumerate(tokens):
            lower = token.lower()

            if lower in self.NOISE_WORDS:
                continue

            if color_tokens:
                color_tokens.append(token)
                continue

            token_has_digit = any(ch.isdigit() for ch in token)

            if i == 0:
                model_tokens.append(token)
                if token_has_digit:
                    seen_number = True
                continue

            if token_has_digit:
                model_tokens.append(token)
                seen_number = True
                continue

            if lower in self.MODEL_KEYWORDS:
                model_tokens.append(token)
                continue

            if seen_number and len(token) <= 2 and token.isalpha():
                model_tokens.append(token)
                continue

            color_tokens.append(token)

        if not model_tokens and tokens:
            model_tokens = [tokens[0]]
            color_tokens = tokens[1:]

        model = " ".join(self.normalize_token_case(t) for t in model_tokens).strip()
        color = " ".join(self.normalize_token_case(t) for t in color_tokens).strip()

        return model, color

    def parse_product_text(self, product_text):
        """
        На входе строка без цены.
        На выходе:
        - brand
        - model
        - memory
        - color
        """
        original = self.normalize_text(product_text)
        if not original:
            return None

        memory, text_wo_memory = self.extract_memory(original)
        brand, text_wo_brand = self.extract_brand(text_wo_memory)

        if not brand and self.file_brand:
            brand = self.file_brand
            remaining = text_wo_brand
        else:
            remaining = text_wo_brand

        remaining = re.sub(r"\s+", " ", remaining).strip()

        model, color = self.split_model_and_color(remaining)

        if not model:
            return None

        return {
            "brand": brand,
            "model": model,
            "memory": memory,
            "color": color,
        }

    def parse(self):
        if not self.read_file():
            return []

        self.file_brand = self.detect_file_brand()

        products = []

        for idx in range(len(self.df)):
            row = self.df.iloc[idx]
            product_text, price = self.row_to_product_text_and_price(row)

            if price is None:
                continue

            if not product_text:
                continue

            parsed = self.parse_product_text(product_text)
            if not parsed:
                continue

            if not parsed["model"]:
                continue

            products.append({
                "brand": parsed["brand"],
                "model": parsed["model"],
                "memory": parsed["memory"],
                "color": parsed["color"],
                "price": price,
            })

        return products


class TextPriceParser:
    """
    Универсальный парсер текстовых прайсов.
    """

    FLAG_MAP = {
        '🇮🇳': 'India',
        '🇯🇵': 'Japan',
        '🇺🇸': 'USA',
        '🇨🇳': 'China',
        '🇭🇰': 'Hong Kong',
        '🇪🇺': 'Europe',
        '🇦🇪': 'UAE',
        '🇰🇿': 'KZ'
    }

    REGION_TEXT_MAP = {
        'hk': 'Hong Kong',
        'jp': 'Japan',
        'japan': 'Japan',
        'india': 'India',
        'ind': 'India',
        'us': 'USA',
        'usa': 'USA',
        'cn': 'China',
        'china': 'China',
        'eu': 'Europe',
        'europe': 'Europe',
        'uae': 'UAE',
        'kz': 'Kazahstan',
        'global': 'Global',
    }

    SIM_TYPES = {'esim', '1sim', '2sim', 'dsim'}
    MEMORY_VALUES = {'32', '64', '128', '256', '512', '1024', '2048', '1tb', '2tb'}
    CONFIG_PATTERN = re.compile(r'^\d{1,2}/\d{2,4}$', re.IGNORECASE)

    SECTION_KEYWORDS = {
        'android': {'category': 'phone', 'brand': ''},

        'iphone': {'category': 'phone', 'brand': 'iPhone'},
        'samsung': {'category': 'phone', 'brand': 'Samsung'},
        'xiaomi': {'category': 'phone', 'brand': 'Xiaomi'},
        'redmi': {'category': 'phone', 'brand': 'Redmi'},
        'poco': {'category': 'phone', 'brand': 'Poco'},
        'honor': {'category': 'phone', 'brand': 'Honor'},
        'huawei': {'category': 'phone', 'brand': 'Huawei'},
        'realme': {'category': 'phone', 'brand': 'Realme'},
        'oneplus': {'category': 'phone', 'brand': 'OnePlus'},
        'google': {'category': 'phone', 'brand': 'Google'},
        'pixel': {'category': 'phone', 'brand': 'Google Pixel'},
        'vivo': {'category': 'phone', 'brand': 'Vivo'},
        'oppo': {'category': 'phone', 'brand': 'Oppo'},

        'dyson': {'category': 'appliance', 'brand': 'Dyson'},
        'airpods': {'category': 'accessory', 'brand': 'AirPods'},
        'apple watch': {'category': 'watch', 'brand': 'Apple Watch'},
        'watch': {'category': 'watch', 'brand': 'Apple Watch'},
        'ipad': {'category': 'tablet', 'brand': 'iPad'},
        'macbook': {'category': 'laptop', 'brand': 'MacBook'},
        'mac mini': {'category': 'laptop', 'brand': 'Mac Mini'},
    }


    BRAND_KEYWORDS = {
        'iphone': {'brand': 'iPhone', 'category': 'phone'},
        'samsung': {'brand': 'Samsung', 'category': 'phone'},
        'xiaomi': {'brand': 'Xiaomi', 'category': 'phone'},
        'redmi': {'brand': 'Redmi', 'category': 'phone'},
        'poco': {'brand': 'Poco', 'category': 'phone'},
        'honor': {'brand': 'Honor', 'category': 'phone'},
        'huawei': {'brand': 'Huawei', 'category': 'phone'},
        'realme': {'brand': 'Realme', 'category': 'phone'},
        'oneplus': {'brand': 'OnePlus', 'category': 'phone'},
        'google': {'brand': 'Google', 'category': 'phone'},
        'pixel': {'brand': 'Google Pixel', 'category': 'phone'},
        'vivo': {'brand': 'Vivo', 'category': 'phone'},
        'oppo': {'brand': 'Oppo', 'category': 'phone'},

        'apple watch': {'brand': 'Apple Watch', 'category': 'watch'},
        'watch': {'brand': 'Apple Watch', 'category': 'watch'},

        'ipad': {'brand': 'iPad', 'category': 'tablet'},
        'macbook': {'brand': 'MacBook', 'category': 'laptop'},
        'mac mini': {'brand': 'Mac Mini', 'category': 'laptop'},

        'airpods': {'brand': 'AirPods', 'category': 'accessory'},
        'pencil': {'brand': 'Apple Pencil', 'category': 'accessory'},

        'dyson': {'brand': 'Dyson', 'category': 'appliance'},
    }

    PHONE_MODEL_WORDS = {
        'pro', 'max', 'plus', 'mini', 'ultra', 'note', 'fe', 'se', 'e', 'е',
        'galaxy', 'pixel', 'redmi', 'poco', 'air'
    }

    TABLET_MODEL_WORDS = {'ipad', 'mini', 'air', 'pro', 'm1', 'm2', 'm3', 'm4', 'm5'}
    LAPTOP_MODEL_WORDS = {'macbook', 'air', 'pro', 'mini', 'm1', 'm2', 'm3', 'm4', 'm5'}
    WATCH_MODEL_WORDS = {'se', 'ultra', 'aw', 's10', 's11', 'watch'}
    WATCH_SPEC_WORDS = {'sm', 'ml', 'ti', 'titanium', 'band', 'ocean', 'sport'}
    TABLET_SPEC_WORDS = {'wifi', 'wi-fi', 'cellular', 'lte', '5g'}
    ACCESSORY_SPEC_WORDS = {'anc', 'usb-c'}

    EMOJI_MARKERS = ['📱', '⌚️', '⌚', '🎧', '🖊️', '🖊', '💻', '📋', '🖥️', '🖥']

    def __init__(self, text):
        self.text = text or ''
        self.lines = self.text.splitlines()
        self.current_category = ''
        self.current_brand = ''
        self.current_group_model = ''

    def normalize_spaces(self, text):
        text = str(text).replace('\xa0', ' ').strip()
        return re.sub(r'\s+', ' ', text)

    def strip_markers(self, text):
        for marker in self.EMOJI_MARKERS:
            text = text.replace(marker, ' ')
        text = re.sub(r'[^\w\s/\-🇦-🇿🇦-🇿]', ' ', text)
        return self.normalize_spaces(text)


    def normalize_token_case(self, token):
        lower = token.lower()

        if re.match(r'^[A-Za-z]+\d+$', token):
            return token.upper()

        mapping = {
            'pro': 'Pro',
            'max': 'Max',
            'plus': 'Plus',
            'mini': 'Mini',
            'ultra': 'Ultra',
            'air': 'Air',
            'aw': 'AW',
            'note': 'Note',
            'fe': 'FE',
            'se': 'SE',
            'wifi': 'WiFi',
            'wi-fi': 'WiFi',
            'usb-c': 'USB-C',
            'anc': 'ANC',
            'airpods': 'AirPods',
            'e': 'e',
            'е': 'e',
        }

        if lower in mapping:
            return mapping[lower]

        if token.isdigit():
            return token

        if re.match(r'^m\d+$', lower):
            return lower.upper()

        if re.match(r'^s\d+$', lower):
            return lower.upper()

        if lower in {'sm', 'ml', 'esim', '1sim', '2sim', 'dsim'}:
            return lower

        return token.capitalize()

    def parse(self):
        products = []

        for raw_line in self.lines:
            line = self.normalize_spaces(raw_line)
            if not line:
                continue

            if self.is_section_header(line):
                self.apply_section_context(line)
                continue

            product = self.parse_product_line(line)
            if product:
                products.append(product)

        return products

    def extract_price(self, line):
        line = self.normalize_spaces(line)

        parts = line.rsplit(' ', 1)
        if len(parts) != 2:
            return None, line

        left, right = parts
        price_digits = re.sub(r'\D', '', right)

        if not price_digits:
            return None, line

        # Не считаем короткие числа ценой: это чаще номер модели/диагональ,
        # например "iPhone 15" или "SE 2 40".
        if len(price_digits) < 3:
            return None, line

        price = float(price_digits)
        remaining = self.normalize_spaces(left.rstrip('-').strip())
        return price, remaining


    def is_section_header(self, line):
        price, _ = self.extract_price(line)
        if price is not None:
            return False

        clean = self.strip_markers(line).lower()
        if not clean:
            return False

        if any(key in clean for key in self.SECTION_KEYWORDS):
            return True

        if re.match(r'^(iphone\s*)?\d+[a-zа-я]?(?:\s+(pro|max|plus|mini|ultra|air))*$', clean):
            return True

        return False

    def apply_section_context(self, line):
        clean = self.strip_markers(line)
        clean_lower = clean.lower()

        for key, data in self.SECTION_KEYWORDS.items():
            if key in clean_lower:
                self.current_category = data['category']
                self.current_brand = data['brand']
                self.current_group_model = clean
                return

        if re.match(r'^(iphone\s*)?\d+[a-zа-я]?(?:\s+(pro|max|plus|mini|ultra|air))*$', clean_lower):
            self.current_category = 'phone'
            self.current_brand = 'iPhone'
            self.current_group_model = ' '.join(self.normalize_token_case(t) for t in clean.split())
            if self.current_group_model.lower().startswith('iphone '):
                self.current_group_model = self.current_group_model[7:]
            return

    def extract_flag_region(self, text):
        for flag, region in self.FLAG_MAP.items():
            if flag in text:
                return flag, region, self.normalize_spaces(text.replace(flag, ' '))
        return '', '', text

    def extract_region_text(self, text):
        tokens = text.split()
        kept = []
        found = ''

        for token in tokens:
            lowered = token.lower()
            if lowered in self.REGION_TEXT_MAP and not found:
                found = self.REGION_TEXT_MAP[lowered]
            else:
                kept.append(token)

        return found, self.normalize_spaces(' '.join(kept))

    def extract_sim_type(self, text):
        tokens = text.split()
        kept = []
        found = ''

        for token in tokens:
            lowered = token.lower()
            if lowered in self.SIM_TYPES and not found:
                found = lowered
            else:
                kept.append(token)

        return found, self.normalize_spaces(' '.join(kept))

    def extract_config(self, text):
        tokens = text.split()
        kept = []
        found = ''

        for token in tokens:
            if self.CONFIG_PATTERN.match(token) and not found:
                found = token
            else:
                kept.append(token)

        return found, self.normalize_spaces(' '.join(kept))

    def extract_memory(self, text):
        tokens = text.split()
        found = ''
        found_index = None

        for i, token in enumerate(tokens):
            lowered = token.lower()
            compact = lowered.replace(' ', '')
            if compact in self.MEMORY_VALUES:
                if 'tb' in compact:
                    found = compact.upper()
                else:
                    digits = re.sub(r'\D', '', compact)
                    found = digits if digits else compact
                found_index = i

        if found_index is None:
            return '', text

        tokens.pop(found_index)
        return found, self.normalize_spaces(' '.join(tokens))

    def detect_brand_category(self, text):
        text_lower = text.lower()

        for key, data in sorted(self.BRAND_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(rf'(?<!\w){re.escape(key)}(?!\w)', text_lower):
                if data['category'] == 'accessory':
                    return data['brand'], data['category'], text

                cleaned = re.sub(
                    rf'(?<!\w){re.escape(key)}(?!\w)',
                    ' ',
                    text,
                    count=1,
                    flags=re.IGNORECASE,
                )
                return data['brand'], data['category'], self.normalize_spaces(cleaned)

        if self.current_category:
            return self.current_brand, self.current_category, text

        return '', self.detect_category_by_hints(text), text

    def detect_category_by_hints(self, text):
        lower = text.lower()

        if any(x in lower for x in ['macbook', 'mac mini']) or re.search(r'\b\d{1,2}/\d{2,4}\b', lower):
            return 'laptop'
        if any(x in lower for x in ['ipad', 'wifi', 'cellular']):
            return 'tablet'
        if any(x in lower for x in ['airpods', 'pencil', 'anc', 'usb-c']):
            return 'accessory'
        if any(x in lower for x in ['ocean band', 'sport band']) or re.search(r'\b(s10|s11|se|ultra)\b', lower):
            return 'watch'
        if any(x in lower for x in ['dyson', 'hs08', 'vinca', 'prussian', 'plum']):
            return 'appliance'
        return 'phone' if self.current_category == 'phone' else 'unknown'

    def parse_product_line(self, line):
        price, rest = self.extract_price(line)
        if price is None:
            return None

        rest = self.strip_markers(rest)

        flag, region, rest = self.extract_flag_region(rest)
        if not region:
            region, rest = self.extract_region_text(rest)

        sim_type, rest = self.extract_sim_type(rest)
        config, rest = self.extract_config(rest)
        memory, rest = self.extract_memory(rest)

        brand, category, rest = self.detect_brand_category(rest)
        if category == 'phone' and config and not memory:
            parts = config.split('/')
            if len(parts) == 2:
                memory = parts[1]


        if not brand:
            if category == 'phone' and self.current_brand:
                brand = self.current_brand
            elif category == 'watch':
                brand = 'Apple Watch'
            elif category == 'tablet':
                brand = 'iPad'
            elif category == 'laptop' and self.current_brand:
                brand = self.current_brand
            elif category == 'accessory' and self.current_brand:
                brand = self.current_brand
            elif category == 'appliance' and self.current_brand:
                brand = self.current_brand


        parser_map = {
            'phone': self.parse_phone_payload,
            'tablet': self.parse_tablet_payload,
            'laptop': self.parse_laptop_payload,
            'watch': self.parse_watch_payload,
            'accessory': self.parse_accessory_payload,
            'appliance': self.parse_appliance_payload,
        }

        parser = parser_map.get(category, self.parse_unknown_payload)
        parsed = parser(rest)

        specs_parts = []
        if config:
            specs_parts.append(config)
        if parsed.get('specs'):
            specs_parts.append(parsed['specs'])

        return {
            'category': category,
            'brand': brand,
            'model': parsed.get('model', '').strip(),
            'color': parsed.get('color', '').strip(),
            'memory': memory,
            'region': region,
            'sim_type': sim_type,
            'specs': ' '.join(part for part in specs_parts if part).strip(),
            'price': price,
            'flag': flag,
            'raw_text': line,
        }

    def split_tail_color(self, tokens, model_word_set=None, spec_word_set=None):
        model_word_set = model_word_set or set()
        spec_word_set = spec_word_set or set()

        model_tokens = []
        color_tokens = []
        spec_tokens = []

        for i, token in enumerate(tokens):
            lower = token.lower()

            if lower in spec_word_set:
                spec_tokens.append(token)
                continue

            if not model_tokens:
                model_tokens.append(token)
                continue

            if lower in model_word_set or any(ch.isdigit() for ch in token):
                if not color_tokens:
                    model_tokens.append(token)
                else:
                    spec_tokens.append(token)
                continue

            color_tokens.append(token)

        return model_tokens, color_tokens, spec_tokens

    def normalize_group_model(self, raw_model):
        raw_model = self.normalize_spaces(raw_model)
        if not raw_model:
            return self.current_group_model

        first = raw_model.split()[0].lower()
        compact_e = re.match(r'^(\d+)[еe]$', first)
        if compact_e:
            return f"{compact_e.group(1)}e"

        if self.current_group_model:
            group_first = self.current_group_model.split()[0].lower()
            if first == group_first:
                return self.current_group_model

        return ' '.join(self.normalize_token_case(t) for t in raw_model.split())

    def parse_phone_payload(self, text):
        tokens = text.split()
        if not tokens:
            return {'model': self.current_group_model or '', 'color': '', 'specs': ''}

        model_tokens, color_tokens, spec_tokens = self.split_tail_color(tokens, self.PHONE_MODEL_WORDS)
        model = ' '.join(self.normalize_token_case(t) for t in model_tokens).strip()
        model = self.normalize_group_model(model)
        color = ' '.join(self.normalize_token_case(t) for t in color_tokens).strip()
        specs = ' '.join(self.normalize_token_case(t) for t in spec_tokens).strip()
        return {'model': model, 'color': color, 'specs': specs}

    def parse_tablet_payload(self, text):
        tokens = text.split()
        model_tokens = []
        color_tokens = []
        spec_tokens = []

        for token in tokens:
            lower = token.lower()
            if lower in self.TABLET_SPEC_WORDS:
                spec_tokens.append(self.normalize_token_case(token))
            elif lower in self.TABLET_MODEL_WORDS or any(ch.isdigit() for ch in token):
                if not color_tokens:
                    model_tokens.append(self.normalize_token_case(token))
                else:
                    spec_tokens.append(self.normalize_token_case(token))
            else:
                color_tokens.append(self.normalize_token_case(token))

        model = ' '.join(model_tokens).strip()
        if model and not model.lower().startswith('ipad'):
            if model_tokens and model_tokens[0].isdigit():
                model = f"iPad {model}"

        return {
            'model': model,
            'color': ' '.join(color_tokens).strip(),
            'specs': ' '.join(spec_tokens).strip(),
        }

    def parse_laptop_payload(self, text):
        tokens = text.split()
        if not tokens:
            return {'model': '', 'color': '', 'specs': ''}

        model_tokens = []
        color = ''
        spec_tokens = []

        laptop_model_words = {'macbook', 'mac', 'mini', 'air', 'pro'}

        for token in tokens:
            lower = token.lower()

            if self.CONFIG_PATTERN.match(token):
                spec_tokens.append(token)
                continue

            if re.match(r'^m\d+$', lower):
                model_tokens.append(self.normalize_token_case(token))
                continue

            if lower in laptop_model_words or token.isdigit():
                model_tokens.append(self.normalize_token_case(token))
                continue

            if not color:
                color = self.normalize_token_case(token)
                continue

            spec_tokens.append(self.normalize_token_case(token))

        return {
            'model': ' '.join(model_tokens).strip(),
            'color': color.strip(),
            'specs': ' '.join(spec_tokens).strip(),
        }




    def parse_watch_payload(self, text):
        tokens = text.split()
        if not tokens:
            return {'model': '', 'color': '', 'specs': ''}

        model_tokens = []
        color = ''
        spec_tokens = []

        watch_model_words = {'aw', 'ultra', 'se', 's10', 's11', 'watch'}
        watch_spec_words = {'sm', 'ml', 'ti', 'titanium', 'band', 'ocean', 'sport'}

        i = 0
        while i < len(tokens):
            token = tokens[i]
            lower = token.lower()

            # модель: AW Ultra 3 / SE 3 / S11
            if not color and (lower in watch_model_words or token.isdigit()):
                model_tokens.append(self.normalize_token_case(token))
                i += 1
                continue

            # первый не-технический токен после модели = цвет
            if not color and lower not in watch_spec_words:
                color = self.normalize_token_case(token)
                i += 1
                continue

            # если цвет уже есть и токен равен цвету, не дублируем его
            if color and lower == color.lower():
                i += 1
                continue

            spec_tokens.append(self.normalize_token_case(token))
            i += 1

        return {
            'model': ' '.join(model_tokens).strip(),
            'color': color.strip(),
            'specs': ' '.join(spec_tokens).strip(),
        }



    def parse_accessory_payload(self, text):
        tokens = text.split()
        if not tokens:
            return {'model': '', 'color': '', 'specs': ''}

        model_tokens = []
        spec_tokens = []

        for token in tokens:
            lower = token.lower()
            if lower in self.ACCESSORY_SPEC_WORDS:
                spec_tokens.append(self.normalize_token_case(token))
            else:
                model_tokens.append(self.normalize_token_case(token))

        return {
            'model': ' '.join(model_tokens).strip(),
            'color': '',
            'specs': ' '.join(spec_tokens).strip(),
        }

    def parse_appliance_payload(self, text):
        tokens = text.split()
        if not tokens:
            return {'model': '', 'color': '', 'specs': ''}

        model = tokens[0].upper() if re.match(r'^[A-Za-z]+\d+$', tokens[0]) else self.normalize_token_case(tokens[0])
        color = ' '.join(self.normalize_token_case(t) for t in tokens[1:])
        return {'model': model, 'color': color, 'specs': ''}

    def parse_unknown_payload(self, text):
        return {
            'model': ' '.join(self.normalize_token_case(t) for t in text.split()),
            'color': '',
            'specs': '',
        }
