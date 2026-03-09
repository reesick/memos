"""
demo/generate_test_data.py – Seed MemoryOS with realistic test facts

Generates ~1000+ facts across multiple entities (people, projects, tech stacks,
companies) by POSTing to the running MemoryOS API. Useful for testing search
quality, graph traversal, and deduplication at scale.

Usage:
    python demo/generate_test_data.py [--api http://localhost:8000] [--count 50]
"""

import argparse
import random
import time
import json
import sys
try:
    import httpx
except ImportError:
    print("httpx not found. pip install httpx")
    sys.exit(1)

API_DEFAULT = "http://localhost:8000"

# ── Synthetic conversations / docs that will be fed to /memory/add ──────────

PEOPLE = ["Arjun", "Priya", "Sam", "Leila", "Dev", "Mia", "Rayan", "Zoe"]
ROLES  = ["backend engineer", "frontend engineer", "ML researcher", "DevOps lead",
          "product manager", "data scientist", "CTO", "iOS developer"]
TECHS  = ["React", "FastAPI", "PyTorch", "Kubernetes", "PostgreSQL", "Redis",
          "TypeScript", "Rust", "Go", "Swift", "GraphQL", "dbt"]
COMPANIES = ["Acme Corp", "DeepThink AI", "BuildFast", "StackedIO", "NexaLabs"]
PROJECTS  = ["MemoryOS", "ProjectAlpha", "DataPipeline", "AuthService", "MobileApp"]
LANGS  = ["Python", "TypeScript", "Go", "Rust", "Swift", "Kotlin"]
SCHOOLS = ["IIT Bombay", "Stanford", "MIT", "NUS", "CMU", "UCL"]
CITIES  = ["Bangalore", "San Francisco", "London", "Singapore", "Berlin", "Toronto"]

TEMPLATES = [
    "{name} is a {role} at {company}.",
    "{name} specializes in {tech} and {tech2}.",
    "{name} studied computer science at {school}.",
    "{name} is currently working on {project}.",
    "{name} prefers {lang} for backend development.",
    "{name} is based in {city}.",
    "{name} has 5 years of experience with {tech}.",
    "{name} leads the {project} team at {company}.",
    "{name} uses {tech} daily and considers it their strongest skill.",
    "{name} recently moved from {city} to {city2}.",
    "The {project} project uses {lang} and {tech}.",
    "{project} is built by the team at {company}.",
    "{company} is hiring senior {role}s.",
    "{company} was founded in {year}.",
    "{name} joined {company} in {year}.",
    "{name} is an expert in {tech} and mentors junior developers.",
    "{name} graduated from {school} in {year}.",
    "{name}'s favorite programming language is {lang}.",
]


def fill(template: str) -> str:
    """Fill a template with random realistic values."""
    return template.format(
        name=random.choice(PEOPLE),
        role=random.choice(ROLES),
        company=random.choice(COMPANIES),
        tech=random.choice(TECHS),
        tech2=random.choice(TECHS),
        project=random.choice(PROJECTS),
        lang=random.choice(LANGS),
        school=random.choice(SCHOOLS),
        city=random.choice(CITIES),
        city2=random.choice(CITIES),
        year=random.randint(2015, 2024),
    )


def generate_facts(count: int) -> list:
    """Generate `count` unique text snippets."""
    facts = set()
    while len(facts) < count:
        tpl = random.choice(TEMPLATES)
        facts.add(fill(tpl))
    return list(facts)


def main():
    parser = argparse.ArgumentParser(description="Seed MemoryOS with test data")
    parser.add_argument("--api", default=API_DEFAULT, help="API base URL")
    parser.add_argument("--count", type=int, default=50, help="Number of text snippets to add")
    args = parser.parse_args()

    print(f"🌱  Seeding MemoryOS at {args.api} with {args.count} snippets…")

    texts = generate_facts(args.count)
    added = 0
    failed = 0
    total_facts = 0

    with httpx.Client(base_url=args.api, timeout=60) as client:
        # Verify API is up
        try:
            r = client.get("/health")
            r.raise_for_status()
        except Exception as e:
            print(f"❌  API not reachable at {args.api}: {e}")
            sys.exit(1)

        for i, text in enumerate(texts, 1):
            try:
                r = client.post("/memory/add", json={
                    "content": text,
                    "source_type": "text",
                    "session_id": "seed_session",
                })
                r.raise_for_status()
                d = r.json()
                total_facts += d.get("facts_added", 0)
                added += 1
                if i % 10 == 0:
                    print(f"  [{i}/{args.count}] {total_facts} facts stored so far…")
            except Exception as e:
                failed += 1
                print(f"  ⚠  Snippet {i} failed: {e}")

    print(f"\n✅  Done. {added}/{args.count} snippets added → {total_facts} facts stored.")
    if failed:
        print(f"   {failed} snippets failed (usually dedup NOOP or LLM extraction skip).")
    return total_facts


if __name__ == "__main__":
    total = main()
    sys.exit(0 if total >= 0 else 1)
