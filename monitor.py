
import re
import sys
import requests
from bs4 import BeautifulSoup

RESIDENCES = {
    "Quai de la Loire":
        "https://logement.smerra.fr/residence-etudiante/fac-habitat-quai-de-la-loire/",
    "Adelaide - Bourg-la-Reine":
        "https://logement.smerra.fr/residence-etudiante/fac-habitat-adelaide/",
}

def verifier(nom, url):
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    texte = soup.get_text(" ", strip=True)

    categories = list(re.finditer(
        r"\bT1\s*bis\b|\bT1\b|\bT2\b",
        texte,
        re.IGNORECASE
    ))

    for i, match in enumerate(categories):
        if match.group().strip().lower() != "t1":
            continue

        fin = (
            categories[i + 1].start()
            if i + 1 < len(categories)
            else len(texte)
        )
        section = texte[match.end():fin]

        if re.search(r"\bComplet\b", section, re.I):
            return "COMPLET"

        if re.search(
            r"\bDisponible\b|\bRéserver\b",
            section,
            re.I
        ):
            return "DISPONIBLE_A_VERIFIER"

    return "INCONNU"

def main():
    erreurs = 0

    for nom, url in RESIDENCES.items():
        try:
            statut = verifier(nom, url)
            print(f"{nom}: {statut}")

            if statut == "DISPONIBLE_A_VERIFIER":
                print(f"ALERTE POTENTIELLE: {url}")

            if statut == "INCONNU":
                erreurs += 1

        except Exception as exc:
            erreurs += 1
            print(f"ERREUR {nom}: {exc}", file=sys.stderr)

    if erreurs:
        sys.exit(1)

if __name__ == "__main__":
    main()
