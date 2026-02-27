import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_initial'),
        ('authentication', '0001_initial'),
        ('employees', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Shift',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=20)),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('grace_in_minutes', models.PositiveSmallIntegerField(default=15)),
                ('grace_out_minutes', models.PositiveSmallIntegerField(default=15)),
                ('break_duration_minutes', models.PositiveSmallIntegerField(default=60)),
                ('working_hours', models.DecimalField(decimal_places=2, default=8.0, max_digits=4)),
                ('half_day_hours', models.DecimalField(decimal_places=2, default=4.0, max_digits=4)),
                ('overtime_allowed', models.BooleanField(default=False)),
                ('max_overtime_hours', models.DecimalField(decimal_places=2, default=4.0, max_digits=4)),
                ('is_night_shift', models.BooleanField(default=False)),
                ('branch', models.ForeignKey(blank=True, help_text='Branch this shift is for (null = organization-wide)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shifts', to='authentication.branch')),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='GeoFence',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('latitude', models.DecimalField(decimal_places=8, max_digits=10)),
                ('longitude', models.DecimalField(decimal_places=8, max_digits=11)),
                ('radius_meters', models.PositiveIntegerField(default=200)),
                ('is_primary', models.BooleanField(default=True)),
                ('branch', models.ForeignKey(blank=True, help_text='Branch this geofence belongs to', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='geo_fences', to='authentication.branch')),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='geo_fences', to='employees.location')),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
            ],
            options={
                'ordering': ['location', 'name'],
            },
        ),
        migrations.CreateModel(
            name='AttendanceRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('date', models.DateField()),
                ('clock_in', models.DateTimeField(blank=True, null=True)),
                ('clock_out', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('present', 'Present'), ('absent', 'Absent'), ('half_day', 'Half Day'), ('late', 'Late'), ('early_out', 'Early Out'), ('on_leave', 'On Leave'), ('holiday', 'Holiday')], default='absent', max_length=20)),
                ('total_hours', models.DecimalField(decimal_places=2, default=0.0, max_digits=5)),
                ('overtime_hours', models.DecimalField(decimal_places=2, default=0.0, max_digits=5)),
                ('is_regularized', models.BooleanField(default=False)),
                ('regularization_reason', models.TextField(blank=True)),
                ('branch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='authentication.branch')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='employees.employee')),
                ('organization', models.ForeignKey(blank=True, help_text='Organization this record belongs to (primary isolation key)', null=True, on_delete=django.db.models.deletion.CASCADE, to='core.organization')),
                ('shift', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='attendance.shift')),
            ],
            options={
                'ordering': ['-date', 'employee'],
            },
        ),
    ]
