import re
from django.db import transaction
from django.utils import timezone
from .models import Product, AggregatedProduct, ProductPrice


class Aggregator:
    """Агрегатор товаров"""

    @staticmethod
    def normalize_text(value):
        if not value:
            return ''
        value = str(value).strip().lower()
        value = re.sub(r'\s+', ' ', value)
        return value

    @staticmethod
    def normalize_memory(memory):
        if not memory:
            return ''
        return re.sub(r'\D', '', str(memory))

    @staticmethod
    def aggregate_all():
        results = {
            'total': Product.objects.count(),
            'aggregated': 0,
            'errors': 0
        }

        try:
            with transaction.atomic():
                ProductPrice.objects.all().delete()
                AggregatedProduct.objects.all().delete()

                today = timezone.localdate()

                today_products = Product.objects.select_related('supplier', 'pricelist').filter(
                    pricelist__uploaded_at__date=today
                )

                groups = {}

                for product in today_products:
                    category_norm = Aggregator.normalize_text(product.category)
                    brand_norm = Aggregator.normalize_text(product.brand)
                    model_norm = Aggregator.normalize_text(product.model)
                    color_norm = Aggregator.normalize_text(product.color)
                    memory_norm = Aggregator.normalize_memory(product.memory)
                    region_norm = Aggregator.normalize_text(product.region)
                    sim_type_norm = Aggregator.normalize_text(product.sim_type)
                    specs_norm = Aggregator.normalize_text(product.specs)

                    key = '|'.join([
                        category_norm,
                        brand_norm,
                        model_norm,
                        color_norm,
                        memory_norm,
                        region_norm,
                        sim_type_norm,
                        specs_norm,
                    ])

                    if key not in groups:
                        groups[key] = {
                            'products': [],
                            'category': product.category,
                            'brand': product.brand,
                            'model': product.model,
                            'color': product.color,
                            'memory': product.memory,
                            'region': product.region,
                            'sim_type': product.sim_type,
                            'specs': product.specs,
                        }

                    groups[key]['products'].append(product)

                for key, group in groups.items():
                    aggregated = AggregatedProduct.objects.create(
                        category=group['category'],
                        brand=group['brand'],
                        model=group['model'],
                        color=group['color'],
                        memory=group['memory'],
                        region=group['region'],
                        sim_type=group['sim_type'],
                        specs=group['specs'],
                    )

                    supplier_best_prices = {}

                    for product in group['products']:
                        supplier_id = product.supplier_id

                        if supplier_id not in supplier_best_prices:
                            supplier_best_prices[supplier_id] = product
                        else:
                            existing = supplier_best_prices[supplier_id]
                            if product.price < existing.price:
                                supplier_best_prices[supplier_id] = product

                    for product in supplier_best_prices.values():
                        ProductPrice.objects.create(
                            aggregated_product=aggregated,
                            supplier=product.supplier,
                            product=product,
                            price=product.price
                        )

                    results['aggregated'] += 1

                    print(
                        f"Создана группа: "
                        f"{group['category']} | {group['brand']} | {group['model']} | {group['color']} | "
                        f"{group['memory']} | {group['region']} | {group['sim_type']} | {group['specs']} - "
                        f"{len(group['products'])} исходных товаров, "
                        f"{len(supplier_best_prices)} поставщиков"
                    )

        except Exception as e:
            print(f"Ошибка агрегации: {e}")
            results['error'] = str(e)
            results['errors'] = 1

        return results
