# Generated to extend workflow action audit coverage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workflows', '0002_alter_workflowaction_organization_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workflowaction',
            name='action',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                    ('forwarded', 'Forwarded'),
                    ('delegated', 'Delegated'),
                    ('escalated', 'Escalated'),
                    ('started', 'Started'),
                    ('auto_approved', 'Auto Approved'),
                    ('auto_rejected', 'Auto Rejected'),
                ],
            ),
        ),
    ]
