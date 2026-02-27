from django.db import migrations, models
import django.db.models.deletion


def map_organization_uuid_to_fk(apps, schema_editor):
    """
    Preserve existing UUID values by resolving them against Organization.
    Values are written back as the same UUIDs prior to FK conversion.
    """
    Organization = apps.get_model('core', 'Organization')
    OrganizationUser = apps.get_model('authentication', 'OrganizationUser')
    Branch = apps.get_model('authentication', 'Branch')

    for membership in OrganizationUser.objects.all().iterator():
        old_uuid = membership.organization
        if not old_uuid:
            continue
        organization = Organization.objects.get(id=old_uuid)
        membership.organization = organization.id
        membership.save(update_fields=['organization'])

    for branch in Branch.objects.all().iterator():
        old_uuid = branch.organization
        if not old_uuid:
            continue
        organization = Organization.objects.get(id=old_uuid)
        branch.organization = organization.id
        branch.save(update_fields=['organization'])


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_emailverificationtoken_passwordresettoken_and_more'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='organizationuser',
            old_name='organization_id',
            new_name='organization',
        ),
        migrations.RenameField(
            model_name='branch',
            old_name='organization_id',
            new_name='organization',
        ),
        migrations.RunPython(
            map_organization_uuid_to_fk,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveIndex(
            model_name='branch',
            name='branches_organiz_8da68f_idx',
        ),
        migrations.RemoveIndex(
            model_name='organizationuser',
            name='organizatio_organiz_a637ab_idx',
        ),
        migrations.AlterField(
            model_name='organizationuser',
            name='organization',
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='organization_users',
                to='core.organization',
            ),
        ),
        migrations.AlterField(
            model_name='branch',
            name='organization',
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='branches',
                to='core.organization',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='organizationuser',
            unique_together={('user', 'organization')},
        ),
        migrations.AlterUniqueTogether(
            name='branch',
            unique_together={('organization', 'name')},
        ),
        migrations.AddIndex(
            model_name='branch',
            index=models.Index(fields=['organization', 'is_active'], name='branches_organiz_8da68f_idx'),
        ),
        migrations.AddIndex(
            model_name='organizationuser',
            index=models.Index(fields=['organization', 'role', 'is_active'], name='organizatio_organiz_a637ab_idx'),
        ),
    ]
