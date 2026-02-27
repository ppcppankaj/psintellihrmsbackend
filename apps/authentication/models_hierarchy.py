"""
Hierarchical Multi-Tenancy Models
Organization → User → Branch

This module defines the mapping models for hierarchical access control.
"""

import uuid
from django.db import models
from django.core.exceptions import ValidationError


class OrganizationUser(models.Model):
    """
    User-Organization Assignment Model
    
    Defines the relationship between a User and an Organization.
    A user can belong to ONE organization only.
    """
    
    class RoleChoices(models.TextChoices):
        ORG_ADMIN = 'ORG_ADMIN', 'Organization Admin'
        EMPLOYEE = 'EMPLOYEE', 'Employee'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='organization_memberships',
        db_index=True
    )
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        db_index=True,
        related_name='organization_users'
    )
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.EMPLOYEE,
        db_index=True
    )
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_org_memberships'
    )
    
    class Meta:
        db_table = 'organization_users'
        unique_together = [('user', 'organization')]
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['organization', 'role', 'is_active'], name='organizatio_organiz_a637ab_idx'),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.organization_id} ({self.get_role_display()})"

    @property
    def user_email(self):
        return self.user.email if self.user_id else None

    @property
    def user_name(self):
        return self.user.full_name if self.user_id else None
    
    def clean(self):
        """
        Validation: User can only belong to ONE organization
        """
        if self.pk is None:  # New instance
            # Check if user already has an organization
            existing = OrganizationUser.objects.filter(
                user=self.user,
                is_active=True
            ).exclude(pk=self.pk).exists()
            
            if existing:
                raise ValidationError(
                    f"User {self.user.email} is already assigned to an organization. "
                    "A user can only belong to one organization."
                )
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Branch(models.Model):
    """
    Branch Model - Child of Organization
    
    Represents a physical location or division within an organization.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        db_index=True,
        related_name='branches'
    )
    
    # Basic Info
    name = models.CharField(max_length=255, db_index=True)
    code = models.CharField(max_length=50, blank=True, db_index=True)
    
    # Branch classification
    branch_type = models.CharField(
        max_length=50,
        choices=[
            ('headquarters', 'Headquarters'),
            ('regional', 'Regional Office'),
            ('branch', 'Branch Office'),
            ('remote', 'Remote/Virtual'),
        ],
        default='branch',
        help_text="Type of branch"
    )
    is_headquarters = models.BooleanField(
        default=False,
        help_text="Whether this is the primary headquarters"
    )
    
    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    
    # Contact
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_branches'
    )
    
    class Meta:
        db_table = 'branches'
        unique_together = [('organization', 'name')]
        indexes = [
            models.Index(fields=['organization', 'is_active'], name='branches_organiz_8da68f_idx'),
            models.Index(fields=['name', 'is_active']),
        ]
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.organization_id})"


class BranchUser(models.Model):
    """
    User-Branch Assignment Model
    
    Defines the relationship between a User and a Branch.
    Users can be assigned to multiple branches within the same organization.
    """
    
    class RoleChoices(models.TextChoices):
        BRANCH_ADMIN = 'BRANCH_ADMIN', 'Branch Admin'
        EMPLOYEE = 'EMPLOYEE', 'Employee'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='branch_memberships',
        db_index=True
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='user_memberships',
        db_index=True
    )
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.EMPLOYEE,
        db_index=True
    )
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_branch_memberships'
    )
    
    class Meta:
        db_table = 'branch_users'
        unique_together = [('user', 'branch')]
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['branch', 'role', 'is_active']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.branch.name} ({self.get_role_display()})"

    @property
    def user_email(self):
        return self.user.email if self.user_id else None

    @property
    def user_name(self):
        return self.user.full_name if self.user_id else None
    
    def clean(self):
        """
        Validation: User must belong to the same organization as the branch
        """
        if self.user_id and self.branch_id:
            # Get user's organization
            try:
                org_membership = OrganizationUser.objects.get(
                    user=self.user,
                    is_active=True
                )
                
                # Check if branch belongs to same organization
                if self.branch.organization != org_membership.organization:
                    raise ValidationError(
                        f"User {self.user.email} belongs to organization "
                        f"{org_membership.organization.name}, but branch {self.branch.name} "
                        f"belongs to {self.branch.organization.name}. Cannot assign user to "
                        "branch in different organization."
                    )
            except OrganizationUser.DoesNotExist:
                raise ValidationError(
                    f"User {self.user.email} must be assigned to an organization "
                    "before being assigned to a branch."
                )
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
