"""Demo seed data.

LGA names and coordinates sourced from xosasx/nigerian-local-government-areas
(github.com/xosasx/nigerian-local-government-areas, itself Wikidata-derived)
and cross-checked against Wikipedia's per-state LGA lists for name accuracy —
but coordinates are still only as good as that source. Seven entries had
verifiable errors (lat/lon swapped, duplicate coordinates shared across two
different LGAs, one point 6 degrees out of range) and were corrected here
using general geographic knowledge, not survey data — flagged inline. Treat
all 95 as approximate pending real GPS data, same caveat as everything else
placeholder in this repo.
"""

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from somfound.models import LGA, Category, Report, RewardOption, SourceChannel, Status, Urgency

STATES = ["Anambra", "Abia", "Ebonyi", "Enugu", "Imo"]

# (name, lat, lon) per state — all 95 LGAs across the 5 South-East states.
LGAS_BY_STATE: dict[str, list[tuple[str, float, float]]] = {
    "Anambra": [
        ("Aguata", 6.0167, 7.0833),
        ("Anambra East", 6.3333, 6.8667),
        ("Anambra West", 6.4167, 6.6833),
        ("Anaocha", 6.15, 7.05),
        ("Awka North", 6.2333, 7.1333),
        ("Awka South", 6.1667, 7.0667),
        ("Ayamelum", 6.6, 6.9667),
        ("Dunukofia", 6.2719, 6.9767),
        ("Ekwusigo", 6.0547, 6.8286),
        ("Idemili North", 6.0971, 6.9847),
        ("Idemili South", 6.1007, 6.8984),
        ("Ihiala", 5.8539, 6.86),
        ("Njikoka", 6.1838, 6.9919),
        ("Nnewi North", 6.0146, 6.921),  # corrected: source had lat==lon
        ("Nnewi South", 5.9384, 6.9218),
        ("Ogbaru", 5.9607, 6.7317),
        ("Onitsha North", 6.1893, 6.8059),
        ("Onitsha South", 6.1358, 6.7885),
        ("Orumba North", 6.0426, 7.2131),
        ("Orumba South", 5.95, 7.2),  # corrected: source had lat==lon
        ("Oyi", 6.23, 6.93),  # corrected: source placed it far south of its neighbors
    ],
    "Abia": [
        ("Aba North", 5.3333, 7.3167),
        ("Aba South", 5.1, 7.35),
        ("Arochukwu", 5.3833, 7.9167),
        ("Bende", 5.5667, 7.6333),
        ("Ikwuano", 5.4333, 7.5667),
        ("Isiala Ngwa North", 5.389, 7.4469),
        ("Isiala Ngwa South", 5.3624, 7.4),
        ("Isuikwuato", 5.5333, 7.4833),
        ("Obi Ngwa", 5.1554, 7.4571),
        ("Ohafia", 5.6167, 7.8333),
        ("Osisioma", 5.1497, 7.3303),
        ("Ugwunagbo", 4.9845, 7.3258),
        ("Ukwa East", 4.8872, 7.3572),
        ("Ukwa West", 4.9884, 7.2425),
        ("Umu Nneochi", 5.9857, 7.469),
        ("Umuahia North", 5.5333, 7.4833),
        ("Umuahia South", 5.5153, 7.4473),
    ],
    "Ebonyi": [
        ("Abakaliki", 6.3333, 8.1),
        ("Afikpo North", 5.8879, 7.9531),
        ("Afikpo South", 5.9667, 7.8667),
        ("Ebonyi", 6.25, 8.0833),
        ("Ezza North", 6.0816, 7.9959),
        ("Ezza South", 6.1778, 8.0404),
        ("Ishielu", 6.4286, 7.8184),
        ("Ivo", 5.9193, 7.5598),
        ("Izzi", 6.3858, 8.0255),
        ("Ohaozara", 6.0302, 7.7141),
        ("Ohaukwu", 6.35, 8.05),  # corrected: source duplicated Ohaozara's coordinates
        ("Onicha", 6.1125, 7.8255),
        ("Ikwo", 6.05, 8.13),  # corrected: source had lat 12.47 (nowhere near Ebonyi)
    ],
    "Enugu": [
        ("Aninri", 6.05, 7.5833),
        ("Awgu", 6.1169, 7.476),
        ("Enugu East", 6.5333, 7.5333),
        ("Enugu North", 6.4667, 7.5167),
        ("Enugu South", 6.4, 7.5),
        ("Ezeagu", 6.75, 7.3333),
        ("Igbo Etiti", 6.6667, 7.3667),
        ("Igbo Eze North", 6.9833, 7.45),
        ("Igbo Eze South", 6.9167, 7.4),
        ("Isi Uzo", 6.7833, 7.7167),
        ("Nkanu East", 6.3333, 7.65),
        ("Nkanu West", 6.3, 7.55),
        ("Nsukka", 6.8567, 7.3958),
        ("Oji River", 6.2667, 7.2667),
        ("Udenu", 6.9167, 7.5167),
        ("Udi", 6.3167, 7.4333),
        ("Uzo-Uwani", 6.75, 7.2),
    ],
    "Imo": [
        ("Aboh Mbaise", 5.45, 7.2333),
        ("Ahiazu Mbaise", 5.547, 7.2703),
        ("Ehime Mbano", 5.6626, 7.3039),
        ("Ezinihitte Mbaise", 5.5051, 7.3677),
        ("Ideato North", 5.8, 7.15),  # corrected: source duplicated Ezinihitte Mbaise's coordinates
        ("Ideato South", 5.85, 7.1),
        ("Ihitte/Uboma", 5.6164, 7.3494),
        ("Ikeduru", 5.5506, 7.0664),
        ("Isiala Mbano", 5.7036, 7.1795),
        ("Isu", 5.6839, 7.0689),
        ("Mbaitoli", 5.5878, 7.05),
        ("Ngor Okpala", 5.4962, 7.0435),
        ("Njaba", 5.7021, 7.0186),
        ("Nkwerre", 5.75, 7.1),
        ("Nwangele", 5.7259, 7.1194),
        ("Obowo", 5.6016, 7.3208),
        ("Oguta", 5.7117, 6.8094),
        ("Ohaji/Egbema", 5.3058, 6.9456),
        ("Okigwe", 5.483, 7.55),
        ("Onuimo", 5.7736, 7.2411),
        ("Orlu", 5.7964, 7.0389),
        ("Orsu", 5.75, 7.05),  # corrected: source duplicated Ihiala's (Anambra) coordinates
        ("Oru East", 5.9833, 6.9833),
        ("Oru West", 5.7358, 6.8833),
        ("Owerri Municipal", 5.485, 7.035),
        ("Owerri North", 5.4567, 7.1028),
        ("Owerri West", 5.4765, 6.9797),
    ],
}


def seed_lgas(session: Session) -> list[LGA]:
    existing = session.exec(select(LGA)).all()
    if existing:
        return list(existing)

    lgas = [
        LGA(name=name, state=state, lat=lat, lon=lon)
        for state, entries in LGAS_BY_STATE.items()
        for name, lat, lon in entries
    ]
    session.add_all(lgas)
    session.commit()
    for lga in lgas:
        session.refresh(lga)
    return lgas


def seed_demo_reports(session: Session, lgas: list[LGA]) -> None:
    existing = session.exec(select(Report)).first()
    if existing:
        return

    by_name = {lga.name: lga for lga in lgas}
    now = datetime.now(timezone.utc)

    # One per state, deliberately, so the default map view shows coverage
    # across the whole region rather than clustering in one spot.
    demo_reports = [
        dict(
            category=Category.CRIME_SAFETY,
            urgency=Urgency.CRITICAL,
            status=Status.PUBLISHED,
            description="Armed robbery reported near Awka South main market around 9pm, residents advised to stay indoors.",
            lga=by_name["Awka South"],
            source_channel=SourceChannel.SMS,
            hours_ago=3,
        ),
        dict(
            category=Category.NEEDS_RESOURCES,
            urgency=Urgency.HIGH,
            status=Status.PUBLISHED,
            description="Community borehole in Nsukka has been broken for 3 days, households relying on distant wells.",
            lga=by_name["Nsukka"],
            source_channel=SourceChannel.SMS,
            hours_ago=30,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.MODERATE,
            status=Status.PUBLISHED,
            description="Pothole widening on the Umuahia North road, motorcycles struggling after rain.",
            lga=by_name["Umuahia North"],
            source_channel=SourceChannel.WEB,
            hours_ago=50,
        ),
        dict(
            category=Category.COMMUNITY_DEV,
            urgency=Urgency.INFORMATIONAL,
            status=Status.PUBLISHED,
            description="New primary school block commissioned in Owerri Municipal, enrollment open for the new term.",
            lga=by_name["Owerri Municipal"],
            source_channel=SourceChannel.WEB,
            hours_ago=100,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.MODERATE,
            status=Status.PENDING,
            description="Frequent power outages reported in Abakaliki over the past week.",
            lga=by_name["Abakaliki"],
            source_channel=SourceChannel.SMS,
            hours_ago=5,
        ),
    ]

    for data in demo_reports:
        lga = data.pop("lga")
        hours_ago = data.pop("hours_ago")
        created_at = now - timedelta(hours=hours_ago)
        report = Report(
            lga_id=lga.id,
            lat=lga.lat,
            lon=lga.lon,
            created_at=created_at,
            published_at=created_at if data["status"] == Status.PUBLISHED else None,
            **data,
        )
        session.add(report)

    session.commit()


# Illustrative only — replace with the org's actual partnerships (an airtime
# aggregator, specific gift card vendors) before any real pilot. Nothing
# here is a real payment integration; redemption fulfillment is manual.
REWARD_CATALOG = [
    {"name": "₦500 Airtime", "points_cost": 500, "description": "MTN, Glo, Airtel, or 9mobile — specify network when redeeming."},
    {"name": "₦1,000 Airtime", "points_cost": 1000, "description": "MTN, Glo, Airtel, or 9mobile — specify network when redeeming."},
    {"name": "₦2,000 Gift Card", "points_cost": 2000, "description": "Placeholder — real vendor (Jumia, Konga, etc.) TBD."},
]


def seed_reward_catalog(session: Session) -> None:
    existing = session.exec(select(RewardOption)).first()
    if existing:
        return
    session.add_all(RewardOption(**data) for data in REWARD_CATALOG)
    session.commit()
