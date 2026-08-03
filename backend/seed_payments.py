# -*- coding: utf-8 -*-
"""Add realistic payment orders (платёжные поручения) to enrich the paid/obligation
picture. Idempotent-ish: skips numbers already present.

    python backend/seed_payments.py
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

# (number, counterparty, date, amount, (fond,opis,delo), purpose)
PAYMENTS = [
    # СтройМонтаж — два платежа = договор закрыт (8 750 000)
    ("ПП-2023/206", "ТОО «СтройМонтаж KZ»", "2023-04-10", 4375000, ("Ф-3", "Оп-1", "Д-05"),
     "аванс 50% по договору подряда № ПОДР-2023/05 на ремонт архивохранилища"),
    ("ПП-2023/241", "ТОО «СтройМонтаж KZ»", "2023-07-05", 4375000, ("Ф-3", "Оп-1", "Д-05"),
     "окончательный расчёт по договору подряда № ПОДР-2023/05 (акт № АВР-2023/05)"),
    # ИП Сериков — два этапа = частично (2 520 000 из 3 600 000)
    ("ПП-2022/079", "ИП Сериков А.Б.", "2022-03-26", 1080000, ("Ф-2", "Оп-1", "Д-33"),
     "оплата 1 этапа (30%) по договору № УСЛ-2022/33 (акт № АВР-2022/33-1)"),
    ("ПП-2022/124", "ИП Сериков А.Б.", "2022-05-16", 1440000, ("Ф-2", "Оп-1", "Д-33"),
     "оплата 2 этапа (40%) по договору № УСЛ-2022/33 за услуги оцифровки"),
    # АйТи Сервис Плюс — три месяца = частично (600 000 из 2 400 000)
    ("ПП-2023/034", "ТОО «АйТи Сервис Плюс»", "2023-02-05", 200000, ("Ф-2", "Оп-2", "Д-60"),
     "техническое обслуживание за январь 2023 по договору № УСЛ-2023/60"),
    ("ПП-2023/069", "ТОО «АйТи Сервис Плюс»", "2023-03-06", 200000, ("Ф-2", "Оп-2", "Д-60"),
     "техническое обслуживание за февраль 2023 по договору № УСЛ-2023/60"),
    ("ПП-2023/101", "ТОО «АйТи Сервис Плюс»", "2023-04-05", 200000, ("Ф-2", "Оп-2", "Д-60"),
     "техническое обслуживание за март 2023 по договору № УСЛ-2023/60"),
    # Астана Бизнес Центр — ещё два месяца аренды = частично (всего 1 350 000 из 5 400 000)
    ("ПП-2020/061", "ТОО «Астана Бизнес Центр»", "2020-04-03", 450000, ("Ф-1", "Оп-1", "Д-14"),
     "арендная плата за апрель 2020 по договору аренды № АР-2019/14"),
    ("ПП-2020/078", "ТОО «Астана Бизнес Центр»", "2020-05-04", 450000, ("Ф-1", "Оп-1", "Д-14"),
     "арендная плата за май 2020 по договору аренды № АР-2019/14"),
]


def _login():
    body = urllib.parse.urlencode({"username": ADMIN[0], "password": ADMIN[1]}).encode()
    req = urllib.request.Request(API + "/api/auth/login", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def _existing_numbers(token):
    req = urllib.request.Request(API + "/api/documents?limit=200",
                                 headers={"Authorization": "Bearer " + token})
    docs = json.loads(urllib.request.urlopen(req).read())
    return {d.get("doc_number", "") for d in docs}


def _upload(token, fields, filename, content):
    boundary = "----earchivepay31417"
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
    req = urllib.request.Request(
        API + "/api/documents", data=buf.getvalue(),
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req).read())


def main():
    tok = _login()
    have = _existing_numbers(tok)
    todo = [p for p in PAYMENTS if p[0] not in have]
    print(f"Уже в базе: {len(PAYMENTS) - len(todo)} · Добавляю: {len(todo)} платёжных поручений")
    for num, cp, ddate, amount, (f, o, d), purpose in todo:
        body = (
            f"ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № {num} от {ddate}\n\n"
            f"Плательщик: ТОО «Цифровой Архив», БИН 190340012345, ИИК KZ12345678901234567.\n"
            f"Получатель: {cp}.\n"
            f"Назначение платежа: {purpose}.\n"
            f"Сумма: {amount:,} тенге.\n".replace(",", " ")
        )
        fields = {
            "title": f"Платёжное поручение {num}", "description": purpose,
            "fond": f, "opis": o, "delo": d,
            "doc_type": "Платёжное поручение", "doc_number": num, "counterparty": cp,
            "doc_date": ddate, "amount": amount, "currency": "KZT",
        }
        _upload(tok, fields, f"{num.replace('/', '_')}.txt", body)
        print(f"  + {num}  {cp}  {amount:,} ₸".replace(",", " "))
    if not todo:
        print("Нечего добавлять.")
        return
    print("\nЖдём обработки…")
    for _ in range(60):
        req = urllib.request.Request(API + "/api/documents?limit=200",
                                     headers={"Authorization": "Bearer " + tok})
        docs = json.loads(urllib.request.urlopen(req).read())
        pending = [x for x in docs if x["status"] in ("uploaded", "scanning", "processing")]
        print(f"  готово: {len(docs) - len(pending)} / {len(docs)}  (в обработке: {len(pending)})")
        if not pending:
            break
        time.sleep(4)
    print("Готово.")


if __name__ == "__main__":
    sys.exit(main())
