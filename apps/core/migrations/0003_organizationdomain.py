from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        (
            "core",
            "0002_rename_core_announ_organiz_2721f4_idx_core_announ_organiz_f158c6_idx_and_more",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationDomain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("domain_name", models.CharField(max_length=255, unique=True)),
                ("is_primary", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domains",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["domain_name"],
                "verbose_name": "Organization Domain",
                "verbose_name_plural": "Organization Domains",
            },
        ),
        migrations.AddIndex(
            model_name="organizationdomain",
            index=models.Index(fields=["organization", "is_primary"], name="core_orgdomain_primary_idx"),
        ),
        migrations.AddIndex(
            model_name="organizationdomain",
            index=models.Index(fields=["domain_name"], name="core_orgdomain_domain_idx"),
        ),
    ]
