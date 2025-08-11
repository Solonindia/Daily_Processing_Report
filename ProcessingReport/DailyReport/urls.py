from django.urls import path
from . import views
from .views import CustomLogoutView

urlpatterns = [
    path('', views.redirect_to_home),
    path('home/', views.home_page, name='home'),
    path('superuser/signup/', views.signup_view, name='signup'),
    path('user/login/', views.user_login_view, name='login'),  
    path('superuser/login/',views.admin_login_view,name="login1"),
    path('superuser/services/', views.admin_page, name='admin'),
    path('user/services/', views.user_page, name='user'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),


    path('custom-admin/assign-access/', views.assign_project_access, name='assign_project_access'),   
    path('custom-admin/project-sections/', views.admin_project_sections, name='admin_project_sections'),
    path('user/sections/', views.user_project_sections, name='user_project_sections'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('export-pdf/<int:project_id>/', views.export_project_pdf, name='export_project_pdf'),

]
