import os
from flask import Flask, request, jsonify, render_template, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from Centrobank_kurs import get_latest_currency_rates, get_all_currencies
from flask_cors import CORS
import json
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='static', template_folder='.')
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.secret_key = os.urandom(24).hex()

# === НАСТРОЙКА БАЗЫ ДАННЫХ ===
database_url = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# === МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ ===
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    dubina = db.Column(db.String(80), nullable=False, default='не указано')
    age = db.Column(db.Integer, nullable=False)
    registeredAt = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='active')
    password = db.Column(db.String(120), nullable=False)  # ⚠️ В продакшене хешируйте!

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'dubina': self.dubina,
            'age': self.age,
            'registeredAt': self.registeredAt.isoformat(),
            'status': self.status
        }

# === МИГРАЦИЯ СТАРЫХ ДАННЫХ (запустится ОДИН РАЗ при первом деплое) ===
def migrate_old_users():
    """Переносит пользователей из users.json в PostgreSQL (только если база пуста)"""
    if User.query.first():
        return  # База уже заполнена
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    users_file = os.path.join(base_dir, 'users.json')
    
    if not os.path.exists(users_file):
        return
    
    try:
        with open(users_file, 'r', encoding='utf-8') as f:
            old_users = json.load(f)
        
        for u in old_users:
            # Очищаем ключи от пробелов (как в вашем users.json: "id " -> "id")
            clean_user = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in u.items()}
            
            # Пропускаем некорректные записи
            if not clean_user.get('username') or not clean_user.get('password'):
                continue
            
            try:
                age = int(clean_user.get('age', 18))
                if age < 18: age = 18
            except:
                age = 18
            
            new_user = User(
                id=clean_user.get('id', None),  # id будет проигнорирован, если не уникален
                username=clean_user['username'].strip(),
                dubina=clean_user.get('dubina', 'не указано').strip(),
                age=age,
                password=clean_user['password'],
                status=clean_user.get('status', 'active').strip(),
                registeredAt=datetime.fromisoformat(clean_user['registeredAt'].strip()) if 'registeredAt' in clean_user else datetime.utcnow()
            )
            db.session.add(new_user)
        
        db.session.commit()
        print(f"✅ Мигрировано {len(old_users)} пользователей из users.json")
    except Exception as e:
        print(f"⚠️ Ошибка миграции: {e}")

# Создаём таблицы и мигрируем данные при запуске
with app.app_context():
    db.create_all()
    migrate_old_users()  # Автоматически сработает ТОЛЬКО при первом запуске на Render

# === РОУТЫ (полностью переписаны под БД) ===
@app.route('/')
def Site():
    return render_template('Site.html')

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data.get('username') or len(data['username'].strip()) < 3:
            return jsonify({'success': False, 'error': 'Братуха, минимум 3 буквы черкани'}), 400
        
        age = data.get('age')
        if not age:
            return jsonify({'success': False, 'error': 'Укажи свой возраст, кореш'}), 400
        try:
            age = int(age)
        except:
            return jsonify({'success': False, 'error': 'Возраст должен быть числом'}), 400
        if age < 18 or age > 120:
            return jsonify({'success': False, 'error': 'Сюда только 18+, подрасти сначала'}), 400
        
        if not data.get('password') or len(data['password']) < 5:
            return jsonify({'success': False, 'error': 'Слишком мало символов, минимум 5 давай'}), 400
        if data['password'] != data.get('confirmPassword'):
            return jsonify({'success': False, 'error': 'Пароли не совпадают'}), 400
        
        if User.query.filter_by(username=data['username'].strip()).first():
            return jsonify({'success': False, 'error': 'У меня уже есть кореш с таким именем'}), 400
        
        new_user = User(
            username=data['username'].strip(),
            dubina=str(data.get('dubina', 'не указано')).strip(),
            age=age,
            password=data['password'],
            status='active'
        )
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Подстрахуй, кореш {new_user.username}',
            'user': new_user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка регистрации: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data.get('username') or not data.get('password'):
            return jsonify({'success': False, 'error': 'Введи логин и пароль, кореш'}), 400
        
        user = User.query.filter_by(username=data['username']).first()
        if not user or user.password != data['password']:
            return jsonify({'success': False, 'error': 'Не знаю таких'}), 404
        
        session['user_id'] = user.id
        session['username'] = user.username
        
        return jsonify({
            'success': True,
            'message': 'Здарова, кореш',
            'user': user.to_dict()
        }), 200
    except Exception as e:
        print(f"Ошибка входа: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Давай пока'}), 200

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            return jsonify({'success': True, 'authenticated': True, 'user': user.to_dict()}), 200
    return jsonify({'success': True, 'authenticated': False}), 200

@app.route('/api/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify({
        'success': True,
        'users': [u.to_dict() for u in users],
        'total': len(users)
    }), 200

# === РОУТЫ ВАЛЮТ (БЕЗ ИЗМЕНЕНИЙ) ===
@app.route('/api/currency-rates', methods=['GET'])
def currency_rates():
    try:
        date_str = request.args.get('date')
        result = get_currency_by_date(date_str) if date_str else get_latest_currency_rates()
        return jsonify(result), 200
    except Exception as e:
        print(f"Ошибка курсов: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/api/currency-rates/all', methods=['GET'])
def all_currency_rates():
    try:
        date_str = request.args.get('date')
        result = get_all_currencies(datetime.strptime(date_str, '%Y-%m-%d')) if date_str else get_all_currencies()
        return jsonify(result), 200
    except Exception as e:
        print(f"Ошибка всех валют: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/currency')
def currency_page():
    if 'user_id' not in session:
        return render_template('Site.html')
    return render_template('currency.html')

# === ЗАПУСК ===
if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Polyak Production - сервер запущен!")
    print(f"📍 Порт: {os.environ.get('PORT', 5000)}")
    print(f"🐘 БД: {'PostgreSQL (Render)' if 'DATABASE_URL' in os.environ else 'SQLite (локально)'}")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)