"""
Génération de rapports et exports de données — HackFlow ESPRIT.

Comprend :
- L'export Excel (.xlsx) complet des partenariats filtrés avec openpyxl.
- Feuille détaillée "Partenariats" et feuille analytique "Résumé".
- Protection contre l'injection de formules (Formula Injection / CSV Injection).
- Limitation de sécurité (max 5000 lignes).
"""

from decimal import Decimal
import io
from typing import Any
from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from sponsors.models import ContributionTypeChoices, Sponsorship, StatusChoices, TierChoices

MAX_EXPORT_ROWS = 5000


def sanitize_excel_cell(val: Any) -> Any:
    """
    Convertit la valeur en type standard (évite les proxy gettext_lazy de Django).
    Pour les chaînes textuelles, conserve la chaîne sans apostrophe visible.
    La neutralisation contre l'injection de formules est assurée par le forçage
    du type texte explicite (cell.data_type = "s").
    """
    if val is None:
        return ""
    if isinstance(val, (int, float, Decimal, bool)):
        return val
    return str(val)


def is_formula_injection_risk(val: Any) -> bool:
    """Vérifie si la valeur textuelle commence par un caractère déclencheur de formule (=, +, -, @)."""
    if val is None or isinstance(val, (int, float, Decimal, bool)):
        return False
    str_val = str(val)
    return bool(str_val and str_val[0] in ("=", "+", "-", "@"))


def export_sponsorships_to_excel(queryset: QuerySet[Sponsorship]) -> io.BytesIO:
    """
    Génère un classeur Excel structuré avec deux feuilles :
    1. 'Partenariats' : Liste des conventions avec montants formatés (3 décimales).
    2. 'Résumé' : Tableaux récapitulatifs (totaux financiers, répartition statut & tier).

    Lève ValueError si le volume dépasse MAX_EXPORT_ROWS (5000 lignes).
    Lève RuntimeError si la bibliothèque openpyxl n'est pas installée.
    """
    if not OPENPYXL_AVAILABLE:
        raise RuntimeError("La bibliothèque 'openpyxl' n'est pas installée sur le serveur.")

    total_count = queryset.count()
    if total_count > MAX_EXPORT_ROWS:
        raise ValueError(f"L'export est limité à {MAX_EXPORT_ROWS} lignes maximum ({total_count} lignes demandées).")

    wb = openpyxl.Workbook()

    # Styles réutilisables
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")  # Slate-800
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    section_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")  # Slate-100
    section_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    bold_font = Font(name="Calibri", size=11, bold=True)
    regular_font = Font(name="Calibri", size=11)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    right_align = Alignment(horizontal="right", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # -------------------------------------------------------------------------
    # FEUILLE 1 : PARTENARIATS
    # -------------------------------------------------------------------------
    ws_data = wb.active
    ws_data.title = "Partenariats"
    ws_data.views.sheetView[0].showGridLines = True

    headers = [
        "Sponsor",
        "Secteur",
        "Hackathon",
        "Niveau (Tier)",
        "Montant (DT)",
        "Type de contribution",
        "Statut",
        "Dernière mise à jour",
    ]

    ws_data.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws_data.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    sponsorships = (
        queryset.select_related("sponsor", "hackathon")
        .order_by("-updated_at", "-created_at")
    )

    for row_idx, sp in enumerate(sponsorships, start=2):
        row_values = [
            sp.sponsor.name,
            sp.sponsor.get_sector_display(),
            sp.hackathon.name,
            sp.get_tier_display(),
            float(sp.amount),
            sp.get_contribution_type_display(),
            sp.get_status_display(),
            sp.updated_at.strftime("%d/%m/%Y %H:%M") if sp.updated_at else "",
        ]

        # Formatage et affectation des cellules
        for col_idx, raw_val in enumerate(row_values, start=1):
            cell = ws_data.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border

            # Alignements et types spécifiques
            if col_idx == 5:  # Montant en DT
                cell.value = raw_val
                cell.number_format = "#,##0.000"
                cell.alignment = right_align
            else:
                str_val = sanitize_excel_cell(raw_val)
                cell.value = str_val
                # Forçage du type texte explicite ("s") pour neutraliser toute formule
                if is_formula_injection_risk(raw_val):
                    cell.data_type = "s"

                if col_idx in (2, 4, 6, 7, 8):
                    cell.alignment = center_align
                else:
                    cell.alignment = left_align

    # Ajustement automatique de la largeur des colonnes
    for col in ws_data.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_data.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # -------------------------------------------------------------------------
    # FEUILLE 2 : RÉSUMÉ & ANALYTIQUE
    # -------------------------------------------------------------------------
    ws_summary = wb.create_sheet(title="Résumé")
    ws_summary.views.sheetView[0].showGridLines = True

    # Titre du résumé
    ws_summary.cell(row=1, column=1, value="Synthèse Financière et Opérationnelle des Partenariats").font = Font(name="Calibri", size=14, bold=True, color="0F172A")
    ws_summary.cell(row=2, column=1, value=f"Généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')} — HackFlow ESPRIT").font = Font(name="Calibri", size=10, italic=True, color="64748B")

    # Calcul des totaux clés
    confirmed_qs = queryset.filter(status=StatusChoices.CONFIRME)
    total_confirmed = confirmed_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0.000")
    count_confirmed = confirmed_qs.count()

    in_progress_qs = queryset.filter(status__in=[StatusChoices.PROSPECT, StatusChoices.CONTACTE, StatusChoices.NEGOCIATION])
    total_in_progress = in_progress_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0.000")
    count_in_progress = in_progress_qs.count()

    # Bloc KPIs généraux
    ws_summary.cell(row=4, column=1, value="Indicateur Clé").font = section_font
    ws_summary.cell(row=4, column=2, value="Nombre").font = section_font
    ws_summary.cell(row=4, column=3, value="Montant Total (DT)").font = section_font
    for c in range(1, 4):
        ws_summary.cell(row=4, column=c).fill = section_fill
        ws_summary.cell(row=4, column=c).border = thin_border

    kpi_rows = [
        ("Partenariats Confirmés (Sécurisés)", count_confirmed, float(total_confirmed)),
        ("Partenariats en Négociation / Cours", count_in_progress, float(total_in_progress)),
        ("Total Sélection Active", total_count, float(total_confirmed + total_in_progress)),
    ]

    for offset, (label, count_val, amt_val) in enumerate(kpi_rows, start=5):
        ws_summary.cell(row=offset, column=1, value=label).font = regular_font
        ws_summary.cell(row=offset, column=2, value=count_val).alignment = center_align
        amt_cell = ws_summary.cell(row=offset, column=3, value=amt_val)
        amt_cell.number_format = "#,##0.000"
        amt_cell.alignment = right_align
        for c in range(1, 4):
            ws_summary.cell(row=offset, column=c).border = thin_border

    # Table Répartition par statut
    start_row_status = 10
    ws_summary.cell(row=start_row_status, column=1, value="Répartition par Statut").font = Font(name="Calibri", size=12, bold=True)
    ws_summary.cell(row=start_row_status + 1, column=1, value="Statut").font = header_font
    ws_summary.cell(row=start_row_status + 1, column=2, value="Nombre").font = header_font
    ws_summary.cell(row=start_row_status + 1, column=3, value="Montant Total (DT)").font = header_font
    for c in range(1, 4):
        ws_summary.cell(row=start_row_status + 1, column=c).fill = header_fill
        ws_summary.cell(row=start_row_status + 1, column=c).alignment = center_align

    current_r = start_row_status + 2
    for code, label in StatusChoices.choices:
        qs_stat = queryset.filter(status=code)
        st_count = qs_stat.count()
        st_sum = qs_stat.aggregate(s=Sum("amount"))["s"] or Decimal("0.000")

        ws_summary.cell(row=current_r, column=1, value=sanitize_excel_cell(label)).font = regular_font
        ws_summary.cell(row=current_r, column=2, value=st_count).alignment = center_align
        cell_amt = ws_summary.cell(row=current_r, column=3, value=float(st_sum))
        cell_amt.number_format = "#,##0.000"
        cell_amt.alignment = right_align
        for c in range(1, 4):
            ws_summary.cell(row=current_r, column=c).border = thin_border
        current_r += 1

    # Table Répartition par niveau (Tier)
    start_row_tier = current_r + 2
    ws_summary.cell(row=start_row_tier, column=1, value="Répartition par Niveau (Tier)").font = Font(name="Calibri", size=12, bold=True)
    ws_summary.cell(row=start_row_tier + 1, column=1, value="Niveau").font = header_font
    ws_summary.cell(row=start_row_tier + 1, column=2, value="Nombre").font = header_font
    ws_summary.cell(row=start_row_tier + 1, column=3, value="Montant Total (DT)").font = header_font
    for c in range(1, 4):
        ws_summary.cell(row=start_row_tier + 1, column=c).fill = header_fill
        ws_summary.cell(row=start_row_tier + 1, column=c).alignment = center_align

    current_r = start_row_tier + 2
    for code, label in TierChoices.choices:
        qs_tier = queryset.filter(tier=code)
        tr_count = qs_tier.count()
        tr_sum = qs_tier.aggregate(s=Sum("amount"))["s"] or Decimal("0.000")

        ws_summary.cell(row=current_r, column=1, value=sanitize_excel_cell(label)).font = regular_font
        ws_summary.cell(row=current_r, column=2, value=tr_count).alignment = center_align
        cell_amt = ws_summary.cell(row=current_r, column=3, value=float(tr_sum))
        cell_amt.number_format = "#,##0.000"
        cell_amt.alignment = right_align
        for c in range(1, 4):
            ws_summary.cell(row=current_r, column=c).border = thin_border
        current_r += 1

    # Ajustement largeur résumé
    for col in ws_summary.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_summary.column_dimensions[col_letter].width = max(max_len + 4, 18)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
