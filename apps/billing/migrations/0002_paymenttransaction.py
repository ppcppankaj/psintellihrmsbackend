"""Align legacy billing schema and introduce payment transactions."""
import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        # --- Subscription → OrganizationSubscription ---------------------------------
        migrations.RenameModel(
            old_name='Subscription',
            new_name='OrganizationSubscription',
        ),
        migrations.RenameField(
            model_name='organizationsubscription',
            old_name='end_date',
            new_name='expiry_date',
        ),
        migrations.RemoveField(
            model_name='organizationsubscription',
            name='billing_cycle',
        ),
        migrations.RemoveField(
            model_name='organizationsubscription',
            name='next_billing_date',
        ),
        migrations.RemoveField(
            model_name='organizationsubscription',
            name='payment_method',
        ),
        migrations.RemoveField(
            model_name='organizationsubscription',
            name='price',
        ),
        migrations.RemoveField(
            model_name='organizationsubscription',
            name='status',
        ),
        migrations.AddField(
            model_name='organizationsubscription',
            name='is_trial',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='organizationsubscription',
            name='trial_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='organizationsubscription',
            name='organization',
            field=models.ForeignKey(
                blank=True,
                help_text='Organization this record belongs to (primary isolation key)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='core.organization',
            ),
        ),
        migrations.AlterField(
            model_name='organizationsubscription',
            name='plan',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='subscriptions',
                to='billing.plan',
            ),
        ),
        migrations.AddConstraint(
            model_name='organizationsubscription',
            constraint=models.UniqueConstraint(
                fields=('organization',),
                condition=Q(('is_active', True)),
                name='uq_active_subscription_per_org',
            ),
        ),
        # --- Plan field updates -------------------------------------------------------
        migrations.RenameField(
            model_name='plan',
            old_name='price_monthly',
            new_name='monthly_price',
        ),
        migrations.RenameField(
            model_name='plan',
            old_name='price_yearly',
            new_name='yearly_price',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='features',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='is_trial',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='max_admins',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='trial_days',
        ),
        migrations.AddField(
            model_name='plan',
            name='max_branches',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='plan',
            name='storage_limit',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Storage limit in MB for uploaded documents',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='plan',
            name='attendance_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='plan',
            name='document_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='plan',
            name='helpdesk_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='plan',
            name='payroll_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='plan',
            name='recruitment_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='plan',
            name='timesheet_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='plan',
            name='workflow_enabled',
            field=models.BooleanField(default=True),
        ),
        # --- Razorpay payment transactions -------------------------------------------
        migrations.CreateModel(
            name='PaymentTransaction',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('currency', models.CharField(default='INR', max_length=10)),
                (
                    'status',
                    models.CharField(
                        choices=[('created', 'Created'), ('success', 'Success'), ('failed', 'Failed')],
                        default='created',
                        max_length=20,
                    ),
                ),
                ('razorpay_order_id', models.CharField(blank=True, max_length=100)),
                ('razorpay_payment_id', models.CharField(blank=True, max_length=100)),
                ('razorpay_signature', models.CharField(blank=True, max_length=255)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                (
                    'created_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='%(class)s_created',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'deleted_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='%(class)s_deleted',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'organization',
                    models.ForeignKey(
                        blank=True,
                        help_text='Organization this record belongs to (primary isolation key)',
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to='core.organization',
                    ),
                ),
                (
                    'plan',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='payment_transactions',
                        to='billing.plan',
                    ),
                ),
                (
                    'subscription',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='payment_transactions',
                        to='billing.organizationsubscription',
                    ),
                ),
                (
                    'updated_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='%(class)s_updated',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
