"""Populate the shop with a realistic generic automotive starter catalogue.

Design constraints (do not change without reading the product brief):

* Uses the existing Product / ProductGroup models. No new product system.
* Products are matched by SKU, falling back to name for hand-created rows, so
  re-running is idempotent (update_or_create) and never collides on the unique
  slug. A hand-created product's auto-generated SKU is preserved.
* NO brand names. Every product is a generic fitment description. Nothing here
  claims OEM / genuine / distributor status for any manufacturer.
* NO manufacturer part numbers. SKUs are internal Ratshie references only.
* NO generated or hotlinked images. Products without an image deliberately fall
  back to the storefront placeholder so nothing incorrect is ever displayed.
* Prices are realistic South African starter values in ZAR, editable in admin.
  They are NOT official Ratshie pricing.
* Existing real product data is never clobbered: a product that already has a
  price set by a human is left alone unless --force-prices is passed.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from products.models import Product, ProductGroup

# (name, description, sort_order)
GROUPS = [
    ("Filters", "Oil, air, cabin and fuel filters.", 10),
    ("Braking", "Brake pads, discs and shoes.", 20),
    ("Engine", "Spark plugs, belts, mounts and gaskets.", 30),
    ("Suspension", "Shock absorbers, control arms, links and ball joints.", 40),
    ("Electrical", "Batteries, bulbs, fuses and wiper motors.", 50),
    ("Accessories", "Wiper blades, floor mats, chargers and emergency kits.", 60),
    ("Tools", "Socket sets, jacks, diagnostic tools and workshop kits.", 70),
]

# Common South African fitments referenced by the generic catalogue.
POPULAR = "Toyota Hilux,Ford Ranger,Toyota Corolla,Ford Fiesta,Volkswagen Polo,Hyundai i20,Kia Picanto,Nissan NP200,Nissan Navara"

# Consumable fluids use the existing LUBRICANT product_type so admin reporting
# and enquiry routing stay correct. Everything else is a SPARE_PART.
LUBRICANTS = {
    "Brake Fluid DOT 4 - 500ml",
}

# name, group, price, original_price, stock, featured, is_new,
# vehicle_makes, vehicle_models, short_description
CATALOGUE = [
    # ---------------------------------------------------------------- Filters
    ("Toyota Corolla Oil Filter", "Filters", "149.00", None, 40, True, True,
     "Toyota", "Corolla",
     "Spin-on oil filter for Toyota Corolla petrol engines. Check the code on your existing filter before ordering."),
    ("Toyota Hilux Oil Filter", "Filters", "159.00", None, 35, False, False,
     "Toyota", "Hilux",
     "Spin-on oil filter for Toyota Hilux 2.4 and 2.8 diesel engines."),
    ("Toyota Fortuner Oil Filter", "Filters", "159.00", None, 18, False, False,
     "Toyota", "Fortuner",
     "Spin-on oil filter for Toyota Fortuner diesel and petrol engines."),
    ("Volkswagen Polo Oil Filter", "Filters", "139.00", None, 30, False, False,
     "Volkswagen", "Polo",
     "Spin-on oil filter for Volkswagen Polo 1.0 and 1.4 petrol engines."),
    ("Ford Ranger Oil Filter", "Filters", "169.00", None, 28, False, False,
     "Ford", "Ranger",
     "Spin-on oil filter for Ford Ranger 2.2 diesel engines."),
    ("Universal Panel Air Filter", "Filters", "249.00", None, 22, True, True,
     "", "",
     "Rectangular panel air filter for many petrol vehicles. Measure your old filter before ordering."),
    ("Round Air Filter - 70mm", "Filters", "219.00", None, 26, False, False,
     "", "",
     "Round 70mm air filter element for classic carburettor and older petrol vehicles."),
    ("Cabin / Pollen Filter - Universal", "Filters", "199.00", None, 45, False, False,
     "", "",
     "Activated cabin filter for fresh air vents. Check the shape and size against your existing filter."),
    ("In-Line Fuel Filter", "Filters", "189.00", None, 20, False, False,
     "", "",
     "In-line fuel filter for petrol vehicles with a fuel line filter. Confirm thread size and hose diameter."),
    ("Diesel Fuel Filter with Water Sensor", "Filters", "329.00", "399.00", 12, True, False,
     "", "",
     "Diesel fuel filter with integrated water sensor. Confirm the sensor port matches your vehicle."),

    # ---------------------------------------------------------------- Braking
    ("Front Brake Pad Set - Ceramic", "Braking", "599.00", "749.00", 24, True, True,
     "", "",
     "Ceramic front brake pad set. Measure your existing pad width and disc diameter before ordering."),
    ("Rear Brake Pad Set - Ceramic", "Braking", "549.00", None, 20, False, False,
     "", "",
     "Ceramic rear brake pad set. Confirm whether your vehicle uses disc or drum brakes at the rear."),
    ("Brake Disc - Front 258mm", "Braking", "699.00", None, 16, False, False,
     "", "",
     "Front brake disc, 258mm diameter. Check minimum thickness and wheel bolt pattern."),
    ("Brake Disc - Vented Front", "Braking", "849.00", None, 12, False, False,
     "", "",
     "Vented front brake disc for improved heat dissipation. Verify diameter, thickness and offset."),
    ("Brake Drum - Rear 180mm", "Braking", "489.00", None, 10, False, False,
     "", "",
     "Cast rear brake drum, 180mm. Confirm inner diameter and half-shaft fitment."),
    ("Brake Shoe Set - Rear", "Braking", "459.00", None, 14, False, False,
     "", "",
     "Complete rear drum brake shoe set with springs and adjusters included."),
    ("Brake Caliper Repair Kit", "Braking", "329.00", None, 18, False, False,
     "", "",
     "Caliper repair kit with seals and dust boots. Piston diameter must match your caliper."),
    ("Brake Fluid DOT 4 - 500ml", "Braking", "129.00", None, 60, False, False,
     "", "",
     "DOT 4 brake fluid, 500ml. Use the grade specified in your vehicle owner's manual."),
    ("Brake Light Switch", "Braking", "149.00", None, 22, False, False,
     "", "",
     "Brake pedal / brake light switch for common thread sizes. Confirm the thread and terminal count."),

    # ----------------------------------------------------------------- Engine
    ("Spark Plug Set (x4) - Copper Core", "Engine", "499.00", None, 30, True, True,
     "", "",
     "Set of four copper-core spark plugs. Use the gap and heat range specified for your engine."),
    ("Spark Plug Set (x4) - Iridium", "Engine", "899.00", None, 16, False, False,
     "", "",
     "Set of four iridium spark plugs for longer service intervals. Confirm heat range."),
    ("Serpentine Drive Belt", "Engine", "379.00", None, 20, False, False,
     "", "",
     "Multi-rib serpentine belt. Measure your old belt length and profile before ordering."),
    ("V-Belt - 13 x 900mm", "Engine", "149.00", None, 34, False, False,
     "", "",
     "Classical V-belt, 13mm top width x 900mm. Measure the length before ordering."),
    ("Engine Mount - Right", "Engine", "549.00", None, 12, False, False,
     "", "",
     "Right-hand engine mount. Confirm the mounting stud pattern for your engine."),
    ("Engine Mount - Left", "Engine", "549.00", None, 12, False, False,
     "", "",
     "Left-hand engine mount. Confirm the mounting stud pattern for your engine."),
    ("Valve Cover Gasket Set", "Engine", "429.00", None, 14, False, False,
     "", "",
     "Valve cover and spark plug seal gasket set. Confirm engine code before ordering."),
    ("Cylinder Head Gasket", "Engine", "899.00", None, 6, False, False,
     "", "",
     "Cylinder head gasket. Confirm engine code and cylinder count before ordering."),
    ("Oil Drain Plug Washer Set", "Engine", "89.00", None, 80, False, False,
     "", "",
     "Assorted oil drain plug crush washers. Measure the drain plug thread before ordering."),

    # ------------------------------------------------------------ Suspension
    ("Front Shock Absorber - Gas Pressurised", "Suspension", "799.00", None, 16, True, True,
     "", "",
     "Gas-pressurised front shock absorber. Confirm upper and lower mounting eyes and the extended length."),
    ("Rear Shock Absorber - Gas Pressurised", "Suspension", "749.00", None, 16, False, False,
     "", "",
     "Gas-pressurised rear shock absorber. Confirm eye-to-eye length before ordering."),
    ("Lower Control Arm - Left", "Suspension", "1099.00", None, 8, False, False,
     "", "",
     "Left-hand lower control arm with ball joint and bushings. Confirm side and position."),
    ("Lower Control Arm - Right", "Suspension", "1099.00", None, 8, False, False,
     "", "",
     "Right-hand lower control arm with ball joint and bushings. Confirm side and position."),
    ("Stabiliser Link Kit", "Suspension", "289.00", None, 26, False, False,
     "", "",
     "Stabiliser link kit. Confirm ball joint stud length and thread diameter."),
    ("Lower Ball Joint", "Suspension", "479.00", None, 14, False, False,
     "", "",
     "Lower ball joint. Confirm taper pin diameter, stud length and whether a bracket is needed."),
    ("Upper Control Arm Bush Pair", "Suspension", "399.00", None, 18, False, False,
     "", "",
     "Upper control arm bush pair. Confirm inner and outer sleeve diameters."),
    ("Coil Spring - Front Pair", "Suspension", "1199.00", "1399.00", 6, False, False,
     "", "",
     "Front coil spring pair. Confirm spring rate, wire diameter and seat diameter."),

    # ------------------------------------------------------------- Electrical
    ("Car Battery 12V 620CCA", "Electrical", "1899.00", None, 10, True, True,
     "", "",
     "12V maintenance-free car battery, 620CCA. Confirm case size, polarity and terminal type."),
    ("Car Battery 12V 400CCA", "Electrical", "1499.00", None, 12, False, False,
     "", "",
     "12V maintenance-free car battery, 400CCA. Confirm case size, polarity and terminal type."),
    ("Heavy Duty Jump Starter 12V", "Electrical", "1299.00", None, 10, False, False,
     "", "",
     "Portable 12V jump starter with built-in battery and USB output. Charge before first use."),
    ("Headlight Bulb H4 - Pair", "Electrical", "249.00", None, 40, False, False,
     "", "",
     "H4 halogen headlight bulb pair. Confirm the bulb code stamped on your existing bulb."),
    ("Headlight Bulb H7 - Pair", "Electrical", "279.00", None, 36, False, False,
     "", "",
     "H7 halogen headlight bulb pair. Confirm the bulb code and wattage for your vehicle."),
    ("Fuse Assortment Kit", "Electrical", "199.00", None, 50, False, False,
     "", "",
     "Mixed mini and standard blade fuse assortment for panel repair."),
    ("Wiper Motor - Front", "Electrical", "1099.00", None, 8, False, False,
     "", "",
     "Front wiper motor. Confirm the number and position of the arms on your vehicle."),
    ("Alternator 12V 90A", "Electrical", "2299.00", None, 4, False, False,
     "", "",
     "12V 90A alternator. Confirm pulley type, mounting ears and the reference number on your old unit."),

    # ------------------------------------------------------------ Accessories
    ("Wiper Blades - Set of 2 (530/430mm)", "Accessories", "199.00", None, 48, True, True,
     "", "",
     "Universal-fit wiper blade pair, 530mm and 430mm. Confirm your wiper arm type before ordering."),
    ("Wiper Blades - Set of 3 (530/430/400mm)", "Accessories", "279.00", None, 36, False, False,
     "", "",
     "Universal-fit wiper blade set, 530mm, 430mm and 400mm. Confirm your wiper arm type."),
    ("Rubber Floor Mat Set - Universal", "Accessories", "449.00", "549.00", 24, False, False,
     "", "",
     "Universal rubber floor mat set with fitted shape. Measure your footwell and check the retention clips."),
    ("Tailored Floor Mat Set - Corolla", "Accessories", "899.00", None, 12, False, False,
     "Toyota", "Corolla",
     "Vehicle-specific rubber floor mats for Toyota Corolla. Confirm model year before ordering."),
    ("12V Tyre Inflator", "Accessories", "349.00", None, 20, False, False,
     "", "",
     "12V portable tyre inflator with analogue gauge. Check the valve adapter included."),
    ("Jump Start Cables - Heavy Duty 4m", "Accessories", "299.00", None, 22, False, False,
     "", "",
     "Heavy duty jump start cables, 4m. Confirm cable gauge is adequate for your engine size."),
    ("Emergency Kit - Vehicle", "Accessories", "379.00", None, 26, False, False,
     "", "",
     "Vehicle emergency kit with reflective triangle, torch, gloves and first aid items."),
    ("Phone Holder - Dashboard Mount", "Accessories", "149.00", None, 44, False, False,
     "", "",
     "Dashboard phone holder with suction mount. Confirm your phone width before ordering."),

    # ----------------------------------------------------------------- Tools
    ("Socket Set - 46 Piece", "Tools", "899.00", None, 12, True, True,
     "", "",
     "46-piece socket set in metric and imperial. Includes ratchet, extension and spinner handle."),
    ("Socket Set - 40 Piece Metric", "Tools", "699.00", None, 14, False, False,
     "", "",
     "40-piece metric socket set with quarter-inch and three-eighth-inch drives."),
    ("Torsion Wrench 1/2\" 28-210Nm", "Tools", "1149.00", None, 8, False, False,
     "", "",
     "Click-type torque wrench with 28-210Nm range. Check calibration certificate validity."),
    ("Hydraulic Floor Jack 2T", "Tools", "1699.00", "1899.00", 6, True, False,
     "", "",
     "2 tonne low-profile hydraulic floor jack. Check the lifting point rating for your vehicle."),
    ("Jack Stand Set - 2T (Pair)", "Tools", "699.00", None, 10, False, False,
     "", "",
     "Pair of 2 tonne ratcheting jack stands. Always support the vehicle on stands before working underneath."),
    ("OBD2 Diagnostic Scanner", "Tools", "899.00", None, 12, False, False,
     "", "",
     "OBD2 code reader reading and clearing engine fault codes. Supports most 1996+ petrol vehicles."),
    ("Digital Multimeter", "Tools", "499.00", None, 16, False, False,
     "", "",
     "Digital multimeter for volts, amps, ohms and continuity. Includes test leads and battery."),
    ("Torque Wrench Set - 3 Piece", "Tools", "899.00", None, 8, False, False,
     "", "",
     "Three-piece click-type torque wrench set in metric sizes. Check calibration certificate validity."),
    ("Wheel Bolt Nut Set (x20)", "Tools", "279.00", None, 30, False, False,
     "", "",
     "20-piece wheel nut and bolt set. Confirm thread pitch, seat type and cone/nut before ordering."),
    ("Grease Gun - Manual", "Tools", "399.00", None, 12, False, False,
     "", "",
     "Manual grease gun with 500g capacity for CV joint and chassis servicing."),
]


class Command(BaseCommand):
    help = (
        "Populate the shop with a generic automotive starter catalogue "
        "(idempotent, no brands, no generated images)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force-prices",
            action="store_true",
            help=(
                "Overwrite prices on products that already have a real price set. "
                "Without this flag an existing non-zero price is preserved."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force_prices = options["force_prices"]
        dry_run = options["dry_run"]

        groups = {}
        for name, description, order in GROUPS:
            slug = slugify(name)
            if dry_run:
                groups[slug] = ProductGroup(name=name, slug=slug)
                continue
            group, _ = ProductGroup.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "description": description, "sort_order": order},
            )
            groups[slug] = group

        created_count = 0
        updated_count = 0
        price_kept = 0
        missing_images = []

        for row in CATALOGUE:
            (
                name, group_name, price, original_price, stock, featured, is_new,
                makes, models, short_desc,
            ) = row

            sku = "RSH-" + slugify(name).upper().replace("-", "-")[:60]
            group = groups[slugify(group_name)]

            defaults = {
                "name": name,
                "product_group": group,
                "product_type": (
                    Product.ProductType.LUBRICANT
                    if name in LUBRICANTS
                    else Product.ProductType.SPARE_PART
                ),
                "short_description": short_desc,
                "description": short_desc,
                "brand": "",
                "sku": sku,
                "price": Decimal(price),
                "original_price": Decimal(original_price) if original_price else None,
                "stock": stock,
                "is_available": True,
                "is_active": True,
                "is_featured": featured,
                "is_new": is_new,
                "availability": "in_stock",
                "vehicle_makes": makes,
                "vehicle_models": models,
            }

            if dry_run:
                existing = Product.objects.filter(sku=sku).first()
                if existing is None:
                    created_count += 1
                else:
                    updated_count += 1
                if not existing or not existing.public_image:
                    missing_images.append(name)
                continue

            # Never clobber real prices a human has already entered. Match on SKU
            # first, then fall back to the same name so a hand-created product
            # is updated in place instead of colliding on the unique slug. Since
            # every product now carries an auto-generated SKU, match by name
            # alone (no longer requiring an empty SKU).
            existing = Product.objects.filter(sku=sku).first()
            if existing is None:
                existing = Product.objects.filter(name=name).first()
                # Preserve a hand-created product's auto-generated SKU.
                if existing is not None and existing.sku and existing.sku != sku:
                    defaults.pop("sku", None)

            # Never clobber real prices a human has already entered.
            if not force_prices and existing is not None and existing.price:
                price_kept += 1
                defaults["price"] = existing.price
                if existing.original_price is not None:
                    defaults["original_price"] = existing.original_price

            lookup = {"sku": sku} if existing is None or existing.sku == sku else {"pk": existing.pk}

            product, created = Product.objects.update_or_create(
                defaults=defaults, **lookup
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

            if not product.public_image:
                missing_images.append(product.name)

        verb = "would create" if dry_run else "created"
        vupd = "would update" if dry_run else "updated"
        self.stdout.write(
            f"Product groups: {len(groups)}   "
            f"Products {verb}: {created_count}   {vupd}: {updated_count}"
        )
        if price_kept:
            self.stdout.write(
                f"Existing prices preserved: {price_kept} "
                "(use --force-prices to overwrite)"
            )
        self.stdout.write(f"Sale items: {sum(1 for r in CATALOGUE if r[3])}")
        self.stdout.write(
            f"Featured: {sum(1 for r in CATALOGUE if r[5])}   "
            f"Total: {len(CATALOGUE)}"
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                f"Products WITHOUT an image ({len(missing_images)}) - the storefront "
                "shows its placeholder until real images are supplied:"
            )
        )
        for name in missing_images:
            self.stdout.write(f"  - {name}")
        self.stdout.write("")
        self.stdout.write(
            "Prices are realistic South African STARTER values, not official "
            "Ratshie pricing. Correct them in Django admin before launch."
        )
