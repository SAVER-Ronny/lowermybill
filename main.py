from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
import stripe
import os

app = FastAPI()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
DOMAIN = os.environ.get("DOMAIN", "http://localhost:8000")

class BillRequest(BaseModel):
    bill_text: str

PREVIEW_PROMPT = """You are an expert at negotiating bills down. 
Given a bill description, write 2 punchy sentences:
1. Estimate realistic savings - typically 20-40% of their current bill per year. 
   NEVER suggest saving more than they currently pay.
   If they pay $100/month, max savings is $480/year (40%).
2. Tease the exact strategy without revealing it.
End with: "Unlock the full word-for-word script below ↓"
Be specific with dollar amounts. Be realistic."""

FULL_SCRIPT_PROMPT = """You are a world-class bill negotiation expert.
Generate a complete word-for-word script. Use this exact format:

📞 OPENING LINE
[Exact words when they answer - casual and confident]

🎯 THE REQUEST
[Exact words to ask for a discount - be specific]

💪 IF THEY SAY NO — USE THESE 3 COMEBACKS
1. [First rebuttal]
2. [Second rebuttal] 
3. [Third rebuttal - mention cancelling]

🏆 CLOSING LINE
[How to lock in the deal]

⏰ BEST TIME TO CALL
[Specific day + time + why]

🔄 IF NOTHING WORKS
[Escalation strategy]

💡 PRO TIP
[One insider trick specific to this type of bill]

Be extremely specific. Use real numbers. Sound natural, not scripted."""

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html") as f:
        return f.read()

@app.get("/success", response_class=HTMLResponse)
async def success_page():
    with open("static/index.html") as f:
        return f.read()

@app.post("/api/preview")
async def preview(request: BillRequest):
    if len(request.bill_text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Tell us more about your bill")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PREVIEW_PROMPT},
            {"role": "user", "content": f"My bill: {request.bill_text}"}
        ],
        max_tokens=120
    )
    return {"preview": response.choices[0].message.content}

@app.post("/api/checkout")
async def checkout(request: BillRequest):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Bill Negotiation Script",
                    "description": "Word-for-word script to lower your bill today"
                },
                "unit_amount": 700,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{DOMAIN}/",
        metadata={"bill_text": request.bill_text[:1000]}
    )
    return {"url": session.url}

@app.get("/api/script")
async def get_script(session_id: str):
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session")

    if session.payment_status != "paid":
        raise HTTPException(status_code=402, detail="Payment required")

    bill_text = session.metadata.get("bill_text", "")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": FULL_SCRIPT_PROMPT},
            {"role": "user", "content": f"My bill: {bill_text}"}
        ],
        max_tokens=700
    )
    return {"script": response.choices[0].message.content}

app.mount("/static", StaticFiles(directory="static"), name="static")
# force redeploy

