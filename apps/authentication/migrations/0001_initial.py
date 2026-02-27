import uuid
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_id', models.UUIDField(blank=True, db_index=True, help_text='Organization ID (denormalized for performance). Use OrganizationUser for source of truth.', null=True)),
                ('email', models.EmailField(db_index=True, max_length=254, unique=True)),
                ('username', models.CharField(blank=True, help_text='Legacy username (optional, not used for login)', max_length=255, null=True, unique=True)),
                ('employee_id', models.CharField(blank=True, db_index=True, max_length=50)),
                ('slug', models.SlugField(blank=True, help_text='URL-friendly identifier', max_length=100, unique=True)),
                ('first_name', models.CharField(max_length=50)),
                ('last_name', models.CharField(max_length=50)),
                ('middle_name', models.CharField(blank=True, max_length=50)),
                ('phone', models.CharField(blank=True, max_length=15)),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='avatars/')),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('gender', models.CharField(blank=True, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other'), ('prefer_not_to_say', 'Prefer not to say')], max_length=30)),
                ('is_active', models.BooleanField(default=True)),
                ('is_staff', models.BooleanField(default=False)),
                ('is_verified', models.BooleanField(default=False)),
                ('is_org_admin', models.BooleanField(db_index=True, default=False, help_text='User is an admin of their organization (can create/manage users within org)')),
                ('password_changed_at', models.DateTimeField(blank=True, null=True)),
                ('must_change_password', models.BooleanField(default=False)),
                ('failed_login_attempts', models.PositiveSmallIntegerField(default=0)),
                ('locked_until', models.DateTimeField(blank=True, null=True)),
                ('is_2fa_enabled', models.BooleanField(default=False)),
                ('two_factor_secret', models.CharField(blank=True, max_length=255)),
                ('backup_codes', models.JSONField(blank=True, default=list)),
                ('last_login_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('last_login_device', models.CharField(blank=True, max_length=255)),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('timezone', models.CharField(default='Asia/Kolkata', max_length=50)),
                ('language', models.CharField(default='en', max_length=10)),
                ('notification_preferences', models.JSONField(blank=True, default=dict)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'ordering': ['first_name', 'last_name'],
            },
        ),
        migrations.CreateModel(
            name='Branch',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_id', models.UUIDField(db_index=True, help_text='Parent organization ID')),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('code', models.CharField(blank=True, db_index=True, max_length=50)),
                ('branch_type', models.CharField(choices=[('headquarters', 'Headquarters'), ('regional', 'Regional Office'), ('branch', 'Branch Office'), ('remote', 'Remote/Virtual')], default='branch', help_text='Type of branch', max_length=50)),
                ('is_headquarters', models.BooleanField(default=False, help_text='Whether this is the primary headquarters')),
                ('address_line1', models.CharField(blank=True, max_length=255)),
                ('address_line2', models.CharField(blank=True, max_length=255)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=100)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('postal_code', models.CharField(blank=True, max_length=20)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_branches', to='authentication.user')),
            ],
            options={
                'db_table': 'branches',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='OrganizationUser',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_id', models.UUIDField(db_index=True, help_text='Organization ID')),
                ('role', models.CharField(choices=[('ORG_ADMIN', 'Organization Admin'), ('EMPLOYEE', 'Employee')], db_index=True, default='EMPLOYEE', max_length=20)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_org_memberships', to='authentication.user')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='organization_memberships', to='authentication.user')),
            ],
            options={
                'db_table': 'organization_users',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='BranchUser',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('role', models.CharField(choices=[('BRANCH_ADMIN', 'Branch Admin'), ('EMPLOYEE', 'Employee')], db_index=True, default='EMPLOYEE', max_length=20)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_memberships', to='authentication.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_branch_memberships', to='authentication.user')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_memberships', to='authentication.user')),
            ],
            options={
                'db_table': 'branch_users',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='user',
            unique_together={('organization_id', 'email')},
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['organization_id', 'email'], name='authenticat_organiz_91ea80_idx'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['organization_id', 'employee_id'], name='authenticat_organiz_6ec5c1_idx'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['organization_id', 'is_active', 'is_deleted'], name='authenticat_organiz_181dbb_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='organizationuser',
            unique_together={('user', 'organization_id')},
        ),
        migrations.AlterUniqueTogether(
            name='branchuser',
            unique_together={('user', 'branch')},
        ),
    ]
