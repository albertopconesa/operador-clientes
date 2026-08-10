import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


load_dotenv()

BASE = Path(__file__).parent
DB = BASE / "operador.db"

app = FastAPI(title="Operador de Captación Web")

app.mount(
    "/static",
    StaticFiles(directory=BASE / "static"),
    name="static"
)


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()

    con.execute("""
    CREATE TABLE IF NOT EXISTS prospects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      place_id TEXT UNIQUE,
      name TEXT NOT NULL,
      address TEXT,
      phone TEXT,
      website TEXT,
      maps_url TEXT,
      rating REAL,
      reviews INTEGER,
      score INTEGER,
      status TEXT DEFAULT 'nuevo',
      sector TEXT,
      zone TEXT,
      raw_json TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    con.commit()
    con.close()


init_db()


class SearchIn(BaseModel):
    sector: str
    zone: str
    only_without_website: bool = True
    max_results: int = 20


class SaveIn(BaseModel):
    business: dict
    sector: str = ""
    zone: str = ""


class StatusIn(BaseModel):
    status: str


class AnalyzeIn(BaseModel):
    business: dict


def score_business(p: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []

    website = p.get("websiteUri")
    phone = (
        p.get("nationalPhoneNumber")
        or p.get("internationalPhoneNumber")
    )

    rating = float(p.get("rating") or 0)
    reviews = int(p.get("userRatingCount") or 0)

    if not website:
        score += 4
        reasons.append("Sin web asociada")

    if phone:
        score += 2
        reasons.append("Teléfono disponible")

    if reviews >= 50:
        score += 2
        reasons.append("50+ reseñas")

    elif reviews >= 10:
        score += 1
        reasons.append("10+ reseñas")

    if rating >= 4.2 and reviews >= 5:
        score += 1
        reasons.append("Buena valoración")

    if p.get("businessStatus") == "OPERATIONAL":
        score += 1
        reasons.append("Negocio operativo")

    return min(score, 10), reasons


def normalize(p: dict) -> dict:
    score, reasons = score_business(p)

    return {
        "place_id": p.get("id"),
        "name": (
            (p.get("displayName") or {}).get("text")
            or "Sin nombre"
        ),
        "address": p.get("formattedAddress") or "",
        "phone": (
            p.get("nationalPhoneNumber")
            or p.get("internationalPhoneNumber")
            or ""
        ),
        "website": p.get("websiteUri") or "",
        "maps_url": p.get("googleMapsUri") or "",
        "rating": p.get("rating") or 0,
        "reviews": p.get("userRatingCount") or 0,
        "business_status": p.get("businessStatus") or "",
        "types": p.get("types") or [],
        "score": score,
        "reasons": reasons,
        "raw": p,
    }


@app.get("/")
def home():
    return FileResponse(
        BASE / "static" / "index.html"
    )


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(
        BASE / "static" / "manifest.webmanifest"
    )


@app.get("/sw.js")
def sw():
    return FileResponse(
        BASE / "static" / "sw.js",
        media_type="application/javascript"
    )


@app.post("/api/search")
async def search(inp: SearchIn):

    key = os.getenv(
        "GOOGLE_PLACES_API_KEY",
        ""
    ).strip()

    if not key or key.startswith("pega_"):

        demo = [
            {
                "id": "demo1",
                "displayName": {
                    "text": f"Taller Ejemplo {inp.zone}"
                },
                "formattedAddress": f"Centro, {inp.zone}",
                "nationalPhoneNumber": "968 000 001",
                "rating": 4.7,
                "userRatingCount": 84,
                "googleMapsUri": "https://maps.google.com",
                "businessStatus": "OPERATIONAL",
                "types": ["car_repair"]
            },
            {
                "id": "demo2",
                "displayName": {
                    "text": f"Reformas Ejemplo {inp.zone}"
                },
                "formattedAddress": (
                    f"Avenida Principal, {inp.zone}"
                ),
                "nationalPhoneNumber": "968 000 002",
                "rating": 4.4,
                "userRatingCount": 27,
                "googleMapsUri": "https://maps.google.com",
                "businessStatus": "OPERATIONAL",
                "types": ["general_contractor"]
            },
            {
                "id": "demo3",
                "displayName": {
                    "text": f"Negocio con Web {inp.zone}"
                },
                "formattedAddress": (
                    f"Calle Mayor, {inp.zone}"
                ),
                "nationalPhoneNumber": "968 000 003",
                "websiteUri": "https://example.com",
                "rating": 4.5,
                "userRatingCount": 110,
                "googleMapsUri": "https://maps.google.com",
                "businessStatus": "OPERATIONAL",
                "types": ["store"]
            },
        ]

        items = [
            normalize(x)
            for x in demo
        ]

        if inp.only_without_website:
            items = [
                x
                for x in items
                if not x["website"]
            ]

        return {
            "mode": "demo",
            "items": sorted(
                items,
                key=lambda x: x["score"],
                reverse=True
            )
        }

    url = (
        "https://places.googleapis.com/"
        "v1/places:searchText"
    )

    mask = ",".join([
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.websiteUri",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.types"
    ])

    payload = {
        "textQuery": (
            f"{inp.sector} en {inp.zone}"
        ),
        "languageCode": "es",
        "regionCode": "ES",
        "pageSize": max(
            1,
            min(inp.max_results, 20)
        )
    }

    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": mask,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(
        timeout=25
    ) as client:

        r = await client.post(
            url,
            json=payload,
            headers=headers
        )

    if r.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Google Places: {r.text}"
        )

    places = r.json().get(
        "places",
        []
    )

    items = [
        normalize(x)
        for x in places
    ]

    if inp.only_without_website:
        items = [
            x
            for x in items
            if not x["website"]
        ]

    items.sort(
        key=lambda x: (
            x["score"],
            x["reviews"]
        ),
        reverse=True
    )

    return {
        "mode": "real",
        "items": items
    }


@app.post("/api/prospects")
def save_prospect(inp: SaveIn):

    b = inp.business
    con = db()

    con.execute("""
    INSERT INTO prospects(
        place_id,
        name,
        address,
        phone,
        website,
        maps_url,
        rating,
        reviews,
        score,
        sector,
        zone,
        raw_json
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)

    ON CONFLICT(place_id)
    DO UPDATE SET
      name=excluded.name,
      address=excluded.address,
      phone=excluded.phone,
      website=excluded.website,
      maps_url=excluded.maps_url,
      rating=excluded.rating,
      reviews=excluded.reviews,
      score=excluded.score,
      sector=excluded.sector,
      zone=excluded.zone,
      raw_json=excluded.raw_json
    """, (
        b.get("place_id"),
        b.get("name"),
        b.get("address"),
        b.get("phone"),
        b.get("website"),
        b.get("maps_url"),
        b.get("rating"),
        b.get("reviews"),
        b.get("score"),
        inp.sector,
        inp.zone,
        json.dumps(
            b,
            ensure_ascii=False
        )
    ))

    con.commit()
    con.close()

    return {
        "ok": True
    }


@app.get("/api/prospects")
def list_prospects():

    con = db()

    rows = con.execute("""
        SELECT *
        FROM prospects
        ORDER BY score DESC, created_at DESC
    """).fetchall()

    con.close()

    return [
        dict(r)
        for r in rows
    ]


@app.patch(
    "/api/prospects/{pid}/status"
)
def set_status(
    pid: int,
    inp: StatusIn
):

    allowed = {
        "nuevo",
        "contactar",
        "contactado",
        "interesado",
        "cliente",
        "descartado"
    }

    if inp.status not in allowed:
        raise HTTPException(
            400,
            "Estado no válido"
        )

    con = db()

    con.execute(
        """
        UPDATE prospects
        SET status=?
        WHERE id=?
        """,
        (
            inp.status,
            pid
        )
    )

    con.commit()
    con.close()

    return {
        "ok": True
    }


@app.post("/api/analyze")
def analyze(inp: AnalyzeIn):

    key = os.getenv(
        "OPENAI_API_KEY",
        ""
    ).strip()

    b = inp.business

    if (
        not key
        or key.startswith("pega_")
    ):

        return {
            "mode": "demo",
            "text": (
                f"Prioriza "
                f"{b.get('name', 'este negocio')}: "
                f"tiene una puntuación "
                f"{b.get('score', '?')}/10. "
                "Propón una web sencilla con llamada, "
                "WhatsApp, servicios, ubicación y reseñas. "
                "Contacto recomendado: breve, personalizado "
                "y sin afirmar que ya representas al negocio."
            )
        }

    from openai import OpenAI

    client = OpenAI(
        api_key=key
    )

    prompt = f"""
Actúa como analista comercial para una agencia web local en España.

Analiza este prospecto y devuelve en español:

1) Por qué puede necesitar web.
2) Propuesta de web de 5 secciones.
3) Mensaje inicial de contacto de máximo 80 palabras.
4) Objeción probable y respuesta.

No inventes datos ni afirmes relación con el negocio.

Prospecto:
{json.dumps(b, ensure_ascii=False)}
"""

    response = client.responses.create(
        model=os.getenv(
            "OPENAI_MODEL",
            "gpt-5.6"
        ),
        input=prompt
    )

    return {
        "mode": "real",
        "text": response.output_text
    }


@app.get("/demo")
async def demo():
    return FileResponse(
        BASE / "static" / "demo.html"
    )
