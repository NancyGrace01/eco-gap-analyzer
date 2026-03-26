import os
import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User




class Company(models.Model):
    name = models.CharField(max_length=255)
    sector = models.CharField(max_length=100, blank=True, null=True)
    industries = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees', null=True, blank=True)
    has_active_subscription = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.company.name if self.company else 'No Company'}"

class TeamInvitation(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    is_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Invite to {self.email} for {self.company.name}"
    
    

class AnalysisReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    document = models.FileField(upload_to='audit_docs/')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Status Flags
    is_processed = models.BooleanField(default=False)
    current_step = models.CharField(max_length=50, default="Initialized") # e.g., "Analyzing Keywords..."
    
    # Security Flags
    file_deleted = models.BooleanField(default=False)
    
    def check_and_delete_file(self):
        """Self-destruct logic (10 mins)"""
        if self.file_deleted: return
        if timezone.now() > self.created_at + timezone.timedelta(minutes=10):
            if self.document and os.path.isfile(self.document.path):
                os.remove(self.document.path)
                self.file_deleted = True
                self.save()

class AnalysisLayer(models.Model):
    report = models.ForeignKey(AnalysisReport, on_delete=models.CASCADE, related_name='layers')
    standard = models.CharField(max_length=50, default="GRI") 
    layer_type = models.CharField(max_length=50) 
    layer_score = models.IntegerField(default=0)
    summary_text = models.TextField(blank=True)
    

class LayerFinding(models.Model):
    layer = models.ForeignKey(AnalysisLayer, on_delete=models.CASCADE, related_name='findings')
    item = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True, null=True, default="-")
    status = models.CharField(max_length=100)
    details = models.TextField()
    recommendation = models.TextField(blank=True, null=True)
    
    # --- NEW FIELDS FOR INTERACTIVE UI (PHASE 3) ---
    page_number = models.CharField(max_length=50, blank=True, null=True)
    section_name = models.CharField(max_length=255, blank=True, null=True)
    status_breakdown = models.TextField(blank=True, null=True) 
    raw_excerpt = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.layer.layer_type} - {self.item}"
    
    
class XBRLComparison(models.Model):
    """Handles the strict XBRL vs Taxonomy matching."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    # The document the user wants to test
    user_document = models.FileField(upload_to='xbrl_uploads/')
    
    # Reference selection (GRI, IFRS S1, IFRS S2, or Custom)
    reference_standard = models.CharField(max_length=50, default='GRI') 
    custom_reference = models.FileField(upload_to='xbrl_references/', null=True, blank=True)
    
    # Store the JSON results of the comparison
    is_processed = models.BooleanField(default=False)
    results_data = models.JSONField(null=True, blank=True)
    compliance_score = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)


class ComparativeReport(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comparisons', null=True, blank=True)
    base_report = models.ForeignKey(AnalysisReport, related_name='base_for_comparisons', on_delete=models.CASCADE)
    new_report = models.ForeignKey(AnalysisReport, related_name='new_for_comparisons', on_delete=models.CASCADE)
    executive_summary = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comparison: {self.base_report.id} vs {self.new_report.id}"

class ComparativeFinding(models.Model):
    TREND_CHOICES = [
        ('Improved', 'Improved'),
        ('Regressed', 'Regressed'),
        ('Unchanged', 'Unchanged'),
        ('New Gap', 'New Gap')
    ]
    
    comparative_report = models.ForeignKey(ComparativeReport, on_delete=models.CASCADE, related_name='findings')
    framework = models.CharField(max_length=50)  # e.g., 'GRI', 'IFRS S1'
    requirement = models.CharField(max_length=255)
    base_status = models.CharField(max_length=100)
    new_status = models.CharField(max_length=100)
    trend = models.CharField(max_length=50, choices=TREND_CHOICES)
    ai_analysis = models.TextField() # Explains the exact delta/change between the years

    def __str__(self):
        return f"{self.framework} - {self.trend} - {self.requirement}"