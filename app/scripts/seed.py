"""
Seed reference data.
Run: docker compose exec app python -m app.scripts.seed
"""
import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import AsyncSessionLocal
from ..models.reference import (
    Benefit,
    Certification,
    CertificationProvider,
    City,
    CompanySiteType,
    CompanyType,
    Country,
    Experience,
    Function,
    FunctionSpecialty,
    Industry,
    JobStatus,
    JobType,
    OfficeLocation,
    Skill,
    SkillCategory,
    SocialMediaType,
    State,
)
from ..models.user import User


async def upsert(session: AsyncSession, model, unique_field: str, rows: list[dict]):
    """Insert rows that don't already exist (match on unique_field value)."""
    for row in rows:
        key_val = row[unique_field]
        existing = await session.scalar(
            select(model).where(getattr(model, unique_field) == key_val)
        )
        if not existing:
            session.add(model(**row))
    await session.flush()


async def seed(session: AsyncSession):
    print("Seeding countries...")
    await upsert(session, Country, "name", [
        {"name": "United States", "iso_code_2": "US", "iso_code_3": "USA"},
        {"name": "Canada",        "iso_code_2": "CA", "iso_code_3": "CAN"},
    ])

    us = await session.scalar(select(Country).where(Country.name == "United States"))

    print("Seeding states...")
    await upsert(session, State, "name", [
        {"country_id": us.id, "name": "Oklahoma",   "abbreviation": "OK"},
        {"country_id": us.id, "name": "Texas",      "abbreviation": "TX"},
        {"country_id": us.id, "name": "Kansas",     "abbreviation": "KS"},
        {"country_id": us.id, "name": "Missouri",   "abbreviation": "MO"},
        {"country_id": us.id, "name": "Arkansas",   "abbreviation": "AR"},
    ])

    ok = await session.scalar(select(State).where(State.name == "Oklahoma"))

    print("Seeding cities...")
    tulsa_cities = [
        # Served cities — appear in filters
        {"city_name": "Tulsa",         "state_id": ok.id, "is_served": True,  "sort_order": 1},
        {"city_name": "Broken Arrow",  "state_id": ok.id, "is_served": True,  "sort_order": 2},
        {"city_name": "Owasso",        "state_id": ok.id, "is_served": True,  "sort_order": 3},
        {"city_name": "Jenks",         "state_id": ok.id, "is_served": True,  "sort_order": 4},
        {"city_name": "Bixby",         "state_id": ok.id, "is_served": True,  "sort_order": 5},
        {"city_name": "Sand Springs",  "state_id": ok.id, "is_served": True,  "sort_order": 6},
        {"city_name": "Sapulpa",       "state_id": ok.id, "is_served": True,  "sort_order": 7},
        {"city_name": "Claremore",     "state_id": ok.id, "is_served": True,  "sort_order": 8},
        {"city_name": "Catoosa",       "state_id": ok.id, "is_served": True,  "sort_order": 9},
        {"city_name": "Glenpool",      "state_id": ok.id, "is_served": True,  "sort_order": 10},
        {"city_name": "Collinsville",  "state_id": ok.id, "is_served": True,  "sort_order": 11},
        {"city_name": "Skiatook",      "state_id": ok.id, "is_served": True,  "sort_order": 12},
        {"city_name": "Wagoner",       "state_id": ok.id, "is_served": True,  "sort_order": 13},
        {"city_name": "Pryor Creek",   "state_id": ok.id, "is_served": True,  "sort_order": 14},
        # Remote option
        {"city_name": "Remote",        "state_id": None,  "is_served": True,  "sort_order": 99},
    ]
    for c in tulsa_cities:
        existing = await session.scalar(
            select(City).where(City.city_name == c["city_name"])
        )
        if not existing:
            session.add(City(**c))
    await session.flush()

    print("Seeding company types...")
    await upsert(session, CompanyType, "name", [
        {"name": "Private Company"},
        {"name": "Public Company"},
        {"name": "Non-Profit"},
        {"name": "Government / Public Sector"},
        {"name": "Startup"},
        {"name": "Self-Employed / Sole Proprietor"},
        {"name": "Partnership"},
        {"name": "Cooperative"},
        {"name": "Educational Institution"},
        {"name": "Healthcare Organization"},
    ])

    print("Seeding company site types...")
    await upsert(session, CompanySiteType, "name", [
        {"name": "Headquarters"},
        {"name": "Branch Office"},
        {"name": "Remote Office"},
        {"name": "Warehouse"},
        {"name": "Retail Location"},
    ])

    print("Seeding job statuses...")
    await upsert(session, JobStatus, "name", [
        {"name": "active",  "description": "Live and accepting applications"},
        {"name": "closed",  "description": "No longer accepting applications"},
        {"name": "expired", "description": "Past close date or link broken"},
        {"name": "draft",   "description": "Not yet published"},
    ])

    print("Seeding job types...")
    await upsert(session, JobType, "name", [
        {"name": "Full-time"},
        {"name": "Part-time"},
        {"name": "Contract"},
        {"name": "Contract-to-hire"},
        {"name": "Internship"},
        {"name": "Temporary"},
        {"name": "Freelance"},
        {"name": "Volunteer"},
    ])

    print("Seeding office locations...")
    await upsert(session, OfficeLocation, "name", [
        {"name": "On-site"},
        {"name": "Remote"},
        {"name": "Hybrid"},
    ])

    print("Seeding experience levels...")
    experience_levels = [
        "Entry Level",
        "Mid Level",
        "Senior Level",
        "Lead / Principal",
        "Manager",
        "Director",
        "VP / Executive",
        "Internship",
    ]
    for name in experience_levels:
        existing = await session.scalar(select(Experience).where(Experience.name == name))
        if not existing:
            session.add(Experience(name=name))
    await session.flush()

    print("Seeding industries...")
    await upsert(session, Industry, "name", [
        {"name": "Technology / Software",    "sort_order": 1},
        {"name": "Energy / Oil & Gas",       "sort_order": 2},
        {"name": "Healthcare",               "sort_order": 3},
        {"name": "Finance / Banking",        "sort_order": 4},
        {"name": "Manufacturing",            "sort_order": 5},
        {"name": "Education",                "sort_order": 6},
        {"name": "Retail / E-Commerce",      "sort_order": 7},
        {"name": "Construction",             "sort_order": 8},
        {"name": "Transportation / Logistics","sort_order": 9},
        {"name": "Government / Public Sector","sort_order": 10},
        {"name": "Non-Profit",               "sort_order": 11},
        {"name": "Legal",                    "sort_order": 12},
        {"name": "Marketing / Advertising",  "sort_order": 13},
        {"name": "Real Estate",              "sort_order": 14},
        {"name": "Hospitality / Tourism",    "sort_order": 15},
        {"name": "Agriculture",              "sort_order": 16},
        {"name": "Media / Entertainment",    "sort_order": 17},
        {"name": "Insurance",                "sort_order": 18},
        {"name": "Aerospace / Defense",      "sort_order": 19},
        {"name": "Telecommunications",       "sort_order": 20},
    ])

    print("Seeding functions...")
    functions_data = {
        "Engineering / Technology": [
            "Software Development", "DevOps / Platform", "Data Engineering",
            "Data Science / ML", "QA / Testing", "Cybersecurity",
            "Systems / Infrastructure", "Embedded Systems", "Mobile Development",
            "UI / UX Engineering",
        ],
        "Product": [
            "Product Management", "Product Design / UX", "Business Analysis",
        ],
        "Marketing": [
            "Digital Marketing", "Content / SEO", "Brand Management",
            "Growth / Demand Generation", "Marketing Operations",
        ],
        "Sales": [
            "Account Executive", "Business Development", "Sales Engineering",
            "Customer Success", "Sales Operations",
        ],
        "Finance & Accounting": [
            "Accounting", "Financial Analysis", "FP&A", "Audit",
            "Tax", "Payroll",
        ],
        "Human Resources": [
            "Recruiting / Talent Acquisition", "HR Business Partner",
            "Compensation & Benefits", "Learning & Development", "HR Operations",
        ],
        "Operations": [
            "General Operations", "Project Management", "Supply Chain",
            "Logistics", "Manufacturing / Production", "Facilities",
        ],
        "Customer Support": [
            "Technical Support", "Customer Service", "Call Center",
        ],
        "Healthcare": [
            "Nursing", "Physician / PA / NP", "Medical Administration",
            "Allied Health", "Pharmacy", "Behavioral Health",
        ],
        "Legal": [
            "Attorney / Counsel", "Paralegal", "Compliance",
        ],
        "Education": [
            "Teaching / Instruction", "Administration / Advising",
            "Curriculum Development",
        ],
        "Skilled Trades": [
            "Electrical", "Plumbing / HVAC", "Welding / Fabrication",
            "Construction / Carpentry", "Mechanic / Technician",
        ],
        "Executive": [
            "C-Suite", "General Management", "Strategy",
        ],
    }

    for fn_name, specialties in functions_data.items():
        fn = await session.scalar(select(Function).where(Function.name == fn_name))
        if not fn:
            fn = Function(name=fn_name)
            session.add(fn)
            await session.flush()
        for spec in specialties:
            existing_spec = await session.scalar(
                select(FunctionSpecialty).where(
                    FunctionSpecialty.function_id == fn.id,
                    FunctionSpecialty.specialty == spec,
                )
            )
            if not existing_spec:
                session.add(FunctionSpecialty(function_id=fn.id, specialty=spec))
    await session.flush()

    print("Seeding benefits...")
    await upsert(session, Benefit, "name", [
        {"name": "Health Insurance",        "category": "health"},
        {"name": "Dental Insurance",        "category": "health"},
        {"name": "Vision Insurance",        "category": "health"},
        {"name": "401(k)",                  "category": "financial"},
        {"name": "401(k) Match",            "category": "financial"},
        {"name": "Stock Options / Equity",  "category": "financial"},
        {"name": "Paid Time Off",           "category": "time"},
        {"name": "Unlimited PTO",           "category": "time"},
        {"name": "Parental Leave",          "category": "time"},
        {"name": "Flexible Schedule",       "category": "time"},
        {"name": "Remote Work",             "category": "location"},
        {"name": "Relocation Assistance",   "category": "location"},
        {"name": "Tuition Reimbursement",   "category": "development"},
        {"name": "Professional Development Budget", "category": "development"},
        {"name": "Employee Assistance Program",     "category": "wellness"},
        {"name": "Gym / Wellness Stipend",          "category": "wellness"},
        {"name": "Life Insurance",                  "category": "health"},
        {"name": "Short-term Disability",           "category": "health"},
        {"name": "Long-term Disability",            "category": "health"},
        {"name": "Commuter Benefits",               "category": "location"},
    ])

    print("Seeding social media types...")
    await upsert(session, SocialMediaType, "name", [
        {"name": "LinkedIn",   "base_url": "https://linkedin.com/company/"},
        {"name": "Twitter/X",  "base_url": "https://x.com/"},
        {"name": "Facebook",   "base_url": "https://facebook.com/"},
        {"name": "GitHub",     "base_url": "https://github.com/"},
        {"name": "Instagram",  "base_url": "https://instagram.com/"},
        {"name": "YouTube",    "base_url": "https://youtube.com/"},
        {"name": "Website",    "base_url": "https://"},
    ])

    print("Seeding skill categories...")
    skill_categories = [
        {"name": "Programming Languages", "sort_order": 1},
        {"name": "Web Frameworks",        "sort_order": 2},
        {"name": "Databases",             "sort_order": 3},
        {"name": "Cloud Platforms",       "sort_order": 4},
        {"name": "DevOps / Infrastructure","sort_order": 5},
        {"name": "Data & Analytics",      "sort_order": 6},
        {"name": "Mobile Development",    "sort_order": 7},
        {"name": "Security",              "sort_order": 8},
        {"name": "Project Management",    "sort_order": 9},
        {"name": "Design",                "sort_order": 10},
        {"name": "Business Intelligence", "sort_order": 11},
        {"name": "Energy / Industrial",   "sort_order": 12},
        {"name": "Healthcare Technology", "sort_order": 13},
        {"name": "Office / Productivity", "sort_order": 14},
    ]
    for sc in skill_categories:
        existing = await session.scalar(
            select(SkillCategory).where(SkillCategory.name == sc["name"])
        )
        if not existing:
            session.add(SkillCategory(**sc))
    await session.flush()

    cat = {
        sc.name: sc.id
        for sc in (await session.execute(select(SkillCategory))).scalars().all()
    }

    print("Seeding skills...")
    skills_data = [
        # Programming Languages
        ("Python",       "Programming Languages"),
        ("JavaScript",   "Programming Languages"),
        ("TypeScript",   "Programming Languages"),
        ("Java",         "Programming Languages"),
        ("C#",           "Programming Languages"),
        ("C++",          "Programming Languages"),
        ("Go",           "Programming Languages"),
        ("Rust",         "Programming Languages"),
        ("PHP",          "Programming Languages"),
        ("Ruby",         "Programming Languages"),
        ("Swift",        "Programming Languages"),
        ("Kotlin",       "Programming Languages"),
        ("R",            "Programming Languages"),
        ("MATLAB",       "Programming Languages"),
        ("SQL",          "Programming Languages"),
        # Web Frameworks
        ("React",        "Web Frameworks"),
        ("Vue.js",       "Web Frameworks"),
        ("Angular",      "Web Frameworks"),
        ("Next.js",      "Web Frameworks"),
        ("FastAPI",      "Web Frameworks"),
        ("Django",       "Web Frameworks"),
        ("Flask",        "Web Frameworks"),
        ("Node.js",      "Web Frameworks"),
        ("Express.js",   "Web Frameworks"),
        ("Spring Boot",  "Web Frameworks"),
        ("ASP.NET",      "Web Frameworks"),
        ("Laravel",      "Web Frameworks"),
        # Databases
        ("PostgreSQL",   "Databases"),
        ("MySQL",        "Databases"),
        ("MongoDB",      "Databases"),
        ("Redis",        "Databases"),
        ("Elasticsearch","Databases"),
        ("SQLite",       "Databases"),
        ("Oracle",       "Databases"),
        ("SQL Server",   "Databases"),
        ("Cassandra",    "Databases"),
        ("DynamoDB",     "Databases"),
        # Cloud Platforms
        ("AWS",          "Cloud Platforms"),
        ("Azure",        "Cloud Platforms"),
        ("Google Cloud", "Cloud Platforms"),
        # DevOps
        ("Docker",       "DevOps / Infrastructure"),
        ("Kubernetes",   "DevOps / Infrastructure"),
        ("Terraform",    "DevOps / Infrastructure"),
        ("GitHub Actions","DevOps / Infrastructure"),
        ("Jenkins",      "DevOps / Infrastructure"),
        ("Ansible",      "DevOps / Infrastructure"),
        ("Linux",        "DevOps / Infrastructure"),
        ("Git",          "DevOps / Infrastructure"),
        # Data & Analytics
        ("Pandas",       "Data & Analytics"),
        ("NumPy",        "Data & Analytics"),
        ("Apache Spark", "Data & Analytics"),
        ("Tableau",      "Data & Analytics"),
        ("Power BI",     "Data & Analytics"),
        ("dbt",          "Data & Analytics"),
        ("Airflow",      "Data & Analytics"),
        # Mobile
        ("React Native", "Mobile Development"),
        ("Flutter",      "Mobile Development"),
        ("iOS Development","Mobile Development"),
        ("Android Development","Mobile Development"),
        # Security
        ("Penetration Testing","Security"),
        ("SIEM",         "Security"),
        ("Splunk",       "Security"),
        ("Network Security","Security"),
        # Project Management
        ("Agile / Scrum","Project Management"),
        ("Jira",         "Project Management"),
        ("PMP",          "Project Management"),
        ("Kanban",       "Project Management"),
        # Design
        ("Figma",        "Design"),
        ("Adobe XD",     "Design"),
        ("Sketch",       "Design"),
        # Business Intelligence
        ("Looker",       "Business Intelligence"),
        ("Salesforce",   "Business Intelligence"),
        ("SAP",          "Business Intelligence"),
        # Energy / Industrial
        ("SCADA",        "Energy / Industrial"),
        ("AutoCAD",      "Energy / Industrial"),
        ("PLC Programming","Energy / Industrial"),
        # Healthcare Technology
        ("Epic",         "Healthcare Technology"),
        ("Cerner",       "Healthcare Technology"),
        ("HL7 / FHIR",   "Healthcare Technology"),
        # Office / Productivity
        ("Microsoft Office","Office / Productivity"),
        ("Google Workspace","Office / Productivity"),
        ("Excel / VBA",  "Office / Productivity"),
    ]
    for skill_name, cat_name in skills_data:
        existing = await session.scalar(select(Skill).where(Skill.name == skill_name))
        if not existing:
            session.add(Skill(name=skill_name, skill_category_id=cat.get(cat_name), is_active=True))
    await session.flush()

    print("Seeding certification providers...")
    await upsert(session, CertificationProvider, "name", [
        {"name": "Amazon Web Services (AWS)",   "website": "https://aws.amazon.com/certification/"},
        {"name": "Google Cloud",                "website": "https://cloud.google.com/certification"},
        {"name": "Microsoft",                   "website": "https://learn.microsoft.com/certifications"},
        {"name": "CompTIA",                     "website": "https://www.comptia.org/certifications"},
        {"name": "PMI",                         "website": "https://www.pmi.org/certifications"},
        {"name": "Scrum Alliance",              "website": "https://www.scrumalliance.org"},
        {"name": "Cisco",                       "website": "https://www.cisco.com/c/en/us/training-events/training-certifications.html"},
        {"name": "ISACA",                       "website": "https://www.isaca.org/credentialing"},
        {"name": "ISC2",                        "website": "https://www.isc2.org/certifications"},
        {"name": "Linux Foundation",            "website": "https://training.linuxfoundation.org"},
        {"name": "Salesforce",                  "website": "https://trailhead.salesforce.com/credentials"},
        {"name": "Meta (Facebook)",             "website": "https://www.facebook.com/business/learn"},
        {"name": "HubSpot Academy",             "website": "https://academy.hubspot.com"},
    ])

    aws_prov = await session.scalar(
        select(CertificationProvider).where(CertificationProvider.name == "Amazon Web Services (AWS)")
    )
    gc_prov = await session.scalar(
        select(CertificationProvider).where(CertificationProvider.name == "Google Cloud")
    )
    ms_prov = await session.scalar(
        select(CertificationProvider).where(CertificationProvider.name == "Microsoft")
    )
    comptia_prov = await session.scalar(
        select(CertificationProvider).where(CertificationProvider.name == "CompTIA")
    )
    pmi_prov = await session.scalar(
        select(CertificationProvider).where(CertificationProvider.name == "PMI")
    )
    isc2_prov = await session.scalar(
        select(CertificationProvider).where(CertificationProvider.name == "ISC2")
    )

    print("Seeding certifications...")
    certs_data = [
        {"name": "AWS Certified Solutions Architect – Associate", "code": "SAA-C03", "provider_id": aws_prov.id, "category": "Cloud", "level": "Associate"},
        {"name": "AWS Certified Developer – Associate",           "code": "DVA-C02", "provider_id": aws_prov.id, "category": "Cloud", "level": "Associate"},
        {"name": "AWS Certified DevOps Engineer – Professional",  "code": "DOP-C02", "provider_id": aws_prov.id, "category": "Cloud", "level": "Professional"},
        {"name": "Google Cloud Professional Cloud Architect",     "code": "PCA",     "provider_id": gc_prov.id,  "category": "Cloud", "level": "Professional"},
        {"name": "Google Cloud Professional Data Engineer",       "code": "PDE",     "provider_id": gc_prov.id,  "category": "Data",  "level": "Professional"},
        {"name": "Microsoft Azure Fundamentals",                  "code": "AZ-900",  "provider_id": ms_prov.id,  "category": "Cloud", "level": "Fundamentals"},
        {"name": "Microsoft Azure Administrator",                 "code": "AZ-104",  "provider_id": ms_prov.id,  "category": "Cloud", "level": "Associate"},
        {"name": "CompTIA Security+",                             "code": "SY0-701", "provider_id": comptia_prov.id, "category": "Security", "level": "Foundation"},
        {"name": "CompTIA A+",                                    "code": "220-1101","provider_id": comptia_prov.id, "category": "IT Support", "level": "Foundation"},
        {"name": "Project Management Professional (PMP)",         "code": "PMP",     "provider_id": pmi_prov.id, "category": "Project Management", "level": "Professional"},
        {"name": "Certified Information Systems Security Professional (CISSP)", "code": "CISSP", "provider_id": isc2_prov.id, "category": "Security", "level": "Professional"},
    ]
    for cert in certs_data:
        existing = await session.scalar(select(Certification).where(Certification.name == cert["name"]))
        if not existing:
            session.add(Certification(**cert))
    await session.flush()

    # -----------------------------------------------------------------------
    # Seed admin user (if ADMIN_EMAIL is set and no admin exists yet)
    # -----------------------------------------------------------------------
    if settings.ADMIN_EMAIL:
        existing_admin = await session.scalar(
            select(User).where(User.email == settings.ADMIN_EMAIL)
        )
        if not existing_admin:
            print(f"Creating admin user: {settings.ADMIN_EMAIL}")
            admin = User(
                email=settings.ADMIN_EMAIL,
                full_name="Site Admin",
                oauth_provider="seed",
                oauth_subject=settings.ADMIN_EMAIL,
                is_admin=True,
                is_active=True,
            )
            session.add(admin)
            await session.flush()
            print(
                f"  Admin user created. Sign in will work once you configure an OAuth provider "
                f"and that provider returns {settings.ADMIN_EMAIL} as the email."
            )

    await session.commit()


async def main():
    print("=== TulsaJobSpot Seed ===")
    async with AsyncSessionLocal() as session:
        await seed(session)
    print("=== Seed complete ===")


if __name__ == "__main__":
    asyncio.run(main())
