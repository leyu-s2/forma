from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx
import os

app = FastAPI()

# URL Salesap API (основной)
SALESAP_API_URL = "https://api.salesap.ru/v1"
# Твой токен Salesap, лучше хранить в Railway Variables (API_TOKEN)
API_TOKEN = os.getenv("API_TOKEN")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
 
    # 1️⃣ Получаем токен из аргумента
    token_query = request.query_params.get("token")
    token_header = request.headers.get("Authorization")  # "Bearer <TOKEN>"
    body = await request.json()
    token_body = body.get("token")

    # Проверяем любой источник
    token = token_query or (token_header[7:] if token_header and token_header.startswith("Bearer ") else None) or token_body
        return JSONResponse(status_code=403, content={"error": "invalid token"})

    # 2️⃣ Получаем тело запроса
    body = await request.json()
    deal_id = body.get("deal_id") or body.get("id")

    if not deal_id:
        return JSONResponse(status_code=400, content={"error": "no deal id"})

    # 3️⃣ Отвечаем CRM сразу, чтобы не ждать
    background_tasks.add_task(process_webhook, deal_id)
    return JSONResponse(status_code=200, content={"status": "received"})


async def process_webhook(deal_id: str):
   
    headers = {"Authorization": f"Bearer {API_TOKEN}"}

    async with httpx.AsyncClient(timeout=30) as client:
        # 1️⃣ Получаем данные исходной сделки
        r = await client.get(f"{SALESAP_API_URL}/deals/{deal_id}", headers=headers)
        if r.status_code != 200:
            print(f"[ERROR] Не удалось получить сделку {deal_id}: {r.text}")
            return
        deal = r.json()

        # 2️⃣ Подготавливаем данные для дубля
        #    (убираем id и поля, которые нельзя повторить)
        new_deal_data = {
            "title": f"{deal['title']} (Дубль)",
            "status_id": deal.get("status_id"),
            "price": deal.get("price"),
            "custom_fields": deal.get("custom_fields", []),
            "responsible_user_id": deal.get("responsible_user_id"),
        }

        # 3️⃣ Создаём дубль сделки
        r2 = await client.post(f"{SALESAP_API_URL}/deals", headers=headers, json=new_deal_data)
        if r2.status_code != 201:
            print(f"[ERROR] Не удалось создать дубль: {r2.text}")
            return
        new_deal = r2.json()
        new_deal_id = new_deal.get("id")
        print(f"[OK] Создан дубль сделки {new_deal_id}")

        # 4️⃣ Создаём связь между сделками
        relation_data = {
            "from_type": "deal",
            "from_id": deal_id,
            "to_type": "deal",
            "to_id": new_deal_id,
            "relation_type": "linked"  # пример типа связи
        }

        r3 = await client.post(f"{SALESAP_API_URL}/relations", headers=headers, json=relation_data)
        if r3.status_code not in (200, 201):
            print(f"[ERROR] Не удалось создать связь: {r3.text}")
            return

        print(f"[OK] Сделки {deal_id} и {new_deal_id} связаны успешно ✅")
