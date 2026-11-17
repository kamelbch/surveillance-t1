
import os
import re
import sys
import smtplib
import requests
from bs4 import BeautifulSoup
from email.message import EmailMessage

RESIDENCES = {
    "Quai de la Loire": {
        "page": "https://logement.smerra.fr/residence-etudiante/fac-habitat-quai-de-la-loire/",
        "reservation": "https://w2.fac-habitat.com/Quai-de-la-Loire/p/4/21/9207/version=iframe_reservation",
    },
    "Adelaide - Bourg-la-Reine": {
        "page": "https://logement.smerra.fr/residence-etudiante/fac-habitat-adelaide/",
        "reservation": "https://w2.fac-habitat.com/Adelaide/p/4/20/15409/version=iframe_reservation/new/",
    },
}

HEADERS = {"User-Agent": "Mozilla/5.0"}
PATTERN_TYPE = re.compile(
    r"\bT1\s*bis\b|\bT1\b|\bT2\b|\bT3\b|\bT4\b",
    re.I,
)
PATTERN_AVAILABLE = re.compile(
    r"\bdisponible(?:s)?\b|\bplaces?\s+disponibles?\b",
    re.I,
)
PATTERN_FULL = re.compile(
    r"\bcomplet(?:e|s|es)?\b|\bindisponible(?:s)?\b",
    re.I,
)


def get_sections(url):
    response = requests.get(
        url, headers=HEADERS, timeout=25
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    text = soup.get_text(" ", strip=True)
    matches = list(PATTERN_TYPE.finditer(text))

    sections = []

    for index, match in enumerate(matches):
        if match.group().replace(" ", "").lower() != "t1":
            continue

        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        section = text[match.end():end][:500]
        sections.append(section)

    return sections, text


def check_residence(name, urls):
    for source in ("reservation", "page"):
        url = urls[source]

        try:
            sections, text = get_sections(url)
        except requests.RequestException as exc:
            print(f"{name} [{source}]: erreur {exc}")
            continue

        print(f"{name} [{source}]: {len(sections)} sections T1")

        if not sections:
            print(f"Diagnostic: {text[:350]}")
            continue

        for section in sections:
            print(f"T1: {section[:200]}")

            available = bool(PATTERN_AVAILABLE.search(section))
            full = bool(PATTERN_FULL.search(section))

            if available and not full:
                return "A_VERIFIER", url

        if any(PATTERN_FULL.search(s) for s in sections):
            return "COMPLET_PROBABLE", url

    return "INCONNU", urls["page"]


def send_email(name, url):
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    recipient = os.environ.get("ALERT_EMAIL")

    if not all((user, password, recipient)):
        print("Email non configure : variables SMTP manquantes")
        return False

    message = EmailMessage()
    message["Subject"] = f"T1 potentiellement disponible - {name}"
    message["From"] = user
    message["To"] = recipient
    message.set_content(
        f"Une disponibilite T1 potentielle a ete detectee.\n"
        f"Residence : {name}\n"
        f"Lien : {url}\n\n"
        "Attention : verifier manuellement avant de conclure "
        "qu'un logement est reservable."
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=25) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)

    return True


def main():
    found = False

    for name, urls in RESIDENCES.items():
        status, url = check_residence(name, urls)
        print(f"RESULTAT {name}: {status}")

        if status == "A_VERIFIER":
            found = True
            if os.environ.get("ENABLE_ALERTS") == "true":
                send_email(name, url)

    if not found:
        print("Aucune disponibilite T1 detectee avec certitude.")

    print("Controle termine.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        sys.exit(1)
