"""Demo seed data.

Coordinates are approximate town-center estimates for demo purposes only —
replace with real GPS data once a pilot LGA/villages are confirmed (see
README §10, Open questions). Villages here are a placeholder cluster in
Idemili North LGA, Anambra State, chosen only because it's a compact,
well-known set of towns to demo the map with.
"""

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from somfound.models import Category, Report, SourceChannel, Status, Urgency, Village

VILLAGES = [
    {"name": "Ogidi", "ward": "Ogidi", "lga": "Idemili North", "lat": 6.1667, "lon": 6.8333},
    {"name": "Abatete", "ward": "Abatete", "lga": "Idemili North", "lat": 6.1000, "lon": 6.8000},
    {"name": "Nkpor", "ward": "Nkpor", "lga": "Idemili North", "lat": 6.1500, "lon": 6.8300},
    {"name": "Umuoji", "ward": "Umuoji", "lga": "Idemili North", "lat": 6.1200, "lon": 6.7800},
    {"name": "Eziowelle", "ward": "Eziowelle", "lga": "Idemili North", "lat": 6.1300, "lon": 6.7900},
    {"name": "Uke", "ward": "Uke", "lga": "Idemili North", "lat": 6.1400, "lon": 6.7700},
    {"name": "Oraukwu", "ward": "Oraukwu", "lga": "Idemili North", "lat": 6.1100, "lon": 6.8100},
    {"name": "Ideani", "ward": "Ideani", "lga": "Idemili North", "lat": 6.0900, "lon": 6.7600},
]


def seed_villages(session: Session) -> list[Village]:
    existing = session.exec(select(Village)).all()
    if existing:
        return list(existing)

    villages = [Village(**data) for data in VILLAGES]
    session.add_all(villages)
    session.commit()
    for v in villages:
        session.refresh(v)
    return villages


def seed_demo_reports(session: Session, villages: list[Village]) -> None:
    existing = session.exec(select(Report)).first()
    if existing:
        return

    by_name = {v.name: v for v in villages}
    now = datetime.now(timezone.utc)

    demo_reports = [
        dict(
            category=Category.CRIME_SAFETY,
            urgency=Urgency.CRITICAL,
            status=Status.PUBLISHED,
            description="Armed robbery reported near Ogidi main market around 9pm, residents advised to stay indoors.",
            village=by_name["Ogidi"],
            source_channel=SourceChannel.SMS,
            hours_ago=3,
        ),
        dict(
            category=Category.NEEDS_RESOURCES,
            urgency=Urgency.HIGH,
            status=Status.PUBLISHED,
            description="Community borehole in Umuoji has been broken for 3 days, households relying on distant wells.",
            village=by_name["Umuoji"],
            source_channel=SourceChannel.SMS,
            hours_ago=30,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.MODERATE,
            status=Status.PUBLISHED,
            description="Pothole widening on the Abatete-Eziowelle road, motorcycles struggling after rain.",
            village=by_name["Abatete"],
            source_channel=SourceChannel.WEB,
            hours_ago=50,
        ),
        dict(
            category=Category.COMMUNITY_DEV,
            urgency=Urgency.INFORMATIONAL,
            status=Status.PUBLISHED,
            description="New primary school block commissioned in Nkpor, enrollment open for the new term.",
            village=by_name["Nkpor"],
            source_channel=SourceChannel.WEB,
            hours_ago=100,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.MODERATE,
            status=Status.PENDING,
            description="Frequent power outages reported in Oraukwu over the past week.",
            village=by_name["Oraukwu"],
            source_channel=SourceChannel.SMS,
            hours_ago=5,
        ),
    ]

    for data in demo_reports:
        village = data.pop("village")
        hours_ago = data.pop("hours_ago")
        created_at = now - timedelta(hours=hours_ago)
        report = Report(
            village_id=village.id,
            lat=village.lat,
            lon=village.lon,
            created_at=created_at,
            published_at=created_at if data["status"] == Status.PUBLISHED else None,
            **data,
        )
        session.add(report)

    session.commit()
