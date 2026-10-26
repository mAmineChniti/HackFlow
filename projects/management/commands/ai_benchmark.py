"""Print the reproducible AI evaluation metrics used by the rubric demo."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from projects.ai_benchmark import (
    evaluate_category_classifier,
    evaluate_generative_quality,
)


class Command(BaseCommand):
    help = (
        "Run the AI benchmarks: category precision/recall/F1, confusion "
        "matrix, generative rubric checks and latency."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON instead of tables.",
        )
        parser.add_argument(
            "--remote",
            action="store_true",
            help=(
                "Use the configured Groq model instead of the local fallback. "
                "This sends network calls and may incur API cost or rate limits."
            ),
        )

    def handle(self, *args, **options):
        use_remote = options["remote"]
        classification = evaluate_category_classifier(use_remote=use_remote)
        generative = evaluate_generative_quality(use_remote=use_remote)

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {"classification": classification, "generative": generative},
                    indent=2,
                )
            )
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "Category detection — labelled validation set "
                f"({classification['sample_count']} examples)"
            )
        )
        self.stdout.write(f"Source: {classification['benchmark_source']}")
        self.stdout.write(
            f"Accuracy: {classification['accuracy_percent']:.1f}% "
            f"({classification['correct_count']}/{classification['sample_count']})"
        )
        self.stdout.write(
            f"Macro precision: {classification['macro_precision']:.3f} | "
            f"macro recall: {classification['macro_recall']:.3f} | "
            f"macro F1: {classification['macro_f1']:.3f}"
        )
        self.stdout.write(
            f"Latency p50/p95: {classification['latency_p50_ms']:.2f} ms / "
            f"{classification['latency_p95_ms']:.2f} ms"
        )
        self.stdout.write("")
        self.stdout.write("Per class:")
        self.stdout.write(
            f"{'category':10} {'support':>7} {'precision':>9} {'recall':>7} {'f1':>7}"
        )
        for item in classification["per_class"]:
            self.stdout.write(
                f"{item['code']:10} {item['support']:>7} "
                f"{item['precision']:>9.3f} {item['recall']:>7.3f} {item['f1']:>7.3f}"
            )
        self.stdout.write("")
        self.stdout.write("Confusion matrix (rows = actual, columns = predicted):")
        labels = [item["code"] for item in classification["labels"]]
        self.stdout.write(" " * 10 + " ".join(f"{label:>7}" for label in labels))
        for row in classification["confusion_matrix"]:
            self.stdout.write(
                f"{row['code']:10} " + " ".join(f"{cell['count']:>7}" for cell in row["cells"])
            )
        if classification["errors"]:
            self.stdout.write("")
            self.stdout.write("Misclassified examples:")
            for error in classification["errors"]:
                self.stdout.write(
                    f"- {error['title']}: expected {error['expected']}, "
                    f"got {error['predicted']} ({error['confidence']} confidence)"
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "Generative review — qualitative rubric and structural checks "
                f"({generative['sample_count']} examples)"
            )
        )
        self.stdout.write(f"Source: {generative['benchmark_source']}")
        self.stdout.write(
            f"Schema completeness: {generative['completeness_percent']:.1f}% | "
            f"valid score range: {generative['score_range_percent']:.1f}% | "
            f"deterministic: {generative['consistency_percent']:.1f}%"
        )
        self.stdout.write(
            f"Latency p50/p95: {generative['latency_p50_ms']:.2f} ms / "
            f"{generative['latency_p95_ms']:.2f} ms | "
            f"average score: {generative['average_score']}/10"
        )
        for criterion in generative["criteria"]:
            self.stdout.write(f"- {criterion['criterion']}: {criterion['question']}")
