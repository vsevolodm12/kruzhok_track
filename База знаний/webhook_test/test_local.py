#!/usr/bin/env python3
"""
Локальный тест парсинга оценок из комментариев.
Запускать без сервера для проверки логики.
"""

import requests
import json

# Тестовый вебхук (имитация ZenClass)
SAMPLE_WEBHOOK = {
    "id": "test123abc",
    "hash": "fake_hash_for_testing",
    "event_name": "lesson_task_accepted",
    "timestamp": 1706540400,
    "payload": {
        "user_id": "user-123",
        "user_email": "student@example.com",
        "course_id": "course-456",
        "course_name": "Тестовый курс по Python",
        "tarif_id": "tarif-789",
        "tarif_name": "Базовый",
        "task_id": "task-001",
        "task_name": "Домашнее задание №1",
        "task_type": "homework",
        "task_result": "ok",
        "report_link": "https://zenclass.ru/report/123",
        "comment": "Отличная работа! Оценка: 5"
    }
}


def send_test_webhook(url: str, comment: str = None):
    """Отправить тестовый вебхук на локальный сервер."""
    webhook = SAMPLE_WEBHOOK.copy()
    webhook['payload'] = SAMPLE_WEBHOOK['payload'].copy()
    
    if comment is not None:
        webhook['payload']['comment'] = comment
    
    print(f"\n📤 Отправляю вебхук с комментарием: '{webhook['payload']['comment']}'")
    
    try:
        response = requests.post(url, json=webhook)
        print(f"📥 Ответ сервера: {response.status_code}")
        return response.json()
    except requests.exceptions.ConnectionError:
        print("❌ Ошибка: Сервер не запущен!")
        print("   Запустите: python server.py")
        return None


if __name__ == '__main__':
    SERVER_URL = "http://localhost:5000/webhook"
    
    print("="*60)
    print("🧪 Тестирование парсинга оценок из комментариев")
    print("="*60)
    
    # Тестовые комментарии
    test_comments = [
        "Отличная работа! Оценка: 5",
        "Хорошо, но есть замечания. Оценка 4",
        "5/5 - идеально!",
        "Балл: 3",
        "Неплохо! 4",
        "5",
        "Работа принята, доработайте следующую",  # Без оценки
        "",  # Пустой
    ]
    
    print("\nУбедитесь, что сервер запущен (python server.py)")
    print("Нажмите Enter для отправки тестовых вебхуков...")
    input()
    
    for comment in test_comments:
        send_test_webhook(SERVER_URL, comment)
        print("-" * 40)
