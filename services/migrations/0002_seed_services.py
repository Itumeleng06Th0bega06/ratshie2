from django.db import migrations

SERVICES = [
    {
        "name": "Mechanical Repairs & Diagnostics",
        "slug": "mechanical-repairs-diagnostics",
        "short_description": "Skilled mechanical repairs and accurate diagnostics to get you back on the road.",
        "icon": "engine",
        "sort_order": 1,
        "is_featured": True,
    },
    {
        "name": "Car Parts, Lubricants & Accessories",
        "slug": "car-parts-lubricants-accessories",
        "short_description": "Quality spare parts, lubricants and accessories for a wide range of vehicles.",
        "icon": "gearbox",
        "sort_order": 2,
        "is_featured": True,
    },
    {
        "name": "Mobile Spares Delivery",
        "slug": "mobile-spares-delivery",
        "short_description": "Mobile spares delivery within 50 km - the parts you need, delivered to you.",
        "icon": "truck",
        "sort_order": 3,
        "is_featured": True,
    },
    {
        "name": "Emergency Support & Roadside Delivery",
        "slug": "emergency-support-roadside-delivery",
        "short_description": "Emergency support and roadside parts delivery when you need it most.",
        "icon": "wrench",
        "sort_order": 4,
        "is_featured": True,
    },
]


def seed(apps, schema_editor):
    Service = apps.get_model("services", "Service")
    for svc in SERVICES:
        Service.objects.update_or_create(slug=svc["slug"], defaults=svc)


def unseed(apps, schema_editor):
    Service = apps.get_model("services", "Service")
    Service.objects.filter(slug__in=[s["slug"] for s in SERVICES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
