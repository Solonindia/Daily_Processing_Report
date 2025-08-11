from django.contrib.auth import login, authenticate
from django.shortcuts import render, redirect
from .forms import CustomUserCreationForm 
from django.http import HttpResponseForbidden
from django.contrib.auth import views as auth_views
from django.contrib import messages

# Create your views here.
def home_page(request):
    return render(request, 'home_page.html')

def redirect_to_home(request):
    return redirect('home')

def user_login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('user')  
        else:
            return render(request, 'user_login.html', {'error_message': 'Invalid credentials'})
    return render(request, 'user_login.html')

def admin_login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_superuser:
            login(request, user)
            return redirect('admin')  
        else:
            return render(request, 'admin_login.html', {'error_message': 'Invalid credentials'})

    return render(request, 'admin_login.html')

def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, 'register.html', {'success_message': 'User created successfully'})
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})

def admin_page(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access Denied: You do not have admin privileges.")
    
    return render(request, 'admin.html')

def user_page(request):
    # Restrict access to superusers
    if request.user.is_superuser:
        return HttpResponseForbidden("Access Denied: This page is for users only.")
    
    # Render the user page with site information
    return render(request, 'user.html')

class CustomLogoutView(auth_views.LogoutView):
    def dispatch(self, request, *args, **kwargs):
        messages.success(request, "Logout successful")
        return super().dispatch(request, *args, **kwargs)


from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from .models import ProjectAccess
from django.contrib.auth.models import User

@login_required
def assign_project_access(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access Denied: Admins only.")

    if request.method == 'POST':
        project_name = request.POST.get('project_name')
        username = request.POST.get('user_name')
        location = request.POST.get('location')
        project_type = request.POST.get('type_of_project')

        if not all([project_name, username, location, project_type]):
            messages.error(request, "All fields are required.")
        else:
            try:
                user = User.objects.get(username=username)
                ProjectAccess.objects.create(
                    user=user,
                    project_name=project_name,
                    location=location,
                    type_of_project=project_type
                )
                messages.success(request, f"Project '{project_name}' assigned to {username}.")
                return redirect('assign_project_access')
            except User.DoesNotExist:
                messages.error(request, "User does not exist.")

    return render(request, 'admin_assign_project.html')




from datetime import datetime
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.db.models import Sum
from .models import ProjectAccess, Section, ProgressItem
import json,math


@login_required
def admin_project_sections(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Admins only.")

    project_access_list = ProjectAccess.objects.all()
    selected_project_id = request.GET.get('project_id')
    sections_data = []
    today = timezone.now().date()

    def format_date(date_obj):
        return date_obj.strftime("%d-%m-%Y") if date_obj else ''

    # 1. Load data to render
    if selected_project_id:
        try:
            project = ProjectAccess.objects.get(id=selected_project_id)
            sections = Section.objects.filter(project=project).prefetch_related("items__entries")

            for sec in sections:
                section_items = []

                for item in item_sort(sec.items.all()):
                    expected_today = 'N/A'
                    today_progress = 0
                    completed = 0
                    balance = 'N/A'
                    status = 'Missing Dates'

                    if item.targeted_start_date and item.targeted_end_date and item.scope is not None:
                        done_so_far = item.entries.filter(
                            date__lt=today
                        ).aggregate(total=Sum('progress_done'))['total'] or 0

                        today_entry = item.entries.filter(
                            date=today
                        ).order_by('-id').first()

                        today_progress = today_entry.progress_done if today_entry else 0
                        completed = done_so_far + today_progress
                        balance = max(item.scope - completed, 0)

                        expected_balance = max(item.scope - done_so_far, 0)
                        remaining_days = (item.targeted_end_date - today).days + 1

                        # expected_today = round(expected_balance / remaining_days, 2) if remaining_days > 0 else expected_balance
                        expected_today = math.ceil(expected_balance / remaining_days) if remaining_days > 0 else expected_balance
                        # status = 'Ontime' if today <= item.targeted_end_date else 'Delay'
                        status = item.get_status()

                    section_items.append({
                        'id': item.id,
                        'description': item.description,
                        'uom': item.uom,
                        'order': item.order,
                        'scope': item.scope,
                        'targeted_start_date': format_date(item.targeted_start_date),
                        'targeted_end_date': format_date(item.targeted_end_date),
                        'expected_today': expected_today,
                        'today_progress': today_progress,
                        'completed': completed,
                        'balance': balance,
                        'status': status,
                        'actual_start_date': format_date(item.scope_assigned_date),  # ✅ Replaced
                        'actual_end_date': format_date(item.scope_completed_date),  # ✅ Replaced
                    })

                sections_data.append({
                    'id': sec.id,
                    'title': sec.title,
                    'items': section_items,
                })
        except ProjectAccess.DoesNotExist:
            messages.error(request, "Invalid project.")

    # 2. Handle Save
    if request.method == 'POST':
        project_id = request.POST.get('project_id')
        project = get_object_or_404(ProjectAccess, id=project_id)

        total_sections = int(request.POST.get('total_sections', 0))
        submitted_section_ids = []
        submitted_item_ids = []

        for idx in range(total_sections):
            section_id = request.POST.get(f'section_id_{idx}')
            title = request.POST.get(f'section_title_{idx}').strip()
            if not title:
                continue

            if section_id:
                section = get_object_or_404(Section, id=section_id, project=project)
                section.title = title
                section.save()
            else:
                section = Section.objects.create(project=project, title=title, created_by=request.user)

            submitted_section_ids.append(section.id)

            descriptions = request.POST.getlist(f'description_{idx}[]')
            uoms = request.POST.getlist(f'uom_{idx}[]')
            scopes = request.POST.getlist(f'scope_{idx}[]')
            item_ids = request.POST.getlist(f'item_id_{idx}[]')
            targeted_starts = request.POST.getlist(f'targeted_start_date_{idx}[]')
            targeted_ends = request.POST.getlist(f'targeted_end_date_{idx}[]')

            for order_index, (desc, uom, scope, start_str, end_str) in enumerate(zip(descriptions, uoms, scopes, targeted_starts, targeted_ends)):
                desc = desc.strip()
                uom = uom.strip()
                scope = float(scope) if scope.strip() else None

                def parse_date(dstr):
                    try:
                        return datetime.strptime(dstr.strip(), "%d-%m-%Y").date() if dstr.strip() else None
                    except ValueError:
                        return None

                targeted_start = parse_date(start_str)
                targeted_end = parse_date(end_str)

                if not desc:
                    continue

                item_id = item_ids[order_index] if order_index < len(item_ids) else None

                if item_id:
                    item = get_object_or_404(ProgressItem, id=item_id, section=section)
                    item.description = desc
                    item.uom = uom
                    item.scope = scope
                    item.order = order_index
                    item.targeted_start_date = targeted_start
                    item.targeted_end_date = targeted_end
                    item.save()
                else:
                    item = ProgressItem.objects.create(
                        section=section,
                        description=desc,
                        uom=uom,
                        scope=scope,
                        order=order_index,
                        targeted_start_date=targeted_start,
                        targeted_end_date=targeted_end,
                        created_by=request.user
                    )

                submitted_item_ids.append(item.id)

        Section.objects.filter(project=project).exclude(id__in=submitted_section_ids).delete()
        ProgressItem.objects.filter(section__project=project).exclude(id__in=submitted_item_ids).delete()

        messages.success(request, "Sections and items updated.")
        return redirect(f"{reverse('admin_project_sections')}?project_id={project_id}")

    return render(request, 'admin_project_sections.html', {
        'project_access_list': project_access_list,
        'selected_project_id': selected_project_id,
        'sections_data': json.dumps(sections_data)
    })


def item_sort(items):
    return sorted(items, key=lambda x: x.order if x.order is not None else 0)




# from django.contrib.auth.decorators import login_required
# from django.shortcuts import render, redirect
# from django.http import HttpResponseForbidden
# from django.utils import timezone
# from django.db.models import Sum
# from .models import ProjectAccess, Section, ProgressItem, ProgressEntry

# @login_required
# def user_project_sections(request):
#     if request.user.is_superuser:
#         return HttpResponseForbidden("Admins only.")

#     try:
#         project = ProjectAccess.objects.get(user=request.user)
#     except ProjectAccess.DoesNotExist:
#         return render(request, 'user_project_sections.html', {
#             'error': 'You do not have access to any project.'
#         })

#     sections = Section.objects.filter(project=project).prefetch_related("items__entries")
#     today = timezone.now().date()
#     error_messages = []

#     #### 🔄 PART 1: Backfill dates on every request
#     for item in ProgressItem.objects.filter(section__project=project):
#         total_progress = item.entries.aggregate(total=Sum('progress_done'))['total'] or 0

#         # 🔹 Start Date
#         if not item.scope_assigned_date and total_progress > 0:
#             first_entry = item.entries.order_by('date').first()
#             item.scope_assigned_date = first_entry.date if first_entry else item.targeted_start_date

#         # 🔹 End Date
#         if item.scope and total_progress >= item.scope:
#             if not item.scope_completed_date:
#                 last_entry = item.entries.order_by('-date').first()
#                 item.scope_completed_date = last_entry.date if last_entry else item.targeted_end_date
#         elif item.scope_completed_date:
#             item.scope_completed_date = None

#         item.save()

#     #### ✏️ PART 2: On POST - Save progress
#     if request.method == 'POST':
#         for item in ProgressItem.objects.filter(section__project=project):
#             progress_raw = request.POST.get(f"progress_{item.id}", "").strip()

#             if not item.targeted_start_date or not item.targeted_end_date or item.scope is None:
#                 if progress_raw:
#                     error_messages.append(f"Cannot enter progress for '{item.description}' due to missing dates.")
#                 continue

#             if progress_raw == "":
#                 continue

#             try:
#                 progress_val = float(progress_raw)
#                 if progress_val < 0:
#                     error_messages.append(f"Negative value not allowed for '{item.description}'.")
#                     continue

#                 done_so_far = item.entries.filter(user=request.user, date__lt=today).aggregate(
#                     total=Sum('progress_done'))['total'] or 0

#                 today_entry = item.entries.filter(user=request.user, date=today).first()
#                 existing_today_progress = today_entry.progress_done if today_entry else 0

#                 new_total = done_so_far + progress_val
#                 if new_total > item.scope:
#                     allowed_today_max = item.scope - done_so_far
#                     error_messages.append(
#                         f"Progress for '{item.description}' exceeds scope. Max allowed today: {allowed_today_max}")
#                     continue

#                 # 🔹 First progress → assign start date
#                 if not item.scope_assigned_date:
#                     item.scope_assigned_date = today

#                 # 🔹 Save today's progress
#                 if today_entry:
#                     today_entry.progress_done = progress_val
#                     today_entry.save()
#                 else:
#                     ProgressEntry.objects.create(user=request.user, item=item, progress_done=progress_val)

#                 # 🔁 Recalculate after save
#                 total_progress = item.entries.aggregate(total=Sum('progress_done'))['total'] or 0

#                 # 🔹 End Date update/reset logic
#                 if total_progress >= item.scope:
#                     if not item.scope_completed_date:
#                         item.scope_completed_date = today
#                 elif item.scope_completed_date:
#                     item.scope_completed_date = None

#                 item.save()

#             except ValueError:
#                 error_messages.append(f"Invalid input for '{item.description}'.")

#         return redirect('user_project_sections')

#     #### 📦 PART 3: Render Data
#     sections_data = []
#     for section in sections:
#         item_data = []
#         for item in section.items.all().order_by('order', 'id'):
#             expected_today = 'N/A'
#             balance = 'N/A'
#             completed = 0
#             status = 'Missing Dates'
#             today_progress = 0
#             max_today_input = None

#             if item.targeted_start_date and item.targeted_end_date and item.scope is not None:
#                 done_so_far = item.entries.filter(user=request.user, date__lt=today).aggregate(
#                     total=Sum('progress_done'))['total'] or 0

#                 today_entry = item.entries.filter(user=request.user, date=today).first()
#                 today_progress = today_entry.progress_done if today_entry else 0

#                 completed = done_so_far + today_progress
#                 balance = max(item.scope - completed, 0)

#                 expected_balance = max(item.scope - done_so_far, 0)
#                 remaining_days = (item.targeted_end_date - today).days + 1
#                 expected_today = round(expected_balance / remaining_days, 2) if remaining_days > 0 else expected_balance

#                 status = 'Ontime' if today <= item.targeted_end_date else 'Delay'
#                 max_today_input = item.scope - done_so_far

#             item_data.append({
#                 'id': item.id,
#                 'description': item.description,
#                 'uom': item.uom,
#                 'scope': item.scope,
#                 'targeted_start_date': item.targeted_start_date,
#                 'targeted_end_date': item.targeted_end_date,
#                 'expected_today': expected_today,
#                 'today_progress': today_progress,
#                 'completed': completed,
#                 'balance': balance,
#                 'status': status,
#                 'max_today_input': max_today_input,
#                 'scope_assigned_date': item.scope_assigned_date,
#                 'scope_completed_date': item.scope_completed_date
#             })

#         sections_data.append({
#             'title': section.title,
#             'items': item_data
#         })

#     return render(request, 'user_project_sections.html', {
#         'project': project,
#         'sections_data': sections_data,
#         'today': today,
#         'error': "\n".join(error_messages) if error_messages else None
#     })


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.db.models import Sum
from .models import ProjectAccess, Section, ProgressItem, ProgressEntry

@login_required
def user_project_sections(request):
    if request.user.is_superuser:
        return HttpResponseForbidden("Admins only.")

    try:
        project = ProjectAccess.objects.get(user=request.user)
    except ProjectAccess.DoesNotExist:
        return render(request, 'user_project_sections.html', {
            'error': 'You do not have access to any project.'
        })

    sections = Section.objects.filter(project=project).prefetch_related("items__entries")
    today = timezone.now().date()
    error_messages = []

    #### ✏️ PART 1: On POST - Save progress
    if request.method == 'POST':
        for item in ProgressItem.objects.filter(section__project=project):
            progress_raw = request.POST.get(f"progress_{item.id}", "").strip()

            if not item.targeted_start_date or not item.targeted_end_date or item.scope is None:
                if progress_raw:
                    error_messages.append(f"Cannot enter progress for '{item.description}' due to missing dates.")
                continue

            if progress_raw == "":
                continue

            try:
                progress_val = float(progress_raw)
                if progress_val < 0:
                    error_messages.append(f"Negative value not allowed for '{item.description}'.")
                    continue

                done_so_far = item.entries.filter(user=request.user, date__lt=today).aggregate(
                    total=Sum('progress_done'))['total'] or 0

                today_entry = item.entries.filter(user=request.user, date=today).first()
                existing_today_progress = today_entry.progress_done if today_entry else 0

                new_total = done_so_far + progress_val
                if new_total > item.scope:
                    allowed_today_max = item.scope - done_so_far
                    error_messages.append(
                        f"Progress for '{item.description}' exceeds scope. Max allowed today: {allowed_today_max}")
                    continue

                # 🔹 First time progress → assign scope_assigned_date
                if not item.scope_assigned_date:
                    if progress_val > 0:
                        prev_total = item.entries.exclude(date=today).aggregate(total=Sum('progress_done'))['total'] or 0
                        if prev_total == 0:
                            item.scope_assigned_date = today
                else:
                    # 🔹 If progress reset to 0 and total is 0 → clear scope_assigned_date
                    total_without_today = item.entries.exclude(date=today).aggregate(total=Sum('progress_done'))['total'] or 0
                    if progress_val == 0 and total_without_today == 0:
                        item.scope_assigned_date = None

                # 🔹 Save today's progress
                if today_entry:
                    today_entry.progress_done = progress_val
                    today_entry.save()
                else:
                    ProgressEntry.objects.create(user=request.user, item=item, progress_done=progress_val)

                # 🔁 Recalculate total
                total_progress = item.entries.aggregate(total=Sum('progress_done'))['total'] or 0

                # 🔹 End Date update/reset logic
                if total_progress >= item.scope:
                    if not item.scope_completed_date:
                        item.scope_completed_date = today
                elif item.scope_completed_date:
                    item.scope_completed_date = None

                item.save()

            except ValueError:
                error_messages.append(f"Invalid input for '{item.description}'.")

        return redirect('user_project_sections')

    #### 📦 PART 2: Render Data
    sections_data = []
    for section in sections:
        item_data = []
        for item in section.items.all().order_by('order', 'id'):
            expected_today = 'N/A'
            balance = 'N/A'
            completed = 0
            status = 'Missing Dates'
            today_progress = 0
            max_today_input = None

            if item.targeted_start_date and item.targeted_end_date and item.scope is not None:
                done_so_far = item.entries.filter(user=request.user, date__lt=today).aggregate(
                    total=Sum('progress_done'))['total'] or 0

                today_entry = item.entries.filter(user=request.user, date=today).first()
                today_progress = today_entry.progress_done if today_entry else 0

                completed = round(done_so_far + today_progress)
                balance = round(max(item.scope - completed, 0))

                expected_balance = round(max(item.scope - done_so_far, 0))
                remaining_days = (item.targeted_end_date - today).days + 1
                expected_today = math.ceil(expected_balance / remaining_days) if remaining_days > 0 else expected_balance

                # status = 'Ontime' if today <= item.targeted_end_date else 'Delay'
                status = item.get_status()
                max_today_input = item.scope - done_so_far


            item_data.append({
                'id': item.id,
                'description': item.description,
                'uom': item.uom,
                'scope': item.scope,
                'targeted_start_date': item.targeted_start_date,
                'targeted_end_date': item.targeted_end_date,
                'expected_today': expected_today,
                'today_progress': today_progress,
                'completed': completed,
                'balance': balance,
                'status': status,
                'max_today_input': max_today_input,
                'scope_assigned_date': item.scope_assigned_date,
                'scope_completed_date': item.scope_completed_date
            })

        sections_data.append({
            'title': section.title,
            'items': item_data
        })

    return render(request, 'user_project_sections.html', {
        'project': project,
        'sections_data': sections_data,
        'today': today,
        'error': "\n".join(error_messages) if error_messages else None
    })


from decimal import Decimal, ROUND_HALF_UP

def custom_round(value):
    return int(Decimal(value).quantize(0, rounding=ROUND_HALF_UP))


# from django.utils.timezone import now
# from django.contrib.admin.views.decorators import staff_member_required
# from django.db.models import Sum
# from django.shortcuts import render
# from .models import ProjectAccess, ProgressItem
# from decimal import Decimal, ROUND_HALF_UP
# @staff_member_required
# def admin_dashboard(request):
#     today = now().date()
#     dashboard_data = []
#     projects = ProjectAccess.objects.all()

#     for project in projects:
#         items = ProgressItem.objects.filter(section__project=project).prefetch_related('entries')

#         activities_today = []
#         delay_activities = []
#         ontime_activities = []
#         missing_activities = []

#         total_scope = 0
#         total_completed = 0
#         delay_percentages = []
#         ontime_percentages = []
#         all_target_end_dates = []
#         all_completed_dates = []

#         for item in items:
#             today_entry = item.entries.filter(date=today).first()
#             if today_entry and today_entry.progress_done > 0:
#                 done_so_far = item.entries.filter(date__lt=today).aggregate(total=Sum('progress_done'))['total'] or 0
#                 today_progress = today_entry.progress_done or 0
#                 total_completed_item = done_so_far + today_progress
#                 balance = max(item.scope - total_completed_item, 0) if item.scope else 'N/A'
#                 expected_today = 'N/A'
#                 if item.scope and item.targeted_end_date:
#                     remaining_scope = item.scope - done_so_far
#                     remaining_days = (item.targeted_end_date - today).days + 1
#                     expected_today = math.ceil(remaining_scope / remaining_days) if remaining_days > 0 else remaining_scope
                
#                 # if not item.targeted_start_date or not item.targeted_end_date:
#                 #     status = 'Missing Dates'
#                 # elif today <= item.targeted_end_date:
#                 #     status = 'Ontime'
#                 # else:
#                 #     status = 'Delay'

#                 status = item.get_status()

#                 # if not item.targeted_end_date:
#                 #     status = 'Missing Dates'
#                 # elif item.scope_completed_date:
#                 #     if item.scope_completed_date <= item.targeted_end_date:
#                 #         status = 'Ontime'
#                 #     else:
#                 #         status = 'Delay'
#                 # else:
#                 #     if today <= item.targeted_end_date:
#                 #         status = 'Ontime'
#                 #     else:
#                 #         status = 'Delay'

#                 # status = item.get_status()


#                 activities_today.append({
#                     'description': item.description,
#                     'uom': item.uom,
#                     'scope': item.scope,
#                     'targeted_start_date': item.targeted_start_date,
#                     'targeted_end_date': item.targeted_end_date,
#                     'scope_assigned_date': item.scope_assigned_date,
#                     'scope_completed_date': item.scope_completed_date,
#                     'total_progress': total_completed_item,
#                     'balance': balance,
#                     'expected_today': expected_today,
#                     'status': status,
#                     'today_progress': today_progress
#                 })

#             # === Total Status Check ===
#             total_progress = item.total_progress()
#             balance = item.remaining_balance()

#             activity_data = {
#                 'description': item.description,
#                 'uom': item.uom,
#                 'scope': item.scope,
#                 'targeted_start_date': item.targeted_start_date,
#                 'targeted_end_date': item.targeted_end_date,
#                 'scope_assigned_date': item.scope_assigned_date,
#                 'scope_completed_date': item.scope_completed_date,
#                 'total_progress': total_progress,
#                 'balance': balance,
#             }

#             if item.scope:
#                 total_scope += item.scope
#                 total_completed += total_progress

#             if not item.targeted_start_date or not item.targeted_end_date:
#                 missing_activities.append(activity_data)
#             elif today <= item.targeted_end_date:
#                 percentage = round((total_progress / item.scope) * 100, 2) if item.scope else 0
#                 activity_data['percentage'] = percentage
#                 ontime_percentages.append(percentage)
#                 ontime_activities.append(activity_data)
#             else:
#                 actual_end = item.scope_completed_date or today
#                 delay_days = max((actual_end - item.targeted_end_date).days, 0)
#                 percentage = round((total_progress / item.scope) * 100) if item.scope else 0
#                 activity_data['delay_days'] = delay_days
#                 activity_data['percentage'] = percentage
#                 delay_percentages.append(percentage)
#                 delay_activities.append(activity_data)

#             # collect target and actual end dates for total delay calc
#             if item.targeted_end_date:
#                 all_target_end_dates.append(item.targeted_end_date)
#             if item.scope_completed_date:
#                 all_completed_dates.append(item.scope_completed_date)

#         # === Final Stats ===
#         avg_ontime = round(sum(ontime_percentages) / len(ontime_percentages)) if ontime_percentages else 0
#         avg_delay = round(sum(delay_percentages) / len(delay_percentages)) if delay_percentages else 0
#         # overall_completion_percent = round((total_completed / total_scope) * 100) if total_scope else 0
#         total_activities_count = len(ontime_percentages) + len(delay_percentages)
#         total_activities_percent = sum(ontime_percentages) + sum(delay_percentages)

#         if total_activities_count > 0:
#             overall_completion_percent = custom_round((total_activities_percent / total_activities_count))
#         else:
#             overall_completion_percent = 0


#         # Total Delay Days (Project-Level)
#         project_completed = (total_scope > 0) and (total_completed >= total_scope)
#         if project_completed and all_completed_dates and all_target_end_dates:
#             actual_end = max(all_completed_dates)
#             latest_target = max(all_target_end_dates)
#             project_delay_days = max((actual_end - latest_target).days, 0)
#         else:
#             project_delay_days = sum([act.get('delay_days', 0) for act in delay_activities])

#         dashboard_data.append({
#             'project_id': project.id,
#             'project_name': project.project_name,
#             'user': project.user.username,
#             'location': project.location,
#             'type': project.type_of_project,

#             'activities_today': activities_today,
#             'delay_activities': delay_activities,
#             'ontime_activities': ontime_activities,
#             'missing_activities': missing_activities,

#             'count_today': len(activities_today),
#             'count_delay': len(delay_activities),
#             'count_ontime': len(ontime_activities),
#             'count_missing': len(missing_activities),

#             'avg_ontime_percent': avg_ontime,
#             'avg_delay_percent': avg_delay,
#             'project_delay_days': project_delay_days,
#             'overall_completion_percent': overall_completion_percent,
#         })

#     return render(request, 'admin_project_dashboard.html', {
#         'dashboard_data': dashboard_data,
#         'today': today,
#     })



from django.utils.timezone import now
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from django.shortcuts import render
from .models import ProjectAccess, ProgressItem
from decimal import Decimal, ROUND_HALF_UP

@staff_member_required
def admin_dashboard(request):
    today = now().date()
    dashboard_data = []
    projects = ProjectAccess.objects.all()

    for project in projects:
        items = ProgressItem.objects.filter(section__project=project).prefetch_related('entries')

        activities_today = []
        delay_activities = []
        ontime_activities = []
        missing_activities = []

        total_scope = 0
        total_completed = 0
        delay_percentages = []
        ontime_percentages = []
        all_target_end_dates = []
        all_completed_dates = []

        for item in items:
            today_entry = item.entries.filter(date=today).first()
            if today_entry and today_entry.progress_done > 0:
                done_so_far = item.entries.filter(date__lt=today).aggregate(total=Sum('progress_done'))['total'] or 0
                today_progress = today_entry.progress_done or 0
                total_completed_item = done_so_far + today_progress
                balance = max(item.scope - total_completed_item, 0) if item.scope else 'N/A'
                expected_today = 'N/A'
                if item.scope and item.targeted_end_date:
                    remaining_scope = item.scope - done_so_far
                    remaining_days = (item.targeted_end_date - today).days + 1
                    expected_today = round(remaining_scope / remaining_days, 2) if remaining_days > 0 else remaining_scope

                status = item.get_status()

                activities_today.append({
                    'description': item.description,
                    'uom': item.uom,
                    'scope': item.scope,
                    'targeted_start_date': item.targeted_start_date,
                    'targeted_end_date': item.targeted_end_date,
                    'scope_assigned_date': item.scope_assigned_date,
                    'scope_completed_date': item.scope_completed_date,
                    'total_progress': total_completed_item,
                    'balance': balance,
                    'expected_today': expected_today,
                    'status': status,
                    'today_progress': today_progress
                })

            # === Total Status Check ===
            total_progress = item.total_progress()
            balance = item.remaining_balance()
            percentage = round((total_progress / item.scope) * 100, 2) if item.scope else 0

            activity_data = {
                'description': item.description,
                'uom': item.uom,
                'scope': item.scope,
                'targeted_start_date': item.targeted_start_date,
                'targeted_end_date': item.targeted_end_date,
                'scope_assigned_date': item.scope_assigned_date,
                'scope_completed_date': item.scope_completed_date,
                'total_progress': total_progress,
                'balance': balance,
                'percentage': percentage
            }

            if item.scope:
                total_scope += item.scope
                total_completed += total_progress

            status = item.get_status()
            if status == 'Missing Dates':
                missing_activities.append(activity_data)
            elif status == 'Ontime':
                ontime_percentages.append(percentage)
                ontime_activities.append(activity_data)
            elif status == 'Delay':
                actual_end = item.scope_completed_date or today
                activity_data['delay_days'] = max((actual_end - item.targeted_end_date).days, 0)
                delay_percentages.append(percentage)
                delay_activities.append(activity_data)

            if item.targeted_end_date:
                all_target_end_dates.append(item.targeted_end_date)
            if item.scope_completed_date:
                all_completed_dates.append(item.scope_completed_date)

        avg_ontime = round(sum(ontime_percentages) / len(ontime_percentages)) if ontime_percentages else 0
        avg_delay = round(sum(delay_percentages) / len(delay_percentages)) if delay_percentages else 0

        total_activities_count = len(ontime_percentages) + len(delay_percentages)
        total_activities_percent = sum(ontime_percentages) + sum(delay_percentages)

        if total_activities_count > 0:
            overall_completion_percent = custom_round(total_activities_percent / total_activities_count)
        else:
            overall_completion_percent = 0

        project_completed = (total_scope > 0) and (total_completed >= total_scope)
        if project_completed and all_completed_dates and all_target_end_dates:
            actual_end = max(all_completed_dates)
            latest_target = max(all_target_end_dates)
            project_delay_days = max((actual_end - latest_target).days, 0)
        else:
            project_delay_days = sum([act.get('delay_days', 0) for act in delay_activities])

        dashboard_data.append({
            'project_id': project.id,
            'project_name': project.project_name,
            'user': project.user.username,
            'location': project.location,
            'type': project.type_of_project,

            'activities_today': activities_today,
            'delay_activities': delay_activities,
            'ontime_activities': ontime_activities,
            'missing_activities': missing_activities,

            'count_today': len(activities_today),
            'count_delay': len(delay_activities),
            'count_ontime': len(ontime_activities),
            'count_missing': len(missing_activities),

            'avg_ontime_percent': avg_ontime,
            'avg_delay_percent': avg_delay,
            'project_delay_days': project_delay_days,
            'overall_completion_percent': overall_completion_percent,
        })

    return render(request, 'admin_project_dashboard.html', {
        'dashboard_data': dashboard_data,
        'today': today,
    })




# from django.template.loader import get_template
# from django.http import HttpResponse
# from xhtml2pdf import pisa
# from django.utils.timezone import now
# from django.db.models import Sum
# from .models import ProjectAccess, ProgressItem

# def export_project_pdf(request, project_id):
#     today = now().date()

#     try:
#         project = ProjectAccess.objects.get(id=project_id)
#     except ProjectAccess.DoesNotExist:
#         return HttpResponse("Project not found", status=404)

#     items = ProgressItem.objects.filter(section__project=project).prefetch_related('entries')

#     activities_today = []
#     delay_activities = []
#     ontime_activities = []
#     missing_activities = []

#     total_scope = 0
#     total_completed = 0
#     delay_percentages = []
#     ontime_percentages = []
#     all_target_end_dates = []
#     all_completed_dates = []

#     for item in items:
#         today_entry = item.entries.filter(date=today).first()
#         if today_entry and today_entry.progress_done > 0:
#             done_so_far = item.entries.filter(date__lt=today).aggregate(total=Sum('progress_done'))['total'] or 0
#             today_progress = today_entry.progress_done or 0
#             total_completed_item = done_so_far + today_progress
#             balance = max(item.scope - total_completed_item, 0) if item.scope else 'N/A'
#             expected_today = 'N/A'
#             if item.scope and item.targeted_end_date:
#                 remaining_scope = item.scope - done_so_far
#                 remaining_days = (item.targeted_end_date - today).days + 1
#                 expected_today = -(-remaining_scope // remaining_days) if remaining_days > 0 else remaining_scope  # ceil logic

#             status = 'Missing Dates'
#             if item.targeted_start_date and item.targeted_end_date:
#                 status = 'Ontime' if today <= item.targeted_end_date else 'Delay'

#             activities_today.append({
#                 'description': item.description,
#                 'uom': item.uom,
#                 'scope': item.scope,
#                 'targeted_start_date': item.targeted_start_date,
#                 'targeted_end_date': item.targeted_end_date,
#                 'scope_assigned_date': item.scope_assigned_date,
#                 'scope_completed_date': item.scope_completed_date,
#                 'total_progress': total_completed_item,
#                 'balance': balance,
#                 'expected_today': expected_today,
#                 'status': status,
#                 'today_progress': today_progress
#             })

#         total_progress = item.total_progress()
#         balance = item.remaining_balance()

#         activity_data = {
#             'description': item.description,
#             'uom': item.uom,
#             'scope': item.scope,
#             'targeted_start_date': item.targeted_start_date,
#             'targeted_end_date': item.targeted_end_date,
#             'scope_assigned_date': item.scope_assigned_date,
#             'scope_completed_date': item.scope_completed_date,
#             'total_progress': total_progress,
#             'balance': balance,
#         }

#         if item.scope:
#             total_scope += item.scope
#             total_completed += total_progress

#         if not item.targeted_start_date or not item.targeted_end_date:
#             missing_activities.append(activity_data)
#         elif today <= item.targeted_end_date:
#             percentage = round((total_progress / item.scope) * 100, 2) if item.scope else 0
#             activity_data['percentage'] = percentage
#             ontime_percentages.append(percentage)
#             ontime_activities.append(activity_data)
#         else:
#             actual_end = item.scope_completed_date or today
#             delay_days = max((actual_end - item.targeted_end_date).days, 0)
#             percentage = round((total_progress / item.scope) * 100, 2) if item.scope else 0
#             activity_data['delay_days'] = delay_days
#             activity_data['percentage'] = percentage
#             delay_percentages.append(percentage)
#             delay_activities.append(activity_data)

#         if item.targeted_end_date:
#             all_target_end_dates.append(item.targeted_end_date)
#         if item.scope_completed_date:
#             all_completed_dates.append(item.scope_completed_date)

#     avg_ontime = round(sum(ontime_percentages) / len(ontime_percentages), 2) if ontime_percentages else 0
#     avg_delay = round(sum(delay_percentages) / len(delay_percentages), 2) if delay_percentages else 0
#     # overall_completion_percent = round((total_completed / total_scope) * 100, 2) if total_scope else 0

#     total_activities_count = len(ontime_percentages) + len(delay_percentages)
#     total_activities_percent = sum(ontime_percentages) + sum(delay_percentages)

#     if total_activities_count > 0:
#         overall_completion_percent = custom_round((total_activities_percent / total_activities_count))
#     else:
#         overall_completion_percent = 0



#     project_completed = (total_scope > 0) and (total_completed >= total_scope)
#     if project_completed and all_completed_dates and all_target_end_dates:
#         actual_end = max(all_completed_dates)
#         latest_target = max(all_target_end_dates)
#         project_delay_days = max((actual_end - latest_target).days, 0)
#     else:
#         project_delay_days = sum([act.get('delay_days', 0) for act in delay_activities])

#     context = {
#         'project': project,
#         'today': today,
#         'activities_today': activities_today,
#         'delay_activities': delay_activities,
#         'ontime_activities': ontime_activities,
#         'missing_activities': missing_activities,

#         'count_today': len(activities_today),
#         'count_delay': len(delay_activities),
#         'count_ontime': len(ontime_activities),
#         'count_missing': len(missing_activities),

#         'avg_ontime_percent': avg_ontime,
#         'avg_delay_percent': avg_delay,
#         'project_delay_days': project_delay_days,
#         'overall_completion_percent': overall_completion_percent,
#     }

#     template = get_template('project_pdf_template.html')
#     html = template.render(context)

#     response = HttpResponse(content_type='application/pdf')
#     response['Content-Disposition'] = f'attachment; filename="Project_{project.id}_Report.pdf"'

#     pisa_status = pisa.CreatePDF(html, dest=response)
#     if pisa_status.err:
#         return HttpResponse("PDF generation failed", status=500)

#     return response


from django.template.loader import get_template
from django.http import HttpResponse
from xhtml2pdf import pisa
from django.utils.timezone import now
from django.db.models import Sum
from .models import ProjectAccess, ProgressItem
from decimal import Decimal, ROUND_HALF_UP

def custom_round(value):
    return int(Decimal(value).quantize(0, rounding=ROUND_HALF_UP))

def export_project_pdf(request, project_id):
    today = now().date()

    try:
        project = ProjectAccess.objects.get(id=project_id)
    except ProjectAccess.DoesNotExist:
        return HttpResponse("Project not found", status=404)

    items = ProgressItem.objects.filter(section__project=project).prefetch_related('entries')

    activities_today = []
    delay_activities = []
    ontime_activities = []
    missing_activities = []

    total_scope = 0
    total_completed = 0
    delay_percentages = []
    ontime_percentages = []
    all_target_end_dates = []
    all_completed_dates = []

    for item in items:
        # === Calculate today's activity ===
        today_entry = item.entries.filter(date=today).first()
        if today_entry and today_entry.progress_done > 0:
            done_so_far = item.entries.filter(date__lt=today).aggregate(total=Sum('progress_done'))['total'] or 0
            today_progress = today_entry.progress_done or 0
            total_completed_item = done_so_far + today_progress
            balance = max(item.scope - total_completed_item, 0) if item.scope else 'N/A'
            expected_today = 'N/A'
            if item.scope and item.targeted_end_date:
                remaining_scope = item.scope - done_so_far
                remaining_days = (item.targeted_end_date - today).days + 1
                expected_today = -(-remaining_scope // remaining_days) if remaining_days > 0 else remaining_scope  # ceil

            status = get_item_status(item, today)

            activities_today.append({
                'description': item.description,
                'uom': item.uom,
                'scope': item.scope,
                'targeted_start_date': item.targeted_start_date,
                'targeted_end_date': item.targeted_end_date,
                'scope_assigned_date': item.scope_assigned_date,
                'scope_completed_date': item.scope_completed_date,
                'total_progress': total_completed_item,
                'balance': balance,
                'expected_today': expected_today,
                'status': status,
                'today_progress': today_progress
            })

        # === Total progress status ===
        total_progress = item.total_progress()
        balance = item.remaining_balance()
        percentage = round((total_progress / item.scope) * 100, 2) if item.scope else 0

        activity_data = {
            'description': item.description,
            'uom': item.uom,
            'scope': item.scope,
            'targeted_start_date': item.targeted_start_date,
            'targeted_end_date': item.targeted_end_date,
            'scope_assigned_date': item.scope_assigned_date,
            'scope_completed_date': item.scope_completed_date,
            'total_progress': total_progress,
            'balance': balance,
            'percentage': percentage
        }

        if item.scope:
            total_scope += item.scope
            total_completed += total_progress

        status = get_item_status(item, today)

        if status == 'Missing Dates':
            missing_activities.append(activity_data)
        elif status == 'Ontime':
            ontime_percentages.append(percentage)
            ontime_activities.append(activity_data)
        elif status == 'Delay':
            actual_end = item.scope_completed_date or today
            activity_data['delay_days'] = max((actual_end - item.targeted_end_date).days, 0)
            delay_percentages.append(percentage)
            delay_activities.append(activity_data)

        if item.targeted_end_date:
            all_target_end_dates.append(item.targeted_end_date)
        if item.scope_completed_date:
            all_completed_dates.append(item.scope_completed_date)

    avg_ontime = round(sum(ontime_percentages) / len(ontime_percentages), 2) if ontime_percentages else 0
    avg_delay = round(sum(delay_percentages) / len(delay_percentages), 2) if delay_percentages else 0

    total_activities_count = len(ontime_percentages) + len(delay_percentages)
    total_activities_percent = sum(ontime_percentages) + sum(delay_percentages)
    if total_activities_count > 0:
        overall_completion_percent = custom_round(total_activities_percent / total_activities_count)
    else:
        overall_completion_percent = 0

    project_completed = (total_scope > 0) and (total_completed >= total_scope)
    if project_completed and all_completed_dates and all_target_end_dates:
        actual_end = max(all_completed_dates)
        latest_target = max(all_target_end_dates)
        project_delay_days = max((actual_end - latest_target).days, 0)
    else:
        project_delay_days = sum([act.get('delay_days', 0) for act in delay_activities])

    context = {
        'project': project,
        'today': today,
        'activities_today': activities_today,
        'delay_activities': delay_activities,
        'ontime_activities': ontime_activities,
        'missing_activities': missing_activities,

        'count_today': len(activities_today),
        'count_delay': len(delay_activities),
        'count_ontime': len(ontime_activities),
        'count_missing': len(missing_activities),

        'avg_ontime_percent': avg_ontime,
        'avg_delay_percent': avg_delay,
        'project_delay_days': project_delay_days,
        'overall_completion_percent': overall_completion_percent,
    }

    template = get_template('project_pdf_template.html')
    html = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Project_{project.id}_Report.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse("PDF generation failed", status=500)

    return response


def get_item_status(item, today):
    """Applies the exact OnTime/Delay rules."""
    if not item.targeted_start_date or not item.targeted_end_date:
        return "Missing Dates"

    if item.scope_completed_date:
        return "Ontime" if item.scope_completed_date <= item.targeted_end_date else "Delay"
    else:
        return "Ontime" if today <= item.targeted_end_date else "Delay"
