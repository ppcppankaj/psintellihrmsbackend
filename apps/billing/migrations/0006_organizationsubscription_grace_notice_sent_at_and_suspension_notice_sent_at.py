from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0005_organizationsubscription_expired_notice_sent_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationsubscription",
            name="grace_notice_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="organizationsubscription",
            name="suspension_notice_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
