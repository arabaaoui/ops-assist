# ops-assist

Un **agent d'enquête sur incident** open source, construit avec [Google ADK](https://github.com/google/adk-python).
Demandez-lui *« pourquoi l'API de paiement est-elle lente depuis 9 h ? »* : il rassemble des preuves,
puis répond par un rapport typé qui sépare les **faits** (avec leur source), les **hypothèses** (avec
un degré de confiance et les faits sur lesquels elles reposent) et ce qu'il **ne sait pas**.

**État : étape 0.** L'agent lit les alertes et doit répondre par un `IncidentReport` valide ;
métriques, journaux et changements existent déjà dans la couche d'observation et deviennent des
outils aux étapes suivantes.

C'est le projet fil rouge d'un cours vidéo en français sur l'ingénierie des agents d'IA : chaque
chapitre lui ajoute une capacité. English version: [README.md](README.md).

## Principes

- **Lecture seule par défaut.** Une seule action d'écriture (le retour arrière d'un déploiement)
  arrive plus tard, et ne s'exécute qu'après confirmation humaine, sur le rejeu ou la pile de
  démonstration, jamais sur un environnement réel.
- **Agnostique du fournisseur.** Les modèles passent par LiteLLM ; le fournisseur est une
  configuration, avec une chaîne de repli ordonnée (`FallbackModel` d'ADK, expérimental) : le
  modèle suivant est essayé sur HTTP 429, 500, 502, 503 ou 504 avant toute sortie, jamais sur une
  requête mal formée, une erreur de connexion ou un modèle renommé.
- **Hors ligne.** Par défaut, l'agent enquête sur un incident *rejoué*, enregistré sur disque : ni
  infrastructure, ni compte. Toutes les données sont fictives.
- **Testé sans modèle.** La CI fait tourner la boucle de l'agent sur un modèle scripté : ni clé, ni coût.

## Démarrer

```bash
uv sync
uv run pytest -q                       # tout tourne hors ligne
cp .env.example .env                   # puis choisir un profil
uv run adk web apps                    # interface de développement ADK sur http://localhost:8000
```

Deux profils de modèle, dans `src/ops_assist/data/profiles.yaml` (autre fichier : `OPS_ASSIST_PROFILES_FILE`) :

| Profil | Prérequis | Réglage |
|---|---|---|
| `local` (par défaut) | [Ollama](https://ollama.com) et un modèle qui sait appeler des outils | `OPS_ASSIST_PROFILE=local` |
| `api` | une clé d'API d'un fournisseur avec offre gratuite | `OPS_ASSIST_PROFILE=api` et la clé du fournisseur |

Les identifiants de modèle sont des exemples : remplacez-les par `OPS_ASSIST_MODELS="fournisseur/modele,fournisseur/secours"`.
Les modèles surchargés n'héritent pas de l'adresse du profil ; posez `OPS_ASSIST_API_BASE` s'il leur
en faut une. Des incidents enregistrés peuvent vivre hors du paquet avec `OPS_ASSIST_INCIDENTS_DIR`.

## Licence

[Apache 2.0](LICENSE).
