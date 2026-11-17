

import re
import sys
import requests
from bs4 import BeautifulSoup, Tag

RESIDENCES = {
    "Quai de la Loire": (
        "https://w2.fac-habitat.com/"
        "Quai-de-la-Loire/p/4/21/9207/"
        "version=iframe_reservation"
    ),
    "Adelaide - Bourg-la-Reine": (
        "https://w2.fac-habitat.com/"
        "Adelaide/p/4/20/15409/"
        "version=iframe_reservation/new/"
    ),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

TYPE_RE = re.compile(
    r"(?<!\w)T1(?!\s*bis|\w)", re.I
)

ANY_TYPE_RE = re.compile(
    r"\bT1\s*bis\b|\bT1\b|\bT2\b|\bT3\b|\bT4\b",
    re.I
)

BUTTON_RE = re.compile(
    r"Déposer\s+une\s+demande", re.I
)

DISABLED_RE = re.compile(
    r"disabled|inactive|unavailable|"
    r"indisponible|grayed|greyed|"
    r"non-disponible",
    re.I
)


def normaliser(texte):
    return " ".join(texte.split())


def statut_logement(texte):
    debut = normaliser(texte)[:150].lower()

    if re.search(
        r"\bdisponible\b|\bdispo immédiate\b",
        debut
    ):
        return "DISPONIBLE"

    if re.search(
        r"\bà venir\b|\ba venir\b|"
        r"\bdispo à venir\b",
        debut
    ):
        return "A_VENIR"

    if re.search(r"\bcomplet\b", debut):
        return "COMPLET"

    return "INCONNU"


def bouton_desactive(element):
    """
    Cherche des indices HTML indiquant
    qu'un bouton est désactivé.
    """
    if element.has_attr("disabled"):
        return True

    if element.get("aria-disabled", "").lower() == "true":
        return True

    if element.get("inert") is not None:
        return True

    classes = " ".join(element.get("class", []))

    if DISABLED_RE.search(classes):
        return True

    style = element.get("style", "").lower()

    if "pointer-events:none" in style.replace(" ", ""):
        return True

    return False


def inspecter_bouton(element):
    """
    Retourne ACTIF_PROBABLE, DESACTIVE
    ou INCONNU.
    """
    if bouton_desactive(element):
        return "DESACTIVE"

    parents = list(element.parents)[:3]

    for parent in parents:
        if not isinstance(parent, Tag):
            continue

        if bouton_desactive(parent):
            return "DESACTIVE"

    if element.name in ("button", "a", "input"):
        return "ACTIF_PROBABLE"

    if element.get("role") == "button":
        return "ACTIF_PROBABLE"

    return "INCONNU"


def trouver_cartes(soup):
    """
    Repère les cartes contenant un type T1.
    Exclut les cartes T1 bis.
    """
    cartes = []
    vus = set()

    for element in soup.find_all(
        ["div", "article", "li", "section"]
    ):
        texte = normaliser(
            element.get_text(" ", strip=True)
        )

        if not TYPE_RE.search(texte):
            continue

        if not BUTTON_RE.search(texte):
            continue

        types = list(ANY_TYPE_RE.finditer(texte))

        if len(types) != 1:
            continue

        if types[0].group().strip().lower() != "t1":
            continue

        if len(texte) > 1000:
            continue

        # Conserver uniquement le conteneur
        # le plus précis.
        enfants_valides = False

        for enfant in element.find_all(
            ["div", "article", "li", "section"],
            recursive=False
        ):
            t = normaliser(
                enfant.get_text(" ", strip=True)
            )

            if (
                TYPE_RE.search(t)
                and BUTTON_RE.search(t)
                and len(t) < len(texte)
            ):
                enfants_valides = True
                break

        if enfants_valides:
            continue

        if id(element) not in vus:
            cartes.append(element)
            vus.add(id(element))

    return cartes


def trouver_bouton(carte):
    candidats = []

    for element in carte.find_all(True):
        if element.name not in (
            "button", "a", "input", "div", "span"
        ):
            continue

        texte = normaliser(
            element.get_text(" ", strip=True)
        )

        if element.name == "input":
            texte = element.get("value", texte)

        if BUTTON_RE.fullmatch(texte):
            candidats.append(element)

    # Préférer le véritable élément interactif.
    for element in candidats:
        if (
            element.name in ("button", "a", "input")
            or element.get("role") == "button"
        ):
            return element

    if candidats:
        return candidats[-1]

    return None


def analyser_residence(nom, url):
    print(f"\n=== {nom} ===")
    print(f"URL: {url}")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text, "html.parser"
    )

    for element in soup(
        ["script", "style", "noscript"]
    ):
        element.decompose()

    cartes = trouver_cartes(soup)

    print(f"Cartes T1 identifiées: {len(cartes)}")

    if not cartes:
        print("DIAGNOSTIC: aucune carte T1 isolée.")
        print(
            "Extrait HTML:",
            str(soup)[:1500]
        )
        return "INCONNU"

    alertes = []
    incertitudes = 0

    for index, carte in enumerate(cartes, 1):
        texte = normaliser(
            carte.get_text(" ", strip=True)
        )

        statut = statut_logement(texte)
        bouton = trouver_bouton(carte)

        if bouton is None:
            etat = "INCONNU"
        else:
            etat = inspecter_bouton(bouton)

        print(f"\nT1 #{index}")
        print(f"Statut: {statut}")
        print(f"Bouton: {etat}")
        print(f"Texte: {texte[:300]}")

        if bouton is not None:
            print(
                "HTML bouton:",
                str(bouton)[:700]
            )

        if etat == "ACTIF_PROBABLE":
            alertes.append({
                "numero": index,
                "statut": statut,
                "texte": texte[:200]
            })

        elif etat == "INCONNU":
            incertitudes += 1

    if alertes:
        print("\n*** DEMANDE POTENTIELLEMENT ACCESSIBLE ***")

        for alerte in alertes:
            print(
                f"T1 #{alerte['numero']} - "
                f"{alerte['statut']}"
            )

        print("Lien:", url)

        return "DEMANDE_POTENTIELLE"

    if incertitudes:
        return "INCONNU"

    return "AUCUN_BOUTON_ACTIF"


def main():
    erreurs = 0

    for nom, url in RESIDENCES.items():
        try:
            resultat = analyser_residence(
                nom, url
            )

            print(
                f"\nRESULTAT {nom}: {resultat}"
            )

            if resultat == "INCONNU":
                erreurs += 1

        except Exception as exc:
            erreurs += 1
            print(
                f"ERREUR {nom}: {exc}",
                file=sys.stderr
            )

    print("\n=== FIN DE LA SURVEILLANCE ===")

    if erreurs:
        print(
            "Attention: certaines vérifications "
            "nécessitent un diagnostic."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
