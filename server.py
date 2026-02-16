import os
from flask import Flask, request, jsonify, render_template, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from Centrobank_kurs import get_latest_currency_rates, get_all_currencies
from flask_cors import CORS
import json
from werkzeug.security import generate_password_hash, check_password_hash  # Уже импортировано - отлично!

app = Flask(__name__, static_folder='static', template_folder='.')
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.secret_key = os.urandom(24).hex()

# === НАСТРОЙКА БАЗЫ ДАННЫХ ===
database_url = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
if database_url and database_url.startswith("postgres://"):
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
    password_hash = db.Column(db.String(200), nullable=False)  # ИЗМЕНЕНО: безопасное имя поля

    @property
    def password(self):
        raise AttributeError('Пароль нельзя читать!')
    
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'dubina': self.dubina,
            'age': self.age,
            'registeredAt': self.registeredAt.isoformat(),
            'status': self.status
        }

# === БЕЗОПАСНАЯ МИГРАЦИЯ (БЕЗ ПЕРЕНОСА ID, С ХЕШИРОВАНИЕМ) ===
def migrate_old_users():
    if User.query.first():
        print("⏭️ База уже содержит данные, миграция пропущена")
        return
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    users_file = os.path.join(base_dir, 'users.json')
    
    if not os.path.exists(users_file):
        print("⏭️ Файл users.json не найден, миграция не требуется")
        return
    
    try:
        with open(users_file, 'r', encoding='utf-8') as f:
            old_users = json.load(f)
        
        migrated = 0
        for u in old_users:
            # Очистка ключей и значений от пробелов
            clean = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in u.items()}
            
            # Валидация
            if not clean.get('username') or not clean.get('password'):
                continue
            if User.query.filter_by(username=clean['username'].strip()).first():
                continue
            
            # Обработка возраста
            try:
                age = int(clean.get('age', 18))
                age = max(18, min(age, 120))
            except:
                age = 18
            
            # Обработка даты
            try:
                reg_date = datetime.fromisoformat(clean['registeredAt'].strip()) if clean.get('registeredAt') else datetime.utcnow()
            except:
                reg_date = datetime.utcnow()
            
            # Создание пользователя С ХЕШИРОВАНИЕМ
            new_user = User()
            new_user.username = clean['username'].strip()
            new_user.dubina = clean.get('dubina', 'не указано').strip()
            new_user.age = age
            new_user.status = clean.get('status', 'active').strip()
            new_user.registeredAt = reg_date
            new_user.password = clean['password']  # Автоматически хешируется через @password.setter
            
            db.session.add(new_user)
            migrated += 1
        
        db.session.commit()
        print(f"✅ Успешно перенесено {migrated} пользователей в БД (пароли защищены хешем!)")
        
        # Опционально: удаление файла после миграции (на Render файловая система эфемерна)
        try:
            os.remove(users_file)
            print("🗑️ Файл users.json удалён после миграции")
        except:
            pass
            
    except Exception as e:
        db.session.rollback()
        print(f"❌ Ошибка миграции: {str(e)[:100]}")

# Инициализация БД и миграция
with app.app_context():
    db.create_all()
    migrate_old_users()

# === ИСПРАВЛЕННЫЕ РОУТЫ С ХЕШИРОВАНИЕМ ===
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        
        # Валидация
        if len(username) < 3:
            return jsonify({'success': False, 'error': 'Братуха, минимум 3 буквы черкани'}), 400
        
        try:
            age = int(data.get('age', 0))
            if age < 18 or age > 120:
                return jsonify({'success': False, 'error': 'Сюда только 18+, подрасти сначала'}), 400
        except:
            return jsonify({'success': False, 'error': 'Возраст должен быть числом'}), 400
        
        if len(data.get('password', '')) < 5:
            return jsonify({'success': False, 'error': 'Слишком мало символов, минимум 5 давай'}), 400
        if data['password'] != data.get('confirmPassword'):
            return jsonify({'success': False, 'error': 'Пароли не совпадают'}), 400
        
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'error': 'У меня уже есть кореш с таким именем'}), 400
        
        # Создание пользователя С ХЕШИРОВАНИЕМ
        new_user = User()
        new_user.username = username
        new_user.dubina = str(data.get('dubina', 'не указано')).strip()
        new_user.age = age
        new_user.status = 'active'
        new_user.password = data['password']  # Авто-хеширование
        
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
        user = User.query.filter_by(username=data.get('username', '').strip()).first()
        
        # БЕЗОПАСНАЯ ПРОВЕРКА ПАРОЛЯ
        if not user or not user.verify_password(data.get('password', '')):
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

# Остальные роуты (/logout, /check-auth, /users, валюты) остаются БЕЗ ИЗМЕНЕНИЙ
# (они не работают с паролями напрямую)

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

@app.route('/')
def Site():
    return render_template('Site.html')
@app.route('/ban')
def ban_page():
    return render_template('ban.html')
@app.route('/terms')
def terms_page():
    return render_template('terms.html')

# === ЗАПУСК ===
if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Polyak Production - сервер запущен!")
    print(f"📍 Порт: {os.environ.get('PORT', 5000)}")
    print(f"🐘 БД: {'PostgreSQL (Render)' if 'DATABASE_URL' in os.environ else 'SQLite (локально)'}")
    print("🔒 Пароли хешируются с использованием Werkzeug")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)