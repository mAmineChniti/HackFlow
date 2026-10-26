import statistics
import time
from types import SimpleNamespace

from django.core.management.base import BaseCommand

from teams import ai

# Mots volontairement absents des données : s'ils apparaissent, l'IA a inventé.
INVENTED_SKILLS = ["java", "kubernetes", "docker", "photoshop", "c++", "angular"]


class Command(BaseCommand):
    help = "Measure real response time of Groq and check text quality."

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=5)

    def handle(self, *args, **options):
        team = SimpleNamespace(name="Alpha Team", hackathon=SimpleNamespace(title="Hack Tunis"))
        analysis = {
            "roles": ["backend", "frontend"],
            "skills": ["python", "react"],
            "missing_roles": ["designer", "data"],
        }
        suggestions = [
            {"username": "alice", "role": "designer", "score": 6,
             "reasons": ["comble le rôle manquant : designer", "apporte : figma"]},
            {"username": "karim", "role": "data", "score": 6,
             "reasons": ["comble le rôle manquant : data", "apporte : ml"]},
        ]
        prompt = ai.build_prompt(team, analysis, suggestions)

        durations, failures, mentions_ok, length_ok, invented = [], 0, 0, 0, 0
        runs = options["runs"]
        for i in range(1, runs + 1):
            start = time.perf_counter()
            try:
                text = ai.generate_text(prompt)
            except ai.AIUnavailable as exc:
                failures += 1
                self.stdout.write(f"run {i}: FAILED ({exc})")
                continue
            elapsed = time.perf_counter() - start
            durations.append(elapsed)
            lowered = text.lower()
            mentions = all(s["username"] in lowered for s in suggestions)
            short = len([line for line in text.splitlines() if line.strip()]) <= 8
            fake = [w for w in INVENTED_SKILLS if w in lowered]
            mentions_ok += mentions
            length_ok += short
            invented += bool(fake)
            self.stdout.write(
                f"run {i}: {elapsed:.2f}s | candidats cités={mentions} | longueur ok={short} | inventé={fake or 'non'}"
            )

        self.stdout.write("-" * 60)
        if durations:
            self.stdout.write(
                f"Groq response time: mean={statistics.mean(durations):.2f}s  "
                f"median={statistics.median(durations):.2f}s  min={min(durations):.2f}s  max={max(durations):.2f}s"
            )
            ok = len(durations)
            self.stdout.write(
                f"Qualité sur {ok} réponses : candidats cités {mentions_ok}/{ok}, "
                f"longueur respectée {length_ok}/{ok}, compétences inventées {invented}/{ok}"
            )
        self.stdout.write(f"Failures: {failures}/{runs}")