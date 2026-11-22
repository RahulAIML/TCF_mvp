"""Large combinatorial topic material so prompts are not drawn from a list of eight or thirty-six.

Each theme is assembled from independent facets (domain, setting, angle, place). Recently used
themes are passed in by the caller and skipped. The space is large enough that a learner does not
cycle through the same situation by exhaustion of a short list.
"""
from __future__ import annotations

import random
from typing import Iterable, Sequence

PLACES = [
    "Montréal", "Québec", "Ottawa", "Gatineau", "Sherbrooke", "Trois-Rivières", "Moncton",
    "Winnipeg", "Toronto", "Vancouver", "Halifax", "Laval", "Longueuil", "Saguenay", "Lévis",
    "Calgary", "Edmonton", "Victoria", "Regina", "Whitehorse", "Lyon", "Bordeaux", "Lille",
    "Nantes", "Toulouse", "Marseille", "Strasbourg", "Rennes", "Bruxelles", "Genève", "Lausanne",
    "Dakar", "Abidjan", "Tunis", "Rabat",
]

DOMAINS = [
    "le logement et la colocation", "les transports du quotidien", "le travail à distance",
    "le bénévolat", "l'alimentation", "les réseaux sociaux", "l'apprentissage des langues",
    "le sport amateur", "les vacances en famille", "la vie de quartier", "les bibliothèques",
    "le recyclage", "les fêtes locales", "l'accueil des nouveaux arrivants", "la santé au travail",
    "les études à l'âge adulte", "le commerce de proximité", "les animaux de compagnie",
    "l'hiver et les déplacements", "les parcs", "la sécurité routière", "le cinéma",
    "les jeux vidéo", "la consommation d'énergie", "le tourisme local", "la lecture",
    "les horaires de travail", "le covoiturage", "les jardins communautaires", "la musique",
    "les objets de seconde main", "le téléphone à l'école", "les cours du soir", "la cuisine",
    "un déménagement", "la garde d'enfants", "le budget familial", "le voisinage",
    "les services municipaux", "l'accès aux soins", "le bilinguisme au travail",
    "les espaces de coworking", "la réparation plutôt que le remplacement",
]

SETTINGS = [
    "dans un quartier résidentiel", "au centre-ville", "dans une petite ville",
    "sur un campus", "dans une entreprise", "dans une association", "à la maison",
    "dans un service public", "pendant un hiver rigoureux", "au bord d'un fleuve",
    "dans un immeuble à logements", "lors d'un festival local", "dans une école",
    "dans une clinique de quartier", "sur le trajet domicile-travail",
]

ANGLES = [
    "un désaccord entre deux personnes", "un changement récent", "un choix à justifier",
    "une contrainte de budget", "un souvenir précis", "une proposition à défendre",
    "un problème pratique à résoudre", "une habitude à expliquer", "un projet à organiser",
    "deux solutions à comparer",
]

_ROLE_PLACES = [
    "un centre sportif municipal", "une régie de logement", "un refuge pour animaux",
    "une bibliothèque de quartier", "un office de tourisme", "une clinique sans rendez-vous",
    "une école de langues", "un atelier de réparation de vélos", "une coopérative alimentaire",
    "un théâtre communautaire", "un marché public", "une maison de la culture",
    "un service d'accueil des nouveaux arrivants", "une librairie indépendante",
    "un parc national", "un musée régional", "une station de radio locale",
    "un café-emploi", "une caisse populaire", "un centre de compostage",
]

_ROLE_PARTNERS = [
    "l'employé à l'accueil", "la responsable des inscriptions", "le propriétaire",
    "une bénévole", "le conseiller", "la bibliothécaire", "l'agente municipale",
    "le technicien", "la coordonnatrice", "un collègue qui organise l'activité",
]

_OPINION_QUESTIONS = [
    "Faut-il {action} ?",
    "Est-il souhaitable de {action} ?",
    "{topic} : pour ou contre ?",
    "Dans quelle mesure faut-il {action} ?",
]

_OPINION_ACTIONS = [
    "rendre les transports en commun gratuits le week-end",
    "limiter les voitures dans le centre-ville",
    "enseigner une deuxième langue dès l'école primaire",
    "interdire le téléphone en classe",
    "généraliser la semaine de quatre jours",
    "taxer davantage les logements laissés vides",
    "financer le sport amateur par la ville",
    "réduire l'éclairage public après minuit",
    "obliger les commerces à accepter la réparation",
    "ouvrir les bibliothèques le dimanche",
    "créer plus de rues piétonnes en hiver",
    "limiter la publicité destinée aux enfants",
    "favoriser le télétravail deux jours par semaine",
    "installer des composteurs dans chaque immeuble",
    "réserver des logements aux étudiants près du campus",
    "subventionner les cours de français pour les adultes",
    "fermer certaines rues lors des journées de marché",
    "encourager le covoiturage entre collègues",
    "réduire les emballages dans les épiceries",
    "proposer des horaires de travail plus souples aux parents",
]


def _fresh(candidates: Sequence[str], avoid: Iterable[str], count: int) -> list[str]:
    blocked = {item.strip().lower() for item in avoid if item and item.strip()}
    pool = [item for item in candidates if item.strip().lower() not in blocked]
    if len(pool) < count:
        pool = list(candidates)
    if len(pool) <= count:
        return list(pool)
    return random.sample(pool, count)


def writing_theme_catalog(limit: int = 240) -> list[str]:
    catalog: list[str] = []
    for domain in DOMAINS:
        for setting in SETTINGS:
            catalog.append(f"{domain}, {setting}")
            if len(catalog) >= limit:
                return catalog
    return catalog


def pick_writing_themes(count: int, avoid: Iterable[str] = ()) -> list[str]:
    catalog = []
    for domain in DOMAINS:
        for angle in ANGLES:
            catalog.append(f"{domain} : {angle}")
    return _fresh(catalog, avoid, count)


def speaking_topic(task_type: str, avoid: Iterable[str] = ()) -> str:
    blocked = {item.strip().lower() for item in avoid if item and item.strip()}
    for _ in range(12):
        if task_type == "role_play":
            place = random.choice(_ROLE_PLACES)
            partner = random.choice(_ROLE_PARTNERS)
            city = random.choice(PLACES[:20])
            topic = (
                f"À {city}, vous êtes dans {place}. L'examinateur joue {partner} : "
                "posez des questions précises pour obtenir les informations dont vous avez besoin."
            )
        elif task_type == "basic_interaction":
            domain = random.choice(DOMAINS)
            city = random.choice(PLACES)
            topic = f"Parler de soi à propos de {domain}, en prenant appui sur la vie à {city}."
        else:
            action = random.choice(_OPINION_ACTIONS)
            pattern = random.choice(_OPINION_QUESTIONS)
            topic = pattern.format(action=action, topic=action)
        if topic.strip().lower() not in blocked:
            return topic
    return topic + f" ({random.randint(1000, 9999)})"


# Large enough that a run of twenty sessions does not keep drawing the same examiner.
EXAMINERS = [
    ("Marie Dupont", "examinatrice"), ("Sophie Martin", "examinatrice"), ("Claire Lefebvre", "examinatrice"),
    ("Isabelle Moreau", "examinatrice"), ("Nathalie Petit", "examinatrice"), ("Camille Bernard", "examinatrice"),
    ("Léa Rousseau", "examinatrice"), ("Chloé Garnier", "examinatrice"), ("Émilie Caron", "examinatrice"),
    ("Audrey Pelletier", "examinatrice"), ("Julie Gagnon", "examinatrice"), ("Sarah Tremblay", "examinatrice"),
    ("Amélie Bouchard", "examinatrice"), ("Valérie Côté", "examinatrice"), ("Noémie Lavoie", "examinatrice"),
    ("Catherine Roy", "examinatrice"), ("Sandrine Gauthier", "examinatrice"), ("Mélanie Fortin", "examinatrice"),
    ("Geneviève Bergeron", "examinatrice"), ("Caroline Beaulieu", "examinatrice"), ("Élise Marchand", "examinatrice"),
    ("Jean-Pierre Bernard", "examinateur"), ("Thomas Rousseau", "examinateur"), ("Michel Laurent", "examinateur"),
    ("Nicolas Gagnon", "examinateur"), ("Antoine Lefebvre", "examinateur"), ("Olivier Caron", "examinateur"),
    ("Sébastien Moreau", "examinateur"), ("François Pelletier", "examinateur"), ("Marc Tremblay", "examinateur"),
    ("Luc Bouchard", "examinateur"), ("Simon Côté", "examinateur"), ("David Lavoie", "examinateur"),
    ("Éric Roy", "examinateur"), ("Julien Gauthier", "examinateur"), ("Mathieu Fortin", "examinateur"),
    ("Gabriel Bergeron", "examinateur"), ("Paul Beaulieu", "examinateur"), ("Maxime Marchand", "examinateur"),
    ("Samuel Dupont", "examinateur"), ("Alexandre Martin", "examinateur"),
]


def pick_examiner(avoid: Iterable[str] = ()) -> tuple[str, str]:
    blocked = {name.strip().lower() for name in avoid if name}
    choices = [pair for pair in EXAMINERS if pair[0].lower() not in blocked]
    if not choices:
        choices = list(EXAMINERS)
    return random.choice(choices)


def place() -> str:
    return random.choice(PLACES)


def domain() -> str:
    return random.choice(DOMAINS)
