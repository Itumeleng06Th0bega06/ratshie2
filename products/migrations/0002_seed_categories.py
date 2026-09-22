from django.db import migrations


def seed(apps, schema_editor):
    ProductCategory = apps.get_model("products", "ProductCategory")
    ProductCategory.objects.update_or_create(
        slug="spare-parts",
        defaults={
            "name": "Spare Parts",
            "description": (
                "Quality replacement parts, filters, brake components, belts, "
                "suspension and electrical parts for a wide range of vehicles."
            ),
            "sort_order": 1,
        },
    )
    ProductCategory.objects.update_or_create(
        slug="lubricants",
        defaults={
            "name": "Lubricants",
            "description": (
                "Engine oils, gearbox and transmission fluids, brake fluid, "
                "coolant and quality automotive lubricants."
            ),
            "sort_order": 2,
        },
    )


def unseed(apps, schema_editor):
    ProductCategory = apps.get_model("products", "ProductCategory")
    ProductCategory.objects.filter(slug__in=["spare-parts", "lubricants"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
