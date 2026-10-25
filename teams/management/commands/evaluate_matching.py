from django.core.management.base import BaseCommand

from teams import services

# Scénarios annotés à la main : "relevant" = candidats qu'un humain jugerait complémentaires.
SCENARIOS = [
    {
        "name": "Équipe backend seule",
        "team_roles": {"backend"},
        "team_skills": {"python", "django"},
        "candidates": {
            "ali": ("designer", "figma, ui"),
            "sara": ("frontend", "react, css"),
            "omar": ("backend", "python, django"),
            "lina": ("data", "python, pandas"),
            "youssef": ("other", ""),
            "nour": ("backend", "java, spring"),
        },
        "relevant": {"ali", "sara", "lina"},
    },
    {
        "name": "Backend + frontend (cas difficile)",
        "team_roles": {"backend", "frontend"},
        "team_skills": {"python", "react"},
        "candidates": {
            "ali": ("designer", "figma"),
            "lina": ("data", "python, ml"),
            "omar": ("backend", "go, docker, kubernetes"),
            "youssef": ("other", "figma, ui, sketch"),
            "sara": ("frontend", "react"),
        },
        "relevant": {"ali", "lina", "youssef"},
    },
    {
        "name": "Designer seul",
        "team_roles": {"designer"},
        "team_skills": {"figma"},
        "candidates": {
            "karim": ("backend", "django, postgres"),
            "mariem": ("frontend", "react"),
            "sami": ("designer", "figma, illustrator"),
            "hela": ("data", "python"),
        },
        "relevant": {"karim", "mariem", "hela"},
    },
    {
        "name": "Il manque seulement la data",
        "team_roles": {"backend", "frontend", "designer"},
        "team_skills": {"python", "react", "figma"},
        "candidates": {
            "lina": ("data", "python, pandas, ml"),
            "omar": ("backend", "python"),
            "sara": ("frontend", "react"),
            "amel": ("data", "sql"),
            "zied": ("other", "sql, excel"),
        },
        "relevant": {"lina", "amel"},
    },
    {
        "name": "Peu de candidats",
        "team_roles": {"backend"},
        "team_skills": {"python"},
        "candidates": {"ali": ("frontend", "react"), "ben": ("backend", "python")},
        "relevant": {"ali"},
    },
    {
        "name": "Équipe data seule",
        "team_roles": {"data"},
        "team_skills": {"python", "ml"},
        "candidates": {
            "a1": ("backend", "django"),
            "a2": ("frontend", "react, css"),
            "a3": ("designer", "figma"),
            "a4": ("data", "python, ml, sklearn"),
        },
        "relevant": {"a1", "a2", "a3"},
    },
]


def rank(scenario, limit=3):
    missing = [r for r in services.CORE_ROLES if r not in scenario["team_roles"]]
    scored = []
    for name, (role, skills) in scenario["candidates"].items():
        score, _ = services.score_candidate(
            role=role,
            skills=services.parse_skills(skills),
            missing_roles=missing,
            team_skills=set(scenario["team_skills"]),
        )
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, name in scored[:limit]]


def evaluate():
    rows = []
    for scenario in SCENARIOS:
        suggested = rank(scenario)
        relevant = scenario["relevant"]
        tp = len(set(suggested) & relevant)
        precision = tp / len(suggested) if suggested else 0.0
        recall = tp / len(relevant) if relevant else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        baseline = len(relevant) / len(scenario["candidates"])  # choix au hasard
        rows.append(
            {
                "name": scenario["name"],
                "suggested": suggested,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "baseline": baseline,
            }
        )
    n = len(rows)
    return {
        "rows": rows,
        "precision": sum(r["precision"] for r in rows) / n,
        "recall": sum(r["recall"] for r in rows) / n,
        "f1": sum(r["f1"] for r in rows) / n,
        "baseline": sum(r["baseline"] for r in rows) / n,
    }


class Command(BaseCommand):
    help = "Évalue le matching (Precision@3, Recall@3, F1) sur des scénarios annotés."

    def handle(self, *args, **options):
        result = evaluate()
        self.stdout.write("Scénario".ljust(38) + "P@3    R@3    F1     Hasard")
        for r in result["rows"]:
            self.stdout.write(
                r["name"].ljust(38)
                + f"{r['precision']:.2f}   {r['recall']:.2f}   {r['f1']:.2f}   {r['baseline']:.2f}"
                + "   -> " + ", ".join(r["suggested"])
            )
        self.stdout.write("-" * 70)
        self.stdout.write(
            f"MOYENNE: Precision@3={result['precision']:.2f}  Recall@3={result['recall']:.2f}  "
            f"F1={result['f1']:.2f}  | Précision d'un choix au hasard={result['baseline']:.2f}"
        )