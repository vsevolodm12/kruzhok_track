import json
import logging
import os
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from datetime import timedelta

from .models import Student, Course, Enrollment, Task, Grade, ScheduleEvent, Deadline
from .services.telegram import TelegramAuthService

logger = logging.getLogger(__name__)


# ===========================================
# Health Check
# ===========================================

def health_check(request):
    """Проверка работоспособности сервера."""
    return JsonResponse({'status': 'ok', 'timestamp': timezone.now().isoformat()})


def spa_app(request):
    """Serve the React SPA (index.html). File lives in backend/ → /app/index.html in Docker."""
    spa_path = settings.BASE_DIR / 'index.html'
    try:
        with open(spa_path, 'r', encoding='utf-8') as f:
            content = f.read()
        response = HttpResponse(content, content_type='text/html')
        response['Cache-Control'] = 'no-store'
        return response
    except FileNotFoundError:
        return HttpResponse('index.html not found at ' + str(spa_path), status=404)


# ===========================================
# Telegram Mini App Views
# ===========================================

def index(request):
    """Главная страница Mini App. Проверяет авторизацию."""
    student_id = request.session.get('student_id')

    if student_id:
        try:
            Student.objects.get(id=student_id)
            return redirect('dashboard')
        except Student.DoesNotExist:
            request.session.flush()

    return render(request, 'auth/login.html')


@csrf_exempt
@require_POST
def telegram_auth(request):
    """Авторизация через Telegram initData."""
    try:
        data = json.loads(request.body)
        init_data = data.get('init_data', '')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not init_data:
        return JsonResponse({'error': 'init_data required'}, status=400)

    validated = TelegramAuthService.validate_init_data(init_data)
    if not validated:
        return JsonResponse({'error': 'Invalid init_data'}, status=401)

    user_data = TelegramAuthService.extract_user_data(validated)
    if not user_data:
        return JsonResponse({'error': 'No user data'}, status=401)

    telegram_id = user_data['telegram_id']

    try:
        student = Student.objects.get(telegram_id=telegram_id)
        request.session['student_id'] = student.id
        return JsonResponse({
            'status': 'authorized',
            'student': {'id': student.id, 'name': student.name, 'email': student.email}
        })
    except Student.DoesNotExist:
        request.session['telegram_data'] = user_data
        return JsonResponse({
            'status': 'need_link',
            'message': 'Введите email для привязки аккаунта'
        })


@csrf_exempt
@require_POST
def email_auth(request):
    """
    Авторизация по email (основной способ).
    Если в сессии есть telegram_data (от предыдущего шага TG) — привязывает telegram_id.
    """
    try:
        data = json.loads(request.body)
        email = data.get('email', '').lower().strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not email:
        return JsonResponse({'error': 'Email required'}, status=400)

    try:
        student = Student.objects.get(email=email)
    except Student.DoesNotExist:
        return JsonResponse({
            'error': 'not_found',
            'message': 'Студент с таким email не найден'
        }, status=404)

    # Если есть данные Telegram в сессии — привязываем
    telegram_data = request.session.get('telegram_data')
    if telegram_data:
        telegram_id = telegram_data['telegram_id']
        if not Student.objects.filter(telegram_id=telegram_id).exclude(id=student.id).exists():
            student.telegram_id = telegram_id
            first_name = telegram_data.get('first_name', '')
            last_name = telegram_data.get('last_name', '')
            full_name = f"{first_name} {last_name}".strip()
            if full_name and (not student.name or student.name == email.split('@')[0]):
                student.name = full_name
            student.save()
        try:
            del request.session['telegram_data']
        except KeyError:
            pass

    request.session['student_id'] = student.id

    return JsonResponse({
        'status': 'authorized',
        'student': {'id': student.id, 'name': student.name, 'email': student.email}
    })


@csrf_exempt
@require_POST
def link_email(request):
    """Обратная совместимость — алиас для email_auth."""
    return email_auth(request)


def logout(request):
    """Выход из аккаунта."""
    request.session.flush()
    return redirect('index')


# ===========================================
# Dashboard Views
# ===========================================

def dashboard(request):
    """Главный дашборд — соответствует Home в дизайне."""
    student = _get_current_student(request)
    if not student:
        return redirect('index')

    # Активные курсы студента
    enrollments = Enrollment.objects.filter(
        student=student,
        status=Enrollment.Status.ACTIVE
    ).select_related('course')

    # Текущий курс (из сессии или первый)
    current_course_id = request.session.get('current_course_id')
    current_enrollment = None

    if current_course_id:
        current_enrollment = enrollments.filter(course_id=current_course_id).first()

    if not current_enrollment and enrollments.exists():
        current_enrollment = enrollments.first()
        request.session['current_course_id'] = current_enrollment.course_id

    if not current_enrollment:
        return render(request, 'dashboard/home.html', {
            'student': student,
            'enrollments': [],
            'current_course': None,
        })

    current_course = current_enrollment.course

    # Оценки по текущему курсу
    grades = Grade.objects.filter(
        student=student,
        task__course=current_course,
        status=Grade.Status.ACCEPTED
    ).select_related('task')

    # Статистика: "Сдано" и "Процент"
    total_submitted = grades.count()
    grades_with_score = grades.filter(value__isnull=False)

    if grades_with_score.exists():
        total_percent = 0
        count = 0
        for g in grades_with_score:
            if g.task.max_score > 0:
                total_percent += (g.value / g.task.max_score) * 100
                count += 1
        average_percent = round(total_percent / count) if count > 0 else 0
    else:
        average_percent = 0

    # Расписание курса (ближайшие 4)
    schedule = ScheduleEvent.objects.filter(
        course=current_course,
        scheduled_at__gte=timezone.now()
    ).order_by('scheduled_at')[:4]

    next_event = schedule.first() if schedule.exists() else None

    # Дедлайны (ближайшие 7 дней)
    week_limit = timezone.now() + timedelta(days=7)
    deadlines = Deadline.objects.filter(
        course=current_course,
        due_date__gte=timezone.now(),
        due_date__lte=week_limit
    ).order_by('due_date')

    context = {
        'student': student,
        'enrollments': enrollments,
        'current_course': current_course,
        'total_submitted': total_submitted,
        'average_percent': average_percent,
        'schedule': schedule,
        'next_event': next_event,
        'deadlines': deadlines,
    }

    return render(request, 'dashboard/home.html', context)


def switch_course(request, course_id):
    """Переключение текущего курса."""
    student = _get_current_student(request)
    if not student:
        return redirect('index')

    # Проверяем что студент записан на курс
    if Enrollment.objects.filter(student=student, course_id=course_id).exists():
        request.session['current_course_id'] = course_id

    return redirect('dashboard')


def stats_page(request):
    """Страница статистики — соответствует Stats в дизайне."""
    student = _get_current_student(request)
    if not student:
        return redirect('index')

    current_course = _get_current_course(request, student)

    # Активный таб (тип задания)
    active_tab = request.GET.get('type', 'homework')

    if not current_course:
        return render(request, 'dashboard/stats.html', {
            'student': student, 'current_course': None,
            'active_tab': active_tab, 'task_types': [
                {'key': 'homework', 'label': 'Домашка'},
                {'key': 'mock', 'label': 'Пробник'},
                {'key': 'essay', 'label': 'Эссе'},
                {'key': 'project', 'label': 'Проект'},
            ],
            'grades': [], 'chart_data': [], 'average_score': 0,
        })

    # Оценки по типу
    grades = Grade.objects.filter(
        student=student,
        task__course=current_course,
        task__task_type=active_tab,
        status=Grade.Status.ACCEPTED,
        value__isnull=False
    ).select_related('task').order_by('checked_at')

    # Средний балл (по баллам, не процентам!)
    if grades.exists():
        average_score = round(sum(g.value for g in grades) / grades.count())
    else:
        average_score = 0

    # Данные для графика
    chart_data = []
    grades_list = list(grades)
    for i, grade in enumerate(grades_list):
        prev_grade = grades_list[i - 1] if i > 0 else None
        diff = grade.value - prev_grade.value if prev_grade else None
        chart_data.append({
            'grade': grade,
            'index': i + 1,
            'diff': diff,
        })

    # Типы заданий для табов
    task_types = [
        {'key': 'homework', 'label': 'Домашка'},
        {'key': 'mock', 'label': 'Пробник'},
        {'key': 'essay', 'label': 'Эссе'},
        {'key': 'project', 'label': 'Проект'},
    ]

    context = {
        'student': student,
        'current_course': current_course,
        'active_tab': active_tab,
        'task_types': task_types,
        'grades': grades,
        'chart_data': list(reversed(chart_data)),  # Новые сверху
        'average_score': average_score,
    }

    return render(request, 'dashboard/stats.html', context)


def history_page(request):
    """Страница истории — соответствует History в дизайне."""
    student = _get_current_student(request)
    if not student:
        return redirect('index')

    current_course = _get_current_course(request, student)

    if not current_course:
        return render(request, 'dashboard/history.html', {
            'student': student, 'current_course': None, 'grades': [],
        })

    # Все оценки по текущему курсу
    grades = Grade.objects.filter(
        student=student,
        task__course=current_course
    ).select_related('task').order_by('-checked_at')

    context = {
        'student': student,
        'current_course': current_course,
        'grades': grades,
    }

    return render(request, 'dashboard/history.html', context)


# ===========================================
# API Endpoints (JSON)
# ===========================================

@require_GET
def api_me(request):
    """API: данные текущего пользователя."""
    student = _get_current_student(request)
    if not student:
        return JsonResponse({'error': 'Not authorized'}, status=401)

    return JsonResponse({
        'id': student.id,
        'name': student.name,
        'email': student.email,
    })


@require_GET
def api_courses(request):
    """API: список курсов студента."""
    student = _get_current_student(request)
    if not student:
        return JsonResponse({'error': 'Not authorized'}, status=401)

    enrollments = Enrollment.objects.filter(student=student).select_related('course')

    courses = []
    for enrollment in enrollments:
        course = enrollment.course
        grades_count = Grade.objects.filter(
            student=student,
            task__course=course,
            status=Grade.Status.ACCEPTED
        ).count()

        courses.append({
            'id': course.id,
            'name': course.name,
            'status': enrollment.status,
            'grades_count': grades_count,
        })

    return JsonResponse({'courses': courses})


def schedule_page(request):
    """Страница полного расписания курса."""
    student = _get_current_student(request)
    if not student:
        return redirect('index')

    current_course = _get_current_course(request, student)
    if not current_course:
        return redirect('dashboard')

    # Все занятия курса
    schedule = ScheduleEvent.objects.filter(
        course=current_course
    ).order_by('scheduled_at')

    # Группировка по месяцам
    schedule_by_month = {}
    for event in schedule:
        month_key = event.scheduled_at.strftime('%Y-%m')
        month_label = event.scheduled_at.strftime('%B %Y')
        if month_key not in schedule_by_month:
            schedule_by_month[month_key] = {
                'key': month_key,
                'label': month_label,
                'events': []
            }
        schedule_by_month[month_key]['events'].append(event)

    context = {
        'student': student,
        'current_course': current_course,
        'schedule': schedule,
        'schedule_by_month': list(schedule_by_month.values()),
    }

    return render(request, 'dashboard/schedule.html', context)


@require_GET
def api_stats(request):
    """API: статистика по типу заданий."""
    student = _get_current_student(request)
    if not student:
        return JsonResponse({'error': 'Not authorized'}, status=401)

    current_course_id = request.session.get('current_course_id')
    if not current_course_id:
        return JsonResponse({'error': 'No course selected'}, status=400)

    task_type = request.GET.get('type', 'homework')

    grades = Grade.objects.filter(
        student=student,
        task__course_id=current_course_id,
        task__task_type=task_type,
        status=Grade.Status.ACCEPTED,
        value__isnull=False
    ).select_related('task').order_by('checked_at')

    if grades.exists():
        average_score = round(sum(g.value for g in grades) / grades.count())
    else:
        average_score = 0

    grades_data = []
    grades_list = list(grades)
    for i, grade in enumerate(grades_list):
        prev_grade = grades_list[i - 1] if i > 0 else None
        diff = grade.value - prev_grade.value if prev_grade else None
        grades_data.append({
            'id': grade.id,
            'name': grade.task.name,
            'score': grade.value,
            'max_score': grade.task.max_score,
            'date': grade.checked_at.isoformat() if grade.checked_at else None,
            'diff': diff,
        })

    return JsonResponse({
        'type': task_type,
        'average_score': average_score,
        'grades': grades_data,
    })


@require_GET
def api_grades(request):
    """API: все оценки студента по всем курсам (для фронтенда)."""
    student = _get_current_student(request)
    if not student:
        return JsonResponse({'error': 'Not authorized'}, status=401)

    task_type_map = {
        'homework': 'HW',
        'mock': 'MOCK',
        'essay': 'ESSAY',
        'project': 'PROJECT',
        'other': 'HW',
    }

    grades = Grade.objects.filter(
        student=student,
        status=Grade.Status.ACCEPTED,
    ).select_related('task', 'task__course').order_by('-checked_at')

    grades_data = []
    for grade in grades:
        grades_data.append({
            'id': grade.id,
            'course_id': grade.task.course_id,
            'type': task_type_map.get(grade.task.task_type, 'HW'),
            'name': grade.task.name,
            'date': grade.checked_at.date().isoformat() if grade.checked_at else None,
            'score': grade.value,
            'max_score': grade.task.max_score,
            'teacher_comment': grade.teacher_comment,
        })

    return JsonResponse({'grades': grades_data})


@require_GET
def api_schedule(request):
    """API: расписание занятий по всем курсам студента."""
    student = _get_current_student(request)
    if not student:
        return JsonResponse({'error': 'Not authorized'}, status=401)

    course_ids = list(Enrollment.objects.filter(student=student).values_list('course_id', flat=True))

    events = ScheduleEvent.objects.filter(
        course_id__in=course_ids
    ).order_by('scheduled_at')

    schedule_data = []
    for event in events:
        schedule_data.append({
            'id': event.id,
            'course_id': event.course_id,
            'topic': event.title,
            'starts_at': event.scheduled_at.isoformat(),
            'duration_minutes': event.duration_minutes,
        })

    return JsonResponse({'schedule': schedule_data})


@require_GET
def api_deadlines(request):
    """API: дедлайны по всем курсам студента."""
    student = _get_current_student(request)
    if not student:
        return JsonResponse({'error': 'Not authorized'}, status=401)

    course_ids = list(Enrollment.objects.filter(student=student).values_list('course_id', flat=True))

    deadlines = Deadline.objects.filter(
        course_id__in=course_ids
    ).order_by('due_date')

    deadlines_data = []
    for deadline in deadlines:
        deadlines_data.append({
            'id': deadline.id,
            'course_id': deadline.course_id,
            'title': deadline.title,
            'due_date': deadline.due_date.isoformat(),
            'submitted': deadline.submitted,
        })

    return JsonResponse({'deadlines': deadlines_data})


@csrf_exempt
@require_POST
def update_name(request):
    """Обновление имени студента."""
    student = _get_current_student(request)
    if not student:
        return JsonResponse({'error': 'Not authorized'}, status=401)

    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not name or len(name) < 2:
        return JsonResponse({'error': 'Имя слишком короткое'}, status=400)

    if len(name) > 100:
        return JsonResponse({'error': 'Имя слишком длинное'}, status=400)

    student.name = name
    student.save(update_fields=['name'])

    return JsonResponse({'status': 'ok', 'name': student.name})


# ===========================================
# Helpers
# ===========================================

def _get_current_student(request) -> Student | None:
    """Получает текущего авторизованного студента."""
    student_id = request.session.get('student_id')
    if not student_id:
        return None

    try:
        return Student.objects.get(id=student_id)
    except Student.DoesNotExist:
        return None


def _get_current_course(request, student) -> Course | None:
    """Возвращает текущий курс из сессии или первый доступный."""
    current_course_id = request.session.get('current_course_id')

    if current_course_id:
        try:
            course = Course.objects.get(id=current_course_id)
            if Enrollment.objects.filter(student=student, course=course).exists():
                return course
        except Course.DoesNotExist:
            pass

    # Fallback: первый активный курс
    enrollment = Enrollment.objects.filter(
        student=student,
        status=Enrollment.Status.ACTIVE
    ).select_related('course').first()

    if enrollment:
        request.session['current_course_id'] = enrollment.course_id
        return enrollment.course

    return None
