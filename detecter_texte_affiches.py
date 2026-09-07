"""Repere des mots cles (festivals et studios) dans les affiches par OCR.

Les resultats sont copies par categorie et par genre, avec un rapport CSV.

Usage :
    python detecter_texte_affiches.py              # analyse complete de train/
    python detecter_texte_affiches.py --nettoyer   # repasse un OCR sur les
                                                   # dossiers deja produits et
                                                   # supprime les faux positifs
"""

from pathlib import Path
import argparse
import csv
import os
import re
import shutil
import unicodedata

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from rapidocr import RapidOCR


TRAIN_DIR = Path("train")
OUTPUT_DIR = Path("affiches_avec_texte")
REPORT_FILE = Path("affiches_avec_texte.csv")
LABELS_FILE = Path("train_labels.csv")
MIN_SCORE = 0.4
OCR_MAX_SIDE = 1280

CLASS_NAMES = {
    0: "animation",
    1: "blockbuster",
    2: "horreur",
    3: "comedie",
    4: "art_et_essai",
}

REPORT_FIELDS = [
    "filename", "categorie", "genre", "mots_trouves",
    "score_ocr", "texte_ocr", "copied_to",
]

# Motifs appliques au texte compacte (minuscules, sans accent ni espace).
CATEGORY_PATTERNS = {
    "cannes": (r"cannes",),
    # "berling" (et ses variantes) ne doit pas compter comme "berlin".
    "berlin": (r"berlin(?!g)", r"berlinale"),
    "venise": (r"venise", r"venice", r"venezia"),
    "dreamworks": (r"dreamworks?",),
    "pixar": (r"pixar(?!t)",),
}

# Une affiche detectee pour la categorie est rejetee si un de ces motifs
# apparait dans son texte compacte.
CATEGORY_EXCLUSIONS = {
    "cannes": (r"horscompetition", r"outofcompetition"),
}


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def load_labels():
    labels = {}
    with LABELS_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            filename, label = line.split(",", 1)
            labels[filename.strip()] = CLASS_NAMES.get(
                int(label.strip()), f"label_{label.strip()}"
            )
    return labels


def strip_accents(text):
    normalized = unicodedata.normalize("NFD", text)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_text(text):
    text = strip_accents(text).lower()
    return re.sub(r"[^a-z0-9]+", " ", text)


def compact_text(text):
    return re.sub(r"[^a-z]", "", normalize_text(text))


def create_ocr():
    return RapidOCR(
        params={
            "Global.log_level": "error",
            "Global.use_cls": False,
            "Global.max_side_len": OCR_MAX_SIDE,
            "Det.lang_type": "en",
            "Rec.lang_type": "en",
        }
    )


def read_ocr_lines(ocr, image_path):
    result = ocr(str(image_path), use_cls=False, text_score=MIN_SCORE)
    texts = []
    scores = []
    if result is None or getattr(result, "txts", None) is None:
        return texts, scores
    result_scores = result.scores or (0.0,) * len(result.txts)
    for text, score in zip(result.txts, result_scores):
        if not text or not str(text).strip():
            continue
        if score is not None and score < MIN_SCORE:
            continue
        texts.append(str(text).strip())
        scores.append(float(score) if score is not None else 0.0)
    return texts, scores


def excluded_patterns(category, compact):
    return [
        pattern
        for pattern in CATEGORY_EXCLUSIONS.get(category, ())
        if re.search(pattern, compact)
    ]


def matched_patterns(category, compact):
    matches = []
    for pattern in CATEGORY_PATTERNS[category]:
        found = re.search(pattern, compact)
        if found:
            matches.append(found.group(0))
    return matches


def find_categories(texts):
    compact = compact_text(" ".join(texts))
    found = {}
    for category in CATEGORY_PATTERNS:
        if excluded_patterns(category, compact):
            continue
        matches = matched_patterns(category, compact)
        if matches:
            found[category] = matches
    return found


def scan_train_dir(ocr, labels):
    image_paths = sorted(TRAIN_DIR.glob("*.jpg"))
    if not image_paths:
        raise FileNotFoundError(f"Aucune affiche trouvee dans : {TRAIN_DIR}")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for index, image_path in enumerate(image_paths, start=1):
        try:
            texts, scores = read_ocr_lines(ocr, image_path)
        except Exception as error:
            print(f"OCR impossible pour {image_path.name} : {error}")
            continue

        categories = find_categories(texts)
        if categories:
            genre = labels.get(image_path.name, "genre_inconnu")
            joined_text = " | ".join(texts)
            best_score = max(scores) if scores else 0.0
            for category, keywords in categories.items():
                destination = OUTPUT_DIR / safe_name(category) / safe_name(genre)
                destination.mkdir(parents=True, exist_ok=True)
                copied_path = destination / image_path.name
                shutil.copy2(image_path, copied_path)
                rows.append({
                    "filename": image_path.name,
                    "categorie": category,
                    "genre": genre,
                    "mots_trouves": ",".join(keywords),
                    "score_ocr": f"{best_score:.3f}",
                    "texte_ocr": joined_text,
                    "copied_to": str(copied_path),
                })
                print(
                    f"{image_path.name} -> {category} ({genre}, "
                    f"mots={','.join(keywords)})"
                )

        if index % 200 == 0:
            print(f"Progression : {index}/{len(image_paths)} affiches")

    return rows


def clean_output_dir(ocr):
    if not OUTPUT_DIR.exists():
        raise FileNotFoundError(f"Dossier introuvable : {OUTPUT_DIR}")

    removed = []
    kept = 0
    for category_dir in sorted(OUTPUT_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        if category not in CATEGORY_PATTERNS:
            print(f"Categorie inconnue, ignoree : {category}")
            continue

        for image_path in sorted(category_dir.rglob("*.jpg")):
            try:
                texts, _ = read_ocr_lines(ocr, image_path)
            except Exception as error:
                print(f"OCR impossible pour {image_path.name} : {error}")
                continue

            compact = compact_text(" ".join(texts))
            exclusions = excluded_patterns(category, compact)
            matches = matched_patterns(category, compact)
            if exclusions:
                reason = f"exclu ({','.join(exclusions)})"
            elif not matches:
                reason = "mot cle absent"
            else:
                kept += 1
                continue

            image_path.unlink()
            removed.append({
                "filename": image_path.name,
                "categorie": category,
                "raison": reason,
                "chemin": str(image_path),
            })
            print(f"Supprime {image_path} : {reason}")

        for directory in sorted(category_dir.rglob("*"), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()

    return removed, kept


def update_report(removed):
    if not REPORT_FILE.exists() or not removed:
        return
    deleted = {(row["filename"], row["categorie"]) for row in removed}
    with REPORT_FILE.open("r", newline="", encoding="utf-8") as file:
        rows = [
            row
            for row in csv.DictReader(file)
            if (row.get("filename"), row.get("categorie")) not in deleted
        ]
    write_report(rows)


def write_report(rows):
    with REPORT_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows, key):
    counts = {}
    for row in rows:
        counts[row[key]] = counts.get(row[key], 0) + 1
    for value, count in sorted(counts.items()):
        print(f"  {value} : {count}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nettoyer",
        action="store_true",
        help="repasse un OCR sur affiches_avec_texte/ et supprime les faux positifs",
    )
    args = parser.parse_args()

    print("Chargement du moteur OCR...")
    ocr = create_ocr()

    if args.nettoyer:
        removed, kept = clean_output_dir(ocr)
        update_report(removed)
        print(f"Affiches conservees : {kept}")
        print(f"Affiches supprimees : {len(removed)}")
        summarize(removed, "categorie")
        return

    rows = scan_train_dir(ocr, load_labels())
    write_report(rows)
    print(f"Affiches detectees : {len(rows)}")
    summarize(rows, "categorie")
    print(f"Dossier de sortie : {OUTPUT_DIR}")
    print(f"Rapport : {REPORT_FILE}")


if __name__ == "__main__":
    main()
