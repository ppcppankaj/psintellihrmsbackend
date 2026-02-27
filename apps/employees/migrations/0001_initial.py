import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_initial'),
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=20)),
                ('description', models.TextField(blank=True)),
                ('cost_center', models.CharField(blank=True, max_length=50)),
                ('branch', models.ForeignKey(blank=True, help_text='Branch this department belongs to (null = organization-wide)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='departments', to='authentication.branch')),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Designation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=20)),
                ('description', models.TextField(blank=True)),
                ('level', models.PositiveSmallIntegerField(default=1)),
                ('grade', models.CharField(blank=True, max_length=20)),
                ('job_family', models.CharField(blank=True, max_length=50)),
                ('min_salary', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('max_salary', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Location',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=20)),
                ('address_line1', models.CharField(max_length=255)),
                ('address_line2', models.CharField(blank=True, max_length=255)),
                ('city', models.CharField(max_length=100)),
                ('state', models.CharField(max_length=100)),
                ('country', models.CharField(default='India', max_length=100)),
                ('postal_code', models.CharField(max_length=20)),
                ('latitude', models.DecimalField(blank=True, decimal_places=8, max_digits=10, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=8, max_digits=11, null=True)),
                ('geo_fence_radius', models.PositiveIntegerField(default=200)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('timezone', models.CharField(default='Asia/Kolkata', max_length=50)),
                ('is_headquarters', models.BooleanField(default=False)),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('employee_id', models.CharField(db_index=True, max_length=50)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('gender', models.CharField(blank=True, max_length=20)),
                ('marital_status', models.CharField(blank=True, choices=[('single', 'Single'), ('married', 'Married'), ('divorced', 'Divorced'), ('widowed', 'Widowed')], max_length=20)),
                ('blood_group', models.CharField(blank=True, max_length=5)),
                ('nationality', models.CharField(default='Indian', max_length=50)),
                ('employment_type', models.CharField(choices=[('full_time', 'Full Time'), ('part_time', 'Part Time'), ('contract', 'Contract'), ('intern', 'Intern'), ('consultant', 'Consultant')], default='full_time', max_length=20)),
                ('employment_status', models.CharField(choices=[('active', 'Active'), ('probation', 'Probation'), ('notice_period', 'Notice Period'), ('inactive', 'Inactive'), ('terminated', 'Terminated')], default='probation', max_length=20)),
                ('date_of_joining', models.DateField()),
                ('confirmation_date', models.DateField(blank=True, null=True)),
                ('probation_end_date', models.DateField(blank=True, null=True)),
                ('notice_period_days', models.PositiveSmallIntegerField(default=30)),
                ('date_of_exit', models.DateField(blank=True, null=True)),
                ('exit_reason', models.CharField(blank=True, max_length=100)),
                ('last_working_date', models.DateField(blank=True, null=True)),
                ('work_mode', models.CharField(choices=[('office', 'Office'), ('remote', 'Remote'), ('hybrid', 'Hybrid')], default='office', max_length=20)),
                ('pan_number', models.CharField(blank=True, db_index=True, max_length=255)),
                ('aadhaar_number', models.CharField(blank=True, db_index=True, max_length=255)),
                ('passport_number', models.CharField(blank=True, max_length=255)),
                ('passport_expiry', models.DateField(blank=True, null=True)),
                ('uan_number', models.CharField(blank=True, max_length=255)),
                ('pf_number', models.CharField(blank=True, max_length=255)),
                ('esi_number', models.CharField(blank=True, max_length=255)),
                ('bio', models.TextField(blank=True)),
                ('linkedin_url', models.URLField(blank=True)),
                ('branch', models.ForeignKey(blank=True, help_text='Physical branch/location where employee works', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='authentication.branch')),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='employees.department')),
                ('designation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='employees.designation')),
                ('hr_manager', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='hr_reports', to='employees.employee')),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='employees.location')),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
                ('reporting_manager', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='direct_reports', to='employees.employee')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='employee', to='authentication.user')),
            ],
            options={
                'ordering': ['employee_id'],
            },
        ),
        migrations.AddField(
            model_name='department',
            name='head',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='headed_departments', to='employees.employee'),
        ),
        migrations.AddField(
            model_name='department',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sub_departments', to='employees.department'),
        ),
        migrations.AddIndex(
            model_name='department',
            index=models.Index(fields=['organization', 'name'], name='idx_department_org_name'),
        ),
        migrations.AlterUniqueTogether(
            name='department',
            unique_together={('organization', 'code')},
        ),
        migrations.AlterUniqueTogether(
            name='designation',
            unique_together={('organization', 'code')},
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['employee_id'], name='employees_e_employe_080927_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['department', 'employment_status'], name='employees_e_departm_27a5fc_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['reporting_manager'], name='employees_e_reporti_77852f_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='employee',
            unique_together={('organization', 'employee_id')},
        ),
    ]
