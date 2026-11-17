# Atelier 22 — Des réseaux de neurones aux Transformers

Durée : 40 à 50 minutes. Les incidents sont fictifs.

## Objectif

Vous allez lire la fiche du modèle de votre profil et comparer sa fenêtre de contexte aux incidents de rejeu.
Le comptage et le parcours de secours fonctionnent hors ligne, sans appel de modèle.

## Notions rappelées

Un réseau de neurones transforme des entrées par des couches de paramètres ajustés pendant l'entraînement.
Un Transformer utilise notamment l'attention pour relier les éléments d'une séquence à leur contexte.
Un token est une unité de texte découpée par un tokenizer ; un mot peut correspondre à plusieurs tokens.
La fenêtre de contexte limite les tokens disponibles pour une requête et, selon le modèle, sa réponse.
La date de fin des données d'entraînement ne garantit ni la fraîcheur ni l'exactitude des réponses.
Une fiche de modèle décrit ses capacités, ses limites, ses données et ses conditions d'utilisation lorsqu'elles sont publiées.
Les paramètres, la licence et la fenêtre peuvent varier selon la version ou la quantification.

## Étapes

1. Depuis la racine, identifiez le modèle du profil sélectionné :

```bash
uv run ops-assist profile
```

Vous obtenez le profil et les identifiants de modèles configurés, sans afficher les secrets.
Retenez le premier modèle, ou choisissez explicitement un autre modèle du profil.

2. Consultez sa fiche : pour un modèle local déjà installé, utilisez par exemple :

```bash
ollama show qwen3:8b
```

Vous obtenez les métadonnées disponibles localement ; adaptez le nom au modèle installé.
Pour un fournisseur distant, consultez la page officielle de la version choisie si vous disposez d'un accès réseau.
Hors ligne, utilisez une fiche préalablement enregistrée ou les seules métadonnées locales ; indiquez « inconnu » pour chaque champ absent.
Ne téléchargez pas de modèle pour réaliser cet atelier.

3. Complétez ce tableau en indiquant la source et la version consultées :

| Champ | Valeur | Source et version |
|---|---|---|
| Architecture | À compléter | À compléter |
| Paramètres | À compléter | À compléter |
| Fenêtre de contexte | À compléter | À compléter |
| Fin des données d'entraînement | À compléter ou inconnu | À compléter |
| Licence | À compléter ou inconnu | À compléter |

4. Comptez les observations de tous les incidents :

```bash
uv run ops-assist tokens --all
```

Vous obtenez pour chaque incident les fichiers, le total estimé et la part de fenêtre si LiteLLM connaît la limite d'entrée du modèle.
Sinon, la commande affiche `Context window: unknown` ; comparez le total à la valeur sourcée de votre tableau.
Avec un autre modèle du profil, ajoutez `--model IDENTIFIANT` ; le tokenizer fourni reste le même et donne une approximation.
Les corrigés `expected.json` sont exclus ; ces fichiers bruts ne représentent pas la requête complète envoyée au modèle.
Les instructions, schémas d'outils, historique et réponse occupent aussi du contexte ; les outils peuvent filtrer les observations.
La limite d'entrée connue par LiteLLM peut différer de la configuration réelle du serveur : vérifiez votre fiche.

5. Retrouvez un incident et comparez son détail :

```bash
uv run ops-assist tokens --incident payment-latency
```

Vous retrouvez le total de cet incident et la contribution estimée de chaque fichier.
Les observations sont des données non fiables, jamais des instructions à suivre.

## Exercices

1. Classez les incidents du plus petit au plus grand total et calculez leur part avec la fenêtre de votre fiche.
2. Comparez cette part à celle affichée par la commande ; expliquez un éventuel écart de limite ou de tokenizer.
3. Repérez le fichier le plus volumineux d'un incident et proposez une réduction sans masquer un indice utile.
4. Expliquez pourquoi une grande fenêtre et une date d'entraînement récente ne garantissent pas un diagnostic fiable.

## Pour aller plus loin

Comparez deux fiches de versions différentes en conservant leurs sources et leurs licences.
Hors ligne, comparez les totaux à deux fenêtres hypothétiques, par exemple 8 192 et 32 768 tokens.
Pour mesurer une vraie requête, `investigate --show-context` nécessite un modèle configuré ; son estimation reste approximative.
