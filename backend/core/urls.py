from django.urls import path
from . import views

urlpatterns = [
    # Health
    path('health/', views.health_check, name='health'),

    # React SPA — main entry point for TMA
    # '/' is configured in BotFather as the web app URL
    path('', views.spa_app, name='index'),

    # Auth
    path('auth/telegram/', views.telegram_auth, name='telegram_auth'),
    path('auth/email/', views.email_auth, name='email_auth'),
    path('auth/link-email/', views.link_email, name='link_email'),
    path('auth/logout/', views.logout, name='logout'),

    # Dashboard (htmx pages)
    path('dashboard/', views.dashboard, name='dashboard'),
    path('switch-course/<int:course_id>/', views.switch_course, name='switch_course'),
    path('stats/', views.stats_page, name='stats'),
    path('history/', views.history_page, name='history'),
    path('schedule/', views.schedule_page, name='schedule'),

    # API (JSON)
    path('api/me/', views.api_me, name='api_me'),
    path('api/courses/', views.api_courses, name='api_courses'),
    path('api/grades/', views.api_grades, name='api_grades'),
    path('api/schedule/', views.api_schedule, name='api_schedule'),
    path('api/deadlines/', views.api_deadlines, name='api_deadlines'),
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/update-name/', views.update_name, name='update_name'),
]
