"""Migration enabling GST-compliant invoices."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
import django.db.models.deletion


def populate_invoice_defaults(apps, schema_editor):  # pragma: no cover - data backfill
	Invoice = apps.get_model('billing', 'Invoice')
	for invoice in Invoice.objects.select_related('subscription__plan', 'organization'):
		updated_fields = []

		if getattr(invoice, 'plan_id', None) is None and invoice.subscription_id:
			invoice.plan_id = getattr(invoice.subscription, 'plan_id', None)
			if invoice.plan_id:
				updated_fields.append('plan')

		if not getattr(invoice, 'billing_name', None):
			organization = invoice.organization
			invoice.billing_name = getattr(organization, 'name', '') or 'Billing Contact'
			updated_fields.append('billing_name')

		if getattr(invoice, 'billing_address', None) is None:
			invoice.billing_address = ''
			updated_fields.append('billing_address')

		if getattr(invoice, 'gstin', None) is None:
			invoice.gstin = ''
			updated_fields.append('gstin')

		if not getattr(invoice, 'generated_at', None):
			invoice.generated_at = timezone.now()
			updated_fields.append('generated_at')

		if invoice.paid_status not in ('pending', 'paid', 'overdue'):
			invoice.paid_status = 'pending'
			updated_fields.append('paid_status')

		if updated_fields:
			invoice.save(update_fields=updated_fields)


def noop_reverse(apps, schema_editor):  # pragma: no cover - backward noop
	del apps, schema_editor


class Migration(migrations.Migration):

	dependencies = [
		('billing', '0002_paymenttransaction'),
	]

	operations = [
		migrations.CreateModel(
			name='OrganizationBillingProfile',
			fields=[
				('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
				('updated_at', models.DateTimeField(auto_now=True)),
				('is_deleted', models.BooleanField(db_index=True, default=False)),
				('deleted_at', models.DateTimeField(blank=True, null=True)),
				('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
				('is_active', models.BooleanField(db_index=True, default=True)),
				('legal_name', models.CharField(max_length=255)),
				('billing_address', models.TextField(blank=True)),
				('gstin', models.CharField(blank=True, max_length=15)),
				('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
				('deleted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_deleted', to=settings.AUTH_USER_MODEL)),
				('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
				('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
			],
			options={
				'verbose_name': 'Organization Billing Profile',
				'verbose_name_plural': 'Organization Billing Profiles',
			},
		),
		migrations.AddConstraint(
			model_name='organizationbillingprofile',
			constraint=models.UniqueConstraint(fields=('organization',), name='uq_billing_profile_per_org'),
		),
		migrations.RenameField(
			model_name='invoice',
			old_name='tax',
			new_name='gst_amount',
		),
		migrations.RenameField(
			model_name='invoice',
			old_name='total',
			new_name='total_amount',
		),
		migrations.RenameField(
			model_name='invoice',
			old_name='status',
			new_name='paid_status',
		),
		migrations.RemoveField(
			model_name='invoice',
			name='billing_period_start',
		),
		migrations.RemoveField(
			model_name='invoice',
			name='billing_period_end',
		),
		migrations.AddField(
			model_name='invoice',
			name='billing_address',
			field=models.TextField(blank=True, default=''),
			preserve_default=False,
		),
		migrations.AddField(
			model_name='invoice',
			name='billing_name',
			field=models.CharField(default='', max_length=255),
			preserve_default=False,
		),
		migrations.AddField(
			model_name='invoice',
			name='generated_at',
			field=models.DateTimeField(default=timezone.now),
			preserve_default=False,
		),
		migrations.AddField(
			model_name='invoice',
			name='gst_percentage',
			field=models.DecimalField(decimal_places=2, default=Decimal('18.00'), max_digits=5),
		),
		migrations.AddField(
			model_name='invoice',
			name='gstin',
			field=models.CharField(blank=True, default='', max_length=15),
			preserve_default=False,
		),
		migrations.AddField(
			model_name='invoice',
			name='plan',
			field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='invoices', to='billing.plan'),
		),
		migrations.AlterField(
			model_name='invoice',
			name='gst_amount',
			field=models.DecimalField(decimal_places=2, max_digits=10),
		),
		migrations.AlterField(
			model_name='invoice',
			name='paid_status',
			field=models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('overdue', 'Overdue')], default='pending', max_length=20),
		),
		migrations.AlterField(
			model_name='invoice',
			name='subscription',
			field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='billing.organizationsubscription'),
		),
		migrations.AlterField(
			model_name='invoice',
			name='total_amount',
			field=models.DecimalField(decimal_places=2, max_digits=10),
		),
		migrations.RunPython(populate_invoice_defaults, noop_reverse),
		migrations.AlterField(
			model_name='invoice',
			name='generated_at',
			field=models.DateTimeField(auto_now_add=True),
		),
		migrations.AlterField(
			model_name='invoice',
			name='plan',
			field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invoices', to='billing.plan'),
		),
	]
