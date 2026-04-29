from django.test import TestCase

from .models import AggregatedProduct
from .parser import TextPriceParser


class TextPriceParserTests(TestCase):
    def test_base_ipad_keeps_explicit_model_name(self):
        parsed = TextPriceParser('iPad 13 128 WiFi 50000').parse()

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]['category'], 'tablet')
        self.assertEqual(parsed[0]['brand'], 'iPad')
        self.assertEqual(parsed[0]['model'], 'iPad 13')
        self.assertEqual(parsed[0]['memory'], '128')
        self.assertEqual(parsed[0]['specs'], 'WiFi')

    def test_iphone_header_is_not_parsed_as_product_with_price(self):
        parsed = TextPriceParser('iPhone 15\n16 ₽\n15 128 blue 🇮🇳 49500').parse()

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]['brand'], 'iPhone')
        self.assertEqual(parsed[0]['model'], '15')
        self.assertEqual(parsed[0]['price'], 49500.0)


class AggregatedProductDisplayTests(TestCase):
    def test_display_name_does_not_duplicate_brand_when_model_contains_it(self):
        product = AggregatedProduct(
            category='tablet',
            brand='iPad',
            model='iPad 13',
            memory='128',
            specs='WiFi',
        )

        self.assertEqual(str(product), 'iPad 13 128gb WiFi')
