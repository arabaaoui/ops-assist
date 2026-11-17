# Atelier 28 — Ce que fait CUDA

## Objectif

Vous décrivez la pile logicielle d'un accélérateur et interprétez son utilisation.
Le parcours principal fonctionne hors ligne, sans modèle et sans téléchargement.

## Notions rappelées

Un GPU traite en parallèle de nombreuses opérations, mais le matériel seul ne suffit pas.
Le pilote permet au système d'exploitation de communiquer avec l'accélérateur.
Le runtime fournit aux programmes les fonctions nécessaires pour lancer des calculs.
Un kernel est une fonction exécutée sur l'accélérateur pour traiter les données.
CUDA réunit des outils et un runtime pour programmer certains GPU.
cuBLAS fournit notamment des opérations d'algèbre linéaire optimisées.
cuDNN fournit des primitives optimisées pour les réseaux de neurones.
Un framework utilise ces couches pour exécuter des tenseurs et leurs opérations.
En inférence comme en entraînement, les multiplications de matrices sont fréquentes.
Leur accélération dépend du matériel, des pilotes et de logiciels compatibles.
La mémoire, le transfert des données et le type numérique influencent aussi le débit.

D'autres piles existent : ROCm, Metal et oneAPI ciblent différents matériels.
XLA compile des calculs pour différentes cibles, notamment les TPU.
Triton aide à écrire des kernels optimisés pour des accélérateurs pris en charge.
Ces solutions ne sont pas interchangeables sans vérifier les versions et le matériel.

## Étapes hors ligne

Depuis la racine du dépôt, lancez le diagnostic sans contacter de service :

```bash
uv run ops-assist doctor
```

Résultat attendu : CPU, RAM, GPU, puis `Accelerator: CUDA`, `ROCm`,
`Metal`, `none` ou `unknown`, avec la version du pilote si disponible.
CUDA correspond ici à la présence de l'outil et d'un pilote, pas à une preuve
que le runtime ou les bibliothèques sont installés et compatibles.
Metal est identifié sur Apple Silicon ; les autres configurations peuvent manquer.
ROCm est détecté par `rocm-smi` ; un outil absent ne prouve pas l'absence de matériel.
Les erreurs et les délais dépassés deviennent des valeurs `unknown`.

Pour voir les champs sans modèle ni socket :

```bash
uv run ops-assist doctor --json
```

Résultat attendu : `accelerator` contient `backend` et `version`,
et `ollama` vaut `disabled`. Le conseil matériel reste une estimation.

## Étape facultative en local

Si un serveur Ollama local est déjà démarré et contient un modèle chargé :

```bash
ollama ps
uv run ops-assist doctor --ollama
```

Résultat attendu : `ollama ps` présente les modèles chargés et leur placement.
Le diagnostic affiche `Ollama` avec le nom, la taille et `CPU`, `GPU` ou `CPU/GPU`.
Il compare `size_vram` à `size` : zéro, totalité ou fraction respectivement.
Une liste vide signifie qu'aucun modèle n'est chargé ; `unknown` indique une erreur.
La requête vise uniquement `127.0.0.1:11434`, avec un délai court et sans redirection.
Elle ne télécharge rien et ne lance aucune inférence ; elle est désactivée par défaut.
Sans serveur, utilisez le parcours hors ligne ci-dessus ou les tests simulés :

```bash
OPS_ASSIST_TEST_ASYNC_TICK=1 uv run pytest tests/test_doctor.py -q
```

Résultat attendu : les tests passent sans lancer de processus ni ouvrir de socket.

## Exercices

1. Dessinez la chaîne reliant application, framework, runtime, pilote et matériel.
2. Expliquez pourquoi un pilote présent ne garantit pas une bibliothèque compatible.
3. Pour une taille de 100 et une VRAM de 25, déduisez le placement affiché.
4. Comparez ROCm, Metal et XLA selon leur rôle dans la pile logicielle.

## Pour aller plus loin

Consultez la documentation de votre pile si vous en disposez localement.
Sinon, reprenez le schéma de la pile et indiquez où se situent cuBLAS et cuDNN.
