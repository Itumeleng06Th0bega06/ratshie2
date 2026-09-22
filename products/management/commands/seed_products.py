"""Seed the shop with realistic demo products and generated local images.

Run: python manage.py seed_products

This command creates/updates a catalogue of realistic demo products (spare
parts and lubricants) with fabricated but plausible ZAR prices, stock levels
and locally-generated placeholder images. It is idempotent (update_or_create
keyed on a stable slug).
"""
from pathlib import Path
from io import BytesIO
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils.text import slugify

from products.models import Product, ProductImage
from PIL import Image, ImageDraw, ImageFont

CATEGORY_COLORS = {
    "oil": (201, 151, 43),
    "brake": (38, 48, 60),
    "filter": (56, 122, 181),
    "belt": (46, 60, 74),
    "suspension": (141, 62, 42),
    "electrical": (112, 76, 158),
    "coolant": (38, 154, 137),
    "tyre": (52, 52, 52),
    "battery": (33, 150, 83),
    "accessory": (198, 120, 40),
}


def _make_image(product_type: str, label: str, accent: str) -> ContentFile:
    """Render a simple placeholder product image with Pillow."""
    w, h = 800, 800
    bg = CATEGORY_COLORS.get(accent, (60, 60, 60))
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    # subtle lighter panel in the centre
    panel = tuple(min(255, c + 40) for c in bg)
    draw.rounded_rectangle([120, 160, 680, 640], radius=48, fill=panel)

    # icon: a simple part-ish glyph
    cx, cy = w // 2, 400
    draw.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], outline=(255, 255, 255), width=10)
    draw.line([cx, cy - 80, cx, cy + 80], fill=(255, 255, 255), width=10)
    draw.line([cx - 80, cy, cx + 80, cy], fill=(255, 255, 255), width=10)

    # label text
    font = None
    for cand in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(cand).exists():
            try:
                font = ImageFont.truetype(cand, 56)
            except Exception:
                font = None
            break
    if font is None:
        font = ImageFont.load_default()

    text = label[:20]
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (w - tw) / 2
    draw.text((tx, 700), text, fill=(255, 255, 255), font=font)

    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return ContentFile(out.read(), name=f"{slugify(text) or 'product'}.png")


PRODUCTS = [
    # ---------------- Lubricants ----------------
    {
        "product_type": Product.ProductType.LUBRICANT,
        "name": "Full Synthetic Engine Oil 5W-30 (5L)",
        "brand": "Shell Helix Ultra",
        "price": "649.00",
        "compare_at_price": None,
        "sku": "OIL-5W30-5L",
        "viscosity": "5W-30",
        "volume": "5 Litre",
        "oil_type": "Full Synthetic",
        "spec": "API SP, ACEA C3",
        "short_description": "Premium full-synthetic engine oil for modern petrol and diesel engines.",
        "accent": "oil",
        "featured": True,
        "stock": 42,
    },
    {
        "product_type": Product.ProductType.LUBRICANT,
        "name": "Semi-Synthetic Engine Oil 10W-40 (5L)",
        "brand": "Castrol Magnatec",
        "price": "429.00",
        "compare_at_price": "499.00",
        "sku": "OIL-10W40-5L",
        "viscosity": "10W-40",
        "volume": "5 Litre",
        "oil_type": "Semi-Synthetic",
        "spec": "API SN, ACEA A3/B4",
        "short_description": "Reliable semi-synthetic for older petrol and light diesel engines.",
        "accent": "oil",
        "featured": True,
        "stock": 60,
    },
    {
        "product_type": Product.ProductType.LUBRICANT,
        "name": "Diesel Engine Oil 15W-40 (5L)",
        "brand": "Total Quartz 5000",
        "price": "385.00",
        "compare_at_price": None,
        "sku": "OIL-15W40-5L",
        "viscosity": "15W-40",
        "volume": "5 Litre",
        "oil_type": "Mineral",
        "spec": "API CH-4",
        "short_description": "Heavy-duty diesel engine oil suited to turbo and N/A diesel engines.",
        "accent": "oil",
        "featured": False,
        "stock": 35,
    },
    {
        "product_type": Product.ProductType.LUBRICANT,
        "name": "Automatic Transmission Fluid ATF DX III (4L)",
        "brand": "Castrol ATF",
        "price": "540.00",
        "compare_at_price": None,
        "sku": "FLU-ATF-4L",
        "volume": "4 Litre",
        "oil_type": "ATF",
        "spec": "Dexron III",
        "short_description": "Quality automatic transmission fluid for smooth gear changes.",
        "accent": "oil",
        "featured": False,
        "stock": 28,
    },
    {
        "product_type": Product.ProductType.LUBRICANT,
        "name": "Gearbox / Differential Oil 80W-90 (1L)",
        "brand": "Engen Gearoil",
        "price": "159.00",
        "compare_at_price": None,
        "sku": "GEAR-80W90-1L",
        "viscosity": "80W-90",
        "volume": "1 Litre",
        "oil_type": "Gear Oil",
        "spec": "API GL-4",
        "short_description": "Manual gearbox and differential lubricant for common applications.",
        "accent": "oil",
        "featured": False,
        "stock": 45,
    },
    {
        "product_type": Product.ProductType.LUBRICANT,
        "name": "Brake Fluid DOT 4 (500ml)",
        "brand": "Castrol Response",
        "price": "125.00",
        "compare_at_price": None,
        "sku": "FLU-DOT4-500",
        "volume": "500 ml",
        "oil_type": "Brake Fluid",
        "spec": "DOT 4",
        "short_description": "High-boiling-point brake fluid for safe, consistent braking.",
        "accent": "brake",
        "featured": True,
        "stock": 80,
    },
    {
        "product_type": Product.ProductType.LUBRICANT,
        "name": "Antifreeze / Coolant Concentrate (5L)",
        "brand": "Engen Antifreeze",
        "price": "215.00",
        "compare_at_price": "259.00",
        "sku": "COOL-80-5L",
        "volume": "5 Litre",
        "oil_type": "Coolant",
        "spec": "Ethylene glycol based",
        "short_description": "Long-life antifreeze concentrate protecting against corrosion and overheating.",
        "accent": "coolant",
        "featured": False,
        "stock": 50,
    },
    {
        "product_type": Product.ProductType.LUBRICANT,
        "name": "Power Steering Fluid (1L)",
        "brand": "Gearbox/P/S Fluid",
        "price": "145.00",
        "compare_at_price": None,
        "sku": "FLU-PS-1L",
        "volume": "1 Litre",
        "oil_type": "Power steering fluid",
        "spec": "ATF compatible",
        "short_description": "Keeps power steering systems smooth and responsive.",
        "accent": "oil",
        "featured": False,
        "stock": 38,
    },
    # ---------------- Filters ----------------
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Engine Oil Filter (Universal)",
        "brand": "Fram",
        "price": "85.00",
        "compare_at_price": None,
        "sku": "FIL-OIL-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "High-flow oil filter for a wide range of petrol engines.",
        "accent": "filter",
        "featured": True,
        "stock": 90,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Cabin / Pollen Air Filter",
        "brand": "Bosch",
        "price": "165.00",
        "compare_at_price": None,
        "sku": "FIL-CABIN-GEN",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Improves cabin air quality by filtering dust and pollen.",
        "accent": "filter",
        "featured": False,
        "stock": 55,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Air Filter Panel (Universal)",
        "brand": "Fram",
        "price": "195.00",
        "compare_at_price": None,
        "sku": "FIL-AIR-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Panel-style air filter helping keep your engine breathing clean.",
        "accent": "filter",
        "featured": False,
        "stock": 48,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Fuel Filter (In-Line Universal)",
        "brand": "Bosch",
        "price": "175.00",
        "compare_at_price": None,
        "sku": "FIL-FUEL-UNI",
        "vehicle_makes": "Toyota, Ford, Nissan",
        "short_description": "In-line fuel filter protecting your injectors and pump.",
        "accent": "filter",
        "featured": False,
        "stock": 40,
    },
    # ---------------- Brakes ----------------
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Front Brake Pad Set (Universal) — Ceramic",
        "brand": "Ferodo",
        "price": "345.00",
        "compare_at_price": "399.00",
        "sku": "BRK-PAD-FR-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Low-dust ceramic front brake pads for daily commuters.",
        "accent": "brake",
        "featured": True,
        "stock": 36,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Rear Brake Pad Set (Universal) — Ceramic",
        "brand": "Ferodo",
        "price": "315.00",
        "compare_at_price": None,
        "sku": "BRK-PAD-RR-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Reliable ceramic rear brake pads for balanced braking.",
        "accent": "brake",
        "featured": False,
        "stock": 33,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Brake Disc (Front, 258mm)",
        "brand": "Ferodo",
        "price": "425.00",
        "compare_at_price": None,
        "sku": "BRK-DISC-FR-258",
        "vehicle_makes": "Toyota, Hyundai, Kia",
        "short_description": "Vented front brake disc for consistent performance.",
        "accent": "brake",
        "featured": False,
        "stock": 22,
    },
    # ---------------- Belts ----------------
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Serpentine / Drive Belt (Universal)",
        "brand": "Gates",
        "price": "255.00",
        "compare_at_price": None,
        "sku": "BELT-SERP-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Ribbed drive belt for alternator, power steering and cooling fans.",
        "accent": "belt",
        "featured": False,
        "stock": 27,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "V-Belt (Universal)",
        "brand": "Gates",
        "price": "145.00",
        "compare_at_price": None,
        "sku": "BELT-V-UNI",
        "vehicle_makes": "Toyota, Ford, Nissan",
        "short_description": "Classic V-belt for auxiliary engine drives.",
        "accent": "belt",
        "featured": False,
        "stock": 31,
    },
    # ---------------- Suspension ----------------
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Front Shock Absorber (Universal)",
        "brand": "Monroe",
        "price": "485.00",
        "compare_at_price": None,
        "sku": "SUS-FSHOCK-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "OEM-style front shock absorber for a controlled, comfortable ride.",
        "accent": "suspension",
        "featured": True,
        "stock": 18,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Sway Bar Link Kit (Universal)",
        "brand": "MOOG",
        "price": "265.00",
        "compare_at_price": None,
        "sku": "SUS-SWAY-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Stabiliser link kit to reduce body roll and knocking.",
        "accent": "suspension",
        "featured": False,
        "stock": 25,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Ball Joint (Lower, Universal)",
        "brand": "MOOG",
        "price": "295.00",
        "compare_at_price": None,
        "sku": "SUS-BALL-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Lower ball joint for safe steering and suspension movement.",
        "accent": "suspension",
        "featured": False,
        "stock": 20,
    },
    # ---------------- Electrical ----------------
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Battery — 12V 620CCA (Maintenance-Free)",
        "brand": "Willard",
        "price": "1250.00",
        "compare_at_price": "1390.00",
        "sku": "ELE-BAT-620",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Reliable maintenance-free lead-acid battery with strong cold cranking.",
        "accent": "battery",
        "featured": True,
        "stock": 15,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Alternator (Reconditioned, Universal)",
        "brand": "Lucas",
        "price": "895.00",
        "compare_at_price": None,
        "sku": "ELE-ALT-RECON",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Reconditioned alternator — tested and ready to install.",
        "accent": "electrical",
        "featured": False,
        "stock": 8,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Spark Plug Set (x4, Copper Core)",
        "brand": "NGK",
        "price": "185.00",
        "compare_at_price": None,
        "sku": "ELE-SPARK-4",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Set of four copper-core spark plugs for smoother running.",
        "accent": "electrical",
        "featured": False,
        "stock": 44,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Headlight Bulb H4 (Pair, Halogen)",
        "brand": "Osram",
        "price": "115.00",
        "compare_at_price": None,
        "sku": "ELE-H4-HAL",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Bright halogen H4 main-beam bulbs (pair).",
        "accent": "electrical",
        "featured": False,
        "stock": 70,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Wiper Blades (Set of 2, 530mm/430mm)",
        "brand": "Bosch",
        "price": "195.00",
        "compare_at_price": None,
        "sku": "ACC-WIPER-SET",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Quiet, streak-free wiper blade set (driver + passenger).",
        "accent": "accessory",
        "featured": False,
        "stock": 52,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Wiper Blades (Set of 3, 530mm/430mm/400mm)",
        "brand": "Bosch",
        "price": "245.00",
        "compare_at_price": None,
        "sku": "ACC-WIPER-SET3",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Complete three-blade set including rear wiper.",
        "accent": "accessory",
        "featured": False,
        "stock": 30,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "12V Tyre Inflator / Compressor",
        "brand": "CIG Accessory",
        "price": "549.00",
        "compare_at_price": None,
        "sku": "ACC-INFLATOR",
        "vehicle_makes": "Universal",
        "short_description": "Portable 12V compressor to top up tyre pressure anywhere.",
        "accent": "tyre",
        "featured": False,
        "stock": 12,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Jump Start Cables (Heavy Duty, 4m)",
        "brand": "Accessory",
        "price": "275.00",
        "compare_at_price": None,
        "sku": "ACC-JUMP-4M",
        "vehicle_makes": "Universal",
        "short_description": "Heavy-duty booster cables for quick starts in emergencies.",
        "accent": "electrical",
        "featured": False,
        "stock": 26,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Coolant Reservoir / Expansion Tank (Universal)",
        "brand": "Gates",
        "price": "285.00",
        "compare_at_price": None,
        "sku": "COOL-TANK-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan",
        "short_description": "Replacement expansion tank for cooling systems.",
        "accent": "coolant",
        "featured": False,
        "stock": 16,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Radiator Cap (Universal)",
        "brand": "Gates",
        "price": "95.00",
        "compare_at_price": None,
        "sku": "COOL-CAP-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan",
        "short_description": "Standard 16PSI radiator cap keeping your system pressurised.",
        "accent": "coolant",
        "featured": False,
        "stock": 60,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Engine Oil Drain Plug Gasket (Universal)",
        "brand": "Accessory",
        "price": "25.00",
        "compare_at_price": None,
        "sku": "FIL-GASKET-DRAIN",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Copper drain plug washer for leak-free oil changes.",
        "accent": "oil",
        "featured": False,
        "stock": 120,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Cabin Filter + Oil Filter Service Combo",
        "brand": "Bosch / Fram",
        "price": "229.00",
        "compare_at_price": "275.00",
        "sku": "COMBO-FILTERS",
        "vehicle_makes": "Universal",
        "short_description": "Convenient combo of oil filter and cabin/pollen filter.",
        "accent": "filter",
        "featured": False,
        "stock": 34,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Performance Air Filter (Sports, Universal)",
        "brand": "KN",
        "price": "780.00",
        "compare_at_price": "899.00",
        "sku": "FIL-AIR-SPORT",
        "vehicle_makes": "Toyota, VW, Ford, Nissan",
        "short_description": "Washable sports air filter for improved airflow.",
        "accent": "filter",
        "featured": False,
        "stock": 9,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Brake Light Switch (Universal)",
        "brand": "Bosch",
        "price": "135.00",
        "compare_at_price": None,
        "sku": "ELE-BRKSW-UNI",
        "vehicle_makes": "Toyota, VW, Ford, Nissan, Hyundai",
        "short_description": "Replacement brake light switch for reliable brake lights.",
        "accent": "electrical",
        "featured": False,
        "stock": 41,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Fuse Assortment Kit (Mixed Amp)",
        "brand": "Accessory",
        "price": "85.00",
        "compare_at_price": None,
        "sku": "ELE-FUSE-KIT",
        "vehicle_makes": "Universal",
        "short_description": "Handy assortment of blade fuses for on-the-road fixes.",
        "accent": "electrical",
        "featured": False,
        "stock": 65,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Roof Rack Cross Bars (Adjustable, Universal)",
        "brand": "Accessory",
        "price": "1250.00",
        "compare_at_price": "1399.00",
        "sku": "ACC-ROOFRACK",
        "vehicle_makes": "Universal",
        "short_description": "Adjustable roof rack cross bars for extra carrying capacity.",
        "accent": "accessory",
        "featured": False,
        "stock": 6,
    },
    {
        "product_type": Product.ProductType.SPARE_PART,
        "name": "Steering Wheel Cover (Leather-Look, 15 inch)",
        "brand": "Accessory",
        "price": "115.00",
        "compare_at_price": None,
        "sku": "ACC-STWHEEL",
        "vehicle_makes": "Universal",
        "short_description": "Comfortable leather-look steering wheel cover.",
        "accent": "accessory",
        "featured": False,
        "stock": 48,
    },
]


class Command(BaseCommand):
    help = "Create/update a realistic demo product catalogue with generated images."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        media_dir = Path(settings.MEDIA_ROOT) / "products"
        media_dir.mkdir(parents=True, exist_ok=True)

        for data in PRODUCTS:
            name = data["name"]
            slug = slugify(name)

            defaults = {
                "product_type": data["product_type"],
                "name": name,
                "short_description": data.get("short_description", ""),
                "brand": data.get("brand", ""),
                "sku": data.get("sku", ""),
                "price": Decimal(data["price"]),
                "original_price": (
                    Decimal(data["compare_at_price"]) if data.get("compare_at_price") else None
                ),
                "availability": "in_stock",
                "stock": data.get("stock", 10),
                "is_available": True,
                "vehicle_makes": data.get("vehicle_makes", ""),
                "viscosity": data.get("viscosity", ""),
                "volume": data.get("volume", ""),
                "oil_type": data.get("oil_type", ""),
                "spec": data.get("spec", ""),
                "is_featured": data.get("featured", False),
                "is_new": data.get("is_new", False),
                "is_active": True,
            }

            product, created = Product.objects.update_or_create(
                slug=slug, defaults=defaults
            )

            # Attach primary image if missing
            if not product.images.filter(is_primary=True).exists():
                img_file = _make_image(
                    data["product_type"], data["name"], data["accent"]
                )
                ProductImage.objects.create(
                    product=product,
                    image=img_file,
                    is_primary=True,
                    sort_order=0,
                    alt_text=name,
                )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created_count} created, {updated_count} updated, "
                f"{Product.objects.filter(is_active=True).count()} active products total."
            )
        )
