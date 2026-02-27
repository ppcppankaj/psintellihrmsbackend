# Generated manually to support notification hardening
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='delivery_attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='notification',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='notification',
            name='priority',
            field=models.CharField(choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('critical', 'Critical')], default='normal', max_length=10),
        ),
        migrations.AddField(
            model_name='notification',
            name='scheduled_for',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='notification',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('scheduled', 'Scheduled'), ('sent', 'Sent'), ('delivered', 'Delivered'), ('read', 'Read'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
    ]
