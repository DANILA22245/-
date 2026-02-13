from flask import Flask, request, jsonify, render_template, session
import json
import os
from datetime import datetime
from Centrobank_kurs import get_latest_currency_rates, get_currency_by_date, get_all_currencies


app = Flask(__name__, static_folder='static', template_folder='.')
app.secret_key = app.secret_key = os.urandom(24).hex()  # Или другой уникальный ключ

# Путь к файлу с пользователями
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, 'users.json')

# Создаём файл, если он не существует
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)

@app.route('/')
def Site():
    return render_template('Site.html')

# === РОУТЫ АВТОРИЗАЦИИ ===
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        if not data.get('username') or not data.get('password'):
            return jsonify({'success': False, 'error': 'Введи логин и пароль, кореш'}), 400
        
        # Загружаем пользователей
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = json.load(f)
        
        # Ищем пользователя
        user = next((u for u in users if u['username'] == data['username']), None)
        
        if not user:
            return jsonify({'success': False, 'error': 'Не знаю таких'}), 404
        
        # Проверяем пароль
        if user['password'] != data['password']:
            return jsonify({'success': False, 'error': 'Неверный пароль'}), 401
        
        # Создаём сессию
        session['user_id'] = user['id']
        session['username'] = user['username']
        
        # Возвращаем данные без пароля
        user_safe = {k: v for k, v in user.items() if k != 'password'}
        
        return jsonify({
            'success': True,
            'message': f'Здарова, кореш',
            'user': user_safe
        }), 200

    except Exception as e:
        print(f"Ошибка входа: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    """Выход из системы"""
    session.clear()
    return jsonify({'success': True, 'message': 'Давай пока'}), 200

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """Проверка авторизации"""
    if 'user_id' in session:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = json.load(f)
        
        user = next((u for u in users if u['id'] == session['user_id']), None)
        
        if user:
            user_safe = {k: v for k, v in user.items() if k != 'password'}
            return jsonify({'success': True, 'authenticated': True, 'user': user_safe}), 200

    return jsonify({'success': True, 'authenticated': False}), 200

# === РОУТЫ РЕГИСТРАЦИИ ===
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        # Валидация данных
        if not data.get('username') or len(data['username']) < 3:
            return jsonify({'success': False, 'error': 'Братуха, минимум 3 буквы черкани'}), 400
        
        # Валидация возраста
        age = data.get('age')
        if not age:
            return jsonify({'success': False, 'error': 'Укажи свой возраст, кореш'}), 400
        
        try:
            age = int(age)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Возраст должен быть числом'}), 400
        
        if age < 18:
            return jsonify({'success': False, 'error': 'Сюда только 18+, подрасти сначала'}), 400
        
        if age > 120:
            return jsonify({'success': False, 'error': 'Не ври, кореш'}), 400
        
        if not data.get('password') or len(data['password']) < 5:
            return jsonify({'success': False, 'error': 'Слишком мало символов, минимум 5 давай'}), 400
        
        if data['password'] != data.get('confirmPassword'):
            return jsonify({'success': False, 'error': 'Пароли не совпадают'}), 400
        
        # Загружаем существующих пользователей
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = json.load(f)
        
        # Проверяем, существует ли уже такой пользователь
        username_exists = any(user['username'] == data['username'] for user in users)
        
        if username_exists:
            return jsonify({'success': False, 'error': 'У меня уже есть кореш с таким именем'}), 400
        
        # Создаем нового пользователя
        new_user = {
            'id': len(users) + 1,
            'username': data['username'],
            'dubina': data.get('dubina', 'не указано'),
            'age': data.get('age'),
            'registeredAt': datetime.now().isoformat(),
            'status': 'active'
        }
        
        # Сохраняем пароль отдельно
        new_user_secure = new_user.copy()
        new_user_secure['password'] = data['password']
        
        users.append(new_user_secure)
        
        # Сохраняем в файл
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        
        # Возвращаем успешный ответ
        return jsonify({
            'success': True, 
            'message': f'Подстрахуй, кореш {data["username"]}',
            'user': new_user
        }), 200

    except Exception as e:
        print(f"Ошибка регистрации: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/api/users', methods=['GET'])
def get_users():
    """Получить список всех пользователей (для админа)"""
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = json.load(f)
        
        # Убираем пароли из ответа
        users_safe = [{k: v for k, v in user.items() if k != 'password'} for user in users]
        
        return jsonify({
            'success': True,
            'users': users_safe,
            'total': len(users_safe)
        }), 200

    except Exception as e:
        print(f"Ошибка получения пользователей: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

# === РОУТЫ ИНТЕГРАЦИИ С ЦБ РФ ===
@app.route('/api/currency-rates', methods=['GET'])
def currency_rates():
    """Получение курсов валют от ЦБ РФ за указанную дату"""
    try:
        date_str = request.args.get('date')
        
        if date_str:
            result = get_currency_by_date(date_str)
        else:
            result = get_latest_currency_rates()
        
        return jsonify(result), 200

    except Exception as e:
        print(f"Ошибка получения курсов валют: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/api/currency-rates/all', methods=['GET'])
def all_currency_rates():
    """Получение всех валют с курсами"""
    try:
        date_str = request.args.get('date')
        
        if date_str:
            date = datetime.strptime(date_str, '%Y-%m-%d')
            result = get_all_currencies(date)
        else:
            result = get_all_currencies()
        
        return jsonify(result), 200

    except Exception as e:
        print(f"Ошибка получения всех валют: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500
# Добавь этот роут после остальных роутов, но перед запуском сервера

@app.route('/currency')
def currency_page():
    """Страница с курсами валют"""
    # Проверяем авторизацию
    if 'user_id' not in session:
        return render_template('Site.html')
    
    return render_template('currency.html')

@app.route('/api/currency-rates/history', methods=['GET'])
def currency_history():
    """Получение истории курсов за период"""
    try:
        days = request.args.get('days', 365, type=int)
        result = get_currency_history(days)
        return jsonify(result), 200
    except Exception as e:
        print(f"Ошибка получения истории курсов: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500


@app.route('/api/currency-rates/last-week', methods=['GET'])
def currency_last_week():
    """Получение курсов за последние 7 дней"""
    try:
        result = get_currency_last_week()
        return jsonify(result), 200
    except Exception as e:
        print(f"Ошибка получения данных за неделю: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Polyak Production - сервер запущен!")
    print("📍 Адрес: http://localhost:5000")
    print("📁 Данные пользователей сохраняются в: users.json")
    print("💱 Интеграция с ЦБ РФ активна")
    print("=" * 50)
    
    # Для Render - используем переменную окружения PORT
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)