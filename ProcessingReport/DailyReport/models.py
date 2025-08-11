from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

class ProjectAccess(models.Model):
    PROJECT_TYPES = [
        ('ground mount', 'Ground Mount'),
        ('roof top', 'Roof Top'),
        ('bess', 'BESS'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    project_name = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    type_of_project = models.CharField(max_length=20, choices=PROJECT_TYPES)
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project_name} -> {self.user.username}"


class Section(models.Model):
    project = models.ForeignKey(ProjectAccess, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.title


class ProgressItem(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="items", null=True)
    description = models.CharField(max_length=255)
    uom = models.CharField(max_length=50)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    scope = models.FloatField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    scope_assigned_date = models.DateField(null=True, blank=True)
    scope_completed_date = models.DateField(null=True, blank=True)
    targeted_start_date = models.DateField(null=True, blank=True)
    targeted_end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.description

    def total_progress(self):
        return sum(entry.progress_done for entry in self.entries.all())

    def remaining_balance(self):
        return max(self.scope - self.total_progress(), 0) if self.scope else 0

    def expected_per_day(self):
        if self.scope and self.targeted_start_date and self.targeted_end_date:
            days = (self.targeted_end_date - self.targeted_start_date).days + 1
            if days > 0:
                return round(self.scope / days, 2)
        return 0
    
    def set_auto_dates_if_missing(self):
        today = timezone.now().date()

        if not self.scope_assigned_date:
            if self.targeted_start_date and self.targeted_start_date <= today:
                self.scope_assigned_date = self.targeted_start_date
            else:
                self.scope_assigned_date = today

        total_done = self.entries.aggregate(total=models.Sum('progress_done'))['total'] or 0
        if self.scope and total_done >= self.scope and not self.scope_completed_date:
            self.scope_completed_date = today

    def get_status(self):
        today = timezone.now().date()
        total_done = self.entries.aggregate(total=models.Sum('progress_done'))['total'] or 0

        # No target date → can't check
        if not self.targeted_end_date:
            return 'Missing Dates'

        # If completed
        if self.scope and total_done >= self.scope:
            if self.scope_completed_date:
                # Compare stored completion date
                return 'Ontime' if self.scope_completed_date <= self.targeted_end_date else 'Delay'
            else:
                # No stored date, but progress shows completed → assume today
                # return 'In Progress' if today <= self.targeted_end_date else 'Delay'
                return 'Ontime' if today <= self.targeted_end_date else 'Delay'

        # Not completed
        return 'Ontime' if today <= self.targeted_end_date else 'Delay'





class ProgressEntry(models.Model):
    item = models.ForeignKey(ProgressItem, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    progress_done = models.FloatField()

    class Meta:
        unique_together = ('item', 'date')
        ordering = ['date']
