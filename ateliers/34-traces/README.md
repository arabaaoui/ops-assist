# Atelier 34 — Tracer chaque requête

## Objectif

Vous allez suivre une enquête depuis sa racine jusqu'aux appels de modèle et d'outils.
Le chapitre 35 du cours présente les traces distribuées.
Cet atelier utilise uniquement des incidents fictifs.

## Notions rappelées

Un log décrit un événement à un instant donné.
Une métrique agrège des mesures, par exemple un nombre d'erreurs.
Une trace relie des opérations qui participent à une même demande.
Un span représente une opération, son début, sa fin et ses attributs.
Le span parent relie les opérations à l'enquête.
La durée se lit entre les horodatages de début et de fin.
Le statut d'un outil indique si son résultat a réussi, échoué ou été refusé.
Les tokens disponibles proviennent des métadonnées du modèle.
Une valeur absente signifie que le fournisseur ne l'a pas fournie.

Ne placez pas de question, de log, d'argument ou de réponse dans les spans.
Les exceptions peuvent aussi contenir des données sensibles.
Un identifiant de modèle ou de service reste une métadonnée à protéger.
ADK peut capturer le contenu de messages par défaut dans ses spans historiques.
L'exporteur de cet atelier ne collecte que les spans créés par ops-assist.
Les instrumentations externes ont leur propre configuration et leur propre risque.

## Étapes

### Chemin entièrement hors ligne

1. Exécutez les tests sans serveur, sans modèle et sans export réseau :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest -q tests/test_tracing.py
```

Résultat attendu : les tests passent avec un exporteur de spans en mémoire.
Ils vérifient aussi qu'un secret fictif ne figure pas dans les spans.
Vous pouvez lire le test pour retrouver les noms et les attributs attendus.

### Explorer une trace localement

2. Installez l'extra optionnel puis démarrez Jaeger sur votre poste :

```bash
uv sync --extra otel
docker compose -f docker-compose.otel.yaml up -d
```

Résultat attendu : l'interface répond à `http://127.0.0.1:16686`.
Ces commandes nécessitent respectivement les paquets et l'image en cache ou un accès réseau.

3. Avec un modèle local configuré et démarré, lancez une enquête :

```bash
OPS_ASSIST_OTEL=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
  uv run --extra otel ops-assist investigate "Pourquoi le service est-il lent ?"
```

Résultat attendu : un rapport apparaît dans le terminal.
Sans `OPS_ASSIST_OTEL=1`, aucun exporteur propre à ops-assist n'est créé.
Les observations restent celles du jeu fictif en replay par défaut.

4. Dans Jaeger, choisissez le service `ops-assist`, puis recherchez les traces.
Ouvrez `investigation` et dépliez les spans `model_call` et `tool_call`.
Résultat attendu : chaque outil affiche son nom et son résultat ;
chaque appel de modèle affiche l'agent, le modèle et les tokens disponibles.
Comparez les durées des spans et repérez les opérations les plus longues.

5. Arrêtez le serveur local quand vous avez fini :

```bash
docker compose -f docker-compose.otel.yaml down
```

Résultat attendu : le conteneur est arrêté.

## Exercices

1. Expliquez ce qu'une trace montre qu'un compteur d'erreurs ne montre pas.
2. Dans le test, remplacez la chaîne fictive et vérifiez qu'elle reste absente des spans.
3. Comparez le nombre de spans de modèle au nombre de spans d'outil.
4. Identifiez les métadonnées qui pourraient révéler une information sensible.

## Pour aller plus loin

Comparez le temps de l'enquête à la somme des durées de ses enfants.
Des opérations peuvent se chevaucher : cette somme n'est pas toujours le temps total.
Étudiez les règles de conservation et d'accès avant d'exporter des traces réelles.
