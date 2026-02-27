import uuid
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, help_text='UUID - the ONLY key used for data isolation', primary_key=True, serialize=False)),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='organizations/logos/')),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('website', models.URLField(blank=True)),
                ('timezone', models.CharField(default='Asia/Kolkata', max_length=100)),
                ('currency', models.CharField(default='INR', max_length=3)),
                ('subscription_status', models.CharField(choices=[('trial', 'Trial'), ('active', 'Active'), ('past_due', 'Past Due'), ('cancelled', 'Cancelled'), ('suspended', 'Suspended')], db_index=True, default='trial', max_length=20)),
                ('trial_ends_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'organizations',
                'ordering': ['name'],
                'indexes': [models.Index(fields=['subscription_status', 'is_active'], name='organizatio_subscri_794bfa_idx')],
            },
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user_email', models.EmailField(blank=True, max_length=254, null=True)),
                ('action', models.CharField(db_index=True, max_length=50)),
                ('resource_type', models.CharField(db_index=True, max_length=100)),
                ('resource_id', models.CharField(db_index=True, max_length=100)),
                ('resource_repr', models.CharField(blank=True, max_length=255, null=True)),
                ('old_values', models.JSONField(blank=True, null=True)),
                ('new_values', models.JSONField(blank=True, null=True)),
                ('changed_fields', models.JSONField(blank=True, default=list)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True, null=True)),
                ('request_id', models.CharField(blank=True, max_length=100, null=True)),
                ('organization_id', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='FeatureFlag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_enabled', models.BooleanField(default=False)),
                ('enabled_for_all', models.BooleanField(default=False)),
                ('enabled_organizations', models.JSONField(blank=True, default=list)),
                ('enabled_users', models.JSONField(blank=True, default=list)),
                ('enabled_percentage', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Announcement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=255)),
                ('content', models.TextField()),
                ('priority', models.CharField(choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('urgent', 'Urgent')], default='normal', max_length=10)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('is_published', models.BooleanField(default=False)),
                ('is_pinned', models.BooleanField(default=False)),
                ('target_all', models.BooleanField(default=True)),
                ('target_departments', models.JSONField(blank=True, default=list)),
                ('target_branches', models.JSONField(blank=True, default=list)),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
            ],
            options={
                'ordering': ['-is_pinned', '-published_at'],
            },
        ),
        migrations.CreateModel(
            name='OrganizationSettings',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('date_format', models.CharField(choices=[('YYYY-MM-DD', 'YYYY-MM-DD'), ('DD/MM/YYYY', 'DD/MM/YYYY'), ('MM/DD/YYYY', 'MM/DD/YYYY'), ('DD-MM-YYYY', 'DD-MM-YYYY')], default='YYYY-MM-DD', max_length=20)),
                ('time_format', models.CharField(choices=[('12h', '12-hour'), ('24h', '24-hour')], default='24h', max_length=5)),
                ('week_start_day', models.PositiveSmallIntegerField(default=0)),
                ('enable_geofencing', models.BooleanField(default=False)),
                ('enable_face_recognition', models.BooleanField(default=False)),
                ('enable_biometric', models.BooleanField(default=False)),
                ('leave_approval_levels', models.PositiveSmallIntegerField(default=1)),
                ('expense_approval_levels', models.PositiveSmallIntegerField(default=1)),
                ('probation_period_days', models.PositiveIntegerField(default=90)),
                ('notice_period_days', models.PositiveIntegerField(default=30)),
                ('payroll_cycle_day', models.PositiveSmallIntegerField(default=1)),
                ('enable_auto_payroll', models.BooleanField(default=False)),
                ('branding_primary_color', models.CharField(default='#1976d2', max_length=7)),
                ('branding_secondary_color', models.CharField(default='#dc004e', max_length=7)),
                ('custom_settings', models.JSONField(blank=True, default=dict)),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
            ],
            options={
                'verbose_name_plural': 'Organization Settings',
            },
        ),
        migrations.AddIndex(
            model_name='announcement',
            index=models.Index(fields=['organization', 'is_published', '-published_at'], name='core_announ_organiz_2721f4_idx'),
        ),
    ]
