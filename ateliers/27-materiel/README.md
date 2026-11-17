# Atelier 27 — CPU, GPU, TPU, NPU

## Objectif

Vous interprétez les ressources de votre machine et un conseil de profil.
Cet atelier démarre le module 5 et fonctionne entièrement hors ligne, sans modèle.

## Notions rappelées

Un calcul séquentiel exécute des étapes dépendantes les unes après les autres.
Le calcul parallèle répartit des opérations indépendantes entre plusieurs unités.
La coordination et les dépendances empêchent souvent une accélération proportionnelle.
Un CPU polyvalent excelle dans le contrôle, les branches et les tâches variées.
Un GPU dispose de nombreuses unités adaptées aux calculs parallèles sur des tableaux.
Un TPU est un accélérateur spécialisé pour les opérations tensorielles.
Un NPU est un accélérateur neuronal, souvent intégré à un appareil pour l'inférence locale.
Ces catégories se recouvrent : les performances dépendent de l'architecture et du logiciel.

Les FLOPS mesurent un débit d'opérations flottantes, souvent théorique.
La bande passante mémoire mesure le volume de données transféré par seconde.
Un processeur très rapide peut attendre ses données si la mémoire ne suit pas.
À l'inverse, un calcul dense peut être limité par la puissance de calcul disponible.
La quantité de mémoire indique si le modèle tient ; elle ne prédit pas sa vitesse.

## Étapes hors ligne

Depuis la racine du dépôt, inspectez la machine :

```bash
uv run ops-assist doctor
```

Résultat attendu : nombre de CPU logiques, modèle, RAM totale et disponible,
GPU détecté ou `none`, puis profil conseillé et raisonnement.
Un champ `unknown` précise pourquoi une mesure n'a pas pu être obtenue.
La commande ne modifie pas la configuration et ne contacte aucun service.

Obtenez ensuite le même diagnostic sous forme exploitable par un programme :

```bash
uv run ops-assist doctor --json
```

Résultat attendu : un objet JSON avec `cpu`, `ram`, `gpu` et `advice`.
Les quantités mémoire numériques sont en octets ; `null` indique une mesure GPU absente.
Sur Linux, la RAM provient de `/proc/meminfo` ; sur macOS, elle vient de `sysctl`.
Sur Apple Silicon, le GPU utilise une mémoire unifiée avec le CPU.
La mémoire disponible n'est pas mesurée sur macOS : le conseil reste prudent.
Si `nvidia-smi` est disponible, sa mémoire GPU libre est mesurée avec un délai borné.
L'absence de cet outil ne prouve pas l'absence de tout autre type de GPU.

Le conseil estime un modèle de 7 milliards de paramètres en 4 bits :
environ 0,5 à 0,6 Go par milliard pour les poids, plus 2 Go de marge
pour le contexte et le moteur, soit environ 6,2 Go au total.
Il compare ce seuil à la mémoire GPU libre ou, sans GPU dédié détecté, à la RAM disponible.
Si la mémoire utilisable est inconnue ou insuffisante, il conseille un profil API.
Cette estimation ne garantit ni vitesse, ni compatibilité, ni mémoire réellement suffisante.
Le modèle configuré peut avoir une autre taille et demander une marge différente.

Consultez enfin les profils existants, toujours sans appel modèle :

```bash
uv run ops-assist profile --list
```

Résultat attendu : une liste contenant `local` et `api` parmi les profils configurés.
Le diagnostic ne sélectionne aucun profil et ne télécharge aucun poids.

## Exercices

1. Relevez CPU, RAM et GPU ; quels champs sont inconnus et pourquoi ?
2. Estimez les poids 4 bits de modèles de 3 et 8 milliards de paramètres.
3. Comparez ces estimations à la mémoire disponible et ajoutez 2 Go de marge.
4. Imaginez un calcul séquentiel puis un calcul parallèle limité par la bande passante.

## Pour aller plus loin

Lisez Jouppi et al., « In-Datacenter Performance Analysis of a Tensor Processing Unit », 2017 :
https://arxiv.org/abs/1704.04760
Comparez ses mesures de calcul et de bande passante ; une copie locale permet une lecture hors ligne.
Sans article, reprenez les mesures affichées et expliquez pourquoi elles ne suffisent pas à prédire le débit.
