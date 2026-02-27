"""
Asset Management Models
"""

from django.db import models
from django.conf import settings
from apps.core.models import OrganizationEntity


class AssetCategory(OrganizationEntity):
    """Asset categories (e.g., Laptop, Phone, Vehicle)"""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Icon name for UI")
    
    class Meta:
        verbose_name_plural = "Asset Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Asset(OrganizationEntity):
    """Individual company assets"""
    
    # Status choices
    AVAILABLE = 'available'
    ASSIGNED = 'assigned'
    MAINTENANCE = 'maintenance'
    RETIRED = 'retired'
    
    STATUS_CHOICES = [
        (AVAILABLE, 'Available'),
        (ASSIGNED, 'Assigned'),
        (MAINTENANCE, 'In Maintenance'),
        (RETIRED, 'Retired'),
    ]
    
    # Basic info
    name = models.CharField(max_length=200)
    asset_tag = models.CharField(max_length=50, unique=True, help_text="Unique asset identifier")
    serial_number = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    
    # Classification
    category = models.ForeignKey(
        AssetCategory, 
        on_delete=models.PROTECT, 
        related_name='assets'
    )
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='assets',
        help_text="Branch this asset belongs to"
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=AVAILABLE)
    
    # Purchase info
    purchase_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vendor = models.CharField(max_length=200, blank=True)
    warranty_expires = models.DateField(null=True, blank=True)
    
    # Current assignment
    current_assignee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_assets'
    )
    
    # Location
    location = models.CharField(max_length=200, blank=True)
    
    # Additional
    notes = models.TextField(blank=True)
    image = models.ImageField(upload_to='assets/', null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.asset_tag} - {self.name}"
    
    def assign_to(self, employee, assigned_by=None, notes=''):
        """Assign asset to an employee"""
        from apps.employees.models import Employee
        
        # Create assignment record
        assignment = AssetAssignment.objects.create(
            asset=self,
            employee=employee,
            assigned_by=assigned_by,
            notes=notes
        )
        
        # Update asset status
        self.current_assignee = employee
        self.status = self.ASSIGNED
        self.save()
        
        return assignment
    
    def unassign(self, returned_by=None, notes=''):
        """Return asset from current assignee"""
        if self.current_assignee:
            # Update latest assignment
            assignment = self.assignments.filter(
                employee=self.current_assignee,
                returned_date__isnull=True
            ).first()
            
            if assignment:
                from django.utils import timezone
                assignment.returned_date = timezone.now().date()
                assignment.return_notes = notes
                assignment.save()
        
        self.current_assignee = None
        self.status = self.AVAILABLE
        self.save()


class AssetAssignment(OrganizationEntity):
    """Track asset assignment history"""
    
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='asset_assignments'
    )
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='asset_assignments',
        help_text="Branch where asset was assigned"
    )
    
    # Assignment details
    assigned_date = models.DateField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assets_assigned'
    )
    notes = models.TextField(blank=True)
    
    # Return details
    returned_date = models.DateField(null=True, blank=True)
    return_notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-assigned_date']
    
    def __str__(self):
        return f"{self.asset.name} → {self.employee}"
    
    @property
    def is_active(self):
        return self.returned_date is None


class AssetMaintenance(OrganizationEntity):
    """Track asset maintenance records"""
    
    SCHEDULED = 'scheduled'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (SCHEDULED, 'Scheduled'),
        (IN_PROGRESS, 'In Progress'),
        (COMPLETED, 'Completed'),
        (CANCELLED, 'Cancelled'),
    ]
    
    PREVENTIVE = 'preventive'
    CORRECTIVE = 'corrective'
    EMERGENCY = 'emergency'
    
    TYPE_CHOICES = [
        (PREVENTIVE, 'Preventive'),
        (CORRECTIVE, 'Corrective'),
        (EMERGENCY, 'Emergency'),
    ]
    
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='maintenance_records'
    )
    
    maintenance_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=CORRECTIVE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=SCHEDULED)
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    scheduled_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vendor = models.CharField(max_length=200, blank=True)
    
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_performed'
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-scheduled_date']
    
    def __str__(self):
        return f"{self.asset.asset_tag} - {self.title}"


class AssetRequest(OrganizationEntity):
    """Employee asset requests"""
    
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    FULFILLED = 'fulfilled'
    CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
        (FULFILLED, 'Fulfilled'),
        (CANCELLED, 'Cancelled'),
    ]
    
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='asset_requests'
    )
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requests'
    )
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    justification = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    
    requested_date = models.DateField(auto_now_add=True)
    needed_by = models.DateField(null=True, blank=True)
    
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asset_requests_reviewed'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    fulfilled_asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fulfilled_requests'
    )
    
    class Meta:
        ordering = ['-requested_date']
    
    def __str__(self):
        return f"{self.employee} - {self.title}"
    
    def approve(self, reviewer, notes=''):
        from django.utils import timezone
        self.status = self.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()
    
    def reject(self, reviewer, notes=''):
        from django.utils import timezone
        self.status = self.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()
    
    def fulfill(self, asset, reviewer=None):
        from django.utils import timezone
        self.status = self.FULFILLED
        self.fulfilled_asset = asset
        if reviewer:
            self.reviewed_by = reviewer
            self.reviewed_at = timezone.now()
        self.save()
