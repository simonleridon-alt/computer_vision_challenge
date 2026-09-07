"""Copie les affiches de train/ dans un dossier par genre d'apres train_labels.csv.

Usage :
    python separer_affiches_par_genre.py            # copie les images
    python separer_affiches_par_genre.py --deplacer # deplace au lieu de copier
"""

from pathlib import Path
import argparse
import shutil


TRAIN_DIR = Path("train")
OUTPUT_DIR = Path("train_par_genre")
LABELS_FILE = Path("train_labels.csv")

CLASS_NAMES = {
    0: "animation",
    1: "blockbuster",
    2: "horreur",
    3: "comedie",
    4: "art_et_essai",
}


def load_labels():
    labels = {}
    with LABELS_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            filename, label = line.split(",", 1)
            filename = filename.strip()
            label = label.strip()
            if filename.lower() == "filename" or not label.isdigit():
                continue
            labels[filename] = CLASS_NAMES.get(int(label), f"label_{label}")
    return labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deplacer",
        action="store_true",
        help="deplace les fichiers au lieu de les copier",
    )
    args = parser.parse_args()

    labels = load_labels()
    if not TRAIN_DIR.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {TRAIN_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    counts = {}
    sans_label = []

    for image_path in sorted(TRAIN_DIR.iterdir()):
        if not image_path.is_file() or image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        genre = labels.get(image_path.name)
        if genre is None:
            sans_label.append(image_path.name)
            genre = "sans_label"
        destination = OUTPUT_DIR / genre
        destination.mkdir(parents=True, exist_ok=True)
        if args.deplacer:
            shutil.move(str(image_path), destination / image_path.name)
        else:
            shutil.copy2(image_path, destination / image_path.name)
        counts[genre] = counts.get(genre, 0) + 1

    total = sum(counts.values())
    print(f"Affiches traitees : {total}")
    for genre, count in sorted(counts.items()):
        print(f"  {genre} : {count}")
    if sans_label:
        print(f"Sans label dans {LABELS_FILE} : {len(sans_label)}")
    print(f"Dossier de sortie : {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
