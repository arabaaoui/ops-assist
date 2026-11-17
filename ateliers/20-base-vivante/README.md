# Atelier 20 — Une base de connaissances vivante

## Objectif

Vous transformez un rapport d'incident fictif en postmortem relu, puis indexé.
Vous vérifiez sa provenance et sa fraîcheur sans appeler de modèle.
Cet atelier conclut le module 3.

## Notions rappelées

Un rapport sépare faits, hypothèses et inconnues.
Un postmortem conserve ce qui permettra de mieux traiter un prochain incident.
La provenance relie le document à une session et au SHA-256 du rapport validé.
Le hachage porte sur le JSON canonique du rapport, avant expurgation.
Il permet de comparer une version, sans prouver que son contenu est vrai.
La date `updated` indique l'âge du document, pas la véracité de son contenu.
Un brouillon ne devient cherchable qu’après une décision humaine.
L'expurgation des secrets est heuristique : utilisez des données fictives.

## Étapes hors ligne

1. Créez un rapport fictif et choisissez un répertoire d'état temporaire :

```sh
export OPS_ASSIST_STATE_DIR="$(mktemp -d)"
cat > "$OPS_ASSIST_STATE_DIR/report.json" <<'JSON'
{"summary":"Latency increased.","status":"insufficient_data","facts":[],"hypotheses":[],"unknowns":["Cause unknown"]}
JSON
uv run ops-assist validate "$OPS_ASSIST_STATE_DIR/report.json"
```

Résultat attendu : `OK`.

2. Générez le brouillon avec le rapport local :

```sh
uv run ops-assist knowledge draft-postmortem --report "$OPS_ASSIST_STATE_DIR/report.json"
ls "$OPS_ASSIST_STATE_DIR/knowledge/drafts"
```

Résultat attendu : un fichier `postmortem-….md` portant `status: draft`.
Lisez-le et complétez le service, les faits et les actions avec des données fictives.
Le corps porte un hachage : après modification, relisez-le puis utilisez `--accept-edits`.
Après une enquête CLI, `knowledge draft-postmortem --session ID` utilise son rapport validé ; sans option, la commande prend le dernier rapport.

3. Construisez l'index et vérifiez que le brouillon n'y apparaît pas :

```sh
uv run ops-assist knowledge index
uv run ops-assist knowledge search "Latency increased"
```

Résultat attendu : aucun identifiant du brouillon dans les résultats.
Le hachage d'embeddings par défaut fonctionne sans réseau.

4. Relisez le fichier, puis validez son identifiant dans un terminal :

```sh
uv run ops-assist knowledge approve postmortem-REMPLACER --accept-edits
```

Saisissez `yes`, puis votre nom ; le nom du compte est proposé par défaut.
Résultat attendu : chemin dans `knowledge/approved`, avec identité, date et mode de validation.
L'index est mis à jour ; la recherche affiche maintenant le document, sa date et `stale`.
Un humain doit décider de la validation ; une option explicite existe pour l’automatisation.
Hors terminal, elle exige `OPS_ASSIST_ALLOW_NONINTERACTIVE_APPROVAL=1`, `--yes` et `--approver NOM`.
Ce mode est enregistré avec `approval: noninteractive` ; en terminal, `--yes` exige aussi `--approver NOM`.

5. Consultez les documents anciens :

```sh
OPS_ASSIST_KNOWLEDGE_MAX_AGE_DAYS=90 uv run ops-assist knowledge stale
```

Résultat attendu : les identifiants dont la date dépasse 90 jours, s'il y en a.

## Exercices

1. Modifiez le corps d’un brouillon ; observez le refus sans `--accept-edits`, puis expliquez les hachages.
2. Refusez la confirmation ; vérifiez que le fichier reste dans `drafts` et absent de l'index.
3. Essayez deux seuils de fraîcheur et comparez les résultats.
4. Ajoutez un faux mot de passe au rapport, puis vérifiez son expurgation dans le brouillon.

## Pour aller plus loin

Après chaque incident, relisez la provenance, attribuez un responsable et vérifiez les faits avant d'alimenter la base.
Versionnez les documents approuvés avec votre méthode habituelle : une nouvelle version doit conserver son historique et une date revue.
Les fichiers de rapports locaux peuvent contenir des données non expurgées ; protégez-les et utilisez des données fictives.

## Bilan du module 3

Vous avez parcouru embeddings, recherche hybride, graphe et recherche agentique.
Une base utile reste un ensemble de sources datées, vérifiées et entretenues par des humains.
