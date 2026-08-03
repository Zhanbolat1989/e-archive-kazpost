# -*- coding: utf-8 -*-
"""Демонстрационный пример кадастровых документов на недвижимость: покупка
здания в 2020 году, затем продажа в 2024-м — с полной цепочкой
правоустанавливающих документов и заменой (supersede) при смене собственника.

    python backend/seed_realestate.py
"""
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = os.environ.get("API_URL", "http://localhost:8001").rstrip("/")
ADMIN = ("admin@earchive.kz", "admin12345")

CADASTRAL_NUMBER = "21:312:001:0157"
ADDRESS = "г. Астана, ул. Кенесары, д. 20"
AREA = 480.5


def _login():
    body = urllib.parse.urlencode({"username": ADMIN[0], "password": ADMIN[1]}).encode()
    req = urllib.request.Request(API + "/api/auth/login", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def _multipart(fields: dict, filename: str, content: str) -> tuple[bytes, str]:
    boundary = "----earchiverealestate5521"
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        buf.write(str(v).encode("utf-8"))
        buf.write(b"\r\n")
    buf.write(f"--{boundary}\r\n".encode())
    buf.write(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
    buf.write(b"Content-Type: text/plain\r\n\r\n")
    buf.write(content.encode("utf-8"))
    buf.write(f"\r\n--{boundary}--\r\n".encode())
    return buf.getvalue(), boundary


def _upload(token, fields, filename, content):
    body, boundary = _multipart(fields, filename, content)
    req = urllib.request.Request(
        API + "/api/documents", data=body,
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _supersede(token, doc_id, fields, filename, content):
    body, boundary = _multipart(fields, filename, content)
    req = urllib.request.Request(
        API + f"/api/documents/{doc_id}/supersede", data=body,
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _existing(token):
    req = urllib.request.Request(API + "/api/documents?limit=200",
                                 headers={"Authorization": "Bearer " + token})
    docs = json.loads(urllib.request.urlopen(req).read())
    return {d.get("doc_number", "") for d in docs}


def _wait_ready(token, doc_id):
    for _ in range(30):
        req = urllib.request.Request(API + f"/api/documents/{doc_id}",
                                     headers={"Authorization": "Bearer " + token})
        d = json.loads(urllib.request.urlopen(req).read())
        if d["status"] in ("ready", "failed", "infected"):
            return d
        time.sleep(3)
    return d


def main():
    tok = _login()
    have = _existing(tok)
    if "ПС-2020/041" in have:
        print("Пример уже загружен — пропускаю (идемпотентно).")
        return

    print(f"Объект: {CADASTRAL_NUMBER}, {ADDRESS}, {AREA} м²\n")

    # 1) 2020 — покупка здания (первичный правоустанавливающий документ)
    body1 = (
        "ДОГОВОР КУПЛИ-ПРОДАЖИ НЕДВИЖИМОГО ИМУЩЕСТВА № ПС-2020/041\n"
        "г. Астана, 14 февраля 2020 г.\n\n"
        "Продавец: ТОО «СтройИнвест Астана», БИН 070540011223.\n"
        "Покупатель: ТОО «Цифровой Архив», БИН 190340012345.\n\n"
        f"Предмет договора: административное здание по адресу {ADDRESS}, "
        f"общей площадью {AREA} кв.м, кадастровый номер {CADASTRAL_NUMBER}.\n"
        "1. Цена объекта составляет 185 000 000 (сто восемьдесят пять миллионов) тенге.\n"
        "2. Право собственности переходит к Покупателю с момента государственной "
        "регистрации в правовом кадастре.\n"
        "3. Обременения на момент заключения договора отсутствуют.\n"
    )
    d1 = _upload(tok, {
        "title": "Договор купли-продажи административного здания", "doc_type": "Правоустанавливающий документ",
        "doc_number": "ПС-2020/041", "counterparty": "ТОО «Цифровой Архив»",
        "doc_date": "2020-02-14", "amount": 185000000, "currency": "KZT",
        "cadastral_number": CADASTRAL_NUMBER, "real_estate_address": ADDRESS, "real_estate_area": AREA,
    }, "PS-2020_041.txt", body1)
    print(f"  + [Правоустанавливающий документ] {d1['title']} ({d1['doc_number']})")

    # 2) 2020 — справка о зарегистрированных правах (правоудостоверяющий документ)
    body2 = (
        "СПРАВКА О ЗАРЕГИСТРИРОВАННЫХ ПРАВАХ (ОБРЕМЕНЕНИЯХ) НА НЕДВИЖИМОЕ ИМУЩЕСТВО\n"
        "№ СЗП-2020/00318 от 2 марта 2020 г.\n\n"
        f"Объект: административное здание, {ADDRESS}.\n"
        f"Кадастровый номер: {CADASTRAL_NUMBER}. Площадь: {AREA} кв.м.\n"
        "Правообладатель: ТОО «Цифровой Архив», БИН 190340012345.\n"
        "Вид права: право собственности. Дата регистрации: 02.03.2020.\n"
        "Основание: Договор купли-продажи № ПС-2020/041 от 14.02.2020.\n"
        "Обременения: не зарегистрированы.\n"
    )
    d2 = _upload(tok, {
        "title": "Справка о зарегистрированных правах на здание", "doc_type": "Справка о зарегистрированных правах",
        "doc_number": "СЗП-2020/00318", "counterparty": "ТОО «Цифровой Архив»",
        "doc_date": "2020-03-02", "cadastral_number": CADASTRAL_NUMBER,
        "real_estate_address": ADDRESS, "real_estate_area": AREA,
    }, "SZP-2020_00318.txt", body2)
    print(f"  + [Справка о зарег. правах] {d2['title']} ({d2['doc_number']})")

    # 3) 2020 — кадастровый (технический) паспорт
    body3 = (
        "КАДАСТРОВЫЙ ПАСПОРТ ОБЪЕКТА НЕДВИЖИМОСТИ\n"
        f"№ КП-2020/0092 от 20 февраля 2020 г.\n\n"
        f"Кадастровый номер: {CADASTRAL_NUMBER}\n"
        f"Адрес: {ADDRESS}\n"
        f"Вид объекта: нежилое здание (административное). Площадь: {AREA} кв.м. Этажность: 3.\n"
        "Год постройки: 2011. Материал стен: кирпич.\n"
    )
    d3 = _upload(tok, {
        "title": "Кадастровый паспорт административного здания", "doc_type": "Кадастровый паспорт",
        "doc_number": "КП-2020/0092", "doc_date": "2020-02-20",
        "cadastral_number": CADASTRAL_NUMBER, "real_estate_address": ADDRESS, "real_estate_area": AREA,
    }, "KP-2020_0092.txt", body3)
    print(f"  + [Кадастровый паспорт] {d3['title']} ({d3['doc_number']})")

    print("\nЖдём обработки исходных документов…")
    for d in (d1, d2, d3):
        _wait_ready(tok, d["id"])

    # 4) 2024 — смена собственника: НОВЫЙ правоустанавливающий документ,
    # заменяющий (supersede) исходный договор купли-продажи 2020 года.
    body4 = (
        "ДОГОВОР КУПЛИ-ПРОДАЖИ НЕДВИЖИМОГО ИМУЩЕСТВА № ПС-2024/077\n"
        "г. Астана, 5 июня 2024 г.\n\n"
        "Продавец: ТОО «Цифровой Архив», БИН 190340012345.\n"
        "Покупатель: ТОО «Байтерек Недвижимость», БИН 150640007744.\n\n"
        f"Предмет договора: административное здание, {ADDRESS}, "
        f"кадастровый номер {CADASTRAL_NUMBER}, площадь {AREA} кв.м.\n"
        "1. Цена объекта составляет 230 000 000 (двести тридцать миллионов) тенге.\n"
        "2. Право собственности Продавца прекращается с момента государственной "
        "регистрации перехода права к Покупателю (ст. 6-7 Закона № 310-III).\n"
    )
    d4 = _supersede(tok, d1["id"], {
        "title": "Договор купли-продажи здания (переход права 2024)",
        "doc_type": "Правоустанавливающий документ",
        "doc_number": "ПС-2024/077", "counterparty": "ТОО «Байтерек Недвижимость»",
        "doc_date": "2024-06-05", "amount": 230000000,
        # кадастровый номер/адрес/площадь/дело наследуются от d1 автоматически
    }, "PS-2024_077.txt", body4)
    print(f"\n  ↻ [Заменяет ПС-2020/041] {d4['title']} ({d4['doc_number']})")

    # 5) 2024 — новая справка о зарегистрированных правах (заменяет старую)
    body5 = (
        "СПРАВКА О ЗАРЕГИСТРИРОВАННЫХ ПРАВАХ (ОБРЕМЕНЕНИЯХ) НА НЕДВИЖИМОЕ ИМУЩЕСТВО\n"
        "№ СЗП-2024/00905 от 10 июня 2024 г.\n\n"
        f"Объект: административное здание, {ADDRESS}.\n"
        f"Кадастровый номер: {CADASTRAL_NUMBER}. Площадь: {AREA} кв.м.\n"
        "Правообладатель: ТОО «Байтерек Недвижимость», БИН 150640007744.\n"
        "Вид права: право собственности. Дата регистрации: 10.06.2024.\n"
        "Основание: Договор купли-продажи № ПС-2024/077 от 05.06.2024.\n"
        "Право предыдущего правообладателя (ТОО «Цифровой Архив») прекращено "
        "10.06.2024 (справка № СЗП-2020/00318 более не действует).\n"
    )
    d5 = _supersede(tok, d2["id"], {
        "title": "Справка о зарегистрированных правах (новый собственник)",
        "doc_type": "Справка о зарегистрированных правах",
        "doc_number": "СЗП-2024/00905", "counterparty": "ТОО «Байтерек Недвижимость»",
        "doc_date": "2024-06-10",
    }, "SZP-2024_00905.txt", body5)
    print(f"  ↻ [Заменяет СЗП-2020/00318] {d5['title']} ({d5['doc_number']})")

    print("\nЖдём обработки новых версий…")
    for d in (d4, d5):
        _wait_ready(tok, d["id"])

    # Проверка истории версий
    req = urllib.request.Request(API + f"/api/documents/{d4['id']}/history",
                                 headers={"Authorization": "Bearer " + tok})
    hist = json.loads(urllib.request.urlopen(req).read())
    print(f"\nИстория объекта {CADASTRAL_NUMBER}:")
    for item in hist["chain"]:
        status = "ТЕКУЩАЯ" if item["is_current"] else f"заменена {item['superseded_at']}"
        print(f"  - {item['title']} ({item['doc_number']}) — {status}")
    print("\nГотово.")


if __name__ == "__main__":
    sys.exit(main())
