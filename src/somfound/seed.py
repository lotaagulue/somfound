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
    """Idempotent per-entry (checked by description, which is distinctive
    synthetic text anyway) rather than gated on the whole table being empty —
    that used to mean a single pre-existing report (real or manual) would
    silently skip seeding *all* demo content forever. Per-entry checking also
    means expanding this list later only inserts what's actually missing,
    safe to run again against a DB that already has some of these — which is
    exactly how the live production DB was backfilled with the expanded set
    below, with no real migration needed."""
    by_name = {lga.name: lga for lga in lgas}
    now = datetime.now(timezone.utc)
    existing_descriptions = set(session.exec(select(Report.description)).all())

    # Several per state, deliberately spread across *different* LGAs within
    # each state (never two reports sharing one LGA's centroid) — after
    # #55/#56 fixed the map silently stacking same-coordinate markers on top
    # of each other, seed data shouldn't turn around and reintroduce exactly
    # that problem. Mix of category/urgency/status/source_channel/
    # confirmations so a first-time visitor sees the app's actual range
    # (moderation queue with something in it, a couple of resolved reports
    # showing the full lifecycle, some peer-confirmed) rather than a wall of
    # identical-looking published pins.
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
        # --- Anambra ---
        dict(
            category=Category.CRIME_SAFETY,
            urgency=Urgency.HIGH,
            status=Status.PUBLISHED,
            description="Reports of phone snatching along the Upper Iweka axis in Onitsha North, two incidents this week.",
            lga=by_name["Onitsha North"],
            source_channel=SourceChannel.WEB,
            hours_ago=6,
            confirmations_count=3,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.MODERATE,
            status=Status.PUBLISHED,
            description="Streetlights along the Nnewi North-Uruagu road have been out for two weeks, dark stretch at night.",
            lga=by_name["Nnewi North"],
            source_channel=SourceChannel.SMS,
            hours_ago=40,
        ),
        dict(
            category=Category.NEEDS_RESOURCES,
            urgency=Urgency.HIGH,
            status=Status.PUBLISHED,
            description="General hospital in Idemili North reporting shortage of malaria drugs and IV fluids.",
            lga=by_name["Idemili North"],
            source_channel=SourceChannel.WEB,
            hours_ago=18,
            confirmations_count=5,
        ),
        dict(
            category=Category.COMMUNITY_DEV,
            urgency=Urgency.INFORMATIONAL,
            status=Status.PUBLISHED,
            description="New ICT center commissioned at Ihiala community secondary school, computer classes starting next month.",
            lga=by_name["Ihiala"],
            source_channel=SourceChannel.WEB,
            hours_ago=95,
        ),
        # --- Abia ---
        dict(
            category=Category.CRIME_SAFETY,
            urgency=Urgency.CRITICAL,
            status=Status.PUBLISHED,
            description="Armed men attempted to break into a shop along Ogbor Hill in Aba North last night, vigilante group responded.",
            lga=by_name["Aba North"],
            source_channel=SourceChannel.SMS,
            hours_ago=4,
            confirmations_count=7,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.HIGH,
            status=Status.PUBLISHED,
            description="Bridge along the Ohafia-Arochukwu road showing cracks after last week's heavy rain, motorists advised caution.",
            lga=by_name["Ohafia"],
            source_channel=SourceChannel.WEB,
            hours_ago=50,
        ),
        dict(
            category=Category.NEEDS_RESOURCES,
            urgency=Urgency.MODERATE,
            status=Status.PENDING,
            description="Borehole at the Isiala Ngwa North community square has been dry for a week.",
            lga=by_name["Isiala Ngwa North"],
            source_channel=SourceChannel.SMS,
            hours_ago=10,
        ),
        dict(
            category=Category.COMMUNITY_DEV,
            urgency=Urgency.INFORMATIONAL,
            status=Status.PUBLISHED,
            description="Arochukwu youth association organized a free health screening this weekend, over 200 residents attended.",
            lga=by_name["Arochukwu"],
            source_channel=SourceChannel.WEB,
            hours_ago=120,
            confirmations_count=2,
        ),
        # --- Ebonyi ---
        dict(
            category=Category.CRIME_SAFETY,
            urgency=Urgency.HIGH,
            status=Status.PUBLISHED,
            description="Suspicious persons spotted around Afikpo North motor park at night, residents asked to be vigilant.",
            lga=by_name["Afikpo North"],
            source_channel=SourceChannel.SMS,
            hours_ago=25,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.MODERATE,
            status=Status.PUBLISHED,
            description="Culvert along the Ikwo-Abakaliki road has collapsed, causing flooding on the road during rain.",
            lga=by_name["Ikwo"],
            source_channel=SourceChannel.WEB,
            hours_ago=60,
        ),
        dict(
            category=Category.NEEDS_RESOURCES,
            urgency=Urgency.HIGH,
            status=Status.PUBLISHED,
            description="Flooding has displaced several families in Ohaozara, temporary shelter urgently needed.",
            lga=by_name["Ohaozara"],
            source_channel=SourceChannel.SMS,
            hours_ago=14,
            confirmations_count=4,
        ),
        dict(
            category=Category.COMMUNITY_DEV,
            urgency=Urgency.INFORMATIONAL,
            status=Status.RESOLVED,
            description="Ezza North primary health center renovation completed, now fully equipped for maternal care.",
            lga=by_name["Ezza North"],
            source_channel=SourceChannel.WEB,
            hours_ago=150,
            resolved_hours_ago=20,
        ),
        # --- Enugu ---
        dict(
            category=Category.CRIME_SAFETY,
            urgency=Urgency.MODERATE,
            status=Status.PUBLISHED,
            description="Reports of a cult-related clash near Abakpa Nike in Enugu East, situation reportedly calm now.",
            lga=by_name["Enugu East"],
            source_channel=SourceChannel.WEB,
            hours_ago=33,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.CRITICAL,
            status=Status.PUBLISHED,
            description="Major landslide has blocked the Udi-Awgu road, no vehicle movement possible currently.",
            lga=by_name["Udi"],
            source_channel=SourceChannel.SMS,
            hours_ago=8,
            confirmations_count=6,
        ),
        dict(
            category=Category.NEEDS_RESOURCES,
            urgency=Urgency.MODERATE,
            status=Status.PUBLISHED,
            description="Community requesting additional water tanks in Nkanu East as the dry season worsens the water shortage.",
            lga=by_name["Nkanu East"],
            source_channel=SourceChannel.WEB,
            hours_ago=70,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.INFORMATIONAL,
            status=Status.RESOLVED,
            description="Oji River bridge repairs have been completed, road reopened to traffic.",
            lga=by_name["Oji River"],
            source_channel=SourceChannel.SMS,
            hours_ago=160,
            resolved_hours_ago=12,
        ),
        # --- Imo ---
        dict(
            category=Category.CRIME_SAFETY,
            urgency=Urgency.HIGH,
            status=Status.PUBLISHED,
            description="Kidnapping attempt reported along the Orlu-Owerri expressway, police alerted.",
            lga=by_name["Orlu"],
            source_channel=SourceChannel.SMS,
            hours_ago=12,
            confirmations_count=8,
        ),
        dict(
            category=Category.INFRASTRUCTURE,
            urgency=Urgency.MODERATE,
            status=Status.PUBLISHED,
            description="Federal road through Okigwe town has multiple potholes causing regular traffic delays.",
            lga=by_name["Okigwe"],
            source_channel=SourceChannel.WEB,
            hours_ago=45,
        ),
        dict(
            category=Category.NEEDS_RESOURCES,
            urgency=Urgency.HIGH,
            status=Status.PENDING,
            description="Mbaitoli community clinic reporting shortage of vaccines for routine immunization.",
            lga=by_name["Mbaitoli"],
            source_channel=SourceChannel.SMS,
            hours_ago=16,
        ),
        dict(
            category=Category.COMMUNITY_DEV,
            urgency=Urgency.INFORMATIONAL,
            status=Status.PUBLISHED,
            description="Ngor Okpala women's cooperative launches new skills-acquisition program for local youth.",
            lga=by_name["Ngor Okpala"],
            source_channel=SourceChannel.WEB,
            hours_ago=110,
            confirmations_count=1,
        ),
    ]

    for data in demo_reports:
        if data["description"] in existing_descriptions:
            continue
        lga = data.pop("lga")
        hours_ago = data.pop("hours_ago")
        resolved_hours_ago = data.pop("resolved_hours_ago", None)
        created_at = now - timedelta(hours=hours_ago)
        published_at = created_at if data["status"] in (Status.PUBLISHED, Status.RESOLVED) else None
        resolved_at = now - timedelta(hours=resolved_hours_ago) if data["status"] == Status.RESOLVED else None
        report = Report(
            lga_id=lga.id,
            lat=lga.lat,
            lon=lga.lon,
            created_at=created_at,
            published_at=published_at,
            resolved_at=resolved_at,
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
