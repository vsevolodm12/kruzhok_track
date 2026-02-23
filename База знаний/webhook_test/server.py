#!/usr/bin/env python3
"""
Тестовый сервер для приёма вебхуков ZenClass.
Парсит оценку из комментария преподавателя.
"""

from flask import Flask, request, jsonify
from datetime import datetime
import hashlib
import re
import json

app = Flask(__name__)

# Секретный ключ (получите из ZenClass после создания автоматизации)
SECRET_KEY = "0Vo19nSKWZSyo6d8WI1blZlbGIm7biTJ"

# Лог полученных вебхуков
webhooks_log = []


def verify_signature(data: dict, secret: str) -> bool:
    """Проверка подписи вебхука по алгоритму ZenClass."""
    webhook_id = data.get('id', '')
    timestamp = data.get('timestamp', '')
    received_hash = data.get('hash', '')
    
    # Формируем строку: secret&id&timestamp
    concat = f"{secret}&{webhook_id}&{timestamp}"
    calculated_hash = hashlib.sha1(concat.encode()).hexdigest()
    
    return calculated_hash == received_hash


def parse_grade_from_comment(comment: str) -> dict:
    """
    Парсинг оценки из комментария преподавателя.
    
    Поддерживаемые форматы:
    - "Оценка: 5"
    - "оценка 4"
    - "5/5"
    - "Балл: 4"
    - Просто число в начале или конце: "Отлично! 5"
    """
    if not comment:
        return {"grade": None, "raw_comment": comment, "parse_method": "empty"}
    
    comment_lower = comment.lower().strip()
    
    # Паттерн 1: "Оценка: X" или "Оценка X"
    match = re.search(r'оценка[:\s]+(\d+)', comment_lower)
    if match:
        return {
            "grade": int(match.group(1)),
            "raw_comment": comment,
            "parse_method": "оценка_keyword"
        }
    
    # Паттерн 2: "Балл: X" или "Балл X"
    match = re.search(r'балл[:\s]+(\d+)', comment_lower)
    if match:
        return {
            "grade": int(match.group(1)),
            "raw_comment": comment,
            "parse_method": "балл_keyword"
        }
    
    # Паттерн 3: "X/Y" (например "5/5" или "4/5")
    match = re.search(r'(\d+)\s*/\s*\d+', comment_lower)
    if match:
        return {
            "grade": int(match.group(1)),
            "raw_comment": comment,
            "parse_method": "fraction"
        }
    
    # Паттерн 4: Число в конце строки
    match = re.search(r'(\d+)\s*$', comment_lower)
    if match:
        grade = int(match.group(1))
        if 1 <= grade <= 10:  # Разумный диапазон оценок
            return {
                "grade": grade,
                "raw_comment": comment,
                "parse_method": "number_at_end"
            }
    
    # Паттерн 5: Число в начале строки
    match = re.search(r'^(\d+)', comment_lower)
    if match:
        grade = int(match.group(1))
        if 1 <= grade <= 10:
            return {
                "grade": grade,
                "raw_comment": comment,
                "parse_method": "number_at_start"
            }
    
    return {
        "grade": None,
        "raw_comment": comment,
        "parse_method": "not_found"
    }


@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Обработчик вебхуков от ZenClass."""
    
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {e}"}), 400
    
    # Логируем сырые данные
    print("\n" + "="*60)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ПОЛУЧЕН ВЕБХУК")
    print("="*60)
    print(f"Event: {data.get('event_name')}")
    print(f"ID: {data.get('id')}")
    print(f"Timestamp: {data.get('timestamp')}")
    
    # Проверяем подпись (опционально для теста)
    if SECRET_KEY != "your_secret_key_here":
        is_valid = verify_signature(data, SECRET_KEY)
        print(f"Signature valid: {is_valid}")
        if not is_valid:
            print("⚠️  ВНИМАНИЕ: Подпись не совпадает!")
    
    # Обрабатываем payload
    payload = data.get('payload', {})
    event_name = data.get('event_name', '')
    
    print(f"\n📦 Payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    # Если это событие "Задание принято" - парсим оценку
    if event_name == 'lesson_task_accepted':
        print("\n🎯 СОБЫТИЕ: Задание принято!")
        print(f"   Студент: {payload.get('user_email')}")
        print(f"   Курс: {payload.get('course_name')}")
        print(f"   Задание: {payload.get('task_name')}")
        print(f"   Результат теста: {payload.get('task_result')}")
        
        comment = payload.get('comment', '')
        print(f"   Комментарий: {comment}")
        
        # Парсим оценку
        grade_result = parse_grade_from_comment(comment)
        print(f"\n📊 ПАРСИНГ ОЦЕНКИ:")
        print(f"   Оценка: {grade_result['grade']}")
        print(f"   Метод: {grade_result['parse_method']}")
        
        if grade_result['grade']:
            print(f"\n✅ УСПЕХ: Оценка {grade_result['grade']} распознана!")
        else:
            print(f"\n⚠️  Оценка не найдена в комментарии")
    
    # Другие события
    elif event_name == 'product_user_subscribed':
        print("\n🎯 СОБЫТИЕ: Студент подписался на продукт!")
        print(f"   Email: {payload.get('user_email')}")
        print(f"   Продукт: {payload.get('product_name')}")
        
    elif event_name == 'access_to_course_expired':
        print("\n🎯 СОБЫТИЕ: Закончился доступ к курсу!")
        print(f"   Email: {payload.get('user_email')}")
        print(f"   Курс: {payload.get('course_name')}")
    
    # Сохраняем в лог
    webhooks_log.append({
        "received_at": datetime.now().isoformat(),
        "data": data
    })
    
    print("\n" + "="*60 + "\n")
    
    # ZenClass ожидает код 200
    return jsonify({"status": "ok"}), 200


@app.route('/webhooks', methods=['GET'])
def list_webhooks():
    """Показать все полученные вебхуки."""
    return jsonify(webhooks_log)


@app.route('/test', methods=['POST'])
def test_parse():
    """Тестовый эндпоинт для проверки парсинга комментариев."""
    data = request.get_json()
    comment = data.get('comment', '')
    result = parse_grade_from_comment(comment)
    return jsonify(result)


@app.route('/', methods=['GET'])
def index():
    """Главная страница."""
    return """
    <h1>ZenClass Webhook Tester</h1>
    <p>Сервер работает!</p>
    <ul>
        <li><b>POST /webhook</b> — эндпоинт для вебхуков ZenClass</li>
        <li><a href="/webhooks">GET /webhooks</a> — список полученных вебхуков</li>
        <li><b>POST /test</b> — тест парсинга комментариев (JSON: {"comment": "..."})</li>
    </ul>
    <h2>Тест парсинга оценок:</h2>
    <form id="testForm">
        <input type="text" id="comment" placeholder="Введите комментарий..." style="width: 300px">
        <button type="submit">Проверить</button>
    </form>
    <pre id="result"></pre>
    <script>
        document.getElementById('testForm').onsubmit = async (e) => {
            e.preventDefault();
            const comment = document.getElementById('comment').value;
            const res = await fetch('/test', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({comment})
            });
            const data = await res.json();
            document.getElementById('result').textContent = JSON.stringify(data, null, 2);
        };
    </script>
    """


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 ZenClass Webhook Test Server")
    print("="*60)
    print("Эндпоинты:")
    print("  POST /webhook  — для вебхуков ZenClass")
    print("  GET  /webhooks — список полученных")
    print("  POST /test     — тест парсинга")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=8000, debug=True)
