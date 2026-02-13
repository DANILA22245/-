"""
Модуль для интеграции с ЦБ РФ
Получение курсов валют и других финансовых данных
"""

from datetime import datetime, timedelta
from zeep import Client
from zeep.exceptions import Fault
import requests
from lxml import etree

# URL SOAP сервиса ЦБ РФ
CBR_SOAP_URL = "http://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx?WSDL"


def get_currency_rates(date=None):
    """
    Получение курсов валют с ЦБ РФ за указанную дату через SOAP
    Возвращает курсы USD и EUR

    Args:
        date: datetime объект (если None, то текущая дата)

    Returns:
        dict: {'success': bool, 'date': str, 'usd': float, 'eur': float}
    """
    try:
        if date is None:
            date = datetime.now()

        # Создаём клиент SOAP
        client = Client(CBR_SOAP_URL)

        # Вызываем метод GetCursOnDate
        result = client.service.GetCursOnDate(date)

        # Парсим результат
        usd_rate = None
        eur_rate = None

        # Ищем нужные валюты в результате
        for valute in result.ValuteCursOnDate:
            if hasattr(valute, "VchCode"):
                if valute.VchCode == "USD":
                    usd_rate = float(valute.Vcurs) / float(valute.Vnom)
                elif valute.VchCode == "EUR":
                    eur_rate = float(valute.Vcurs) / float(valute.Vnom)

        return {
            "success": True,
            "date": date.strftime("%d.%m.%Y"),
            "usd": round(usd_rate, 4) if usd_rate else None,
            "eur": round(eur_rate, 4) if eur_rate else None,
        }

    except Fault as e:
        print(f"SOAP ошибка: {e}")
        return {"success": False, "error": f"SOAP ошибка: {str(e)}"}
    except Exception as e:
        print(f"Ошибка получения курсов: {e}")
        return {"success": False, "error": f"Ошибка: {str(e)}"}


def get_currency_rates_fallback(date=None):
    """
    Альтернативный метод получения курсов через XML напрямую (без SOAP)

    Args:
        date: datetime объект (если None, то текущая дата)

    Returns:
        dict: {'success': bool, 'date': str, 'usd': float, 'eur': float}
    """
    try:
        if date is None:
            date = datetime.now()

        # Форматируем дату для запроса (день/месяц/год)
        date_str = date.strftime("%d/%m/%Y")

        # URL для получения курсов за конкретную дату
        url = f"http://www.cbr.ru/scripts/XML_daily.asp?date_req={date_str}"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Парсим XML
        root = etree.fromstring(response.content)

        usd_rate = None
        eur_rate = None

        for valute in root.findall(".//Valute"):
            char_code = valute.find("CharCode").text
            nominal = float(valute.find("Nominal").text)
            value = float(valute.find("Value").text.replace(",", "."))

            rate = value / nominal

            if char_code == "USD":
                usd_rate = rate
            elif char_code == "EUR":
                eur_rate = rate

        return {
            "success": True,
            "date": date.strftime("%d.%m.%Y"),
            "usd": round(usd_rate, 4) if usd_rate else None,
            "eur": round(eur_rate, 4) if eur_rate else None,
        }

    except Exception as e:
        print(f"Ошибка получения курсов (альтернативный метод): {e}")
        return {"success": False, "error": f"Ошибка: {str(e)}"}


def get_latest_currency_rates():
    """
    Получение последних доступных курсов валют
    Если сегодня нет данных (выходной), возвращает данные за предыдущий день

    Returns:
        dict: {'success': bool, 'date': str, 'usd': float, 'eur': float}
    """
    try:
        # Пробуем получить курс за сегодня
        result = get_currency_rates_fallback()

        # Если сегодня нет данных (выходной или праздник)
        if result["success"] and (result["usd"] is None or result["eur"] is None):
            # Пробуем вчера
            yesterday = datetime.now() - timedelta(days=1)
            result = get_currency_rates_fallback(yesterday)

            # Если и вчера нет, пробуем позавчера
            if result["success"] and (result["usd"] is None or result["eur"] is None):
                day_before = datetime.now() - timedelta(days=2)
                result = get_currency_rates_fallback(day_before)

        return result

    except Exception as e:
        print(f"Ошибка получения последних курсов: {e}")
        return {"success": False, "error": f"Ошибка: {str(e)}"}


def get_currency_by_date(date_str):
    """
    Получение курсов валют за указанную дату

    Args:
        date_str: строка в формате 'ГГГГ-ММ-ДД'

    Returns:
        dict: {'success': bool, 'date': str, 'usd': float, 'eur': float}
    """
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")

        # Сначала пробуем через SOAP
        result = get_currency_rates(date)

        # Если SOAP не сработал, используем альтернативный метод
        if not result["success"]:
            result = get_currency_rates_fallback(date)

        return result

    except ValueError as e:
        return {
            "success": False,
            "error": "Неверный формат даты. Используйте ГГГГ-ММ-ДД",
        }
    except Exception as e:
        print(f"Ошибка получения курсов за дату: {e}")
        return {"success": False, "error": f"Ошибка: {str(e)}"}


def get_all_currencies(date=None):
    """
    Получение всех валют с курсами за указанную дату

    Args:
        date: datetime объект (если None, то текущая дата)

    Returns:
        dict: {'success': bool, 'date': str, 'currencies': list}
    """
    try:
        if date is None:
            date = datetime.now()

        # Форматируем дату для запроса
        date_str = date.strftime("%d/%m/%Y")

        # URL для получения курсов за конкретную дату
        url = f"http://www.cbr.ru/scripts/XML_daily.asp?date_req={date_str}"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Парсим XML
        root = etree.fromstring(response.content)

        currencies = []

        for valute in root.findall(".//Valute"):
            char_code = valute.find("CharCode").text
            nominal = float(valute.find("Nominal").text)
            value = float(valute.find("Value").text.replace(",", "."))
            name = valute.find("Name").text

            rate = value / nominal

            currencies.append(
                {
                    "code": char_code,
                    "name": name,
                    "nominal": nominal,
                    "rate": round(rate, 4),
                    "value": round(value, 4),
                }
            )

        return {
            "success": True,
            "date": date.strftime("%d.%m.%Y"),
            "currencies": currencies,
        }


    except Exception as e:
        print(f"Ошибка получения всех валют: {e}")
        return {"success": False, "error": f"Ошибка: {str(e)}"}
