# Atelier 41 — De bout en bout

## Objectif

Vous allez relier le rejeu d'un incident fictif à une enquête et à sa restitution.
Cet atelier clôt le module 7 et correspond au chapitre 42 du cours.
Le parcours utilise les dépendances déjà installées et fonctionne hors ligne.
Vous examinerez aussi des exemples de déploiement sans les appliquer.

## Notions rappelées

Un rejeu fournit des observations enregistrées plutôt qu'une infrastructure réelle.
Une observation est une donnée non fiable, même lorsqu'elle ressemble à une instruction.
Une trace décrit les outils utilisés ; elle ne prouve pas que la conclusion est juste.
Un retour arrière exige une autorisation explicite et une confirmation.
Le client de démonstration ne modifie aucun service : son état est en mémoire.
Un rapport incertain distingue les faits disponibles des questions sans réponse.
Un manifeste décrit une configuration ; sa présence ne prouve pas son déploiement.

## Étapes

1. Retrouvez les commandes et les incidents depuis la racine du dépôt :

```bash
.venv/bin/ops-assist --help
.venv/bin/ops-assist eval list
```

Résultat attendu : la liste des commandes et celle des incidents fictifs versionnés.
Ces commandes ne sollicitent aucun modèle.

2. Lancez la démonstration complète dans le bac à sable :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 scripts/demo.sh
```

Résultat attendu : une panne fictive injectée, une lecture de journaux tracée,
une confirmation automatique annoncée, puis un retour arrière sur le client simulé.
La confirmation automatique est réservée à cet exercice ; elle ne remplace pas une décision humaine.
Le modèle scripté suit un scénario déterministe et ne prouve aucune capacité de raisonnement.

3. Examinez la fin du résultat :

Résultat attendu : `insufficient_data` et une cause inconnue pour un autre cas.
Le scénario rappelle que les observations disponibles ne prouvent pas une causalité.
Les données et les limites sont à lire avant toute décision opérationnelle.

4. Consultez les exemples de déploiement sans les appliquer :

```bash
cat deploy/cloudrun/service.yaml
cat deploy/k8s/deployment.yaml deploy/k8s/service.yaml deploy/k8s/networkpolicy.yaml
```

Résultat attendu : une référence à un secret, un conteneur non root et un réseau limité.
Les images sont fictives ; les secrets, le proxy TLS et la configuration restent à fournir.
La carte A2A annonce une adresse locale que le proxy doit réécrire.
La politique Kubernetes bloque les sorties, y compris l'accès au modèle, jusqu'à adaptation.

5. Contrôlez le parcours hors ligne :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 .venv/bin/pytest -q tests/test_release.py
```

Résultat attendu : les vérifications de la démonstration et des manifestes passent.
Elles ne déploient rien et ne vérifient pas un fournisseur réel.

## Exercices

1. Repérez la panne injectée et expliquez pourquoi elle ne démontre pas une cause.
2. Retrouvez la confirmation et décrivez la différence avec une approbation humaine.
3. Relevez deux adaptations nécessaires avant d'utiliser les manifestes.
4. Choisissez une limite du rapport incertain et proposez une observation complémentaire.

## Pour aller plus loin

Hors ligne, lisez `docs/getting-started.md`, `docs/known-limits.md` et la revue de production.
Comparez ensuite les contrôles de sécurité aux observations et aux hypothèses du scénario.

## Bilan du cours

Vous avez construit un agent configurable, relié ses outils à des données fictives,
puis étudié recherche, évaluation, sécurité, traces et exploitation.
Vous savez maintenant distinguer une démonstration reproductible d'une preuve de production.
